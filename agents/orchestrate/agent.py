import logging
import os
import sys
import asyncio
import json
from typing import Optional, AsyncGenerator, List, Callable, Any, Literal, Dict
from enum import Enum

# --- Imports ---
import google.auth
import google.auth.credentials
import nest_asyncio  # FIX: Top-level import to fail fast if missing
from opentelemetry import trace
import opentelemetry.semconv._incubating.attributes.gen_ai_attributes as ai_semconv
from google import genai
from google.adk.agents import Agent, InvocationContext
from google.genai.types import Content, Part
from google.adk.events import Event
from pydantic import Field, PrivateAttr, BaseModel
from vertexai.preview.reasoning_engines import ReasoningEngine
import vertexai

# --- Custom Imports ---
# NEW: Secure A2A infrastructure
from agents.common.secure_a2a import SecureRemoteA2aAgent, invoke_with_retry
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
    POST_PLAN_EVENT = "POST_PLAN_EVENT"
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
    # Using SecureRemoteA2aAgent for production-grade A2A communication
    planner_agent: Optional[SecureRemoteA2aAgent] = Field(default=None, exclude=True)
    social_agent: Optional[SecureRemoteA2aAgent] = Field(default=None, exclude=True)
    platform_mcp_client_agent: Optional[SecureRemoteA2aAgent] = Field(default=None, exclude=True)

    _model_client: Any = PrivateAttr(default=None)
    # Added fields for InvocationContext compatibility
    session_service: Optional[Any] = Field(default=None, exclude=True)
    session: Optional[Any] = Field(default=None, exclude=True)

    def __post_init__(self):
        super().__post_init__()
        # Only load from env if not already set (e.g. by constructor)
        if not self.project:
            self.project = os.getenv("COMMON_GOOGLE_CLOUD_PROJECT")
        if not self.location:
            self.location = os.getenv("COMMON_GOOGLE_CLOUD_LOCATION")
            
        self.otel_collector_endpoint = os.getenv("OTEL_COLLECTOR_ENDPOINT")
        
        logger.info(f"🔍 DEBUG: __post_init__ - Project: {self.project}, Location: {self.location}")
        
        # Initialize Vertex AI SDK (Critical for GenerativeModel)
        if self.project and self.location:
            # vertexai.init(project=self.project, location=self.location) # No longer needed for google.genai
            logger.info(f"✅ Initializing google.genai.Client for project {self.project} in {self.location}")
            try:
                self._model_client = genai.Client(vertexai=True, project=self.project, location=self.location)
                logger.info("✅ Successfully initialized google.genai.Client")
            except Exception as e:
                logger.error(f"❌ Failed to initialize google.genai.Client: {e}")
                self._model_client = None
        else:
            logger.warning("⚠️ Missing project/location env vars. google.genai.Client init skipped.")

        # if self.model:
        #     self._model_client = GenerativeModel(self.model)
        
        self.tools = []
        # Eager init REMOVED to support lazy loading on server with correct env vars
        # self._initialize_remote_agents()

    def set_up(self):
        """Lazy initialization called by Vertex AI (or VertexAdkProxy)."""
        logger.info("🚀 OrchestrateServiceAgent.set_up() called")
        self._initialize_remote_agents()

    
    def _initialize_remote_agents(self):
        """Initialize remote A2A agent clients using Secure A2A Discovery."""
        logger.info("🔐 _initialize_remote_agents called (Secure A2A Mode)")
        logger.info(f"🔍 DEBUG: PLANNER_AGENT_URL from os.environ: {os.getenv('PLANNER_AGENT_URL', 'NOT_SET')}")
        logger.info(f"🔍 DEBUG: SOCIAL_AGENT_URL from os.environ: {os.getenv('SOCIAL_AGENT_URL', 'NOT_SET')}")
        logger.info(f"🔍 DEBUG: PLATFORM_MCP_CLIENT_AGENT_URL from os.environ: {os.getenv('PLATFORM_MCP_CLIENT_AGENT_URL', 'NOT_SET')}")
        
        # Configuration Fallback - recover from environment if fields are empty
        if not self.planner_agent_resource_name:
            self.planner_agent_resource_name = os.getenv("PLANNER_AGENT_URL", "")
        if not self.social_agent_resource_name:
            self.social_agent_resource_name = os.getenv("SOCIAL_AGENT_URL", "")
        if not self.platform_mcp_client_agent_resource_name:
            self.platform_mcp_client_agent_resource_name = os.getenv("PLATFORM_MCP_CLIENT_AGENT_URL", "")
        
        # A2A requires that at least the planner is defined.
        if not self.planner_agent_resource_name:
            raise ValueError("PLANNER_AGENT_URL must be defined.")

        logger.info(f"🔐 Final - Planner Resource: {self.planner_agent_resource_name}")
        logger.info(f"🔐 Final - Social Resource: {self.social_agent_resource_name}")
        logger.info(f"🔐 Final - Platform Resource: {self.platform_mcp_client_agent_resource_name}")

        # Initialize Secure A2A Clients with Dynamic Card Discovery
        # Cards are fetched lazily from /.well-known/agent.json
        
        try:
            # Initialize Planner Agent (Cloud Run with A2A protocol)
            if self.planner_agent_resource_name:
                # Use Cloud Run URL instead of Reasoning Engine
                planner_base_url = os.getenv(
                    "PLANNER_AGENT_URL",
                    "https://planner-agent-lyejyshilq-uc.a.run.app"
                )
                
                logger.info(f"🔧 Initializing Planner Agent (Cloud Run)")
                logger.info(f"   URL: {planner_base_url}")
                
                # Dynamic card discovery - fetch from /.well-known/agent.json
                self.planner_agent = SecureRemoteA2aAgent(
                    name="planner_agent",
                    description="Interface to the Planner Agent",
                    agent_card_url=f"{planner_base_url}/.well-known/agent.json",
                    scopes=['https://www.googleapis.com/auth/cloud-platform']
                )
                logger.info(f"✅ Initialized Planner Agent with dynamic card discovery")
            
            if self.social_agent_resource_name:
                # Initialize Social Agent (Cloud Run with A2A protocol)
                # Use Cloud Run URL instead of Reasoning Engine
                social_base_url = os.getenv(
                    "SOCIAL_AGENT_URL",
                    "https://social-agent-lyejyshilq-uc.a.run.app"
                )
                
                logger.info(f"🔧 Initializing Social Agent (Cloud Run)")
                logger.info(f"   URL: {social_base_url}")
                
                # Dynamic card discovery - fetch from /.well-known/agent.json
                self.social_agent = SecureRemoteA2aAgent(
                    name="social_agent",
                    description="Interface to the Social Agent",
                    agent_card_url=f"{social_base_url}/.well-known/agent.json",
                    scopes=['https://www.googleapis.com/auth/cloud-platform']
                )
                logger.info(f"✅ Initialized Social Agent with dynamic card discovery")

            if self.platform_mcp_client_agent_resource_name:
                # Initialize Platform MCP Client Agent (Cloud Run with A2A protocol)
                # Use Cloud Run URL instead of Reasoning Engine
                platform_base_url = os.getenv(
                    "PLATFORM_AGENT_URL",
                    "https://platform-mcp-client-agent-lyejyshilq-uc.a.run.app"
                )
                
                logger.info(f"🔧 Initializing Platform MCP Client Agent (Cloud Run)")
                logger.info(f"   URL: {platform_base_url}")
                
                # Dynamic card discovery - fetch from /.well-known/agent.json
                self.platform_mcp_client_agent = SecureRemoteA2aAgent(
                    name="platform_mcp_client_agent",
                    description="Interface to the Platform MCP Client Agent",
                    agent_card_url=f"{platform_base_url}/.well-known/agent.json",
                    scopes=['https://www.googleapis.com/auth/cloud-platform']
                )
                logger.info(f"✅ Initialized Platform MCP Client Agent with dynamic card discovery")
                
        except Exception as e:
            logger.error(f"Failed to initialize secure A2A agents: {e}", exc_info=True)

    def _fetch_agent_card_from_query(self, resource_name: str):
        """
        Fetch Agent Card by calling the agent's query endpoint with GET_AGENT_CARD.
        
        This is a workaround for agents deployed via VertexAdkProxy that don't
        automatically expose the .well-known/agent.json endpoint.
        
        Returns the agent card dictionary with the URL injected.
        """
        import google.auth
        import google.auth.transport.requests
        import requests
        import json
        
        logger.info(f"🃏 Fetching Agent Card via query for {resource_name}...")
        
        # 1. Parse location from resource name
        try:
            parts = resource_name.split('/')
            if 'locations' not in parts:
                raise ValueError("Invalid resource name format")
            loc_idx = parts.index('locations')
            location = parts[loc_idx + 1]
        except Exception as e:
            logger.error(f"Failed to parse resource name: {e}")
            raise
            
        # 2. Construct query URL and A2A base URL
        query_url = f"https://{location}-aiplatform.googleapis.com/v1beta1/{resource_name}:query"
        a2A_base_url = f"https://{location}-aiplatform.googleapis.com/v1beta1/{resource_name}/a2a"
        
        # 3. Get credentials
        try:
            creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
            auth_req = google.auth.transport.requests.Request()
            creds.refresh(auth_req)
        except Exception as e:
            logger.error(f"Failed to get credentials: {e}")
            raise
            
        # 4. Call query endpoint
        headers = {
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json"
        }
        body = {"input": {"input": "GET_AGENT_CARD"}}
        
        try:
            response = requests.post(query_url, json=body, headers=headers, timeout=30)
            response.raise_for_status()
            resp_json = response.json()
            
            # 5. Parse response
            card_dict = None
            if "candidates" in resp_json:
                text = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    import ast
                    parsed = ast.literal_eval(text)
                
                if isinstance(parsed, dict) and "agent_card" in parsed:
                    card_dict = parsed["agent_card"]
                else:
                    card_dict = parsed
            else:
                card_dict = resp_json
                
            # 6. Inject the A2A base URL
            if card_dict and "url" not in card_dict:
                card_dict["url"] = a2a_base_url
                logger.info(f"🔗 Injected A2A URL: {a2a_base_url}")
            
            # 7. Return the dictionary - let RemoteA2aAgent parse it
            if card_dict:
                logger.info(f"✅ Successfully fetched Agent Card dictionary")
                return card_dict
            else:
                raise ValueError("Failed to parse agent card from response")
                
        except Exception as e:
            logger.error(f"Failed to fetch agent card: {e}", exc_info=True)
            raise

    def _construct_agent_card_url(self, resource_name: str) -> str:
        """
        Constructs the standard Agent Engine Agent Card URL from a resource name.
        
        Format: https://{LOCATION}-aiplatform.googleapis.com/v1beta1/{RESOURCE_NAME}/a2a/.well-known/agent.json
        """
        if not resource_name or not resource_name.startswith("projects/"):
            return resource_name
            
        try:
            parts = resource_name.split('/')
            if 'locations' in parts:
                loc_idx = parts.index('locations')
                location = parts[loc_idx + 1]
                return f"https://{location}-aiplatform.googleapis.com/v1beta1/{resource_name}/a2a/.well-known/agent.json"
        except Exception:
            pass
            
        return resource_name



    @property
    def model_client(self) -> genai.Client | None:
        return self._model_client

    async def _async_set_up(self, reasoning_engine_id: Optional[str] = None, **kwargs):
        """
        Async setup: Initializes Memory and Remote A2A Clients.
        Includes robust fallback to Env Vars if configuration is missing.
        """
        logger.info(f"--- Running _async_set_up for {self.__class__.__name__} ---")
        
        # --- DIAGNOSTIC CODE TO IDENTIFY ENVIRONMENT / SERVICE ACCOUNT ---
        print(f"#### DIAGNOSTIC #### ENV_VAR: GOOGLE_APPLICATION_CREDENTIALS = {os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'NOT_SET')}")
        print(f"#### DIAGNOSTIC #### ENV_VAR: GCLOUD_PROJECT = {os.getenv('GCLOUD_PROJECT', 'NOT_SET')}")
        print(f"#### DIAGNOSTIC #### ENV_VAR: CLOUD_RUN_SERVICE_ACCOUNT_EMAIL = {os.getenv('CLOUD_RUN_SERVICE_ACCOUNT_EMAIL', 'NOT_SET')}")
        try:
            credentials, project_id = google.auth.default()
            if hasattr(credentials, 'service_account_email'):
                print(f"#### DIAGNOSTIC #### AGENT IDENTITY (SERVICE ACCOUNT - from google.auth): {credentials.service_account_email}")
            else:
                print("#### DIAGNOSTIC #### AGENT IDENTITY (USER OR OTHER - from google.auth): Could not determine service account email from credentials.")
        except Exception as e:
            print(f"#### DIAGNOSTIC #### AGENT IDENTITY: Failed to get default credentials via google.auth.default(): {e}")
        # --- END DIAGNOSTIC CODE ---
        
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
            self.planner_agent_resource_name = os.getenv("PLANNER_AGENT_URL", "")
        if not self.social_agent_resource_name:
            self.social_agent_resource_name = os.getenv("SOCIAL_AGENT_URL", "")
        if not self.platform_mcp_client_agent_resource_name:
            self.platform_mcp_client_agent_resource_name = os.getenv("PLATFORM_MCP_CLIENT_AGENT_URL", "")

        # A2A requires that at least the planner is defined.
        if not self.planner_agent_resource_name:
            raise ValueError("PLANNER_AGENT_URL must be defined.")

        logger.info(f"ASYNC_SET_UP - Final - Planner URL: {self.planner_agent_resource_name}")
        logger.info(f"ASYNC_SET_UP - Final - Social URL: {self.social_agent_resource_name}")
        logger.info(f"ASYNC_SET_UP - Final - Platform URL: {self.platform_mcp_client_agent_resource_name}")

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
        logger.info(f"🔍 DEBUG: classify_intent - _model_client: {self._model_client is not None}, Project: {self.project}, Location: {self.location}")
        
        if not self._model_client and self.project and self.location:
            logger.info("🔄 Hydrating model client after cold start...")
            self._model_client = genai.Client(vertexai=True, project=self.project, location=self.location)
            
        from .intention_classifier import IntentClassifier
        # Pass both client and model name
        classifier = IntentClassifier(self._model_client, self.model)
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
                
                # Stream events from the sub-agent with retry logic
                logger.info(f"🚀 Sending A2A request to {agent_name}...")
                async for event in invoke_with_retry(target_agent.run_async, sub_ctx):
                    logger.info(f"📥 Received event from {agent_name}: {event.content.parts[0].text[:50]}...")
                    yield event
                logger.info(f"✅ Finished A2A stream from {agent_name}")
                    
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
                elif intent == UserIntent.POST_PLAN_EVENT:
                    async for event in self._invoke_remote_agent("platform_mcp_client_agent", user_prompt, current_invocation_id, ctx): yield event
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

