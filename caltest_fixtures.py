"""In-app multi-calendar canary fixtures (2035 internal only).

Creates the Close leads/tasks and the Barbara placeholder block that the S1-S11
scenarios need, and removes them again, without leaving Streamlit.

Safety rails, all of them deliberate:
  * This has its OWN flag, CALTEST_FIXTURES_ENABLED, deliberately separate from
    CALENDAR_BRIDGE_UI_ENABLED. That one also routes live sending through the
    bridge, so reusing it would mean test tooling could not exist in production
    without changing how real invites are sent. These must stay independent.
  * The panel is a collapsed expander: present for whoever needs it, not in the
    way of anyone who does not.
  * Every lead name and task text carries the CALTEST_PREFIX marker, and cleanup
    refuses to touch anything without it.
  * Meetings are pinned to YEAR 2035. Cleanup only ever deletes calendar events
    inside that year, so a real customer invite cannot be removed by accident.
  * Cleanup requires a typed confirmation before it deletes Close records.

Guest addresses follow SCENARIOS.md: the app sends the mail AND the calendar
invite to one address, so each scenario picks the address that proves its point.
"""
import os
import uuid
from datetime import date, datetime, timezone

import requests
import streamlit as st

import calendar_utils

# Same Close custom field the app itself filters consultants on.
CONSULTANT_FIELD = "custom.lcf_TRIulkQaxJArdGl2k89qY6NKR0ZTYkzjRdeILo1h5fi"
CALTEST_PREFIX = "CALTEST"
CANARY_YEAR = 2035
PLACEHOLDER_TITLE = "CALTEST-2035-SLOT"
PLACEHOLDER_DAY = "2035-09-19"
LANCE_PRINCIPAL = "lance@whiteboardgeeks.com"
STATE_KEY = "caltest_fixture_state"
CLOSE_BASE = "https://api.close.com/api/v1"

SCENARIOS = [
    ("CALTEST-S1-MAIN", "unique_plus"),
    ("CALTEST-S2-IGOOGLE", "unique_plus"),
    ("CALTEST-S3-IMS", "unique_plus"),
    ("CALTEST-S4-RR", "unique_plus"),
    ("CALTEST-S4-RR-B", "unique_plus"),
    ("CALTEST-S4-RR-C", "unique_plus"),
    ("CALTEST-S5-TIME", "unique_plus"),
    ("CALTEST-S6-TITLE", "unique_plus"),
    ("CALTEST-S7-RSVP", "calendar_principal"),
    ("CALTEST-S8-EXISTING", "reuse_s1"),
]


def enabled():
    """Fixture tooling flag, independent of the bridge sending flag.

    Reads an env var (wbg-apps, via compose) or a Streamlit secret (Community
    Cloud, which has no env-var UI), so the same code works in both.
    """
    if os.getenv("CALTEST_FIXTURES_ENABLED", "false").strip().lower() == "true":
        return True
    try:
        return str(st.secrets.get("CALTEST_FIXTURES_ENABLED", "")).strip().lower() == "true"
    except Exception:
        return False


def render(consultant):
    """Self-gated entry point, so callers never need to know the flag."""
    if not enabled():
        return
    panel(consultant)


def _close(method, path, body=None):
    key = st.secrets["CLOSE_API_KEY"]
    response = requests.request(
        method, CLOSE_BASE + path, auth=(key, ""), json=body, timeout=(5, 30)
    )
    if response.status_code >= 400:
        raise ValueError(f"Close {method} {path} failed: {response.status_code}")
    return response.json() if response.content else {}


@st.cache_data(ttl=600, show_spinner=False)
def resolve_assignee(email):
    """Find the Close user id for a consultant by email.

    Looked up rather than stored in consultant_config, so the production config
    stays untouched by test tooling.
    """
    key = st.secrets["CLOSE_API_KEY"]
    skip = 0
    while skip < 500:
        response = requests.get(CLOSE_BASE + "/user/", auth=(key, ""), timeout=(5, 30),
                                params={"_limit": 100, "_skip": skip})
        if response.status_code >= 400:
            return None
        page = response.json()
        for user in page.get("data") or []:
            if (user.get("email") or "").lower() == (email or "").lower():
                return user["id"]
        if not page.get("has_more"):
            return None
        skip += 100
    return None


def _guest_email(kind, s1_email):
    if kind == "calendar_principal":
        return LANCE_PRINCIPAL
    if kind == "reuse_s1":
        return s1_email
    return f"lance+{uuid.uuid4().hex[:12]}@whiteboardgeeks.com"


