"""Private operator API. Only health probes are unauthenticated; no public action hooks."""
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hmac
from hashlib import sha256
import json
import time
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import Settings
from .crm import Close
from .domain import BARBARA, Blocked, exclusion_reasons, instant, time_key
from .inventory import Inventory
from .providers import Providers
from .store import Store


class Invite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(pattern=r"^task_[A-Za-z0-9]+$", max_length=150)
    lead_id: str = Field(pattern=r"^lead_[A-Za-z0-9]+$", max_length=150)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    groups: list[Literal["main", "google", "microsoft"]] = Field(min_length=1, max_length=3)
    start: str
    end: str
    timezone: str = "UTC"
    title: str = Field(min_length=1, max_length=1000)
    description: str = Field(max_length=20000)
    leads_per_block: int = Field(ge=1)
    allow_existing: bool = False

    @model_validator(mode="after")
    def valid(self):
        if len(set(self.groups)) != len(self.groups):
            raise ValueError("duplicate groups")
        if instant(self.end) <= instant(self.start):
            raise ValueError("end must follow start")
        try:
            ZoneInfo(self.timezone)
        except Exception:
            raise ValueError("unknown timezone") from None
        return self


class Disable(BaseModel):
    disabled: bool
    reason: str = Field(min_length=3, max_length=300)


class Resolve(BaseModel):
    source: Literal["organizer", "barbara"]
    organizer_revision: str
    barbara_revision: str


class DeletionReview(BaseModel):
    side: Literal["organizer", "barbara"]


class ConfirmDeletion(DeletionReview):
    expected_version: str
    confirmation_token: str
    actor: str = Field(min_length=3, max_length=150)
    reason: str = Field(min_length=10, max_length=500)


class ConfirmActivity(BaseModel):
    activity_id: str = Field(pattern=r"^acti_[A-Za-z0-9]+$", max_length=150)


class OperatorEvidence(BaseModel):
    actor: str = Field(min_length=3, max_length=150)
    reason: str = Field(min_length=10, max_length=500)


