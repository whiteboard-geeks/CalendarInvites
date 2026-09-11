# Native Save follow-up — 2026-09-09

Result: the default private-copy flow saves successfully with Google's extra
confirmation. Setting `guestsCanModify=true` is NOT a validated way to remove that
friction: the controlled repeat failed to save and surfaced a Google error.

This supersedes the inconclusive modify-flag probe in
`calendar-spike-results-2026-09-09.md`, not the successful native RSVP/bridge tests.

## Controlled comparison

Two fresh, local-only fixtures on Barbara's calendar, September 16, 2035:
- Same external Microsoft organizer identity and accepted Barbara attendee.
- No customers or lead guests; no real Microsoft source event created for these
  local persistence fixtures. The earlier real-source experiment had likewise
  failed to persist the requested change with the flag enabled.
- A: default `guestsCanModify` false/absent; B: true.
- Both returned `privateCopy=true` from the API.
- Both tested using native Calendar title-field filling and Save, avoiding the
  earlier time-widget/DOM-value uncertainty. No production UI code was changed.

A / default:
- Google showed its 'changes only ... own calendar' confirmation.
- Confirmed OK; API read-back showed the new title and updated timestamp.

B / modify enabled:
- Google showed the standard update-email prompt instead.
- Save + Send did not persist the new title or change the updated timestamp.
- Repeated with a different title and Don't send: also did not persist.
- A page notice observer captured the transient error:

> Oops, we couldn't update this event, please try again in a few minutes

This establishes a failed native save, not merely a stale snapshot or a missing
sign-in. It does not establish Google's internal implementation or prove that no
other supported design can satisfy organizer-equivalent editing. Do not treat
locally setting a guest permission flag as actual authority over the remote event.

## Identity and scope

Chrome was signed in as `lance@whiteboardgeeks.com`, operating Barbara's calendar
through existing access. This is not a Barbara-signed-in desktop/mobile pilot.
No new permissions, credentials or sharing settings were required for this follow-up.

## Cleanup

Both new fixtures were cancelled and verified by API read-back. Follow-up UID
queries on Barbara's and Lance's WBG calendars found zero active matching events.
Cleanup finished 2026-09-09 17:50 UTC. The session's test tab was closed.
Raw temporary evidence: `/tmp/barbara-native-save.3QreYA/`.

## Design consequence

Keep the working default private-copy flow as a candidate with an explicit UX
limitation, not a claimed seamless implementation. Do not ship the modify-flag
workaround. Any alternative keeping Barbara as the real organizer and rotating
invitation transport would change the sending/reputation model and needs separate
validation and Lance's approval; it must not silently replace the requested model.
