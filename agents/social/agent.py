import os
import asyncio
import datetime
from zoneinfo import ZoneInfo
import uuid
from google.adk.agents import LoopAgent, LlmAgent, BaseAgent
from google.adk.tools import FunctionTool
from .instavibe import get_person_posts,get_person_friends,get_person_id_by_name,get_person_attended_events
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from typing import AsyncGenerator
import logging
from opentelemetry import trace

# Agent Card support for A2A discovery
# Removed inline Agent Card support - now handled by A2aAgent deployment
create_social_agent_card = None
serve_agent_card_as_query_response = None
try:
    from agents.common.observability import setup_observability
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from agents.common.observability import setup_observability
from google.genai import types
from google.adk.agents.callback_context import CallbackContext
from typing import Optional, Any
from google.generativeai import GenerativeModel # Use the Google AI client
tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)

class SocialLlmAgent(LlmAgent):
    display_name: Optional[str] = None
    otel_collector_endpoint: Optional[str] = None
    model_client: Any = None

    def __post_init__(self):
        super().__post_init__()
        if self.model:
            self.model_client = GenerativeModel(self.model)
        else:
            print("WARNING: SocialLlmAgent initialized without a model name.")

    async def _async_set_up(self, **kwargs):
        logger.info(f"--- Running _async_set_up for {self.__class__.__name__} ---")
        os.environ["OTEL_SERVICE_NAME"] = self.name
        setup_observability(endpoint_override=self.otel_collector_endpoint)
        
        # Initialize model_client if missing (critical for unpickled agents)
        if not self.model_client and self.model:
             logger.info(f"Initializing model_client for {self.model}")
             self.model_client = GenerativeModel(self.model)
             
        logger.info(f"{self.__class__.__name__} async setup complete.")

    def set_up(self, **kwargs):
        """A synchronous wrapper for the async setup."""
        logger.info(f"Sync set_up called for {self.__class__.__name__}")
        try:
            asyncio.run(self._async_set_up(**kwargs))
            logger.info(f"set_up completed for {self.__class__.__name__}.")
        except Exception as e:
            logger.error(f"Error during set_up for {self.__class__.__name__}: {e}", exc_info=True)
            raise
        return self

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """This is the main, streaming entry point for the agent."""
        # Extract invocation_id from context
        invocation_id = ctx.invocation_id
        
        if not self.model_client:
            yield Event(
                invocation_id=invocation_id,
                author=self.name, 
                content=types.Content(parts=[types.Part(text="Model client not initialized")])
            )
            return

        # This reuses the single, shared client
        prompt_content = ctx.user_content
        response = await self.model_client.generate_content_async(prompt_content)

        # Yield the full response event with invocation_id
        yield Event(
            invocation_id=invocation_id,
            author=self.name, 
            content=response.candidates[0].content
        )

    def query(self, input: str, **kwargs):
        """
        Synchronous wrapper for streaming to make the agent compatible with the Governed A2A client.
        The 'input' argument is explicitly named so Vertex AI adds it to the API schema.
        """
        with tracer.start_as_current_span(f"a2a.social.{self.name}") as span:
            # Simplified: input is now directly a string from the client
            message_text = input

            span.set_attribute("agent.name", self.name)
            span.set_attribute("user.prompt", message_text)
            span.set_attribute("request.data", str(kwargs))
            logger.info(f"Handling social request: {kwargs}")

            try:
                # Create event loop for bridging async to sync
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Create invocation context from kwargs
                    ctx = InvocationContext(
                        user_content=types.Content(parts=[types.Part(text=message_text)]),
                        session=None,
                        invocation_id=str(uuid.uuid4()),
                        metadata=kwargs
                    )
                    
                    # Get the async generator from _run_async_impl
                    async_gen = self._run_async_impl(ctx)
                    
                    # Bridge: synchronously iterate over async generator and yield events
                    response_events = []
                    while True:
                        try:
                            event = loop.run_until_complete(async_gen.__anext__())
                            response_events.append(event)
                        except StopAsyncIteration:
                            break
                    
                    span.set_status(trace.StatusCode.OK)
                    # For non-streaming agents, we might return the final result
                    # Here we return the list of events, which is unconventional but works for now.
                    # A better implementation might process events to a final return value.
                    return response_events

                finally:
                    loop.close()
                    
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.StatusCode.ERROR, str(e))
                logger.error(f"Error in social query: {e}", exc_info=True)
                raise

