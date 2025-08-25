import os
import logging
import asyncio
import nest_asyncio
from dotenv import load_dotenv
from typing import Any, Dict, Optional, AsyncGenerator
from google.adk.agents import BaseAgent, LlmAgent, LoopAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from . import agent as planner_agent_module
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from opentelemetry import trace

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
nest_asyncio.apply()
tracer = trace.get_tracer(__name__)

class PlannerAgent(BaseAgent):
    """An agent that helps users plan a night out."""

    def __init__(self, name: str = "planner_agent") -> None:
        super().__init__(name)
        self._agent = None
        self._runner = None

    def set_up(self) -> None:
        """Initializes the agent and runner."""
        if self._runner:
            return

        with tracer.start_as_current_span("PlannerAgent.set_up") as main_span:
            logging.info("Starting PlannerAgent.set_up")
            main_span.add_event("Starting PlannerAgent.set_up")
            try:
                with tracer.start_as_current_span("build_agent_and_runner"):
                    self._agent = self._build_agent()
                    self._runner = Runner(
                        app_name=self._agent.name,
                        agent=self._agent,
                        artifact_service=InMemoryArtifactService(),
                        session_service=InMemorySessionService(),
                        memory_service=InMemoryMemoryService(),
                    )
                logging.info(f"PlannerAgent '{self.name}' set up complete.")
                main_span.set_status(trace.Status(trace.StatusCode.OK))
            except Exception as e:
                logging.error(f"Error during PlannerAgent set_up: {e}", exc_info=True)
                main_span.record_exception(e)
                main_span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    def _build_agent(self) -> LlmAgent:
        """Builds the underlying LLM agent."""
        return planner_agent_module.create_agent()

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        self.set_up()
        if not self._runner:
            raise RuntimeError("PlannerAgent runner not initialized. set_up() failed or was not called.")

        user_id = ctx.session.user_id
        session_id = ctx.session.id
        query_text = ctx.last_message.parts[0].text if ctx.last_message and ctx.last_message.parts else ""

        if not query_text:
            logging.warning("PlannerAgent received an empty query.")
            yield Event(author=self.name, actions=EventActions(finish=True, output="No query provided."))
            return

        logging.info(f"PlannerAgent '{self.name}' processing query for user '{user_id}' in session '{session_id}': '{query_text}'")

        try:
            response_event = None
            async for event in self._runner.run(
                user_id=user_id,
                session_id=session_id,
                new_message=Content(parts=[Part(text=query_text)], role="user")
            ):
                response_event = event
                break

            if response_event and response_event.content and response_event.content.parts:
                final_output = response_event.content.parts[0].text
                logging.info(f"PlannerAgent '{self.name}' got final response: {final_output}")
                yield Event(author=self.name, actions=EventActions(finish=True, output=final_output))
            else:
                logging.warning("PlannerAgent did not receive a valid response from the runner.")
                yield Event(author=self.name, actions=EventActions(finish=True, output="Failed to get a response."))
        except Exception as e:
            logging.error(f"Error during PlannerAgent execution for session '{session_id}': {e}", exc_info=True)
            yield Event(author=self.name, actions=EventActions(finish=True, output=f"An error occurred: {e}"))