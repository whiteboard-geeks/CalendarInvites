function markAcceptedMeetingsAcrossCalendarsWithPagination() {
  const now = new Date();
  const future = new Date();
  future.setDate(now.getDate() + 21);
  const yourEmail = Session.getEffectiveUser().getEmail().toLowerCase();

  Logger.log(`Running as: ${yourEmail}`);
  Logger.log(`Checking events from ${now.toISOString()} to ${future.toISOString()}`);

  // Any run of our own markers at the front of a title. Must list EVERY emoji we
  // have ever written, or a title carrying one we don't know about survives the
  // clean step and the new emoji gets stacked on front of it.
  const emojiAtStart = /^(?:(?:📬|📦|✅)\s*)+/u;

  const calendars = Calendar.CalendarList.list().items;

  calendars.forEach(cal => {
    Logger.log(`\n🔍 Checking calendar: "${cal.summary}" (${cal.id})`);

    let pageToken;
    let totalEvents = 0;

    do {
      const response = Calendar.Events.list(cal.id, {
        timeMin: now.toISOString(),
        timeMax: future.toISOString(),
        singleEvents: true,
        orderBy: 'startTime',
        maxResults: 250,
        pageToken: pageToken
      });

      const events = response.items;
      if (!events || events.length === 0) {
        Logger.log('No events found on this page.');
        break;
      }

      events.forEach(event => {
        const originalTitle = event.summary || '';
        Logger.log(`\n📅 Event: "${originalTitle || '[No Title]'}"`);

        if (!originalTitle) {
          Logger.log('⚠️ Skipping: No summary.');
          return;
        }
        if (!event.attendees || event.attendees.length === 0) {
          Logger.log('⚠️ Skipping: No attendees.');
          return;
        }
        const organizerEmail = (event.organizer?.email || '').toLowerCase();
        // Imported private copies keep the outreach organizer. Only edit our primary copy.
        const isOwnPrivateCopy = event.privateCopy === true && cal.primary === true &&
                                 cal.accessRole === 'owner';
        if (organizerEmail !== yourEmail && !isOwnPrivateCopy) {
          Logger.log(`⚠️ Skipping: Not our organizer event or primary private copy.`);
          return;
        }

        // Log attendee statuses
        event.attendees.forEach(a => {
          Logger.log(`   - Attendee: ${a.email} | Status: ${a.responseStatus}`);
        });

        const someoneElseAccepted = event.attendees.some(a =>
          !a.self && (a.email || '').toLowerCase() !== yourEmail &&
          (a.email || '').toLowerCase() !== organizerEmail && a.responseStatus === 'accepted'
        );

        const hasIntro = originalTitle.includes('Intro');

        // Two mailer campaigns send blind invites with IDENTICAL titles. Only the
        // body says which: MTP (comic boards, letters) mentions the spam/quarantine
        // folder; Video Card mentions a 'Video Card' or 'Video Brochure'. Key on the
        // quarantine line -- the mailed item changes wave to wave, that line doesn't.
        const body = (event.description || '').replace(/<[^>]+>/g, ' ').toLowerCase();
        const isMTP = body.indexOf('quarantine folder') !== -1 ||
                      body.indexOf('comic board') !== -1;

        const correctEmoji = hasIntro ? (isMTP ? '📦' : '📬') : '✅';
        const hasLeadingEmoji = emojiAtStart.test(originalTitle);

        if (!someoneElseAccepted) {
          // ❌ No accepts right now (e.g., meeting moved → responses reset).
          // If we previously marked it, strip the emoji.
          if (hasLeadingEmoji) {
            const cleanedTitle = originalTitle.replace(emojiAtStart, '');
            Logger.log(`🧹 Removing emoji; updating title to: "${cleanedTitle}"`);
            try {
              Calendar.Events.patch(
                { summary: cleanedTitle },
                cal.id,
                event.id,
                { sendUpdates: 'none' }
              );
            } catch (e) {
              Logger.log(`❌ Failed to remove emoji: ${e.message}`);
            }
          } else {
            Logger.log('⏭️ No accepts and no leading emoji; leaving as-is.');
          }
          return; // Done with this event
        }

        // ✅ At least one non-organizer has accepted.
        // Ensure the *correct* emoji is present (MTP intro → 📦, other intro → 📬,
        // everything else → ✅).
        if (originalTitle.startsWith(`${correctEmoji} `) &&
            !emojiAtStart.test(originalTitle.slice(correctEmoji.length + 1))) {
          Logger.log(`✅ Skipping: Already has correct emoji (${correctEmoji}).`);
          return;
        }

        const cleanedTitle = originalTitle.replace(emojiAtStart, '');
        const updatedTitle = `${correctEmoji} ${cleanedTitle}`;

        Logger.log(`🔄 Adding/setting emoji (${isMTP ? 'MTP' : hasIntro ? 'video card' : 'non-intro'}); updating title to: "${updatedTitle}"`);
        try {
          Calendar.Events.patch(
            { summary: updatedTitle },
            cal.id,
            event.id,
            { sendUpdates: 'none' }
          );
        } catch (e) {
          Logger.log(`❌ Failed to update event: ${e.message}`);
        }
      });

      totalEvents += events.length;
      pageToken = response.nextPageToken;
    } while (pageToken);

    Logger.log(`✅ Finished calendar "${cal.summary}". Events processed: ${totalEvents}`);
  });

  Logger.log('🎉 All calendars checked and updates completed.');
}