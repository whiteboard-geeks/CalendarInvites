#!/usr/bin/env python3
"""Create Close leads+tasks Streamlit can actually find.

The app searches Close with `view=inbox`, i.e. the assignee's due/overdue tray.
Fixtures therefore must be assigned to Barbara AND due today, or they never
appear. That is why each task below sets assigned_to + date; the app itself is
unchanged and does no assignee filtering of its own.

Guest email is the calendar attendee AND the invite mail To — the app has one
field (Close contact email). Pick it per scenario:

  plus-address  Unique. Avoids the existing-invite dialog. Mail may arrive, but
                Google Calendar will not put the event on lance@ (attendee ≠
                calendar principal). Use for send/organizer/copy tests (S1–S6).
  lance@        Calendar principal. Needed for RSVP on Lance’s copy (S7).
  reuse S1      Same plus-address as S1 so S8 hits the existing-invite dialog.

Microsoft Zapmail From (display name Barbara Pigg, non-workspace domain) is
often Trash/Spam as Workspace “employee spoofing”. S7 therefore uses Instantly
Google, not Microsoft.
"""
import json, uuid, urllib.request, urllib.parse, base64
from datetime import date, datetime, timezone
from pathlib import Path

CONSULTANT_FIELD = "custom.lcf_TRIulkQaxJArdGl2k89qY6NKR0ZTYkzjRdeILo1h5fi"
BARBARA_USER = "user_8HHUh3SH67YzD8IMakjKoJ9SWputzlUdaihCG95g7as"
LANCE_CALENDAR = "lance@whiteboardgeeks.com"
STATE = Path(__file__).with_name(".state.json")
SCENARIOS = [
    "CALTEST-S1-MAIN",
    "CALTEST-S2-IGOOGLE",
    "CALTEST-S3-IMS",
    "CALTEST-S4-RR",
    "CALTEST-S4-RR-B",
    "CALTEST-S4-RR-C",
    "CALTEST-S5-TIME",
    "CALTEST-S6-TITLE",
    "CALTEST-S7-RSVP",
    "CALTEST-S8-EXISTING",
]


def close_key():
    env = Path.home() / "Projects/bruno-collections/Close API v1/.env"
    for line in env.read_text().splitlines():
        if line.startswith("api_key="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("Close api_key missing")


def call(method, path, body=None):
    auth = base64.b64encode((close_key() + ":").encode()).decode()
    req = urllib.request.Request(
        "https://api.close.com/api/v1" + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": "Basic " + auth, "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def streamlit_visible_tasks():
    """Mirror the app's own query exactly (blind_invite.search_tasks_in_close).

    If a fixture is not in here, the app cannot see it either.
    """
    out, skip = [], 0
    while True:
        q = urllib.parse.urlencode({
            "_type": "lead",
            "is_complete": "false",
            "view": "inbox",
            "_limit": 100,
            "_skip": skip,
        })
        page = call("GET", "/task/?" + q)
        out += page.get("data") or []
        if not page.get("has_more"):
            return out
        skip += 100


def guest_email(tag, s1_email):
    if tag == "CALTEST-S7-RSVP":
        return LANCE_CALENDAR, "calendar_principal"
    if tag == "CALTEST-S8-EXISTING":
        if not s1_email:
            raise SystemExit("S8 needs S1 email (create S1 first)")
        return s1_email, "reuse_s1_existing_dialog"
    return f"lance+{uuid.uuid4().hex[:12]}@whiteboardgeeks.com", "unique_plus"


def main():
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000+00:00")
    rows = []
    s1_email = None
    for tag in SCENARIOS:
        email, guest_kind = guest_email(tag, s1_email)
        lead = call("POST", "/lead/", {
            "name": f"{tag} Internal Canary",
            CONSULTANT_FIELD: "Barbara Pigg",
            "contacts": [{"name": "Lance Johnson", "emails": [{"email": email, "type": "office"}]}],
            "addresses": [{"label": "business", "address_1": "1 Test St", "city": "Austin",
                           "state": "TX", "zipcode": "78701", "country": "US"}],
        })
        task_body = {
            "_type": "lead",
            "lead_id": lead["id"],
            "date": today,
            "is_complete": False,
            "assigned_to": BARBARA_USER,
            "text": f"{tag} calendar invite fixture — internal 2035 canary",
        }
        task = call("POST", "/task/", task_body)
        extra_task_id = None
        if tag == "CALTEST-S8-EXISTING":
            extra = call("POST", "/task/", task_body)
            extra_task_id = extra["id"]
        if task.get("is_complete") or task.get("assigned_to") != BARBARA_USER:
            raise SystemExit(f"task not Streamlit-ready: {tag} {task}")
        if tag == "CALTEST-S1-MAIN":
            s1_email = email
        rows.append({
            "tag": tag,
            "email": email,
            "guest_kind": guest_kind,
            "lead_id": lead["id"],
            "task_id": task["id"],
            "extra_task_id": extra_task_id,
        })
        print(tag, guest_kind, email, task["id"])

    import time as _time
    missing = list(SCENARIOS)
    for _ in range(5):
        texts = [t.get("text") or "" for t in streamlit_visible_tasks()]
        missing = [tag for tag in SCENARIOS if not any(tag in text for text in texts)]
        if not missing:
            break
        _time.sleep(1)
    if missing:
        raise SystemExit(f"App search (view=inbox) would not see: {missing}")
    STATE.write_text(json.dumps({"created_at": now, "leads": rows}, indent=2))
    print("visible_to_app_ok", len(rows), "state", STATE)


if __name__ == "__main__":
    main()
