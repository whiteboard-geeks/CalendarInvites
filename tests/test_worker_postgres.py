from copy import deepcopy
import pytest

from bridge.domain import Blocked
from bridge.providers import ProviderError
from bridge.worker import Worker


def linked(worker, command, group="google"):
    row = worker.store.reserve(dict(command, groups=[group]), lambda *_: ([], 8))
    worker.process(row["operation"])
    return worker.store.get(row["operation"])


def pair(worker, meeting):
    o, b, _ = worker.provider_pair(meeting)
    return o, b, meeting["data"]["organizer"]["id"], meeting["data"].get("barbara", {}).get("id")


def later(event, hour):
    return {"start": {"dateTime": f"2035-09-09T{hour}:00:00+00:00", "timeZone": "UTC"},
            "end": {"dateTime": f"2035-09-09T{hour}:30:00+00:00", "timeZone": "UTC"}}


@pytest.mark.parametrize("group", ["google", "microsoft", "main"])
def test_one_original_private_copy_or_main_no_copy(worker, command, group):
    meeting = linked(worker, command, group)
    assert meeting["state"] == "complete"
    o,b,oi,bi = pair(worker, meeting)
    assert o.writes.count("create") == 1
    if group == "main":
        assert bi is None
        assert o.writes == ["create"]
    else:
        assert b.events[bi]["privateCopy"] is True
        assert not any(a["email"] == "main@example.test" for a in o.events[oi]["attendees"])
        assert b.events[bi]["organizer"] == o.events[oi]["organizer"]
    worker.process(meeting["operation"])
    assert o.writes.count("create") == 1
    assert worker.crm.calls == 1


@pytest.mark.parametrize("failure", ["timeout", "copy"])
def test_restart_repairs_partial_send_without_resending_or_early_close(worker, command, failure):
    row = worker.store.reserve(command, lambda *_: ([],8))
    o,b,_,_ = (*worker.provider_pair(row)[:2],None,None)
    if failure == "timeout":
        o.create_timeout = True
    else:
        b.copy_failure = True
    with pytest.raises(Blocked):
        worker.process(row["operation"])
    assert worker.crm.calls == 0
    restarted = Worker(worker.settings, worker.store, worker.providers, worker.inventory, worker.crm)
    restarted.process(row["operation"])
    assert o.writes.count("create") == 1
    assert b.writes.count("import") == 1
    assert worker.store.get(row["operation"])["state"] == "complete"


@pytest.mark.parametrize("side", ["organizer", "barbara"])
def test_both_time_directions_duplicate_out_of_order_reconciliation(worker, command, side):
    meeting = linked(worker, command)
    o,b,oi,bi = pair(worker,meeting)
    source, id = (o,oi) if side == "organizer" else (b,bi)
    source.update(id, **later(source.events[id],15))
    b.update(bi, summary="✅ Local emoji")
    for _ in range(4):  # no notification payload used, always fetch fresh authoritative sides
        worker.process(meeting["operation"])
    assert o.events[oi]["start"] == b.events[bi]["start"]
    assert b.events[bi]["summary"] == "✅ Local emoji"
    assert o.events[oi]["summary"] == "Introduction"
    assert o.writes.count("time") + b.writes.count("time") == 1
    assert o.events[oi]["iCalUID"] == meeting["data"]["organizer"]["iCalUID"]


def test_conflicting_concurrent_edits_pause_no_last_writer_wins(worker, command):
    meeting = linked(worker,command)
    o,b,oi,bi = pair(worker,meeting)
    o.update(oi, **later(o.events[oi],15))
    b.update(bi, **later(b.events[bi],16))
    worker.process(meeting["operation"])
    assert worker.store.get(meeting["operation"])["state"] == "sync_conflict"
    assert "time" not in o.writes + b.writes


@pytest.mark.parametrize("status", ["needsAction", "accepted", "tentative", "declined"])
def test_native_rsvp_mapping_decline_not_cancellation(worker, command, status):
    meeting = linked(worker,command)
    o,b,oi,bi = pair(worker,meeting)
    o.update(oi, attendees=[{"email": "lead@example.test", "responseStatus": status}])
    worker.process(meeting["operation"])
    assert b.events[bi]["attendees"][0].get("responseStatus", "needsAction") == status
    assert "cancel" not in o.writes + b.writes


def test_emoji_only_generates_zero_outbound_updates(worker, command):
    meeting = linked(worker,command)
    o,b,oi,bi = pair(worker,meeting)
    before = len(o.writes) + len(b.writes)
    b.update(bi, summary="✅🙂 Local automation")
    worker.process(meeting["operation"])
    assert len(o.writes) + len(b.writes) == before


@pytest.mark.parametrize("side", ["organizer", "barbara"])
def test_confirmed_cancellation_both_directions(worker, command, side):
    meeting = linked(worker,command)
    o,b,oi,bi = pair(worker,meeting)
    source,id = (o,oi) if side == "organizer" else (b,bi)
    source.update(id,status="cancelled")
    worker.process(meeting["operation"])
    assert worker.store.get(meeting["operation"])["state"] == "cancelled"
    assert o.events[oi]["status"] == b.events[bi]["status"] == "cancelled"


