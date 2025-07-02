# agents/social/a2a_server.py
import asyncio
import os
import logging
from fastapi import FastAPI

# python_a2a model imports
from python_a2a import AgentCard, AgentSkill
from python_a2a.models import Message, MessageRole, TextContent # Final correct imports
# Other necessary imports from python_a2a
from python_a2a.server import A2AServer, RequestContext # Added RequestContext here
from typing import AsyncIterable # For stream handler type hint, though may not be used if not streaming
# AgentExecutor, Task, EventQueue, TaskUpdater are removed
# from python_a2a.client.helpers import create_text_message_object # Will construct Message manually

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

# SocialAgentExecutor class removed

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

    agent_card = AgentCard(
        name=AGENT_NAME_FOR_CARD,
        description=AGENT_DESCRIPTION_FOR_CARD,
        url=public_base_url,
        version="1.0.0",
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"],
        skills=[skill]
    )

    async def on_message_handler(request_context: RequestContext, message: Message) -> Message:
        query = None
        if message.parts and isinstance(message.parts[0], TextContent):
            query = message.parts[0].text

        if not query:
            logger.warning("No user input query found in message parts for Social agent.")
            return Message(role=MessageRole.AGENT, parts=[TextContent(text="Error: User input is missing.")])

        logger.info(f"Social Agent on_message_handler received query: {query[:100]}...")
        try:
            loop = asyncio.get_event_loop()
            # Assuming passed_adk_social_agent.run or .invoke is synchronous
            adk_agent_response = await loop.run_in_executor(None, passed_adk_social_agent.invoke, query)

            logger.info(f"ADK social agent executed. Result type: {type(adk_agent_response)}")

            final_text_response = ""
            if isinstance(adk_agent_response, google_genai_types.Content) and adk_agent_response.parts: # Specific to ADK GoogleLlm
                part_data = adk_agent_response.parts[0]
                if hasattr(part_data, 'text') and part_data.text:
                    final_text_response = part_data.text
                else:
                    final_text_response = str(adk_agent_response) # Fallback
            elif isinstance(adk_agent_response, str):
                final_text_response = adk_agent_response
            elif isinstance(adk_agent_response, dict) and 'output' in adk_agent_response: # Generic dict output
                 final_text_response = str(adk_agent_response['output'])
            else:
                final_text_response = str(adk_agent_response) # Fallback to stringifying

            return Message(role=MessageRole.AGENT, parts=[TextContent(text=final_text_response)])
        except Exception as e:
            logger.error(f"Error during ADK social agent execution: {e}", exc_info=True)
            return Message(role=MessageRole.AGENT, parts=[TextContent(text=f"Error executing social agent: {str(e)}")])

    async def on_message_stream_handler(request_context: RequestContext, message: Message) -> AsyncIterable[Message]:
        logger.warning("Streaming not implemented for Social Agent.")
        yield Message(role=MessageRole.AGENT, parts=[TextContent(text="Error: Streaming not supported by this agent.")])
        # raise NotImplementedError("Streaming not implemented for Social Agent.")

    custom_fastapi_app = FastAPI(title=f"{AGENT_NAME_FOR_CARD} Custom Routes")
    @custom_fastapi_app.get("/_a2a_health")
    async def health():
      return {"status": "ok", "agent_name": AGENT_NAME_FOR_CARD, "a2a_interface": "active"}

    a2a_server_instance = A2AServer(
        agent_card=agent_card,
        on_message=on_message_handler,
        on_message_stream=on_message_stream_handler,
        app=custom_fastapi_app,
    )
    logger.info(f"A2AServer instance created for {AGENT_NAME_FOR_CARD} with new handlers.")
    return a2a_server_instance
