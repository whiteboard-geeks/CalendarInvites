# Calendar feature — confirmed original-event bridge

Updated: 2026-09-09.

## Confirmed by Lance

- Round robin equally across the checked groups, then across eligible mailboxes within each group.
- Barbara uses Google Calendar in Chrome.
- A required Chrome extension is **not acceptable**. Do not build or propose that as the deployment plan.
- Both Barbara and recipients should experience one continuous meeting, without a replacement event or duplicate invitation caused by synchronization.
- Update the existing organizer event through its provider API; keep its identity/UID stable.
- All four per-guest RSVP states must appear in the native Google Calendar guest list.
- Preserve Barbara's existing title/emoji automations.
- Testing may use Barbara's calendar only far in the future, with controlled internal accounts and no live customers.
- Outreach mailboxes must be **active in Instantly** (status 1). A running campaign is not required (Lance, 2026-09-10). Instantly account pause still excludes.
- If Close shows an outgoing email to the lead from one of our sending addresses in the last 30 days, send the invite from that same address (eligible mailbox). Otherwise round-robin the checked groups.

## What remains unresolved

The original-event API bridge passed provider-level time/RSVP tests, but the tested
private Google copy did not preserve native drag behavior. Organizer-owned controls
worked; changing the private copy to organizer-owned removed notification isolation.
The local guestsCanModify workaround failed Save. These are observed constraints,
not proof that every possible supported architecture has been exhausted.

The alternative with Barbara as true organizer passed initial Microsoft-mail delivery
to Google, native acceptance and rescheduling on the same recipient event. Follow-up
updates came from Barbara's primary account. Google-mail delivery variants remain
unvalidated. This alternative changes the organizer/sending model and has NOT been
approved as a substitute.

## Architecture direction reaffirmed by Lance

Lance rejected the alternate sender model and reiterated:

> Why can't we just have barbara update the calendar invite and then it updates via API to the original invite account?

Use that original-event bridge:
1. Barbara edits her calendar copy.
2. The worker patches the existing event on the original sending account, retaining
   its organizer, event identity and UID. Do not delete/recreate the meeting.
3. Original-event changes and actual guest responses flow back to Barbara's copy.
4. Her copy must not independently invite the customer.

The provider API steps already passed controlled tests; the automatic production
worker has not been built. Full Edit/Save on the private copy worked with Google's
local-copy confirmation; native dragging did not pass. Keep those UX findings
separate from backend sync capability. Do not use the drag limitation to silently
switch organizers, add an extension, or keep reopening the rejected transport model.

No browser extension, native-client switch, production rollout or organizer-model
change is authorized by this requirements record.
