# agents/social/a2a_server.py
import asyncio
import os
import logging
from fastapi import FastAPI

# python_a2a model imports
from python_a2a import AgentCard, AgentSkill
from python_a2a.models import Message, MessageRole, TextContent # Final correct imports
# Other necessary imports from python_a2a
from python_a2a.server import A2AServer
from python_a2a.agent import AgentExecutor, Task
from python_a2a.server.events import EventQueue, TaskUpdater
from python_a2a.server.request_context import RequestContext
from python_a2a.client.helpers import create_text_message_object # Review usage with new MessageRole

# ADK and agent-specific imports
from google.adk.agents import Agent as AdkAgentType
from google.genai import types as google_genai_types # For types.Content
# from agents.social.agent import SocialAgent # This import is unused and likely incorrect; actual agent instance is passed in.

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

# Configuration for the A2A server component
A2A_UVICORN_PORT_SOCIAL = int(os.environ.get("A2A_UVICORN_PORT_SOCIAL", 8002))
AGENT_NAME_FOR_CARD = "Social A2A Agent" # Consistent naming
AGENT_DESCRIPTION_FOR_CARD = "Social agent for profile and activity summarization, A2A enabled (python-a2a v0.5.0)."

class SocialAgentExecutor(AgentExecutor):
    def __init__(self, agent: AdkAgentType):
        if agent is None:
            raise ValueError("ADK Social agent instance is None for SocialAgentExecutor.")
        self.agent = agent
        logger.info(f"SocialAgentExecutor initialized with ADK agent: {getattr(self.agent, 'name', 'Unnamed ADK Agent')}")

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        query = context.get_user_input()

        task = context.current_task
        if not task:
            task_id = f"task_{os.urandom(8).hex()}"
            context_id_for_task = getattr(context.message, 'messageId', task_id)
            task = Task(id=task_id, contextId=context_id_for_task, status="working")
            event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        if not query:
            logger.warning(f"No user input found for Social task {task.id}.")
            updater.fail(message="User input is missing for social agent.")
            return

        logger.info(f"SocialAgentExecutor: Executing task {task.id} for query: {query[:100]}...")
        try:
            loop = asyncio.get_event_loop()
            adk_agent_response = await loop.run_in_executor(None, self.agent.run, query)

            logger.info(f"ADK social agent executed for task {task.id}. Result type: {type(adk_agent_response)}")

            final_text_response = ""
            if isinstance(adk_agent_response, google_genai_types.Content) and adk_agent_response.parts:
                part_data = adk_agent_response.parts[0]
                if hasattr(part_data, 'text') and part_data.text:
                    final_text_response = part_data.text
                else:
                    final_text_response = str(adk_agent_response)
            elif isinstance(adk_agent_response, str):
                final_text_response = adk_agent_response
            elif isinstance(adk_agent_response, dict) and 'output' in adk_agent_response:
                 final_text_response = str(adk_agent_response['output'])
            else:
                final_text_response = str(adk_agent_response)

            response_a2a_message = create_text_message_object(content=final_text_response, role="agent")
            if hasattr(response_a2a_message, 'taskId') and task.id: response_a2a_message.taskId = task.id
            if hasattr(response_a2a_message, 'contextId') and task.contextId: response_a2a_message.contextId = task.contextId
            event_queue.enqueue_event(response_a2a_message)

            task.status = "completed"
            event_queue.enqueue_event(task)
            logger.info(f"Task {task.id} completed successfully by SocialAgentExecutor.")

        except Exception as e:
            logger.error(f"Error during ADK social agent execution for task {task.id}: {e}", exc_info=True)
            task.status = "failed"
            task.error = {"message": f"Error executing social agent: {str(e)}"} # Add error to task
            event_queue.enqueue_event(task)


def create_social_a2a_server(passed_adk_social_agent: AdkAgentType) -> A2AServer:
    if passed_adk_social_agent is None:
        logger.critical("Passed ADK Social Agent is None. Cannot create A2A server.")
        raise ValueError("ADK Social Agent instance is required by create_social_a2a_server.")

    public_base_url = os.environ.get("A2A_PUBLIC_BASE_URL", f"http://localhost:{A2A_UVICORN_PORT_SOCIAL}")

    logger.info(f"Creating A2A server component for Social Agent: {AGENT_NAME_FOR_CARD}")
    logger.info(f"AgentCard URL will be: {public_base_url}")

    skill = AgentSkill(
        id="social_profile_summary_skill",
        name="Social Profile Summarizer",
        description="Summarizes social media profiles and activities.",
    )
    # AgentCapabilities removed, streaming is handled by method implementation

    agent_card = AgentCard(
        name=AGENT_NAME_FOR_CARD,
        description=AGENT_DESCRIPTION_FOR_CARD,
        url=public_base_url,
        version="1.0.0",
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"],
        skills=[skill]
        # capabilities attribute removed
    )

    executor = SocialAgentExecutor(passed_adk_social_agent)

    custom_fastapi_app = FastAPI(title=f"{AGENT_NAME_FOR_CARD} Custom Routes")
    @custom_fastapi_app.get("/_a2a_health")
    async def health():
      return {"status": "ok", "agent_name": AGENT_NAME_FOR_CARD, "a2a_interface": "active"}

    a2a_server_instance = A2AServer(
        agent_card=agent_card,
        agent_executor=executor,
        app=custom_fastapi_app,
    )
    logger.info(f"A2AServer instance created for {AGENT_NAME_FOR_CARD}.")
    return a2a_server_instance

# Standalone execution block removed.
