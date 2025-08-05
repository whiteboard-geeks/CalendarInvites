# CalendarInvites
Streamlit app for automated calendar invite generation with Close CRM integration and Zoom meeting templates.

## Why It Exists
Sales teams spend too much time manually creating calendar invites and coordinating meetings with leads. This automates the entire workflow from CRM task search to meeting creation with pre-configured templates and automatic task completion.

## What Makes It Interesting
- **CRM workflow automation**: Seamlessly integrates with Close CRM to search tasks, fetch lead information, and update records
- **Smart calendar management**: Automatically generates calendar invites with Zoom meeting links and customizable templates
- **Session state management**: Uses Streamlit's advanced state management for complex multi-step workflows
- **Professional UX**: Clean interface for reviewing and approving invites before sending, with bulk processing capabilities

## Tech Stack
- **UI Framework**: Streamlit with advanced session state management
- **CRM Integration**: Close CRM API for lead and task management
- **Calendar**: Google Calendar API for meeting creation
- **Video Conferencing**: Zoom API integration for meeting links
- **Email**: Automated email sending with customizable templates

## How to Run
```bash
git clone https://github.com/lancejohnson/CalendarInvites.git
cd CalendarInvites
pip install -r requirements.txt

# Set environment variables
export CLOSE_API_KEY=your_close_api_key
export GOOGLE_CALENDAR_CREDENTIALS=your_google_credentials
export ZOOM_API_KEY=your_zoom_api_key

# Run Streamlit app
streamlit run blind_invite.py
```

## Demo
Interactive Streamlit interface showing task search, invite preview, and batch processing workflows.

## Status
Production-ready - Used daily for sales team calendar management and CRM automation.

## Notes
Built with extensive session state management to handle complex workflows. Includes detailed pseudocode documentation showing the planned architecture and implementation approach.
