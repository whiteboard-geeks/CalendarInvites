# Barbara: sender pools and two-way calendar synchronization

Status: proposed scope; group rotation and native RSVP requirements confirmed; implementation not approved.
Prepared: 2026-09-09. No production settings or application code changed.

**Architecture reaffirmed:** see `calendar-confirmed-requirements.md`.
Barbara's edits must update the original sending account's existing event via API.
Keep that organizer and event identity fixed. Lance rejected both a required Chrome
extension and the alternative rotating-initial-mail model; neither is the plan.

**Native-UX limitation, separate from API sync:**
`calendar-private-owner-and-drag-results-2026-09-09.md` records failed native drag
on both delegated and own-account private copies, alongside a passing organizer-owned
control. Full Edit/Save worked with Google's confirmation; API propagation is proven.
The automatic worker still needs implementation. Do not claim dragging is solved or
redirect the architecture because of that UI limitation. Barbara uses Chrome.

**Feasibility results:** `calendar-spike-results-2026-09-09.md` supersedes the
untested representation assumptions below. Native RSVP, provider response roundtrips
and manual time/cancellation bridging passed; full native UX remains a release gate.
The candidate is an externally organized private copy with Barbara as an accepted
local-only attendee, not a Barbara-organized mirror. All tracked test events were removed.

## 1. Prior decisions and what changes now

Found the July 22 chat `b6985e8b-a378-4802-9e02-cd02259816a3`
(Obsidian/Oratory), including its closing request to write a build spec.
The result is `docs/distributed-sending-and-calendar-sync.md`; preserve that
approved historical draft rather than silently rewriting it.

Previously agreed: spread sends across warmed Google/Microsoft outreach identities,
put an owned event on the consultant's real calendar, and preserve drag-to-reschedule.
The two-event model is still the right starting point. Merely inviting Barbara as
an attendee does not give her organizer authority over the outreach event.

Today's additions:
- Three selectable sources: Barbara main, Instantly Google, Instantly Microsoft.
- Discover many eligible mailboxes from Instantly rather than a static pool.
- Changes to the outreach organizer event must also reach Barbara, not just RSVP.
- Preserve Barbara's existing title/emoji automations; do not introduce competing labels.

The old spec's time-only loop guard, lead-email duplicate check, and simple send
sequence are insufficient for bidirectional synchronization and retry safety.
Historical auth/deliverability experiments are leads, not proof of current access
or guaranteed inbox placement. Instantly warmup is not a calendar delivery guarantee.

## 2. Current implementation: actual integration points

- `calendar_utils.py`: Google-only, identity taken from Streamlit session state;
  `create_calendar_invite()` creates one event directly on the consultant calendar.
- `blind_invite.py:1329`: calls create, ignores the result, then completes the Close
  task and logs success. Creation can return None on an HTTP error. Replace this
  success assumption as part of durable sending, not as an unrelated refactor.
- `check_lead_invite_exists()` searches calendar attendees and treats API errors as
  safe to send. An attendee-free mirror breaks that lookup. Use durable operation
  records plus legacy-event checks; unknown duplicate-check status must block sending.
- Scheduling already reads the consultant's calendar and supports multiple leads
  per block. Keep that capacity policy; reserve capacity transactionally so two
  operators cannot overbook it. Outreach calendars are not independent availability.
- No durable meeting-link store or sync worker in the current implementation.

## 3. Operator experience and eligibility

For Barbara only at first, show:
- [ ] Main calendar
- [ ] Google calendars in Instantly — eligible / total
- [ ] Microsoft calendars in Instantly — eligible / total

Show projected allocation before sending. Require at least one usable source;
never silently enable the main calendar or another unchecked source as fallback.
Existing behavior remains the default during rollout; outreach pools are opt-in.

An expandable account table shows mailbox, verified provider, Barbara ownership,
Instantly connection status, active campaign assignments, recent outbound use,
warmup/review status, calendar authorization health, invite count/cap, last checked,
and a specific exclusion reason. Include an audited manual disable control.

Discovery is read-only: paginate Instantly accounts and campaign/account mappings.
The shared Instantly workspace includes April and Groundwork senders; do not use
all connected accounts or trust a local-part prefix as ownership authorization.
Seed an explicitly reviewed Barbara registry with stable provider/tenant identity.
Provider comes from verified metadata, not the email domain's spelling.

