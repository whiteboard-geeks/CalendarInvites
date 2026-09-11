# Alternative tested: Barbara owns the event; initial mail transport rotates

Status: **partially validated alternative; requires Lance's approval of the changed
sending model and additional interoperability tests. Not an implementation approval.**
Date: 2026-09-09.

## Finding

A Microsoft outreach mailbox successfully delivered an invitation whose actual
organizer remained Barbara. Gmail recognized it as a meeting, the recipient's
acceptance updated Barbara's native event automatically, and a normal Calendar UI
reschedule updated the SAME recipient meeting without the private-copy warning.

A later explicit Google Calendar update email was received from
`Barbara Pigg <barbara.pigg@whiteboardgeeks.com>`, not the outreach mailbox.

**This is rotation of initial invitation delivery, NOT rotation of organizer calendars.**
It meets the native-ownership objective in the tested Microsoft→Google path, but
changes the reputation/sender behavior and does not by itself create editable
outreach-calendar events for other software.

## 1. Model and standards basis

Create one true organizer event on Barbara's main calendar. For an outreach send,
deliver its initial iCalendar REQUEST using the selected mailbox's mail API:

```text
Email From: selected outreach mailbox
Reply-To: Barbara's main address
METHOD:REQUEST
UID: the canonical Barbara event's iCalUID
ORGANIZER;SENT-BY="mailto:outreach@example.com":mailto:barbara.pigg@whiteboardgeeks.com
ATTENDEE;RSVP=TRUE:mailto:the-recipient@example.com
```

`SENT-BY` represents an authorized scheduling agent; it does not make that agent
the organizer. RFC 5546 §3.2.2.5 explicitly describes one calendar user acting on
behalf of an organizer and says attendee responses remain directed to the organizer.
Do not falsify the actual email sender or reuse another account's authorization.

For main-calendar sends, use the normal Google Calendar invitation path. The
confirmed group rotation remains unchanged: equal rotation among checked groups,
then round robin within the chosen group.

## 2. What actually passed

Test meeting: September 23, 2035, clearly marked INTERNAL TEST / DO NOT ATTEND.
No customers or current appointments were used.

1. Imported a normal event onto Barbara's calendar, with Barbara as organizer and
   Lance's WBG address as guest. The response had organizer.self=true and no
   privateCopy flag. Import itself created zero guest copies before the email.
2. Sent a real MIME invitation via the existing Microsoft test mailbox
   `barbara@whiteboardgeekmailerpros.com` using Graph sendMail.
3. Read the received Gmail message and decoded its calendar attachment. Exchange
   preserved Barbara as ORGANIZER, the Microsoft mailbox as SENT-BY, and the
   canonical event UID. Email From was the actual Microsoft mailbox.
4. Gmail rendered normal invitation controls and identified Barbara as organizer.
5. Clicked Yes in Gmail. Barbara's canonical event immediately showed accepted.
   **No mirror, RSVP projection, re-import update, or worker was involved.**
6. Opened Barbara's real event in the native Calendar editor through Lance's
   existing delegated access. Normal organizer guest-permission controls appeared.
7. Changed 1:00–1:30pm Eastern to 2:00–2:30pm and saved. No private-copy confirmation
   appeared. API read-back verified the canonical time and the recipient's matching
   time, with exactly ONE recipient event for that UID.
8. The reschedule reset the guest response to needsAction, as normal Google
   scheduling semantics do; this was not a lost custom status or sync bug.
9. Made a second organizer API update with sendUpdates=all. The received update
   email was FROM Barbara's primary address. The recipient still had one event.

The update email's subject truncated the long event title (`...organizer microso...`).
An exact full-title Gmail query initially missed it. A broader scoped notification
query found it. Production correlation should use event/message identifiers and
calendar attachment UID, not exact notification subjects.

## 3. What did NOT pass / remains unknown

### Google mail transport

Google sending used Lance's WBG mailbox as a stand-in, NOT an Instantly Google
mailbox. Gmail API accepted the messages. Test cases included:
- Google→Microsoft using the initial calendar MIME and a corrected Content-Class.
- Google→personal Gmail using 7-bit and base64 calendar parts.
- A fresh UID using Exchange-normalized calendar content, sent through Gmail to
  both controlled Microsoft and personal Gmail recipients.

The Google-sent mail reached the personal Gmail inbox as ordinary mail, but no
native invitation/RSVP controls were observed. The Microsoft calendar never
materialized a matching event during the test windows (including a later broader
calendarView check). These paths are **not validated**.

The existing Microsoft test app grants Calendars.ReadWrite and Mail.Send, not
Mail.Read. A mailbox-message read returned 403, so we did not establish whether the
Google→Microsoft problem was delivery, filtering, MIME handling, or required manual
inbox action. No extra permissions were granted to work around that limitation.

