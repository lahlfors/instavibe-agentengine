import asyncio
import os
import logging
import json

from fastapi import FastAPI
import uvicorn

from a2a.server import A2AStarletteApplication
from a2a.types import AgentCard, AgentSkill, AgentCapabilities, Part, MessageSendParams
from a2a.agent_executor import AgentExecutor
from a2a.events import EventQueue, TaskUpdater
from a2a.request_context import RequestContext

# Attempt to import the OrchestrateServiceAgent
try:
    # The ADK agent instance is created within OrchestrateServiceAgent
    from agents.orchestrate.orchestrate_service_agent import OrchestrateServiceAgent
    # We'll need to instantiate OrchestrateServiceAgent, which in turn creates the ADK agent.
    # It requires remote_agent_addresses_str. This should come from env for the A2A server.
    REMOTE_AGENT_ADDRESSES_STR = os.environ.get("AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES", "")
    orchestrate_service_agent_instance = OrchestrateServiceAgent(remote_agent_addresses_str=REMOTE_AGENT_ADDRESSES_STR)
    # The actual ADK agent is orchestrate_service_agent_instance.host_agent_logic.root_agent
    # or similar, let's assume OrchestrateServiceAgent provides a way to get the ADK agent
    # or its tools directly. For now, we'll pass OrchestrateServiceAgent and it will delegate.
    ADK_ORCHESTRATE_AGENT_INSTANCE = orchestrate_service_agent_instance # Simplified for now
    SERVICE_NAME = os.environ.get("AGENT_SERVICE_NAME", "orchestrate-agent") # From orchestrate.agent
except ImportError as e:
    logging.error(f"Failed to import ADK orchestrate agent: {e}. Ensure agents.orchestrate.orchestrate_service_agent is accessible.")
    ADK_ORCHESTRATE_AGENT_INSTANCE = None
    SERVICE_NAME = "orchestrate-agent" # Fallback

logger = logging.getLogger(__name__)
# Ensure logging is configured. If a2a_common was providing this, it needs to be replicated or ensured.
# For now, basic config. In a real scenario, this would use the common logging setup.
if not logger.handlers: # Avoid duplicate handlers if already configured
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
    # Potentially call setup_google_cloud_logging if that utility is made available/replicated
    # from instavibe_common_lib.logging_utils import setup_google_cloud_logging (after refactor)
    # setup_google_cloud_logging(service_name=SERVICE_NAME)


# Configuration
AGENT_NAME = SERVICE_NAME
AGENT_DESCRIPTION = "Orchestrator agent that delegates tasks to specialized remote agents based on user requests."

HOST = os.environ.get("A2A_HOST", "0.0.0.0")
PORT = int(os.environ.get("A2A_PORT", os.environ.get("PORT", 8080)))
# BASE_URL will be critical and should be the public URL of this A2A server when deployed.
# This will be set by an environment variable like A2A_PUBLIC_BASE_URL or SERVICE_URL from Cloud Run.
A2A_PUBLIC_BASE_URL = os.environ.get("A2A_PUBLIC_BASE_URL")
BASE_URL = A2A_PUBLIC_BASE_URL if A2A_PUBLIC_BASE_URL else f"http://{HOST}:{PORT}"