@pytest.mark.parametrize("error", [403,404,500])
def test_auth_error_unknown_404_not_partner_cancellation(worker, command, error):
    meeting = linked(worker,command)
    o,b,oi,bi = pair(worker,meeting)
    o.auth_error = error
    with pytest.raises(ProviderError):
        worker.process(meeting["operation"])
    assert "cancel" not in b.writes


def test_retired_new_sender_keeps_servicing_existing_meetings(worker, command):
    meeting = linked(worker,command)
    worker.store.disable(meeting["sender"],True,"retired")
    o,b,oi,bi = pair(worker,meeting)
    b.update(bi, **later(b.events[bi],15))
    worker.process(meeting["operation"])
    assert "time" in o.writes


def test_rsvp_capability_gate_exposes_degraded_not_silent_success(worker,command):
    meeting = linked(worker,command)
    o,b,oi,bi = pair(worker,meeting)
    b.cas = False
    o.update(oi, attendees=[{"email": "lead@example.test", "responseStatus": "accepted"}])
    worker.process(meeting["operation"])
    assert worker.store.get(meeting["operation"])["state"] == "rsvp_degraded"
    assert "rsvp" not in b.writes


def audit_rows(store, operation):
    with store.connect() as c:
        row = c.execute("SELECT count(*) AS n, max(m.updated_at) AS updated FROM bridge_audit a JOIN bridge_meetings m "
                        "ON m.operation=a.operation WHERE a.operation=%s", (operation,)).fetchone()
    return row["n"], row["updated"]


def test_unchanged_polls_write_no_audit_or_updated_at(worker, command):
    meeting = linked(worker, command)
    o, b, oi, bi = pair(worker, meeting)
    before = audit_rows(worker.store, meeting["operation"])
    for _ in range(5):
        worker.process(meeting["operation"])
    assert audit_rows(worker.store, meeting["operation"]) == before
    assert worker.store.get(meeting["operation"])["state"] == "complete"
    b.update(bi, summary="✅ Local emoji")
    worker.process(meeting["operation"])
    after_change = audit_rows(worker.store, meeting["operation"])
    assert after_change[0] == before[0] + 1
    worker.process(meeting["operation"])
    assert audit_rows(worker.store, meeting["operation"]) == after_change


def test_persistent_rsvp_degraded_is_recorded_once(worker, command):
    meeting = linked(worker, command)
    o, b, oi, bi = pair(worker, meeting)
    b.cas = False
    o.update(oi, attendees=[{"email": "lead@example.test", "responseStatus": "accepted"}])
    worker.process(meeting["operation"])
    degraded = audit_rows(worker.store, meeting["operation"])
    for _ in range(3):
        worker.process(meeting["operation"])
    assert audit_rows(worker.store, meeting["operation"]) == degraded
    assert worker.store.get(meeting["operation"])["state"] == "rsvp_degraded"


def due_in_seconds(store, operation):
    with store.connect() as c:
        return c.execute("SELECT extract(epoch FROM due_at-now()) AS s FROM bridge_jobs WHERE operation=%s",
                         (operation,)).fetchone()["s"]


def test_live_meetings_poll_at_cadence_settled_rows_daily(worker, command):
    row = worker.store.reserve(command, lambda *_: ([], 8))
    assert worker.tick()
    assert 0 < due_in_seconds(worker.store, row["operation"]) <= worker.settings.poll_seconds
    o, b, oi, bi = pair(worker, worker.store.get(row["operation"]))
    o.update(oi, status="cancelled")
    worker.store.enqueue(row["operation"])
    assert worker.tick()
    assert worker.store.get(row["operation"])["state"] == "cancelled"
    assert due_in_seconds(worker.store, row["operation"]) > 86000
    worker.store.enqueue(row["operation"])  # operator reconcile still forces one fresh pass
    assert worker.tick()
    assert due_in_seconds(worker.store, row["operation"]) > 86000
    # Reservation-time future checks live in the API; a meeting whose end has passed settles.
    past = worker.store.reserve(dict(command, task_id="task_past", start="2020-01-01T14:00:00+00:00",
                                     end="2020-01-01T14:30:00+00:00"), lambda *_: ([], 8))
    assert worker.tick()
    assert worker.store.get(past["operation"])["state"] == "complete"
    assert due_in_seconds(worker.store, past["operation"]) > 86000


def test_crash_after_private_import_repairs_without_second_invite(worker, command, monkeypatch):
    row = worker.store.reserve(command, lambda *_: ([], 8))
    save = worker.store.save
    def crash(operation, state, data, action):
        if action == "events_linked":
            raise RuntimeError("simulated process loss after provider confirmation")
        save(operation, state, data, action)
    monkeypatch.setattr(worker.store, "save", crash)
    with pytest.raises(RuntimeError):
        worker.process(row["operation"])
    monkeypatch.setattr(worker.store, "save", save)
    worker.process(row["operation"])
    result = worker.store.get(row["operation"])
    o, b, _, _ = pair(worker, result)
    assert o.writes.count("create") == 1
    assert b.writes.count("import") == 1
    assert result["data"]["links"]["organizer"]["iCalUID"] == result["data"]["links"]["barbara"]["iCalUID"]
    assert result["state"] == "complete"
