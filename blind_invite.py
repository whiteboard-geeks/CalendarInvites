import streamlit as st
import requests
import base64


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

    # Step 1: User input for task search
    task_search = st.text_input("Enter task search string:")

    # Retrieve the Close API key from Streamlit secrets
    close_api_key = st.secrets["CLOSE_API_KEY"]

    if st.button("Search Tasks"):
        if task_search:
            tasks = search_tasks_in_close(task_search, close_api_key)
            if tasks:
                st.write(
                    f"Found {len(tasks)} lead(s) that have that task description to be completed:"
                )
                for task in tasks:
                    st.write(f"- {task['lead_name']}")

                # Show meeting length and leads per block inputs after tasks are found
                meeting_length = st.selectbox(
                    "Select meeting length:",
                    options=[10, 15, 20, 25, 30],
                    index=1,  # Default to 15 minutes
                )

                leads_per_block = st.number_input(
                    "Enter number of leads per block:",
                    min_value=1,
                    value=6,  # Default to 6 leads per block
                )

                st.write(f"Meeting length: {meeting_length} minutes")
                st.write(f"Leads per block: {leads_per_block}")
            else:
                st.write("No tasks found.")
        else:
            st.warning("Please enter a task search string.")


# Run the app
if __name__ == "__main__":
    main()
