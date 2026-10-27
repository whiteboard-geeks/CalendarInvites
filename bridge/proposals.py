"""Invitee "propose a new time" → a Yes/No event on Barbara's calendar → relayed back.

Detection: Microsoft organizers expose attendee.proposedNewTime in Graph. Google organizers
do not (the API has no proposal field), so the organizer mailbox is read over IMAP for
METHOD:COUNTER calendar attachments. Barbara answers on a private-copy "proposal" event:
Yes moves the original (the invitee gets Google/Outlook's normal update), No keeps the time
and replies in the Instantly thread. She can edit (not drag) the proposal first to counter.
"""
from datetime import datetime, timedelta, timezone
import email
from email.utils import parseaddr
import imaplib
import logging
import re
from zoneinfo import ZoneInfo

import requests

from .config import secret
from .domain import Blocked, identity, instant, time_key
from .providers import ProviderError, iana_zone

log = logging.getLogger("calendar_bridge")
OPEN = ("new", "asked")
BARBARA_ZONE = "America/New_York"  # her calendar setting, read 2026-10-27


def ics_counters(text):
    """Return [{uid, from, start, end}] for METHOD:COUNTER VEVENTs (UTC ISO strings)."""
    text = re.sub(r"\r?\n[ \t]", "", text)  # RFC 5545 line unfolding
    if not re.search(r"^METHOD:COUNTER\s*$", text, re.M | re.I):
        return []
    found = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        props = {}
        for line in block.splitlines():
            name, _, value = line.partition(":")
            key, *params = name.split(";")
            props.setdefault(key.upper(), (dict(p.split("=", 1) for p in params if "=" in p), value.strip()))
        def when(key):
            params, value = props[key]
            dt = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
            zone = "UTC" if value.endswith("Z") else iana_zone(params.get("TZID", "UTC").strip('"'))
            return dt.replace(tzinfo=ZoneInfo(zone)).astimezone(timezone.utc).isoformat()
        try:
            attendee = props.get("ATTENDEE", ({}, ""))[1]
            found.append({"uid": props["UID"][1], "from": attendee.split(":", 1)[-1].lower(),
                          "start": when("DTSTART"), "end": when("DTEND")})
        except (KeyError, ValueError, Blocked):
            continue  # unparseable proposal: Barbara still has the email itself
    return found


def zapmail_passwords():
    found, page = {}, 1
    while page <= 20:
        r = requests.get("https://api.zapmail.ai/api/v2/mailboxes/list", params={"page": page, "limit": 50},
                         headers={"x-auth-zapmail": secret("ZAPMAIL_API_KEY"), "x-service-provider": "GOOGLE",
                                  "User-Agent": "curl/8.0"}, timeout=(5, 30))
        if r.status_code != 200:
            raise Blocked("zapmail_http_" + str(r.status_code))
        data = r.json()["data"]
        for domain in data.get("domains") or []:
            for box in domain.get("mailboxes") or []:
                if box.get("email") and box.get("appPassword"):
                    found[box["email"].lower()] = box["appPassword"]
        if not data.get("nextPage") or page >= data.get("totalPages", page):
            return found
        page += 1
    return found


def imap_counters(mailbox, password, days=14):
    with imaplib.IMAP4_SSL("imap.gmail.com", timeout=30) as imap:
        imap.login(mailbox, password)
        imap.select("INBOX", readonly=True)
        _, ids = imap.search(None, "X-GM-RAW", '"filename:ics newer_than:%dd"' % days)
        found = []
        for num in ids[0].split()[-50:]:
            _, parts = imap.fetch(num, "(BODY.PEEK[])")
            message = email.message_from_bytes(parts[0][1])
            sender = parseaddr(message.get("From", ""))[1].lower()
            for part in message.walk():
                if part.get_content_type() in ("text/calendar", "application/ics") or (part.get_filename() or "").lower().endswith(".ics"):
                    payload = part.get_payload(decode=True) or b""
                    for counter in ics_counters(payload.decode(part.get_content_charset() or "utf-8", "replace")):
                        found.append(dict(counter, **{"from": counter["from"] or sender}))
        return found