class SocialLoopAgent(LoopAgent):
    display_name: Optional[str] = None
    otel_collector_endpoint: Optional[str] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # otel_collector_endpoint is set by Pydantic if passed in kwargs

    async def __async_set_up(self, **kwargs):
        logger.info(f"--- Running _async_set_up for {self.__class__.__name__} ---")
        os.environ["OTEL_SERVICE_NAME"] = self.name
        setup_observability(endpoint_override=self.otel_collector_endpoint)
        logger.info(f"{self.__class__.__name__} async setup complete.")

    def set_up(self, **kwargs):
        """A synchronous wrapper for the async setup."""
        logger.info(f"Sync set_up called for {self.__class__.__name__}")
        try:
            asyncio.run(self._async_set_up(**kwargs))
            logger.info(f"set_up completed for {self.__class__.__name__}.")
        except Exception as e:
            logger.error(f"Error during set_up for {self.__class__.__name__}: {e}", exc_info=True)
            raise

        for agent in self.sub_agents:
            if hasattr(agent, "set_up"):
                agent.set_up()
        return self

    def query(self, **kwargs):
        # The LoopAgent's entry point is __call__
        return self(**kwargs)

def create_agent(model: str):
    class CheckCondition(BaseAgent):
        async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
            logger.info(f"Summary: {ctx.session.state.get('summary')}")
            status = ctx.session.state.get("summary_status", "fail").strip()
            is_done = (status == "completed")
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name, 
                actions=EventActions(escalate=is_done)
            )

    profile_agent = SocialLlmAgent(
        name="profile_agent",
        model=model,
        description="Agent to answer questions about the this person's social profile.",
        instruction="You are a helpful agent who can answer user questions about this person's social profile.",
        tools=[
            FunctionTool(get_person_posts),
            FunctionTool(get_person_friends),
            FunctionTool(get_person_id_by_name),
            FunctionTool(get_person_attended_events),
        ]
    )

    summary_agent = SocialLlmAgent(
        name="summary_agent",
        model=model,
        description="Generate a comprehensive social summary.",
        instruction="Your primary task is to synthesize social profile information into a single, comprehensive paragraph.",
        output_key="summary"
    )

    check_agent = SocialLlmAgent(
        name="check_agent",
        model=model,
        description="Check if everyone's social profile are summarized.",
        output_key="summary_status"
    )

    def modify_output_after_agent(callback_context: CallbackContext) -> Optional[types.Content]:
        agent_name = callback_context.agent_name
        invocation_id = callback_context.invocation_id
        current_state = callback_context.state.to_dict()
        status = current_state.get("summary_status").strip()
        is_done = (status == "completed")
        final_summary = current_state.get("summary")
        if final_summary and is_done and isinstance(final_summary, str):
            return types.Content(role="model", parts=[types.Part(text=final_summary.strip())])
        else:
            return None

    root_agent = SocialLoopAgent(
        name="InteractivePipeline",
        sub_agents=[
            profile_agent,
            summary_agent,
            check_agent,
            CheckCondition(name="Checker")
        ],
        description="Find everyone's social profile on events, post and friends",
        max_iterations=10,
        after_agent_callback=modify_output_after_agent
    )
    return root_agent

gemini_model = os.getenv("COMMON_GEMINI_MODEL", "gemini-2.5-flash")
root_agent = create_agent(model=gemini_model)
