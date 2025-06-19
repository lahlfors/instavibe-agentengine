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

# Initialize logger
logger = logging.getLogger(__name__)

# Global variables for agent engines
planner_agent_engine = None
orchestrator_agent_engine = None

def init_agent_engines(project_id, location): # Renamed to init_agent_engines
    """Initializes the Vertex AI Agent Engines for Planner and Orchestrator."""
    global planner_agent_engine, orchestrator_agent_engine
    logger.info("Attempting to initialize agent engines...")

    try:
        # Initialize with the specific location, this is important for when we instantiate
        # a ReasoningEngine object later using its full resource name (which includes the location).
        logger.info(f"Initializing Vertex AI with project: {project_id}, location: {location}")
        vertexai.init(project=project_id, location=location)
    except Exception as e:
        logger.error(f"Failed to initialize Vertex AI: {e}", exc_info=True)
        planner_agent_engine = None
        orchestrator_agent_engine = None
        logger.warning("Planner and Orchestrator agent engines are None due to Vertex AI initialization failure.")
        return

    # Initialize Planner Agent
    planner_resource_name_from_env = os.getenv("AGENTS_PLANNER_RESOURCE_NAME")
    if planner_resource_name_from_env:
        logger.info(f"Found AGENTS_PLANNER_RESOURCE_NAME: {planner_resource_name_from_env}. Attempting direct connection to Planner.")
        try:
            planner_agent_engine = reasoning_engines.ReasoningEngine(planner_resource_name_from_env)
            logger.info(f"Successfully connected to Planner Agent using resource name: {planner_resource_name_from_env}")
        except Exception as e:
            logger.error(f"Failed to connect directly to Planner using AGENTS_PLANNER_RESOURCE_NAME '{planner_resource_name_from_env}': {e}", exc_info=True)
            planner_agent_engine = None # Ensure it's None on failure
    else:
        logger.info("AGENTS_PLANNER_RESOURCE_NAME not set for Planner. Will attempt to find by listing if needed.")

    # Initialize Orchestrator Agent
    orchestrator_resource_name_from_env = os.getenv("AGENTS_ORCHESTRATE_RESOURCE_NAME") # New ENV VAR
    if orchestrator_resource_name_from_env:
        logger.info(f"Found AGENTS_ORCHESTRATE_RESOURCE_NAME: {orchestrator_resource_name_from_env}. Attempting direct connection to Orchestrator.")
        try:
            orchestrator_agent_engine = reasoning_engines.ReasoningEngine(orchestrator_resource_name_from_env)
            logger.info(f"Successfully connected to Orchestrator Agent using resource name: {orchestrator_resource_name_from_env}")
        except Exception as e:
            logger.error(f"Failed to connect directly to Orchestrator using AGENTS_ORCHESTRATE_RESOURCE_NAME '{orchestrator_resource_name_from_env}': {e}", exc_info=True)
            orchestrator_agent_engine = None # Ensure it's None on failure
    else:
        logger.info("AGENTS_ORCHESTRATE_RESOURCE_NAME not set for Orchestrator. Will attempt to find by listing if needed.")

    # Fallback to listing logic if direct connection failed or env var not set for either agent
    # This part attempts to find any agent that wasn't successfully initialized above.
    agents_to_find_by_listing = []
    if planner_agent_engine is None and not planner_resource_name_from_env: # Only list if no direct attempt was made or it failed AND no env var
        agents_to_find_by_listing.append({"name": "Planner Agent", "global_var": "planner_agent_engine"})
    if orchestrator_agent_engine is None and not orchestrator_resource_name_from_env: # Same for orchestrator
        agents_to_find_by_listing.append({"name": "Orchestrator Agent", "global_var": "orchestrator_agent_engine"}) # Assuming "Orchestrator Agent" is its display name

    if agents_to_find_by_listing:
        logger.info(f"Attempting to initialize agents by listing (fallback) for: {', '.join([a['name'] for a in agents_to_find_by_listing])}")
        try:
            logger.info("Initializing ReasoningEngineServiceClient for listing (fallback)")
            client = ReasoningEngineServiceClient()

            parent_for_list = f"projects/{project_id}/locations/global"
            logger.info(f"Listing reasoning engines in {parent_for_list} (fallback)")
            all_engines_in_project = client.list_reasoning_engines(parent=parent_for_list)

            # Create a dictionary for quick lookup
            engines_map = {engine.display_name: engine for engine in all_engines_in_project if f"/locations/{location}/" in engine.name}
            logger.info(f"Found {len(engines_map)} engines in target location '{location}': {list(engines_map.keys())}")


            for agent_config in agents_to_find_by_listing:
                target_display_name = agent_config["name"]
                engine_var_name = agent_config["global_var"]

                found_engine = engines_map.get(target_display_name)

                if found_engine:
                    engine_id_full = found_engine.name
                    logger.info(f"{target_display_name} found: {engine_id_full}. Attempting to connect using full name (fallback).")
                    try:
                        engine_instance = reasoning_engines.ReasoningEngine(engine_id_full)
                        globals()[engine_var_name] = engine_instance # Dynamically set planner_agent_engine or orchestrator_agent_engine
                        logger.info(f"Successfully connected to {target_display_name} (fallback).")
                    except Exception as e_connect_fallback:
                        logger.error(f"Failed to connect to {target_display_name} using full name {engine_id_full} during fallback: {e_connect_fallback}", exc_info=True)
                        globals()[engine_var_name] = None
                else:
                    logger.warning(f"{target_display_name} not found in project {project_id} and specific location {location} (fallback after listing).")
                    globals()[engine_var_name] = None

        except Exception as e_list:
            logger.error(f"Error during fallback agent engine initialization (listing): {e_list}", exc_info=True)
            # Ensure agents that were meant to be found by listing are None if listing fails
            for agent_config in agents_to_find_by_listing:
                globals()[agent_config["global_var"]] = None


    # Final status log for Planner Agent
    if planner_agent_engine is None:
        logger.warning("Planner agent engine is None after all initialization attempts.")
    else:
        logger.info("Planner agent engine initialized successfully.")

    # Final status log for Orchestrator Agent
    if orchestrator_agent_engine is None:
        logger.warning("Orchestrator agent engine is None after all initialization attempts.")
    else:
        logger.info("Orchestrator agent engine initialized successfully.")