Do not infer that Gmail API cannot send calendar invitations in general. This
specific implementation did not achieve the required cross-client behavior. Further
MIME/client investigation needs a clean fixture and a receiver whose message contents
and calendar processing can both be inspected. No more speculative format changes
were made after the bounded variants failed.

### Other unpassed requirements

- Native Microsoft/Outlook recipient lifecycle under the new transport model.
- Actual Barbara-signed-in desktop/mobile testing; this used Lance's existing access.
- Every RSVP state under this alternative (accepted was tested; all four native
  display states were proven in the earlier private-copy experiment).
- Native cancellation delivery and recipient cleanup across all clients.
- Compatibility with Barbara's actual emoji automations; none were inspected/changed.
- Existing Instantly Google/Microsoft mailbox inventory and mail authorization.
- Events edited by software on outreach calendars: there is no organizer event there
  in this model unless an explicit non-inviting mirror/bridge is separately built.

## 4. Engineering implications IF this model is approved

- Keep one canonical, Barbara-owned Google event and its normal native guests/RSVP.
- Persist selected initial sender, immutable meeting UID, provider email identifiers,
  send-operation key and delivery state. Do not change sender after an ambiguous send.
- Main sends use ordinary Calendar invitation creation. Outreach sends create the
  canonical event without initial Calendar mail, then deliver its REQUEST through
  the selected authorized transport once that transport's client matrix passes.
- Creation and sending remain a durable multi-step operation: an unsent canonical
  event must not be treated as a completed invite or completed Close task.
- No RSVP mirror worker is needed for supported native response paths.
- If external software must edit outreach calendars, either integrate it with the
  canonical event API, or create explicitly linked **non-inviting appointments**
  there and bridge their time/cancellation changes. Those are not lead-facing
  organizers, and require their own concurrency/loop/notification tests.
- Ordinary native follow-up updates and cancellations use Barbara/Google's normal
  organizer identity. An API bridge cannot silently intercept Calendar's native
  outbound mail and re-route it through rotating accounts.
- Barbara's primary calendar identity remains visible in the first invitation.
  This is NOT full primary-domain reputation isolation, even with an authenticated
  outreach From address. Warmup is not a guarantee of calendar invite placement.
- Native updates may include the canonical event's decorated title. If keeping
  emojis off every guest copy is a strict requirement, that is another unresolved
  constraint; do not promise a title filter over Google's own native notifications.

## 5. Test hygiene / implementation notes

- The EmailMessage MIME builder cleared Content-* headers when set_content ran;
  Content-Class must be applied AFTER content construction. This was corrected in
  the isolated test generator, not the production application.
- The service account was not delegated the standalone gmail.send scope. Its
  pre-existing gmail.modify grant allowed the send endpoint. No Google scope grants
  were changed. The failed first attempt stopped at token refresh; absence from Sent
  was verified before the correctly authorized attempt.
- Graph MIME sendMail returning 202 is acceptance for processing, not delivery proof.
- Corrected test MIME variants were deliberately recorded as new test messages,
  not silent retries of an ambiguous delivery.

## 6. Cleanup

At 2026-09-09 **18:24 UTC**:
- All five tracked calendar entries (four canonical fixtures and one confirmed
  recipient copy) were cancelled/removed and verified.
- UID queries on Barbara's and Lance's WBG calendars found zero active test events.
- Microsoft calendarView showed zero events in the test window before cleanup.
- The separate temporary credential on the existing Microsoft test app was revoked,
  its secret file removed, and the original credential verified unchanged.
- Both session-created browser tabs were closed. Test emails remain as an audit trail.
- No production application code, sender settings, domain configuration, permissions,
  or tenant consent were changed.

Temporary raw evidence: `/tmp/barbara-organizer-transport.eOt71M/`.

## Decision required

Is it acceptable for **initial invitations to rotate among selected sending accounts,
while Barbara remains organizer and subsequent native updates/cancellations come from
her primary account**? If yes, refine this alternative and finish the failed Google/
Outlook interoperability tests before implementation. If no, retain the external-
organizer requirement and do not present this transport model as equivalent.

## References

- RFC 5545 §3.2.18, SENT-BY: https://www.rfc-editor.org/rfc/rfc5545.html#section-3.2.18
- RFC 5546 §3.2.2.5: https://www.rfc-editor.org/rfc/rfc5546.html#section-3.2.2.5
- Graph MIME mail: https://learn.microsoft.com/en-us/graph/outlook-send-mime-message
- Graph sendMail: https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0
- Earlier results: `calendar-spike-results-2026-09-09.md`, `calendar-native-save-followup-2026-09-09.md`.
