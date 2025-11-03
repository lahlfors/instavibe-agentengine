import os
import pprint
import json 
import logging
import google.cloud.aiplatform as vertexai
from vertexai.generative_models import GenerativeModel
from vertexai.preview.reasoning_engines import ReasoningEngine
from opentelemetry import trace
import opentelemetry.semconv._incubating.attributes.gen_ai_attributes as ai_semconv
from typing import Generator, Dict, Any

# Initialize logger
logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# --- CONFIGURATION ---
# This is the stable name you set in 'deploy_all.py'
ORCHESTRATE_AGENT_DISPLAY_NAME = "Orchestrate Agent" 

# Global variable for the ADK app instance
adk_app: ReasoningEngine | None = None

def init_agent_engine(project_id, location):
    """
    Initializes the Vertex AI ADK Application client by finding the
    agent by its stable display_name.
    """
    global adk_app
    if adk_app:
        logger.info("ADK App client is already initialized.")
        return

    logger.info("Attempting to initialize ADK App client...")

    try:
        logger.info(f"Initializing Vertex AI with project: {project_id}, location: {location}")
        vertexai.init(project=project_id, location=location)
    except Exception as e:
        logger.error(f"Failed to initialize Vertex AI: {e}", exc_info=True)
        return

    try:
        # Find the agent by its known, stable display_name
        logger.info(f"Searching for agent with display_name: '{ORCHESTRATE_AGENT_DISPLAY_NAME}'")
        
        agent_filter = f'display_name="{ORCHESTRATE_AGENT_DISPLAY_NAME}"'
        engines = ReasoningEngine.list(filter=agent_filter)

        if not engines:
            logger.error(f"FATAL: Could not find any Reasoning Engine with display_name: '{ORCHESTRATE_AGENT_DISPLAY_NAME}'")
            return

        adk_app = engines[0]  # Get the first match
        logger.info(f"Successfully connected to ReasoningEngine (ADK App) client: {adk_app.resource_name}")
        
    except Exception as e:
        logger.error(f"Failed to get ReasoningEngine using display_name '{ORCHESTRATE_AGENT_DISPLAY_NAME}': {e}", exc_info=True)
        adk_app = None


def _handle_adk_stream(stream_iterator, user_id, session_id, logger_prefix="") -> Generator[Dict[str, Any], None, str]:
    """
    A helper generator to process and log an ADK stream.
    Yields 'thought' events and returns the accumulated text.
    """
    accumulated_text = ""
    try:
        for chunk_idx, chunk in enumerate(stream_iterator):
            text_to_accumulate = None
            
            if hasattr(chunk, 'response'): 
                text_to_accumulate = chunk.response
                yield {"type": "thought", "data": f"ADK App ({logger_prefix} response): \"{text_to_accumulate}\""}
            elif hasattr(chunk, 'thought'):
                yield {"type": "thought", "data": f"ADK App ({logger_prefix} thought): \"{chunk.thought}\""}
            elif hasattr(chunk, 'tool_result'):
                tool_name = getattr(chunk, 'tool_name', 'unknown tool')
                yield {"type": "thought", "data": f"ADK App ({logger_prefix} tool_result for {tool_name}): \"{chunk.tool_result}\""}
            elif isinstance(chunk, dict) and 'content' in chunk: 
                try:
                    text_to_accumulate = chunk['content']['parts'][0]['text']
                    yield {"type": "thought", "data": f"ADK App ({logger_prefix} response dict): \"{text_to_accumulate}\""}
                except (KeyError, IndexError, TypeError):
                     pass # Ignore malformed dicts
            else:
                unknown_chunk_str = str(chunk)
                logger.warning(f"Received chunk of unexpected type/structure {type(chunk)} from ADK App (user: {user_id}, session: {session_id}): {unknown_chunk_str}")
                yield {"type": "thought", "data": f"ADK App ({logger_prefix} unknown chunk): {unknown_chunk_str}"}

            if text_to_accumulate:
                accumulated_text += text_to_accumulate
                
    except Exception as e:
        logger.error(f"Error during ADK stream iteration (user: {user_id}, session: {session_id}): {e}", exc_info=True)
        yield {"type": "thought", "data": f"Error during ADK stream: {str(e)}"}
        raise
    
    return accumulated_text


