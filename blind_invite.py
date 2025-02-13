import streamlit as st
import requests
import base64
import calendar_utils
import datetime
import pytz


# Function to search tasks in Close CRM
def search_tasks_in_close(task_search, close_api_key):
    # Encode the API key using Base64
    encoded_api_key = base64.b64encode(f"{close_api_key}:".encode()).decode()

    url = "https://api.close.com/api/v1/task/"
    headers = {
        "Authorization": f"Basic {encoded_api_key}",  # Use Basic auth with encoded key
        "Content-Type": "application/json",
    }
    params = {
        "_type": "lead",  # Assuming you want to search lead tasks
        "is_complete": False,
        "view": "inbox",
    }
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        tasks = response.json().get("data", [])
        # Filter tasks based on the task_search string
        filtered_tasks = [
            task for task in tasks if task_search.lower() in task["text"].lower()
        ]
        return filtered_tasks
    else:
        st.error("Task fetch failed")
        return []


def mark_task_complete_in_close(task_id, close_api_key):
    """Marks a task as complete in Close CRM."""
    encoded_api_key = base64.b64encode(f"{close_api_key}:".encode()).decode()
    url = f"https://api.close.com/api/v1/task/{task_id}/"
    headers = {
        "Authorization": f"Basic {encoded_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = {"is_complete": True}
    response = requests.put(url, headers=headers, json=data)
    if response.status_code != 200:
        raise ValueError(f"Failed to mark task as complete: {response.text}")
    return response.json()


def create_blind_invite_custom_activity_in_close(
    lead_id, close_api_key, date_of_meeting, date_invite_sent
):
    encoded_api_key = base64.b64encode(f"{close_api_key}:".encode()).decode()
    url = "https://api.close.com/api/v1/activity/custom/"
    headers = {
        "Authorization": f"Basic {encoded_api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "custom_activity_type_id": "actitype_0CmcjmRFeEsO3yJFnLLVpS",
        "lead_id": lead_id,
        "custom.cf_HiNTk2RNrqwaf0Uq4zgCOp6dB5v6IYy5KedqOaraZAB": date_of_meeting,
        "custom.cf_4Z6vPUo0xgW8CiECtoBSiMuA50RHsO0cVxFxsp9lq9u": date_invite_sent,
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        raise ValueError(f"Failed to create custom activity: {response.text}")
    return response.json()


def split_contact_name(full_name):
    name_parts = full_name.split()
    if len(name_parts) == 1:
        return name_parts[0], ""
    elif len(name_parts) == 2:
        return name_parts[0], name_parts[1]
    else:
        return f"{name_parts[0]} {name_parts[1]}", name_parts[2]


def get_state_timezone(state_code):
    """Maps US state codes to their primary timezone."""
    state_timezone_map = {
        "AL": "America/Chicago",  # Alabama
        "AK": "America/Anchorage",  # Alaska
        "AZ": "America/Phoenix",  # Arizona
        "AR": "America/Chicago",  # Arkansas
        "CA": "America/Los_Angeles",  # California
        "CO": "America/Denver",  # Colorado
        "CT": "America/New_York",  # Connecticut
        "DE": "America/New_York",  # Delaware
        "FL": "America/New_York",  # Florida
        "GA": "America/New_York",  # Georgia
        "HI": "Pacific/Honolulu",  # Hawaii
        "ID": "America/Boise",  # Idaho
        "IL": "America/Chicago",  # Illinois
        "IN": "America/Indiana/Indianapolis",  # Indiana
        "IA": "America/Chicago",  # Iowa
        "KS": "America/Chicago",  # Kansas
        "KY": "America/New_York",  # Kentucky
        "LA": "America/Chicago",  # Louisiana
        "ME": "America/New_York",  # Maine
        "MD": "America/New_York",  # Maryland
        "MA": "America/New_York",  # Massachusetts
        "MI": "America/Detroit",  # Michigan
        "MN": "America/Chicago",  # Minnesota
        "MS": "America/Chicago",  # Mississippi
        "MO": "America/Chicago",  # Missouri
        "MT": "America/Denver",  # Montana
        "NE": "America/Chicago",  # Nebraska
        "NV": "America/Los_Angeles",  # Nevada
        "NH": "America/New_York",  # New Hampshire
        "NJ": "America/New_York",  # New Jersey
        "NM": "America/Denver",  # New Mexico
        "NY": "America/New_York",  # New York
        "NC": "America/New_York",  # North Carolina
        "ND": "America/Chicago",  # North Dakota
        "OH": "America/New_York",  # Ohio
        "OK": "America/Chicago",  # Oklahoma
        "OR": "America/Los_Angeles",  # Oregon
        "PA": "America/New_York",  # Pennsylvania
        "RI": "America/New_York",  # Rhode Island
        "SC": "America/New_York",  # South Carolina
        "SD": "America/Chicago",  # South Dakota
        "TN": "America/Chicago",  # Tennessee
        "TX": "America/Chicago",  # Texas
        "UT": "America/Denver",  # Utah
        "VT": "America/New_York",  # Vermont
        "VA": "America/New_York",  # Virginia
        "WA": "America/Los_Angeles",  # Washington
        "WV": "America/New_York",  # West Virginia
        "WI": "America/Chicago",  # Wisconsin
        "WY": "America/Denver",  # Wyoming
        "DC": "America/New_York",  # District of Columbia
    }
    return state_timezone_map.get(state_code.upper())


def get_lead_info(lead_id, close_api_key):
    encoded_api_key = base64.b64encode(f"{close_api_key}:".encode()).decode()
    url = f"https://api.close.com/api/v1/lead/{lead_id}"
    headers = {
        "Authorization": f"Basic {encoded_api_key}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # This will raise an exception for HTTP errors

        if response.status_code == 200:
            lead_data = response.json()

            # Check if lead has contacts
            if not lead_data.get("contacts") or len(lead_data["contacts"]) == 0:
                st.error(f"Lead {lead_id} has no contacts")
                return None

            # Check if contact has a name
            contact = lead_data["contacts"][0]
            if not contact.get("name"):
                st.error(f"Contact in lead {lead_id} has no name")
                return None

            # Check if contact has an email
            if not contact.get("emails") or len(contact["emails"]) == 0:
                st.error(f"Contact in lead {lead_id} has no email")
                return None

            lead_data["company_name"] = lead_data["name"].split("-")[0]
            contact_name = contact["name"]
            lead_data["contact_name"] = contact_name
            lead_data["contact_firstname"], lead_data["contact_lastname"] = (
                split_contact_name(contact_name)
            )
            lead_data["contact_email"] = contact["emails"][0]["email"]

            # Initialize timezone information
            lead_data["timezone"] = None
            lead_data["timezone_offset"] = None
            lead_data["timezone_abbr"] = None
            lead_data["timezone_error"] = None

            # Add timezone information based on the lead's state if available
            if lead_data.get("addresses") and len(lead_data["addresses"]) > 0:
                state = lead_data["addresses"][0].get("state")
                if state:
                    timezone_name = get_state_timezone(state)
                    if timezone_name:
                        timezone = pytz.timezone(timezone_name)
                        lead_data["timezone"] = timezone_name
                        lead_data["timezone_offset"] = datetime.datetime.now(
                            timezone
                        ).strftime("%z")
                        lead_data["timezone_abbr"] = datetime.datetime.now(
                            timezone
                        ).strftime("%Z")
                    else:
                        lead_data["timezone_error"] = f"Unknown state code: {state}"
                else:
                    lead_data["timezone_error"] = "No state found in address"
            else:
                lead_data["timezone_error"] = "No address found"

            return lead_data
        else:
            st.error(f"Lead fetch failed with status code {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to fetch lead {lead_id}: {str(e)}")
        return None


def append_lead_info_to_tasks(tasks, close_api_key):
    updated_tasks = []
    for task in tasks:
        lead_info = get_lead_info(task["lead_id"], close_api_key)
        if lead_info is None:
            st.error(f"Failed to get lead info for task {task['id']}")
            continue
        task["lead_id"] = lead_info["id"]
        task["company_name"] = lead_info["company_name"]
        task["contact_name"] = lead_info["contact_name"]
        task["contact_email"] = lead_info["contact_email"]
        task["contact_firstname"] = lead_info["contact_firstname"]
        task["contact_lastname"] = lead_info["contact_lastname"]
        task["contact_lastinitial"] = (
            lead_info["contact_lastname"][0] if lead_info["contact_lastname"] else ""
        )
        # Add timezone information to task
        task["timezone"] = lead_info.get("timezone")
        task["timezone_offset"] = lead_info.get("timezone_offset")
        task["timezone_abbr"] = lead_info.get("timezone_abbr")
        task["timezone_error"] = lead_info.get("timezone_error")
        updated_tasks.append(task)
    return updated_tasks


def analyze_timezone_distribution(tasks):
    """Analyzes the distribution of leads across timezones and shows required slots by ET time.

    Shows how many slots are needed at each ET time based on timezone constraints:
    - 9am ET: ET leads
    - 10am ET: ET + CT leads
    - 11am ET: ET + CT + MT leads
    - 12pm ET: ET + CT + MT + PT leads
    - 1pm ET: ET + CT + MT + PT + AK leads
    - 2pm ET: ET + CT + MT + PT + AK + HI leads
    """
    # Initialize timezone counters
    timezone_counts = {
        "ET": 0,
        "CT": 0,
        "MT": 0,
        "PT": 0,
        "AK": 0,
        "HI": 0,
        "Unknown": 0,
    }

    # Map timezone names to our simplified categories
    timezone_mapping = {
        "America/New_York": "ET",
        "America/Indiana/Indianapolis": "ET",
        "America/Detroit": "ET",
        "America/Chicago": "CT",
        "America/Denver": "MT",
        "America/Phoenix": "MT",
        "America/Boise": "MT",
        "America/Los_Angeles": "PT",
        "America/Anchorage": "AK",
        "Pacific/Honolulu": "HI",
    }

    # Count leads in each timezone
    for task in tasks:
        timezone = task.get("timezone")
        if not timezone:
            timezone_counts["Unknown"] += 1
            continue

        # Map the timezone to our simplified category
        category = timezone_mapping.get(timezone, "Unknown")
        timezone_counts[category] += 1

    # Calculate cumulative slots needed at each ET time
    slots_needed = {
        "9am ET": timezone_counts["ET"],
        "10am ET": timezone_counts["ET"] + timezone_counts["CT"],
        "11am ET": timezone_counts["ET"]
        + timezone_counts["CT"]
        + timezone_counts["MT"],
        "12pm ET": timezone_counts["ET"]
        + timezone_counts["CT"]
        + timezone_counts["MT"]
        + timezone_counts["PT"],
        "1pm ET": timezone_counts["ET"]
        + timezone_counts["CT"]
        + timezone_counts["MT"]
        + timezone_counts["PT"]
        + timezone_counts["AK"],
        "2pm ET": timezone_counts["ET"]
        + timezone_counts["CT"]
        + timezone_counts["MT"]
        + timezone_counts["PT"]
        + timezone_counts["AK"]
        + timezone_counts["HI"],
    }

    return timezone_counts, slots_needed


def process_placeholder_slots(
    tasks, placeholder_event_name, meeting_length, leads_per_block
):
    """Process and analyze placeholder slots.

    Args:
        tasks: List of tasks to process
        placeholder_event_name: Name of placeholder events to search for
        meeting_length: Length of each meeting in minutes
        leads_per_block: Number of leads that can be scheduled in each time slot

    Returns:
        dict: Contains all the processed data needed for display, including:
            - timezone_counts: Count of leads in each timezone
            - slots_needed: Slots needed at each time
            - schedule_times: Mapping of times to timezones
            - placeholder_events: List of placeholder events found
            - total_available_slots: Total number of available slots
            - available_slots: Available slots at each time
            - all_timezones_satisfied: Whether all timezone requirements are met
            - table_data: Formatted data for display
            - slot_availability: Detailed availability for each slot
    """
    # Reset invite state when finding new slots
    st.session_state.invites_sent = False
    st.session_state.create_invites_clicked = False

    # Analyze timezone distribution first
    timezone_counts, slots_needed = analyze_timezone_distribution(tasks)

    # Map times to timezones for display
    schedule_times = {
        "9am": {"tz": "ET", "count": timezone_counts["ET"]},
        "10am": {"tz": "CT", "count": timezone_counts["CT"]},
        "11am": {"tz": "MT", "count": timezone_counts["MT"]},
        "12pm": {"tz": "PT", "count": timezone_counts["PT"]},
        "1pm": {"tz": "AK", "count": timezone_counts["AK"]},
        "2pm": {"tz": "HI", "count": timezone_counts["HI"]},
    }

    # Get placeholder events
    placeholder_events = calendar_utils.find_placeholder_events(placeholder_event_name)
    if not placeholder_events:
        return {
            "timezone_counts": timezone_counts,
            "slots_needed": slots_needed,
            "schedule_times": schedule_times,
            "placeholder_events": None,
        }

    # Sort placeholder events by start time
    placeholder_events = sorted(
        placeholder_events,
        key=lambda x: x["start"].get("dateTime", x["start"].get("date")),
    )

    # Check each event duration
    insufficient_blocks = []
    total_event_time = 0
    for event in placeholder_events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))
        start_dt = datetime.datetime.fromisoformat(start)
        end_dt = datetime.datetime.fromisoformat(end)
        duration = (end_dt - start_dt).total_seconds() / 60  # duration in minutes
        total_event_time += duration

        if duration < meeting_length:
            insufficient_blocks.append(event)

    if insufficient_blocks:
        return {
            "timezone_counts": timezone_counts,
            "slots_needed": slots_needed,
            "schedule_times": schedule_times,
            "placeholder_events": placeholder_events,
            "insufficient_blocks": insufficient_blocks,
        }

    # Calculate total available capacity considering existing events
    total_available_slots = 0

    # First calculate total slots available at each hour
    slots_at_hour = {
        14: 0,  # 2pm
        13: 0,  # 1pm
        12: 0,  # 12pm
        11: 0,  # 11am
        10: 0,  # 10am
        9: 0,  # 9am
    }

    # Process each event and calculate slot availability
    slot_availability = []
    for event in placeholder_events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))
        start_dt = datetime.datetime.fromisoformat(start)
        end_dt = datetime.datetime.fromisoformat(end)

        num_slots = int((end_dt - start_dt).total_seconds() / 60 / meeting_length)
        event_slots = []

        for slot_index in range(num_slots):
            slot_start = start_dt + datetime.timedelta(
                minutes=slot_index * meeting_length
            )
            slot_end = slot_start + datetime.timedelta(minutes=meeting_length)

            # Get existing events in this slot
            existing_events = calendar_utils.get_events_in_range(
                slot_start.isoformat(),
                slot_end.isoformat(),
            )

            # Count non-placeholder events
            events_in_slot = len(
                [
                    event
                    for event in existing_events
                    if event["summary"] != placeholder_event_name
                ]
            )

            # Calculate available slots in this time slot
            available_in_slot = max(0, leads_per_block - events_in_slot)
            total_available_slots += available_in_slot

            # Add to the appropriate hour bucket
            slot_start_et = slot_start.astimezone(pytz.timezone("America/New_York"))
            hour_et = slot_start_et.hour
            if hour_et in slots_at_hour:
                slots_at_hour[hour_et] += available_in_slot

            # Store slot availability for display
            event_slots.append(
                {
                    "start": slot_start_et,
                    "available": available_in_slot,
                    "total": leads_per_block,
                }
            )

        slot_availability.append({"event": event, "slots": event_slots})

    # Now allocate slots to each timezone requirement
    time_to_hour = {
        "2pm": 14,
        "1pm": 13,
        "12pm": 12,
        "11am": 11,
        "10am": 10,
        "9am": 9,
    }

    # Start with latest time first
    unallocated_slots = dict(slots_at_hour)  # Copy of available slots
    available_slots = {}
    for time in ["2pm", "1pm", "12pm", "11am", "10am", "9am"]:
        hour = time_to_hour[time]
        leads_needed = timezone_counts[schedule_times[time]["tz"]]

        # Calculate total available slots at or after this hour
        slots_available = sum(
            unallocated_slots[h] for h in unallocated_slots if h >= hour
        )

        # Record available slots for this time
        available_slots[time] = slots_available

        # Remove the slots we need for this timezone from available slots,
        # starting with the earliest possible time for this timezone
        slots_to_allocate = min(leads_needed, slots_available)
        for h in sorted(unallocated_slots.keys()):
            if h >= hour and slots_to_allocate > 0:
                allocated = min(slots_to_allocate, unallocated_slots[h])
                unallocated_slots[h] -= allocated
                slots_to_allocate -= allocated

    # Create table rows
    table_data = []
    all_timezones_satisfied = True
    for time in ["2pm", "1pm", "12pm", "11am", "10am", "9am"]:
        leads = timezone_counts[schedule_times[time]["tz"]]
        available = available_slots[time]
        status = "✅" if available >= leads else "⛔"
        if status == "⛔":
            all_timezones_satisfied = False
        table_data.append(
            {
                "Time (ET) or later": time,
                "Leads to Schedule": leads,
                "Available Slots": available,
                "Status": status,
            }
        )

    return {
        "timezone_counts": timezone_counts,
        "slots_needed": slots_needed,
        "schedule_times": schedule_times,
        "placeholder_events": placeholder_events,
        "total_available_slots": total_available_slots,
        "available_slots": available_slots,
        "all_timezones_satisfied": all_timezones_satisfied,
        "table_data": table_data,
        "slot_availability": slot_availability,
    }