class OrchestratorAgentExecutor(AgentExecutor):
    def __init__(self, adk_orchestrator: OrchestrateServiceAgent):
        if adk_orchestrator is None:
            raise ValueError("ADK Orchestrator (OrchestrateServiceAgent) is None. Cannot initialize Executor.")
        self.adk_orchestrator = adk_orchestrator
        # The actual ADK Agent with tools is within HostAgent, accessed via OrchestrateServiceAgent
        self.host_agent_logic = self.adk_orchestrator.host_agent_logic
        if not self.host_agent_logic or not hasattr(self.host_agent_logic, 'send_task'):
            raise ValueError("HostAgent logic or send_task tool not found in ADK Orchestrator.")
        logger.info(f"OrchestratorAgentExecutor initialized with ADK orchestrator.")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # For the orchestrator, the input might be more complex than a simple string.
        # It might be a JSON object specifying the target agent and the message.
        # The `InstavibeWorkflowAgent` sends a JSON string payload.
        json_input_str = context.get_user_input() # This should be the JSON string
        if not json_input_str:
            logger.warning("No user input (JSON string) found in request context for Orchestrator.")
            # updater.fail(...) would be appropriate here if we had it.
            return

        task = context.current_task
        if not task:
            task = context.new_task() # This creates a new task ID
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)
        logger.info(f"OrchestratorAgentExecutor: Executing task {task.id} with input: {json_input_str[:200]}...")

        try:
            input_data = json.loads(json_input_str)
            target_agent_name = input_data.get("agent_name") # Or however the workflow agent structures it
            message_for_target_agent = input_data.get("message") # Or "payload", "query" etc.
            # The `InstavibeWorkflowAgent` sends:
            # {
            #     "user_name": ..., "user_id_context": ..., "confirmed_plan": ...,
            #     "invite_message": ..., "task_description": ...
            # }
            # This doesn't directly map to `agent_name` and `message` for `send_task`.
            # This implies the Orchestrator's ADK agent (HostAgent) instruction
            # and tools need to be designed to parse this richer input structure,
            # or this A2A server needs to adapt it.

            # For now, let's assume the `HostAgent`'s `send_task` tool is what we want to call,
            # and it expects `agent_name` and `message`.
            # The `HostAgent` itself is an LLM agent that uses `send_task` as a tool.
            # So, the A2A call to the orchestrator should provide a query that makes the
            # orchestrator LLM decide to use its `send_task` tool.

            # The input from InstavibeWorkflowAgent for "post_event" is:
            # orchestrator_input_payload = json.dumps(orchestrator_input_details)
            # orchestrator_input_details = {
            # "user_name": user_name, "user_id_context": agent_session_user_id,
            # "confirmed_plan": confirmed_plan, "invite_message": edited_invite_message,
            # "task_description": f"User '{user_name}' wants to create an event..."
            # }
            # This entire JSON string is the `query` for the orchestrator's ADK LLM agent.

            adk_agent_to_run = self.host_agent_logic.root_agent # The LlmAgent instance from HostAgent
            if not adk_agent_to_run:
                raise ValueError("ADK root_agent not found in HostAgent logic.")

            loop = asyncio.get_event_loop()
            # The query is the full JSON string from the workflow agent
            adk_agent_response_obj = await loop.run_in_executor(None, adk_agent_to_run.run, json_input_str)

            logger.info(f"ADK orchestrator agent LLM executed. Response type: {type(adk_agent_response_obj)}")
            logger.debug(f"ADK orchestrator agent LLM response: {str(adk_agent_response_obj)[:500]}")

            # The response from the orchestrator's ADK agent run (which internally calls tools like send_task)
            # will be the textual narration from the LLM.
            response_text = ""
            if isinstance(adk_agent_response_obj, str):
                response_text = adk_agent_response_obj
            elif isinstance(adk_agent_response_obj, dict) and "output" in adk_agent_response_obj: # Common ADK pattern
                response_text = str(adk_agent_response_obj['output'])
            else:
                response_text = str(adk_agent_response_obj) # Fallback

            # The InstavibeWorkflowAgent expects a simple text response from the orchestrator A2A call.
            updater.add_artifact(parts=[Part(text=response_text)], mime_type="text/plain")
            updater.complete()
            logger.info(f"Orchestrator task {task.id} completed. Response: {response_text[:200]}")

        except json.JSONDecodeError as je:
            logger.error(f"Failed to parse input JSON for task {task.id}: {je}", exc_info=True)
            updater.fail(message=f"Invalid input format: {str(je)}")
        except Exception as e:
            logger.error(f"Error during ADK orchestrator agent execution for task {task.id}: {e}", exc_info=True)
            updater.fail(message=f"Error executing orchestrator agent: {str(e)}")


async def create_orchestrator_a2a_server():
    if ADK_ORCHESTRATE_AGENT_INSTANCE is None:
        logger.critical("ADK Orchestrator (OrchestrateServiceAgent) is not loaded. Cannot start A2A server.")
        return None

    logger.info(f"Creating A2A server for Orchestrator Agent: {AGENT_NAME}")
    logger.info(f"Configured Base URL for Agent Card: {BASE_URL}")
    if not A2A_PUBLIC_BASE_URL:
        logger.warning("A2A_PUBLIC_BASE_URL environment variable is not set. The AgentCard URL might be incorrect for external discovery.")


    agent_capabilities = AgentCapabilities(streaming=True) # Orchestrator might involve multiple tool calls.

    # The primary "skill" of the orchestrator is to receive a complex user request
    # (often as a JSON blob describing the task) and then use its internal LLM
    # and tools (like `send_task` to other agents) to fulfill it.
    orchestrator_main_skill = AgentSkill(
        id='orchestrate_task',
        name='Orchestrate Complex Task',
        description='Receives a task description (often in JSON format), understands the intent, and coordinates with other specialized agents to achieve the goal. For example, posting an event by interacting with social agents.',
        inputModes=["application/json"], # It expects a JSON string as input
        outputModes=["text/plain"] # It provides a textual summary/confirmation of its actions
    )

    agent_card = AgentCard(
        name=AGENT_NAME,
        description=AGENT_DESCRIPTION,
        url=BASE_URL, # This MUST be the publicly accessible URL of this A2A server
        version="1.0.0",
        defaultInputModes=["application/json"], # Orchestrator expects a JSON payload describing the task
        defaultOutputModes=["text/plain"],    # It will respond with a status or confirmation
        capabilities=agent_capabilities,
        skills=[orchestrator_main_skill]
    )

    executor = OrchestratorAgentExecutor(ADK_ORCHESTRATE_AGENT_INSTANCE)
    a2a_app = A2AStarletteApplication(agent_card=agent_card, executor=executor)

    logger.info(f"A2AStarletteApplication created for {AGENT_NAME}.")
    return a2a_app

