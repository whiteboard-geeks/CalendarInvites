# Barbara's native calendar experience: feasibility gate

Status: pre-test proposal retained for context; core mechanics now tested, native UX gate still open.
Date: 2026-09-09. Companion to `barbara-calendar-pools-plan.md`.

**Read the observed results first:** `calendar-spike-results-2026-09-09.md`.
They supersede assumptions below: Barbara-organized imports are not isolated;
external-organizer private copies require Barbara as a local attendee; same-UID
re-import can project native RSVP in place. Native confirmation behavior remains
unresolved. Tests were authorized by Lance and all tracked test events were cleaned up.

Lance confirmed group-level round robin and clarified that Barbara must interact
with events normally, as if she were the organizer. A title/time-only placeholder
on her calendar does not meet that requirement.

## 1. Product contract

Barbara stays in her ordinary Google Calendar, on desktop and mobile:
- One visible event on her main calendar, regardless of the sending provider.
- Open it and see real guests and their latest responses in the normal guest list.
- Drag to move, resize duration, edit meeting details, add/remove guests and cancel.
- See accepted organizer-side changes without copying/recreating events.
- Keep existing emoji/title automations, local colors and personal reminders.
- No mailbox switching, external-calendar overlay forest, special reschedule button,
  manual copying, or routine visits to an admin dashboard.

Operator tooling handles exceptional outages/conflicts; Barbara should not be
expected to monitor a synchronization console. Define an alert owner and recovery
latency before deployment. A background bridge cannot be literally instantaneous;
measure normal latency and set an explicit service objective rather than implying
an atomic transaction across Google and Microsoft.

## 2. What Google documents, and what it does not prove

Confirmed from current Calendar API documentation:
- `events.import` adds a private copy of an existing event.
- The event resource's immutable `privateCopy` field says propagation is disabled
  when true; this is unrelated to event visibility or private extended properties.
- Organizer is read-only except during import; `events.move` changes the organizer.
- Import accepts an attendee list. The resource supports attendee response status.
- `sendUpdates=none` on a normal insert is NOT a reliable isolation strategy:
  Google's documentation warns about adverse synchronization effects, and notification
  flags alone are not proof that later edits in Google's UI cannot send messages.

Not proven by those docs:
- Whether the exact imported organizer/attendee arrangement needed here is accepted.
- Whether Barbara gets all necessary organizer controls on that private copy.
- Whether guest add/remove, Save/Send prompts, deletion, and mobile edits preserve
  isolation and privateCopy semantics indefinitely.
- Whether imported/projected RSVP values remain visible as expected, and whether
  Calendar UI actions trigger any extra invitation emails despite disabled propagation.

Therefore private import is a candidate to TEST, not a promised solution.

## 3. Candidate architecture to test first

External event: true organizer is the selected outreach mailbox; actual invitations,
updates, cancellations and recipient responses belong to this event.

Barbara event: a private imported control copy, with native guest data and observed
RSVP states, on her real calendar. Test whether import permits Barbara to own/control
that local copy without changing the external organizer or propagating invitations.
Retain the true external organizer identity in the durable mapping; never manufacture
an RSVP or represent the local organizer metadata as the sender of the real invitation.

Test UID strategy in isolation as well: same external iCalUID vs a separate local
control UID, including duplicate suppression, auto-linking, and subsequent incoming
updates. Do not decide by assumption or reuse identifiers in production until that
behavior is established. No additional attendee invitation to Barbara.

The bridge observes her real edits and applies the meaningful changes to the
external organizer event. Responses and external organizer edits are projected back
into the local event. Existing durable retry/conflict requirements still apply.

If this supports guest display but not organizer editing, or emits duplicate updates,
it FAILS. Do not quietly downgrade to a description-based guest list or blank mirror.

## 4. Native behavior proof matrix (release-blocking)

Use disposable internal test identities/calendars plus controlled Gmail and Microsoft
recipients; get approval for exact accounts before sending any tests. Do not use
Barbara's live calendar or cold leads as experiments.

Test each action for BOTH Google and Microsoft external organizers:

1. Create: Barbara sees one event, organizer-style controls and native guests;
   recipient sees one real invite from the selected outreach identity.
2. Drag and resize in desktop Google Calendar: same external event changes, lead
   gets the correct update, and there is no second organizer email from Barbara.
3. Repeat time/details edits on mobile; confirm behavior rather than infer from desktop.
4. Native guest add: exactly one new attendee invitation from the external organizer;
   native guest remove: expected cancellation/removal behavior, no second event.