def main():
    st.set_page_config(page_title="Auto Calendar Invites")

    # Password protection
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        password = st.text_input("Enter password:", type="password")
        if st.button("Login"):
            if password == st.secrets["PASSWORD"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password")
        return

    st.title("Auto Calendar Invites")

    # Default event description template
    event_description_default = """Hi {{first_name}},

I'm the CEO of Whiteboard Geeks, we make whiteboard videos to simplify complex messages for medical companies. Not terribly long ago I sent you a package with what we call a 'Video Card' or 'Video Brochure'. With the way the mail goes & hybrid work schedules, I wasn't sure if it arrived so I thought I'd invite you to a quick meeting.

I'm hoping to share more about our process for telling your most important story, and explain how we've been able to drive great results for companies like Medtronic, Eli Lilly, and Cleveland Clinic. 

If this time doesn't work for you please feel free to propose one that does. Whatever is convenient.

Agenda:
- Share science behind the Whiteboard Geeks success stories, benchmarking data, and observed industry trends
- Learn about your current objectives and challenges
- Get feedback on the usefulness of Whiteboard Geeks services for your organization
- Plus we'll unlock the vault and show you videos related to your specific challenge-because videos are fun 😊🎥⭐

As a bonus: I'll give you a fun hand-drawn virtual background just for showing your smiling face! Yay! We get lots of compliments on our backgrounds…and now you can have one! 

Zoom Call information:
Barbara Pigg is inviting you to a scheduled Zoom meeting.

Topic: Barbara Pigg's Personal Meeting Room

Join Zoom Meeting
https://us02web.zoom.us/j/4960127137

Meeting ID: 496 012 7137

---

One tap mobile
+16469313860,,4960127137# US
+13017158592,,4960127137# US (Washington DC)

---

Dial by your location
• +1 646 931 3860 US
• +1 301 715 8592 US (Washington DC)
• +1 305 224 1968 US
• +1 309 205 3325 US
• +1 312 626 6799 US (Chicago)
• +1 646 558 8656 US (New York)
• +1 346 248 7799 US (Houston)
• +1 360 209 5623 US
• +1 386 347 5053 US
• +1 507 473 4847 US
• +1 564 217 2000 US
• +1 669 444 9171 US
• +1 669 900 9128 US (San Jose)
• +1 689 278 1000 US
• +1 719 359 4580 US
• +1 253 205 0468 US
• +1 253 215 8782 US (Tacoma)

Meeting ID: 496 012 7137

Find your local number: https://us02web.zoom.us/u/ksKzmwpEc"""

    # Initialize session state for tasks and options
    if "tasks" not in st.session_state:
        st.session_state.tasks = []
    if "meeting_length" not in st.session_state:
        st.session_state.meeting_length = 30
    if "leads_per_block" not in st.session_state:
        st.session_state.leads_per_block = 6
    if "invites_sent" not in st.session_state:
        st.session_state.invites_sent = False
    if "current_task_index" not in st.session_state:
        st.session_state.current_task_index = 0
    if "review_mode" not in st.session_state:
        st.session_state.review_mode = False
    if "current_title" not in st.session_state:
        st.session_state.current_title = ""
    if "current_description" not in st.session_state:
        st.session_state.current_description = ""
    if "template_title" not in st.session_state:
        st.session_state.template_title = "Intro {{first_name}} {{last_initial}} @  {{company}} + Barbara P @ Whiteboard Geeks"
    if "template_description" not in st.session_state:
        st.session_state.template_description = event_description_default
    if "slot_usage" not in st.session_state:
        st.session_state.slot_usage = {}  # Will track {slot_start_time: number_of_leads}

    # Initialize session state for search attempt
    if "search_attempted" not in st.session_state:
        st.session_state.search_attempted = False

    # Step 1: User input for task search
    task_search = st.text_input("Enter task search string:")

    # Retrieve the Close API key from Streamlit secrets
    close_api_key = st.secrets["CLOSE_API_KEY"]

    if st.button("Search Tasks") and task_search:
        with st.spinner("Searching for tasks..."):
            st.session_state.tasks = search_tasks_in_close(task_search, close_api_key)
            st.session_state.tasks = append_lead_info_to_tasks(
                st.session_state.tasks, close_api_key
            )
            # Sort tasks by timezone offset, westernmost (most negative) first
            st.session_state.tasks.sort(
                key=lambda x: int(x.get("timezone_offset", "0000").replace(":", ""))
                if x.get("timezone_offset")
                else 0
            )
            st.session_state.search_attempted = True

    if st.session_state.search_attempted:
        if st.session_state.tasks:
            st.write(
                f"Found {len(st.session_state.tasks)} lead(s) that have that task description to be completed:"
            )
            # Check if any tasks have timezone errors
            has_timezone_errors = any(
                task.get("timezone_error") for task in st.session_state.tasks
            )

            # Create expander with auto-expand based on errors
            with st.expander("View all leads", expanded=has_timezone_errors):
                # Display all tasks, highlighting those with errors
                for task in st.session_state.tasks:
                    if task.get("timezone_error"):
                        st.error(
                            f"{task['company_name']} - {task['contact_name']} (Timezone Error: {task['timezone_error']})"
                        )
                    else:
                        st.write(f"{task['company_name']} - {task['contact_name']}")

            # Now filter out tasks with timezone errors
            st.session_state.tasks = [
                task
                for task in st.session_state.tasks
                if not task.get("timezone_error")
            ]
            st.write(
                f"\nProceeding with {len(st.session_state.tasks)} error-free leads"
            )

            # Additional check for timezone offsets and sort
            tasks_with_offsets = []
            for task in st.session_state.tasks:
                if not task.get("timezone_offset"):
                    st.error(
                        f"Task for {task['company_name']} - {task['contact_name']} missing timezone offset"
                    )
                else:
                    tasks_with_offsets.append(task)

            # Sort by timezone offset, westernmost first
            tasks_with_offsets.sort(
                key=lambda x: int(x["timezone_offset"].replace(":", ""))
            )
            st.session_state.tasks = tasks_with_offsets

            if not st.session_state.tasks:
                st.error(
                    "No valid tasks remaining. Please fix timezone issues and try again."
                )
                return

            # Show meeting length and leads per block inputs after tasks are found
            st.session_state.meeting_length = st.selectbox(
                "Select meeting length:",
                options=[10, 15, 20, 25, 30],
                index=[10, 15, 20, 25, 30].index(st.session_state.meeting_length),
                key="meeting_length_select",
            )

            # Reset flags if meeting length changed
            if "prev_meeting_length" not in st.session_state:
                st.session_state.prev_meeting_length = st.session_state.meeting_length
            elif (
                st.session_state.prev_meeting_length != st.session_state.meeting_length
            ):
                st.session_state.time_looks_good = False
                st.session_state.create_invites_clicked = False
                st.session_state.prev_meeting_length = st.session_state.meeting_length

            st.session_state.leads_per_block = st.number_input(
                "Enter number of leads per block:",
                min_value=1,
                value=st.session_state.leads_per_block,
                key="leads_per_block_input",
            )

            # Reset flags if leads per block changed
            if "prev_leads_per_block" not in st.session_state:
                st.session_state.prev_leads_per_block = st.session_state.leads_per_block
            elif (
                st.session_state.prev_leads_per_block
                != st.session_state.leads_per_block
            ):
                st.session_state.time_looks_good = False
                st.session_state.create_invites_clicked = False
                st.session_state.prev_leads_per_block = st.session_state.leads_per_block

            # Add a text input for placeholder event name
            placeholder_event_name = st.text_input(
                "Placeholder event name:", "Blind invite", key="placeholder_name_input"
            )

            # Reset flags if placeholder name changed
            if "prev_placeholder_name" not in st.session_state:
                st.session_state.prev_placeholder_name = placeholder_event_name
            elif st.session_state.prev_placeholder_name != placeholder_event_name:
                st.session_state.time_looks_good = False
                st.session_state.create_invites_clicked = False
                st.session_state.prev_placeholder_name = placeholder_event_name

            if st.button("Find Placeholder Slots"):
                # All computation in the spinner
                with st.spinner("Finding and analyzing available slots..."):
                    result = process_placeholder_slots(
                        st.session_state.tasks,
                        placeholder_event_name,
                        st.session_state.meeting_length,
                        st.session_state.leads_per_block,
                    )

                # All display code after the spinner
                if not result["placeholder_events"]:
                    st.write("No 'Placeholder' slots found.")
                    return

                if "insufficient_blocks" in result:
                    st.write("The following blocks are not long enough:")
                    for block in result["insufficient_blocks"]:
                        st.write(
                            f"- {block['summary']} from {block['start']} to {block['end']}"
                        )
                    st.write("Please update these blocks and re-run.")
                    return

                # Display timezone distribution in an expander
                with st.expander("Timezone Distribution", expanded=False):
                    st.write("### Leads that must be scheduled after:")
                    # Display each timezone's leads with their scheduling time
                    for time, info in result["schedule_times"].items():
                        if info["count"] > 0:
                            st.write(
                                f"- {time} - {info['count']} leads in {info['tz']}"
                            )

                    if result["timezone_counts"]["Unknown"] > 0:
                        st.warning(
                            f"⚠️ {result['timezone_counts']['Unknown']} leads with unknown timezone"
                        )

                # Make entire Available slots section collapsible
                with st.expander("### Available slots in placeholder events"):
                    # Create tabs for each block
                    tab_labels = []
                    for event_data in result["slot_availability"]:
                        event = event_data["event"]
                        start = event["start"].get(
                            "dateTime", event["start"].get("date")
                        )
                        end = event["end"].get("dateTime", event["end"].get("date"))
                        start_dt = datetime.datetime.fromisoformat(start)
                        end_dt = datetime.datetime.fromisoformat(end)

                        # Convert to Eastern Time for display
                        eastern = pytz.timezone("America/New_York")
                        start_et = start_dt.astimezone(eastern)
                        end_et = end_dt.astimezone(eastern)

                        # Create tab label with date and time range
                        tab_label = f"**{start_et.strftime('%A, %B %d')}** {start_et.strftime('%I:%M %p')} - {end_et.strftime('%I:%M %p')} ET"
                        tab_labels.append(tab_label)

                    # Create tabs
                    tabs = st.tabs(tab_labels)

                    # Fill each tab with its content
                    for idx, (tab, event_data) in enumerate(
                        zip(tabs, result["slot_availability"])
                    ):
                        with tab:
                            for slot in event_data["slots"]:
                                slot_start_et = slot["start"]
                                st.write(
                                    f"{slot_start_et.strftime('%I:%M %p')} ET - {slot['available']} of {slot['total']} available"
                                )

                # Display timezone requirements analysis
                st.write("\n### Timezone Requirements Analysis")
                st.table(result["table_data"])

                # Check if we have enough total capacity
                if result["total_available_slots"] < len(st.session_state.tasks):
                    st.write(
                        f"Not enough available capacity in the placeholder slots. Need {len(st.session_state.tasks)} slots but only have {result['total_available_slots']} available after accounting for existing events."
                    )
                elif not result["all_timezones_satisfied"]:
                    st.write(
                        "⚠️ Some timezone requirements cannot be met with current slot distribution"
                    )
                else:
                    st.write("✅ Time looks good")
                    st.session_state.time_looks_good = True
                    st.session_state.placeholder_events = result["placeholder_events"]

            if st.session_state.get("time_looks_good", False):
                # Add template fields for event customization
                st.subheader("Event Customization")
                title_input = st.text_input(
                    "Event Title Template:",
                    value=st.session_state.template_title,
                    help="Use {{first_name}}, {{last_name}}, {{company}}, and {{last_initial}} as placeholders",
                    key="event_title_template",
                )
                if title_input != st.session_state.template_title:
                    st.session_state.template_title = title_input
                    # Reset review mode if template is modified
                    st.session_state.review_mode = False

                description_input = st.text_area(
                    "Event Description Template:",
                    value=st.session_state.template_description,
                    help="Use {{first_name}}, {{last_name}}, {{company}}, and {{last_initial}} as placeholders",
                    key="event_description_template",
                )
                if description_input != st.session_state.template_description:
                    st.session_state.template_description = description_input
                    # Reset review mode if template is modified
                    st.session_state.review_mode = False

                # Show example of template output with first task's data
                if st.session_state.tasks:
                    first_task = st.session_state.tasks[0]
                    st.subheader("Preview with first task's data:")
                    st.write(
                        "Contact:",
                        first_task["contact_firstname"],
                        first_task["contact_lastname"],
                    )
                    st.write("Company:", first_task["company_name"])

                    example_title = calendar_utils.format_template(
                        st.session_state.template_title, first_task
                    )
                    example_desc = calendar_utils.format_template(
                        st.session_state.template_description,
                        first_task,
                    )

                    st.write("Your event title will look like:", example_title)
                    st.write("Your description will look like:", example_desc)

                # Ensure the 'Create Invites' button remains visible after being clicked
                if "create_invites_clicked" not in st.session_state:
                    st.session_state.create_invites_clicked = False

                if not st.session_state.review_mode and st.button("Review Invites"):
                    st.session_state.review_mode = True
                    st.session_state.current_task_index = 0
                    # Initialize the first task's rendered templates
                    task = st.session_state.tasks[0]
                    st.session_state.current_title = calendar_utils.format_template(
                        st.session_state.template_title, task
                    )
                    st.session_state.current_description = (
                        calendar_utils.format_template(
                            st.session_state.template_description, task
                        )
                    )
                    st.rerun()

                if st.session_state.review_mode:
                    task = st.session_state.tasks[st.session_state.current_task_index]
                    total_tasks = len(st.session_state.tasks)

                    # Display progress
                    st.write(
                        f"Reviewing invite {st.session_state.current_task_index + 1} of {total_tasks}"
                    )

                    # Contact information at the top
                    st.write("### Contact Information")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.write(
                            f"**Name:** {task['contact_firstname']} {task['contact_lastname']}"
                        )
                        st.write(f"**Company:** {task['company_name']}")
                    with col2:
                        st.write(f"**Email:** {task['contact_email']}")
                    with col3:
                        if task.get("timezone"):
                            st.write(
                                f"**Timezone:** {task['timezone_abbr']} ({task['timezone_offset']})"
                            )
                        else:
                            st.write("**Timezone:** Unknown")

                    # Send invite button at the top
                    if st.button("Send Invite", key="send_invite"):
                        try:
                            # Find the next available slot
                            slot_found = False
                            for (
                                placeholder_event
                            ) in st.session_state.placeholder_events:
                                start = placeholder_event["start"].get(
                                    "dateTime", placeholder_event["start"].get("date")
                                )
                                end = placeholder_event["end"].get(
                                    "dateTime", placeholder_event["end"].get("date")
                                )
                                start_dt = datetime.datetime.fromisoformat(start)
                                end_dt = datetime.datetime.fromisoformat(end)

                                # Calculate number of slots in this placeholder event
                                event_duration = (
                                    end_dt - start_dt
                                ).total_seconds() / 60
                                num_slots = int(
                                    event_duration / st.session_state.meeting_length
                                )

                                # Try each slot in this placeholder event
                                for slot_index in range(num_slots):
                                    slot_start = start_dt + datetime.timedelta(
                                        minutes=slot_index
                                        * st.session_state.meeting_length
                                    )
                                    slot_key = slot_start.isoformat()

                                    # Initialize slot usage if not exists
                                    if slot_key not in st.session_state.slot_usage:
                                        st.session_state.slot_usage[slot_key] = 0

                                    # Get existing events in this slot
                                    slot_end = slot_start + datetime.timedelta(
                                        minutes=st.session_state.meeting_length
                                    )
                                    existing_events = (
                                        calendar_utils.get_events_in_range(
                                            slot_start.isoformat(),
                                            slot_end.isoformat(),
                                        )
                                    )

                                    # Count events that overlap with this slot (excluding placeholder events)
                                    events_in_slot = len(
                                        [
                                            event
                                            for event in existing_events
                                            if event["summary"]
                                            != placeholder_event_name
                                        ]
                                    )

                                    # Check if slot has capacity (considering both tracked invites and existing events)
                                    total_events = (
                                        st.session_state.slot_usage[slot_key]
                                        + events_in_slot
                                    )
                                    if total_events < st.session_state.leads_per_block:
                                        # Create the calendar invite
                                        calendar_utils.create_calendar_invite(
                                            task,
                                            slot_start.isoformat(),
                                            slot_end.isoformat(),
                                            title_template=st.session_state.current_title,
                                            description_template=st.session_state.current_description,
                                        )

                                        # Update slot usage
                                        st.session_state.slot_usage[slot_key] += 1
                                        slot_found = True

                                        # Mark task as complete and update UI
                                        try:
                                            mark_task_complete_in_close(
                                                task["id"], close_api_key
                                            )
                                            create_blind_invite_custom_activity_in_close(
                                                task["lead_id"],
                                                close_api_key,
                                                slot_start.date().isoformat(),
                                                datetime.datetime.now()
                                                .date()
                                                .isoformat(),
                                            )
                                            st.success(
                                                f"Invite sent to {task['contact_name']} and task marked as complete and custom activity created"
                                            )
                                            # Remove the completed task from session state
                                            st.session_state.tasks = [
                                                t
                                                for t in st.session_state.tasks
                                                if t["id"] != task["id"]
                                            ]
                                        except ValueError as e:
                                            st.warning(
                                                f"Invite sent but failed to mark task as complete: {str(e)}"
                                            )
                                        break

                                if slot_found:
                                    break

                            if not slot_found:
                                st.error(
                                    "No available slots found. All slots are at capacity."
                                )
                                return

                            # Move to next task if there are any remaining
                            if st.session_state.tasks:
                                st.session_state.current_task_index = min(
                                    st.session_state.current_task_index,
                                    len(st.session_state.tasks) - 1,
                                )
                                if (
                                    st.session_state.tasks
                                ):  # Double check in case list is now empty
                                    next_task = st.session_state.tasks[
                                        st.session_state.current_task_index
                                    ]
                                    st.session_state.current_title = (
                                        calendar_utils.format_template(
                                            st.session_state.template_title, next_task
                                        )
                                    )
                                    st.session_state.current_description = (
                                        calendar_utils.format_template(
                                            st.session_state.template_description,
                                            next_task,
                                        )
                                    )
                                else:
                                    st.session_state.review_mode = False
                            else:
                                st.session_state.review_mode = False
                            st.rerun()
                        except ValueError as e:
                            st.error(f"Failed to create invite: {str(e)}")

                    # Editable fields
                    st.write("### Event Details")
                    st.session_state.current_title = st.text_input(
                        "Event Title",
                        value=st.session_state.current_title,
                        key=f"title_{st.session_state.current_task_index}",
                    )
                    st.session_state.current_description = st.text_area(
                        "Event Description",
                        value=st.session_state.current_description,
                        key=f"desc_{st.session_state.current_task_index}",
                    )
        else:
            st.write("No tasks found.")


# Run the app
if __name__ == "__main__":
    main()
