from datetime import datetime
import os
import requests
import base64

# Get Close.io API key from environment
api_key = os.getenv("CLOSE_API_KEY")
if not api_key:
    raise ValueError("CLOSE_API_KEY environment variable is not set")

# No need to decode since the API key should be provided in plain text
headers = {
    "Authorization": f"Basic {base64.b64encode(api_key.encode()).decode()}",
    "Content-Type": "application/json",
}

# List of lead IDs
lead_ids = [
    "lead_Lhqoxq3zAEdZKzGNPE6GuMW6V7mlMJlhQPU3R19vltp",  # BP - CT - GMT-6
    "lead_Z7wS8MX7wIcKcsgk6jgShfPYCyIpQct15sAAPtVYkFn",  # BP - PT - GMT-8
    "lead_NazuF7xufuyBEfxbSVj3Oy7O7XFUhuhKBbMw8gFnz0m",  # BP - MT - GMT-7
    "lead_Y3NyDeiRSY9HcgT7LqyrWzcvAuWrb0YQAeH6QQMqPrG",  # BP - ET - GMT-5
    "lead_CF7NLlmG3yircJjsRSzeOME2iXEY6W35Mam5gHNTdJ0",  # BP - ET - GMT-5
    "lead_Lcyyy03fdeMsBxMYQV0TxGMDPUYqryoS9zXsW6crB6O",  # BP - HI - GMT-10
    "lead_FcPBliF5o7VgaDA1q4odf6hqO3d22T7V9logAt8ysRj",  # BP - AK - GMT-9
    "lead_LdcRg9QQqqseacmFqyIDmPMZkoJhH7N8vtXwjKI5OLz",  # AL - ET - GMT-5
    "lead_ByjVODHgM5p87lxArQzB5JkkRvL833xhOsBdHXUxTc9",  # AL - CT - GMT-6
    "lead_rIPIKEA2jTrDfXxk6IKxnu0Rs72g17KQA1n1Lf41n6F",  # AL - MT - GMT-7
    "lead_EoogswUZmjMBbeAcdogZPvubHzd8mDlDveXUZ9Syp2q",  # AL - PT - GMT-8
    "lead_n2UE7lOoSumV9gHEwp5B06IBqArxsuDrunbc3GrLRqo",  # AL - AK - GMT-9
    "lead_ACHXiiNdBxTD1CrXpyCCmzCV0Gx5YBo00pAtbKvm89w",  # AL - HI - GMT-10
]

# Task details
task_text = "TEST Send Calendar Invitation: https://docs.google.com/document/d/1_LVxexavRHrOAM-h9ppsVVZZKQ31nvRULs9qoHv2Ti8/"


def check_task_exists(lead_id, task_text):
    try:
        # Get tasks for the lead
        response = requests.get(
            f"https://api.close.com/api/v1/task/?lead_id={lead_id}", headers=headers
        )
        response.raise_for_status()
        tasks = response.json()["data"]

        # Check if any task matches our text
        return any(
            task["text"] == task_text and task["is_complete"] is False for task in tasks
        )

    except requests.exceptions.RequestException as e:
        print(f"Error checking tasks for lead {lead_id}: {str(e)}")
        return False


def create_task_for_lead(lead_id):
    try:
        # First check if task already exists
        if check_task_exists(lead_id, task_text):
            print(f"Task already exists for lead {lead_id}")
            return False

        # Create task if it doesn't exist
        task_data = {
            "lead_id": lead_id,
            "text": task_text,
            "due_date": datetime.now().strftime("%Y-%m-%d"),  # Due today
            "is_complete": False,
        }

        response = requests.post(
            "https://api.close.com/api/v1/task/", headers=headers, json=task_data
        )
        response.raise_for_status()
        print(f"Created task for lead {lead_id}: {response.json()}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error creating task for lead {lead_id}: {str(e)}")
        return False


def main():
    print("Starting task creation process...")

    for lead_id in lead_ids:
        success = create_task_for_lead(lead_id)
        if success:
            print(f"Successfully created task for {lead_id}")
        else:
            print(f"Failed to create task for {lead_id}")

    print("Task creation process completed.")


if __name__ == "__main__":
    main()
