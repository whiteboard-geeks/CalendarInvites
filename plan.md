# Implementation Plan: Multi-Consultant Support

## Variables Needed Per Consultant

1. **Basic Information**
   - Full name (for filtering and display)
   - Job title (for templates)
   - Email address (for calendar invites)
   - Close CRM consultant ID/field value

2. **Calendar Integration**
   - Calendar ID
   - Service account access (ensure service account has access to each consultant's calendar)

3. **Meeting Information**
   - Zoom meeting URL
   - Zoom meeting ID
   - One-tap mobile links
   - Dial-in numbers

4. **Templates**
   - Default event title template
   - Default event description template with consultant-specific wording

5. **Close CRM Integration**
   - Custom activity type ID for blind invites
   - Any consultant-specific custom fields

## Implementation Steps

- [x] **Create Consultant Configuration Structure**
  - [x] Define a dictionary/object structure to store all consultant-specific variables
  - [x] Initially populate with Barbara Pigg and April Lowrie data
  - [x] Add placeholder for April's Zoom URL and meeting ID (to be determined)
  - [x] Add functionality to access consultant's first name and last initial for templates

- [x] **Add Consultant Selection UI**
  - [x] Add dropdown at top of app to select consultant
  - [x] Store selection in session state
  - [x] Apply selection when searching tasks and creating invites
  - [x] Added validation to prevent defaulting to any consultant

- [x] **Modify Filtering Logic**
  - [x] Replace hardcoded `if consultant != "Barbara Pigg"` check with dynamic lookup
  - [x] Update task filtering to use selected consultant

- [x] **Update Calendar Integration**
  - [x] Make calendar ID dynamic based on selected consultant
  - [x] Update attendee information in calendar invites

- [x] **Customize Templates**
  - [x] Load appropriate templates based on selected consultant
  - [x] Replace hardcoded meeting information
  - [x] Update event title to include consultant first name and last initial
  - [x] Create to-do for updating April's description template later

## User Experience Considerations

1. **Default Selection**
   - [x] No default consultant - explicit selection required
   - Remember last used consultant for returning users

2. **Visual Indicators**
   - Clearly show which consultant is currently active
   - Color-code or label interface elements by consultant

## Hard-Coded References to Update

In blind_invite.py:

- [x] Line 168-173: Consultant filtering - `if consultant != "Barbara Pigg":`
- [x] Line 243-249: Event description template with Barbara Pigg's information
- [x] Line 244: `I'm the CEO of Whiteboard Geeks` (company-specific text)
- [x] Line 272-301: Zoom meeting information hard-coded in template
- [x] Line 276: `Barbara Pigg is inviting you`
- [x] Line 278: `Barbara Pigg's Personal Meeting Room`
- [x] Line 280: `https://us02web.zoom.us/j/4960127137`
- [x] Line 282: `Meeting ID: 496 012 7137`

In calendar_utils.py:

- [x] Line 9: `CALENDAR_ID = "barbara.pigg@whiteboardgeeks.com"`
- [x] Line 155: Email hard-coded in calendar invite attendees: `"email": "barbara.pigg@whiteboardgeeks.com"`
- [x] Line 156: Set as calendar owner with `"self": True`
- [x] Line 185: Same CALENDAR_ID used in checking lead invites
- [x] Line 216: Same CALENDAR_ID used in getting events in range

Other references:

- The Close CRM custom activity type ID: `"custom_activity_type_id": "actitype_0CmcjmRFeEsO3yJFnLLVpS"`

## April Lowrie Information (For Reference)

- Job title: Creative Director
- Email: april.lowrie@whiteboardgeeks.com
- Close CRM ID: user_wOfS9vCRRQt7nQAaij3dCSr38xadW6N7fTMjMbHF88n
- Calendar ID: april.lowrie@whiteboardgeeks.com
- Zoom URL & meeting ID: To be determined
- Event title format: "Intro {{first_name}} {{last_initial}} @ {{company}} + April L @ Whiteboard Geeks"
- Description template: Will need to be customized later
- Custom activity type ID: Same as Barbara's

## Remaining TODOs

1. **April Lowrie Information Updates**
   - [ ] Update April's Zoom meeting URL and meeting ID
   - [x] Create customized description template for April
   - [ ] Review and test April's configuration

2. **User Experience Improvements**
   - [x] Add "Consultant" to the "Contact Information" section where the user clicks "Send Invite"
