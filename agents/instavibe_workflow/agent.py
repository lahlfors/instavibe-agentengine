# Instavibe Workflow Agent - agent.py
import os
import json
import logging
from vertexai.preview.generative_models import GenerativeModel, Part
from vertexai.preview import reasoning_engines

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the Vertex AI SDK once
try:
    PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
    LOCATION = os.environ.get("COMMON_GOOGLE_CLOUD_LOCATION") # Matching env var from introvertally
    if not PROJECT_ID or not LOCATION:
        raise ValueError("GOOGLE_CLOUD_PROJECT and COMMON_GOOGLE_CLOUD_LOCATION environment variables must be set.")
    reasoning_engines.init(project=PROJECT_ID, location=LOCATION)
    logger.info(f"Vertex AI SDK initialized for project {PROJECT_ID} in {LOCATION}")
except Exception as e:
    logger.error(f"Failed to initialize Vertex AI SDK: {e}", exc_info=True)
    # Depending on deployment, this might be a fatal error.
    # For now, we log and let it proceed; calls will fail later.

class InstavibeWorkflowAgent:
    """
    Agent to handle Instavibe workflows like plan generation and event posting.
    This agent is designed to be called by an HTTP entrypoint (e.g., Flask app in main.py),
    which will manage the ADK session.
    """

    def __init__(self, model_name="gemini-1.0-pro"): # Changed to a valid model name
        try:
            self.model = GenerativeModel(model_name)
            logger.info(f"GenerativeModel '{model_name}' initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize GenerativeModel '{model_name}': {e}", exc_info=True)
            self.model = None # Ensure model is None if initialization fails

    def _generate_event_plan(self, user_name, planned_date, location_n_perference, selected_friend_names_list, adk_session=None):
        """
        Generates an event plan using the LLM.
        adk_session is passed for context but not directly used by GenerativeModel in this simplified setup.
        If this were a true ADK Agent, adk_session would be used by agent.run() or agent.stream().
        """
        thoughts = []
        if not self.model:
            thoughts.append("Model not initialized. Cannot generate plan.")
            return None, thoughts

        friends_list_example_for_prompt = json.dumps(selected_friend_names_list)
        selected_friend_names_str = ', '.join(selected_friend_names_list)

        prompt_message = f"""Plan a personalized night out for {user_name} with friends {selected_friend_names_str} on {planned_date}, with the location or preference being "{location_n_perference}".

Analyze friend interests (if possible, use Instavibe profiles or summarized interests) to create a tailored plan. Ensure the plan includes the date {planned_date}.

Output the entire plan in a SINGLE, COMPLETE JSON object with the following structure. **CRITICAL: The FINAL RESPONSE MUST BE ONLY THIS JSON. If any fields are missing or unavailable, INVENT them appropriately to complete the JSON structure. Do not return any conversational text or explanations. Just the raw, valid JSON.**

{{
  "friends_name_list": {friends_list_example_for_prompt},
  "event_name": "string",
  "event_date": "{planned_date}",
  "event_description": "string",
  "locations_and_activities": [
    {{
      "name": "string",
      "latitude": 12.345,
      "longitude": -67.890,
      "address": "string or null",
      "description": "string"
    }}
  ],
  "post_to_go_out": "string"
}}
"""
        thoughts.append(f"Generating event plan with prompt: {prompt_message[:200]}...")
        logger.info(f"Sending planning prompt to LLM for user '{user_name}'.")

        try:
            # In a true ADK Agent setup, this would be:
            # response = adk_agent_object.run(message=prompt_message, session=adk_session)
            # For now, directly using the GenerativeModel:
            response = self.model.generate_content(prompt_message)

            # Extract text, handling potential variations in response structure
            if hasattr(response, 'text'):
                generated_text = response.text
            elif hasattr(response, 'candidates') and response.candidates and \
                 hasattr(response.candidates[0], 'content') and hasattr(response.candidates[0].content, 'parts') and \
                 response.candidates[0].content.parts and hasattr(response.candidates[0].content.parts[0], 'text'):
                generated_text = response.candidates[0].content.parts[0].text
            else:
                generated_text = str(response) # Fallback
                thoughts.append(f"Warning: Could not extract text directly from response. Full response: {generated_text[:200]}")

            thoughts.append(f"LLM raw response for plan: {generated_text[:200]}...")
            logger.info(f"LLM raw response for plan (user '{user_name}'): {generated_text[:200]}...")

            # Attempt to parse the JSON from the response
            # Remove markdown code block if present
            if "```json" in generated_text:
                json_block = generated_text.split("```json", 1)[1].rsplit("```", 1)[0].strip()
                thoughts.append("Extracted JSON from markdown block.")
            elif "```" in generated_text and generated_text.strip().startswith("{") and generated_text.strip().endswith("}"): # Simpler JSON in backticks
                json_block = generated_text.strip().strip('`').strip()
                thoughts.append("Extracted JSON from simple backticks.")
            else:
                json_block = generated_text.strip()

            plan_json = json.loads(json_block)
            thoughts.append("Successfully parsed plan JSON.")
            return plan_json, thoughts
        except json.JSONDecodeError as e:
            thoughts.append(f"JSONDecodeError: {str(e)}. Raw text: {generated_text}")
            logger.error(f"JSONDecodeError for plan (user '{user_name}'): {str(e)}. Raw text: {generated_text}", exc_info=True)
            return None, thoughts
        except Exception as e:
            thoughts.append(f"Error generating plan: {str(e)}")
            logger.error(f"Error generating plan (user '{user_name}'): {str(e)}", exc_info=True)
            return None, thoughts

    def _process_event_posting(self, user_name, confirmed_plan, edited_invite_message, agent_session_user_id, adk_session=None):
        """
        Processes the event posting request using the LLM.
        This simulates instructing another agent or system.
        adk_session is passed for context.
        """
        thoughts = []
        if not self.model:
            thoughts.append("Model not initialized. Cannot process event posting.")
            return False, "Model not initialized.", thoughts

        prompt_message = f"""
You are an Orchestrator assistant for the Instavibe platform. User '{user_name}' (User ID for this interaction: '{agent_session_user_id}') has finalized an event plan and wants to:
1. Create the event on Instavibe.
2. Create an invite post for this event on Instavibe.

You have tools like `list_remote_agents` to discover available specialized agents and `send_task(agent_name: str, message: str)` to delegate tasks to them.
Your primary role is to understand the user's overall goal, identify the necessary steps, select the most appropriate remote agent(s) for those steps, and then send them clear instructions.

Confirmed Plan:
```json
{json.dumps(confirmed_plan, indent=2)}
```

Invite Message (this is the exact text for the post content):
"{edited_invite_message}"

Your explicit tasks are, in this exact order:

TASK 1: Create the Event on Instavibe.
- First, identify a suitable remote agent that is capable of creating events on the Instavibe platform. You should use your `list_remote_agents` tool if you need to refresh your knowledge of available agents and their capabilities.
- Once you have selected an appropriate agent, you MUST use your tool to instruct that agent to create the event.
- The `message` you send to the agent for this task should be a clear, natural language instruction. This message MUST include all necessary details for event creation, derived from the "Confirmed Plan" JSON:
    - Event Name: "{confirmed_plan.get('event_name', 'Unnamed Event')}"
    - Event Description: "{confirmed_plan.get('event_description', 'No description provided.')}"
    - Event Date: "{confirmed_plan.get('event_date', 'MISSING_EVENT_DATE_IN_PLAN')}" (ensure this is in a standard date/time format like ISO 8601)
    - Locations: {json.dumps(confirmed_plan.get('locations_and_activities', []))} (describe these locations clearly to the agent)
    - Attendees: {json.dumps(list(set(confirmed_plan.get('friends_name_list', []) + [user_name])))} (this list includes the user '{user_name}' and their friends)
- Narrate your thought process: which agent you are selecting (or your criteria if you can't name it), and the natural language message you are formulating for the tool to create the event.
- After the tool call is complete, briefly acknowledge its success based on the tool's response.

TASK 2: Create the Invite Post on Instavibe.
- Only after TASK 1 (event creation) is confirmed as successful, you MUST use your tool again.
- The `message` you send to the agent for this task should be a clear, natural language instruction to create a post. This message MUST include:
    - The author of the post: "{user_name}"
    - The content of the post: The "Invite Message" provided above ("{edited_invite_message}")
    - An instruction to associate this post with the event created in TASK 1 (e.g., by referencing its name: "{confirmed_plan.get('event_name', 'Unnamed Event')}")
    - Indicate the sentiment is "positive" as it's an invitation.
- Narrate the natural language message you are formulating for the `send_task` tool to create the post.
- After the `send_task` tool call is (simulated as) complete, briefly acknowledge its success.

IMPORTANT INSTRUCTIONS FOR YOUR BEHAVIOR:
- Your primary role here is to orchestrate these two actions by selecting an appropriate remote agent and sending it clear, natural language instructions via your tool.
- Your responses during this process should be a stream of consciousness, primarily narrating your agent selection (if applicable), the formulation of your natural language messages for, and their outcomes.
- Do NOT output any JSON yourself. Your output must be plain text only, describing your actions.
- Conclude with a single, friendly success message confirming that you have (simulated) instructing the remote agent to create both the event and the post. For example: "Alright, I've instructed the appropriate Instavibe agent to create the event '{confirmed_plan.get('event_name', 'Unnamed Event')}' and to make the invite post for {user_name}!"
"""
        thoughts.append(f"Processing event posting with prompt: {prompt_message[:200]}...")
        logger.info(f"Sending posting prompt to LLM for user '{user_name}'.")

        try:
            # In a true ADK Agent setup with tools, this would be more complex,
            # involving agent.stream() and handling tool calls.
            # For now, we simulate by getting a text response.
            response = self.model.generate_content(prompt_message)

            if hasattr(response, 'text'):
                generated_text = response.text
            elif hasattr(response, 'candidates') and response.candidates and \
                 hasattr(response.candidates[0], 'content') and hasattr(response.candidates[0].content, 'parts') and \
                 response.candidates[0].content.parts and hasattr(response.candidates[0].content.parts[0], 'text'):
                generated_text = response.candidates[0].content.parts[0].text
            else:
                generated_text = str(response) # Fallback
                thoughts.append(f"Warning: Could not extract text directly from response. Full response: {generated_text[:200]}")


            thoughts.append(f"LLM raw response for posting: {generated_text[:200]}...")
            logger.info(f"LLM raw response for posting (user '{user_name}'): {generated_text[:200]}...")

            # The expected output is a confirmation message.
            # We assume success if we get any non-empty text response.
            if generated_text and generated_text.strip():
                thoughts.append("Successfully processed posting instructions (simulated).")
                # We return the LLM's narration as the "message"
                return True, generated_text.strip(), thoughts
            else:
                thoughts.append("LLM returned empty response for posting.")
                return False, "LLM returned empty response.", thoughts

        except Exception as e:
            thoughts.append(f"Error processing event posting: {str(e)}")
            logger.error(f"Error processing event posting (user '{user_name}'): {str(e)}", exc_info=True)
            return False, str(e), thoughts

    def run(self, action: str, payload: dict, adk_session=None):
        """
        Main execution method for the agent.
        Determines the action and calls the appropriate internal method.
        `adk_session` is passed from the entrypoint (main.py).
        """
        logger.info(f"Workflow agent received action: '{action}' with payload: {payload.get('user_name', 'Unknown User')}")

        if not self.model:
            logger.error("Workflow agent cannot run: Model not initialized.")
            return {
                "success": False,
                "error": "Model not initialized in workflow agent.",
                "thoughts": ["Attempted to run workflow, but model is not available."]
            }

        if action == "generate_plan":
            user_name = payload.get("user_name")
            planned_date = payload.get("planned_date")
            location_n_perference = payload.get("location_n_perference")
            selected_friend_names_list = payload.get("selected_friend_names_list", [])

            if not all([user_name, planned_date, location_n_perference]):
                return {"success": False, "error": "Missing required fields for generate_plan", "thoughts": ["Validation failed for generate_plan payload."]}

            plan_json, thoughts = self._generate_event_plan(
                user_name, planned_date, location_n_perference, selected_friend_names_list, adk_session
            )
            if plan_json:
                return {"success": True, "result_type": "plan", "data": plan_json, "thoughts": thoughts}
            else:
                return {"success": False, "error": "Failed to generate plan.", "thoughts": thoughts}

        elif action == "post_event":
            user_name = payload.get("user_name")
            confirmed_plan = payload.get("confirmed_plan")
            edited_invite_message = payload.get("edited_invite_message")
            agent_session_user_id = payload.get("agent_session_user_id", user_name) # Fallback for user_id context

            if not all([user_name, confirmed_plan, edited_invite_message]):
                return {"success": False, "error": "Missing required fields for post_event", "thoughts": ["Validation failed for post_event payload."]}

            success, message, thoughts = self._process_event_posting(
                user_name, confirmed_plan, edited_invite_message, agent_session_user_id, adk_session
            )
            if success:
                return {"success": True, "result_type": "post_confirmation", "message": message, "thoughts": thoughts}
            else:
                return {"success": False, "error": f"Failed to process event posting: {message}", "thoughts": thoughts}

        else:
            logger.warning(f"Unknown action received: {action}")
            return {"success": False, "error": f"Unknown action: {action}", "thoughts": [f"Action '{action}' is not supported."]}