# Initialize agent engines on module load
COMMON_GOOGLE_CLOUD_PROJECT = os.getenv("COMMON_GOOGLE_CLOUD_PROJECT")
COMMON_GOOGLE_CLOUD_LOCATION = os.getenv("COMMON_GOOGLE_CLOUD_LOCATION")

if COMMON_GOOGLE_CLOUD_PROJECT and COMMON_GOOGLE_CLOUD_LOCATION:
    logger.info(f"Attempting to initialize agent engines for project {COMMON_GOOGLE_CLOUD_PROJECT} in {COMMON_GOOGLE_CLOUD_LOCATION}")
    init_agent_engines(COMMON_GOOGLE_CLOUD_PROJECT, COMMON_GOOGLE_CLOUD_LOCATION) # Updated call
else:
    logger.error("COMMON_GOOGLE_CLOUD_PROJECT or COMMON_GOOGLE_CLOUD_LOCATION environment variables not set. Agent engines will not be initialized.")



def call_agent_for_plan(user_name, planned_date, location_n_perference, selected_friend_names_list):
    user_id = str(user_name)
    # agent_thoughts_log = [] # No longer needed here, we yield directly

    yield {"type": "thought", "data": f"--- IntrovertAlly Agent Call Initiated ---"}
    yield {"type": "thought", "data": f"Session ID for this run: {user_id}"}
    yield {"type": "thought", "data": f"User: {user_name}"}
    yield {"type": "thought", "data": f"Planned Date: {planned_date}"}
    yield {"type": "thought", "data": f"Location/Preference: {location_n_perference}"}
    yield {"type": "thought", "data": f"Selected Friends: {', '.join(selected_friend_names_list)}"}
    yield {"type": "thought", "data": f"Initiating plan for {user_name} on {planned_date} regarding '{location_n_perference}' with friends: {', '.join(selected_friend_names_list)}."}

    selected_friend_names_str = ', '.join(selected_friend_names_list)
    # print(f"Selected Friends (string for agent): {selected_friend_names_str}") # Console log

    # Constructing an example for the prompt, e.g., ["Alice", "Bob"]
    friends_list_example_for_prompt = json.dumps(selected_friend_names_list)

    prompt_message = f"""Plan a personalized night out for {user_name} with friends {selected_friend_names_str} on {planned_date}, with the location or preference being "{location_n_perference}".

    Analyze friend interests (if possible, use Instavibe profiles or summarized interests) to create a tailored plan.  Ensure the plan includes the date {planned_date}.

    Output the entire plan in a SINGLE, COMPLETE JSON object with the following structure.  **CRITICAL: The FINAL RESPONSE MUST BE ONLY THIS JSON.  If any fields are missing or unavailable, INVENT them appropriately to complete the JSON structure.  Do not return any conversational text or explanations.  Just the raw, valid JSON.**

    {{
    "friends_name_list": {friends_list_example_for_prompt}, //  Array of strings: {selected_friend_names_str}
    "event_name": "string",        // Concise, descriptive name for the event (e.g., "{selected_friend_names_str}'s Night Out")
    "event_date": "{planned_date}", // Date in ISO 8601 format.
    "event_description": "string", // Engaging summary of planned activities.
    "locations_and_activities": [  // Array detailing each step of the plan.
        {{
        "name": "string",          // Name of the place, venue, or activity.
        "latitude": 12.345,        // Approximate latitude (e.g., 34.0522) or null if not available.
        "longitude": -67.890,      // Approximate longitude (e.g., -118.2437) or null if not available.
        "address": "string or null", // Physical address if available, otherwise null.
        "description": "string"    // Description of this location/activity.
        }}
        // Add more location/activity objects as needed.
    ],
    "post_to_go_out": "string"     // Short, catchy, and exciting text message from {user_name} to invite friends.
    }}
    """

    print(f"--- Sending Prompt to Agent ---") 
    print(prompt_message) 
    yield {"type": "thought", "data": f"Sending detailed planning prompt to agent for {user_name}'s event."}

    accumulated_json_str = ""

    yield {"type": "thought", "data": f"--- Agent Response Stream Starting ---"}
    try:
        if not planner_agent_engine:
            logger.error("Planner agent engine is not initialized. Check previous logs for errors during init_agent_engine, especially missing environment variables or issues connecting to the reasoning engine.") # Added this line
            yield {"type": "error", "data": {"message": "Agent engine not initialized. Cannot query for plan.", "raw_output": ""}}
            return

        # Ensure planner_agent_engine.stream returns an iterable/async iterable
        # The original code was iterating over planner_agent_engine.query(),
        # now we are using .stream() as per the fix for the agent definition.
        # The client code here should expect a stream of events.
        # stream_iterator = planner_agent_engine.stream(input=prompt_message, session_id=user_id) # Incorrect: .stream() not an attribute
        # Correct way to get a stream is to call the ReasoningEngine object directly.
        stream_response = planner_agent_engine(input=prompt_message, session_id=user_id)

        for event_idx, event in enumerate(stream_response): # Iterate over the direct call result
            print(f"\n--- Stream Event {event_idx} Received ---") # Console
            pprint.pprint(event) # Console
            try:
                if isinstance(event, dict):
                    # Existing logic for dictionary events
                    content = event.get('content', {})
                    parts = content.get('parts', [])

                    if not parts: # Check if parts might be None or empty
                        # If content itself has 'text', it might be a simple dict response
                        if content and 'text' in content and isinstance(content['text'], str):
                             yield {"type": "thought", "data": f"Agent (dict event content text): \"{content['text']}\""}
                             accumulated_json_str += content['text']
                        # else: # No parts and no direct text in content
                        #    pass # Or log empty dict event if necessary
                    else: # Process parts
                        for part_idx, part in enumerate(parts):
                            if isinstance(part, dict):
                                text = part.get('text')
                                if text:
                                    yield {"type": "thought", "data": f"Agent (dict event part text): \"{text}\""}
                                    accumulated_json_str += text
                                else:
                                    tool_code = part.get('tool_code')
                                    tool_code_output = part.get('tool_code_output')
                                    if tool_code:
                                        yield {"type": "thought", "data": f"Agent is considering using a tool: {tool_code.get('name', 'Unnamed tool')}."}
                                    if tool_code_output:
                                        yield {"type": "thought", "data": f"Agent received output from tool '{tool_code.get('name', 'Unnamed tool')}'."}
                elif isinstance(event, str):
                    # New logic for string events
                    logger.info(f"Received raw string event from agent query: {event}")
                    yield {"type": "thought", "data": f"Agent (string event): \"{event}\""}
                    accumulated_json_str += event
                else:
                    # Log/handle other unexpected event types
                    logger.warning(f"Received event of unexpected type {type(event)} from agent query: {str(event)}")
                    yield {"type": "thought", "data": f"Agent (unknown event type {type(event)}): {str(event)}"}
            except Exception as e_inner: # This outer try-except catches errors from the above logic
                logger.error(f"Error processing agent event part {event_idx} (type: {type(event)}): {e_inner}", exc_info=True)
                yield {"type": "thought", "data": f"Error processing agent event part {event_idx}: {str(e_inner)}"}

    except Exception as e_outer:
        yield {"type": "thought", "data": f"Critical error during agent stream query: {str(e_outer)}"}
        yield {"type": "error", "data": {"message": f"Error during agent interaction: {str(e_outer)}", "raw_output": accumulated_json_str}}
        return # Stop generation
    
    yield {"type": "thought", "data": f"--- End of Agent Response Stream ---"}

    # Attempt to extract JSON if it's wrapped in markdown
    if "```json" in accumulated_json_str:
        print("Detected JSON in markdown code block. Extracting...") 
       
        try:
            # Extract content between ```json and ```
            json_block = accumulated_json_str.split("```json", 1)[1].rsplit("```", 1)[0].strip()
            accumulated_json_str = json_block
            print(f"Extracted JSON block: {accumulated_json_str}") 
        except IndexError:
            # print("Error extracting JSON from markdown block. Will try to parse as is.") # Console
            yield {"type": "thought", "data": "Could not extract JSON from markdown block, will attempt to parse the full response."}

    if accumulated_json_str:
        try:
            final_result_json = json.loads(accumulated_json_str)
            yield {"type": "plan_complete", "data": final_result_json}
        except json.JSONDecodeError as e:
            # print(f"Error decoding accumulated string as JSON: {e}") # Console
            yield {"type": "thought", "data": f"Failed to parse the agent's output as a valid plan. Error: {e}"}
            yield {"type": "thought", "data": f"Raw output received: {accumulated_json_str}"}
            # print("Returning raw accumulated string due to JSON parsing error.") # Console
            yield {"type": "error", "data": {"message": f"JSON parsing error: {e}", "raw_output": accumulated_json_str}}
    else:
        # print("No text content accumulated from agent response.") # Console
        yield {"type": "thought", "data": "Agent did not provide any text content in its response."}
        yield {"type": "error", "data": {"message": "Agent returned no content.", "raw_output": ""}}



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
    yield {"type": "thought", "data": f"Initiating process to post event and invite for {user_name} via Orchestrator."}

    # This is the message to the Orchestrator Agent.
    # It's less about "You are an Orchestrator" and more "Please orchestrate the following..."
    orchestration_request_message = f"""
User '{user_name}' wants to finalize and announce an event. Please orchestrate the following tasks:

1.  **Create the event on Instavibe.**
    *   Event Details (from confirmed plan):
        *   Event Name: "{confirmed_plan.get('event_name', 'Unnamed Event')}"
        *   Event Description: "{confirmed_plan.get('event_description', 'No description provided.')}"
        *   Event Date: "{confirmed_plan.get('event_date', 'MISSING_EVENT_DATE_IN_PLAN')}"
        *   Locations: {json.dumps(confirmed_plan.get('locations_and_activities', []))}
        *   Attendees: {json.dumps(list(set(confirmed_plan.get('friends_name_list', []) + [user_name])))}
    *   Instruction: Find a suitable agent and instruct it to create this event with all the provided details.

2.  **Create an invite post for this event on Instavibe.**
    *   Post Details:
        *   Author: "{user_name}"
        *   Content: "{edited_invite_message}"
        *   Associate with event: "{confirmed_plan.get('event_name', 'Unnamed Event')}"
        *   Sentiment: "positive"
    *   Instruction: After the event creation is confirmed successful, find a suitable agent and instruct it to create this invite post.

Please manage the execution of these tasks, including any necessary agent discovery and task delegation.
Provide updates on the progress and confirm completion.
    """

    yield {"type": "thought", "data": f"Sending orchestration request to Orchestrator Agent for {user_name}'s event."}
    logger.info(f"Orchestration request for {user_name}:\n{orchestration_request_message}")
    
    accumulated_response_text = ""

    try:
        if not orchestrator_agent_engine: # Check orchestrator_agent_engine
            logger.error("Orchestrator agent engine is not initialized. Cannot send orchestration request.")
            yield {"type": "error", "data": {"message": "Orchestrator agent engine not initialized. Cannot process event posting.", "raw_output": ""}}
            return

        # Using .query() for the orchestrator as it might return a single structured response or stream of thoughts.
        # If OrchestratorServiceAgent's query() is streaming, this loop will process it.
        # If it's a single dict, this loop will run once.
        # The key is that OrchestratorServiceAgent.query() should be compatible with this.
        # For ADK agents, response is typically a stream of events.
        # We expect the orchestrator to give textual updates or a final confirmation.

        # Using .stream() as it's more consistent with ADK agent interactions
        # stream_iterator = orchestrator_agent_engine.stream( # Incorrect: .stream() not an attribute
        #     input=orchestration_request_message,
        #     session_id=agent_session_user_id # Use the same session ID for context
        # )
        # Correct way to get a stream is to call the ReasoningEngine object directly.
        stream_response = orchestrator_agent_engine(
            input=orchestration_request_message,
            session_id=agent_session_user_id
        )

        for event_idx, event in enumerate(stream_response): # Iterate over the direct call result
            logger.info(f"\n--- Orchestrator Agent Event {event_idx} Received ---")
            # pprint.pprint(event) # Keep for debugging if necessary, can be verbose
            try:
                if isinstance(event, dict):
                    content = event.get('content', {})
                    parts = content.get('parts', [])
                    if not parts and content and 'text' in content and isinstance(content['text'], str): # Simple dict response
                        text = content['text']
                        yield {"type": "thought", "data": f"Orchestrator (dict event content text): \"{text}\""}
                        accumulated_response_text += text
                    else:
                        for part_idx, part in enumerate(parts):
                            if isinstance(part, dict):
                                text = part.get('text')
                                if text:
                                    yield {"type": "thought", "data": f"Orchestrator: \"{text}\""}
                                    accumulated_response_text += text
                                # Orchestrator might also log tool calls it makes, handle if necessary
                                tool_code = part.get('tool_code')
                                tool_code_output = part.get('tool_code_output')
                                if tool_code:
                                    yield {"type": "thought", "data": f"Orchestrator is using a tool: {tool_code.get('name', 'Unnamed tool')}."}
                                if tool_code_output:
                                    # Output from tools like send_task might be complex. For now, just log its presence.
                                    # tool_output_text = tool_code_output.get('output', {}).get('text', '[No text in tool output]')
                                    # yield {"type": "thought", "data": f"Orchestrator received output from tool '{tool_code.get('name', 'Unnamed tool')}': {tool_output_text}"}
                                    yield {"type": "thought", "data": f"Orchestrator received output from tool '{tool_code.get('name', 'Unnamed tool')}'."}

                elif isinstance(event, str): # If the agent yields raw strings
                    yield {"type": "thought", "data": f"Orchestrator (raw string): \"{event}\""}
                    accumulated_response_text += event
                else:
                    logger.warning(f"Received event of unexpected type {type(event)} from orchestrator: {str(event)}")
                    yield {"type": "thought", "data": f"Orchestrator (unknown event type {type(event)}): {str(event)}"}

            except Exception as e_inner:
                logger.error(f"Error processing orchestrator agent event part {event_idx} (type: {type(event)}): {e_inner}", exc_info=True)
                yield {"type": "thought", "data": f"Error processing orchestrator agent event part {event_idx}: {str(e_inner)}"}


    except Exception as e_outer:
        logger.error(f"Critical error during orchestrator agent stream query: {e_outer}", exc_info=True)
        yield {"type": "thought", "data": f"Critical error during orchestrator agent interaction: {str(e_outer)}"}
        yield {"type": "error", "data": {"message": f"Error during orchestrator agent interaction: {str(e_outer)}", "raw_output": accumulated_response_text}}
        return

    yield {"type": "thought", "data": f"--- End of Orchestrator Agent Response Stream ---"}
    # The final message from the orchestrator should indicate success/failure.
    # We might need a more structured way for the orchestrator to signal completion.
    # For now, we assume the accumulated_response_text contains the confirmation.
    yield {"type": "posting_finished", "data": {"success": True, "message": accumulated_response_text or "Orchestrator has finished processing the event and post creation."}}
