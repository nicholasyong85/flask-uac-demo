from flask import Flask, request, jsonify
import requests
import os
from openai import OpenAI

app = Flask(__name__)

# Set these environment variables in Render
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
UAC_API_TOKEN = os.environ.get("UAC_API_TOKEN")
UAC_API_URL = os.environ.get("UAC_API_URL")  # e.g. https://uac.mycompany.com/api/workflow/launch
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
JIRA_USER_EMAIL = os.environ.get("JIRA_USER_EMAIL")
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL")  # e.g. https://yourcompany.atlassian.net
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "mistralai/mistral-7b-instruct")  # Optional override

# Connect to OpenRouter API
client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

# Available onboarding workflows
AVAILABLE_WORKFLOWS = {
    "IT - Singapore": "Onboarding_IT_SG",
    "HR - Malaysia": "Onboarding_HR_MY",
    "Finance - Remote": "Onboarding_Fin_Remote"
}

def get_workflow_from_gpt(ticket_data):
    prompt = f"""
You are a decision engine. Based on the following onboarding ticket fields, choose the best matching workflow from this list:
{list(AVAILABLE_WORKFLOWS.values())}

Ticket Data:
First Name: {ticket_data.get('first_name')}
Last Name: {ticket_data.get('last_name')}
Email: {ticket_data.get('email')}
Department: {ticket_data.get('department')}
Location: {ticket_data.get('location')}
Job Title: {ticket_data.get('job_title')}

Respond with ONLY the workflow name.
"""
    response = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

def trigger_uac_workflow(workflow_name, ticket_data):
    headers = {"Authorization": f"Bearer {UAC_API_TOKEN}"}
    payload = {
        "workflow_name": workflow_name,
        "variables": {
            "first_name": ticket_data.get("first_name"),
            "last_name": ticket_data.get("last_name"),
            "email": ticket_data.get("email"),
            "department": ticket_data.get("department"),
            "location": ticket_data.get("location"),
            "job_title": ticket_data.get("job_title")
        }
    }
    response = requests.post(UAC_API_URL, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def comment_and_close_jira_ticket(ticket_key, workflow_name):
    auth = (JIRA_USER_EMAIL, JIRA_API_TOKEN)
    headers = {"Content-Type": "application/json"}

    comment_url = f"{JIRA_BASE_URL}/rest/api/3/issue/{ticket_key}/comment"
    comment_payload = {
        "body": f"ChatGPT selected the workflow `{workflow_name}` and it has been triggered in Stonebranch UAC."
    }
    requests.post(comment_url, json=comment_payload, auth=auth, headers=headers)

    transition_url = f"{JIRA_BASE_URL}/rest/api/3/issue/{ticket_key}/transitions"
    transition_payload = {"transition": {"id": "31"}}  # Adjust this to your Jira transition ID
    requests.post(transition_url, json=transition_payload, auth=auth, headers=headers)

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json

        ticket_data = {
            "ticket_id": data.get("ticket_id"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "email": data.get("email"),
            "department": data.get("department"),
            "location": data.get("location"),
            "job_title": data.get("job_title")
        }

        workflow = get_workflow_from_gpt(ticket_data)
        uac_response = trigger_uac_workflow(workflow, ticket_data)
        comment_and_close_jira_ticket(ticket_data["ticket_id"], workflow)

        return jsonify({
            "status": "success",
            "workflow_triggered": workflow,
            "uac_response": uac_response
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
