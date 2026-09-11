# Bridge deployment record — wbg-apps, 2026-09-09

Status: **deployed in safe mode.** No outreach sends, no Barbara UI controls, dry run on.

## Review and validation before deploy

- Independent review: OK with notes; three P1s fixed by a follow-up worker, verified
  by a final review. 108 tests pass against a disposable UTF-8 PostgreSQL (rerun by
  parent: `108 passed`). P2 fixes applied by parent: backend mounts only
  `/etc/calendar-invites/backend`; API not published through Caddy; first-send
  eligibility merges current registry fields over the reservation snapshot;
  `/meetings/{op}` comment matches behaviour; worker cycle/discovery failures log a
  safe reason and discovery failures no longer stall durable jobs.
- Disposable smoke test on wbg-apps with throwaway secrets and temp config/state
  (ports 18792/18793, project `calendar-invites-smoke`, removed afterwards):
  migrate exit 0; api/postgres/ui/worker healthy; `/healthz` 200, `/readyz` 200,
  `/inventory` 401 unauthenticated / 200 with bearer; UI health and page 200;
  pg_dump archive listed 8 tables; pg_restore into a scratch DB reported schema
  version 1. Nothing from the smoke run remains on the host.

## Production placement

- Release `/opt/calendar-invites/release-20260909` (symlink `current`), built images
  `calendar-invites-backend:release-20260909`, `calendar-invites-ui:release-20260909`.
  Curated release only: no `.git`, credential JSON, `.streamlit`, venv or tests.
- Config `/etc/calendar-invites` (root:10001 0750): `bridge.env`, `compose.env`,
  `streamlit-secrets.toml`, `postgres_password` (root:root 0444 — gid 999 collides
  with host `systemd-journal`), `backend/` (registry, database_url, operator_token,
  Instantly/Close keys, Google service-account JSON, placeholder outreach credentials).
- State `/var/lib/calendar-invites/postgres`; backups `/var/backups/calendar-invites`
  via `calendar-invites-backup.timer` daily 03:40 local, 14-day local retention,
  first run verified. No offsite copy exists.
- Compose project `calendar-invites`: postgres (no published port, internal
  network), api `127.0.0.1:8792`, worker, ui `127.0.0.1:8793`. All healthy;
  worker heartbeat makes `/readyz` 200.
- Caddy: `/etc/caddy/apps/calendar-invites.caddy` — `/calendar-invites/` behind the
  existing Google SSO `forward_auth` (denied → `/login?rd=`), UI prefix preserved.
  Browser check: SSO → existing app password → consultant/task screen rendered.
  The API has no public route.

## Live inventory in production

Registry has only `barbara-main` (unreviewed, cap 0) plus unapproved examples.
Discovery listed 56 Instantly accounts (13 Google / 45 Microsoft groups incl.
examples), all `unreviewed:` and ineligible. Main sender: calendar auth healthy,
excluded by `unreviewed`, `readiness_unreviewed`, `calendar_grant_unreviewed`,
`daily_cap_exhausted`. Flags: `BRIDGE_NEW_SENDS=false`, `BRIDGE_DRY_RUN=true`,
`CALENDAR_BRIDGE_UI_ENABLED=false`, `require_running_campaign=true`.

## Remaining gates before Barbara uses it

1. ~~Owner decision~~ Decided 2026-09-09: paused-campaign mailboxes are NOT eligible; `require_running_campaign=true` is final. Note: at deploy time only two campaigns were running (both April's) and zero Barbara mailboxes were assigned to them, so outreach groups will show 0 eligible until a Barbara campaign is running.
2. Review/approve senders in `backend/registry.toml`: set `reviewed`, `ready`,
   `calendar_write_reviewed`, `approved_campaigns`, `daily_cap`; provision outreach
   Google (DWD or OAuth) and Graph credentials per mailbox; restart api/worker.
3. Controlled canary with 2035 internal fixtures: `BRIDGE_DRY_RUN=false`,
   `BRIDGE_NEW_SENDS=true`, `CALENDAR_BRIDGE_UI_ENABLED=true` for Barbara only.
4. Commit the working tree (`webapp`); nothing is committed yet.

Rollback: `docker compose --env-file /etc/calendar-invites/compose.env down` for
api/worker/ui, remove the Caddy snippet and reload; database/backups untouched.
