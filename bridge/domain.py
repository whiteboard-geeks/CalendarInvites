"""Managed-event field contract. No provider revisions are ordered across vendors."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from zoneinfo import ZoneInfo

GROUPS = ("main", "google", "microsoft")
BARBARA = "barbara_pigg"


class Blocked(Exception):
    """Safe, non-sensitive operator reason; never wrap raw provider responses."""


def identity(operation):
    return sha256(operation.encode()).hexdigest()  # Google base32hex-compatible ID


def instant(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise Blocked("timezone_required")
    return dt.astimezone(timezone.utc)


def time_key(event):
    def part(value):
        if "date" in value:
            raise Blocked("all_day_not_supported")
        zone = value.get("timeZone", "UTC")
        dt = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(zone))
        return (dt.astimezone(timezone.utc).isoformat(), zone)
    return part(event["start"]), part(event["end"])


def rsvp_key(event, local_email):
    return sorted((a["email"].lower(), a.get("responseStatus", "needsAction"))
                  for a in event.get("attendees", []) if a["email"].lower() != local_email.lower())


def sync_action(old_o, old_b, organizer, barbara):
    """Return a time/cancellation action; titles and emoji are deliberately local in v1."""
    oc, bc = organizer.get("status") == "cancelled", barbara.get("status") == "cancelled"
    if oc and bc:
        return "cancelled"
    if oc or bc:
        surviving, old = (barbara, old_b) if oc else (organizer, old_o)
        if time_key(surviving) != time_key(old):
            return "conflict"
        return "cancel_barbara" if oc else "cancel_organizer"
    ot, bt = time_key(organizer), time_key(barbara)
    changed_o, changed_b = ot != time_key(old_o), bt != time_key(old_b)
    if changed_o and changed_b and ot != bt:
        return "conflict"
    if ot == bt:
        return "noop"
    if changed_o:
        return "time_barbara"
    if changed_b:
        return "time_organizer"
    return "conflict"  # unexplained initial divergence is not an arrival-order decision


# Google import is full-representation. Unknown future writable fields fail closed.
IMPORT_FIELDS = frozenset("summary description location start end attendees organizer iCalUID "
    "reminders colorId extendedProperties visibility transparency recurrence recurringEventId "
    "originalStartTime sequence status attachments conferenceData source guestsCanInviteOthers "
    "guestsCanSeeOtherGuests guestsCanModify endTimeUnspecified eventType".split())
READ_ONLY_FIELDS = frozenset("kind etag id htmlLink created updated creator privateCopy locked "
    "hangoutLink attendeesOmitted anyoneCanAddSelf".split())


def private_body(original, local_email, live=None):
    if original["organizer"]["email"].lower() == local_email.lower():
        raise Blocked("external_organizer_required")
    source = live if live is not None else original
    if source.get("recurrence") or source.get("recurringEventId") or source.get("eventType", "default") != "default":
        raise Blocked("unsupported_event_representation")
    unknown = set(source) - IMPORT_FIELDS - READ_ONLY_FIELDS
    if unknown:
        raise Blocked("unknown_import_fields")
    body = {k: deepcopy(v) for k, v in source.items() if k in IMPORT_FIELDS}
    body.update(iCalUID=original["iCalUID"], organizer=deepcopy(original["organizer"]))
    body["attendees"] = [deepcopy(a) for a in original.get("attendees", [])
                         if a["email"].lower() != local_email.lower()]
    body["attendees"].append({"email": local_email, "responseStatus": "accepted"})
    return body


# Instantly account status: 1=active, 2=paused, 3=temporary maintenance,
# negatives are connection/bounce/sending errors.
#
# A paused mailbox is paused for COLD EMAIL. It is still healthy, warmed and
# authenticated, and hosting a calendar invite is not sending a campaign.
# Requiring status 1 conflated the two, so deliberate cold-email pauses looked
# like broken senders. Error states and maintenance still exclude, as does
# warmup that is banned or suspended.
INSTANTLY_CALENDAR_OK = (1, 2)


def instantly_usable(health):
    status = health.get("account_status")
    if status is None:
        # Health recorded before account_status existed: fall back to the old
        # signal rather than silently widening eligibility on missing data.
        return health.get("connected") is True
    if status not in INSTANTLY_CALENDAR_OK:
        return False
    warmup = health.get("warmup_status")
    return warmup is None or warmup >= 0


def exclusion_reasons(account, now, freshness=900):
    reasons = []
    for key, reason in (("reviewed", "unreviewed"), ("ready", "readiness_unreviewed"),
                        ("calendar_write_reviewed", "calendar_grant_unreviewed")):
        if account.get(key) is not True:
            reasons.append(reason)
    if account.get("owner") != BARBARA:
        reasons.append("wrong_owner")
    if account.get("disabled", False):
        reasons.append("disabled_for_new_sends")
    if account.get("group") not in GROUPS or account.get("provider") not in ("google", "microsoft"):
        reasons.append("unknown_provider")
    if not account.get("tenant") or not account.get("subject") or not account.get("calendar_id"):
        reasons.append("missing_provider_identity")
    health = account.get("health", {})
    if now - health.get("checked_at", 0) > freshness:
        reasons.append("stale_health")
    if health.get("calendar_auth") is not True:
        reasons.append("calendar_auth_unhealthy")
    if account.get("group") != "main":
        if not instantly_usable(health):
            reasons.append("instantly_unusable")
        if health.get("provider") != account.get("provider"):
            reasons.append("provider_unverified")
        # Instantly account status 1 is enough; a running campaign is not required.
        if health.get("setup_pending") is not False:
            reasons.append("setup_incomplete_or_unknown")
    if account.get("daily_cap", 0) <= account.get("used", 0):
        reasons.append("daily_cap_exhausted")
    return reasons


def choose(groups, cursor, mailbox_cursors, accounts, now):
    selected = [g for g in GROUPS if g in groups]
    if not selected or len(set(groups)) != len(groups) or set(groups) - set(GROUPS):
        raise Blocked("select_at_least_one_valid_group")
    group = selected[cursor % len(selected)]
    eligible = sorted((a for a in accounts if a["group"] == group and not exclusion_reasons(a, now)),
                      key=lambda a: a["id"])
    if not eligible:
        raise Blocked("selected_group_unavailable:" + group)
    last = mailbox_cursors.get(group, "")
    sender = next((a for a in eligible if a["id"] > last), eligible[0])
    return group, sender


def prefer_sender(email, accounts, now):
    email = (email or "").lower()
    matches = [a for a in accounts if a.get("email", "").lower() == email and not exclusion_reasons(a, now)]
    return matches[0] if matches else None
