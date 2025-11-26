import os
import pprint
import json 
import logging
import google.cloud.aiplatform as vertexai
from vertexai.generative_models import GenerativeModel
from vertexai.preview.reasoning_engines import ReasoningEngine
from opentelemetry import trace
import opentelemetry.semconv._incubating.attributes.gen_ai_attributes as ai_semconv

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
from typing import Generator, Dict, Any

# Initialize logger
logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# --- CONFIGURATION ---
# This is the stable name you set in 'deploy_all.py'
ORCHESTRATE_AGENT_DISPLAY_NAME = "Orchestrate Agent" 

# Global variable for the Reasoning Engine instance
adk_app: ReasoningEngine | None = None

def init_agent_engine(project_id, location):
    """
    Initializes the Vertex AI ADK Application client by finding the
    agent by its stable display_name. Always refreshes to get the latest agent.
    """
    global adk_app
    # Always refresh to get the latest deployed agent
    logger.info("Initializing/Refreshing ADK App client...")

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

        # Sort by creation time (newest first) to ensure we get the latest deployment
        logger.info(f"Found {len(engines)} engines. Sorting by create_time...")
        for i, e in enumerate(engines):
            logger.info(f"  - Engine {i}: {e.resource_name} (Created: {e.create_time})")
            
        engines = sorted(engines, key=lambda e: e.create_time, reverse=True)
        found_engine = engines[0]  # Get the newest match
        logger.info(f"Selected newest engine: {found_engine.resource_name} (Created: {found_engine.create_time})")
        
        # CRITICAL FIX: The object returned by list() does NOT have dynamic methods (like query).
        # We must re-instantiate it using the resource name to fetch the schema and bind methods.
        adk_app = ReasoningEngine(found_engine.resource_name)
        
        logger.info(f"Reasoning Engine initialized successfully: {adk_app.resource_name}")
        
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

    # Use structured template for reliable parsing
    prompt = PLANNING_REQUEST_TEMPLATE.format(
        user_name=user_name,
        friends_list=selected_friend_names_str,
        planned_date=planned_date,
        location=location_n_perference
    )
    logger.info(f"--- Sending Prompt to ADK App for user {user_id} ---")
    yield {"type": "thought", "data": f"Sending detailed planning prompt to ADK App for {user_name}'s event."}

    with tracer.start_as_current_span("call_agent_for_plan") as span:
        model_name = "gemini-2.5-flash" # Or get from env
        span.set_attribute(ai_semconv.GEN_AI_SYSTEM, "google_vertexai")
        span.set_attribute(ai_semconv.GEN_AI_REQUEST_MODEL, model_name)
        model = GenerativeModel(model_name)
        
        # ... (Token counting and span setup) ...

        try:
            # Lazy initialization if adk_app is not ready
            if not adk_app:
                logger.info("ADK App not initialized. Attempting lazy initialization...")
                project_id = os.getenv("COMMON_GOOGLE_CLOUD_PROJECT")
                location = os.getenv("COMMON_GOOGLE_CLOUD_LOCATION")
                if project_id and location:
                    init_agent_engine(project_id, location)
                else:
                    logger.error("Cannot lazy initialize: Missing project_id or location env vars.")

            if not adk_app:
                logger.error("ADK App is not initialized. Cannot query for plan.")
                yield {"type": "error", "data": {"message": "ADK App not initialized. Cannot query for plan.", "raw_output": ""}}
                return

            # Use direct query() method (VertexAdkProxy pattern)
            logger.info(f"Querying Reasoning Engine: {adk_app.resource_name} with message: {prompt}")
            
            # Call query method directly - returns iterator of events
            response_stream = adk_app.query(message=prompt, user_id=user_id)
            
            # Collect streamed response
            for chunk in response_stream:
                # Inspect chunk type for debugging
                logger.info(f"[DEBUG] Received chunk: {type(chunk).__name__} - {repr(chunk)[:200]}")

                # 1. Handle "Thoughts" (Intermediate steps, tool calls, reasoning)
                # Check for 'thought' attribute or specific event types if available
                if hasattr(chunk, 'thought') and chunk.thought:
                    yield {"type": "thought", "data": f"Agent Thought: {chunk.thought}"}
                    continue # Thoughts are not part of the final JSON
                
                if hasattr(chunk, 'tool_call') and chunk.tool_call:
                     yield {"type": "thought", "data": f"Agent Tool Call: {chunk.tool_call}"}
                     continue

                # 2. Handle "Content" (The actual response text)
                text_chunk = ""
                
                # Try to extract text based on various possible chunk structures
                if isinstance(chunk, dict):
                    if 'response' in chunk:
                        text_chunk = chunk['response']
                    elif 'output' in chunk:
                        text_chunk = str(chunk['output'])
                    elif 'content' in chunk and 'parts' in chunk['content']:
                        try:
                            parts = chunk['content']['parts']
                            if parts and isinstance(parts, list) and 'text' in parts[0]:
                                text_chunk = parts[0]['text']
                        except (KeyError, IndexError, TypeError):
                            text_chunk = str(chunk)
                else:
                    # Object access
                    if hasattr(chunk, 'text') and chunk.text:
                         text_chunk = chunk.text
                    elif hasattr(chunk, 'content') and chunk.content:
                         # ADK Event object often has content.parts
                         if hasattr(chunk.content, 'parts') and chunk.content.parts:
                             try:
                                 text_chunk = chunk.content.parts[0].text
                             except:
                                 pass
                    elif hasattr(chunk, 'response') and chunk.response:
                        text_chunk = chunk.response

                if text_chunk:
                    accumulated_json_str += text_chunk
                    # Optionally stream the building JSON as a thought, or just wait. 
                    # Streaming it might look messy if it's raw JSON, but shows progress.
                    # Let's show it as a thought for now so the user sees something happening.
                    yield {"type": "thought", "data": f"{text_chunk}"}
            
            logger.info(f"[plan] Received complete response from agent (length: {len(accumulated_json_str)})")
            yield {"type": "thought", "data": f"Agent response complete ({len(accumulated_json_str)} chars)"}
            yield {"type": "thought", "data": f"--- Query complete ---"}

        except Exception as e_outer:
            logger.error(f"Error during agent query for user {user_id}: {e_outer}", exc_info=True)
            yield {"type": "thought", "data": f"Critical error during agent query: {str(e_outer)}"}
            yield {"type": "error", "data": {"message": f"Error during agent interaction: {str(e_outer)}", "raw_output": accumulated_json_str}}
            return

    
    if "```json" in accumulated_json_str:
        try:
            # Find the start of the JSON block
            start_index = accumulated_json_str.find("```json") + 7
            # Find the end of the JSON block
            end_index = accumulated_json_str.rfind("```")
            if start_index != -1 and end_index != -1 and end_index > start_index:
                accumulated_json_str = accumulated_json_str[start_index:end_index].strip()
                logger.info("Successfully stripped markdown code blocks from response.")
        except Exception as e:
            logger.warning(f"Failed to strip markdown: {e}")


    if accumulated_json_str:
        logger.info(f"[DEBUG] Raw accumulated response: {accumulated_json_str}")
        try:
            final_result_json = json.loads(accumulated_json_str)
            logger.info(f"[DEBUG] Parsed JSON: {final_result_json}")
            yield {"type": "plan_complete", "data": final_result_json}
        except json.JSONDecodeError as e:
            # If it's not JSON, it might be a conversational response (clarifying questions)
            logger.info(f"Response is not JSON, treating as conversational text: {accumulated_json_str[:100]}...")
            yield {"type": "agent_message", "data": {"message": accumulated_json_str}}
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

            logger.info(f"Querying agent for post_plan_event with user_id: {adk_user_id}")
            yield {"type": "thought", "data": f"Querying agent for posting plan..."}
            
            try:
                # Use direct query() method (VertexAdkProxy pattern)
                logger.info(f"Posting event to Reasoning Engine: {adk_app.resource_name}")
                
                # Call query method directly - returns iterator of events
                # Note: post_plan_event likely returns a simple string or JSON, but via stream
                response_stream = adk_app.query(message=prompt_message, user_id=adk_user_id)
                
                # Collect streamed response
                accumulated_response_text = ""
                for chunk in response_stream:
                    if isinstance(chunk, dict):
                        if 'response' in chunk:
                            accumulated_response_text += chunk['response']
                        elif 'output' in chunk:
                            accumulated_response_text += str(chunk['output'])
                        elif 'content' in chunk and 'parts' in chunk['content']:
                             try:
                                parts = chunk['content']['parts']
                                if parts and isinstance(parts, list) and 'text' in parts[0]:
                                    accumulated_response_text += parts[0]['text']
                             except:
                                 accumulated_response_text += str(chunk)
                        else:
                            accumulated_response_text += str(chunk)
                    else:
                        if hasattr(chunk, 'text'):
                             accumulated_response_text += chunk.text
                        else:
                             accumulated_response_text += str(chunk)
                
                logger.info(f"Event Response: {accumulated_response_text}")
                
                logger.info(f"[post] Received response from agent (length: {len(accumulated_response_text)})")
                yield {"type": "thought", "data": f"Agent response received ({len(accumulated_response_text)} chars)"}
                
            except Exception as e:
                logger.error(f"Error querying agent for posting (user {adk_user_id}): {e}", exc_info=True)
                yield {"type": "error", "data": {"message": f"Error querying agent for posting: {str(e)}", "raw_output": ""}}
                return
            
            yield {"type": "thought", "data": f"--- Query complete ---"}

        except Exception as e_outer_post:
            logger.error(f"Error during agent query for posting: {e_outer_post}", exc_info=True)
            yield {"type": "error", "data": {"message": f"Error during agent interaction for posting: {str(e_outer_post)}", "raw_output": accumulated_response_text}}
            return

    yield {"type": "posting_finished", "data": {"success": True, "message": "ADK App has finished processing."}}