def scan(worker):
    """Find new proposals for upcoming outreach meetings, record them and queue the meeting."""
    store = worker.store
    with store.connect() as c:
        rows = c.execute("""SELECT operation, group_name, data FROM bridge_meetings
            WHERE group_name != 'main' AND state NOT IN ('cancelled','sync_conflict')
            AND start_at > now() AND (data->>'linked')::boolean""").fetchall()
    found = []  # (operation, proposal)
    google = {}
    for row in rows:
        data = row["data"]
        if row["group_name"] == "microsoft":
            if any(a.get("responseStatus") in ("tentative", "declined") for a in data["organizer"].get("attendees", [])):
                api = worker.providers.for_account(data["sender_identity"])
                found += [(row["operation"], p) for p in api.proposals(data["organizer"]["id"])]
        else:
            google.setdefault(data["sender_identity"]["email"].lower(), {})[data["uid"]] = row["operation"]
    if google:
        passwords = zapmail_passwords()
        for mailbox, by_uid in google.items():
            if mailbox not in passwords:
                log.warning("proposal_scan_no_imap_password")
                continue
            try:
                counters = imap_counters(mailbox, passwords[mailbox])
            except (imaplib.IMAP4.error, OSError):
                log.warning("proposal_scan_imap_failed")
                continue
            found += [(by_uid[p["uid"]], p) for p in counters if p["uid"] in by_uid]
    for operation, proposal in found:
        record(store, operation, proposal)


def proposal_key(p):
    return "|".join((p["from"], p["start"], p["end"]))


def record(store, operation, proposal):
    with store.meeting_lock(operation) as locked:
        if not locked:
            return  # next scan retries
        meeting = store.get(operation)
        data, key = meeting["data"], proposal_key(proposal)
        current = time_key(data["organizer"])[0][0]
        if (key in data.get("proposals_seen", []) or instant(proposal["start"]) == instant(current)
                or instant(proposal["start"]) <= datetime.now(timezone.utc)
                or instant(proposal["end"]) <= instant(proposal["start"])):
            return
        old = data.get("proposal")
        if old and old["status"] in OPEN:
            old["status"] = "superseded"
            data.setdefault("proposals_done", []).append(old)
            if old.get("event_id"):
                data.setdefault("proposal_cleanup", []).append(old["event_id"])
        data.setdefault("proposals_seen", []).append(key)
        data["proposal"] = dict(proposal, key=key, status="new", original_start=current,
                                found_at=datetime.now(timezone.utc).isoformat())
        store.save(operation, meeting["state"], data, "proposal_received")
        store.enqueue(operation)


def zone_of(data):
    zone = data.get("timezone") or "UTC"
    return BARBARA_ZONE if zone == "UTC" else zone  # the UI stores most meetings as UTC


def fmt(iso, zone):
    dt = instant(iso).astimezone(ZoneInfo(zone))
    return dt.strftime("%A, %B %-d at %-I:%M %p ") + dt.tzname()


def proposal_event(data, main_email):
    p, zone = data["proposal"], zone_of(data)
    return {"iCalUID": "proposal-" + identity(p["key"] + data["uid"])[:40] + "@calendarinvites.whiteboardgeeks.com",
            "summary": "🕒 New time proposed: " + data["title"],
            "description": (p["from"] + " asked to move this meeting from " + fmt(p["original_start"], zone)
                            + " to this time.\n\nYes: move the meeting here. They get the updated invite.\n"
                            "No: keep the original time. They get a short email reply saying so.\n"
                            "Another time: open this event, change the time, Save, then click Yes. (Dragging it does not save.)"),
            "start": {"dateTime": p["start"], "timeZone": zone}, "end": {"dateTime": p["end"], "timeZone": zone},
            "organizer": {"email": data["sender_identity"]["email"]},
            "attendees": [{"email": main_email, "responseStatus": "needsAction"}], "status": "confirmed"}


