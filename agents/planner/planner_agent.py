import os # For path joining
import logging
import asyncio
import nest_asyncio # Added
from dotenv import load_dotenv # To load .env
from typing import Any, Dict, Optional # Removed AsyncIterable, ensured Any, Dict, Optional
from google.adk.agents import LoopAgent
from google.adk.tools.tool_context import ToolContext
# from google.adk.sessions import SessionNotFoundError # Removed
# from google.adk.sessions import Session # Removed Session for Optional[Any]
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part # Modified import
from agents.app.common.task_manager import AgentTaskManager # Corrected to agents.app.common
from agents.app.utils.tracing import get_tracer # Import the tracer utility
from . import agent

# Load environment variables from the root .env file.
# While agent.py also does this, adding it here ensures that if PlannerAgent
# is used or tested in a context where agent.py wasn't the first import,
# the environment is still correctly configured.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# Apply nest_asyncio to allow asyncio.run() within an existing event loop (e.g., server)
nest_asyncio.apply()

# Initialize logger at the module level
logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

class PlannerAgent(AgentTaskManager):
  """An agent to help user planning a night out with its desire location."""

  SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

  def __init__(self):
    with tracer.start_as_current_span("PlannerAgent.__init__") as span:
        logger.info("Initializing PlannerAgent...")
        self._agent = self._build_agent()
        span.set_attribute("agent.name", self._agent.name)
        logger.info(f"PlannerAgent initialized with ADK agent name: {self._agent.name}")
        self._user_id = "remote_agent" # Default user_id
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )
        logger.info("PlannerAgent Runner configured.")
        span.set_attribute("runner.configured", True)

  def get_processing_message(self) -> str:
      return "Processing the planning request..."

  def _build_agent(self) -> LoopAgent:
    """Builds the LLM agent for the night out planning agent."""
    with tracer.start_as_current_span("PlannerAgent._build_agent") as span:
        logger.info(f"Building ADK LoopAgent with agent name: {agent.AGENT_NAME}, model: {agent.MODEL_NAME}")
        span.set_attribute("adk.agent.name", agent.AGENT_NAME)
        span.set_attribute("adk.agent.model", agent.MODEL_NAME)
        # This span will cover the instantiation of agent.root_agent
        # which happens in the return statement.
        return agent.root_agent

  def query(self, query: str, **kwargs: Any) -> Dict[str, Any]: # Renamed query_text back to query, made sync
    with tracer.start_as_current_span("PlannerAgent.query") as span:
        span.set_attribute("agent.name", "PlannerAgent")
        span.set_attribute("method.name", "query")
        span.set_attribute("query.length", len(query))
        span.set_attribute("kwargs", str(kwargs)) # Be cautious with sensitive data in kwargs

        logger.info(f"PlannerAgent query started. Query length: {len(query)}. Kwargs: {kwargs}")
        logger.debug(f"Full query text: {query}")
        app_name = self._agent.name
        span.set_attribute("adk.app.name", app_name)

        # Determine the user_id and desired_session_id for this interaction
        # ADK 1.0.0 examples use user_id for session context and run_async.
        # The session_id from kwargs (from instavibe-app) is the user_name.
        interaction_user_id = str(kwargs.get("session_id", self._user_id)) # Default to agent's user_id if no session_id from app

        # For InMemorySessionService with ADK 1.0.0, the example shows passing session_id to create_session
        # This session_id is then used in run_async. Let's use interaction_user_id as the basis for session_id too
        # if we want the session to be identified by "Alice".
        # If instavibe-app is providing "Alice" as kwargs["session_id"], then interaction_user_id becomes "Alice".
        # We'll use this as the session_id for get/create, effectively making session_id = user_id for these calls.
        desired_session_id_for_service = interaction_user_id
        span.set_attribute("session.user_id", interaction_user_id)
        span.set_attribute("session.desired_id", desired_session_id_for_service)
        logger.debug(f"Session management: app_name='{app_name}', user_id='{interaction_user_id}', desired_session_id='{desired_session_id_for_service}'")

        current_session_obj: Optional[Any] = None
        session_status = "unknown"
        try:
            with tracer.start_as_current_span("PlannerAgent.query.get_session") as get_session_span:
                get_session_span.set_attribute("session.user_id", interaction_user_id)
                get_session_span.set_attribute("session.id_lookup", desired_session_id_for_service)
                logger.info(f"Attempting to get session for user '{interaction_user_id}', session_id '{desired_session_id_for_service}'...")
                current_session_obj = self._runner.session_service.get_session(
                    app_name=app_name, user_id=interaction_user_id, session_id=desired_session_id_for_service
                )
                if current_session_obj:
                    logger.info(f"Found existing session: {current_session_obj.id} for user '{interaction_user_id}'")
                    get_session_span.set_attribute("session.status", "found")
                    get_session_span.set_attribute("session.retrieved_id", current_session_obj.id)
                    session_status = "found_existing"
                else:
                    logger.info(f"Session '{desired_session_id_for_service}' for user '{interaction_user_id}' not found. Will attempt to create.")
                    get_session_span.set_attribute("session.status", "not_found")
                    session_status = "requires_creation"
        except Exception as e_get:
            logger.warning(f"Exception during get_session for user '{interaction_user_id}', session_id '{desired_session_id_for_service}': {e_get}. Assuming session needs creation.", exc_info=True)
            current_session_obj = None
            session_status = "get_error"
            span.set_attribute("session.get_error", str(e_get))


        if current_session_obj is None:
            try:
                with tracer.start_as_current_span("PlannerAgent.query.create_session") as create_session_span:
                    create_session_span.set_attribute("session.user_id", interaction_user_id)
                    create_session_span.set_attribute("session.id_create_attempt", desired_session_id_for_service)
                    logger.info(f"Creating session for user '{interaction_user_id}', session_id '{desired_session_id_for_service}'...")
                    current_session_obj = self._runner.session_service.create_session(
                        app_name=app_name, user_id=interaction_user_id, session_id=desired_session_id_for_service
                    )
                    logger.info(f"Successfully created session: {current_session_obj.id} for user '{interaction_user_id}'.")
                    create_session_span.set_attribute("session.status", "created")
                    create_session_span.set_attribute("session.created_id", current_session_obj.id)
                    session_status = "created_new"
            except Exception as e_create:
                logger.error(f"Failed to create session for user '{interaction_user_id}' with session_id '{desired_session_id_for_service}': {e_create}", exc_info=True)
                span.set_attribute("error", True)
                span.set_attribute("error.message", f"Session management failure during create: {e_create}")
                span.set_attribute("session.status", "create_error")
                return {"error": f"Session management failure during create: {e_create}"}

        if not current_session_obj:
            logger.error(f"Critical error: Failed to obtain a session object for user '{interaction_user_id}', session_id '{desired_session_id_for_service}'.")
            span.set_attribute("error", True)
            span.set_attribute("error.message", "Failed to get or create a session.")
            span.set_attribute("session.status", "critical_failure")
            return {"error": "Failed to get or create a session."}

        span.set_attribute("session.final_status", session_status)
        span.set_attribute("session.final_id", current_session_obj.id)
        logger.debug(f"Successfully obtained session: {current_session_obj.id}")
        response_event_data = None

        async def _execute_run_and_get_first_event():
            """Helper async function to run the agent and get the first event."""
            # This will run within the ADK runner's main span if ADK creates one,
            # or we can wrap self._runner.run if needed, but let's assume ADK handles its internals for now.
            logger.info(f"Executing ADK runner for session_id: {current_session_obj.id}, user_id: {interaction_user_id}.")
            logger.debug(f"Runner input message for session {current_session_obj.id}: Role='user', Text='{query[:100]}...' (truncated if long)")

            event_count = 0
            async for event in self._runner.run(
                user_id=interaction_user_id,
                session_id=current_session_obj.id,
                new_message=Content(parts=[Part(text=query)], role="user")
            ):
                event_count += 1
                logger.debug(f"Received event {event_count} from runner for session {current_session_obj.id}. Type: {type(event)}")
                if hasattr(event, 'content') and event.content and hasattr(event.content, 'parts') and event.content.parts:
                     logger.debug(f"Event content part 0 text (if available): {event.content.parts[0].text[:100] if hasattr(event.content.parts[0], 'text') else 'N/A'}")
                elif isinstance(event, dict):
                    logger.debug(f"Event is a dict: {str(event)[:200]}")
                return event
            logger.warning(f"ADK runner finished for session {current_session_obj.id} without yielding any events after {event_count} iterations.")
            return None

        try:
            with tracer.start_as_current_span("PlannerAgent.query.adk_run_async") as adk_run_span:
                adk_run_span.set_attribute("adk.runner.session_id", current_session_obj.id)
                adk_run_span.set_attribute("adk.runner.user_id", interaction_user_id)
                logger.info(f"Calling asyncio.run for _execute_run_and_get_first_event, session: {current_session_obj.id}")
                response_event_data = asyncio.run(_execute_run_and_get_first_event())
                logger.info(f"Asyncio.run completed for session {current_session_obj.id}. Event data received: {'Yes' if response_event_data else 'No'}")
                adk_run_span.set_attribute("adk.runner.event_received", bool(response_event_data))
                if response_event_data and hasattr(response_event_data, 'content') and response_event_data.content and \
                   hasattr(response_event_data.content, 'parts') and response_event_data.content.parts and \
                   hasattr(response_event_data.content.parts[0], 'text'):
                    adk_run_span.set_attribute("adk.runner.response_text_length", len(response_event_data.content.parts[0].text))

        except Exception as e_run:
            logger.error(f"Error during asyncio.run(_execute_run_and_get_first_event) for session {current_session_obj.id}: {e_run}", exc_info=True)
            span.set_attribute("error", True)
            span.set_attribute("error.message", f"Agent execution error: {e_run}")
            if hasattr(e_run, "__class__"):
                 span.set_attribute("error.type", e_run.__class__.__name__)
            return {"error": f"Agent execution error: {e_run}"}

        if response_event_data:
            logger.debug(f"Raw response_event_data from runner (type {type(response_event_data)}): {str(response_event_data)[:200]}")
            span.set_attribute("response.type", type(response_event_data).__name__)
            if isinstance(response_event_data, dict):
                logger.info(f"PlannerAgent query returning dict response for session {current_session_obj.id}.")
                logger.debug(f"Returning dict response: {str(response_event_data)[:200]}")
                span.set_attribute("response.format", "dict")
                return response_event_data

            if hasattr(response_event_data, 'content') and response_event_data.content and \
               hasattr(response_event_data.content, 'parts') and response_event_data.content.parts and \
               hasattr(response_event_data.content.parts[0], 'text'):
                extracted_text = response_event_data.content.parts[0].text
                logger.info(f"PlannerAgent query extracted text content for session {current_session_obj.id}. Length: {len(extracted_text)}")
                logger.debug(f"Returning extracted text: {extracted_text[:200]}")
                span.set_attribute("response.format", "text_extracted")
                span.set_attribute("response.text_length", len(extracted_text))
                return {"output": extracted_text}

            logger.warning(f"Runner returned event of type {type(response_event_data)} for session {current_session_obj.id} that was not a dict and not directly convertible: {str(response_event_data)[:200]}")
            span.set_attribute("response.format", "unknown_conversion")
            return {"raw_event_data": str(response_event_data)}
        else:
            logger.warning(f"No response event received from agent execution for session {current_session_obj.id}.")
            span.set_attribute("response.format", "none")
            span.set_attribute("error", True) # Technically not an exception, but an unexpected outcome
            span.set_attribute("error.message", "No response event received from agent execution")
            return {"error": "No response event received from agent execution"}