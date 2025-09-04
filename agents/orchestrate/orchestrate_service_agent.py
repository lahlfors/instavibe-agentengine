# In agents/orchestrate/orchestrate_service_agent.py
import logging
import os
import asyncio
import google.auth
import google.auth.credentials
import json
from opentelemetry import trace
import opentelemetry.semconv._incubating.attributes.gen_ai_attributes as ai_semconv
from vertexai.generative_models import GenerativeModel
from google.adk.agents import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.planners import BuiltInPlanner
from google.adk.tools.tool_context import ToolContext
from google.genai.types import ThinkingConfig
from typing import Optional
from agents.app.utils.communication import call_agent_capability
from google.adk.memory import VertexAiMemoryBankService
from google.adk.tools import preload_memory_tool
from common.observability import setup_observability

logging.basicConfig(level=logging.INFO)
tracer = trace.get_tracer(__name__)

class OrchestrateServiceAgent(Agent):
    """
    The main orchestrator agent, interacting with Memory Bank via REST API and delegating tasks.
    """
    project: Optional[str] = None
    location: Optional[str] = None
    reasoning_engine_id: Optional[str] = None
    orchestrator_agent: Optional[Agent] = None
    memory_service: Optional[VertexAiMemoryBankService] = None
    otel_collector_endpoint: Optional[str] = None

    def __init__(self, name: str, instruction: Optional[str] = None, description: Optional[str] = None):
        super().__init__(
            name=name,
            model="gemini-2.5-flash",
            instruction=instruction or "I am an orchestrator agent with memory and task delegation capabilities.",
            description=description or "An agent that can create/search memories and delegate tasks.",
        )

    def set_up(self, **kwargs):
        # Synchronous entry point for the Reasoning Engine
        print(f"Sync set_up called for {self.__class__.__name__}, running async setup...")
        try:
            asyncio.run(self._async_set_up(**kwargs))
            print(f"Async set_up for {self.__class__.__name__} completed.")
        except Exception as e:
            print(f"Error during async set_up for {self.__class__.__name__}: {e}")
            raise

    async def _async_set_up(self, **kwargs):
        # All your original async logic can go here
        print(f"--- Running _async_set_up for {self.__class__.__name__} ---")
        os.environ["OTEL_SERVICE_NAME"] = self.name
        setup_observability()
        if self.orchestrator_agent:
            return

        logging.info("--- ORCHESTRATE AGENT RUNTIME SETUP ---")
        self.project = os.getenv("COMMON_GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("COMMON_GOOGLE_CLOUD_LOCATION")
        self.reasoning_engine_id = os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ID")

        if not self.project or not self.location:
            raise RuntimeError("COMMON_GOOGLE_CLOUD_PROJECT and COMMON_GOOGLE_CLOUD_LOCATION environment variables must be set.")
        if not self.reasoning_engine_id:
            logging.error("GOOGLE_CLOUD_AGENT_ENGINE_ID environment variable not set.")
            raise RuntimeError("GOOGLE_CLOUD_AGENT_ENGINE_ID environment variable must be set.")

        self.memory_service = VertexAiMemoryBankService(
            project=self.project,
            location=self.location,
            agent_engine_id=self.reasoning_engine_id,
        )
        logging.info("VertexAiMemoryBankService initialized.")

        thinking_config = ThinkingConfig(
            include_thoughts=True,
            thinking_budget=-1,  # Use dynamic thinking
        )
        planner = BuiltInPlanner(thinking_config=thinking_config)
        all_tools = [self.send_task, preload_memory_tool.PreloadMemoryTool(memory=self.memory_service)]

        self.orchestrator_agent = Agent(
            model="gemini-2.5-flash",
            name="orchestrate_agent",
            instruction=self.root_instruction,
            description=(
                "This agent orchestrates the decomposition of the user request into"
                " tasks that can be performed by the child agents."
            ),
            tools=all_tools,
            planner=planner,
            memory=self.memory_service,
        )
        logging.info("--- ORCHESTRATE AGENT RUNTIME SETUP COMPLETE ---")
        print("--- _async_setup_logic complete ---")


    def root_instruction(self, context: ReadonlyContext) -> str:
        return '''
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
    '''

    async def send_task(
        self,
        agent_name: str,
        action: str,
        data: dict,
        tool_context: ToolContext
    ) -> dict:
        """
        Finds a remote agent and invokes one of its capabilities.
        """
        with tracer.start_as_current_span(f"{agent_name}.{action}") as span:
            span.set_attribute("agent.name", self.name)
            span.set_attribute(ai_semconv.GEN_AI_OPERATION_NAME, "send_task")
            span.set_attribute(ai_semconv.GEN_AI_TOOL_NAME, "send_task")
            tool_params = {
                "agent_name": agent_name,
                "action": action,
                "data": data,
            }
            span.set_attribute(ai_semconv.GEN_AI_TOOL_PARAMETERS, json.dumps(tool_params))
            try:
                response_data = await call_agent_capability(
                    source_agent="orchestrate_agent",
                    target_agent=agent_name,
                    capability=action,
                    prompt=data
                )
                span.set_attribute(ai_semconv.OUTPUT_VALUE, json.dumps(response_data))
                return response_data
            except Exception as e:
                span.set_attribute(ai_semconv.OUTPUT_VALUE, json.dumps({"error": str(e)}))
                return {"error": f"An error occurred while sending task to '{agent_name}': {e}"}

    def query(self, input_text: str) -> str:
        with tracer.start_as_current_span("orchestrate_agent.query") as span:
            span.set_attribute("agent.name", self.name)
            span.set_attribute(ai_semconv.GEN_AI_SYSTEM, "google_vertexai")
            span.set_attribute(ai_semconv.GEN_AI_REQUEST_MODEL, self.orchestrator_agent.model)

            model = GenerativeModel(self.orchestrator_agent.model)

            # Count and set INPUT tokens
            try:
                prompt_tokens = model.count_tokens([input_text]).total_tokens
                span.set_attribute(ai_semconv.GEN_AI_USAGE_INPUT_TOKENS, prompt_tokens)
            except Exception as e:
                logging.warning(f"Could not count input tokens accurately: {e}, falling back to estimation.")
                span.set_attribute(ai_semconv.GEN_AI_USAGE_INPUT_TOKENS, len(input_text) // 4)

            # Add PROMPT CONTENT as an EVENT
            span.add_event(
                "gen_ai.prompt",
                {"gen_ai.prompt.value": input_text}
            )

            if not self.orchestrator_agent:
                logging.error("OrchestratorAgent not initialized. set_up() was not called.")
                raise RuntimeError("Agent not properly initialized.")

            response_text = self.orchestrator_agent.query(input_text)

            # Add COMPLETION CONTENT as an EVENT
            span.add_event(
                "gen_ai.completion",
                {"gen_ai.completion.value": response_text}
            )

            # Count and set OUTPUT tokens
            try:
                completion_tokens = model.count_tokens([response_text]).total_tokens
                span.set_attribute(ai_semconv.GEN_AI_USAGE_OUTPUT_TOKENS, completion_tokens)
            except Exception as e:
                logging.warning(f"Could not count output tokens accurately: {e}, falling back to estimation.")
                span.set_attribute(ai_semconv.GEN_AI_USAGE_OUTPUT_TOKENS, len(response_text) // 4)

            return response_text

OrchestrateServiceAgent.model_rebuild()

root_agent = OrchestrateServiceAgent(
    name="orchestrate_service_agent",
)
