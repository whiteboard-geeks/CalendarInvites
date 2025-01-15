import streamlit as st
import requests
import base64
import calendar_utils
import datetime


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


def split_contact_name(full_name):
    name_parts = full_name.split()
    if len(name_parts) == 1:
        return name_parts[0], ""
    elif len(name_parts) == 2:
        return name_parts[0], name_parts[1]
    else:
        return f"{name_parts[0]} {name_parts[1]}", name_parts[2]


def get_lead_info(lead_id, close_api_key):
    encoded_api_key = base64.b64encode(f"{close_api_key}:".encode()).decode()
    url = f"https://api.close.com/api/v1/lead/{lead_id}"
    headers = {
        "Authorization": f"Basic {encoded_api_key}",
        "Content-Type": "application/json",
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        lead_data = response.json()
        lead_data["company_name"] = lead_data["name"].split("-")[0]
        contact_name = lead_data["contacts"][0]["name"]
        lead_data["contact_name"] = contact_name
        lead_data["contact_firstname"], lead_data["contact_lastname"] = (
            split_contact_name(contact_name)
        )
        lead_data["contact_email"] = lead_data["contacts"][0]["emails"][0]["email"]
        return lead_data
    else:
        st.error("Lead fetch failed")
        return None


def append_lead_info_to_tasks(tasks, close_api_key):
    updated_tasks = []
    for task in tasks:
        lead_info = get_lead_info(task["lead_id"], close_api_key)
        task["lead_id"] = lead_info["id"]
        task["company_name"] = lead_info["company_name"]
        task["contact_name"] = lead_info["contact_name"]
        task["contact_email"] = lead_info["contact_email"]
        task["contact_firstname"] = lead_info["contact_firstname"]
        task["contact_lastname"] = lead_info["contact_lastname"]
        updated_tasks.append(task)
    return updated_tasks


def main():
    st.title("Automated Calendar Invites")

    # Initialize session state for tasks and options
    if "tasks" not in st.session_state:
        st.session_state.tasks = []
    if "meeting_length" not in st.session_state:
        st.session_state.meeting_length = 15
    if "leads_per_block" not in st.session_state:
        st.session_state.leads_per_block = 6
    if "invites_sent" not in st.session_state:
        st.session_state.invites_sent = False

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
            st.session_state.search_attempted = True

    if st.session_state.search_attempted:
        if st.session_state.tasks:
            st.write(
                f"Found {len(st.session_state.tasks)} lead(s) that have that task description to be completed:"
            )
            for task in st.session_state.tasks:
                st.write(f"- {task['lead_name']}")

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

            # Add template fields for event customization
            st.subheader("Event Customization")
            event_title_template = st.text_input(
                "Event Title Template:",
                "Intro {{first_name}} @  {{company}} + Barbara P @ Whiteboard Geeks",
                help="Use {{first_name}}, {{last_name}}, and {{company}} as placeholders",
                key="event_title_template",
            )
            event_description_default = """Hi {{first_name}},

I'm the CEO of Whiteboard Geeks, we make whiteboard videos to simplify complex messages for medical companies. Not terribly long ago I sent you a package with what we call a ‘Video Card’ or ‘Video Brochure’. With the way the mail goes & hybrid work schedules, I wasn't sure if it arrived so I thought I'd invite you to a quick meeting.

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

Find your local number: https://us02web.zoom.us/u/ksKzmwpEc
"""
            event_description_template = st.text_area(
                "Event Description Template:",
                event_description_default,
                help="Use {{first_name}}, {{last_name}}, and {{company}} as placeholders",
                key="event_description_template",
            )

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
                    event_title_template, first_task
                )
                example_desc = calendar_utils.format_template(
                    event_description_template,
                    first_task,
                )

                st.write("Your event title will look like:", example_title)
                st.write("Your description will look like:", example_desc)

            # Reset flags if placeholder name changed
            if "prev_placeholder_name" not in st.session_state:
                st.session_state.prev_placeholder_name = placeholder_event_name
            elif st.session_state.prev_placeholder_name != placeholder_event_name:
                st.session_state.time_looks_good = False
                st.session_state.create_invites_clicked = False
                st.session_state.prev_placeholder_name = placeholder_event_name

            if st.button("Find Placeholder Slots"):
                # Reset invite state when finding new slots
                st.session_state.invites_sent = False
                st.session_state.create_invites_clicked = False

                placeholder_events = calendar_utils.find_placeholder_events(
                    placeholder_event_name
                )
                if placeholder_events:
                    # Check each event duration
                    insufficient_blocks = []
                    total_event_time = 0
                    for event in placeholder_events:
                        start = event["start"].get(
                            "dateTime", event["start"].get("date")
                        )
                        end = event["end"].get("dateTime", event["end"].get("date"))
                        start_dt = datetime.datetime.fromisoformat(start)
                        end_dt = datetime.datetime.fromisoformat(end)
                        duration = (
                            end_dt - start_dt
                        ).total_seconds() / 60  # duration in minutes
                        total_event_time += duration

                        if duration < st.session_state.meeting_length:
                            insufficient_blocks.append(event)

                    if insufficient_blocks:
                        st.write("The following blocks are not long enough:")
                        for block in insufficient_blocks:
                            st.write(
                                f"- {block['summary']} from {block['start']} to {block['end']}"
                            )
                        st.write("Please update these blocks and re-run.")
                    else:
                        # Check total event time
                        required_time = (
                            len(st.session_state.tasks)
                            * st.session_state.meeting_length
                        ) / st.session_state.leads_per_block
                        if total_event_time < required_time:
                            st.write(
                                "You need to add more time to accommodate all tasks."
                            )
                        else:
                            st.write("✅ Time looks good")
                            st.session_state.time_looks_good = True
                            st.session_state.placeholder_events = placeholder_events
                else:
                    st.write("No 'Placeholder' slots found.")

            # Ensure the 'Create Invites' button remains visible after being clicked
            if "create_invites_clicked" not in st.session_state:
                st.session_state.create_invites_clicked = False

            if st.session_state.get("time_looks_good", False):
                if (
                    st.button("Create Invites")
                    or st.session_state.create_invites_clicked
                ) and not st.session_state.invites_sent:
                    st.session_state.create_invites_clicked = True
                    st.session_state.invites_sent = True
                    if st.session_state.placeholder_events:
                        task_index = 0
                        for placeholder_event in st.session_state.placeholder_events:
                            if task_index >= len(st.session_state.tasks):
                                break

                            start = placeholder_event["start"].get(
                                "dateTime", placeholder_event["start"].get("date")
                            )
                            end = placeholder_event["end"].get(
                                "dateTime", placeholder_event["end"].get("date")
                            )
                            start_dt = datetime.datetime.fromisoformat(start)
                            end_dt = datetime.datetime.fromisoformat(end)

                            block_duration = (end_dt - start_dt).total_seconds() / 60
                            meetings_per_block = int(
                                block_duration // st.session_state.meeting_length
                            )

                            for _ in range(meetings_per_block):
                                if task_index >= len(st.session_state.tasks):
                                    break

                                for _ in range(st.session_state.leads_per_block):
                                    if task_index >= len(st.session_state.tasks):
                                        break

                                    task = st.session_state.tasks[task_index]
                                    meeting_end_dt = start_dt + datetime.timedelta(
                                        minutes=st.session_state.meeting_length
                                    )
                                    try:
                                        calendar_utils.create_calendar_invite(
                                            task,
                                            start_dt.isoformat(),
                                            meeting_end_dt.isoformat(),
                                            title_template=event_title_template,
                                            description_template=event_description_template,
                                        )
                                        st.write(
                                            f"Created invite for task: {task['text']} from {start_dt} to {meeting_end_dt}"
                                        )
                                        task_index += 1
                                    except ValueError as e:
                                        st.error(f"Failed to create invite: {str(e)}")
                                        st.session_state.invites_sent = False
                                        break

                                start_dt += datetime.timedelta(
                                    minutes=st.session_state.meeting_length
                                )
                    else:
                        st.write("No available slots to create invites.")
        else:
            st.write("No tasks found.")


# Run the app
if __name__ == "__main__":
    main()