def create_agent(model, planner_url, social_url, platform_url, project, location):
    logger.info(f"CREATE_AGENT - Planner URL: {planner_url}")
    logger.info(f"CREATE_AGENT - Social URL: {social_url}")
    logger.info(f"CREATE_AGENT - Platform URL: {platform_url}")
    logger.info(f"CREATE_AGENT - Project: {project}, Location: {location}")

    # CRITICAL: Initialize Vertex AI SDK *before* agent instantiation
    # This ensures the Agent base class uses the correct backend (Vertex AI) 
    # instead of defaulting to Google AI (which needs an API key).
    # if project and location:
    #     vertexai.init(project=project, location=location)
    #     logger.info(f"✅ CREATE_AGENT - Initialized Vertex AI SDK")
    # else:
    #     logger.warning("⚠️ CREATE_AGENT - Missing project/location. Vertex AI init skipped.")

    return OrchestrateServiceAgent(
        name="orchestrate_service_agent",
        model=model,
        project=project,
        location=location,
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
    platform_url=os.getenv("PLATFORM_MCP_CLIENT_AGENT_URL", ""),
    project=os.getenv("COMMON_GOOGLE_CLOUD_PROJECT", ""),
    location=os.getenv("COMMON_GOOGLE_CLOUD_LOCATION", "")
)