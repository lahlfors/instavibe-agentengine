import os
import json
import logging
import asyncio
from typing import Dict, Any, Generator, Optional
import nest_asyncio
import httpx
import google.auth
from google.auth.transport.requests import Request

# Apply nest_asyncio to allow nested event loops (critical for Streamlit/sync environments)
nest_asyncio.apply()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Structured request template for reliable agent interaction
PLANNING_REQUEST_TEMPLATE = """CREATE EVENT PLAN

USER_NAME: {user_name}
FRIENDS: {friends_list}
DATE: {planned_date}
LOCATION: {location}

Generate a complete JSON event plan with this exact structure:
{{
  "event_name": "Brief catchy name",
  "event_description": "2-3 sentence overview",
  "friends_name_list": ["Friend1", "Friend2"],
  "locations_and_activities": [
    {{
      "name": "Venue name",
      "address": "Full address",
      "latitude": 42.360082,
      "longitude": -71.058880,
      "description": "Description"
    }}
  ],
  "post_to_go_out": "Casual invite message"
}}
"""

# --- Configuration ---
# Use the Cloud Run URL for the Orchestrate Agent
ORCHESTRATE_AGENT_URL = os.getenv("ORCHESTRATE_AGENT_URL") or os.getenv("SERVICE_URL") # Fallback for local testing
if not ORCHESTRATE_AGENT_URL:
    # Default to a placeholder if not set, will be updated by init_agent_engine
    ORCHESTRATE_AGENT_URL = "https://orchestrate-agent-placeholder.run.app"

def get_id_token(target_audience):
    """
    Fetches an ID token for the given target audience (Cloud Run URL).
    """
    try:
        import google.oauth2.id_token
        import google.auth.transport.requests
        
        if not target_audience:
            logger.warning("No target audience provided for ID token.")
            return None
        
        auth_req = google.auth.transport.requests.Request()
        token = google.oauth2.id_token.fetch_id_token(auth_req, target_audience)
        return token
    except Exception as e:
        logger.warning(f"Failed to fetch ID token: {e}. Using default credentials or skipping auth.")
        return None

def call_agent_for_plan(user_name, planned_date, location_n_perference, selected_friend_names_list):
    """
    Calls the Orchestrate Agent via HTTP /chat endpoint to generate a plan.
    """
    user_id = str(user_name)
    accumulated_json_str = ""
    
    yield {"type": "thought", "data": f"--- IntrovertAlly Agent Call Initiated (HTTP) ---"}
    
    # Prepare Prompt
    selected_friend_names_str = ', '.join(selected_friend_names_list)
    prompt = PLANNING_REQUEST_TEMPLATE.format(
        user_name=user_name,
        friends_list=selected_friend_names_str,
        planned_date=planned_date,
        location=location_n_perference
    )

    logger.info(f"Sending prompt to Orchestrate Agent: {prompt[:100]}...")
    
    # Determine URL
    agent_url = os.getenv("ORCHESTRATE_AGENT_URL")
    if not agent_url:
        yield {"type": "error", "data": {"message": "ORCHESTRATE_AGENT_URL not set."}}
        return
        
    chat_url = f"{agent_url}/chat"
    
    # Get Auth Token
    token = get_id_token(agent_url)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        # Use httpx for streaming request
        # We need to run this synchronously since this is a sync generator
        with httpx.Client(timeout=120.0) as client:
            with client.stream("POST", chat_url, json={"prompt": prompt}, headers=headers) as response:
                if response.status_code != 200:
                    error_text = response.read().decode()
                    logger.error(f"Agent returned error {response.status_code}: {error_text}")
                    yield {"type": "error", "data": {"message": f"Agent Error {response.status_code}: {error_text}"}}
                    return

                for chunk in response.iter_text():
                    if chunk:
                        yield {"type": "thought", "data": f"Orchestrator: \"{chunk}\""}
                        accumulated_json_str += chunk
        
        yield {"type": "thought", "data": f"--- Stream Complete ---"}

    except Exception as e:
        logger.error(f"Critical error during agent query: {e}", exc_info=True)
        yield {"type": "error", "data": {"message": f"Agent query failed: {str(e)}"}}
        return

    # Parse JSON
    if accumulated_json_str:
        try:
            # Clean up potential markdown code blocks
            cleaned_json = accumulated_json_str.strip()
            
            # Robust JSON extraction: find the first '{' and the last '}'
            start_idx = cleaned_json.find('{')
            end_idx = cleaned_json.rfind('}')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                cleaned_json = cleaned_json[start_idx:end_idx+1]
                logger.info(f"Extracted JSON substring: {cleaned_json[:50]}...{cleaned_json[-20:]}")
                final_result_json = json.loads(cleaned_json)
                yield {"type": "plan_complete", "data": final_result_json}
            else:
                # Fallback to original logic if no braces found (unlikely for valid JSON)
                logger.warning("Could not find JSON braces, attempting raw parse")
                if cleaned_json.startswith("```json"):
                    cleaned_json = cleaned_json[7:]
                if cleaned_json.startswith("```"):
                    cleaned_json = cleaned_json[3:]
                if cleaned_json.endswith("```"):
                    cleaned_json = cleaned_json[:-3]
                
                final_result_json = json.loads(cleaned_json.strip())
                yield {"type": "plan_complete", "data": final_result_json}
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parse Error: {e}. Raw output: {accumulated_json_str}")
            yield {"type": "error", "data": {"message": f"JSON parsing error: {e}", "raw_output": accumulated_json_str}}
    else:
        yield {"type": "error", "data": {"message": "Agent returned no content.", "raw_output": ""}}


def post_plan_event(user_name, confirmed_plan, edited_invite_message, agent_session_user_id):
    """
    Simulates an agent posting an event via HTTP /chat endpoint.
    """
    yield {"type": "thought", "data": f"--- Post Plan Event Agent Call Initiated ---"}
    
    prompt_message = f"""
    You are an Orchestrator assistant. User '{user_name}' wants to finalize this plan:
    {json.dumps(confirmed_plan)}
    
    Invite Message: "{edited_invite_message}"
    
    Please post this to the platform.
    """
    
    accumulated_response_text = ""
    
    # Determine URL
    agent_url = os.getenv("ORCHESTRATE_AGENT_URL")
    if not agent_url:
        yield {"type": "error", "data": {"message": "ORCHESTRATE_AGENT_URL not set."}}
        return
        
    chat_url = f"{agent_url}/chat"
    
    # Get Auth Token
    token = get_id_token(agent_url)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    try:
        with httpx.Client(timeout=120.0) as client:
            with client.stream("POST", chat_url, json={"prompt": prompt_message}, headers=headers) as response:
                if response.status_code != 200:
                    error_text = response.read().decode()
                    logger.error(f"Agent returned error {response.status_code}: {error_text}")
                    yield {"type": "error", "data": {"message": f"Agent Error {response.status_code}: {error_text}"}}
                    return

                for chunk in response.iter_text():
                    if chunk:
                        yield {"type": "thought", "data": f"Orchestrator: \"{chunk}\""}
                        accumulated_response_text += chunk
                        
    except Exception as e:
        logger.error(f"Error during posting: {e}", exc_info=True)
        yield {"type": "error", "data": {"message": f"Error during posting: {str(e)}"}}
        return

    yield {"type": "posting_finished", "data": {"success": True, "message": "Posting complete."}}
