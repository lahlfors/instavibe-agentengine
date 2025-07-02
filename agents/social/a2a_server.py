# agents/social/a2a_server.py
import asyncio
import os
import logging
from fastapi import FastAPI

# python_a2a model imports
from python_a2a import AgentCard, AgentSkill
from python_a2a.models import Message, MessageRole, TextContent # Final correct imports
# Other necessary imports from python_a2a
from python_a2a.server import A2AServer # Removed RequestContext from this line
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

    # Import DataPart for structured message handling
    from python_a2a.models import DataPart
    import json # For potential stringifying if ADK agent returns dict

    async def on_message_handler(message: Message) -> Message:
        logger.info(f"Social A2A on_message_handler received message: {message.model_dump_json(indent=2)}")
        try:
            if not message.parts or not isinstance(message.parts[0], DataPart) or message.parts[0].type != "data":
                logger.warning("Invalid message format for Social agent: Expected a DataPart with type 'data'.")
                return Message(role=MessageRole.AGENT, parts=[TextContent(text="Invalid message format: Expected a DataPart with type 'data'.")])

            input_data_dict = message.parts[0].data

            if not isinstance(input_data_dict, dict):
                logger.warning(f"Social agent DataPart content is not a dict: {type(input_data_dict)}")
                return Message(role=MessageRole.AGENT, parts=[TextContent(text="Invalid DataPart content for Social agent: Expected a JSON object/dict.")])

            query = input_data_dict.get("query")
            if not query or not isinstance(query, str):
                logger.warning("Social agent: 'query' not found in DataPart or not a string.")
                return Message(role=MessageRole.AGENT, parts=[TextContent(text="Error: 'query' missing or invalid in input data for Social agent.")])

            logger.info(f"Social Agent extracted query: {query[:100]}...")

            loop = asyncio.get_event_loop()
            # passed_adk_social_agent.invoke is synchronous (typical for ADK LoopAgent/LlmAgent)
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

    async def on_message_stream_handler(message: Message) -> AsyncIterable[Message]: # Removed request_context
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
