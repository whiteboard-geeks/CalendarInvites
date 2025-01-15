import datetime
import json
import streamlit as st

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CALENDAR_ID = "lance@whiteboardgeeks.com"


def format_template(template, task):
    """Formats a template string using task data."""
    return (
        template.replace("{{first_name}}", task.get("contact_firstname", ""))
        .replace("{{last_name}}", task.get("contact_lastname", ""))
        .replace("{{company}}", task.get("company_name", ""))
        .replace("{{last_initial}}", task.get("contact_lastinitial", ""))
    )


def create_credentials_dict():
    """Creates a credentials dictionary from Streamlit secrets."""
    return {
        "web": {
            "client_id": st.secrets.google_calendar["client_id"],
            "project_id": st.secrets.google_calendar["project_id"],
            "auth_uri": st.secrets.google_calendar["auth_uri"],
            "token_uri": st.secrets.google_calendar["token_uri"],
            "auth_provider_x509_cert_url": st.secrets.google_calendar[
                "auth_provider_x509_cert_url"
            ],
            "client_secret": st.secrets.google_calendar["client_secret"],
            "redirect_uris": st.secrets.google_calendar["redirect_uris"],
            "javascript_origins": st.secrets.google_calendar["javascript_origins"],
        }
    }


def get_calendar_service():
    """Returns an authorized Google Calendar API service instance."""
    creds = None

    # Try to load from streamlit secrets if token exists
    if "token" in st.session_state:
        creds = Credentials.from_authorized_user_info(st.session_state["token"], SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            credentials_dict = create_credentials_dict()

            # Create OAuth flow using InstalledAppFlow for local server
            flow = InstalledAppFlow.from_client_config(
                credentials_dict,
                SCOPES,
            )

            # Run the local server flow on a different port
            creds = flow.run_local_server(port=8502)

            # Store the credentials in session state
            st.session_state["token"] = json.loads(creds.to_json())
            st.success("Successfully authenticated!")
            st.rerun()  # Rerun the app to use the new credentials

    return build("calendar", "v3", credentials=creds)


def find_placeholder_events(query="Blind Invite"):
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    try:
        service = get_calendar_service()

        # Call the Calendar API
        now = datetime.datetime.utcnow().isoformat() + "Z"  # 'Z' indicates UTC time
        events_result = (
            service.events()
            .list(
                calendarId="lance@whiteboardgeeks.com",
                timeMin=now,
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
                q=query,
            )
            .execute()
        )
        events = events_result.get("items", [])

        if not events:
            print("No upcoming events found.")
            return

        # Prints the start and name of the next 10 events
        return events

    except HttpError as error:
        print(f"An error occurred: {error}")


def create_calendar_invite(
    task, start_time, end_time, title_template=None, description_template=None
):
    """Creates a calendar invite for a given task."""
    try:
        if not title_template or not description_template:
            raise ValueError(
                "Both title_template and description_template are required"
            )

        service = get_calendar_service()

        # Format title and description using templates
        title = format_template(title_template, task)
        description = format_template(description_template, task)

        event = {
            "summary": title,
            "description": description,
            "location": "https://us02web.zoom.us/j/4960127137",
            "start": {
                "dateTime": start_time,
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": end_time,
                "timeZone": "UTC",
            },
            "attendees": [
                {
                    "email": "lance@whiteboardgeeks.com",
                    "responseStatus": "accepted",
                    "self": True,
                },
                {"email": task["contact_email"]},
            ],
        }

        event = (
            service.events()
            .insert(calendarId=CALENDAR_ID, body=event, sendUpdates="all")
            .execute()
        )
        return event

    except HttpError as error:
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    # Find placeholder events
    events = find_placeholder_events()
    print("Found events:", events)

    # Create a sample event
    task = {"text": "Sample Task"}
    start_time = "2025-01-15T10:00:00Z"
    end_time = "2025-01-15T11:00:00Z"
    created_event = create_calendar_invite(task, start_time, end_time)
    print("Created event:", created_event)