Proposed eligibility = reviewed Barbara ownership + selected provider group +
connected/not paused + assigned to an approved active Barbara campaign + reviewed
readiness + working calendar read/write grant + under invite cap + fresh health data.
Show recent usage separately; zero sends today does not necessarily mean inactive.
Confirm exact API fields/status semantics in the read-only inventory phase.
Known local evidence: Instantly account status 1 is connected, -1 disconnected;
campaign sending-status can lag by an hour. Verify individual accounts at send time.

An Instantly email connection does NOT grant this app Google Calendar/Graph access.
Google DWD requires Workspace-admin authorization; otherwise obtain appropriate
per-mailbox OAuth consent and securely retained refresh tokens. Microsoft requires
validated Graph calendar grants and tenant consent. Do not assume July test grants
or Zapmail-exported Instantly tokens are usable by this application.

### Rotation decision — confirmed by Lance

> Three checked groups.

Rotate Main → Google → Microsoft across the checked groups, then round-robin
eligible mailboxes within each group. With all three selected, each group receives
approximately one third of successful new invitations, regardless of mailbox count.
With two selected, alternate those two. Retries retain their reservation and sender;
they do not advance either cursor or count as a new invitation.

Persist group and per-group mailbox cursors, reservations and counters in the
database, not Streamlit; lock allocation under concurrency. Caps apply per mailbox
and optionally per domain. Define counter timezone centrally. Do not blindly reuse
Instantly email limits as calendar-invite limits. Proposed conservative exhaustion
policy: skip unavailable mailboxes within the assigned group; if the entire group
is unusable, pause the batch and surface the reason rather than silently changing
the approved allocation. Operator may explicitly resume with a different selection.

Selection controls NEW invites only. Existing meetings retain their organizer and
continue syncing even after that account leaves the eligible sending pool.

## 4. Event model and ownership

**Revised requirement:** Barbara must work in ordinary Google Calendar with normal
organizer-style controls, not an attendee-free placeholder plus a second admin UI.
The original simple mirror is NOT sufficient. See
`docs/barbara-native-calendar-feasibility.md` for the proposed private-copy spike
and the release-blocking native interaction tests.

One logical meeting, one lead-facing organizer event:
- Main-calendar sender: one real event on Barbara's calendar; no mirror.
- Outreach sender: organizer event on the selected mailbox, plus a local control
  copy on Barbara's main calendar. Native guest/RSVP visibility and edit behavior
  are mandatory feasibility gates, not claimed capabilities yet.
- Do not additionally invite Barbara to the organizer event: that risks a second
  visible copy. The local copy must not independently send meeting invitations.
- The original external organizer identity stays fixed throughout reschedules/cancellation.
- Do not ship a reduced attendee-free mirror as a fallback without Lance's approval.

Persist meetings, event links, last-observed per-side snapshots/revisions,
operation idempotency keys, jobs/outbox, conflicts, sender registry, rotation
reservations, sync cursors/subscriptions, and an audit history. Provider IDs plus
mailbox/calendar/tenant identify an event; private provider metadata assists recovery.
Use stable Graph IDs where supported. Do not use email alone as a lifetime meeting key:
repeat outreach can be legitimate. Scope creation idempotency to the reviewed
business operation (e.g. consultant + Close task), with a separate live-invite warning.

### Field contract

- Start/end/timezone: bidirectional; normalize comparison without losing zone/DST intent.
- Cancellation: bidirectional explicit cancellation of a managed event; recipient
  decline is RSVP, NOT cancellation. A permission error or unavailable calendar is
  NOT evidence of deletion. Verified deletion/tombstone and audit required.
- RSVP: external organizer → local guest response display, if the private-copy
  spike proves this works without invitation propagation. Stored RSVP/app text alone
  does not satisfy the native-experience requirement. Audit existing automations.
- Titles: preserve local automation decorations. Refined proposal: synchronize actual
  business-title edits while retaining known local decoration, using audited automation
  rules and separate canonical/local title snapshots. An emoji-only change must
  produce zero remote calendar writes and zero attendee notifications. Never strip
  every Unicode emoji heuristically or assume every title-only edit is an automation.