async def serve():
    # Ensure OrchestrateServiceAgent is initialized (which depends on env vars)
    # This is done globally for now.
    if ADK_ORCHESTRATE_AGENT_INSTANCE is None:
        logger.error(f"ADK Orchestrator instance not available. Cannot start server.")
        return

    a2a_starlette_app = await create_orchestrator_a2a_server()
    if a2a_starlette_app:
        config = uvicorn.Config(a2a_starlette_app, host=HOST, port=PORT, log_level="info")
        server = uvicorn.Server(config)
        logger.info(f"Starting Uvicorn server for {AGENT_NAME} on {HOST}:{PORT}")
        await server.serve()
    else:
        logger.error(f"Could not create A2A server application for {AGENT_NAME}. Server will not start.")

if __name__ == "__main__":
    # This allows running the server directly for testing.
    # Environment variables like AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES,
    # GOOGLE_CLOUD_PROJECT, etc., need to be set.
    logger.info(f"Attempting to start {AGENT_NAME} A2A server directly...")
    # Initialize OrchestrateServiceAgent if not done, though it's global here
    if ADK_ORCHESTRATE_AGENT_INSTANCE is None:
        logger.error("Cannot start: ADK_ORCHESTRATE_AGENT_INSTANCE is None. Check environment variables for OrchestrateServiceAgent init.")
    else:
        asyncio.run(serve())
else:
    # For Uvicorn run by a process manager: `uvicorn agents.orchestrate.a2a_server:app`
    # We need to provide `app` at module level, initialized asynchronously.
    # This is a common pattern for ASGI apps.
    app_instance_for_uvicorn = None

    async def get_app_instance():
        global app_instance_for_uvicorn
        if app_instance_for_uvicorn is None:
            app_instance_for_uvicorn = await create_orchestrator_a2a_server()
        return app_instance_for_uvicorn

    # If uvicorn can handle an awaitable, this would be ideal.
    # Or, some ASGI servers might pick up an 'app' factory.
    # For now, if not __main__, this setup is more for Gunicorn/Uvicorn to discover.
    # A simple way for `uvicorn module:app` is to have `app` defined after an async setup in some cases,
    # but that can be tricky. The `if __name__ == "__main__"` is the most direct for `python -m`.
    # If this file is imported by another that then runs uvicorn programmatically, that's another way.
    # Let's try to define `app` for uvicorn, but it needs to be created in an async context.
    # This part might need adjustment based on how it's actually run by a production ASGI server.
    # A common pattern is to have a startup event in FastAPI to initialize async resources.
    # A2AStarletteApplication itself is a Starlette app.

    # This assignment will likely fail if `create_orchestrator_a2a_server` isn't called.
    # Uvicorn typically needs `app` to be the Starlette/FastAPI app instance.
    # app = create_orchestrator_a2a_server() # This won't work directly as it's async

    # Factory function for Uvicorn when using --factory
    async def serve_app_factory():
        # Ensure OrchestrateServiceAgent is initialized (which depends on env vars)
        if ADK_ORCHESTRATE_AGENT_INSTANCE is None:
            logger.error("ADK Orchestrator instance not available for factory. Check environment variables for OrchestrateServiceAgent init.")
            # This state is problematic for a factory; ideally, dependencies are ready or handled by the app framework.
            # Raising an error or returning a dummy app might be options.
            # For now, assume global init worked or A2AStarletteApplication handles it.
            # A2AStarletteApplication will raise if executor's agent is None.
            pass # Let create_orchestrator_a2a_server handle the None check for agent

        app = await create_orchestrator_a2a_server()
        if app is None:
            raise RuntimeError("Failed to create A2A application instance in factory.")
        return app

# Example of how you might run this with uvicorn programmatically (not used by CMD directly but for understanding)
# if __name__ == "__main__":
#     # ... (existing __main__ block) ...
# else:
#     # This block is tricky for top-level `app` assignment for uvicorn without running full async setup.
#     # The factory pattern in the CMD is preferred.
#     pass
