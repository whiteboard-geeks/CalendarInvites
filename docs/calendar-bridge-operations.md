# CalendarInvites original-event bridge — deployment and operations

Implementation: branch `webapp`; new routing defaults **OFF**, dry run defaults **ON**.
The approved historical `distributed-sending-and-calendar-sync.md` is unchanged.
This slice retains the original Google/Graph organizer, not a new sending model.

## Confirmed provider evidence (parent, 2026-09-09)

- Google same-UID `events.import`: actual stale If-Match -> 412 with no write;
  actual current event.etag -> 200, same event ID. Worker rebases RSVP only onto
  freshly fetched complete local fields on 412 (maximum three imports), preserving
  local time, title/emoji, description, location, reminders, color and metadata.
  Unknown fields/unsupported recurring representation block rather than disappear.
- Graph actual current @odata.etag PATCH succeeds and changes revision; stale real
  revision -> 412 ErrorIrresolvableConflict with no write. A fabricated tag caused
  500, so code never categorizes arbitrary 500 as a conflict.
- Parent also exercised the actual `bridge.providers.Graph` adapter against a
  controlled 2035 attendee-free event: two create calls returned the same immutable
  ID with exactly one POST; the chosen extended-property Any filter, marker and
  organizer validation passed. Fixture deleted and temporary credential revoked.
  Existing Google service-account full Calendar scope/calendarList owner health
  was independently verified on the controlled primary account (not all outreach grants).
- Native private-copy full Edit/Save worked; dragging did NOT. No browser hacks,
  extension, organizer substitution or claims that drag is solved.
- Instantly official metadata and live read-only inventory verified: provider_code
  2 Google, 3 Microsoft; account status 1 active, 2 paused, 3 maintenance, negatives
  unhealthy. `setup_pending=false` required. Warmup/score are displayed, not proof
  of calendar authorization or deliverability. Instantly account status 1 is enough; a running campaign is not required.
  Close outgoing mail in the last 30 days pins the invite to that from-address
  when the mailbox is eligible; otherwise checked groups round-robin.
  Names/prefixes never approve ownership. Missing usage is explicitly unknown,
  not zero and not a standalone exclusion.
- GET `/accounts`, `/account-campaign-mappings/{email}` use `items` and opaque
  `next_starting_after`, including an empty terminal page. GET `/accounts/{email}`
  and `/campaigns/{id}` supply fresh eligibility evidence. GET
  `/accounts/analytics/daily` uses repeated `emails` keys plus start/end dates;
  top-level array rows `email_account,date,sent` (including subsequences).
  Inventory is read-only, paced below published rate limits; no email-list calls.

## Deployment contract — parent executes, worker did not deploy

Verified host: **wbg-apps**, `87.99.151.184`, existing host Caddy site
`app.whiteboardgeeks.com`. NOT Groundwork. Isolated Compose project, no shared DB
or neighbor networks. Code `/opt/calendar-invites`, mounted server configuration
`/etc/calendar-invites`, persistent Postgres `/var/lib/calendar-invites/postgres`.
API loopback `8792`, UI loopback `8793` (recheck both before deploy). Database has
**no published ports**. Only API/worker have both private DB and outbound networks.

1. Curate a release from the Docker allowlist; never copy the whole working tree
   (legacy repo contains credential files). `.dockerignore` is deny-by-default.
2. Provision external files from approved secret store without printing values.
   `deployment/bridge.env.example` contains path references, not actual secrets.
   `registry.example.toml` has unapproved, zero-cap examples; replace only after
   explicit ownership, stable tenant/user/calendar identity and calendar grant review.
3. Split `/etc/calendar-invites` by consumer. `backend/` (registry, database_url,
   operator_token, Instantly/Close/Google/Graph credential files) is mounted only
   into api/worker/migrate: files root:10001 0440, directory 0750. `postgres_password`
   is mounted only into PostgreSQL; the official image reads it as uid 999, which on
   wbg-apps collides with the host `systemd-journal` group, so keep it root:root 0444
   inside the 0750 root:10001 directory (directory permissions are the barrier). `streamlit-secrets.toml` is mounted only
   into the UI (root:10001 0440). Do not mount keys in Streamlit except the existing
   legacy Google/Close secrets it already requires.