def call_agent_for_plan(user_name, planned_date, location_n_perference, selected_friend_names_list):
    user_id = str(user_name)
    session_id = None
    accumulated_json_str = ""
    
    yield {"type": "thought", "data": f"--- IntrovertAlly Agent Call Initiated (ADK) ---"}
    # ... (other initial thoughts) ...
    
    selected_friend_names_str = ', '.join(selected_friend_names_list)
    friends_list_example_for_prompt = json.dumps(selected_friend_names_list)

    prompt_message = f"""Plan a personalized night out for {user_name} with friends {selected_friend_names_str} on {planned_date}, with the location or preference being "{location_n_perference}".
    ... (Your full planning prompt) ...
    }}
    """
    logger.info(f"--- Sending Prompt to ADK App for user {user_id} ---")
    yield {"type": "thought", "data": f"Sending detailed planning prompt to ADK App for {user_name}'s event."}

    with tracer.start_as_current_span("call_agent_for_plan") as span:
        model_name = "gemini-1.5-flash-001" # Or get from env
        span.set_attribute(ai_semconv.GEN_AI_SYSTEM, "google_vertexai")
        span.set_attribute(ai_semconv.GEN_AI_REQUEST_MODEL, model_name)
        model = GenerativeModel(model_name)
        
        # ... (Token counting and span setup) ...

        try:
            if not adk_app:
                logger.error("ADK App is not initialized. Cannot query for plan.")
                yield {"type": "error", "data": {"message": "ADK App not initialized. Cannot query for plan.", "raw_output": ""}}
                return

            # --- Session Creation ---
            try:
                logger.info(f"Creating session for user_id: {user_id}")
                session = adk_app.create_session(user_id=user_id)
                session_id = session['id']
                yield {"type": "thought", "data": f"Session created: {session_id} for user {user_id}"}
            except Exception as e:
                logger.error(f"Error creating session for user {user_id}: {e}", exc_info=True)
                yield {"type": "error", "data": {"message": f"Error creating session: {str(e)}", "raw_output": ""}}
                return

            yield {"type": "thought", "data": f"--- ADK App Response Stream Starting (session: {session_id}) ---"}
            
            stream_iterator = adk_app.stream_query(
                user_id=user_id,
                session_id=session_id,
                message=prompt_message
            )
            
            # --- Use the new helper ---
            stream_generator = _handle_adk_stream(stream_iterator, user_id, session_id, logger_prefix="plan")
            while True:
                try:
                    yield next(stream_generator)
                except StopIteration as e:
                    accumulated_json_str = e.value # Get the return value from helper
                    break

            yield {"type": "thought", "data": f"--- End of ADK App Response Stream (session: {session_id}) ---"}
            # ... (OpenTelemetry completion logging) ...

        except Exception as e_outer:
            logger.error(f"Error during ADK App interaction for user {user_id} (session: {session_id}): {e_outer}", exc_info=True)
            yield {"type": "thought", "data": f"Critical error during ADK App stream_query: {str(e_outer)}"}
            yield {"type": "error", "data": {"message": f"Error during ADK App interaction: {str(e_outer)}", "raw_output": accumulated_json_str}}
            return
        finally:
            # --- Session Deletion ---
            if adk_app and session_id and user_id:
                try:
                    logger.info(f"Attempting to delete session {session_id} for user {user_id}.")
                    adk_app.delete_session(user_id=user_id, session_id=session_id)
                    yield {"type": "thought", "data": f"Session {session_id} deleted."}
                except Exception as e_del:
                    logger.error(f"Failed to delete session {session_id} for user {user_id}: {e_del}", exc_info=True)

    
    if "```json" in accumulated_json_str:
        # ... (JSON extraction logic) ...
        pass

    if accumulated_json_str:
        try:
            final_result_json = json.loads(accumulated_json_str)
            yield {"type": "plan_complete", "data": final_result_json}
        except json.JSONDecodeError as e:
            # ... (Error handling) ...
            yield {"type": "error", "data": {"message": f"JSON parsing error: {e}", "raw_output": accumulated_json_str}}
    else:
        # ... (Error handling) ...
        yield {"type": "error", "data": {"message": "ADK App returned no content.", "raw_output": ""}}