5. Lead accepts, tentatively accepts, declines, comments or proposes a time:
   verify what each provider actually exposes and what appears in Barbara's native UI.
   Response projection must never send an RSVP on the recipient's behalf.
6. Edit description/location/title; preserve Zoom link integrity and local annotations.
7. Apply existing emoji automation alone: zero outbound meeting-update notifications.
   Combine a drag with an emoji write: one effective time change, no title leakage.
8. Delete/cancel in Calendar, including choosing Send or Don't send when offered:
   establish whether user intent is observable. A deleted event alone may not encode
   a notification choice. If not, document the limitation before claiming equivalence.
9. Undo deletion/restore, duplicate event and move to another calendar: ensure copies
   cannot inherit a link and control the original meeting accidentally. Unmanaged
   copies must not be auto-linked by title or copied private metadata alone.
10. Email guests, proposed-time acceptance, recurring edits and conferencing controls:
    distinguish controls that work normally from those the bridge cannot emulate.
    A user-initiated ordinary email from Barbara is not the same as an unintended
    second meeting invitation; inspect both and disclose sender behavior.
11. Outage and simultaneous edits: no stale rollback, RSVP reset, duplicate invite,
    or silent success; alert the operator while preserving Barbara's event.
12. Repeat writes/reloads and inspect privateCopy, event IDs, UID, organizer,
    attendees and revisions. Inspect controlled recipient calendar AND inbox after
    UI actions; a successful API response is not sufficient evidence.

Record pass/fail and screenshots of actual native controls during the approved spike.
No GUI source changes are needed to explore native Calendar behavior.

## 5. Field-level behavior proposal

Treat each event as shared business data plus local presentation:
- Shared: start/end/timezone, canonical title, business description/location,
  attendee membership, cancellation state, and supported meeting-link changes.
- External-observed: RSVP, response comments and proposed-time data where available.
- Local only: Barbara's known emoji decorations, color, personal reminders, personal
  notes outside shared fields. Preserve these during every remote update.

Audit the actual automations before coding title normalization. Store last canonical
and local titles separately. Recognize only verified decoration rules; do not remove
all emoji or try to infer human intent from arbitrary text. Ordinary rename should
not be silently ignored. If a rename plus decoration is ambiguous, preserve both
raw values and surface it to the operator rather than overwrite either.

Concrete trace for guest/RSVP handling (conditional on private-copy tests passing):
- t0 B={guests:[A],RSVP:A?}, O={guests:[A],RSVP:A?}, S={guests:[A]}.
- t1 Barbara adds C locally: B={guests:[A,C]}, O={guests:[A]}; local propagation OFF.
- t2 worker sees membership-only edit, patches O to [A,C] without resetting A's RSVP;
  provider invites C. Confirm exact notification behavior in the provider spike.
- t3 C accepts on O: O={A?,C:accepted}; worker projects C's response into B only.
- t4 B notification is a matching projection echo: no write back to O, no RSVP sent.

A concurrent removal and RSVP must not re-add a deleted guest: membership and
response snapshots are distinct, pending writes re-read the current recipient set.

## 6. Alternatives and honest boundary

- Google delegated/shared calendar access gives native organizer controls, but events
  live on the sender calendars, not Barbara's main calendar. It also does not provide
  a uniform native Google editing surface for many Microsoft calendars. Not a silent
  substitute for the stated requirement.
- Making Barbara the real organizer is the most native solution, but changes the
  organizer/sending-domain model; a sender alias or a second email does not magically
  preserve independent organizer identity across vendors. Do not call this equivalent.
- An ordinary attendee-free mirror is easier, but misses native guests/RSVP and is
  explicitly rejected as the seamless-experience solution.
- A Google guest copy with guestsCanModify is not blanket organizer authority, may
  grant unwanted editing rights to recipients, and does not solve Microsoft parity.

If the private-copy route fails, bring back the demonstrated gap and the necessary
tradeoff before implementation. In particular, native 'Send/Don't send', email-guest,
proposal handling, organizer transfer, and recurring-series behavior may not be
fully observable/emulatable by an API bridge. Do not promise complete organizer
parity merely because the core drag/edit/RSVP tests pass.

## References

- https://developers.google.com/workspace/calendar/api/v3/reference/events?hl=en
- https://developers.google.com/workspace/calendar/api/v3/reference/events/import?hl=en
- https://developers.google.com/workspace/calendar/api/v3/reference/events/insert?hl=en
- https://developers.google.com/workspace/calendar/api/v3/reference/events/move?hl=en