# Example of how this might be initialized by main.py
# if __name__ == '__main__':
#     # This is for local testing/dev; main.py will handle instantiation in deployment
#     # Ensure GOOGLE_CLOUD_PROJECT and COMMON_GOOGLE_CLOUD_LOCATION are set as env vars

#     # Test plan generation
#     workflow_agent_instance = InstavibeWorkflowAgent()
#     if workflow_agent_instance.model: # Proceed only if model initialized
#         plan_payload = {
#             "user_name": "TestUser",
#             "planned_date": "2023-12-01",
#             "location_n_perference": "A cozy cafe",
#             "selected_friend_names_list": ["FriendA", "FriendB"]
#         }
#         plan_result = workflow_agent_instance.run(action="generate_plan", payload=plan_payload)
#         logger.info(f"Plan generation result: {json.dumps(plan_result, indent=2)}")

#         # Test event posting (assuming a plan was generated)
#         if plan_result["success"]:
#             post_payload = {
#                 "user_name": "TestUser",
#                 "confirmed_plan": plan_result["data"],
#                 "edited_invite_message": "Let's go!",
#                 "agent_session_user_id": "TestUser"
#             }
#             post_result = workflow_agent_instance.run(action="post_event", payload=post_payload)
#             logger.info(f"Event posting result: {json.dumps(post_result, indent=2)}")
#     else:
#         logger.error("Cannot run test: InstavibeWorkflowAgent model not initialized.")
