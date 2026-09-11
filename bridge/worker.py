"""Durable saga and bounded, managed-link reconciliation. No historical auto-adoption."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import logging
import time

from .config import Settings
from .crm import Close
from .domain import Blocked, exclusion_reasons, rsvp_key, sync_action, time_key
from .inventory import Inventory
from .providers import Providers, ProviderError
from .store import Store

log = logging.getLogger("calendar_bridge")

# Cancelled/conflict rows only change through operator routes (which enqueue), and a
# meeting past its end plus grace has nothing left to reconcile at the live cadence.
SETTLED_POLL_SECONDS = 86400
POST_MEETING_GRACE_SECONDS = 86400


class Worker:
    def __init__(self, settings, store, providers, inventory, crm):
        self.settings, self.store, self.providers = settings, store, providers
        self.inventory, self.crm = inventory, crm

    def provider_pair(self, meeting):
        # Persisted compound identity remains authoritative after new-send retirement.
        sender = meeting["data"]["sender_identity"]
        main = meeting["data"].get("main_identity") or self.settings.sender(self.settings.consultant["main_sender"])
        return self.providers.for_account(sender), self.providers.for_account(main), main

    def create(self, meeting):
        operation, data = meeting["operation"], meeting["data"]
        original_api, copy_api, main = self.provider_pair(meeting)
        self.settings.allow_write()
        if "organizer" not in data:
            if not data.get("organizer_attempted"):
                if not self.settings.new_sends:
                    raise Blocked("new_sends_disabled")
                # Do not reassign an exhausted/unhealthy reservation. First-send auth is fresh.
                account = deepcopy(data["sender_identity"])
                current = next((a for a in self.store.inventory() if a["id"] == account["id"]), None)
                if current is None or current.get("disabled") or current.get("reviewed") is not True:
                    raise Blocked("reserved_sender_retired")
                # Eligibility uses the CURRENT registry (owner, approvals, caps); the persisted
                # compound identity (provider/subject/calendar/tenant/credential) stays immutable.
                for key in ("owner", "reviewed", "ready", "calendar_write_reviewed", "approved_campaigns", "daily_cap", "disabled", "group"):
                    if key in current:
                        account[key] = deepcopy(current[key])
                account["health"] = self.inventory.observe(account)
                account["used"] = 0  # already charged at reservation, including across midnight
                if exclusion_reasons(account, time.time()):
                    raise Blocked("reserved_sender_unhealthy")
                data["organizer_attempted"] = True
                data["main_identity"] = main
                self.store.save(operation, "organizer_pending", data, "organizer_create_intent")
            body = {"summary": data["title"], "description": data["description"],
                    "location": self.settings.consultant["location"],
                    "start": {"dateTime": data["start"], "timeZone": data["timezone"]},
                    "end": {"dateTime": data["end"], "timeZone": data["timezone"]},
                    "attendees": [{"email": data["email"]}]}
            if original_api.provider == "google":
                body["extendedProperties"] = {"private": {"bridgeOperation": data["stable_id"]}}
            original = original_api.create(data["stable_id"], body)
            if original_api.provider == "google" and original.get("extendedProperties", {}).get("private", {}).get("bridgeOperation") != data["stable_id"]:
                raise Blocked("google_recovery_marker_mismatch")
            if (not original.get("id") or not original.get("iCalUID") or original.get("status") == "cancelled"
                or original.get("organizer", {}).get("email", "").lower() != data["sender_identity"]["email"].lower()
                or not any(a["email"].lower() == data["email"].lower() for a in original.get("attendees", []))):
                raise Blocked("organizer_identity_not_confirmed")
            if meeting["group_name"] != "main" and any(a["email"].lower() == main["email"].lower() for a in original.get("attendees", [])):
                raise Blocked("barbara_present_on_external_original")
            data["organizer"] = original
            data["uid"] = original["iCalUID"]
            data.setdefault("links", {})["organizer"] = self.compound_link(data["sender_identity"], original)
            self.store.save(operation, "organizer_created", data, "organizer_confirmed")
        if meeting["group_name"] != "main" and "barbara" not in data:
            self.store.save(operation, "mirror_pending", data, "private_copy_intent")
            # Always refresh the original, including on copy-only repair; no re-send.
            original = original_api.get(data["organizer"]["id"])
            if original.get("status") == "cancelled":
                raise Blocked("organizer_cancelled_during_creation")
            data["barbara"] = copy_api.ensure_copy(original, main["email"])
            data.setdefault("links", {})["barbara"] = self.compound_link(main, data["barbara"])
            data["organizer"] = original
        data.setdefault("ack_organizer", deepcopy(data["organizer"]))
        if "barbara" in data:
            data.setdefault("ack_barbara", deepcopy(data["barbara"]))
        data["linked"] = True
        self.store.save(operation, "linked", data, "events_linked")

    @staticmethod
    def compound_link(account, event):
        return {k: account[k] for k in ("provider", "tenant", "subject", "calendar_id")} | {
            "event_id": event["id"], "iCalUID": event["iCalUID"]}

    @staticmethod
    def resting_state(meeting):
        # Keep CRM-derived states; a calendar observation must not bounce them through linked.
        if meeting["data"].get("crm_phase") == "complete":
            return "complete"
        return meeting["state"] if meeting["state"] in ("crm_pending", "crm_uncertain") else "linked"

    @staticmethod
    def observed_side(api, data, side):
        if side in data.get("confirmed_deletions", {}):
            return dict(data[side], status="cancelled")
        return api.get(data[side]["id"])

    def sync(self, meeting):
        data, operation = meeting["data"], meeting["operation"]
        original_api, copy_api, main = self.provider_pair(meeting)
        original = self.observed_side(original_api, data, "organizer")
        if meeting["group_name"] == "main":
            data["organizer"] = original
            if original.get("status") == "cancelled":
                self.store.save(operation, "cancelled", data, "main_cancellation_confirmed")
            elif original != data.get("ack_organizer"):
                data["ack_organizer"] = deepcopy(original)
                self.store.save(operation, meeting["state"], data, "main_state_observed")
            return
        local = self.observed_side(copy_api, data, "barbara")
        copy_api.assert_copy(local, original, main["email"]) if local.get("status") != "cancelled" and original.get("status") != "cancelled" else None
        if original.get("iCalUID", data["organizer"]["iCalUID"]) != data["organizer"]["iCalUID"]:
            raise Blocked("organizer_uid_changed")
        if any(e.get("recurrence") or e.get("recurringEventId") or e.get("eventType", "default") != "default"
               for e in (original, local)):
            raise Blocked("unsupported_managed_event_representation")
        guest_emails = lambda e: sorted(a["email"].lower() for a in e.get("attendees", []))
        local_guest_edit = guest_emails(local) != guest_emails(data["ack_barbara"])
        action = sync_action(data["ack_organizer"], data["ack_barbara"], original, local)
        if action == "conflict":
            data["conflict"] = {"organizer": original, "barbara": local, "kind": "time_or_cancellation"}
            self.store.save(operation, "sync_conflict", data, "concurrent_edit_conflict")
            return
        changed = action != "noop" or original != data["ack_organizer"] or local != data["ack_barbara"]
        if action != "noop":
            self.settings.allow_write()
            data["write_intent"] = {"action": action, "organizer_revision": original.get("etag"), "barbara_revision": local.get("etag")}
            self.store.save(operation, "sync_pending", data, "sync_write_intent")
        if action == "time_barbara":
            local = copy_api.patch_time(local, original)
        elif action == "time_organizer":
            original = original_api.patch_time(original, local)
        elif action == "cancel_barbara":
            local = copy_api.cancel(local)
        elif action == "cancel_organizer":
            original = original_api.cancel(original)
        data.update(organizer=original, barbara=local, ack_organizer=deepcopy(original), ack_barbara=deepcopy(local))
        data.pop("write_intent", None)
        if action.startswith("cancel"):
            self.store.save(operation, "cancelled", data, "partner_cancellation_confirmed")
            return
        # Snapshot time independently before RSVP. Unsafe import must not erase time work.
        # An unchanged poll writes nothing: no audit row, no updated_at bump.
        if changed:
            self.store.save(operation, self.resting_state(meeting), data, "time_reconciled")
        if rsvp_key(original, main["email"]) != rsvp_key(local, main["email"]):
            if local_guest_edit:
                data["conflict"] = {"kind": "unsupported_local_guest_edit", "organizer": original, "barbara": local}
                self.store.save(operation, "sync_conflict", data, "local_guest_edit_requires_review")
                return
            self.settings.allow_write()
            try:
                projected = copy_api.project_rsvp(original, local, main["email"])
            except Blocked as error:
                if str(error).startswith("rsvp_degraded"):
                    if changed or meeting["state"] != "rsvp_degraded" or data.get("sync_error") != str(error):
                        data["sync_error"] = str(error)
                        self.store.save(operation, "rsvp_degraded", data, "rsvp_projection_blocked")
                    return
                raise
            if rsvp_key(original, main["email"]) != rsvp_key(projected, main["email"]):
                raise Blocked("rsvp_projection_not_confirmed")
            # Import 412 rebase may have preserved a NEW local time. Do not acknowledge
            # that time until it has been propagated on the next independent comparison.
            ack = deepcopy(local)
            ack["attendees"] = deepcopy(projected["attendees"])
            data.update(barbara=projected, ack_barbara=ack)
            data.pop("sync_error", None)
            self.store.save(operation, self.resting_state(meeting), data, "rsvp_projected")

    def process(self, operation):
        with self.store.meeting_lock(operation) as locked:
            if not locked:
                raise Blocked("meeting_busy")
            meeting = self.store.get(operation)
            if meeting["state"] in ("cancelled", "sync_conflict"):
                return meeting
            if not meeting["data"].get("linked"):
                self.create(meeting)
                meeting = self.store.get(operation)
            # Calendar repair/sync remains active during CRM outages/uncertainty.
            self.sync(meeting)
            meeting = self.store.get(operation)
            if meeting["state"] not in ("cancelled", "sync_conflict", "rsvp_degraded") and meeting["data"].get("crm_phase") != "complete":
                self.crm.advance(meeting, self.store)
                meeting = self.store.get(operation)
            return meeting

    def poll_delay(self, meeting):
        settled = (meeting["state"] in ("cancelled", "sync_conflict")
                   or meeting["end_at"] + timedelta(seconds=POST_MEETING_GRACE_SECONDS) < datetime.now(timezone.utc))
        return SETTLED_POLL_SECONDS if settled else self.settings.poll_seconds

    def tick(self):
        self.store.heartbeat()
        job = self.store.claim()
        if not job:
            return False
        try:
            meeting = self.process(job["operation"])
            self.store.finish_job(job, self.poll_delay(meeting))
        except Exception as error:
            # Do not log payloads, tokens, mailbox contents or exception strings from SDKs.
            code = str(error) if isinstance(error, Blocked) else "internal_error"
            if isinstance(error, ProviderError) and error.status == 412:
                with self.store.meeting_lock(job["operation"]) as locked:
                    if locked:
                        meeting = self.store.get(job["operation"])
                        meeting["data"]["conflict"] = {"kind": "provider_precondition_failed"}
                        self.store.save(job["operation"], "sync_conflict", meeting["data"], "provider_revision_conflict")
            self.store.finish_job(job, min(3600, 15 * 2 ** min(job["attempts"], 8)), code)
            with self.store.connect() as c:
                self.store.audit(c, job["operation"], "job_degraded", {"reason": code})
            log.warning("job_degraded reason=%s", code)
        return True


def main():
    logging.basicConfig(level=logging.INFO)
    settings = Settings.load()
    store, providers = Store(settings.database_url), Providers(settings)
    store.register(settings.registry)
    inventory = Inventory(settings, providers, store)
    worker = Worker(settings, store, providers, inventory, Close(settings))
    next_inventory, next_discovery = 0, 0
    while True:
        try:
            worked = worker.tick()
            if time.monotonic() >= next_inventory:
                inventory.refresh()
                next_inventory = time.monotonic() + 5
            if time.monotonic() >= next_discovery:
                next_discovery = time.monotonic() + 600
                try:
                    inventory.discover()
                except Exception as error:
                    # Discovery is visibility only; a failure must not stall durable jobs.
                    reason = str(error) if isinstance(error, Blocked) else type(error).__name__
                    log.warning("inventory_discovery_failed reason=%s", reason)
            if not worked:
                time.sleep(1)
        except Exception as error:
            # Safe reason only: Blocked codes are non-sensitive; anything else is typed, not stringified.
            reason = str(error) if isinstance(error, Blocked) else type(error).__name__
            log.error("worker_cycle_failed reason=%s", reason)
            next_inventory = time.monotonic() + 60
            time.sleep(5)


if __name__ == "__main__":
    main()