class Instantly:
    """Decline relay: a reply in the invitee's own Instantly thread, from the same mailbox."""
    base = "https://api.instantly.ai/api/v2"

    def __init__(self, settings):
        self.settings = settings

    def call(self, method, path, **kwargs):
        if method != "GET":
            self.settings.allow_write()
        try:
            r = requests.request(method, self.base + path, headers={"Authorization": "Bearer " + secret("INSTANTLY_API_KEY")},
                                 timeout=(5, 25), **kwargs)
        except requests.RequestException:
            raise Blocked("instantly_transport_uncertain") from None
        if not 200 <= r.status_code < 300:
            raise Blocked("instantly_http_" + str(r.status_code))
        return r.json()

    def reply(self, data, text):
        mailbox = data["sender_identity"]["email"]
        items = self.call("GET", "/emails", params={"lead": data["email"], "eaccount": mailbox, "limit": 20}).get("items", [])
        received = [m for m in items if m.get("ue_type") == 2 and m.get("eaccount", "").lower() == mailbox.lower()]
        if not received:
            raise Blocked("decline_reply_thread_missing")
        last = max(received, key=lambda m: m.get("timestamp_email", ""))
        subject = last.get("subject") or data["title"]
        self.call("POST", "/emails/reply", json={"eaccount": mailbox, "reply_to_uuid": last["id"],
                  "subject": subject if subject.lower().startswith("re:") else "Re: " + subject,
                  "body": {"text": text}})


def decline_text(data):
    p, zone = data["proposal"], zone_of(data)
    return ("Hi,\n\nThanks for suggesting " + fmt(p["start"], zone) + ". Unfortunately that time doesn't work for me, "
            "so let's keep our original time: " + fmt(p["original_start"], zone) + ". Your invitation is unchanged.\n\n"
            "Looking forward to it,\nBarbara")


def advance(worker, meeting):
    """Create, read and resolve Barbara's proposal event. Called under the meeting lock."""
    data, operation = meeting["data"], meeting["operation"]
    p = data.get("proposal")
    if meeting["group_name"] == "main" or not (data.get("proposal_cleanup") or p and p["status"] in OPEN):
        return
    original_api, copy_api, main = worker.provider_pair(meeting)
    def remove(event_id):
        try:
            live = copy_api.get(event_id)
            if live.get("status") != "cancelled":
                copy_api.cancel(live)  # private copy: no email to anyone
        except ProviderError as error:
            if error.status not in (404, 410):
                raise
    if data.get("proposal_cleanup"):
        for event_id in data["proposal_cleanup"]:
            remove(event_id)
        data.pop("proposal_cleanup")
        worker.store.save(operation, meeting["state"], data, "proposal_superseded_removed")
        if not (p and p["status"] in OPEN):
            return
    def close(status):
        if p.get("event_id"):
            remove(p["event_id"])
        p["status"] = status
        data.setdefault("proposals_done", []).append(dict(p))
        data.pop("proposal")
        worker.store.save(operation, meeting["state"], data, "proposal_" + status)
    if meeting["state"] == "cancelled" or instant(p["start"]) <= datetime.now(timezone.utc):
        return close("expired")
    worker.settings.allow_write()
    if p["status"] == "new":
        body = proposal_event(data, main["email"])
        existing = list(copy_api.list(iCalUID=body["iCalUID"]))  # crash-safe retry
        event = existing[0] if existing else copy_api.import_event(body)
        p.update(status="asked", event_id=event["id"])
        worker.store.save(operation, meeting["state"], data, "proposal_asked")
        return
    try:
        event = copy_api.get(p["event_id"])
    except ProviderError as error:
        if error.status not in (404, 410):
            raise
        return close("dismissed")
    if event.get("status") == "cancelled":
        return close("dismissed")
    answer = next((a.get("responseStatus") for a in event.get("attendees", [])
                   if a["email"].lower() == main["email"].lower()), "needsAction")
    if answer == "accepted":
        original = original_api.get(data["organizer"]["id"])
        if original.get("status") == "cancelled":
            return close("expired")
        if time_key(original) != time_key(event):
            # Normal organizer update; the next sync moves Barbara's own copy to match.
            original_api.patch_time(original, event)
        p["accepted_start"] = time_key(event)[0][0]
        return close("accepted")
    if answer == "declined":
        p["status"] = "declining"
        worker.store.save(operation, meeting["state"], data, "proposal_decline_intent")
        try:
            worker.mailer.reply(data, decline_text(data))
            return close("declined")
        except Blocked as error:
            # Never resend blindly: an unknown result may already have reached the invitee.
            p["reply_error"] = str(error)
            return close("declined_reply_failed")
