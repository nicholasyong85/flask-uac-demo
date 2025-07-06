from flask import Flask, request, jsonify
import openai
import requests
import os

app = Flask(__name__)

# Set these environment variables on Render
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
UAC_API_TOKEN = os.environ.get("UAC_API_TOKEN")
UAC_API_URL = os.environ.get("UAC_API_URL")  # e.g. https://uac.mycompany.com/api/workflow/launch
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
JIRA_USER_EMAIL = os.environ.get("JIRA_USER_EMAIL")
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL")  # e.g. https://yourcompany.atlassian.net

# A sample mapping of workflows that GPT will select from
AVAILABLE_WORKFLOWS = {
    "IT - Singapore": "Onboarding_IT_SG",
    "HR - Malaysia": "Onboarding_HR_MY",
    "Finance - Remote": "Onboarding_Fin_Remote"
}

# Use ChatGPT to choose the right UAC workflow
def get_workflow_from_gpt(ticket_data):
    prompt = f"""
You are a decision engine. Based on the following onboarding ticket fields, choose the best matching workflow from this list:
{list(AVAILABLE_WORKFLOWS.values())}

Ticket Data:
Department: {ticket_data.get('department')}
Location: {ticket_data.get('location')}
Role: {ticket_data.get('role')}
Team: {ticket_data.get('team')}

Respond with ONLY the workflow name.
"""
    response = openai.ChatCompletion.create(
        model="gpt-4",
        api_key=OPENAI_API_KEY,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()

# Call UAC to launch the chosen workflow
def trigger_uac_workflow(workflow_name, ticket_data):
    headers = {"Authorization": f"Bearer {UAC_API_TOKEN}"}
    payload = {
        "workflow_name": workflow_name,
        "variables": {
            "username": ticket_data.get("username"),
            "location": ticket_data.get("location")
        }
    }
    response = requests.post(UAC_API_URL, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

# Add a comment and optionally close the Jira ticket
def comment_and_close_jira_ticket(ticket_key, workflow_name):
    headers = {
        "Authorization": f"Basic {JIRA_USER_EMAIL}:{JIRA_API_TOKEN}",
        "Content-Type": "application/json"
    }
    auth = (JIRA_USER_EMAIL, JIRA_API_TOKEN)

    # Comment on ticket
    comment_url = f"{JIRA_BASE_URL}/rest/api/3/issue/{ticket_key}/comment"
    comment_payload = {
        "body": f"ChatGPT selected the workflow `{workflow_name}` and it has been triggered in Stonebranch UAC."
    }
    requests.post(comment_url, json=comment_payload, auth=auth, headers=headers)

    # Transition to Done (Assumes transition ID 31 is “Done” – you may need to confirm this)
    transition_url = f"{JIRA_BASE_URL}/rest/api/3/issue/{ticket_key}/transitions"
    transition_payload = {"transition": {"id": "31"}}
    requests.post(transition_url, json=transition_payload, auth=auth, headers=headers)

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        ticket_key = data.get("key") or data.get("issue", {}).get("key")
        fields = data.get("fields") or data.get("issue", {}).get("fields", {})
        
        # Prepare simplified input for ChatGPT
        ticket_data = {
            "department": fields.get("department", {}).get("value", "Unknown"),
            "location": fields.get("location", {}).get("value", "Unknown"),
            "role": fields.get("customfield_role", "Analyst"),
            "team": fields.get("customfield_team", "N/A"),
            "username": fields.get("customfield_username", "unknown.user")
        }

        workflow = get_workflow_from_gpt(ticket_data)
        uac_response = trigger_uac_workflow(workflow, ticket_data)
        comment_and_close_jira_ticket(ticket_key, workflow)

        return jsonify({
            "status": "success",
            "workflow_triggered": workflow,
            "uac_response": uac_response
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
