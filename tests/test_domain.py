from copy import deepcopy
from itertools import combinations
import time

import pytest

from bridge.domain import Blocked, GROUPS, choose, exclusion_reasons, private_body, rsvp_key, sync_action, time_key


def event(hour=10):
    return {"id": "event", "iCalUID": "uid", "etag": '"1"', "organizer": {"email": "sender@example.test"},
            "start": {"dateTime": f"2035-09-09T{hour}:00:00+00:00", "timeZone": "UTC"},
            "end": {"dateTime": f"2035-09-09T{hour}:30:00+00:00", "timeZone": "UTC"},
            "summary": "Intro", "attendees": [{"email": "lead@example.test", "responseStatus": "needsAction"}]}


@pytest.mark.parametrize("groups", [list(c) for n in range(1, 4) for c in combinations(GROUPS, n)])
def test_all_checked_group_combinations_rotate_equally(groups, registry):
    counts, cursors, mailbox_counts = dict.fromkeys(groups, 0), {}, {}
    for index in range(60):
        group, account = choose(groups, index, cursors, registry["senders"], time.time())
        counts[group] += 1
        mailbox_counts[account["id"]] = mailbox_counts.get(account["id"], 0) + 1
        cursors[group] = account["id"]
    assert max(counts.values()) - min(counts.values()) <= 1
    for group in groups:
        values = [mailbox_counts.get(a["id"], 0) for a in registry["senders"] if a["group"] == group]
        assert max(values) - min(values) <= 1


@pytest.mark.parametrize("groups", [[], ["bogus"], ["main", "main"]])
def test_invalid_selection_never_falls_back(groups, registry):
    with pytest.raises(Blocked):
        choose(groups, 0, {}, registry["senders"], time.time())


@pytest.mark.parametrize("change,reason", [({"owner": "april_lowrie"}, "wrong_owner"),
    ({"reviewed": False}, "unreviewed"), ({"used": 100}, "daily_cap_exhausted"),
    ({"disabled": True}, "disabled_for_new_sends"), ({"health": {}}, "stale_health")])
def test_eligibility_exclusions(change, reason, registry):
    account = dict(registry["senders"][1], **change)
    assert reason in exclusion_reasons(account, time.time())


def test_exhausted_group_pauses_instead_of_other_checked_group(registry):
    accounts = [a for a in registry["senders"] if a["group"] != "google"]
    with pytest.raises(Blocked, match="selected_group_unavailable:google"):
        choose(["main", "google"], 1, {}, accounts, time.time())


def test_zero_or_missing_usage_not_sole_gate(registry):
    account = deepcopy(registry["senders"][1])
    account["health"]["usage"] = None
    assert not exclusion_reasons(account, time.time())


def test_instantly_active_without_campaign_is_eligible(registry):
    account = deepcopy(registry["senders"][1])
    account["health"]["active_campaigns"] = []
    account["health"]["approved_assigned_campaigns"] = []
    assert not exclusion_reasons(account, time.time())


@pytest.mark.parametrize("status,warmup,eligible", [
    (1, 1, True),    # active and warming
    (2, 1, True),    # paused for cold email, still a healthy warmed mailbox
    (2, 0, True),    # paused with warmup also paused
    (3, 1, False),   # temporary maintenance
    (-1, 1, False),  # connection error
    (-2, 1, False),  # soft bounce
    (-3, 1, False),  # sending error
    (1, -1, False),  # warmup banned/suspended
    (2, -2, False),
])
def test_paused_is_usable_but_errors_and_bans_are_not(status, warmup, eligible, registry):
    account = deepcopy(registry["senders"][1])
    account["health"]["account_status"] = status
    account["health"]["warmup_status"] = warmup
    account["health"]["connected"] = status == 1
    reasons = exclusion_reasons(account, time.time())
    assert ("instantly_unusable" not in reasons) is eligible


def test_missing_account_status_falls_back_to_connected(registry):
    account = deepcopy(registry["senders"][1])
    account["health"].pop("account_status", None)
    account["health"]["connected"] = False
    assert "instantly_unusable" in exclusion_reasons(account, time.time())
    account["health"]["connected"] = True
    assert "instantly_unusable" not in exclusion_reasons(account, time.time())


def test_prefer_sender_pins_eligible_mailbox(registry):
    from bridge.domain import prefer_sender
    google = next(a for a in registry["senders"] if a["group"] == "google")
    assert prefer_sender(google["email"].upper(), registry["senders"], time.time())["id"] == google["id"]
    assert prefer_sender("nobody@example.test", registry["senders"], time.time()) is None


@pytest.mark.parametrize("o,b,action", [(11,10,"time_barbara"), (10,11,"time_organizer"),
    (11,12,"conflict"), (11,11,"noop"), (10,10,"noop")])
def test_both_time_directions_and_true_conflict(o,b,action):
    assert sync_action(event(), event(), event(o), event(b)) == action


def test_emoji_title_and_rsvp_decline_are_not_time_or_cancellation():
    local, original = event(), event()
    local["summary"] = "✅ Introduction"
    original["attendees"][0]["responseStatus"] = "declined"
    assert sync_action(event(), event(), original, local) == "noop"


def test_cancellation_vs_concurrent_time_edit():
    original = dict(event(), status="cancelled")
    assert sync_action(event(), event(), original, event()) == "cancel_barbara"
    assert sync_action(event(), event(), original, event(11)) == "conflict"


def test_dst_zone_intent_is_retained():
    a = event()
    a["start"] = {"dateTime": "2035-11-04T01:30:00-04:00", "timeZone": "America/New_York"}
    b = deepcopy(a)
    b["start"]["dateTime"] = "2035-11-04T01:30:00-05:00"
    assert time_key(a) != time_key(b)


def test_full_private_representation_retains_live_local_fields():
    original = event()
    original["attendees"][0]["responseStatus"] = "accepted"
    live = dict(event(), summary="✅ Local title", description="Local notes", location="New room",
                reminders={"useDefault": False, "overrides": [{"method": "popup", "minutes": 5}]},
                colorId="4", extendedProperties={"private": {"automation": "keep"}}, privateCopy=True)
    body = private_body(original, "barbara@example.test", live)
    for field in ("summary", "description", "location", "reminders", "colorId", "extendedProperties"):
        assert body[field] == live[field]
    assert body["organizer"] == original["organizer"]
    assert body["attendees"][-1] == {"email": "barbara@example.test", "responseStatus": "accepted"}
    assert "privateCopy" not in body
    assert rsvp_key(body, "barbara@example.test") == [("lead@example.test", "accepted")]


def test_never_invent_barbara_organizer_private_flag():
    with pytest.raises(Blocked, match="external_organizer_required"):
        private_body(event(), "sender@example.test")
    with pytest.raises(Blocked, match="unknown_import_fields"):
        private_body(dict(event(), unexpectedWritable="keep"), "barbara@example.test")
