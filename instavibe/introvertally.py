#from dotenv import load_dotenv
#load_dotenv() # Ensure this is at the very top

import os
import pprint
import json 
import logging # Added for logging

import google.cloud.aiplatform as vertexai
from google.cloud.aiplatform_v1.services.reasoning_engine_service import ReasoningEngineServiceClient
from vertexai.preview import reasoning_engines # Added for direct RE instantiation
# from vertexai import agent_engines # This is available via vertexai.agent_engines

# google.cloud.aiplatform is already imported as vertexai

# Initialize logger
logger = logging.getLogger(__name__)

# Global variable for the ADK app instance
adk_app = None

def init_agent_engine(project_id, location):
    """Initializes the Vertex AI ADK Application."""
    global adk_app
    logger.info("Attempting to initialize ADK App...")

    try:
        logger.info(f"Initializing Vertex AI with project: {project_id}, location: {location}")
        vertexai.init(project=project_id, location=location)
    except Exception as e:
        logger.error(f"Failed to initialize Vertex AI: {e}", exc_info=True)
        adk_app = None
        logger.warning("ADK App is None due to Vertex AI initialization failure.")
        return

    planner_resource_name_from_env = os.getenv("AGENTS_PLANNER_RESOURCE_NAME")

    if not planner_resource_name_from_env:
        logger.error("AGENTS_PLANNER_RESOURCE_NAME environment variable not set. Cannot initialize ADK App.")
        adk_app = None
        return

    try:
        logger.info(f"Attempting to get ADK App with resource name: {planner_resource_name_from_env}")
        # Ensure vertexai.agent_engines is the correct module path
        # Based on documentation, it should be vertexai.agent_engines
        # If it's reasoning_engines for get, we might need to adjust
        # For now, assuming vertexai.agent_engines as per typical ADK usage for deployed agents
        from vertexai import agent_engines # Ensure this is imported
        adk_app = agent_engines.get(planner_resource_name_from_env)
        logger.info(f"Successfully connected to ADK App using resource name: {planner_resource_name_from_env}")
    except Exception as e:
        logger.error(f"Failed to get ADK App using resource name '{planner_resource_name_from_env}': {e}", exc_info=True)
        adk_app = None

    if adk_app is None:
        logger.warning("ADK App is None after initialization attempts.")
    else:
        logger.info("ADK App initialized successfully.")


# Initialize the agent engine on module load
COMMON_GOOGLE_CLOUD_PROJECT = os.getenv("COMMON_GOOGLE_CLOUD_PROJECT")
COMMON_GOOGLE_CLOUD_LOCATION = os.getenv("COMMON_GOOGLE_CLOUD_LOCATION")

if COMMON_GOOGLE_CLOUD_PROJECT and COMMON_GOOGLE_CLOUD_LOCATION:
    logger.info(f"Attempting to initialize ADK App for project {COMMON_GOOGLE_CLOUD_PROJECT} in {COMMON_GOOGLE_CLOUD_LOCATION}")
    init_agent_engine(COMMON_GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION)
else:
    logger.error("COMMON_GOOGLE_CLOUD_PROJECT or COMMON_GOOGLE_CLOUD_LOCATION environment variables not set. ADK App will not be initialized.")


