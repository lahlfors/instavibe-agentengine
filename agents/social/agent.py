import sys
import os

# Determine the project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import datetime
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from google.adk.agents import LoopAgent, LlmAgent, BaseAgent
from google.adk.tools import FunctionTool
from .instavibe import get_person_posts,get_person_friends,get_person_id_by_name,get_person_attended_events
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from typing import AsyncGenerator
import logging
from opentelemetry import trace
from common.observability import setup_observability
from google.genai import types
from google.adk.agents.callback_context import CallbackContext
from typing import Optional

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
tracer = trace.get_tracer(__name__)
log = logging.getLogger(__name__)

class SocialLlmAgent(LlmAgent):
    def set_up(self):
        setup_observability()
        return self

    def query(self, **kwargs):
        with tracer.start_as_current_span(f"a2a.social.{self.name}") as span:
            span.set_attribute("agent.name", self.name)
            span.set_attribute("user.prompt", kwargs.get("message", ""))
            span.set_attribute("request.data", str(kwargs))
            try:
                response = super().__call__(**kwargs)
                span.set_attribute("agent.final_response", str(response))
                span.set_attribute("response.data", str(response))
                span.set_status(trace.StatusCode.OK)
                return response
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.StatusCode.ERROR, str(e))
                raise

class SocialLoopAgent(LoopAgent):
    def set_up(self):
        setup_observability()
        for agent in self.sub_agents:
            if hasattr(agent, "set_up"):
                agent.set_up()
        return self

    def query(self, **kwargs):
        # The LoopAgent's entry point is __call__
        return self(**kwargs)

def create_agent():
    class CheckCondition(BaseAgent):
        async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
            log.info(f"Summary: {ctx.session.state.get('summary')}")
            status = ctx.session.state.get("summary_status", "fail").strip()
            is_done = (status == "completed")
            yield Event(author=self.name, actions=EventActions(escalate=is_done))

    profile_agent = SocialLlmAgent(
        name="profile_agent",
        model="gemini-1.5-flash",
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
        model="gemini-1.5-flash",
        description="Generate a comprehensive social summary.",
        instruction="Your primary task is to synthesize social profile information into a single, comprehensive paragraph.",
        output_key="summary"
    )

    check_agent = SocialLlmAgent(
        name="check_agent",
        model="gemini-1.5-flash",
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

root_agent = create_agent()
