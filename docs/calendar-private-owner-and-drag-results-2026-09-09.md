# Private ownership and native drag checks — 2026-09-09

**Correction to the earlier scope:** the original-event API bridge is viable, but
native Google Calendar drag behavior is not solved. This is more than the wording
of an extra Save confirmation. Do not mark Barbara's native-UX gate passed.

## 1. Can a copy be organizer-owned AND propagation-disabled?

Tested on Barbara's primary calendar, with an explicitly labeled October 7, 2035
fixture and only controlled internal attendees:

1. Import external organizer + Barbara attendee → `privateCopy=true`.
2. Re-import SAME UID, changing organizer to Barbara → same event ID, organizer.self
   true, but `privateCopy` disappears/defaults false.
3. Re-import external organizer again → `privateCopy=true` returns.

Thus the immutable-field wording does not provide a way to preserve isolation while
changing the organizer through import. Google recomputes the representation. This
is consistent with the earlier creation test: supplying privateCopy=true alongside
Barbara-as-organizer did not force an isolated copy.

Do not use organizer reassignment as a silent-copy workaround. Earlier testing
already showed that an organizer-owned import can propagate a customer invitation
when updated. Nothing here transferred or changed a real outreach meeting.

## 2. Native drag comparison

Used the actual Google Calendar day grid and real pointer input, not API time writes.
All dates were October 7, 2035. Test-only DOM anchors helped target an empty time-grid
position; they did not change Calendar permissions, handlers or event data. The
pointer traces recorded trusted down/up events spanning the intended drag.

### A. External-organizer private copy on Barbara's calendar

Signed-in browser user: Lance, using existing delegated access to Barbara.
- Private copy, default guest modification permission.
- Drag left the event at 11:00–11:30 Eastern, with no saved time change.
- Subsequent Calendar API read-back confirmed unchanged time.

### B. Organizer-owned control on Barbara's calendar

Same browser/user/calendar and same fixture UID, re-imported as Barbara-organized:
- The same drag tooling produced Google's normal update-email confirmation.
- Chose Don't send for this internal control.
- API read-back confirmed the event moved from 11:00 to 09:15 Eastern.
- The exact drop time differed from the intended offset because the automation
  scrolls the source into view. The relevant positive control is that a native drag
  was recognized and its changed time persisted.

### C. Private copy on the signed-in user's OWN primary calendar

To rule out delegated-calendar access as the sole cause, created a separate external-
organizer private copy on Lance's own WBG calendar and operated it while signed in
as Lance:
- Default guest modification permission; Lance accepted as attendee.
- A complete pointer down/up drag did not move it.
- API read-back remained 11:00–11:30 Eastern with `privateCopy=true`.

This is a controlled failure on the current Google web client, not a claim about
all calendar clients or every possible representation. Actual Barbara desktop/mobile
validation remains distinct. The earlier REST time-patching and full Edit/Save
successes do NOT establish native drag-to-reschedule support.

## 3. Consequence for the design

Keep these facts separate:
- The backend can patch the ORIGINAL Google/Microsoft organizer event in place,
  retaining IDs/UID and avoiding a replacement customer meeting. Previously tested.
- The private copy can display native guest RSVP states and can be updated by API.
- Google Calendar's frontend does not necessarily expose the same interactions as
  an organizer event. The tested private-copy drag path failed, and the previously
  tested guestsCanModify=true workaround failed Save.
- A backend API service cannot, by itself, rewrite Google's frontend controls or
  confirmation dialogs. Do not keep forcing permission/ownership flags to imply
  authority the remote organizer has not granted.

Before building a client-side workaround, establish Barbara's actual day-to-day
calendar client and whether any desktop companion would be acceptable. A browser
companion would introduce installation, privacy permissions, DOM/version maintenance
and mobile-coverage concerns; it is not an approved or proven solution.

The Barbara-as-true-organizer/rotating-initial-mail alternative remains a different
model requiring approval; it must not silently replace the original-event bridge.

## 4. Cleanup

Both tracked fixtures were cancelled/removed and verified by API. UID queries on
Barbara's and Lance's WBG calendars found zero active matching events. Cleanup
finished **2026-09-09 19:08 UTC**; the session-created browser tab was closed.
No live customer events, new tenant permissions, credentials, production sender
settings or application source were changed.

Temporary evidence: `/tmp/barbara-private-owner.LmVElY/`.
Includes initial/re-import API results, private/owned/own-account drag read-backs,
a screenshot of the test day grid and cleanup verification.
