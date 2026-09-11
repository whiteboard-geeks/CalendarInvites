# Build Spec — Distributed Invite Sending + Consultant Calendar Sync

**Status:** Design approved, not yet implemented (blocked on outreach-domain warmup)
**Author:** Lance + Claude
**Last updated:** 2026-07-22

---

## 1. Problem

Today every blind invite is sent from the consultant's **real** Google Workspace
mailbox (`barbara.pigg@whiteboardgeeks.com`, `april.lowrie@whiteboardgeeks.com`).
The consultant is the organizer, so:

- the invite lands in the lead's inbox (warmed, reputable domain), and
- the meeting sits on the consultant's real calendar automatically, and
- the consultant reschedules by **dragging the event** on that calendar (Google
  re-notifies the lead because she's the organizer).

At the volume we want, sending cold invites from `whiteboardgeeks.com` accumulates
spam-complaint signal against the **From domain**, which bleeds into WBG's real
business-email reputation. We want to distribute sends across many **warmed,
disposable outreach domains** — a mix of **Google** and **Microsoft** — so the
reputation risk lands on throwaway domains instead of the primary.

The hard requirement: **no matter which outreach domain/platform sends an invite,
the meeting must come back onto the respective consultant's real calendar**, show
the lead's RSVP + no-show status, and the consultant must keep rescheduling by
**dragging events on her own calendar exactly as she does today**.

### Established constraints (from testing, 2026-07-21)

- Calendar invites ride Google/Microsoft calendar infrastructure, not the domain's
  SMTP path — but the **From domain still collects spam-complaint reputation**, which
  is the thing we're isolating.
- **Cold** outreach domains (brand-new, no warmup) → invites land in **Gmail spam**,
  including RSVP replies. Only **warmed** domains deliver to inbox. There is no
  config that skips warmup; reputation is earned.
- Google-organizer → Google-guest events **auto-link** by iCalUID (RSVP + reschedule
  propagate for free). Microsoft-organizer → Google-guest does **not** link as the
  same event, and a guest **cannot** reschedule an organizer's event in Google
  (dragging a guest copy only sends a "proposed new time").

Because of that last point + the drag-to-reschedule requirement, the consultant must
**own** her calendar event. That forces the **SA-mirror model on both platforms**
(we deliberately give up Google's free guest-linking to keep drag-to-reschedule).

---

## 2. Core model — two roles, one link

Split each invite into two roles and bridge them:

| Role | Identity | Master of… | Backed by |
|------|----------|-----------|-----------|
| **Sending identity** | a warmed outreach mailbox (Google **or** MS), picked from the consultant's pool | the lead's invite email + the lead's RSVP | Google SA (DWD) or Entra app-only (Graph) |
| **Consultant calendar** | the consultant's real mailbox (`*.whiteboardgeeks.com`) | the meeting **time** (she drags it) | Google SA domain-wide delegation on `whiteboardgeeks.com` |

- The **outreach organizer event** talks to the lead.
- The **consultant event** is what she sees and drags.
- They are two separate events (two UIDs) tied by a **stored bidirectional link**.
- The consultant's calendar is the **source of truth for time**; the outreach event
  is the **source of truth for lead comms + RSVP**.

```
                 ┌─────────────────────────────┐
   lead  ◄─────► │ OUTREACH ORGANIZER EVENT     │  (warmed Google or MS mailbox)
 (invite,        │  organizer = outreach mbx    │
  RSVP)          │  attendee  = lead            │
                 └──────────────┬──────────────┘
                                │  link (extendedProperties / mapping row)
                 ┌──────────────┴──────────────┐
 consultant ◄──► │ CONSULTANT EVENT            │  (barbara.pigg@whiteboardgeeks.com)
 (drag to        │  she owns it → can drag      │
  reschedule,    │  labeled ✅/❌ from sync      │
  see status)    └─────────────────────────────┘
```

---

## 3. Auth matrix (who can act as whom)

| Action | Mechanism | Prereq |
|--------|-----------|--------|
| Write/read/accept on **consultant's real calendar** + register **watch channels** | Google SA **domain-wide delegation** on `whiteboardgeeks.com`, `subject=<consultant>` | We own the Workspace ✅ (already used by app) |
| Send/patch invite from a **Google outreach mailbox** | SA DWD on that outreach domain **if we own the Workspace**; otherwise per-mailbox OAuth refresh token | Depends on how Google outreach domains are hosted — see §8 |
| Send/patch invite from a **Microsoft outreach mailbox** | **Entra multi-tenant app-only** (Graph `Calendars.ReadWrite`, `Mail.Send`) | App `WBG Calendar Sender` exists; admin-consent per tenant |

> **SA scope change:** the app currently requests `calendar.events` only. Watch
> channels + reading settings need the broader `https://www.googleapis.com/auth/calendar`
> scope. Update the DWD scope grant in the Workspace admin console AND
> `calendar_utils.SCOPES`.

---

## 4. Data model — the link

Each managed meeting needs a durable mapping. Store it in **both** the event's
`extendedProperties.private` (so it travels with the event) **and** a small
persistent table (so the worker can enumerate without scanning calendars).

### 4.1 On the consultant event (`extendedProperties.private`)
```json
{
  "wbg_managed": "1",
  "wbg_role": "consultant",
  "wbg_link_id": "<uuid>",
  "wbg_outreach_platform": "google|microsoft",
  "wbg_outreach_calendar": "barbara@wbg-invites-01.com",
  "wbg_outreach_event_id": "<google eventId | graph event id>",
  "wbg_known_start": "2026-08-01T15:00:00Z",
  "wbg_known_end":   "2026-08-01T15:30:00Z",
  "wbg_lead_email": "jane@acme.com"
}
```

### 4.2 On the outreach organizer event (`extendedProperties.private` / Graph `singleValueExtendedProperties`)
```json
{
  "wbg_managed": "1",
  "wbg_role": "outreach",
  "wbg_link_id": "<uuid>",
  "wbg_consultant_calendar": "barbara.pigg@whiteboardgeeks.com",
  "wbg_consultant_event_id": "<google eventId>"
}
```

### 4.3 Persistent mapping row (SQLite/Postgres — worker-owned)
```
link_id            uuid  pk
consultant_key     text  -- "barbara_pigg"
consultant_cal     text
consultant_evt_id  text
outreach_platform  text  -- google | microsoft
outreach_mailbox   text
outreach_evt_id    text
lead_email         text
lead_ical_uid      text  -- outreach event iCalUID (for METHOD:REQUEST continuity)
known_start        timestamptz
known_end          timestamptz
rsvp_status        text  -- needsAction | accepted | declined | tentative
attended           text  -- unknown | joined | no_show   (from Zoom)
state              text  -- active | cancelled
updated_at         timestamptz
```

`wbg_known_start/end` is the **loop guard**: the worker compares against it to tell a
time change (reschedule) apart from a status-label write.

---

## 5. `consultant_config.py` changes

Add a **sending pool** and split the real calendar out as its own field. The pool
holds warmed outreach mailboxes across both platforms; weighting is decided **after
warmup** (start balanced, shift toward whichever inboxes better).

```python
CONSULTANTS = {
    "barbara_pigg": {
        "basic_info": { ... },                       # unchanged
        # NEW: the authoritative "comes-back-to" calendar
        "real_calendar": "barbara.pigg@whiteboardgeeks.com",
        # NEW: warmed outreach mailboxes this consultant sends AS
        "sending_pool": [
            {"platform": "google",    "mailbox": "barbara@wbg-invites-01.com",
             "weight": 1, "daily_cap": 40, "warmup_state": "warming"},
            {"platform": "microsoft", "mailbox": "barbara@wbg-invites-02.com",
             "weight": 1, "daily_cap": 40, "warmup_state": "warming"},
        ],
        "meeting":  { ... },                          # unchanged (Zoom room)
        "templates":{ ... },                          # unchanged
        "crm_integration": { ... },                   # unchanged
    },
    "april_lowrie": { ... },
}
```

- `calendar_utils.get_current_calendar_id()` → returns `real_calendar` (unchanged
  behavior: the consultant event is still written to her real calendar).
- **New** selector `pick_sending_identity(consultant_key)` → chooses a pool entry:
  round-robin, skipping mailboxes over `daily_cap` or not `warmup_state == "ready"`.
  Records the send against a per-mailbox daily counter (respect Google's per-user
  external-invite throttle and MS per-mailbox limits).

---

## 6. Send flow (replaces `create_calendar_invite`)

Given a `task` (lead), consultant, and chosen slot:

1. `identity = pick_sending_identity(consultant_key)`.
2. **Create the outreach organizer event** on `identity.mailbox`:
   - **Google identity:** SA (DWD on outreach domain, `subject=identity.mailbox`)
     `events.insert(calendarId=identity.mailbox, sendUpdates="all")`,
     `attendees=[lead]`, summary/description/location from templates.
   - **Microsoft identity:** Graph app-only
     `POST /users/{identity.mailbox}/events`, `attendees=[lead]`. Graph sends the
     invite on create.
   - Capture `outreach_evt_id` and (Google) `iCalUID`.
3. **Create the consultant event** on `real_calendar` via SA DWD
   (`subject=real_calendar`): same summary/time/Zoom location, **no lead attendee**
   (she owns it; the lead is handled by the outreach event). Set her
   `extendedProperties` (§4.1) with `wbg_known_start/end`.
4. **Back-fill** `wbg_consultant_event_id` onto the outreach event (§4.2) and write
   the **mapping row** (§4.3).
5. Existing Close CRM task-completion + activity logging stays as-is, keyed to the
   consultant event.

> Idempotency: reuse `check_lead_invite_exists()` (extend it to also check the
> mapping table by `lead_email`) so a lead never gets two live outreach events.

---

## 7. Reschedule flow (preserve drag-to-reschedule)

The consultant drags/deletes on her real calendar exactly as today. A worker
propagates the change to the outreach organizer, which re-notifies the lead **from
the same warmed sending identity** (same UID, `SEQUENCE++` — an update, not a fresh
cold invite).

### 7.1 Watch channels
- For each consultant's real calendar, register a Google **`events.watch`** push
  channel → HTTPS webhook on the worker.
- Channels expire (~7–30 days); worker **renews** before expiry and on `sync` errors.
- Store channel id/resourceId/expiration per consultant.

### 7.2 On webhook fire
1. `events.list(..., syncToken=...)` to pull only changed events (incremental sync).
2. For each changed event with `wbg_managed == "1"` and `wbg_role == "consultant"`:
   - **Deleted / status=cancelled** → cancel the linked outreach event
     (Google `events.delete(sendUpdates="all")` / Graph `POST .../cancel`), mark
     mapping `state=cancelled`. Lead gets a real cancellation.
   - **`start/end` differ from `wbg_known_start/end`** → it's a **reschedule**:
     patch the linked outreach organizer event to the new time —
     - Google: SA `events.patch(calendarId=outreach, eventId, body={start,end}, sendUpdates="all")`
     - Microsoft: Graph `PATCH /users/{outreach}/events/{id}` with new `start/end`
       (Graph auto-sends the update to attendees).
     Then update `wbg_known_start/end` on the consultant event + mapping row.
   - **Only labels/other fields changed, time identical** → **ignore** (this is the
     loop guard; RSVP-label writes from §9 land here and must be no-ops).

### 7.3 Loop prevention (critical)
- Worker writes to the **outreach** calendar never touch the consultant's watch
  channel → no echo from reschedule propagation.
- Worker writes to the **consultant** event (RSVP labels, §9) *do* fire the channel,
  but leave `start/end` untouched → step 7.2 ignores them because time == known time.
- Always compare **time specifically**, never "did anything change."

---

## 8. Google outreach domains — hosting decision (affects §3/§6)

Two ways to be able to send *as* a Google outreach mailbox:

- **(A) We own the outreach Workspace(s)** → enable SA domain-wide delegation on each
  outreach domain (same pattern as primary). Cleanest; SA sends + patches directly.
- **(B) Zapmail-hosted Google mailboxes** → we likely lack super-admin to grant DWD,
  so obtain a **per-mailbox OAuth refresh token** (Zapmail `custom-oauth` with our
  Google Cloud client, scope `https://www.googleapis.com/auth/calendar`), stored
  encrypted, refreshed by the worker.

**Recommendation:** for the Google side, stand up **our own** dedicated warmed
Workspace outreach domains (option A) — DWD is far simpler than juggling refresh
tokens, and we control warmup + admin. Reserve Zapmail for the Microsoft side, where
the Entra app-only path already works cross-tenant.

> Consultant primary calendar is always option A (we own `whiteboardgeeks.com`).

---

## 9. RSVP + no-show sync (labels on the consultant's calendar)

The lead's response goes to the **outreach** organizer, not the consultant. Reflect
it onto her event so she sees status at a glance.

- **RSVP:** worker watches each outreach event's attendee status —
  - Google outreach: `events.get` polling on the syncToken, or a **second watch
    channel** per outreach mailbox.
  - Microsoft outreach: Graph **change-notification subscription** on
    `/users/{mbx}/events` (webhook), or poll.
  On change, patch the **consultant event summary** with a status prefix, e.g.
  `✅ ACCEPTED — Jane @ Acme`, `❌ DECLINED — …`, `⏳ NO REPLY — …`. **Time unchanged**
  → safe against the loop guard.
- **No-show:** after the meeting end, pull Zoom attendance (existing Zoom integration)
  for the consultant's room; if the lead never joined, set `attended=no_show` and
  prefix `🚫 NO-SHOW — …`. The consultant then drags it to a new slot (→ §7), which
  re-invites the lead automatically.

---

## 10. Worker service — responsibilities

A single long-running service (own repo module, deploy on the existing WBG apps host
or `groundwork-apps`; runs under Temporal or as a small FastAPI + scheduler):

1. **Watch-channel lifecycle:** register/renew Google push channels for every
   consultant calendar + every Google outreach mailbox; maintain Graph subscriptions
   for MS outreach mailboxes.
2. **Reschedule/cancel propagation:** consultant event change → outreach event
   (§7).
3. **RSVP/no-show sync:** outreach event / Zoom → consultant event labels (§9).
4. **Warmup gating:** expose per-mailbox `warmup_state`; only `ready` mailboxes enter
   the send rotation. Track daily send counts vs caps.
5. **Idempotency + loop-guard** everywhere (compare against stored known-state).

State store: the mapping table (§4.3) + a `channels` table + a `send_counters` table.

---

## 11. Failure modes & handling

| Case | Handling |
|------|----------|
| Watch channel expired/missed | Periodic full incremental `syncToken` reconcile as a backstop to webhooks |
| Consultant edits title/notes (not time) | Ignored by time-compare loop guard |
| Both a status write and a drag arrive close together | Status write is time-neutral; drag changes time → each evaluated independently |
| Outreach mailbox hits daily cap mid-run | `pick_sending_identity` skips it; alert if a consultant's whole pool is capped |
| Outreach domain reputation tanks | Pull it from pool (`warmup_state != ready`); in-flight events keep working (already sent) |
| Lead replies to the invite email | Goes to the outreach mailbox; route/forward per outreach-inbox policy (out of scope here) |
| Cross-platform reschedule not delivered (MS→Gmail spam) | Same reputation caveat as initial send; mitigated only by warmup |

---

## 12. Phased rollout

1. **Phase 0 — infra (can start now):**
   - Add `real_calendar` + `sending_pool` to `consultant_config` (pools empty/`warming`).
   - Broaden SA scope to `.../auth/calendar`; add DWD on primary (verify).
   - Scaffold the worker + mapping/channels tables. Wire watch channels on the two
     real calendars; prove reschedule/cancel/label round-trips using the **primary
     mailbox itself** as a stand-in "outreach" identity (no warmup needed to test the
     plumbing).
2. **Phase 1 — Google outreach:** stand up + warm 1–2 owned Google Workspace outreach
   domains; enable SA DWD; add to pools as they reach `ready`.
3. **Phase 2 — Microsoft outreach:** provision + warm new WBG Zapmail MS domains
   (old test domains discarded); admin-consent the Entra app per tenant; add to pools.
4. **Phase 3 — measure & weight:** run real invites through both platforms; shift
   pool `weight` toward whichever delivers to inbox better (the "decide after warmup"
   call).

---

## 13. Reference — identities & prior work

- **Entra app (MS send):** `WBG Calendar Sender` — multi-tenant, app-only Graph
  `Calendars.ReadWrite` + `Mail.Send` + `Mail.Read`, admin-consented. Client secret
  re-mintable via `az ad app credential reset` as tenant admin. (Test tenant:
  `whiteboardgeekmailerpros.com` / `w6b749ew0f.onmicrosoft.com` — a **test** domain to
  be discarded; do not use for production.)
- **Zapmail:** MS mailboxes live in the **WBG** Zapmail workspace, Google in
  **Groundwork**; the API **key** selects the workspace, not the `x-service-provider`
  header. Mailbox list = `GET /v2/mailboxes/list` (`GET /v2/mailboxes` 500s).
- **Google SA:** `streamlit@…` service account, DWD on `whiteboardgeeks.com`, used by
  `calendar_utils.get_calendar_service()` via `credentials.with_subject(calendar_id)`.
- **Deliverability reality:** cold outreach domains → Gmail spam until warmed; the
  whole model depends on warmed outreach domains + high lead-accept / low
  spam-complaint rates. See project memory `project_wbg_calendar_invites.md`.
