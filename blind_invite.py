import streamlit as st
import requests


# Function to search tasks in Close CRM
def search_tasks_in_close(task_search, api_key):
    url = "https://api.close.com/api/v1/task/"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    params = {
        "_type": "lead",  # Assuming you want to search lead tasks
        "text__icontains": task_search,  # Filter tasks containing the search string
    }
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        return response.json().get("data", [])
    else:
        st.error("Failed to fetch tasks from Close CRM")
        return []


def main():
    st.title("Automated Calendar Invites")

    # Step 1: User input for task search
    task_search = st.text_input("Enter task search string:")

    # Retrieve the API key from Streamlit secrets
    api_key = st.secrets["close_api_key"]

    if st.button("Search Tasks"):
        if task_search:
            tasks = search_tasks_in_close(task_search, api_key)
            if tasks:
                st.write(f"Found {len(tasks)} tasks:")
                for task in tasks:
                    st.write(f"- {task['text']}")
            else:
                st.write("No tasks found.")
        else:
            st.warning("Please enter a task search string.")


# Run the app
if __name__ == "__main__":
    main()