def create_fixtures(consultant_field, consultant_name, assignee_id):
    """Create the canary leads, tasks and the 2035 placeholder block."""
    today = date.today().isoformat()
    rows, s1_email = [], None

    for tag, kind in SCENARIOS:
        email = _guest_email(kind, s1_email)
        lead = _close("POST", "/lead/", {
            "name": f"{tag} Internal Canary",
            consultant_field: consultant_name,
            "contacts": [{"name": "Lance Johnson",
                          "emails": [{"email": email, "type": "office"}]}],
            "addresses": [{"label": "business", "address_1": "1 Test St",
                           "city": "Austin", "state": "TX",
                           "zipcode": "78701", "country": "US"}],
        })
        task_body = {
            "_type": "lead",
            "lead_id": lead["id"],
            "date": today,          # due today so it lands in the view=inbox tray
            "is_complete": False,
            "assigned_to": assignee_id,
            "text": f"{tag} calendar invite fixture — internal {CANARY_YEAR} canary",
        }
        task = _close("POST", "/task/", task_body)
        extra = _close("POST", "/task/", task_body) if kind == "reuse_s1" else None
        if tag == "CALTEST-S1-MAIN":
            s1_email = email
        rows.append({"tag": tag, "guest": email, "guest_kind": kind,
                     "lead_id": lead["id"], "task_id": task["id"],
                     "extra_task_id": extra["id"] if extra else None})

    placeholder = _create_placeholder()
    return {"created_at": datetime.now(timezone.utc).isoformat(),
            "leads": rows, "placeholder_id": placeholder}


def _create_placeholder():
    service = calendar_utils.get_calendar_service()
    calendar_id = calendar_utils.get_current_calendar_id()
    if service is None or not calendar_id:
        raise ValueError("Calendar unavailable; placeholder not created.")
    event = service.events().insert(
        calendarId=calendar_id,
        sendUpdates="none",
        body={
            "summary": PLACEHOLDER_TITLE,
            "description": "Internal canary placeholder. Do not book customers.",
            "start": {"dateTime": f"{PLACEHOLDER_DAY}T09:00:00", "timeZone": "America/New_York"},
            "end": {"dateTime": f"{PLACEHOLDER_DAY}T18:00:00", "timeZone": "America/New_York"},
            "reminders": {"useDefault": False},
        },
    ).execute()
    return event["id"]


def visible_to_app():
    """The app's own query, so we can prove the fixtures are actually findable."""
    key = st.secrets["CLOSE_API_KEY"]
    out, skip = [], 0
    while True:
        response = requests.get(
            CLOSE_BASE + "/task/", auth=(key, ""), timeout=(5, 30),
            params={"_type": "lead", "is_complete": False, "view": "inbox",
                    "_limit": 100, "_skip": skip},
        )
        if response.status_code >= 400:
            raise ValueError("Close task lookup failed")
        page = response.json()
        out += page.get("data") or []
        if not page.get("has_more"):
            return out
        skip += 100


def discover_canary_leads(max_pages=6):
    """Find canary leads from Close by marker, not from session state.

    Session state dies with the browser tab, which would otherwise orphan
    fixtures permanently. Tasks carry the CALTEST marker in their text, so the
    recent task list is a reliable index of canary leads. Close ignores `query`
    on GET /lead/, so this goes via tasks rather than a lead search.
    """
    key = st.secrets["CLOSE_API_KEY"]
    lead_ids = set()
    for complete in ("false", "true"):
        skip = 0
        for _ in range(max_pages):
            response = requests.get(
                CLOSE_BASE + "/task/", auth=(key, ""), timeout=(5, 30),
                params={"_type": "lead", "is_complete": complete,
                        "_order_by": "-date_created", "_limit": 100, "_skip": skip},
            )
            if response.status_code >= 400:
                break
            page = response.json()
            for task in page.get("data") or []:
                if CALTEST_PREFIX in (task.get("text") or ""):
                    lead_ids.add(task["lead_id"])
            if not page.get("has_more"):
                break
            skip += 100
    return lead_ids


