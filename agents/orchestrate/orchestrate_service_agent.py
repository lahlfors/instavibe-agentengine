# In agents/orchestrate/orchestrate_service_agent.py
from common.observability import setup_observability
setup_observability(service_name="orchestrate-agent")

import logging
import os
import asyncio
from typing import Optional, Dict, Any
from pydantic import BaseModel

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

import google.auth
import google.auth.credentials

from google.adk.agents import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.planners import BuiltInPlanner
from google.adk.tools import Tool
from google.genai.types import ThinkingConfig

from agents.app.utils.communication import call_agent_capability
from google.adk.memory import VertexAiMemoryBankService
from google.adk.tools import preload_memory_tool

logging.basicConfig(level=logging.INFO)

# Get a tracer
tracer = trace.get_tracer(__name__)

class SendTaskArgs(BaseModel):
    agent_name: str
    action: str
    data: Dict[str, Any]

class OrchestrateServiceAgent(Agent):
    """
    The main orchestrator agent, interacting with Memory Bank via REST API and delegating tasks.
    """
    project: Optional[str] = None
    location: Optional[str] = None
    reasoning_engine_id: Optional[str] = None
    memory_service: Optional[VertexAiMemoryBankService] = None

    def __init__(self, name: str, instruction: Optional[str] = None, description: Optional[str] = None):
        super().__init__(
            name=name,
            model="gemini-2.5-flash",
            instruction=self.root_instruction,
            description=description or "An agent that can create/search memories and delegate tasks.",
        )

    async def set_up(self):
        """
        Called by the Agent Engine framework after deployment.
        """
        with tracer.start_as_current_span("OrchestrateServiceAgent.set_up") as span:
            if self.memory_service:
                 span.set_status(Status(StatusCode.OK, description="Already set up"))
                 return

            logging.info("--- ORCHESTRATE AGENT RUNTIME SETUP ---")
            try:
                self.project = os.getenv("COMMON_GOOGLE_CLOUD_PROJECT")
                self.location = os.getenv("COMMON_GOOGLE_CLOUD_LOCATION")
                self.reasoning_engine_id = os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ID")

                if not self.project or not self.location:
                    error_msg = "COMMON_GOOGLE_CLOUD_PROJECT and COMMON_GOOGLE_CLOUD_LOCATION must be set."
                    span.set_status(Status(StatusCode.ERROR, description=error_msg))
                    raise RuntimeError(error_msg)
                if not self.reasoning_engine_id:
                    error_msg = "GOOGLE_CLOUD_AGENT_ENGINE_ID not set."
                    span.set_status(Status(StatusCode.ERROR, description=error_msg))
                    raise RuntimeError(error_msg)

                self.memory_service = VertexAiMemoryBankService(
                    project=self.project,
                    location=self.location,
                    agent_engine_id=self.reasoning_engine_id,
                )
                self.memory = self.memory_service
                logging.info("VertexAiMemoryBankService initialized.")

                thinking_config = ThinkingConfig(
                    include_thoughts=True,
                    thinking_budget=-1,
                )
                self.planner = BuiltInPlanner(thinking_config=thinking_config)

                send_task_tool = Tool(
                    name="send_task",
                    function=self._send_task_impl,
                    description="Delegates a task to a specified remote agent by invoking one of its capabilities.",
                    args_schema=SendTaskArgs
                )
                preload_tool = preload_memory_tool.PreloadMemoryTool(memory=self.memory_service)
                self.tools = [send_task_tool, preload_tool]

                span.set_status(Status(StatusCode.OK))
                logging.info("--- ORCHESTRATE AGENT RUNTIME SETUP COMPLETE ---")

            except Exception as e:
                logging.error(f"Error during set_up: {e}", exc_info=True)
                if span.is_recording():
                    span.set_status(Status(StatusCode.ERROR, description=str(e)))
                    span.record_exception(e)
                raise

    def root_instruction(self, context: ReadonlyContext) -> str:
        return """
    You are an expert AI Orchestrator for the Instavibe application. Your primary responsibility is to intelligently interpret user requests and delegate them to the most appropriate specialized remote agents by invoking their capabilities.

    You have the following agents at your disposal:
    - **planner-agent**: Helps users plan activities and events, considering their interests, budget, and location. It can generate creative and fun plan suggestions.
    - **platform-mcp-client-agent**: Interacts with the Instavibe platform. It can create events, posts, and perform other platform-specific actions.
    - **social-agent**: Interacts with social media platforms.

    Core Workflow:
    1.  **Understand User Intent:** Analyze the user's request to determine the core task.
    2.  **Identify Action and Agent:** Determine the appropriate 'action' (capability) to call and the 'agent_name' that provides it.
    3.  **Provide Reasoning:** After you have identified the agent and action, but before you call the tool, provide a brief summary of your reasoning for choosing a particular agent and action.
    4.  **Delegate Task:** Use the `send_task` tool to delegate the task. Your call MUST include:
        *   `agent_name`: The name of the target agent (e.g., 'planner-agent').
        *   `action`: The name of the capability to invoke (e.g., 'plan', 'create_event').
        *   `data`: A dictionary containing the payload for the action.

    Examples:
    - User Request: "Plan a fun night out for me and my friends."
      - Your thought process: The user wants to plan an event. The 'planner-agent' is the best agent for this.
      - Your tool call: `send_task(agent_name='planner-agent', action='plan', data={'prompt': 'Plan a fun night out for me and my friends.'})`
    - User Request: "Create an event for the plan we just made."
      - Your thought process: The user wants to create an event on Instavibe. The 'platform-mcp-client-agent' is the best agent for this.
      - Your tool call: `send_task(agent_name='platform-mcp-client-agent', action='create_event', data={'event_details': ...})`
    - User Request: "Share the event on social media."
        - Your thought process: The user wants to share something on social media. The 'social-agent' is the best agent for this.
        - Your tool call: `send_task(agent_name='social-agent', action='share', data={'message': 'Check out this cool event I just made on Instavibe!'})`

    Rely strictly on your tools. If the user's request is ambiguous or missing information, ask for clarification.
    """

    async def _send_task_impl(
        self,
        agent_name: str,
        action: str,
        data: dict,
    ) -> dict:
        """
        Implementation for the send_task tool.
        This method is called by the ADK planner when the send_task tool is invoked.
        """
        # The span for the tool call is likely created by the ADK framework.
        # We get the current span to add status and attributes.
        span = trace.get_current_span()

        try:
            logging.info(f"Sending task to '{agent_name}', action '{action}'")
            span.set_attributes({
                "a2a.target_agent": agent_name,
                "a2a.capability": action,
            })

            response_data = await call_agent_capability(
                source_agent=self.name,
                target_agent=agent_name,
                capability=action,
                prompt=data
            )

            if isinstance(response_data, dict) and response_data.get("error"):
                error_detail = response_data['error']
                logging.warning(f"A2A call to {agent_name} for {action} returned an error: {error_detail}")
                if span.is_recording():
                    span.set_status(Status(StatusCode.ERROR, description=f"Error from {agent_name}"))
                    span.add_event("a2a_call_failed", attributes={"error": str(error_detail)})
            else:
                if span.is_recording():
                    span.set_status(Status(StatusCode.OK))
            return response_data
        except Exception as e:
            logging.error(f"Exception during A2A call to {agent_name} for {action}: {e}", exc_info=True)
            if span.is_recording():
                span.set_status(Status(StatusCode.ERROR, description=str(e)))
                span.record_exception(e)
            return {"error": f"An unexpected exception occurred while calling {agent_name}: {str(e)}"}

# root_agent instance remains the same
root_agent = OrchestrateServiceAgent(
    name="orchestrate_service_agent",
)
