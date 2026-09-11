"""Close has no assumed POST idempotency. Ambiguous activity writes require reconciliation."""
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from urllib.parse import quote
import requests

from .config import secret
from .domain import Blocked


class Close:
    def __init__(self, settings, session=None):
        self.settings = settings
        self.http = session or requests.Session()

    def call(self, method, path, body=None, params=None):
        if method != "GET":
            self.settings.allow_write()
        try:
            r = self.http.request(method, "https://api.close.com/api/v1" + path,
                auth=(secret("CLOSE_API_KEY"), ""), json=body, params=params, timeout=(5, 25), allow_redirects=False)
        except requests.RequestException:
            raise Blocked("close_transport_uncertain") from None
        if not 200 <= r.status_code < 300:
            raise Blocked("close_http_" + str(r.status_code))
        return r.json()

    @staticmethod
    def activity_from_email(activity):
        envelope = activity.get("envelope") or {}
        for key in ("from", "sender"):
            rows = envelope.get(key) or []
            if isinstance(rows, list) and rows and rows[0].get("email"):
                return rows[0]["email"].lower()
        _, addr = parseaddr(activity.get("sender") or "")
        return addr.lower() or None

    def recent_from_addresses(self, lead_id, days=30):
        # Newest outgoing sent mail first. Close is the source of truth for sticky sending.
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000000+00:00")
        skip, seen, addresses = 0, set(), []
        while skip < 500:
            rows = self.call("GET", "/activity/email/", params={
                "lead_id": lead_id, "date_created__gt": since, "_limit": 100, "_skip": skip}).get("data") or []
            for activity in rows:
                if activity.get("direction") != "outgoing":
                    continue
                if activity.get("status") not in ("sent", "sent_from_elsewhere") and not activity.get("date_sent"):
                    continue
                email = self.activity_from_email(activity)
                if email and email not in seen:
                    seen.add(email)
                    addresses.append(email)
            if len(rows) < 100:
                break
            skip += 100
        return addresses

    def activity_body(self, meeting):
        config = self.settings.registry["crm"]
        body = {"custom_activity_type_id": config["activity_type"], "lead_id": meeting["data"]["lead_id"],
                "custom." + config["meeting_date_field"]: meeting["data"]["start"][:10],
                "custom." + config["sent_date_field"]: meeting["data"]["sent_date"]}
        if config.get("operation_field"):
            body["custom." + config["operation_field"]] = meeting["operation"]
        return body

    def validate_activity(self, meeting, activity_id):
        result = self.call("GET", "/activity/custom/" + quote(activity_id, safe="") + "/")
        expected = self.activity_body(meeting)
        for key, value in expected.items():
            actual = result.get(key)
            if key.startswith("custom."):
                actual = result.get("custom", {}).get(key[7:], actual)
            if actual != value:
                raise Blocked("close_activity_does_not_match_operation")
        if result.get("status", "published") != "published":
            raise Blocked("close_activity_not_published")
        return result["id"]

    def advance(self, meeting, store):
        data, operation = meeting["data"], meeting["operation"]
        phase = data.get("crm_phase", "not_started")
        if phase in ("activity_intent", "uncertain"):
            data["crm_phase"] = "uncertain"
            store.save(operation, "crm_uncertain", data, "crm_reconciliation_required")
            raise Blocked("crm_uncertain")
        if phase == "not_started":
            data["sent_date"] = datetime.now(timezone.utc).date().isoformat()
            data["crm_phase"] = "activity_intent"
            store.save(operation, "crm_pending", data, "crm_activity_intent")
            # Any exception or process loss after intent is conservative uncertainty.
            result = self.call("POST", "/activity/custom/", self.activity_body(meeting))
            if not result.get("id"):
                raise Blocked("crm_activity_missing_id")
            data.update(crm_phase="activity_confirmed", activity_id=result["id"])
            store.save(operation, "crm_pending", data, "crm_activity_confirmed")
        if data["crm_phase"] == "activity_confirmed":
            self.call("PUT", "/task/" + quote(meeting["task_id"], safe="") + "/", {"is_complete": True})
            data["crm_phase"] = "complete"
            store.save(operation, "complete", data, "crm_task_complete")
