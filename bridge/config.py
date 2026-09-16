"""Server-only registry and mounted secret files; no browser-supplied identities."""
from dataclasses import dataclass
import os
from pathlib import Path
import tomllib

from .domain import BARBARA, Blocked


def secret(name):
    path = os.environ.get(name + "_FILE")
    if not path:
        raise Blocked("missing_secret:" + name)
    return Path(path).read_text().strip()


@dataclass(frozen=True)
class Settings:
    database_url: str
    operator_token: str
    registry: dict
    new_sends: bool = False
    dry_run: bool = True
    poll_seconds: int = 60
    # Proven by controlled stale/current real-ETag tests on 2026-09-09.
    import_cas_verified: bool = True

    @classmethod
    def load(cls):
        registry = tomllib.loads(Path(os.environ["BRIDGE_REGISTRY_FILE"]).read_text())
        settings = cls(secret("DATABASE_URL"), secret("BRIDGE_OPERATOR_TOKEN"), registry,
                       os.getenv("BRIDGE_NEW_SENDS", "false") == "true",
                       os.getenv("BRIDGE_DRY_RUN", "true") != "false",
                       int(os.getenv("BRIDGE_POLL_SECONDS", "60")),
                       os.getenv("BRIDGE_IMPORT_CAS_VERIFIED", "true") == "true")
        settings.validate()
        return settings

    def validate(self):
        if self.registry.get("inventory", {}).get("fixture_file") and not self.dry_run:
            raise Blocked("fixture_inventory_requires_dry_run")
        if len(self.operator_token) < 32:
            raise Blocked("operator_token_too_short")
        if not self.database_url.startswith(("postgresql://", "postgres://")):
            raise Blocked("postgres_required")
        ids = set()
        for sender in self.registry.get("senders", []):
            if sender["id"] in ids:
                raise Blocked("duplicate_sender_id")
            ids.add(sender["id"])
            group, provider = sender.get("group"), sender.get("provider")
            if group not in ("main", "google", "microsoft") or provider != ("google" if group == "main" else group):
                raise Blocked("sender_group_provider_mismatch")
        consultant = self.registry.get("consultant", {})
        if consultant.get("id") != BARBARA or not consultant.get("main_sender"):
            raise Blocked("barbara_registry_required")
        mains = [a["id"] for a in self.registry.get("senders", []) if a["group"] == "main"]
        if mains != [consultant["main_sender"]]:
            raise Blocked("one_google_main_sender_required")
        if not 10 <= self.poll_seconds <= 3600:
            raise Blocked("invalid_poll_interval")

    @property
    def consultant(self):
        return self.registry["consultant"]

    def sender(self, sender_id):
        for sender in self.registry.get("senders", []):
            if sender["id"] == sender_id:
                return sender
        raise Blocked("sender_missing_from_registry")

    def allow_write(self):
        if self.dry_run:
            raise Blocked("dry_run")