def post_plan_event(user_name, confirmed_plan, edited_invite_message, agent_session_user_id):
    """
    Simulates an agent posting an event and a message to Instavibe.
    """
    yield {"type": "thought", "data": f"--- Post Plan Event Agent Call Initiated ---"}
    
    adk_user_id = str(agent_session_user_id if agent_session_user_id else user_name)
    session_id = None
    accumulated_response_text = ""

    prompt_message = f"""
    You are an Orchestrator assistant for the Instavibe platform. User '{user_name}'...
    ... (Your full posting prompt) ...
    """
    
    yield {"type": "thought", "data": f"Sending posting instructions to ADK App for user {adk_user_id}."}
    
    with tracer.start_as_current_span("post_plan_event") as span:
        # ... (OpenTelemetry span setup) ...
        
        try:
            if not adk_app:
                logger.error("ADK App is not initialized. Cannot process post_plan_event.")
                yield {"type": "error", "data": {"message": "ADK App not initialized.", "raw_output": ""}}
                return

            # --- Session Creation ---
            try:
                logger.info(f"Creating session for user_id: {adk_user_id} (for posting)")
                session = adk_app.create_session(user_id=adk_user_id)
                session_id = session['id']
                yield {"type": "thought", "data": f"Session created for posting: {session_id}"}
            except Exception as e:
                logger.error(f"Error creating session for user {adk_user_id} (posting): {e}", exc_info=True)
                yield {"type": "error", "data": {"message": f"Error creating session for posting: {str(e)}", "raw_output": ""}}
                return

            yield {"type": "thought", "data": f"--- ADK App Response Stream Starting for Posting ---"}
            
            stream_iterator_post = adk_app.stream_query(
                user_id=adk_user_id,
                session_id=session_id,
                message=prompt_message
            )
            
            # --- Use the new helper ---
            stream_generator = _handle_adk_stream(stream_iterator_post, adk_user_id, session_id, logger_prefix="post")
            while True:
                try:
                    yield next(stream_generator)
                except StopIteration as e:
                    accumulated_response_text = e.value # Get the return value from helper
                    break
            
            yield {"type": "thought", "data": f"--- End of ADK App Response Stream for Posting ---"}
            # ... (OpenTelemetry completion logging) ...

        except Exception as e_outer_post:
            logger.error(f"Error during ADK App interaction for posting: {e_outer_post}", exc_info=True)
            yield {"type": "error", "data": {"message": f"Error during ADK App interaction for posting: {str(e_outer_post)}", "raw_output": accumulated_response_text}}
            return
        finally:
            # --- Session Deletion ---
            if adk_app and session_id and adk_user_id:
                try:
                    logger.info(f"Attempting to delete session {session_id} for user {adk_user_id} (posting).")
                    adk_app.delete_session(user_id=adk_user_id, session_id=session_id)
                    yield {"type": "thought", "data": f"Session {session_id} (posting) deleted."}
                except Exception as e_del_post:
                    logger.error(f"Failed to delete session {session_id} for user {adk_user_id} (posting): {e_del_post}", exc_info=True)

    yield {"type": "posting_finished", "data": {"success": True, "message": "ADK App has finished processing."}}
