# Calendar feasibility spike — observed results, 2026-09-09

**Result:** native per-guest RSVP display and the core Google/Microsoft bridge are
feasible. Full organizer-equivalent UX is NOT yet a passed release gate.
This was a controlled proof of concept, not an installed synchronization service.

**Later UI follow-up:** `calendar-native-save-followup-2026-09-09.md` supersedes the
inconclusive modify-flag probe below. Default private-copy Save persisted; the
modify-enabled fixture failed with a captured Google error. Two additional 2035
fixtures were subsequently cleaned up.

## Authorization and test boundary

Lance authorized internal testing, including Barbara's calendar if far in the future,
with no live customers. All created meetings were explicitly titled
`[INTERNAL TEST — DO NOT ATTEND]`, dated September 9–11, **2035**.

Identities used:
- Barbara's main calendar: `barbara.pigg@whiteboardgeeks.com`.
- Lance's WBG calendar/mailbox: Google sender or controlled recipient.
- Existing Microsoft TEST mailbox `barbara@whiteboardgeekmailerpros.com`:
  Microsoft sender or controlled recipient. Not a production-ready outreach domain.
- Lance's own Gmail: controlled guest-add recipient.
- Four plus-address aliases of Lance's WBG mailbox: synthetic native RSVP display
  fixture only, NOT evidence of four people actually responding.

Calendar UI was inspected through Lance's existing access to Barbara's calendar,
not a browser session signed in as Barbara. No sharing permissions, domains,
production app settings or live customer events were changed.

## 1. The decisive distinction: organizer-owned vs genuinely private

### Rejected: import with Barbara as organizer

Importing onto Barbara's calendar with `organizer.email = Barbara` yielded a normal
organizer event: `privateCopy` absent/default false. Explicitly supplying
`privateCopy: true` at creation did not change that result.

A subsequent `events.patch(..., sendUpdates="all")` propagated an invitation to
Lance's test calendar. Consequently, an organizer-owned import is NOT a safe silent
control copy. Do not rely on import alone or sendUpdates=none to make it safe.

### Viable candidate: preserve the true external organizer

Importing an external-organizer event onto Barbara's calendar yielded
`privateCopy: true`. Google rejected import unless Barbara was either organizer or
an attendee: `participantIsNeitherOrganizerNorAttendee` (HTTP 400).

Therefore the candidate local representation is:
- Real external organizer identity retained (Google or Microsoft sender).
- Actual lead guests retained.
- Barbara included as an **accepted local-only attendee** on the private copy.
- Barbara is NOT added to the real external organizer event, preventing a second
  native attendee invitation/copy on her main calendar.
- Barbara's local-only attendee entry is stripped from outbound guest-list changes.
- Assert the returned `privateCopy` state; never assume the request can force it.

This means she is not literally the organizer of the local copy. Normal editing
controls can exist, but the organizer/RSVP UI still reflects the external organizer.
That distinction must not be hidden in product promises.

## 2. All four RSVP states: verified in native Google Calendar

The actual Calendar event editor displayed:

```
5 guests
2 yes
1 no, 1 maybe, 1 awaiting
```

That includes Barbara's accepted local entry plus four test guest aliases. Native
accessibility labels on the guest rows were:
- `lance+calendar-yes@whiteboardgeeks.com, Attending`
- `lance+calendar-no@whiteboardgeeks.com, Declined`
- `lance+calendar-maybe@whiteboardgeeks.com, Maybe attending`
- `lance+calendar-awaiting@whiteboardgeeks.com` (native awaiting group)

These were normal guest rows/status indicators, not description text or a custom UI.

### Important write-path discovery

Ordinary `events.patch` did NOT update another guest's RSVP on the private copy:
accepted/tentative/declined remained needsAction in read-back. Attempting to change
an organizer's response was also normalized to accepted; do not use organizer rows
as RSVP fixtures.

**Re-importing the same iCalUID updated the existing private copy IN PLACE**, retaining
its event ID and allowing guest RSVP values to be projected. This was verified by
subsequent `events.get`, not just the import response.

This is an upsert/update strategy, not delete-and-recreate on each response.
However, re-import behaves like a full representation write: a probe omitting
location cleared the location. Preserve all supported business/local fields,
reminders, colors, annotations, recurrence/conferencing data as applicable.
Concurrency control for import must be proven before production: worker locks do
not prevent a human or emoji automation from editing between read and re-import.

## 3. Real response roundtrips, separate from the display fixture

### Microsoft organizer → Google recipient → Barbara

A real Microsoft meeting was sent to Lance's WBG address.
- Initially Microsoft reported no response; local copy showed needsAction.
- Lance accepted through Gmail's native invitation control.
- Microsoft Graph reported **accepted**; re-import projected accepted onto Barbara.
- A real recipient-side Calendar API response changed to tentative;
  Graph reported **tentativelyAccepted**; Barbara's copy showed tentative.
- A real recipient-side response changed to declined;
  Graph reported **declined**; Barbara's copy showed declined.
- The same Barbara event ID was retained throughout. Her local time edit survived
  these RSVP projections.

### Google organizer → Microsoft recipient → Barbara