4. Backend `database_url` file format is
   `postgresql://calendar_invites:<URL-encoded password>@postgres:5432/calendar_invites`.
   `operator_token` must contain a random token of at least 32 characters. All data
   and operator routes require `Authorization: Bearer …`; never store this token in
   a browser/localStorage/query string. Streamlit makes server-side requests.
5. Google credential files support service-account JSON with explicitly authorized
   delegation to registry subject (Barbara's main calendar), or authorized-user OAuth.
   **Instantly Google method (confirmed 2026-09-10):** Zapmail mailbox login + Google
   Calendar OAuth. `GOOGLE_OUTREACH_CREDENTIAL` is an `authorized_user_map` JSON
   (client_id/secret plus per-mailbox refresh tokens). The worker refreshes access
   tokens in memory. While the Google Cloud OAuth app stays in Testing, refresh tokens
   expire in 7 days — renew with `deployment/google-outreach-reauth.py` (Playwright +
   Zapmail TOTP) at least every 4 days and copy the file to
   `/etc/calendar-invites/backend/google_outreach_credential.json` on wbg-apps.
   Scope is `https://www.googleapis.com/auth/calendar`. Instantly connectivity never
   grants Calendar. Graph file contains `client_id`/`client_secret`; registry supplies
   tenant and stable user/calendar ID. Zapmail Microsoft `zapmail-admin@` org-consent
   of the calendar-only multi-tenant app is the Instantly Microsoft method.
   `canEdit` and live calls confirm health; never infer grant from mail auth.
6. Streamlit mounted `streamlit-secrets.toml` retains existing app secrets and adds
   `[calendar_bridge]` with `url="http://api:8000"` and the matching operator token.
   Do not commit that file. Legacy consultants remain unchanged. Backend registry
   supports only Barbara; no arbitrary browser calendar/tenant/sender injection.
7. Run from the curated release directory (commands are a handoff, not executed):

```sh
# External configuration must exist before Compose interpolation/runtime.
export RELEASE_TAG=<reviewed-immutable-release>
export CONFIG_DIR=/etc/calendar-invites STATE_DIR=/var/lib/calendar-invites
# Layout: $CONFIG_DIR/bridge.env, $CONFIG_DIR/backend/*, $CONFIG_DIR/postgres_password,
# $CONFIG_DIR/streamlit-secrets.toml (see step 3 for ownership).
docker compose build api worker ui
docker compose up -d postgres
docker compose --profile tools run --rm migrate
docker compose up -d api worker ui
curl --fail http://127.0.0.1:8792/healthz
curl --fail http://127.0.0.1:8792/readyz
curl --fail http://127.0.0.1:8793/calendar-invites/_stcore/health
```

8. Validate/install `deployment/calendar-invites.caddy` into the existing site's
   apps import. UI prefix is **not stripped** and uses existing `forward_auth` SSO.
   Parent must confirm authorized staff and existing login-denial redirect behavior.
   The API is not published through Caddy at all: Streamlit uses the private Compose
   network and operators use loopback 8792 over SSH. No public webhook paths exist,
   so do not add webhook exceptions. Caddy owns public TLS, not Compose.
9. Keep `BRIDGE_NEW_SENDS=false`, `BRIDGE_DRY_RUN=true`, and
   `CALENDAR_BRIDGE_UI_ENABLED=false` until independent acceptance/deployed health and
   parent-controlled canary. Dry-run is a write prohibition, not simulated success;
   UI displays disabled status and POST sends fail closed. Inventory reads can run.
   Google import CAS is independently proven; `BRIDGE_IMPORT_CAS_VERIFIED=false`
   remains an emergency regression switch. It blocks outreach reservations and
   produces explicit RSVP degraded state for existing links; never silently PATCH
   another guest's response.

## State, capacity, retry and observability

- PostgreSQL UTF8 is required (emoji titles are stored intact). Explicit additive
  schema v1 via `python -m bridge.store`; API startup never fabricates migrations.
- One consultant row lock transactionally selects checked-group equal rotation,
  then sorted mailbox successor rotation, charges UTC-day calendar caps and reserves
  the task/slot/job before mutating provider I/O. Exhausted selected group pauses;
  no unchecked or other-group fallback. Mailbox caps are distinct from Instantly
  email limits; no domain caps in v1. Reserved attempts stay charged conservatively.
- Fresh main-calendar availability is read under that allocation lock. Placeholder
  title is server-reviewed; overlap count plus pending reservations respects the UI's
  leads_per_block (bounded by server max), without counting linked entries twice.
  This serializes app operators, not unrelated humans creating events concurrently
  in Google; that external race cannot be transactionally locked by Postgres.
- Operation = Barbara + Close task, not lifetime lead email. Existing legacy invite
  lookup is paginated and errors block sending. Explicit authenticated
  `allow_existing=true` permits a separately reviewed new operation for a repeat lead.
- Stable Google deterministic ID and Graph transactionId plus persistent operation
  extended property recover ambiguous create results on the SAME mailbox. Graph
  property is `String {7ca9b8f0-90d8-4e8b-91cd-8805c12bfb51} Name CalendarInvitesOperation`;
  value is SHA256 operation key. Recovery uses documented extended-property Any
  filtering, pagination, marker/organizer validation and unique-match assertion,
  never unproven transactionId filtering. Failed lookup blocks instead of resending.
- Original + required private copy must be confirmed before Close activity/task.
  Main is one normal native event, no private copy. Outreach copy keeps external
  organizer, real guests, local-only accepted Barbara and asserted `privateCopy=true`.
  A copy-creation failure repairs the copy without re-inviting the customer.
- Close custom-activity intent is committed BEFORE POST. Timeout/crash/unknown
  response enters `crm_uncertain`; **never blind repost**. Confirm an existing
  activity by ID through the authenticated route (type, lead, dates, optional
  operation custom field verified). Task PUT retries independently and never creates
  another activity or another calendar event. Optional operation custom field must
  already exist and be reviewed; this slice creates no CRM schema.
- Leased jobs use SKIP LOCKED, fencing tokens, retry backoff and session advisory
  meeting locks surviving step commits. A restarted/expired worker cannot concurrently
  write a meeting while the previous lock survives. Provider I/O has bounded timeouts.
  DB connection loss releases the lock; deterministic provider identities/CAS are
  still required for remote ambiguity. Inventory refresh is one account per cycle.
- Reconciliation is a **managed-link polling baseline**, one due job at a time, with
  independent per-side snapshots/opaque revisions. Notifications cannot supply state;
  authenticated reconcile only schedules a fresh read. No calendar-wide adoption,
  no webhooks/subscription-renewal/incremental cursor implementation is claimed.
  Poll period defaults 60 seconds; throughput/lag requires parent canary monitoring
  before scale. Existing identities keep servicing links after new-send retirement.
- Title/emoji-only edits generate no provider writes. V1 titles, description, location
  and Barbara guest editing stay local; original attendee RSVP/list projects inward.
  Guest-list races during RSVP rebase block explicitly. Recurrence, all-day events,
  unsupported Windows/custom timezone names, unknown import fields and organizer
  identity changes fail closed, never get flattened into a fake supported meeting.
- Simultaneous different time edits, cancellation-vs-time races and actual provider
  412s create conflict state. Resolve-time requires both current exact provider
  revisions, a fresh fetch and a targeted conditional write. No arrival-order LWW.
- Confirmed provider cancellation propagates, decline does not. Unknown 404/410,
  permission errors and timeouts never cancel the partner. Hard deletion lacking a
  retained provider cancellation requires authenticated `deletion-review`, then
  `confirm-deletion` with returned expected_version/confirmation_token, actor and
  audit reason. Both steps fetch fresh state/auth and bind the full immutable link.
  A still-existing event or failed auth rejects confirmation. Cancellation-versus-
  reschedule conflicts remain explicit; do not auto-resolve them by arrival order.
- Every conflict state has an authenticated operator exit; none auto-resolves. For a
  cancellation-versus-reschedule conflict, `resolve-time` with `source` set to the
  cancelled side propagates the cancellation (a cancelled side is never revived). For
  `unsupported_local_guest_edit`, `acknowledge-guests` (actor, reason) accepts Barbara's
  local guest change as the new baseline; the next inward RSVP projection rewrites the
  private copy's guest list from the original and never adds her guests to the original.
  For a reservation whose sender was retired or became unhealthy before any send
  attempt, `void` (actor, reason) releases the slot; nothing exists at a provider, the
  daily cap charge is not refunded, and the Close task stays open. The voided operation
  keeps its task identity, so re-sending that lead needs a new Close task.
- Unchanged polls write nothing (no audit row, no `updated_at`). Cancelled/conflict rows
  and meetings more than a day past their end poll daily; `reconcile` and the operator
  routes still force an immediate pass.
- `/healthz` = process. `/readyz` = DB/schema + fresh worker heartbeat. Authenticated
  `/inventory`, `/meetings`, `/meetings/{operation}` expose eligibility, freshness,
  caps, conflicts and job lag/errors; no credentials returned. Audit records retain
  reservation/saga/operator evidence. Container logs emit reason codes, not payloads.
  Alert on readyz503, overdue jobs, sync_conflict, rsvp_degraded and crm_uncertain.

## Backup, restore and rollback

`deployment/backup.sh` creates a permission-restricted custom-format pg_dump and
checks its archive index before rename. Schedule on wbg-apps after parent approval;
there is no assumed generic host backup/offsite coverage. Retention/offsite target
are operator decisions (script deliberately deletes nothing). Database contains
lead/event PII: encrypt backups, restrict access, never publish them.

Restore drill to an isolated database first, with services stopped and sends frozen:

```sh
# Example only: choose a verified archive; never run against neighbors' databases.
docker compose stop api worker ui
docker compose exec -T postgres createdb -U calendar_invites calendar_restore_check
docker compose exec -T postgres pg_restore -U calendar_invites \
  -d calendar_restore_check --exit-on-error < /secure/path/verified.dump
# Validate meeting/job/audit counts and sampled compound links, then discard drill DB.
```

Application rollback: set BRIDGE_NEW_SENDS=false and leave repair/sync worker running
with the last compatible reviewed image/config. DO NOT disable the UI bridge flag
for a managed task then manually resend it through the legacy route. Do not switch
existing organizers, delete private copies, reset caps/cursors or drop the volume.
If freezing new reservations but keeping repair active, keep BRIDGE_DRY_RUN=false;
new-sends flag blocks unattempted originals but permits ambiguous/partial repair.

Disaster restore loses post-backup operations: keep sends AND worker writes disabled
until reconciling provider markers/Close tasks from that interval. Never treat an
old rotation cursor or missing restored task as permission to send from a new mailbox.
Recover current operation identities first, then enable the worker and new sends
separately. No destructive down migration or automatic historical adoption exists.

## Local tests (no real invites)

```sh
python3.11 -m venv /tmp/calendar-bridge-test
/tmp/calendar-bridge-test/bin/pip install -r requirements-bridge-test.txt
/tmp/calendar-bridge-test/bin/python -m pytest -q
# Point ONLY at a disposable UTF8 Postgres (tests create/drop unique schemas):
TEST_DATABASE_URL=postgresql://... /tmp/calendar-bridge-test/bin/python -m pytest -q
```

Without TEST_DATABASE_URL the row-lock/worker/API integration tests explicitly skip;
SQLite is not used or claimed as row-lock proof. HTTP is blocked by an autouse test
fixture; provider adapters use scripted responses, never credentials/live recipients.
Parent owns image builds on Hetzner, SSO/browser verification and controlled canaries.
