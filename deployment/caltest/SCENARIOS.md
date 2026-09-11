# Calendar invite UI canary scenarios

The app invites **one** address: the Close contact email (mail To and calendar attendee are the same). Fixtures pick that address by what the scenario needs to prove.

| Guest | Address | Use |
|---|---|---|
| Unique plus-address | `lance+<hex>@whiteboardgeeks.com` | S1–S6. Avoids the existing-invite dialog. Mail may arrive; Google Calendar **does not** put the event on `lance@` (attendee ≠ calendar principal). |
| Calendar principal | `lance@whiteboardgeeks.com` | **S7 only.** RSVP Yes on Lance’s copy. |
| Reuse S1 | same plus-address as S1 | **S8.** Existing-invite dialog after S1 is sent. |

Microsoft Zapmail From (`Barbara Pigg` + `whiteboardgeeksmail.com` / `wbginbox.com`) is often Trash/Spam (Workspace employee-spoofing). Do **not** use Microsoft for S7 — Instantly Google instead. S3 still uses Microsoft to prove organizer/copy only.

Search string: the scenario `task_text` below.
The app queries Close with `view=inbox` (the assignee's due/overdue tray) and is
**unchanged from production** — it does no assignee filtering of its own. Fixtures
must therefore be assigned to Barbara and due today or they are invisible to it;
`create_leads.py` sets both and then verifies each tag is actually visible.
Placeholder on Barbara’s calendar: `CALTEST-2035-SLOT` (2035-09-18 09:00–18:00 ET; add `CALTEST-2035-SLOT2` on 2035-09-19 if the first block fills).
Consultant custom field must be `Barbara Pigg`.

Create: `python3 deployment/caltest/create_leads.py`
Cleanup: `python3 deployment/caltest/cleanup.py` (Close leads + 2035 CALTEST events). Cleanup **before** S7 so `lance@` is not already a guest on a leftover 2035 event.

## Eligibility

Outreach: Instantly **account status 1**. A running campaign is not required.
Totals include unreviewed Instantly discoveries. BP WBG Calendar does not use Instantly.

## Scenarios

| id | task_text | Guest | Groups checked | What to verify |
|----|-----------|-------|----------------|----------------|
| S1 | `CALTEST-S1-MAIN` | unique plus | BP WBG Calendar only | Search finds 1. Send. Event on Barbara as organizer, guest = plus-address. |
| S2 | `CALTEST-S2-IGOOGLE` | unique plus | Instantly Google only | Send. Barbara copy is private (`privateCopy`), organizer is Instantly Google. |
| S3 | `CALTEST-S3-IMS` | unique plus | Instantly Microsoft only | Send. Barbara private copy, organizer Instantly Microsoft. Do not expect mail in Lance’s inbox or an event on `lance@`. |
| S4 | `CALTEST-S4-RR` | unique plus (3 leads) | All three groups | Next groups rotates BP WBG Calendar → Instantly Google → Instantly Microsoft. Three sends rotate groups. |
| S5 | `CALTEST-S5-TIME` | unique plus | Instantly Google | After send: Google Calendar Edit/Save **time** on Barbara’s copy. Organizer time unchanged until worker sync (dry-run off). |
| S6 | `CALTEST-S6-TITLE` | unique plus | Instantly Google | Title-only/emoji edit on Barbara copy. Organizer title unchanged. |
| S7 | `CALTEST-S7-RSVP` | `lance@` | Instantly Google only | Event appears on Lance’s calendar. RSVP Yes there. Organizer guest list shows accepted. |
| S8 | `CALTEST-S8-EXISTING` | same plus as S1 | BP WBG Calendar | After S1 is sent, search S8. UI shows existing-invite dialog (Skip). API returns 409 `existing_lead_invite_requires_review`. |

S2/S3/S4 need Instantly-active mailboxes (campaign running is not required).

## Post-send sync scenarios (S9–S11)

These run **after** a send, against a live outreach meeting (state `complete`/`linked`).
They need an Instantly organizer — a `main`-only meeting is one native event with nothing to sync.

Flags: sync needs **`BRIDGE_DRY_RUN=false`**. It does **not** need `BRIDGE_NEW_SENDS`,
which gates first-send only. Conflict *detection* still runs under dry-run because it
stops before any provider write; *resolving* needs writes enabled.

| id | Setup | Expected |
|----|-------|----------|
| S9 | Barbara deletes her private copy | Worker cancels the organizer event and the guest copy. Meeting state `cancelled`, no conflict. |
| S10 | Barbara and the organizer are moved to **different** times in the same poll window, then resolve `source=barbara` | Worker parks it: state `sync_conflict`, kind `time_or_cancellation`, **no writes to either side**. After resolve → state `linked`, organizer takes Barbara's time. |
| S11 | Same conflict, resolve `source=organizer` | State `linked`, Barbara's copy rewritten to the organizer's time. Her local title edit (emoji) survives — only time is rewritten. |

**Creating a real conflict:** stop the worker first
(`docker compose … stop worker`), make both edits, then start it. Otherwise the
worker syncs the first edit and the second is a normal one-sided change, not a conflict.

**Resolve call:** `POST /meetings/{operation}/resolve-time` with
`{"source": "barbara"|"organizer", "organizer_revision": <etag>, "barbara_revision": <etag>}`.
Both etags come from the `conflict` payload on `GET /meetings/{operation}`.

## Known Google behaviours (not bugs)

- **A time change clears RSVPs.** When the organizer's time moves, Google resets
  attendee responses to `needsAction` on all copies. A verified S7 `accepted`
  became `needsAction` after an S5-style reschedule. A reschedule costs the prior Yes.
- **Plus-addressed guests never get a calendar copy.** Mail may arrive at
  `lance+hex@`, but Google only files the event on the calendar whose *primary*
  address is the attendee. There is no `lance+hex@` calendar (404).
- **Microsoft Zapmail invites are filtered.** From `Barbara Pigg` on
  `whiteboardgeeksmail.com` / `wbginbox.com` lands in Trash/Spam as Workspace
  "employee spoofing". The event still exists on the organizer; only delivery is affected.
