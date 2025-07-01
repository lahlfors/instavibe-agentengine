import asyncio
import os
import logging

from fastapi import FastAPI # Used by A2AStarletteApplication
import uvicorn

from a2a.server import A2AStarletteApplication
from a2a.types import AgentCard, AgentSkill, AgentCapabilities, Part
from a2a.agent_executor import AgentExecutor
from a2a.events import EventQueue, TaskUpdater
from a2a.request_context import RequestContext

# Import the ADK agent type for type hinting
from google.adk.agents import Agent as AdkAgentType
from google.genai import types # For types.Content if used by ADK agent response

# Try to get some metadata from the original agent module for AgentCard details
try:
    from agents.social.agent import SERVICE_NAME as SOCIAL_SERVICE_NAME_FROM_MODULE
    # Assuming social agent might have a similar AGENT_INSTRUCTION or a default description
    SOCIAL_AGENT_DEFAULT_DESCRIPTION = "Social agent for profile and activity summarization."
except ImportError as e:
    logging.warning(f"Could not import from agents.social.agent for metadata: {e}. Using fallbacks.")
    SOCIAL_SERVICE_NAME_FROM_MODULE = "social-agent"
    SOCIAL_AGENT_DEFAULT_DESCRIPTION = "Social agent for profile and activity summarization."

logger = logging.getLogger(__name__)
# Basic logging configuration. AdkApp's setup can enhance this.
if not logger.handlers: # Avoid duplicate basicConfig if already set by another module
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

# Configuration for the A2A server component
A2A_UVICORN_PORT_SOCIAL = int(os.environ.get("A2A_UVICORN_PORT_SOCIAL", 8002)) # Internal port for Uvicorn
AGENT_NAME_FOR_CARD = SOCIAL_SERVICE_NAME_FROM_MODULE
AGENT_DESCRIPTION_FOR_CARD = SOCIAL_AGENT_DEFAULT_DESCRIPTION


class SocialAgentExecutor(AgentExecutor):
    def __init__(self, adk_agent_instance: AdkAgentType):
        if adk_agent_instance is None:
            raise ValueError("ADK Social agent instance is None for SocialAgentExecutor.")
        self.adk_agent = adk_agent_instance
        logger.info(f"SocialAgentExecutor initialized with ADK agent: {getattr(self.adk_agent, 'name', 'Unnamed ADK Agent')}")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        query = context.get_user_input()
        task = context.current_task or context.new_task()
        if not context.current_task:
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        if not query:
            logger.warning(f"No user input found in request context for SocialAgentExecutor task {task.id}.")
            updater.fail(message="User input is missing for social agent.")
            return

        logger.info(f"SocialAgentExecutor: Executing task {task.id} for query: {query[:100]}...")
        try:
            loop = asyncio.get_event_loop()
            # Assuming self.adk_agent.run is the entry point for the social ADK agent (LoopAgent)
            adk_agent_response = await loop.run_in_executor(None, self.adk_agent.run, query)

            logger.info(f"ADK social agent executed for task {task.id}. Result type: {type(adk_agent_response)}")
            logger.debug(f"ADK social agent result for task {task.id}: {str(adk_agent_response)[:200]}")

            final_text_response = ""
            # Example from previous version: Social agent's LoopAgent used a 'modify_output_after_agent'
            # callback that returned a types.Content object.
            if isinstance(adk_agent_response, types.Content) and adk_agent_response.parts:
                # Extract text from the first part, assuming it's the primary textual response
                part = adk_agent_response.parts[0]
                if hasattr(part, 'text') and part.text:
                    final_text_response = part.text
                else: # Fallback if no text attribute or empty
                    final_text_response = str(adk_agent_response) # Or handle other part types
            elif isinstance(adk_agent_response, str):
                final_text_response = adk_agent_response
            elif isinstance(adk_agent_response, dict) and 'output' in adk_agent_response: # Common ADK LlmAgent pattern
                 final_text_response = str(adk_agent_response['output'])
            else: # Generic fallback
                final_text_response = str(adk_agent_response)

            updater.add_artifact(parts=[Part(text=final_text_response)], mime_type="text/plain")
            updater.complete()
            logger.info(f"Task {task.id} completed successfully by SocialAgentExecutor.")

        except Exception as e:
            logger.error(f"Error during ADK social agent execution for task {task.id}: {e}", exc_info=True)
            updater.fail(message=f"Error executing social agent: {str(e)}")


def create_social_a2a_server(passed_adk_social_agent: AdkAgentType) -> A2AStarletteApplication:
    """
    Creates and returns the A2AStarletteApplication for the Social agent.
    Args:
        passed_adk_social_agent: The instantiated core ADK Agent for the social agent.
    """
    if passed_adk_social_agent is None:
        logger.critical("Passed ADK Social Agent is None. Cannot create A2A server.")
        raise ValueError("ADK Social Agent instance is required by create_social_a2a_server.")

    public_base_url = os.environ.get("A2A_PUBLIC_BASE_URL", f"http://localhost:{A2A_UVICORN_PORT_SOCIAL}")

    logger.info(f"Creating A2A server component for Social Agent: {AGENT_NAME_FOR_CARD}")
    logger.info(f"AgentCard URL will be: {public_base_url}")

    agent_capabilities = AgentCapabilities(streaming=True)
    social_skill = AgentSkill(
        id='get_social_profile_summary',
        name='Get Social Profile Summary',
        description='Finds and summarizes social profiles, including posts, friends, and event attendance.'
    )

    agent_card = AgentCard(
        name=AGENT_NAME_FOR_CARD,
        description=AGENT_DESCRIPTION_FOR_CARD,
        url=public_base_url,
        version="1.0.0",
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"],
        capabilities=agent_capabilities,
        skills=[social_skill]
    )

    executor = SocialAgentExecutor(passed_adk_social_agent)

    a2a_custom_app = FastAPI()
    @a2a_custom_app.get("/_a2a_health")
    async def health():
      return {"status": "ok", "agent_name": AGENT_NAME_FOR_CARD, "a2a_interface": "active"}

    a2a_starlette_app = A2AStarletteApplication(
        agent_card=agent_card,
        executor=executor,
        app=a2a_custom_app
    )

    logger.info(f"A2AStarletteApplication created for {AGENT_NAME_FOR_CARD} with AgentCard URL: {public_base_url}.")
    return a2a_starlette_app

# `if __name__ == "__main__":` block for direct Uvicorn execution is removed.
# Uvicorn will be started by AdkApp's setup_fn in deploy.py.
