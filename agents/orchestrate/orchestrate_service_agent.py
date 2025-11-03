# In agents/orchestrate/orchestrate_service_agent.py
import logging
import os
import sys
import asyncio
import google.auth
import google.auth.credentials
import json
from opentelemetry import trace
import opentelemetry.semconv._incubating.attributes.gen_ai_attributes as ai_semconv
from vertexai.generative_models import GenerativeModel
from google.adk.agents import Agent, InvocationContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.planners import BuiltInPlanner
from google.adk.tools.tool_context import ToolContext
from google.genai.types import ThinkingConfig
from typing import Optional, AsyncGenerator, List, Callable, Any
from google.adk.events import Event
from google.genai.types import Content, Part
from google.adk.events import Event
from pydantic import Field
from vertexai.preview.reasoning_engines import ReasoningEngine # Import ReasoningEngine

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# We are now calling agents directly, not using the old helper
# from agents.app.utils.communication import call_agent_capability 
from google.adk.memory import VertexAiMemoryBankService
from google.adk.tools import preload_memory_tool
from common.observability import setup_observability

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

class OrchestrateServiceAgent(Agent):
    """
    The main orchestrator agent. It is initialized with the resource names
    of other agents and calls them directly using the SDK.
    """
    
    # --- Pydantic Fields ---
    display_name: Optional[str] = Field(default=None, description="The display name for the agent.")
    project: Optional[str] = Field(default=None, description="The Google Cloud project ID.")
    location: Optional[str] = Field(default=None, description="The Google Cloud location.")
    reasoning_engine_id: Optional[str] = Field(default=None, description="The GCP Reasoning Engine ID.")
    
    memory_service: Optional[VertexAiMemoryBankService] = Field(default=None, exclude=True)
    otel_collector_endpoint: Optional[str] = Field(default=None)
    
    # --- Dependency Injection Fields ---
    planner_agent_resource_name: Optional[str] = Field(default=None)
    social_agent_resource_name: Optional[str] = Field(default=None)
    platform_mcp_client_agent_resource_name: Optional[str] = Field(default=None)

    # Agent clients will be initialized in _async_set_up
    planner_agent: Optional[ReasoningEngine] = Field(default=None, exclude=True)
    social_agent: Optional[ReasoningEngine] = Field(default=None, exclude=True)
    platform_mcp_client_agent: Optional[ReasoningEngine] = Field(default=None, exclude=True)

    model_client: Optional[GenerativeModel] = Field(default=None, exclude=True)


    def __post_init__(self):
        super().__post_init__()
        logger.info("--- ORCHESTRATE AGENT POST-INIT (STATIC) ---")
        
        self.project = os.getenv("COMMON_GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("COMMON_GOOGLE_CLOUD_LOCATION")
        self.otel_collector_endpoint = os.getenv("OTEL_COLLECTOR_ENDPOINT")

        if not self.project or not self.location:
            raise RuntimeError("COMMON_GOOGLE_CLOUD_PROJECT and COMMON_GOOGLE_CLOUD_LOCATION must be set.")

        # Initialize static agent components
        if self.model:
            self.model_client = GenerativeModel(self.model)
        else:
            print("WARNING: OrchestrateServiceAgent initialized without a model name.")
        self.planner = BuiltInPlanner(thinking_config=ThinkingConfig(include_thoughts=True, thinking_budget=-1))
        self.tools: List[Callable] = [ self.__async_send_task_tool ]
        self.instruction = self.root_instruction
        
        logger.info("--- ORCHESTRATE AGENT POST-INIT COMPLETE ---")


    async def _async_set_up(self, reasoning_engine_id: str, **kwargs):
        """
        Async setup for dynamic components (Memory) and remote agent clients.
        """
        logger.info(f"--- Running _async_set_up for {self.__class__.__name__} (DYNAMIC) ---")
        os.environ["OTEL_SERVICE_NAME"] = self.name
        setup_observability(endpoint_override=self.otel_collector_endpoint)
        
        self.reasoning_engine_id = reasoning_engine_id

        # --- Initialize Memory ---
        self.memory_service = VertexAiMemoryBankService(
            project=self.project,
            location=self.location,
            agent_engine_id=self.reasoning_engine_id,
        )
        self.memory = self.memory_service
        self.tools.append(preload_memory_tool.PreloadMemoryTool(memory=self.memory_service))
        logger.info(f"Memory service initialized for {self.reasoning_engine_id}.")

        # --- Initialize Remote Agent Clients ---
        logger.info("Connecting to remote agents...")
        try:
            if self.planner_agent_resource_name:
                self.planner_agent = ReasoningEngine.get(self.planner_agent_resource_name)
                logger.info(f"Connected to planner agent: {self.planner_agent_resource_name}")
            else:
                logger.warning("Planner agent resource name not provided.")
                
            if self.social_agent_resource_name:
                self.social_agent = ReasoningEngine.get(self.social_agent_resource_name)
                logger.info(f"Connected to social agent: {self.social_agent_resource_name}")
            else:
                logger.warning("Social agent resource name not provided.")

            if self.platform_mcp_client_agent_resource_name:
                self.platform_mcp_client_agent = ReasoningEngine.get(self.platform_mcp_client_agent_resource_name)
                logger.info(f"Connected to platform agent: {self.platform_mcp_client_agent_resource_name}")
            else:
                logger.warning("Platform MCP client agent resource name not provided.")
                
        except Exception as e:
            logger.error(f"Failed to initialize remote agent clients: {e}", exc_info=True)
            raise
        
        logger.info(f"{self.__class__.__name__} async setup complete.")

    def set_up(self, reasoning_engine_id: str, **kwargs):
        """A synchronous wrapper for the async setup."""
        logger.info(f"Sync set_up called for {self.__class__.__name__}")
        try:
            asyncio.run(self._async_set_up(reasoning_engine_id, **kwargs))
            logger.info(f"set_up completed for {self.__class__.__name__}.")
        except Exception as e:
            logger.error(f"Error during set_up for {self.__class__.__name__}: {e}", exc_info=True)
            raise
        return self


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
    4.  **Delegate Task:** Use the `__async_send_task_tool` to delegate the task. Your call MUST include:
        * `agent_name`: The name of the target agent (e.g., 'planner-agent').
        * `action`: The name of the capability to invoke (e.g., 'plan', 'create_event').
        * `data`: A dictionary containing the payload for the action. (e.g., {"prompt": "user's request"})
    
    Rely strictly on your tools. If the user's request is ambiguous or missing information, ask for clarification.
    '''

    # Renamed with double underscore to be private and fix deployment error
    async def __async_send_task_tool(
        self,
        agent_name: str,
        action: str, # 'action' is now for routing, not the SDK call
        data: dict,
        tool_context: ToolContext
    ) -> dict:
        """
        Finds a remote agent client and invokes it.
        """
        with tracer.start_as_current_span(f"{agent_name}.{action}") as span:
            span.set_attribute("agent.name", self.name)
            span.set_attribute(ai_semconv.GEN_AI_OPERATION_NAME, "send_task")
            span.set_attribute(ai_semconv.GEN_AI_TOOL_NAME, "send_task")
            tool_params = { "agent_name": agent_name, "action": action, "data": data }
            span.set_attribute(ai_semconv.GEN_AI_TOOL_PARAMETERS, json.dumps(tool_params))
            
            try:
                target_agent_client: Optional[ReasoningEngine] = None
                if agent_name == "planner_agent":
                    target_agent_client = self.planner_agent
                elif agent_name == "social_agent":
                    target_agent_client = self.social_agent
                elif agent_name == "platform_mcp_client_agent":
                    target_agent_client = self.platform_mcp_client_agent

                if not target_agent_client:
                    raise ValueError(f"Client for agent '{agent_name}' is not initialized or not found.")

                # The 'data' dict should contain the prompt for the remote agent
                prompt = data.get("prompt", str(data))
                
                # Use stream_query to get a streaming response
                logger.info(f"Sending task to remote agent '{agent_name}'...")
                response_stream = target_agent_client.stream_query(message=prompt)
                
                # Collect the full response.
                final_response = ""
                for chunk in response_stream:
                    if hasattr(chunk, 'response'):
                        final_response += chunk.response
                
                logger.info(f"Received response from '{agent_name}': {final_response[:100]}...")
                
                # Attempt to parse as JSON, otherwise return as text
                try:
                    response_data = json.loads(final_response)
                except json.JSONDecodeError:
                    response_data = {"response": final_response}

                span.set_attribute(ai_semconv.OUTPUT_VALUE, json.dumps(response_data))
                return response_data
            
            except Exception as e:
                logger.error(f"Error calling remote agent '{agent_name}': {e}", exc_info=True)
                span.set_attribute(ai_semconv.OUTPUT_VALUE, json.dumps({"error": str(e)}))
                return {"error": f"An error occurred while sending task to '{agent_name}': {e}"}

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """This is the main, streaming entry point for the agent."""
        user_prompt = ""
        if ctx.user_content and ctx.user_content.parts:
            user_prompt = ctx.user_content.parts[0].text
        
        with tracer.start_as_current_span("orchestrate_agent.run") as span:
            span.set_attribute("agent.name", self.name)
            span.set_attribute(ai_semconv.GEN_AI_SYSTEM, "google_vertexai")
            span.set_attribute(ai_semconv.GEN_AI_REQUEST_MODEL, self.model)
            span.add_event(
                "gen_ai.prompt",
                {"gen_ai.prompt.value": user_prompt}
            )

            try:
                # Call this agent's OWN logic (planner, tools, etc.)
                async for event in super()._run_async_impl(ctx):
                    yield event
            except Exception as e:
                logger.error(f"Error during orchestration: {e}", exc_info=True)
                yield Event(content=Content(parts=[Part(text=f"Error in orchestration: {e}")]))
                raise

OrchestrateServiceAgent.model_rebuild()

# --- MODIFIED create_agent factory ---
def create_agent(
    model: str, 
    planner_url: str, 
    social_url: str, 
    platform_url: str
):
    """Factory to create the orchestrator agent with its dependencies."""
    logger.info(f"Creating OrchestrateServiceAgent with planner={planner_url}, social={social_url}, platform={platform_url}")
    return OrchestrateServiceAgent(
        name="orchestrate_service_agent",
        model=model,
        planner_agent_resource_name=planner_url,
        social_agent_resource_name=social_url,
        platform_mcp_client_agent_resource_name=platform_url
    )

# This instance is loaded by deploy_all.py's load_agent_from_path
# It will be re-created with the correct URLs
gemini_model = os.getenv("COMMON_GEMINI_MODEL", "gemini-2.5-flash")
root_agent = create_agent(
    model=gemini_model,
    planner_url=os.getenv("PLANNER_AGENT_URL", ""),
    social_url=os.getenv("SOCIAL_AGENT_URL", ""),
    platform_url=os.getenv("PLATFORM_MCP_CLIENT_AGENT_URL", "")
)