def create_app(settings=None, store=None, providers=None, crm=None):
    @asynccontextmanager
    async def lifespan(app):
        if app.state.settings is None:
            app.state.settings = Settings.load()
        app.state.settings.validate()
        app.state.store = app.state.store or Store(app.state.settings.database_url)
        app.state.providers = app.state.providers or Providers(app.state.settings)
        app.state.crm = app.state.crm or Close(app.state.settings)
        # Migrations are an explicit deployment step, never destructive startup magic.
        app.state.store.register(app.state.settings.registry)
        yield

    app = FastAPI(title="CalendarInvites bridge", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings, app.state.store, app.state.providers, app.state.crm = settings, store, providers, crm

    def auth(authorization: str = Header(default="")):
        expected = "Bearer " + app.state.settings.operator_token
        if not hmac.compare_digest(authorization.encode(), expected.encode()):
            raise HTTPException(401, "Unauthorized")

    @app.exception_handler(Blocked)
    async def blocked(_, error):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(RequestValidationError)
    async def invalid(_, error):
        # Pydantic's default error details echo user input; no payloads in errors/logs.
        return JSONResponse(status_code=422, content={"detail": "Invalid invite/operator command"})

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def ready():
        try:
            if app.state.store.ready():
                return {"status": "ready"}
        except Exception:
            pass
        raise HTTPException(503, "Database/schema/worker not ready")

    @app.get("/inventory", dependencies=[Depends(auth)])
    def inventory():
        rows = []
        for account in app.state.store.inventory():
            reasons = exclusion_reasons(account, time.time())
            rows.append({k: account.get(k) for k in ("id", "email", "provider", "group", "owner", "reviewed", "daily_cap", "used", "health", "disabled")} | {"exclusions": reasons, "eligible": not reasons})
        counts = {g: {"eligible": sum(a["eligible"] and a["group"] == g for a in rows),
                      "total": sum(a["group"] == g for a in rows)} for g in ("main", "google", "microsoft")}
        with app.state.store.connect() as c:
            rotation = c.execute("SELECT cursor FROM bridge_rotation WHERE consultant=%s", (BARBARA,)).fetchone()
        return {"accounts": rows, "groups": counts, "cursor": rotation["cursor"],
                "new_sends": app.state.settings.new_sends, "dry_run": app.state.settings.dry_run,
                "outreach_release_ready": app.state.settings.import_cas_verified}

    @app.post("/senders/{sender}/disable", dependencies=[Depends(auth)])
    def disable(sender: str, body: Disable):
        app.state.store.disable(sender, body.disabled, body.reason)
        return {"status": "updated"}

    @app.post("/invites", dependencies=[Depends(auth)])
    def invite(body: Invite):
        s, db = app.state.settings, app.state.store
        operation = BARBARA + ":" + body.task_id
        # Read-back of an already reserved task still works with new sends frozen.
        existing = db.get(operation)
        if existing:
            return {"operation": operation, "state": existing["state"]}
        if not s.new_sends:
            raise Blocked("new_sends_disabled")
        s.allow_write()
        if set(body.groups) - {"main"} and not s.import_cas_verified:
            raise Blocked("outreach_release_blocked_rsvp_concurrency")
        if instant(body.start) <= datetime.now(timezone.utc):
            raise Blocked("new_meeting_must_be_future")
        # Slot capacity is the caller's choice, with no server-side ceiling. Overbooking is
        # still prevented by slot_at_capacity, which counts live calendar events plus durable
        # reservations under the consultant lock and refuses the reservation at the limit.
        main = s.sender(s.consultant["main_sender"])
        if body.email.lower() == main["email"].lower():
            raise Blocked("lead_cannot_be_barbara")
        api = app.state.providers.for_account(main)
        def occupancy(start, end):
            if not body.allow_existing:
                existing_leads = [e for e in api.list(q=body.email, singleEvents="true")
                    if e.get("status") != "cancelled" and any(a.get("email", "").lower() == body.email.lower() for a in e.get("attendees", []))]
                if existing_leads:
                    raise Blocked("existing_lead_invite_requires_review")
            events = [e for e in api.list(timeMin=start, timeMax=end, singleEvents="true")
                      if e.get("status") != "cancelled" and e.get("summary") != s.consultant["placeholder_title"]]
            return events, body.leads_per_block
        preferred = []
        try:
            preferred = app.state.crm.recent_from_addresses(body.lead_id)
        except Blocked:
            preferred = []
        meeting = db.reserve(dict(body.model_dump(), main_identity=main, preferred_from=preferred), occupancy)
        return {"operation": operation, "state": meeting["state"]}

    @app.get("/meetings", dependencies=[Depends(auth)])
    def meetings():
        with app.state.store.connect() as c:
            return c.execute("""SELECT m.operation,m.state,m.sender,m.group_name,m.start_at,m.end_at,
                m.updated_at,j.last_error,j.due_at,j.attempts FROM bridge_meetings m JOIN bridge_jobs j USING(operation)
                ORDER BY m.created_at DESC LIMIT 100""").fetchall()

    @app.get("/meetings/{operation}", dependencies=[Depends(auth)])
    def meeting(operation: str):
        row = app.state.store.get(operation)
        if not row:
            raise HTTPException(404, "Unknown managed operation")
        data = row["data"]
        conflict = data.get("conflict")
        if row["state"] == "sync_conflict" and data.get("linked") and "barbara" in data:
            from .worker import Worker
            worker = Worker(app.state.settings, app.state.store, app.state.providers, None, None)
            original_api, copy_api, _ = worker.provider_pair(row)
            conflict = dict(conflict or {}, organizer=worker.observed_side(original_api, data, "organizer"),
                            barbara=worker.observed_side(copy_api, data, "barbara"))
        # No credential references are returned. Conflict payloads carry the observed
        # provider event state (time, status, guests, revision) so an operator can choose;
        # this route is bearer-authenticated and served to the SSO-protected UI only.
        return {"operation": operation, "state": row["state"], "sender": row["sender"],
                "activity_id": data.get("activity_id"), "conflict": conflict,
                "sync_error": data.get("sync_error")}

    @app.post("/meetings/{operation}/reconcile", dependencies=[Depends(auth)])
    def reconcile(operation: str):
        if not app.state.store.get(operation):
            raise HTTPException(404, "Unknown managed operation")
        app.state.store.enqueue(operation)
        return {"status": "queued"}

    @app.post("/meetings/{operation}/confirm-activity", dependencies=[Depends(auth)])
    def confirm_activity(operation: str, body: ConfirmActivity):
        db = app.state.store
        with db.meeting_lock(operation) as locked:
            if not locked:
                raise Blocked("meeting_busy")
            row = db.get(operation)
            if not row or not row["data"].get("linked") or row["data"].get("crm_phase") not in ("activity_intent", "uncertain"):
                raise Blocked("activity_reconciliation_not_applicable")
            activity = app.state.crm.validate_activity(row, body.activity_id)
            row["data"].update(activity_id=activity, crm_phase="activity_confirmed")
            db.save(operation, "crm_pending", row["data"], "operator_confirmed_existing_activity")
            db.enqueue(operation)
        return {"status": "confirmed"}

    def deletion_evidence(row, side):
        from .worker import Worker
        from .providers import ProviderError
        if not row or not row["data"].get("linked") or side not in row["data"]:
            raise Blocked("managed_link_required")
        worker = Worker(app.state.settings, app.state.store, app.state.providers, None, None)
        original_api, copy_api, _ = worker.provider_pair(row)
        api = original_api if side == "organizer" else copy_api
        linked = row["data"][side]
        try:
            current = api.get(linked["id"])
            if current.get("status") != "cancelled":
                raise Blocked("event_still_exists_do_not_confirm_deletion")
        except ProviderError as error:
            if error.status not in (404, 410):
                raise
            if not api.auth_health():
                raise Blocked("calendar_auth_required_for_deletion_review")
        evidence = {"operation": row["operation"], "side": side, "event_id": linked["id"],
                    "uid": linked["iCalUID"], "provider": api.provider, "calendar": api.account["calendar_id"],
                    "subject": api.account["subject"], "tenant": api.account["tenant"],
                    "expected_version": row["updated_at"].isoformat()}
        message = json.dumps(evidence, sort_keys=True).encode()
        evidence["confirmation_token"] = hmac.new(app.state.settings.operator_token.encode(), message, sha256).hexdigest()
        return evidence

    @app.post("/meetings/{operation}/deletion-review", dependencies=[Depends(auth)])
    def deletion_review(operation: str, body: DeletionReview):
        return deletion_evidence(app.state.store.get(operation), body.side)

    @app.post("/meetings/{operation}/confirm-deletion", dependencies=[Depends(auth)])
    def confirm_deletion(operation: str, body: ConfirmDeletion):
        db = app.state.store
        with db.meeting_lock(operation) as locked:
            if not locked:
                raise Blocked("meeting_busy")
            row = db.get(operation)
            evidence = deletion_evidence(row, body.side)  # fresh auth/state, not a replayed 404
            if (body.expected_version != evidence["expected_version"] or
                not hmac.compare_digest(body.confirmation_token, evidence["confirmation_token"])):
                raise Blocked("deletion_review_changed")
            row["data"].setdefault("confirmed_deletions", {})[body.side] = dict(evidence, actor=body.actor, reason=body.reason)
            row["data"].pop("conflict", None)
            db.save(operation, "linked", row["data"], "operator_confirmed_managed_deletion")
            with db.connect() as c:
                db.audit(c, operation, "deletion_evidence", {"side": body.side, "actor": body.actor, "reason": body.reason,
                                                          "event_id": evidence["event_id"], "uid": evidence["uid"]})
            db.enqueue(operation)
        return {"status": "confirmed_for_reconciliation"}

    @app.post("/meetings/{operation}/resolve-time", dependencies=[Depends(auth)])
    def resolve_time(operation: str, body: Resolve):
        from .worker import Worker
        db, s = app.state.store, app.state.settings
        with db.meeting_lock(operation) as locked:
            if not locked:
                raise Blocked("meeting_busy")
            row = db.get(operation)
            if (not row or row["state"] != "sync_conflict" or not row["data"].get("linked")
                or row["data"].get("conflict", {}).get("kind") not in ("time_or_cancellation", "provider_precondition_failed")):
                raise Blocked("no_time_conflict")
            worker = Worker(s, db, app.state.providers, None, app.state.crm)
            original_api, copy_api, _ = worker.provider_pair(row)
            # Same observation as the conflict payload: a confirmed deletion reads as cancelled.
            original = worker.observed_side(original_api, row["data"], "organizer")
            local = worker.observed_side(copy_api, row["data"], "barbara")
            if original.get("etag") != body.organizer_revision or local.get("etag") != body.barbara_revision:
                raise Blocked("conflict_revision_changed")
            cancelled = {side for side, event in (("organizer", original), ("barbara", local)) if event.get("status") == "cancelled"}
            # A cancelled side cannot be revived: for a cancellation-versus-reschedule conflict the
            # explicit source must be the cancelled side, which propagates the cancellation.
            if cancelled and body.source not in cancelled:
                raise Blocked("cancelled_side_cannot_be_revived")
            s.allow_write()
            # Persist the resolution intent, then conditional patch. A crash remains a
            # conflict and requires fresh operator evidence, not a stale replay.
            db.save(operation, "sync_conflict", row["data"], "operator_time_resolution_intent")
            if cancelled:
                if "barbara" not in cancelled:
                    local = copy_api.cancel(local)
                if "organizer" not in cancelled:
                    original = original_api.cancel(original)
            elif body.source == "organizer":
                local = copy_api.patch_time(local, original)
            else:
                original = original_api.patch_time(original, local)
            row["data"].update(organizer=original, barbara=local, ack_organizer=original, ack_barbara=local)
            row["data"].pop("conflict", None)
            if cancelled:
                db.save(operation, "cancelled", row["data"], "operator_cancellation_resolved")
                return {"status": "cancelled"}
            db.save(operation, "linked", row["data"], "operator_time_resolved")
            db.enqueue(operation)
        return {"status": "resolved"}

    @app.post("/meetings/{operation}/acknowledge-guests", dependencies=[Depends(auth)])
    def acknowledge_guests(operation: str, body: OperatorEvidence):
        # Accepts Barbara's local guest edit as reviewed. The next inward RSVP projection
        # rewrites the private copy's guest list from the original; locally added guests
        # are never propagated to the original or notified.
        from .worker import Worker
        db = app.state.store
        with db.meeting_lock(operation) as locked:
            if not locked:
                raise Blocked("meeting_busy")
            row = db.get(operation)
            if (not row or row["state"] != "sync_conflict" or not row["data"].get("linked") or "barbara" not in row["data"]
                or row["data"].get("conflict", {}).get("kind") != "unsupported_local_guest_edit"):
                raise Blocked("no_local_guest_edit_conflict")
            worker = Worker(app.state.settings, db, app.state.providers, None, None)
            _, copy_api, _ = worker.provider_pair(row)
            live = worker.observed_side(copy_api, row["data"], "barbara")
            # Only the guest baseline moves; a concurrent local time change stays unacknowledged.
            row["data"]["ack_barbara"]["attendees"] = deepcopy(live.get("attendees", []))
            row["data"].pop("conflict", None)
            db.save(operation, "linked", row["data"], "operator_acknowledged_local_guest_edit")
            with db.connect() as c:
                db.audit(c, operation, "guest_edit_evidence", {"actor": body.actor, "reason": body.reason,
                                                             "guests": sorted(a["email"].lower() for a in live.get("attendees", []))})
            db.enqueue(operation)
        return {"status": "acknowledged"}

    @app.post("/meetings/{operation}/void", dependencies=[Depends(auth)])
    def void(operation: str, body: OperatorEvidence):
        # Releases a reservation whose sender never attempted the original invitation, so a
        # retired/unhealthy reserved sender stops holding slot capacity forever. Nothing was
        # sent, so nothing is cancelled at a provider. The daily cap charge is not refunded.
        db = app.state.store
        with db.meeting_lock(operation) as locked:
            if not locked:
                raise Blocked("meeting_busy")
            row = db.get(operation)
            if not row:
                raise HTTPException(404, "Unknown managed operation")
            if row["state"] == "cancelled":
                raise Blocked("already_cancelled")
            if row["data"].get("organizer_attempted") or row["data"].get("linked") or "organizer" in row["data"]:
                raise Blocked("void_requires_unattempted_reservation")
            db.save(operation, "cancelled", row["data"], "operator_voided_reservation")
            with db.connect() as c:
                db.audit(c, operation, "void_evidence", {"actor": body.actor, "reason": body.reason, "sender": row["sender"]})
        return {"status": "voided"}

    return app


app = create_app()