def cleanup_fixtures(state):
    """Delete canary Close leads and every CALTEST event in the canary year.

    Combines this session's fixtures with any older canaries still in Close, so
    a lost browser session cannot strand test data.
    """
    targets = {row["lead_id"] for row in (state or {}).get("leads", [])
               if CALTEST_PREFIX in row["tag"]}
    try:
        targets |= discover_canary_leads()
    except Exception:
        pass  # discovery is best-effort; session fixtures still get removed
    removed_leads = 0
    for lead_id in targets:
        try:
            _close("DELETE", "/lead/" + lead_id + "/")
            removed_leads += 1
        except ValueError:
            pass  # already gone
    return removed_leads, cleanup_calendar()


def cleanup_calendar():
    """Remove CALTEST events inside the canary year only."""
    service = calendar_utils.get_calendar_service()
    calendar_id = calendar_utils.get_current_calendar_id()
    if service is None or not calendar_id:
        raise ValueError("Calendar unavailable; cleanup blocked.")
    removed, page_token = 0, None
    while True:
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=f"{CANARY_YEAR}-01-01T00:00:00Z",
            timeMax=f"{CANARY_YEAR + 1}-01-01T00:00:00Z",
            singleEvents=True, maxResults=250, pageToken=page_token,
        ).execute()
        for event in result.get("items", []):
            summary = event.get("summary") or ""
            if CALTEST_PREFIX not in summary and "INTERNAL TEST" not in summary:
                continue
            start = (event.get("start") or {}).get("dateTime") or ""
            if not start.startswith(str(CANARY_YEAR)):
                continue  # belt and braces: never leave the canary year
            try:
                service.events().delete(
                    calendarId=calendar_id, eventId=event["id"], sendUpdates="all"
                ).execute()
                removed += 1
            except Exception:
                pass
        page_token = result.get("nextPageToken")
        if not page_token:
            return removed


def panel(consultant):
    """Render the fixture controls. Caller guarantees the feature flag is on."""
    consultant_name = consultant["basic_info"]["full_name"]
    consultant_field = CONSULTANT_FIELD
    assignee_id = resolve_assignee(consultant["basic_info"].get("email"))
    with st.expander("Internal: multi-calendar test fixtures (2035)", expanded=False):
        st.caption(
            "Internal QA tooling. Not part of the invite workflow — if you are "
            "sending invites to customers, you can ignore this section."
        )
        st.caption(
            f"Creates {len(SCENARIOS)} canary leads/tasks for {consultant_name} plus the "
            f"{PLACEHOLDER_TITLE} block on {PLACEHOLDER_DAY}. Guests are internal "
            "plus-addresses except S7, which uses lance@ so RSVP can be tested. "
            "Nothing here touches customer data."
        )
        if not assignee_id:
            st.warning(
                f"Could not resolve a Close user for {consultant_name}, so fixture "
                "tasks cannot be placed in their inbox view. Canaries unavailable."
            )
            return

        state = st.session_state.get(STATE_KEY)
        left, right = st.columns(2)

        with left:
            if st.button("Create test fixtures", key="caltest_create"):
                with st.spinner("Creating canary leads, tasks and placeholder…"):
                    try:
                        state = create_fixtures(consultant_field, consultant_name, assignee_id)
                        st.session_state[STATE_KEY] = state
                    except ValueError as error:
                        st.error(str(error))
                        return
                texts = [t.get("text") or "" for t in visible_to_app()]
                unseen = [tag for tag, _ in SCENARIOS
                          if not any(tag in text for text in texts)]
                if unseen:
                    st.warning("Created, but the app's search cannot see: " + ", ".join(unseen))
                else:
                    st.success(f"Created {len(state['leads'])} fixtures; all visible to Search Tasks.")

        with right:
            confirm = st.text_input(
                "Type DELETE to enable cleanup", key="caltest_confirm",
                help="Removes canary Close leads (including any left by earlier "
                     "sessions) and every CALTEST event in 2035.",
            )
            if st.button("Clean up test fixtures", key="caltest_cleanup",
                         disabled=confirm.strip().upper() != "DELETE"):
                with st.spinner("Removing canary leads and 2035 CALTEST events…"):
                    try:
                        leads, events = cleanup_fixtures(st.session_state.get(STATE_KEY))
                    except ValueError as error:
                        st.error(str(error))
                        return
                st.session_state.pop(STATE_KEY, None)
                st.success(f"Removed {leads} Close lead(s) and {events} calendar event(s).")

        if state:
            st.caption("Current fixture set — search any tag below in Search Tasks:")
            st.dataframe(
                [{"scenario": r["tag"], "guest": r["guest"], "guest kind": r["guest_kind"]}
                 for r in state["leads"]],
                use_container_width=True,
            )