Lance's WBG Google calendar was the stand-in Google sending identity.
The Microsoft test mailbox received that real invitation and accepted via Graph.
The Google organizer event changed from needsAction to accepted; the private copy
on Barbara's calendar was updated to accepted without changing its event ID.

This proves the provider integration pattern, NOT authorization of existing
Instantly Google mailboxes. Those still need inventory and calendar consent checks.

## 4. Native editing and manual bridge checks

On the Microsoft-organized private copy, the normal Calendar editor exposed title,
start/end, description, location and Guests controls. A native edit changed the
meeting from 11:00 to 12:00 Eastern and added Lance's Gmail as a guest.
API read-back confirmed both local changes and `privateCopy: true`; the Microsoft
organizer was unchanged until the test bridge explicitly patched it.

Manual proof-of-concept bridge steps verified:
- Barbara's edited time → same Microsoft organizer event/UID.
- Microsoft software-side reschedule → same Barbara event ID.
- Equivalent time propagation in both directions for the Google source.
- A local emoji title remained on Barbara's event and was not copied to the source.
- Native guest addition did not add the guest to the Microsoft organizer by itself.
  The bridge added that guest to the real organizer. The controlled Gmail inbox
  showed no matching invitation before that bridge step and one invitation from
  the Microsoft test sender afterward (bounded observation, not an absolute
  notification-delivery guarantee).

No production webhooks, queues, reconciliation loop or concurrent-edit resolver
were deployed. These were explicit API operations validating provider mechanics.

## 5. Remaining native-UX limitations / inconclusive probe

With the verified default private-copy settings, Calendar displayed:

> Changes will be reflected only on this calendar: Barbara Pigg.

Saving the time/guest change showed the normal new-guest Send/Don't send prompt,
then an additional confirmation:

> You are about to make changes that will only be reflected on your own calendar.

The bridge can subsequently propagate the edit, but that text is misleading for
the intended workflow and adds friction. This is a real UX gap, not a reason to
claim the experience is already indistinguishable from organizer ownership.

A follow-up local `guestsCanModify=true` import retained privateCopy and showed a
standard update-email prompt without the extra confirmation in that attempt.
However, the requested time change did NOT persist in API read-back. Input-tool
reliability also varied during that attempt. Treat it as **inconclusive/not a fix**;
do not ship this flag as a solution without a clean repeatable native test.

Other unpassed gates:
- Actual Barbara-signed-in desktop and mobile editing/drag/resize behavior.
- Send vs Don't send intent and optional messages: event state alone may not expose
  the user's notification choice to a worker.
- Native removal vs cancellation, undo, moving/duplicating events and recurrence.
- Proposed-time acceptance and email-guests behavior.
- Barbara's real title/RSVP automation compatibility (only a controlled emoji write
  was tested; no automation implementation was inspected or modified).
- Re-import concurrency, notification isolation under every guest-edit path,
  subscription recovery and sustained account-scale operation.

## 6. Delivery caveat confirmed again

The first Microsoft test invitation landed in Lance's **spam** and did not initially
appear on his Google calendar. Only that exact test email was moved to Inbox; the
native Gmail invitation control then allowed acceptance. No global spam rules changed.

API success does not guarantee invite placement or guest calendar appearance.
This old test domain is unsuitable as evidence that warmed production mailboxes
will deliver reliably. Inventory/readiness remains a separate rollout gate.

## 7. Cancellation and cleanup

API-based cancellation paths were exercised during cleanup:
- Delete Barbara's Google-source control copy, then cancel the Google organizer.
  Microsoft receiver reported `isCancelled: true` before its test copy was removed.
- Cancel the Microsoft organizer, verify it absent, then remove Barbara's copy.

These prove the API primitives/manual sequence, not a native-delete webhook worker.

Cleanup completed at **2026-09-09 17:37 UTC**:
- All **11 tracked calendar entries** cancelled or removed, with read-back verification.
- Follow-up queries across Barbara's and Lance's WBG calendars found **zero active
  events for this run's test UIDs**.
- The separate two-hour credential added to the EXISTING Microsoft test app was
  revoked and its local secret file deleted; the original credential was verified
  unchanged. No app permissions or tenant consents were added.
- Only this session's three browser tabs were closed.
- Test invitation/response/cancellation emails remain as an audit trail.

Raw local test artifacts: `/tmp/barbara-calendar-spike.BVOf52/` (temporary storage).
No raw credential or mailbox dump is committed in this repository.

## 8. Updated recommendation

Proceed with the externally organized private-copy candidate, but **do not call the
native UX gate passed yet**. Freeze these proven mechanics into the design:
1. Equal rotation across checked groups, then within each group (Lance confirmed).
2. Main sender stays a single native organizer event.
3. Outreach sender uses external organizer + Barbara's accepted local-only attendee
   on a private copy; confirm returned privateCopy state.
4. RSVP projection uses same-UID in-place re-import, with complete field preservation
   and a proven concurrency strategy.
5. Ordinary time deltas use targeted patches; canonical titles and local emoji
   decoration remain separate.
6. Complete a short actual-Barbara native UX pilot and resolve the confirmation/
   notification-intent behavior before building out all sender pools and the worker.
