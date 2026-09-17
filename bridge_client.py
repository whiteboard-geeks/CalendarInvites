"""Streamlit server-side bridge client. Feature flag defaults OFF for every consultant."""
import os
from urllib.parse import quote

import requests
import streamlit as st


def enabled():
    return (os.getenv("CALENDAR_BRIDGE_UI_ENABLED", "false") == "true"
            and st.session_state.get("selected_consultant") == "barbara_pigg")


def request(method, path, body=None):
    # Streamlit secrets are server-side; never render token/HTTP diagnostics.
    try:
        config = st.secrets["calendar_bridge"]
    except (KeyError, FileNotFoundError):
        # Flag on without bridge secrets must degrade, not crash the page.
        raise ValueError("Bridge is not configured for this deployment.") from None
    try:
        response = requests.request(method, config["url"].rstrip("/") + path,
            headers={"Authorization": "Bearer " + config["operator_token"]}, json=body, timeout=(5, 30))
    except requests.RequestException:
        raise ValueError("Bridge unavailable; no legacy fallback. Retry the same task.") from None
    if response.status_code == 404 and method == "GET" and path.startswith("/meetings/"):
        return None
    if response.status_code >= 400:
        reason = response.json().get("detail", "Bridge request blocked") if response.headers.get("content-type", "").startswith("application/json") else "Bridge unavailable"
        raise ValueError(str(reason))
    return response.json()


def controls():
    """Bridge sender controls.

    Fixture tooling is rendered separately by caltest_fixtures, under its own
    flag: this flag also switches live sending onto the bridge, so the two must
    be independently switchable.
    """
    if not enabled():
        return
    try:
        _sender_controls()
    except Exception:
        st.error("Bridge sender controls unavailable.")


def _sender_controls():
    st.subheader("Calendar senders")
    try:
        inventory = request("GET", "/inventory")
    except ValueError as error:
        st.error(str(error))
        st.session_state.bridge_groups = []
        return
    selected = []
    labels = {"main": "BP WBG Calendar", "google": "Instantly Google", "microsoft": "Instantly Microsoft"}
    for key, label in labels.items():
        count = inventory["groups"][key]
        if st.checkbox(f"{label} — {count['eligible']}/{count['total']} eligible", value=key == "main", key="bridge_group_" + key):
            selected.append(key)
    st.session_state.bridge_groups = selected
    if selected:
        cursor = inventory["cursor"]
        st.caption("Next groups: " + " → ".join(labels[selected[(cursor + n) % len(selected)]] for n in range(6)))
    else:
        st.warning("Select at least one group. No fallback sender is used.")
    st.caption("Full Edit/Save was tested on the private copy; native dragging is not verified.")
    if not inventory["outreach_release_ready"]:
        st.warning("Outreach release blocked: safe native RSVP projection is disabled.")
    if inventory["dry_run"] or not inventory["new_sends"]:
        st.info("New bridge sends are disabled. Existing meetings keep their original sender.")
    with st.expander("Sender eligibility, health and operations"):
        st.dataframe(inventory["accounts"], use_container_width=True)
        try:
            meetings = request("GET", "/meetings")
            st.dataframe(meetings, use_container_width=True)
            with st.form("bridge_sender_disable"):
                sender = st.selectbox("Reviewed sender control", [a["id"] for a in inventory["accounts"]])
                disabled = st.checkbox("Disable for new sends", value=True)
                reason = st.text_input("Audit reason")
                if st.form_submit_button("Apply sender control"):
                    if sender and len(reason.strip()) >= 3:
                        request("POST", "/senders/" + quote(sender, safe="") + "/disable", {"disabled": disabled, "reason": reason})
                        st.rerun()
                    else:
                        st.error("Select a sender and enter an audit reason.")
            conflicts = [m["operation"] for m in meetings if m["state"] == "sync_conflict"]
            if conflicts:
                operation = st.selectbox("Review sync conflict", conflicts)
                details = request("GET", "/meetings/" + quote(operation, safe=""))
                conflict = details.get("conflict") or {}
                st.json(conflict)
                if conflict.get("kind") in ("time_or_cancellation", "provider_precondition_failed"):
                    source = st.radio("Use time from", ["barbara", "organizer"])
                    if st.button("Confirm time resolution"):
                        request("POST", "/meetings/" + quote(operation, safe="") + "/resolve-time", {
                            "source": source, "organizer_revision": conflict["organizer"]["etag"],
                            "barbara_revision": conflict["barbara"]["etag"]})
                        st.rerun()
            if st.button("Refresh bridge status"):
                st.rerun()
        except ValueError as error:
            st.error(str(error))


def operation_status(task_id):
    return request("GET", "/meetings/" + quote("barbara_pigg:" + task_id, safe=""))


def submit(task, start, end, title, description, capacity, placeholder_title=None,
           allow_existing=False):
    groups = st.session_state.get("bridge_groups", [])
    if not groups:
        raise ValueError("Select at least one sender group; no fallback sender.")
    body = {"task_id": task["id"], "lead_id": task["lead_id"],
        "email": task["contact_email"], "groups": groups, "start": start, "end": end,
        "timezone": "UTC", "title": title, "description": description, "leads_per_block": capacity,
        "allow_existing": allow_existing}
    # Send the operator's own placeholder name so the bridge discounts the same events the UI
    # does; omitted rather than blank so the server falls back to its default.
    if placeholder_title:
        body["placeholder_title"] = placeholder_title
    return request("POST", "/invites", body)
