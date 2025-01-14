import streamlit as st
import requests
import base64
import calendar_utils


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


def main():
    st.title("Automated Calendar Invites")

    # Initialize session state for tasks and options
    if "tasks" not in st.session_state:
        st.session_state.tasks = []
    if "meeting_length" not in st.session_state:
        st.session_state.meeting_length = 15
    if "leads_per_block" not in st.session_state:
        st.session_state.leads_per_block = 6

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
            )

            st.session_state.leads_per_block = st.number_input(
                "Enter number of leads per block:",
                min_value=1,
                value=st.session_state.leads_per_block,
            )

            if st.button("Find Blind Invite Slots"):
                events = calendar_utils.find_blind_invite_events()
                if events:
                    st.write("Available 'Blind Invite' slots:")
                    for event in events:
                        start = event["start"].get(
                            "dateTime", event["start"].get("date")
                        )
                        st.write(f"- {event['summary']} at {start}")
                else:
                    st.write("No 'Blind Invite' slots found.")
        else:
            st.write("No tasks found.")


# Run the app
if __name__ == "__main__":
    main()
