from copy import deepcopy
import os
import time
import uuid

import psycopg
from psycopg.conninfo import make_conninfo
import pytest
import requests

from bridge.config import Settings
from bridge.domain import private_body
from bridge.providers import Google, ProviderError
from bridge.store import Store


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Live HTTP forbidden in tests")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)


@pytest.fixture
def registry():
    accounts = []
    for group, ids in (("main", ["main"]), ("google", ["g1", "g2"]), ("microsoft", ["m1", "m2"])):
        for id in ids:
            provider = "microsoft" if group == "microsoft" else "google"
            accounts.append({"id": id, "email": id + "@example.test", "group": group, "provider": provider,
                "owner": "barbara_pigg", "reviewed": True, "ready": True, "calendar_write_reviewed": True,
                "tenant": "test", "subject": id + "@example.test", "calendar_id": id,
                "approved_campaigns": ["campaign-reviewed"], "daily_cap": 100,
                "credential_secret": "TEST_UNUSED", "health": healthy(provider)})
    return {"consultant": {"id": "barbara_pigg", "main_sender": "main", "location": "Meeting room",
                          "placeholder_title": "Blind Invite", "max_leads_per_block": 100},
            "senders": accounts,
            "crm": {"activity_type": "test-type", "meeting_date_field": "meeting", "sent_date_field": "sent"}}


def healthy(provider="google"):
    return {"checked_at": time.time(), "calendar_auth": True, "connected": True, "provider": provider,
            "active_campaigns": ["campaign-reviewed"], "setup_pending": False, "usage": 0}


@pytest.fixture
def settings(registry):
    return Settings("postgresql://unused/test", "a" * 40, registry, new_sends=True, dry_run=False, import_cas_verified=True)


@pytest.fixture
def store(registry):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to disposable Postgres; SQLite cannot test row locks")
    schema = "bridge_test_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as c:
        c.execute('CREATE SCHEMA "' + schema + '"')
    store = Store(make_conninfo(url, options="-csearch_path=" + schema))
    store.migrate()
    store.register(registry)
    try:
        yield store
    finally:
        with psycopg.connect(url, autocommit=True) as c:
            c.execute('DROP SCHEMA "' + schema + '" CASCADE')


@pytest.fixture
def command():
    return {"task_id": "task_test", "lead_id": "lead_test", "email": "lead@example.test",
            "groups": ["google"], "start": "2035-09-09T14:00:00+00:00", "end": "2035-09-09T14:30:00+00:00",
            "timezone": "UTC", "title": "Introduction", "description": "Description", "leads_per_block": 8,
            "allow_existing": False}


class FakeProvider:
    def __init__(self, account):
        self.account, self.provider = account, account["provider"]
        self.events, self.writes = {}, []
        self.create_timeout = self.copy_failure = False
        self.auth_error = None
        self.cas = True

    def auth_health(self):
        return True

    def get(self, event_id):
        if self.auth_error:
            raise ProviderError(self.auth_error)
        if event_id not in self.events:
            raise ProviderError(404)
        return deepcopy(self.events[event_id])

    def list(self, **params):
        return []

    def create(self, stable_id, body):
        if stable_id not in self.events:
            self.writes.append("create")
            self.events[stable_id] = dict(deepcopy(body), id=stable_id, iCalUID=stable_id + "@test",
                etag='"1"', organizer={"email": self.account["email"]}, status="confirmed")
            if self.create_timeout:
                self.create_timeout = False
                from bridge.domain import Blocked
                raise Blocked("provider_transport_uncertain")
        return self.get(stable_id)

    def ensure_copy(self, original, local_email):
        if self.copy_failure:
            self.copy_failure = False
            raise ProviderError(503)
        id = "copy-" + original["id"]
        if id not in self.events:
            self.writes.append("import")
            self.events[id] = dict(private_body(original, local_email), id=id, etag='"1"', privateCopy=True)
        return self.get(id)

    assert_copy = staticmethod(Google.assert_copy)

    def update(self, id, **fields):
        event = self.events[id]
        event.update(deepcopy(fields))
        event["etag"] = '"' + str(int(event["etag"].strip('"')) + 1) + '"'
        return deepcopy(event)

    def patch_time(self, event, source):
        if self.events[event["id"]]["etag"] != event["etag"]:
            raise ProviderError(412)
        self.writes.append("time")
        return self.update(event["id"], start=source["start"], end=source["end"])

    def cancel(self, event):
        self.writes.append("cancel")
        return self.update(event["id"], status="cancelled")

    def project_rsvp(self, original, live, email):
        from bridge.domain import Blocked
        if not self.cas:
            raise Blocked("rsvp_degraded_import_cas_unproven")
        self.writes.append("rsvp")
        return self.update(live["id"], attendees=private_body(original, email, live)["attendees"])


class FakeProviders:
    def __init__(self, registry):
        self.providers = {a["id"]: FakeProvider(a) for a in registry["senders"]}

    def for_account(self, account):
        return self.providers[account["id"]]


class FakeInventory:
    def observe(self, account):
        return healthy(account["provider"])


class FakeCRM:
    def __init__(self):
        self.calls = 0
        self.recent_from = []

    def recent_from_addresses(self, lead_id, days=30):
        return list(self.recent_from)

    def advance(self, meeting, store):
        assert meeting["data"].get("linked")
        assert meeting["data"].get("organizer")
        if meeting["group_name"] != "main":
            assert meeting["data"].get("barbara")
        self.calls += 1
        meeting["data"]["crm_phase"] = "complete"
        store.save(meeting["operation"], "complete", meeting["data"], "test_crm_complete")


@pytest.fixture
def worker(settings, store, registry):
    from bridge.worker import Worker
    return Worker(settings, store, FakeProviders(registry), FakeInventory(), FakeCRM())
