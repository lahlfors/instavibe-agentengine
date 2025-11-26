
import logging
import os
import sys
import asyncio
import json
from typing import Optional, AsyncGenerator, List, Callable, Any, Literal
from enum import Enum

# --- Imports ---
import google.auth
import google.auth.credentials
import nest_asyncio  # FIX: Top-level import to fail fast if missing
from opentelemetry import trace
import opentelemetry.semconv._incubating.attributes.gen_ai_attributes as ai_semconv
from google.generativeai import GenerativeModel
from google.adk.agents import Agent, InvocationContext
from google.genai.types import Content, Part
from google.adk.events import Event
from pydantic import Field, PrivateAttr, BaseModel
from vertexai.preview.reasoning_engines import ReasoningEngine
import vertexai

# --- Custom Imports ---
from .picklable_a2a_wrappers import PicklableClientFactory
from .governed_client import GovernedReasoningEngineAgent
from a2a.client import ClientConfig
from a2a.types import TransportProtocol
from google.adk.memory import VertexAiMemoryBankService
from google.adk.tools import preload_memory_tool

# Attempt to import setup_observability
try:
    from agents.common.observability import setup_observability
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from agents.common.observability import setup_observability

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

nest_asyncio.apply()

class UserIntent(str, Enum):
    PLAN = "PLAN"
    SOCIAL = "SOCIAL"
    PLATFORM = "PLATFORM"
    UNKNOWN = "UNKNOWN"

