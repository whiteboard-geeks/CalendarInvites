"""Real Calendar/Graph HTTP adapters. Transports are injectable for offline tests.

Unknown 404, authorization failures and timeouts are never deletion evidence.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import time
from urllib.parse import quote
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account, credentials as oauth_credentials

from .config import secret
from .domain import Blocked, private_body


class ProviderError(Blocked):
    def __init__(self, status):
        self.status = status
        super().__init__("provider_http_" + str(status))


class Transport:
    def __init__(self, token, base, writes_allowed=True):
        self.token, self.base, self.writes_allowed = token, base, writes_allowed
        self.session = requests.Session()

    def call(self, method, path, *, body=None, params=None, headers=None):
        if method != "GET" and not self.writes_allowed:
            raise Blocked("dry_run")
        try:
            token = self.token()
        except Exception:
            raise Blocked("provider_auth_unavailable") from None
        h = {"Authorization": "Bearer " + token, "User-Agent": "CalendarInvites-Bridge/1.0"}
        h.update(headers or {})
        try:
            r = self.session.request(method, self.base + path, json=body, params=params,
                                     headers=h, timeout=(5, 25), allow_redirects=False)
        except requests.RequestException:
            raise Blocked("provider_transport_uncertain") from None
        if not 200 <= r.status_code < 300:
            raise ProviderError(r.status_code)
        return r.json() if r.content else {}


def google_oauth_info(config, email):
    # Instantly Google: one file, many mailbox refresh tokens. Main calendar stays a SA or single user.
    if config.get("type") == "authorized_user_map":
        entry = (config.get("accounts") or {}).get((email or "").lower()) or {}
        if not entry.get("refresh_token"):
            raise Blocked("provider_auth_unavailable")
        return {"client_id": config["client_id"], "client_secret": config["client_secret"],
                "refresh_token": entry["refresh_token"],
                "token_uri": config.get("token_uri", "https://oauth2.googleapis.com/token")}
    return config


def google_token(account):
    # Credentials are opened only in the deployed server, never in Streamlit/tests.
    config = json.loads(secret(account["credential_secret"]))
    if config.get("type") == "service_account":
        credential = service_account.Credentials.from_service_account_info(
            config, scopes=["https://www.googleapis.com/auth/calendar"]
        ).with_subject(account["subject"])
    else:
        credential = oauth_credentials.Credentials.from_authorized_user_info(
            google_oauth_info(config, account.get("email")),
            scopes=["https://www.googleapis.com/auth/calendar"])
    def token():
        if not credential.valid:
            credential.refresh(Request())
        return credential.token
    return token


def graph_token(account):
    cached = {}
    def token():
        if cached.get("expires", 0) > time.time() + 60:
            return cached["token"]
        config = json.loads(secret(account["credential_secret"]))
        try:
            r = requests.post("https://login.microsoftonline.com/" + quote(account["tenant"], safe="") + "/oauth2/v2.0/token",
                data={"client_id": config["client_id"], "client_secret": config["client_secret"],
                      "grant_type": "client_credentials", "scope": "https://graph.microsoft.com/.default"}, timeout=(5, 25))
            if r.status_code != 200:
                raise Blocked("graph_auth_failed")
            result = r.json()
            cached.update(token=result["access_token"], expires=time.time() + result["expires_in"])
            return cached["token"]
        except requests.RequestException:
            raise Blocked("graph_auth_unavailable") from None
    return token


def revision(event):
    value = event.get("etag")
    if not value:
        raise Blocked("missing_provider_revision")
    return {"If-Match": value}


class Google:
    provider = "google"
    def __init__(self, account, transport, import_cas_verified=True):
        self.account, self.http = account, transport
        self.base = "/calendars/" + quote(account["calendar_id"], safe="")
        self.import_cas_verified = import_cas_verified

    def auth_health(self):
        cal = self.http.call("GET", "/users/me/calendarList/" + quote(self.account["calendar_id"], safe=""))
        return cal.get("accessRole") in ("owner", "writer")

    def get(self, event_id):
        return self.http.call("GET", self.base + "/events/" + quote(event_id, safe=""))

    def list(self, **params):
        token, seen = None, set()
        while True:
            page = self.http.call("GET", self.base + "/events", params=dict(params, maxResults=250, **({"pageToken": token} if token else {})))
            yield from page.get("items", [])
            token = page.get("nextPageToken")
            if not token:
                return
            if token in seen:
                raise Blocked("provider_pagination_loop")
            seen.add(token)

    def create(self, stable_id, body):
        # Reconcile the deterministic ID before every retry on the same account.
        try:
            return self.get(stable_id)
        except ProviderError as e:
            if e.status != 404:
                raise
        try:
            result = self.http.call("POST", self.base + "/events", body=dict(body, id=stable_id), params={"sendUpdates": "all"})
        except ProviderError as e:
            if e.status != 409:
                raise
            result = self.get(stable_id)
        return result

    def find_copy(self, uid):
        matches = list(self.list(iCalUID=uid, showDeleted="true"))
        if any(e.get("status") == "cancelled" for e in matches):
            raise Blocked("copy_cancelled_during_creation")
        if len(matches) > 1:
            raise Blocked("multiple_uid_copies")
        return matches[0] if matches else None

    def ensure_copy(self, original, local_email):
        existing = self.find_copy(original["iCalUID"])
        if existing:
            self.assert_copy(existing, original, local_email)
            return existing
        result = self.http.call("POST", self.base + "/events/import", body=private_body(original, local_email),
                                params={"supportsAttachments": "true", "conferenceDataVersion": 1})
        result = self.get(result["id"])
        self.assert_copy(result, original, local_email)
        return result

    @staticmethod
    def assert_copy(result, original, local_email):
        if (result.get("privateCopy") is not True or result.get("iCalUID") != original["iCalUID"]
            or result.get("organizer", {}).get("email", "").lower() != original["organizer"]["email"].lower()
            or result["organizer"]["email"].lower() == local_email.lower()):
            raise Blocked("private_copy_invariant_failed")
        if not any(a["email"].lower() == local_email.lower() and a.get("responseStatus") == "accepted"
                   for a in result.get("attendees", [])):
            raise Blocked("missing_local_accepted_attendee")

    def project_rsvp(self, original, live, local_email):
        if not self.import_cas_verified:
            raise Blocked("rsvp_degraded_import_cas_unproven")
        # Real stale/current ETags were independently verified 2026-09-09. On 412,
        # rebase RSVP ONLY onto the latest complete local representation (bounded).
        for attempt in range(3):
            try:
                result = self.http.call("POST", self.base + "/events/import",
                    body=private_body(original, local_email, live), headers=revision(live),
                    params={"supportsAttachments": "true", "conferenceDataVersion": 1})
                break
            except ProviderError as error:
                if error.status != 412:
                    raise
                if attempt == 2:
                    raise Blocked("rsvp_degraded_concurrent_local_edits") from None
                fresh = self.get(live["id"])
                self.assert_copy(fresh, original, local_email)
                if fresh.get("status") == "cancelled":
                    raise Blocked("rsvp_degraded_local_cancelled")
                emails = lambda e: sorted(a["email"].lower() for a in e.get("attendees", []))
                if emails(fresh) != emails(live):
                    raise Blocked("rsvp_degraded_concurrent_guest_edit")
                live = fresh
        if result.get("id") != live["id"]:
            raise Blocked("import_changed_event_identity")
        result = self.get(live["id"])
        self.assert_copy(result, original, local_email)
        return result

    def patch_time(self, event, source):
        return self.http.call("PATCH", self.base + "/events/" + quote(event["id"], safe=""),
            body={"start": source["start"], "end": source["end"]}, headers=revision(event),
            params={"sendUpdates": "none" if event.get("privateCopy") else "all"})

    def cancel(self, event):
        self.http.call("DELETE", self.base + "/events/" + quote(event["id"], safe=""),
                       headers=revision(event), params={"sendUpdates": "none" if event.get("privateCopy") else "all"})
        return dict(event, status="cancelled")  # confirmed conditional DELETE, not inferred 404


GRAPH_OPERATION_PROPERTY = "String {7ca9b8f0-90d8-4e8b-91cd-8805c12bfb51} Name CalendarInvitesOperation"

GRAPH_RSVP = {"accepted": "accepted", "declined": "declined", "tentativelyAccepted": "tentative",
              "notResponded": "needsAction", "none": "needsAction", "organizer": "accepted"}


WINDOWS_ZONES = {"UTC": "UTC", "Eastern Standard Time": "America/New_York",
                 "Central Standard Time": "America/Chicago", "Mountain Standard Time": "America/Denver",
                 "Pacific Standard Time": "America/Los_Angeles", "US Mountain Standard Time": "America/Phoenix",
                 "Alaskan Standard Time": "America/Anchorage", "Hawaiian Standard Time": "Pacific/Honolulu"}


def iana_zone(zone):
    zone = WINDOWS_ZONES.get(zone, zone)
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise Blocked("unsupported_provider_timezone") from None
    return zone


def graph_time(value):
    zone = iana_zone(value.get("timeZone", "UTC"))
    dt = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
    dt = dt.replace(tzinfo=ZoneInfo(zone)) if dt.tzinfo is None else dt.astimezone(ZoneInfo(zone))
    return {"dateTime": dt.replace(tzinfo=None).isoformat(), "timeZone": zone}


def graph_event(raw):
    if raw.get("recurrence") or raw.get("type", "singleInstance") != "singleInstance" or raw.get("isAllDay"):
        raise Blocked("unsupported_graph_event_type")
    def time_part(value, original_zone):
        zone = iana_zone(original_zone or value["timeZone"])
        dt = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(iana_zone(value["timeZone"])))
        return {"dateTime": dt.astimezone(timezone.utc).isoformat(), "timeZone": zone}
    attendees = []
    for a in raw.get("attendees", []):
        response = a.get("status", {}).get("response", "none")
        if response not in GRAPH_RSVP:
            raise Blocked("unknown_graph_rsvp")
        attendees.append({"email": a["emailAddress"]["address"], "responseStatus": GRAPH_RSVP[response]})
    return {"id": raw["id"], "etag": raw.get("@odata.etag"), "iCalUID": raw.get("iCalUId"),
            "organizer": {"email": raw["organizer"]["emailAddress"]["address"]},
            "summary": raw.get("subject", ""), "description": raw.get("body", {}).get("content", ""),
            "location": raw.get("location", {}).get("displayName", ""),
            "start": time_part(raw["start"], raw.get("originalStartTimeZone")),
            "end": time_part(raw["end"], raw.get("originalEndTimeZone")), "attendees": attendees,
            "status": "cancelled" if raw.get("isCancelled") else "confirmed"}


class Graph:
    provider = "microsoft"
    prefer = {"Prefer": 'IdType="ImmutableId", outlook.timezone="UTC"'}
    def __init__(self, account, transport):
        self.account, self.http = account, transport
        self.user = "/users/" + quote(account["subject"], safe="")
        self.base = self.user + "/calendars/" + quote(account["calendar_id"], safe="") + "/events"

    def auth_health(self):
        result = self.http.call("GET", self.user + "/calendars/" + quote(self.account["calendar_id"], safe=""), headers=self.prefer)
        return result.get("canEdit") is True

    def get(self, event_id):
        return graph_event(self.http.call("GET", self.base + "/" + quote(event_id, safe=""), headers=self.prefer))

    def create(self, stable_id, body):
        transaction = str(uuid.UUID(stable_id[:32]))
        # transactionId filtering is NOT assumed. Extended-property Any filtering is
        # the supported durable recovery path; transactionId still deduplicates POST.
        expand = "singleValueExtendedProperties($filter=id eq '" + GRAPH_OPERATION_PROPERTY + "')"
        path, params = self.base, {"$filter": "singleValueExtendedProperties/Any(ep: ep/id eq '" + GRAPH_OPERATION_PROPERTY + "' and ep/value eq '" + stable_id + "')", "$expand": expand, "$top": 100}
        seen, found = set(), []
        while path:
            page = self.http.call("GET", path, params=params, headers=self.prefer)
            found.extend(page.get("value", []))
            link = page.get("@odata.nextLink")
            if link:
                prefix = "https://graph.microsoft.com/v1.0"
                if not link.startswith(prefix + "/") or link in seen:
                    raise Blocked("unsafe_graph_pagination")
                seen.add(link)
                path, params = link[len(prefix):], None
            else:
                path = None
        if len(found) > 1:
            raise Blocked("multiple_graph_transaction_events")
        if found:
            raw = found[0]
            if (not any(p.get("id") == GRAPH_OPERATION_PROPERTY and p.get("value") == stable_id
                        for p in raw.get("singleValueExtendedProperties", []))
                or raw.get("organizer", {}).get("emailAddress", {}).get("address", "").lower() != self.account["email"].lower()):
                raise Blocked("graph_recovery_identity_mismatch")
            return graph_event(raw)
        payload = {"transactionId": transaction,
                   "singleValueExtendedProperties": [{"id": GRAPH_OPERATION_PROPERTY, "value": stable_id}],
                   "subject": body["summary"],
                   "body": {"contentType": "text", "content": body.get("description", "")},
                   "location": {"displayName": body.get("location", "")},
                   "start": graph_time(body["start"]), "end": graph_time(body["end"]),
                   "attendees": [{"emailAddress": {"address": a["email"]}, "type": "required"} for a in body["attendees"]]}
        return graph_event(self.http.call("POST", self.base, body=payload, headers=self.prefer))

    def patch_time(self, event, source):
        result = self.http.call("PATCH", self.base + "/" + quote(event["id"], safe=""),
            body={"start": graph_time(source["start"]), "end": graph_time(source["end"])}, headers=dict(self.prefer, **revision(event)))
        return graph_event(result)

    def cancel(self, event):
        # DELETE organizer event sends cancellation and supports an event precondition.
        self.http.call("DELETE", self.base + "/" + quote(event["id"], safe=""), headers=dict(self.prefer, **revision(event)))
        return dict(event, status="cancelled")


class Providers:
    def __init__(self, settings):
        self.settings, self.cache = settings, {}

    def for_account(self, account):
        key = (account["provider"], account["tenant"], account["subject"], account["calendar_id"])
        if key not in self.cache:
            if account["provider"] == "google":
                self.cache[key] = Google(account, Transport(google_token(account), "https://www.googleapis.com/calendar/v3", not self.settings.dry_run),
                                         self.settings.import_cas_verified)
            elif account["provider"] == "microsoft":
                self.cache[key] = Graph(account, Transport(graph_token(account), "https://graph.microsoft.com/v1.0", not self.settings.dry_run))
            else:
                raise Blocked("unknown_provider")
        return self.cache[key]
