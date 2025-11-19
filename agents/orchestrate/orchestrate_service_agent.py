# agents/orchestrate/orchestrate_service_agent.py
import logging
import os
from google.adk.agents import LlmAgent
from google.adk.readonly_context import ReadonlyContext
from google.adk.planners import BuiltInPlanner
from google.genai.types import ThinkingConfig
from pydantic import Field
from typing import Optional
from a2a.client import ClientConfig
from a2a.types import TransportProtocol

# Import picklable wrappers
from agents.orchestrate.picklable_a2a_wrappers import (
    PicklableRemoteA2aAgent,
    PicklableClientFactory
)

# Import observability and memory
from google.adk.memory import VertexAiMemoryBankService
from google.adk.tools import preload_memory_tool
from common.observability import setup_observability

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrchestrateServiceAgent(LlmAgent):
    """
    Orchestrator that delegates to specialist agents on Agent Engine via A2A protocol.
    Uses picklable RemoteA2aAgent wrappers for deployment to Agent Engine.
    
    Based on Google Cloud Japan's proven pattern:
    https://github.com/google-cloud-japan/sa-ml-workshop/blob/main/blog/Agentic-workflow-AgentEngine-A2A.ipynb
    """
    
    # Resource names for deployed agents (to construct A2A URLs)
    planner_agent_resource_name: Optional[str] = Field(default=None)
    social_agent_resource_name: Optional[str] = Field(default=None)
    platform_agent_resource_name: Optional[str] = Field(default=None)
    
    # Project/location info
    project_id: Optional[str] = Field(default=None)
    location: Optional[str] = Field(default=None)
    reasoning_engine_id: Optional[str] = Field(default=None)
    otel_collector_endpoint: Optional[str] = Field(default=None)
    
    # Memory service (initialized in _async_set_up)
    memory_service: Optional[VertexAiMemoryBankService] = Field(default=None, exclude=True)
    
    def __post_init__(self):
        """Initialize orchestrator with picklable RemoteA2aAgent sub-agents."""
        super().__post_init__()
        
        logger.info("--- ORCHESTRATE AGENT POST-INIT (STATIC) ---")
        
        # Get config from environment
        self.project_id = self.project_id or os.getenv("COMMON_GOOGLE_CLOUD_PROJECT")
        self.location = self.location or os.getenv("COMMON_GOOGLE_CLOUD_LOCATION")
        self.otel_collector_endpoint = os.getenv("OTEL_COLLECTOR_ENDPOINT")
        
        if not self.project_id or not self.location:
            raise RuntimeError("COMMON_GOOGLE_CLOUD_PROJECT and COMMON_GOOGLE_CLOUD_LOCATION must be set.")
        
        # Create picklable client factory (httpx client created lazily at runtime)
        factory = PicklableClientFactory(
            ClientConfig(
                supported_transports=[TransportProtocol.http_json],
                use_client_preference=True,
            )
        )
        
        # Construct A2A URLs from resource names
        planner_resource = self.planner_agent_resource_name or os.getenv("PLANNER_AGENT_URL", "")
        social_resource = self.social_agent_resource_name or os.getenv("SOCIAL_AGENT_URL", "")
        platform_resource = self.platform_agent_resource_name or os.getenv("PLATFORM_MCP_CLIENT_AGENT_URL", "")
        
        planner_a2a_url = f"https://{self.location}-aiplatform.googleapis.com/v1beta1/{planner_resource}/a2a"
        social_a2a_url = f"https://{self.location}-aiplatform.googleapis.com/v1beta1/{social_resource}/a2a"
        platform_a2a_url = f"https://{self.location}-aiplatform.googleapis.com/v1beta1/{platform_resource}/a2a"
        
        logger.info(f"Planner A2A URL: {planner_a2a_url}")
        logger.info(f"Social A2A URL: {social_a2a_url}")
        logger.info(f"Platform A2A URL: {platform_a2a_url}")
        
        # Create picklable RemoteA2aAgent instances
        planner_agent = PicklableRemoteA2aAgent(
            name="planner_agent",
            description="Generates creative event/activity plans based on user preferences",
            agent_card=f"{planner_a2a_url}/v1/card",
            a2a_client_factory=factory
        )
        
        social_agent = PicklableRemoteA2aAgent(
            name="social_agent",
            description="Analyzes social profiles and provides insights",
            agent_card=f"{social_a2a_url}/v1/card",
            a2a_client_factory=factory
        )
        
        platform_agent = PicklableRemoteA2aAgent(
            name="platform_mcp_client_agent",
            description="Interacts with the Instavibe platform to create events and posts",
            agent_card=f"{platform_a2a_url}/v1/card",
            a2a_client_factory=factory
        )
        
        # Set as sub-agents (enables automatic transfer_to_agent)
        self.sub_agents = [planner_agent, social_agent, platform_agent]
        
        # Configure planner
        self.planner = BuiltInPlanner(
            thinking_config=ThinkingConfig(include_thoughts=True, thinking_budget=-1)
        )
        self.instruction = self.root_instruction
        
        logger.info("✅ OrchestrateServiceAgent initialized with picklable A2A sub-agents")
        logger.info("--- ORCHESTRATE AGENT POST-INIT COMPLETE ---")

    async def _async_set_up(self, reasoning_engine_id: str, **kwargs):
        """
        Async setup for dynamic components (Memory and Observability).
        Note: Sub-agents are now configured in __post_init__, not here.
        """
        logger.info(f"--- Running _async_set_up for {self.__class__.__name__} (DYNAMIC) ---")
        
        os.environ["OTEL_SERVICE_NAME"] = self.name
        setup_observability(endpoint_override=self.otel_collector_endpoint)
        
        self.reasoning_engine_id = reasoning_engine_id
        
        # Initialize Memory
        self.memory_service = VertexAiMemoryBankService(
            project=self.project_id,
            location=self.location,
            agent_engine_id=self.reasoning_engine_id,
        )
        self.memory = self.memory_service
        
        # Add memory preload tool
        if not hasattr(self, 'tools') or self.tools is None:
            self.tools = []
        self.tools.append(preload_memory_tool.PreloadMemoryTool(memory=self.memory_service))
        
        logger.info(f"Memory service initialized for {self.reasoning_engine_id}.")
        logger.info(f"{self.__class__.__name__} async setup complete.")

    def set_up(self, reasoning_engine_id: str, **kwargs):
        """Synchronous wrapper for async setup."""
        logger.info(f"Sync set_up called for {self.__class__.__name__}")
        try:
            import asyncio
            asyncio.run(self._async_set_up(reasoning_engine_id, **kwargs))
            logger.info(f"set_up completed for {self.__class__.__name__}.")
        except Exception as e:
            logger.error(f"Error during set_up for {self.__class__.__name__}: {e}", exc_info=True)
            raise
        return self

    def root_instruction(self, context: ReadonlyContext) -> str:
        """
        Root instruction for the orchestrator.
        Uses built-in transfer_to_agent tool instead of custom routing.
        """
        return '''
You are an expert AI Orchestrator for the Instavibe application. Your primary responsibility is to intelligently interpret user requests and delegate them to the most appropriate specialized agents.

You have three specialized agents at your disposal:
- **planner_agent**: Helps users plan activities and events, considering their interests, budget, and location. Use this for generating creative plan suggestions.
- **social_agent**: Analyzes social media profiles and provides insights. Use this for profile analysis tasks.
- **platform_mcp_client_agent**: Interacts with the Instavibe platform. Use this to create events, posts, and perform other platform-specific actions.

Core Workflow:
1. **Understand User Intent**: Analyze the user's request to determine the core task.
2. **Identify Appropriate Agent**: Determine which specialist agent should handle this request.
3. **Provide Reasoning**: Before delegating, provide a brief summary of your reasoning for choosing this agent.
4. **Delegate Using transfer_to_agent**: Use the built-in transfer_to_agent tool to delegate to the appropriate specialist.

Important: Always use transfer_to_agent to delegate to specialists. Do not try to handle specialized requests yourself.
'''


# Factory function
def create_agent(
    model: str,
    planner_resource: str,
    social_resource: str,
    platform_resource: str,
    project_id: str,
    location: str
):
    """Factory to create orchestrator with agent resource names."""
    return OrchestrateServiceAgent(
        name="orchestrate_service_agent",
        model=model,
        planner_agent_resource_name=planner_resource,
        social_agent_resource_name=social_resource,
        platform_agent_resource_name=platform_resource,
        project_id=project_id,
        location=location
    )


# Default instance for deployment
root_agent = create_agent(
    model=os.getenv("COMMON_GEMINI_MODEL", "gemini-2.5-flash"),
    planner_resource=os.getenv("PLANNER_AGENT_URL", ""),
    social_resource=os.getenv("SOCIAL_AGENT_URL", ""),
    platform_resource=os.getenv("PLATFORM_MCP_CLIENT_AGENT_URL", ""),
    project_id=os.getenv("COMMON_GOOGLE_CLOUD_PROJECT", ""),
    location=os.getenv("COMMON_GOOGLE_CLOUD_LOCATION", "")
)