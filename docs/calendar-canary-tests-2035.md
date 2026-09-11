# Canary tests — 2035 internal only

Guest is always `lance@whiteboardgeeks.com`. No live customers.
Search string in the invite app: `CALTEST-2035`.

## Fixtures
1. Three Close leads + incomplete tasks, unique task text, TX address (timezone).
2. One Barbara-calendar placeholder `CALTEST-2035-SLOT` in 2035 with capacity for three 30-min sends.

## Sends (all three account types)
3. **Google Workspace (main)** — Barbara’s `barbara.pigg@whiteboardgeeks.com` as organizer.
4. **Instantly Google** — outreach mailbox organizer + Barbara private copy.
5. **Instantly Microsoft** — Graph organizer + Barbara private copy.

## After send
6. Streamlit search finds only the CALTEST-2035 tasks.
7. Bridge inventory/meetings show linked (or complete) operations.
8. Google Calendar 2035: main event on Barbara; Instantly events as private copies with external organizer.
9. Edit/Save time on a private copy (extra “this calendar only” confirm).
10. Title-only edit does not change the organizer event.
11. RSVP Yes on Lance’s copy of the Microsoft invite.

## Cleanup
12. Cancel/delete 2035 events, complete or delete Close tasks, restore `BRIDGE_NEW_SENDS=false` / dry-run.
