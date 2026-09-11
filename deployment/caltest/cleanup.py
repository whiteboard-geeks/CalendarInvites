#!/usr/bin/env python3
"""Delete Close canary leads (and their tasks). Optionally cancel 2035 CALTEST calendar events."""
import json, os, urllib.request, base64, subprocess
from pathlib import Path

STATE = Path(__file__).with_name(".state.json")
BARBARA = "barbara.pigg@whiteboardgeeks.com"


def close_key():
    env = Path.home() / "Projects/bruno-collections/Close API v1/.env"
    for line in env.read_text().splitlines():
        if line.startswith("api_key="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("Close api_key missing")


def close_call(method, path):
    auth = base64.b64encode((close_key() + ":").encode()).decode()
    req = urllib.request.Request(
        "https://api.close.com/api/v1" + path,
        headers={"Authorization": "Basic " + auth},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def calendar_cleanup():
    token = subprocess.check_output(
        ["/Users/work/.claude/venv/bin/python", "/Users/work/.claude/google-sa-token.py", BARBARA],
        text=True, timeout=30).strip()
    import urllib.parse
    time_min, time_max = "2035-09-16T00:00:00Z", "2035-09-19T00:00:00Z"
    url = ("https://www.googleapis.com/calendar/v3/calendars/" + urllib.parse.quote(BARBARA)
           + "/events?timeMin=" + time_min + "&timeMax=" + time_max + "&singleEvents=true&maxResults=50")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=25) as r:
        items = json.loads(r.read()).get("items", [])
    deleted = 0
    for ev in items:
        summary = ev.get("summary") or ""
        if "CALTEST" not in summary and "INTERNAL TEST" not in summary:
            continue
        req = urllib.request.Request(
            "https://www.googleapis.com/calendar/v3/calendars/" + urllib.parse.quote(BARBARA)
            + "/events/" + ev["id"] + "?sendUpdates=all",
            headers={"Authorization": "Bearer " + token}, method="DELETE")
        try:
            urllib.request.urlopen(req, timeout=20)
            deleted += 1
        except urllib.error.HTTPError as e:
            print("calendar_delete", ev["id"], e.code)
    print("calendar_deleted", deleted)


def main():
    if STATE.exists():
        rows = json.loads(STATE.read_text()).get("leads", [])
        for row in rows:
            code = close_call("DELETE", "/lead/" + row["lead_id"] + "/")
            print("lead", row["tag"], row["lead_id"], code)
        STATE.unlink()
    else:
        print("no state file")
    calendar_cleanup()


if __name__ == "__main__":
    main()