class OrchestrateServiceAgent(Agent):
    """
    The main orchestrator agent. Deterministic Router.
    """
    
    # --- Configuration ---
    display_name: Optional[str] = Field(default=None)
    project: Optional[str] = Field(default=None)
    location: Optional[str] = Field(default=None)
    reasoning_engine_id: Optional[str] = Field(default=None)
    otel_collector_endpoint: Optional[str] = Field(default=None)
    
    memory_service: Optional[VertexAiMemoryBankService] = Field(default=None, exclude=True)
    
    # --- Resource Names ---
    planner_agent_resource_name: Optional[str] = Field(default=None)
    social_agent_resource_name: Optional[str] = Field(default=None)
    platform_mcp_client_agent_resource_name: Optional[str] = Field(default=None)

    # --- Sub-Agents ---
    # Using GovernedReasoningEngineAgent for Zero Trust A2A
    planner_agent: Optional[GovernedReasoningEngineAgent] = Field(default=None, exclude=True)
    social_agent: Optional[GovernedReasoningEngineAgent] = Field(default=None, exclude=True)
    platform_mcp_client_agent: Optional[GovernedReasoningEngineAgent] = Field(default=None, exclude=True)

    _model_client: Any = PrivateAttr(default=None)
    # Added fields for InvocationContext compatibility
    session_service: Optional[Any] = Field(default=None, exclude=True)
    session: Optional[Any] = Field(default=None, exclude=True)

    def __post_init__(self):
        super().__post_init__()
        self.project = os.getenv("COMMON_GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("COMMON_GOOGLE_CLOUD_LOCATION")
        self.otel_collector_endpoint = os.getenv("OTEL_COLLECTOR_ENDPOINT")

        if self.model:
            self._model_client = GenerativeModel(self.model)
        
        self.tools = []
        # Eager init for local testing
        self._initialize_remote_agents()
    
    def _initialize_remote_agents(self):
        """Initialize remote A2A agent clients using Governed Discovery."""
        logger.info("🔧 _initialize_remote_agents called (Governed Mode)")
        
        # Configuration Fallback - recover from environment if fields are empty
        if not self.planner_agent_resource_name:
            self.planner_agent_resource_name = os.getenv("PLANNER_AGENT_URL", "")
            if not self.planner_agent_resource_name:
                logger.error("⚠️ USING HARDCODED FALLBACK FOR PLANNER AGENT ⚠️")
                self.planner_agent_resource_name = "projects/735503743752/locations/us-central1/reasoningEngines/2624274770757156864"

        if not self.social_agent_resource_name:
            self.social_agent_resource_name = os.getenv("SOCIAL_AGENT_URL", "")
            if not self.social_agent_resource_name:
                 logger.error("⚠️ USING HARDCODED FALLBACK FOR SOCIAL AGENT ⚠️")
                 self.social_agent_resource_name = "projects/735503743752/locations/us-central1/reasoningEngines/8348349897145057280"

        if not self.platform_mcp_client_agent_resource_name:
            self.platform_mcp_client_agent_resource_name = os.getenv("PLATFORM_MCP_CLIENT_AGENT_URL", "")
            if not self.platform_mcp_client_agent_resource_name:
                logger.error("⚠️ USING HARDCODED FALLBACK FOR PLATFORM AGENT ⚠️")
                self.platform_mcp_client_agent_resource_name = "projects/735503743752/locations/us-central1/reasoningEngines/7027106356465238016"

        logger.info(f"🔧 Final - Planner Resource: {self.planner_agent_resource_name}")
        logger.info(f"🔧 Final - Social Resource: {self.social_agent_resource_name}")
        logger.info(f"🔧 Final - Platform Resource: {self.platform_mcp_client_agent_resource_name}")

        # Initialize Governed Clients
        try:
            if self.planner_agent_resource_name:
                self.planner_agent = GovernedReasoningEngineAgent(
                    resource_name=self.planner_agent_resource_name,
                    name="planner_agent"
                )
                logger.info(f"✅ Initialized Governed Planner Agent")
            
            if self.social_agent_resource_name:
                self.social_agent = GovernedReasoningEngineAgent(
                    resource_name=self.social_agent_resource_name,
                    name="social_agent"
                )
                logger.info(f"✅ Initialized Governed Social Agent")
            
            if self.platform_mcp_client_agent_resource_name:
                self.platform_mcp_client_agent = GovernedReasoningEngineAgent(
                    resource_name=self.platform_mcp_client_agent_resource_name,
                    name="platform_mcp_client_agent"
                )
                logger.info(f"✅ Initialized Governed Platform Agent")
                
        except Exception as e:
            logger.error(f"Failed to initialize governed agents: {e}", exc_info=True)
            raise

    @property
    def model_client(self) -> GenerativeModel | None:
        return self._model_client

    async def _async_set_up(self, reasoning_engine_id: Optional[str] = None, **kwargs):
        """
        Async setup: Initializes Memory and Remote A2A Clients.
        Includes robust fallback to Env Vars if configuration is missing.
        """
        logger.info(f"--- Running _async_set_up for {self.__class__.__name__} ---")
        
        # 1. Initialize Model Client for Classifier (Critical for Deployed Agent)
        if self.model:
            try:
                self._model_client = GenerativeModel(self.model)
                logger.info(f"ASYNC_SET_UP - Initialized GenerativeModel client for {self.model}")
            except Exception as e:
                logger.error(f"ASYNC_SET_UP - Failed to initialize GenerativeModel: {e}", exc_info=True)
                self._model_client = None
        else:
            logger.warning("ASYNC_SET_UP - OrchestrateServiceAgent model name not set. Cannot initialize model client.")
            self._model_client = None
        
        logger.info(f"ASYNC_SET_UP - Start - Planner URL: {self.planner_agent_resource_name}")
        logger.info(f"ASYNC_SET_UP - Start - Social URL: {self.social_agent_resource_name}")
        logger.info(f"ASYNC_SET_UP - Start - Platform URL: {self.platform_mcp_client_agent_resource_name}")

        # 2. Observability
        os.environ["OTEL_SERVICE_NAME"] = self.name
        setup_observability(endpoint_override=self.otel_collector_endpoint)
        
        # 3. Memory (Optional - only if reasoning_engine_id is provided)
        if reasoning_engine_id:
            self.reasoning_engine_id = reasoning_engine_id
            self.memory_service = VertexAiMemoryBankService(
                project=self.project,
                location=self.location,
                agent_engine_id=self.reasoning_engine_id,
            )
            self.memory = self.memory_service
            self.tools.append(preload_memory_tool.PreloadMemoryTool(memory=self.memory_service))
            logger.info(f"Memory service initialized for {self.reasoning_engine_id}.")
        else:
            logger.warning("Reasoning Engine ID missing. Memory service skipped.")

        # 4. Remote Agents - Configuration Fallback
        # If fields are empty (due to pickle issues), recover from Environment
        if not self.planner_agent_resource_name:
            logger.error("Planner agent resource name is MISSING on entry to fallback.")
            self.planner_agent_resource_name = os.getenv("PLANNER_AGENT_URL", "")
            
            # BREAK GLASS FALLBACK: Hardcoded IDs from latest deployment
            if not self.planner_agent_resource_name:
                logger.error("⚠️ USING HARDCODED FALLBACK FOR PLANNER AGENT ⚠️")
                self.planner_agent_resource_name = "projects/735503743752/locations/us-central1/reasoningEngines/2624274770757156864"

        if not self.social_agent_resource_name:
            self.social_agent_resource_name = os.getenv("SOCIAL_AGENT_URL", "")
            if not self.social_agent_resource_name:
                 logger.error("⚠️ USING HARDCODED FALLBACK FOR SOCIAL AGENT ⚠️")
                 self.social_agent_resource_name = "projects/735503743752/locations/us-central1/reasoningEngines/8348349897145057280"

        if not self.platform_mcp_client_agent_resource_name:
            self.platform_mcp_client_agent_resource_name = os.getenv("PLATFORM_MCP_CLIENT_AGENT_URL", "")
            if not self.platform_mcp_client_agent_resource_name:
                logger.error("⚠️ USING HARDCODED FALLBACK FOR PLATFORM AGENT ⚠️")
                self.platform_mcp_client_agent_resource_name = "projects/735503743752/locations/us-central1/reasoningEngines/7027106356465238016"

        logger.error(f"ASYNC_SET_UP - Final - Planner URL: {self.planner_agent_resource_name}")
        logger.error(f"ASYNC_SET_UP - Final - Social URL: {self.social_agent_resource_name}")
        logger.error(f"ASYNC_SET_UP - Final - Platform URL: {self.platform_mcp_client_agent_resource_name}")

        # 4. Remote Agents
        # NOTE: Remote agents are now initialized in __post_init__ or lazily in _invoke_remote_agent
        # to handle pickling correctly. We do NOT initialize them here anymore.
        pass

        
        logger.info(f"{self.__class__.__name__} async setup complete.")

    def set_up(self, reasoning_engine_id: Optional[str] = None, **kwargs):
        """
        Robust sync wrapper.
        Uses nest_asyncio to prevent 'Event loop is running' crashes during local testing.
        """
        logger.info(f"Sync set_up called. ID: {reasoning_engine_id}")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            logger.info("Using existing event loop (nested).")
            loop.run_until_complete(self._async_set_up(reasoning_engine_id, **kwargs))
        else:
            logger.info("Creating new event loop.")
            asyncio.run(self._async_set_up(reasoning_engine_id, **kwargs))
            
        logger.info("set_up completed successfully.")
        return self

    async def classify_intent(self, user_input: str) -> UserIntent:
        """Delegates to the helper module."""
        # Lazy init for model client (needed after unpickling)
        if not self._model_client and self.model:
            logger.info("🔄 Hydrating model client after cold start...")
            self._model_client = GenerativeModel(self.model)
            
        from .intention_classifier import IntentClassifier
        classifier = IntentClassifier(self._model_client)
        return await classifier.classify(user_input)

    async def _invoke_remote_agent(
        self, 
        agent_name: Literal["planner_agent", "social_agent", "platform_mcp_client_agent"],
        task_content: str,
        invocation_id: str,
        parent_ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """
        Helper: Routes request to a sub-agent and streams the response via Events.
        """
        logger.info(f"🤖 Routing to: {agent_name}")
        
        # CRITICAL: Lazy initialization check
        # After unpickling, __post_init__ doesn't run, so we need to ensure agents are initialized
        if getattr(self, agent_name) is None:
            logger.info(f"🔄 Hydrating {agent_name} client after cold start...")
            self._initialize_remote_agents()
        
        with tracer.start_as_current_span(f"invoke_agent.{agent_name}") as span:
            span.set_attribute("agent.name", self.name)
            
            target_agent = None
            if agent_name == "planner_agent": target_agent = self.planner_agent
            elif agent_name == "social_agent": target_agent = self.social_agent
            elif agent_name == "platform_mcp_client_agent": target_agent = self.platform_mcp_client_agent
            
            if not target_agent:
                msg = f"Error: Client for agent '{agent_name}' is not initialized."
                logger.error(msg)
                # Log current state for debugging
                logger.error(f"DEBUG - {agent_name}_resource_name: {getattr(self, f'{agent_name}_resource_name', 'N/A')}")
                yield Event(invocation_id=invocation_id, author=self.name, content=Content(parts=[Part(text=msg)]))
                return

            try:
                logger.info(f"Delegating to {agent_name} via run_async...")
                
                # Create a minimal context for the sub-agent with the task content
                sub_ctx = InvocationContext(
                    session_service=parent_ctx.session_service,
                    agent=target_agent,
                    session=parent_ctx.session,
                    invocation_id=invocation_id,
                    user_content=Content(parts=[Part(text=task_content)])
                )
                
                # Stream events from the sub-agent
                async for event in target_agent.run_async(sub_ctx):
                    yield event
                    
            except Exception as e:
                logger.error(f"Error calling {agent_name}: {e}", exc_info=True)
                yield Event(invocation_id=invocation_id, author=self.name, content=Content(parts=[Part(text=f"Error: {e}")]))


    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """
        Main Workflow: Classify -> Route -> Execute.
        """
        current_invocation_id = ctx.invocation_id
        
        user_prompt = ""
        if ctx.user_content and ctx.user_content.parts:
            user_prompt = ctx.user_content.parts[0].text
        
        with tracer.start_as_current_span("orchestrate_agent.run") as span:
            try:
                # 1. Classify
                intent = await self.classify_intent(user_prompt)
                logger.info(f"Classified intent: {intent}")
                
                # Yield classification thought
                yield Event(
                    invocation_id=current_invocation_id,
                    author=self.name, 
                    content=Content(parts=[Part(text=f"I've classified your request as: {intent.value}")])
                )
                
                # 2. Route
                if intent == UserIntent.PLAN:
                    async for event in self._invoke_remote_agent("planner_agent", user_prompt, current_invocation_id, ctx): yield event
                elif intent == UserIntent.SOCIAL:
                    async for event in self._invoke_remote_agent("social_agent", user_prompt, current_invocation_id, ctx): yield event
                elif intent == UserIntent.PLATFORM:
                    async for event in self._invoke_remote_agent("platform_mcp_client_agent", user_prompt, current_invocation_id, ctx): yield event
                else:
                    yield Event(
                        invocation_id=current_invocation_id,
                        author=self.name, 
                        content=Content(parts=[Part(text="I'm not sure how to help with that request.")])
                    )
                    
            except Exception as e:
                logger.error(f"Orchestration Error: {e}", exc_info=True)
                yield Event(invocation_id=current_invocation_id, author=self.name, content=Content(parts=[Part(text=f"Error: {e}")]))
                raise

OrchestrateServiceAgent.model_rebuild()

def create_agent(model, planner_url, social_url, platform_url):
    logger.info(f"CREATE_AGENT - Planner URL: {planner_url}")
    logger.info(f"CREATE_AGENT - Social URL: {social_url}")
    logger.info(f"CREATE_AGENT - Platform URL: {platform_url}")
    return OrchestrateServiceAgent(
        name="orchestrate_service_agent",
        model=model,
        planner_agent_resource_name=planner_url,
        social_agent_resource_name=social_url,
        platform_mcp_client_agent_resource_name=platform_url
    )

# Use valid model
gemini_model = os.getenv("COMMON_GEMINI_MODEL", "gemini-2.5-flash")

root_agent = create_agent(
    model=gemini_model,
    planner_url=os.getenv("PLANNER_AGENT_URL", ""),
    social_url=os.getenv("SOCIAL_AGENT_URL", ""),
    platform_url=os.getenv("PLATFORM_MCP_CLIENT_AGENT_URL", "")
)