- Description/location/Zoom: normal manual business-field edits should flow both
  directions. Use per-field snapshots and preserve local notes/metadata, not whole
  stale event replacement. Provider-specific conference ownership requires testing.
- Guest add/remove edits on Barbara's control copy should update the external
  organizer; external guest list and RSVP changes should return to her native view.
  This is gated on proving that her control copy cannot independently notify guests.

A recipient usually cannot move the organizer's event directly. Accept/decline is
RSVP; 'propose new time' is a proposal, not a confirmed reschedule. Confirm provider
support for surfacing proposals; propose manual acceptance for v1. Once accepted
and the organizer event actually changes, synchronize it to Barbara.

## 5. Durable sending and two-way worker

Use a small backend/worker with Postgres and a durable jobs/outbox table; Streamlit
submits commands and shows status. Avoid introducing a workflow engine solely for
this feature unless the deployment already operates one.

Creation states:
`reserved → organizer_pending → organizer_created → mirror_pending → linked → crm_pending → complete`.
Main-calendar sends skip mirror creation. Reserve operation/sender/slot first.
Use provider-supported idempotency (Google client event ID; Graph transactionId),
plus stored recovery identifiers. On ambiguous timeout, reconcile before retrying;
never select a second sender while the first send may have succeeded. Do not cancel
and resend automatically because mirror creation failed: repair the missing mirror.
Do not mark Close complete until required events are confirmed. Retry CRM writes
independently and deduplicate custom activities; a CRM outage must not resend invites.

Watch BOTH Barbara and outreach calendars. Webhooks enqueue work; fetch authoritative
provider state and serialize work per meeting. Store per-calendar sync cursors and
pagination progress durably. Renew subscriptions using returned expirations, verify
webhook tokens/clientState, handle initial sync, lost notifications, invalid cursors,
rate limits and backoff. Incremental reconciliation is the fallback, not unbounded
polling of every event. Rebuild expired cursors without interpreting absent pages as deletions.

Compare the latest managed fields on BOTH sides with their last acknowledged
snapshots. Apply a single-side change using provider concurrency controls where
available, then re-read and advance snapshots. Ignore matching echoes. Provider
revision IDs are opaque; do not compare their values across vendors.

If both sides changed the same field differently, record a conflict and pause that
field rather than using webhook arrival order as last-writer-wins. Resolve in app:
use Barbara time or organizer time, showing old/current values and actor evidence.
Cancellation-versus-reschedule races also require an explicit rule/conflict review.
Do not overwrite a fresh user edit with a stale retry job; re-evaluate desired state.

### Concrete state traces

Notation: B=Barbara, O=outreach, S=acknowledged times, Q=durable pending work.

1. Barbara drag plus emoji:
   - t0 B={time:10,title:Call}, O={time:10,title:Call}, S={B:10,O:10}, Q=[]
   - t1 B={time:11,title:✅ Call}, O={time:10,title:Call}, S unchanged.
   - t2 fresh comparison detects B-only time edit; Q=[patch O.time=11].
   - t3 O patch confirmed; B={11,✅ Call}, O={11,Call}, S={B:11,O:11}, Q=[].
   - t4 duplicate/echo notification fetches identical times: no write. Title untouched.

2. Outreach reschedule, then competing Barbara edit before propagation:
   - t0 B={time:10}, O={time:10}, S={B:10,O:10}.
   - t1 software sets O={time:12}; before worker writes, Barbara sets B={time:11}.
   - t2 worker fetches both: B differs from S.B and O differs from S.O; 11 != 12.
   - result conflict={B:11,O:12}; neither edit silently overwritten; operator resolves.
   - without the Barbara edit, worker would patch B to 12, retaining her title.

3. Organizer create succeeds, response is lost:
   - t0 DB={operation:k,sender:g1,state:organizer_pending}, O=absent.
   - t1 provider creates O=e1; network times out; DB still organizer_pending.
   - t2 retry reconciles operation k with provider identity; finds e1.
   - t3 create/repair B mirror, persist link, then process CRM; never create g2/e2.

