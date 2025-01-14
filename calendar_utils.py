import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CALENDAR_ID = "lance@whiteboardgeeks.com"


def get_calendar_service():
    """Returns an authorized Google Calendar API service instance."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
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


def create_calendar_invite(task, start_time, end_time):
    """Creates a calendar invite for a given task."""
    try:
        service = get_calendar_service()

        event = {
            "summary": "Test event",
            "description": f"Task from Close CRM: {task['text']}",
            "start": {
                "dateTime": start_time,
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": end_time,
                "timeZone": "UTC",
            },
            "attendees": [
                {"email": "lance@servantrealestate.com"},
            ],
        }

        event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
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
