"""Instantly discovery is GET-only. Ownership and calendar grants are separate reviews."""
import json
import time
from pathlib import Path
from urllib.parse import quote

from .config import secret
from .domain import Blocked
from .providers import Transport


class Instantly:
    def __init__(self, transport, schema):
        self.http, self.schema = transport, schema
        self.last_request = 0

    def get(self, path, **kwargs):
        # Deliberately below the official 100/s workspace limit; inventory is not urgent.
        time.sleep(max(0, 0.1 - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        return self.http.call("GET", path, **kwargs)

    def pages(self, path, **params):
        cursor, seen = None, set()
        while True:
            page = self.get(path, params=dict(params, limit=100, **({"starting_after": cursor} if cursor else {})))
            if not isinstance(page.get("items"), list):
                raise Blocked("instantly_unknown_list_schema")
            yield from page["items"]
            cursor = page.get("next_starting_after")
            if not cursor:
                return
            if cursor in seen:
                raise Blocked("instantly_pagination_loop")
            seen.add(cursor)

    def accounts(self):
        return list(self.pages("/accounts"))

    def observe(self, account):
        email = quote(account["email"], safe="")
        raw = self.get("/accounts/" + email)
        mappings = list(self.pages("/account-campaign-mappings/" + email))
        active, assigned = [], []
        for mapping in mappings:
            campaign_id = mapping.get("campaign_id")
            if campaign_id not in account.get("approved_campaigns", []):
                continue
            campaign = self.get("/campaigns/" + quote(campaign_id, safe=""))
            allowed = (1, 4)
            if account["email"].lower() in [e.lower() for e in campaign.get("email_list", [])]:
                assigned.append(campaign_id)
                if campaign.get("status") in allowed and mapping.get("status") in allowed:
                    active.append(campaign_id)
        from datetime import datetime, timezone, timedelta
        date_today = datetime.now(timezone.utc).date()
        today, since = date_today.isoformat(), (date_today - timedelta(days=6)).isoformat()
        usage, usage_health = None, "unavailable"
        try:
            rows = self.get("/accounts/analytics/daily", params={"start_date": since, "end_date": today, "emails": [account["email"]]})
            if isinstance(rows, list):
                matching = [r for r in rows if r.get("email_account", "").lower() == account["email"].lower() and since <= r.get("date", "") <= today]
                if matching and all(isinstance(r.get("sent"), (int, float)) for r in matching):
                    usage, usage_health = sum(r["sent"] for r in matching), "observed"
        except Exception:
            pass  # optional visibility, never mistaken for zero sends
        # Official schema, independently checked 2026-09-09. No domain inference.
        provider = {2: "google", 3: "microsoft"}.get(raw.get("provider_code"))
        # Only retain reviewed, non-secret fields. Instantly responses can contain tokens.
        return {"connected": raw.get("status") == 1, "account_status": raw.get("status"),
                "setup_pending": raw.get("setup_pending"),
                "provider": provider, "active_campaigns": active, "approved_assigned_campaigns": assigned,
                "require_running_campaign": self.schema.get("require_running_campaign", True),
                "campaign_assignments": [{"id": m.get("campaign_id"), "status": m.get("status")} for m in mappings],
                "usage": usage, "usage_health": usage_health, "usage_start": since, "usage_end": today,
                "warmup_status": raw.get("warmup_status"), "warmup_score": raw.get("stat_warmup_score")}


class Inventory:
    def __init__(self, settings, providers, store, instantly=None):
        self.settings, self.providers, self.store = settings, providers, store
        self.instantly = instantly
        self.fixture = None
        fixture = settings.registry.get("inventory", {}).get("fixture_file")
        if fixture:
            if not settings.dry_run:
                raise Blocked("fixture_inventory_requires_dry_run")
            self.fixture = json.loads(Path(fixture).read_text())

    def observe(self, account):
        health = {"checked_at": time.time(), "calendar_auth": False}
        try:
            if self.fixture is not None:
                return dict(self.fixture.get(account["id"], {}), checked_at=time.time())
            if account["group"] != "main":
                if self.instantly is None:
                    self.instantly = Instantly(Transport(lambda: secret("INSTANTLY_API_KEY"), "https://api.instantly.ai/api/v2", False),
                                                self.settings.registry.get("inventory", {}))
                health.update(self.instantly.observe(account))
            health["calendar_auth"] = self.providers.for_account(account).auth_health()
        except Exception:
            health["error"] = "inventory_or_calendar_health_unavailable"
        return health

    def refresh(self):
        configured = {s["id"] for s in self.settings.registry.get("senders", [])}
        accounts = [a for a in self.store.inventory() if a["id"] in configured]
        accounts.sort(key=lambda a: a.get("health", {}).get("checked_at", 0))
        if accounts and time.time() - accounts[0].get("health", {}).get("checked_at", 0) >= 300:
            account = accounts[0]
            self.store.health(account["id"], self.observe(account))
        # One health probe per cycle: large inventories must not starve durable jobs.

    def discover(self):
        if self.fixture is None and self.instantly is None:
            self.instantly = Instantly(Transport(lambda: secret("INSTANTLY_API_KEY"), "https://api.instantly.ai/api/v2", False),
                                        self.settings.registry.get("inventory", {}))
        # Discover unregistered accounts for eligible/total visibility. Never copy raw
        # provider auth material or infer Barbara ownership from mailbox names.
        if self.instantly is not None:
            for raw in self.instantly.accounts():
                email = raw.get("email")
                if not email or any(s.get("email", "").lower() == email.lower() for s in self.settings.registry.get("senders", [])):
                    continue
                provider = {2: "google", 3: "microsoft"}.get(raw.get("provider_code"))
                account = {"id": "unreviewed:" + email.lower(), "email": email, "group": provider or "unknown", "provider": provider,
                           "reviewed": False, "health": {"checked_at": time.time(), "connected": raw.get("status") == 1}}
                from psycopg.types.json import Jsonb
                with self.store.connect() as c:
                    c.execute("INSERT INTO bridge_senders(id,account) VALUES (%s,%s) ON CONFLICT(id) DO UPDATE SET account=EXCLUDED.account",
                              (account["id"], Jsonb(account)))