4. Sender becomes disconnected after a meeting was sent:
   - t0 registry={new_sends:true}, meeting={organizer:g1,active:true}.
   - t1 inventory marks new_sends=false; meeting remains bound to g1.
   - t2 if calendar grant works, existing sync continues; if revoked, retain jobs,
     alert and display degraded status. Never migrate organizer or claim sync succeeded.

5. Recipient declines:
   - t0 O={time:10,rsvp:needsAction}, B={time:10,title:Call}.
   - t1 O={time:10,rsvp:declined}; store RSVP, retain meeting/time/title.
   - t2 any existing Barbara automation may label B; title-only webhook is a no-op.

## 6. Phases and acceptance gates

1. **Read-only inventory/auth/automation audit.** Identify Barbara's actual Google
   and Microsoft mailboxes, active use, tenants, credentials available, and current
   emoji/RSVP automations. Report ready vs blocked and exact consent gaps. No account
   reconnection, consent changes, real invitations or domain purchases in this phase.
2. **Controlled provider spike.** With approved test recipients, prove one Google
   outreach + one Microsoft outreach + Barbara test calendar: organizer identity,
   lead receives only one invite, drag works both ways, cancellation, RSVP, titles,
   permissions and subscription behavior. Inspect notifications, not only API 200s.
3. **Durable foundation.** Database migrations, provider adapters detached from
   Streamlit, operation recovery, sender reservation, Close gating, sync worker,
   audit/conflict/degraded-state UI. Keep production sending feature-flagged off.
4. **Pool UI/inventory.** Three checkboxes, counts, account table, reviewed ownership,
   eligibility and allocation preview. Test concurrent operators and cap exhaustion.
5. **Barbara canary.** Small approved batch, one sender per enabled provider, short
   observation period; reconcile manually before expanding. Freeze new outreach
   sends on rollback but keep sync/repair running for existing outreach meetings.
6. **Scale.** Add remaining authorized mailboxes gradually, measure webhook lag,
   failures, duplicate suppression, account/domain limits and actual delivery.

Required tests: no boxes/all combinations; empty selected pool; stale inventory;
wrong-consultant account exclusion; simultaneous sends; title-only edits; both sync
directions; duplicate/reordered webhooks; concurrent time edits; DST; explicit delete
vs 403/404 ambiguity; decline vs cancellation; create timeout; mirror failure;
worker crash/restart; CRM failure; auth revocation; cap exhaustion; cursor expiry;
legacy invites still recognized; no duplicate Barbara event on main-calendar sends.

V1 excludes new emoji/no-show automation, automatic acceptance of recipient time
proposals, arbitrary recurrent-series edits, historical-event migration, bulk
mailbox/domain provisioning, and silent organizer migration. Existing appointments
continue their current behavior; manage newly created meetings first.

## 7. Decisions / unresolved gates

- Confirmed: rotate equally across checked groups, then within each provider group.
- Approve/refine 'being used': proposed active approved campaign assignment, not merely connected.
- Inventory must establish Google calendar access; neither current mailbox counts
  nor working production grants were checked during this planning pass.
- Native organizer-style experience is a release gate, not a nice-to-have.
  Prove private-copy edit/guest/RSVP/notification behavior before choosing the local
  event implementation; inspect existing title automations for compatibility.
- Confirm cancellation policy (deleting a managed mirror cancels the lead's event),
  conflict handling and which non-time fields belong in v1 before rollout.
- Deployment target, synchronization latency target and alert owner remain to choose.

## References

- Prior approved repo spec: `docs/distributed-sending-and-calendar-sync.md`.
- Local Instantly collection: `Instantly API v2/QUIRKS.md`, account list/get and campaign mapping endpoints.
- Google incremental sync: https://developers.google.com/workspace/calendar/api/guides/sync
- Google push notifications: https://developers.google.com/workspace/calendar/api/guides/push
- Microsoft event updates: https://learn.microsoft.com/en-us/graph/api/event-update?view=graph-rest-1.0

Use least-privilege calendar scopes verified against selected endpoints. Do not
carry forward the older draft's blanket broader-scope/watch-lifetime assumptions
without checking current provider requirements. Secrets stay outside source and logs.