def call_agent_for_plan(user_name, planned_date, location_n_perference, selected_friend_names_list):
    user_id = str(user_name) # ADK uses user_id for session management
    session_id = None # Will be set after creating a session

    yield {"type": "thought", "data": f"--- IntrovertAlly Agent Call Initiated (ADK) ---"}
    yield {"type": "thought", "data": f"User ID for this run: {user_id}"}
    yield {"type": "thought", "data": f"User: {user_name}"}
    yield {"type": "thought", "data": f"Planned Date: {planned_date}"}
    yield {"type": "thought", "data": f"Location/Preference: {location_n_perference}"}
    yield {"type": "thought", "data": f"Selected Friends: {', '.join(selected_friend_names_list)}"}
    yield {"type": "thought", "data": f"Initiating plan for {user_name} on {planned_date} regarding '{location_n_perference}' with friends: {', '.join(selected_friend_names_list)}."}

    selected_friend_names_str = ', '.join(selected_friend_names_list)
    friends_list_example_for_prompt = json.dumps(selected_friend_names_list)

    prompt_message = f"""Plan a personalized night out for {user_name} with friends {selected_friend_names_str} on {planned_date}, with the location or preference being "{location_n_perference}".

    Analyze friend interests (if possible, use Instavibe profiles or summarized interests) to create a tailored plan.  Ensure the plan includes the date {planned_date}.

    Output the entire plan in a SINGLE, COMPLETE JSON object with the following structure.  **CRITICAL: The FINAL RESPONSE MUST BE ONLY THIS JSON.  If any fields are missing or unavailable, INVENT them appropriately to complete the JSON structure.  Do not return any conversational text or explanations.  Just the raw, valid JSON.**

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

    logger.info(f"--- Sending Prompt to ADK App for user {user_id} ---")
    logger.debug(prompt_message)
    yield {"type": "thought", "data": f"Sending detailed planning prompt to ADK App for {user_name}'s event."}

    accumulated_json_str = ""

    try:
        if not adk_app:
            logger.error("ADK App is not initialized. Cannot query for plan.")
            yield {"type": "error", "data": {"message": "ADK App not initialized. Cannot query for plan.", "raw_output": ""}}
            return

        # Create a session
        try:
            logger.info(f"Creating session for user_id: {user_id}")
            session = adk_app.create_session(user_id=user_id)
            session_id = session.session_id # Assuming session object has session_id attribute
            yield {"type": "thought", "data": f"Session created: {session_id} for user {user_id}"}
            logger.info(f"Session {session_id} created for user {user_id}")
        except Exception as e_session_create:
            logger.error(f"Error creating session for user {user_id}: {e_session_create}", exc_info=True)
            yield {"type": "error", "data": {"message": f"Error creating session: {str(e_session_create)}", "raw_output": ""}}
            return

        yield {"type": "thought", "data": f"--- ADK App Response Stream Starting (session: {session_id}) ---"}

        stream_iterator = adk_app.stream_query(
            user_id=user_id,
            session_id=session_id,
            message=prompt_message
        )

        for chunk_idx, chunk in enumerate(stream_iterator):
            # logger.debug(f"Stream Chunk {chunk_idx} (user: {user_id}, session: {session_id}): {chunk}")
            # pprint.pprint(chunk) # Keep for debugging if necessary, but can be verbose

            text_to_accumulate = None
            # ADK stream_query might yield objects with different structures.
            # Common ADK event types include 'thought', 'tool_code', 'tool_result', 'response'.
            # We are primarily interested in the 'response' for accumulating the final JSON.
            # Other event types can be logged as 'thoughts'.

            if hasattr(chunk, 'response'): # Standard way to get LLM response text
                text_to_accumulate = chunk.response
                yield {"type": "thought", "data": f"ADK App (response content): \"{text_to_accumulate}\""}
            elif hasattr(chunk, 'thought'):
                 yield {"type": "thought", "data": f"ADK App (thought): \"{chunk.thought}\""}
            elif hasattr(chunk, 'tool_code'):
                 yield {"type": "thought", "data": f"ADK App (tool_code): \"{chunk.tool_code}\""}
            elif hasattr(chunk, 'tool_result'):
                 yield {"type": "thought", "data": f"ADK App (tool_result for {chunk.tool_name if hasattr(chunk, 'tool_name') else 'unknown tool'}): \"{chunk.tool_result}\""}
            elif isinstance(chunk, str): # Fallback if it's just a string
                text_to_accumulate = chunk
                yield {"type": "thought", "data": f"ADK App (string chunk): \"{text_to_accumulate}\""}
            else: # If structure is unknown, log it
                unknown_chunk_str = str(chunk)
                logger.warning(f"Received chunk of unexpected type/structure {type(chunk)} from ADK App stream_query (user: {user_id}, session: {session_id}): {unknown_chunk_str}")
                yield {"type": "thought", "data": f"ADK App (unknown chunk type {type(chunk)}): {unknown_chunk_str}"}

            if text_to_accumulate:
                accumulated_json_str += text_to_accumulate

        yield {"type": "thought", "data": f"--- End of ADK App Response Stream (session: {session_id}) ---"}

    except Exception as e_outer:
        logger.error(f"Error during ADK App interaction for user {user_id} (session: {session_id}): {e_outer}", exc_info=True)
        yield {"type": "thought", "data": f"Critical error during ADK App stream_query or iteration (session: {session_id}): {str(e_outer)}"}
        yield {"type": "error", "data": {"message": f"Error during ADK App interaction: {str(e_outer)}", "raw_output": accumulated_json_str}}
        # Ensure session is deleted even if an error occurs mid-stream
        if adk_app and session_id and user_id:
            try:
                logger.info(f"Attempting to delete session {session_id} for user {user_id} due to error.")
                adk_app.delete_session(user_id=user_id, session_id=session_id)
                yield {"type": "thought", "data": f"Session {session_id} deleted for user {user_id} after error."}
                logger.info(f"Session {session_id} for user {user_id} deleted after error.")
            except Exception as e_del_err:
                logger.error(f"Failed to delete session {session_id} for user {user_id} after error: {e_del_err}", exc_info=True)
                yield {"type": "thought", "data": f"Failed to delete session {session_id} after error: {str(e_del_err)}"}
        return
    finally:
        # Always attempt to delete the session after processing is complete or an error handled by the main try-except occurred
        if adk_app and session_id and user_id:
            try:
                logger.info(f"Attempting to delete session {session_id} for user {user_id} (end of call_agent_for_plan).")
                adk_app.delete_session(user_id=user_id, session_id=session_id)
                yield {"type": "thought", "data": f"Session {session_id} deleted successfully for user {user_id}."}
                logger.info(f"Session {session_id} for user {user_id} deleted successfully.")
            except Exception as e_del_final:
                logger.error(f"Failed to delete session {session_id} for user {user_id} at end of call: {e_del_final}", exc_info=True)
                yield {"type": "thought", "data": f"Failed to delete session {session_id} at end of call: {str(e_del_final)}"}


    if "```json" in accumulated_json_str:
        logger.info("Detected JSON in markdown code block. Extracting...")
        try:
            json_block = accumulated_json_str.split("```json", 1)[1].rsplit("```", 1)[0].strip()
            accumulated_json_str = json_block
            logger.info(f"Extracted JSON block: {accumulated_json_str}")
        except IndexError:
            logger.warning("Error extracting JSON from markdown block. Will try to parse as is.")
            yield {"type": "thought", "data": "Could not extract JSON from markdown block, will attempt to parse the full response."}

    if accumulated_json_str:
        try:
            final_result_json = json.loads(accumulated_json_str)
            yield {"type": "plan_complete", "data": final_result_json}
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding accumulated string as JSON (user: {user_id}, session: {session_id}): {e}\nRaw data: {accumulated_json_str}", exc_info=True)
            yield {"type": "thought", "data": f"Failed to parse the ADK App's output as a valid plan. Error: {e}"}
            yield {"type": "thought", "data": f"Raw output received: {accumulated_json_str}"}
            yield {"type": "error", "data": {"message": f"JSON parsing error: {e}", "raw_output": accumulated_json_str}}
    else:
        logger.warning(f"No text content accumulated from ADK App response (user: {user_id}, session: {session_id}).")
        yield {"type": "thought", "data": "ADK App did not provide any text content in its response."}
        yield {"type": "error", "data": {"message": "ADK App returned no content.", "raw_output": ""}}


def post_plan_event(user_name, confirmed_plan, edited_invite_message, agent_session_user_id):
    """
    Simulates an agent posting an event and a message to Instavibe.
    Yields 'thought' events for logging.
    """
    yield {"type": "thought", "data": f"--- Post Plan Event Agent Call Initiated ---"}
    yield {"type": "thought", "data": f"Agent Session ID for this run: {agent_session_user_id}"}
    yield {"type": "thought", "data": f"User performing action: {user_name}"}
    yield {"type": "thought", "data": f"Received Confirmed Plan (event_name): {confirmed_plan.get('event_name', 'N/A')}"}
    yield {"type": "thought", "data": f"Received Invite Message: {edited_invite_message[:100]}..."} # Log a preview
    yield {"type": "thought", "data": f"Initiating process to post event and invite for {user_name}."}

    # Use agent_session_user_id if provided (as it implies a context, e.g. from a previous step),
    # otherwise default to user_name for creating a new session context.
    # For ADK, user_id is crucial for session management.
    # The original `agent_session_user_id` seems to be the `user_id` from the previous call.
    # We will use this as the `user_id` for ADK session.
    adk_user_id = str(agent_session_user_id if agent_session_user_id else user_name)
    session_id = None # Will be set after creating a session

    prompt_message = f"""
    You are an Orchestrator assistant for the Instavibe platform. User '{user_name}' (User ID for this interaction: '{adk_user_id}') has finalized an event plan and wants to:
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
    - After the  tool call is complete, briefly acknowledge its success based on the tool's response.

    TASK 2: Create the Invite Post on Instavibe.
    - Only after TASK 1 (event creation) is confirmed as  successful, you MUST use your tool again.
    - The `message` you send to the agent for this task should be a clear, natural language instruction to create a post. This message MUST include:
        - The author of the post: "{user_name}"
        - The content of the post: The "Invite Message" provided above ("{edited_invite_message}")
        - An instruction to associate this post with the event created in TASK 1 (e.g., by referencing its name: "{confirmed_plan.get('event_name', 'Unnamed Event')}").
        - Indicate the sentiment is "positive" as it's an invitation.
    - Narrate the natural language message you are formulating for the `send_task` tool to create the post.
    - After the `send_task` tool call is (simulated as) complete, briefly acknowledge its success.

    IMPORTANT INSTRUCTIONS FOR YOUR BEHAVIOR:
    - Your primary role here is to orchestrate these two actions by selecting an appropriate remote agent and sending it clear, natural language instructions via your  tool.
    - Your responses during this process should be a stream of consciousness, primarily narrating your agent selection (if applicable), the formulation of your natural language messages for , and theiroutcomes.
    - Do NOT output any JSON yourself. Your output must be plain text only, describing your actions.
    - Conclude with a single, friendly success message confirming that you have (simulated) instructing the remote agent to create both the event and the post. For example: "Alright, I've instructed the appropriate Instavibe agent to create the event '{confirmed_plan.get('event_name', 'Unnamed Event')}' and to make the invite post for {user_name}!"
    """

    yield {"type": "thought", "data": f"Sending posting instructions to ADK App for user {adk_user_id}."}
    logger.info(f"--- Sending Prompt to ADK App for posting (user: {adk_user_id}) ---")
    logger.debug(f"Prompt for posting: {prompt_message}")
    
    accumulated_response_text = "" # Used to capture text for error reporting if needed

    try:
        if not adk_app:
            logger.error("ADK App is not initialized. Cannot process post_plan_event.")
            yield {"type": "error", "data": {"message": "ADK App not initialized. Cannot process posting.", "raw_output": ""}}
            return

        # Create a session
        try:
            logger.info(f"Creating session for user_id: {adk_user_id} (for posting)")
            session = adk_app.create_session(user_id=adk_user_id)
            session_id = session.session_id # Assuming session object has session_id attribute
            yield {"type": "thought", "data": f"Session created for posting: {session_id} for user {adk_user_id}"}
            logger.info(f"Session {session_id} created for user {adk_user_id} (for posting)")
        except Exception as e_session_create_post:
            logger.error(f"Error creating session for user {adk_user_id} (for posting): {e_session_create_post}", exc_info=True)
            yield {"type": "error", "data": {"message": f"Error creating session for posting: {str(e_session_create_post)}", "raw_output": ""}}
            return

        yield {"type": "thought", "data": f"--- ADK App Response Stream Starting for Posting (session: {session_id}) ---"}

        stream_iterator_post = adk_app.stream_query(
            user_id=adk_user_id,
            session_id=session_id,
            message=prompt_message
        )

        for chunk_idx, chunk in enumerate(stream_iterator_post):
            # logger.debug(f"Post Event - ADK Chunk {chunk_idx} (user: {adk_user_id}, session: {session_id}): {chunk}")
            # pprint.pprint(chunk) # Debug if needed

            text_from_chunk = None
            if hasattr(chunk, 'response'):
                text_from_chunk = chunk.response
                yield {"type": "thought", "data": f"ADK App (post response content): \"{text_from_chunk}\""}
            elif hasattr(chunk, 'thought'):
                 yield {"type": "thought", "data": f"ADK App (post thought): \"{chunk.thought}\""}
            elif hasattr(chunk, 'tool_code'):
                 yield {"type": "thought", "data": f"ADK App (post tool_code): \"{chunk.tool_code}\""}
            elif hasattr(chunk, 'tool_result'):
                 yield {"type": "thought", "data": f"ADK App (post tool_result for {getattr(chunk, 'tool_name', 'unknown tool')}): \"{chunk.tool_result}\""}
            elif isinstance(chunk, str):
                text_from_chunk = chunk
                yield {"type": "thought", "data": f"ADK App (post string chunk): \"{text_from_chunk}\""}
            else:
                unknown_chunk_str = str(chunk)
                logger.warning(f"Received chunk of unexpected type/structure {type(chunk)} from ADK App stream_query for post (user: {adk_user_id}, session: {session_id}): {unknown_chunk_str}")
                yield {"type": "thought", "data": f"ADK App (post unknown chunk type {type(chunk)}): {unknown_chunk_str}"}

            if text_from_chunk: # Accumulate for error reporting context if needed
                accumulated_response_text += text_from_chunk

        yield {"type": "thought", "data": f"--- End of ADK App Response Stream for Posting (session: {session_id}) ---"}

    except Exception as e_outer_post:
        logger.error(f"Error during ADK App interaction for posting (user: {adk_user_id}, session: {session_id}): {e_outer_post}", exc_info=True)
        yield {"type": "thought", "data": f"Critical error during ADK App stream_query or iteration for posting (session: {session_id}): {str(e_outer_post)}"}
        yield {"type": "error", "data": {"message": f"Error during ADK App interaction for posting: {str(e_outer_post)}", "raw_output": accumulated_response_text}}
        if adk_app and session_id and adk_user_id:
            try:
                logger.info(f"Attempting to delete session {session_id} for user {adk_user_id} (posting error).")
                adk_app.delete_session(user_id=adk_user_id, session_id=session_id)
                yield {"type": "thought", "data": f"Session {session_id} (posting) deleted for user {adk_user_id} after error."}
                logger.info(f"Session {session_id} (posting) for user {adk_user_id} deleted after error.")
            except Exception as e_del_err_post:
                logger.error(f"Failed to delete session {session_id} for user {adk_user_id} (posting error): {e_del_err_post}", exc_info=True)
                yield {"type": "thought", "data": f"Failed to delete session {session_id} (posting) after error: {str(e_del_err_post)}"}
        return
    finally:
        if adk_app and session_id and adk_user_id:
            try:
                logger.info(f"Attempting to delete session {session_id} for user {adk_user_id} (end of post_plan_event).")
                adk_app.delete_session(user_id=adk_user_id, session_id=session_id)
                yield {"type": "thought", "data": f"Session {session_id} (posting) deleted successfully for user {adk_user_id}."}
                logger.info(f"Session {session_id} (posting) for user {adk_user_id} deleted successfully.")
            except Exception as e_del_final_post:
                logger.error(f"Failed to delete session {session_id} for user {adk_user_id} (posting, end of call): {e_del_final_post}", exc_info=True)
                yield {"type": "thought", "data": f"Failed to delete session {session_id} (posting) at end of call: {str(e_del_final_post)}"}

    # The original function always yielded posting_finished, regardless of the agent's text output,
    # as long as no exceptions occurred during the stream. We maintain this behavior.
    yield {"type": "posting_finished", "data": {"success": True, "message": "ADK App has finished processing the event and post creation instructions."}}
