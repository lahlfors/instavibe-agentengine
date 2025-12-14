# In agents/app/agent_engine_adk_app.py
import logging
import time
import asyncio
import vertexai
from vertexai.preview import reasoning_engines
from google.adk.agents import Agent as AdkAgentType
from typing import Optional, List, Dict, Any, Iterator, Union, Literal
from google.api_core import exceptions

logger = logging.getLogger(__name__)

ReasoningEngine = reasoning_engines.ReasoningEngine
AdkApp = reasoning_engines.AdkApp


class VertexAdkProxy:
    """
    A Lazy Composition Proxy for AdkApp.
    
    This class solves TWO critical issues:
    1. Composition: Hides 'async' methods from Vertex Inspector
    2. Lazy Init: Enables the 'Picklable A2A Protocol' by deferring 
       client initialization until runtime
    
    Instead of inheriting from AdkApp (which exposes async methods) and 
    instead of calling set_up() in __init__ (which creates unpicklable locks),
    this proxy defers ALL initialization until the first query on the server.
    """

    def __init__(self, agent: AdkAgentType, env_vars: Optional[Dict[str, str]] = None):
        """
        LIGHTWEIGHT initialization for pickleability.
        
        We create the wrapper but DO NOT call set_up(). This keeps the 
        object "cold" so it can be pickled and uploaded to Agent Engine.
        
        Args:
            agent: The ADK agent to wrap
            env_vars: Environment variables to set on the server-side runtime
        """
        # Create the real AdkApp internally (lightweight, picklable)
        self._internal_app = AdkApp(agent=agent)
        self._env_vars = env_vars or {}
        
        # Track initialization state
        self._is_initialized = False
        
        # CRITICAL FIX: Apply environment variables IMMEDIATELY if we're on the server
        # Detect server environment by checking for Reasoning Engine-specific env vars
        import os
        if os.getenv("K_SERVICE") or os.getenv("REASONING_ENGINE_ID"):
            # We're on the server! Apply env vars NOW
            if self._env_vars:
                logger.info(f"🔥🔥🔥 __init__: Detected server environment, applying {len(self._env_vars)} environment variables...")
                for key, value in self._env_vars.items():
                    os.environ[key] = value
                    logger.info(f"  🔥 Set {key}={value[:50]}...")
                logger.info("🔥🔥🔥 __init__: Environment variables applied successfully!")
    
    def __setstate__(self, state):
        """Called when unpickling on the server. Apply env vars IMMEDIATELY."""
        # Restore the object's state
        self.__dict__.update(state)
        
        # CRITICAL: Apply environment variables IMMEDIATELY upon unpickling
        # This runs on the server BEFORE any other methods are called
        if hasattr(self, '_env_vars') and self._env_vars:
            import os
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"🔥 __setstate__: Applying {len(self._env_vars)} environment variables during unpickling...")
            for key, value in self._env_vars.items():
                os.environ[key] = value
                logger.info(f"  🔥 Set {key}={value[:50]}...")
            logger.info("🔥 __setstate__: Environment variables applied successfully!")


    def _ensure_app_ready(self):
        """
        Ensures the internal AdkApp is set up.
        
        This method is called lazily on the server-side when a method is first invoked.
        It prevents unpicklable objects (like thread locks from set_up()) from being
        created during client-side initialization.
        """
        if not self._is_initialized:
            logger.info("🚀 Lazily initializing AdkApp on the server...")
            logger.info(f"🔍 DEBUG: _env_vars keys: {list(self._env_vars.keys()) if self._env_vars else 'None'}")
            
            # Apply environment variables if provided
            if self._env_vars:
                import os
                logger.info(f"🔧 Applying {len(self._env_vars)} environment variables...")
                for key, value in self._env_vars.items():
                    os.environ[key] = value
                    logger.info(f"  ✓ Set {key}={value[:50]}...")
            else:
                logger.warning("⚠️ No environment variables to apply!")
            
            # Call set_up() on the underlying agent if it has one
            # This is critical for agents like OrchestrateServiceAgent that need
            # to initialize connections after environment variables are set
            logger.info(f"🔍 DEBUG: _internal_app type: {type(self._internal_app)}")
            logger.info(f"🔍 DEBUG: hasattr(_internal_app, 'agent'): {hasattr(self._internal_app, 'agent')}")
            
            if hasattr(self._internal_app, 'agent'):
                logger.info(f"🔍 DEBUG: _internal_app.agent type: {type(self._internal_app.agent)}")
                logger.info(f"🔍 DEBUG: hasattr(_internal_app.agent, 'set_up'): {hasattr(self._internal_app.agent, 'set_up')}")
                
                if hasattr(self._internal_app.agent, 'set_up'):
                    logger.info(f"📞 Calling set_up() on underlying agent: {self._internal_app.agent.__class__.__name__}")
                    self._internal_app.agent.set_up()
                else:
                    logger.warning(f"⚠️ Agent {self._internal_app.agent.__class__.__name__} has no set_up() method")
            else:
                logger.warning("⚠️ _internal_app has no 'agent' attribute!")
            
            logger.info("📞 Calling _internal_app.set_up()...")
            self._internal_app.set_up()
            self._is_initialized = True
            logger.info("✅ AdkApp initialized.")
        else:
            logger.info("ℹ️ AdkApp already initialized, skipping...")
        
        return self._internal_app


    def query(
        self,
        *,
        input: Union[str, Dict[str, Any], None] = None,
        message: Union[str, Dict[str, Any], None] = None,
        user_id: str = "default-user",
        session_id: Optional[str] = None,
        run_config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Iterator[Any]:
        """
        Synchronous bridge method exposed to Vertex AI as 'stream' mode.
        
        Vertex detects: def query(...) -> Iterator
        Mode registered: "stream"
        
        This method:
        1. Lazily initializes the app (connects to sub-agents/databases)
        2. Creates a local event loop for this request
        3. Bridges async implementation to sync interface
        
        Args:
            input: The input string (preferred, standard Vertex AI parameter name)
            message: Alternative parameter name for backward compatibility
            user_id: User identifier (default: "default-user")
            session_id: Optional session ID
            run_config: Optional run configuration
            **kwargs: Additional arguments
            
        Yields:
            Events from the agent's async stream
        """
        # Normalize input/message - prefer 'input' if provided
        # Vertex AI passes the Struct as a dict to the 'input' parameter
        # If we received {"input": "prompt"}, then input variable is {"input": "prompt"}
        # We need to extract the inner string.
        raw_input = input if input is not None else message
        
        actual_message = ""
        if isinstance(raw_input, dict) and 'input' in raw_input:
            actual_message = raw_input['input']
        elif raw_input is not None:
            actual_message = raw_input
        else:
            actual_message = ""
        
        # 1. Warm up the app (Connect to sub-agents/databases NOW)
        app = self._ensure_app_ready()
        
        logger.info(f"VertexAdkProxy: invoking app.async_stream_query with message='{actual_message}'")

        # 2. Handle Event Loop (Robustly)
        import nest_asyncio
        nest_asyncio.apply()

        try:
            # If a loop is already running (e.g. uvicorn), use it.
            # nest_asyncio allows us to call run_until_complete() on it.
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop running, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Filter out 'stream' argument if present, as it's a client-side SDK flag
        # and not accepted by the underlying Runner.run_async
        kwargs.pop('stream', None)

        # 3. Call the internal async method
        # Note: session_id and user_id are only relevant for stateful agents (like Orchestrate)
        # Specialist agents should not use sessions, so we pass None if not provided
        async_gen = app.async_stream_query(
            message=actual_message,
            user_id=user_id,  # Always pass the user_id (defaults to "default-user")
            session_id=None,  # Always None for specialist agents to avoid "Invalid Session" errors
            run_config=run_config,
            **kwargs
        )

        # 4. Bridge Async -> Sync and ensure valid Event schema
        from google.adk.events import Event
        
        while True:
            try:
                chunk = loop.run_until_complete(async_gen.__anext__())
                
                # Ensure the event has an author field (required by Pydantic validation)
                # Pydantic objects are immutable, so we must reconstruct events without author
                if isinstance(chunk, Event) and not hasattr(chunk, 'author'):
                    # Reconstruct the Event with an author field
                    # Get the agent name from the internal app
                    agent_name = getattr(self._internal_app.agent, 'name', 'agent')
                    
                    # Create a new Event with all the original properties plus author
                    chunk = Event(
                        author=agent_name,
                        content=chunk.content if hasattr(chunk, 'content') else None,
                        actions=chunk.actions if hasattr(chunk, 'actions') else None,
                        invocation_id=chunk.invocation_id if hasattr(chunk, 'invocation_id') else None,
                    )
                
                yield chunk
            except StopAsyncIteration:
                break
        
        # Note: We do NOT close the loop if we didn't create it, 
        # and even if we did, it's safer to leave it for the runtime to manage
        # in this specific environment to avoid "loop closed" errors on subsequent calls.

    # --- Delegation for Session Methods ---
    
    async def call_agent(
        self, 
        agent_name: Literal["planner_agent", "social_agent", "platform_mcp_client_agent"],
        task_content: str,
        reasoning: str
    ) -> str:
        """
        Delegate a task to a specialist agent.
        """
        # Ensure app is ready
        app = self._ensure_app_ready()
        # Call the method on the internal app
        return await app.call_agent(agent_name, task_content, reasoning)

    @property
    def tools(self):
        return [self.call_agent]

    def set_up(self):
        self._ensure_app_ready()
    # Delegate to the lazy-loaded internal app
    
    def create_session(self, **kwargs):
        """Create a new session (lazy-loads app, then delegates)."""
        return self._ensure_app_ready().create_session(**kwargs)

    def get_session(self, **kwargs):
        """Get an existing session (lazy-loads app, then delegates)."""
        return self._ensure_app_ready().get_session(**kwargs)

    def list_sessions(self, **kwargs):
        """List sessions (lazy-loads app, then delegates)."""
        return self._ensure_app_ready().list_sessions(**kwargs)

    def delete_session(self, **kwargs):
        """Delete a session (lazy-loads app, then delegates)."""
        return self._ensure_app_ready().delete_session(**kwargs)


def find_existing_reasoning_engine(
    display_name: str, project: str, location: str
) -> Optional[ReasoningEngine]:
    """Finds an existing Reasoning Engine by display name."""
    try:
        filters = f'display_name="{display_name}"'
        engines = ReasoningEngine.list(filter=filters, project=project, location=location)
        return engines[0] if engines else None
    except Exception as e:
        logger.error(f"Error listing Reasoning Engines: {e}", exc_info=True)
        return None

def deploy_adk_agent_engine(
    agent_object: AdkAgentType,
    display_name: str,
    project: str,
    location: str,
    requirements: List[str],
    extra_packages: List[str],
    force_update: bool = False,
    env_vars: Optional[Dict[str, str]] = None,
    gcs_dir_name: Optional[str] = None,
) -> Optional[ReasoningEngine]:
    """ 
    Deploys a Reasoning Engine. 
    If force_update is True (default for this script), it deletes ALL existing engines 
    with the same display name first to ensure a clean state.
    """

    vertexai.init(project=project, location=location)

    logger.info(f"Wrapping ADK agent '{agent_object.name}' in VertexAdkProxy for deployment.")
    try:
        app = VertexAdkProxy(agent=agent_object, env_vars=env_vars)
    except Exception as e:
        logger.error(f"Failed to create VertexAdkProxy: {e}", exc_info=True)
        raise

    if force_update:
        logger.info(f"Force update requested. Checking for existing Reasoning Engines: '{display_name}'")
        
        try:
            # List all engines
            filters = f'display_name="{display_name}"'
            existing_agents = ReasoningEngine.list(filter=filters, project=project, location=location)
            
            if existing_agents:
                logger.info(f"Found {len(existing_agents)} existing agents to delete.")
                
                # Get access token for REST API calls
                import subprocess
                import requests
                
                token_result = subprocess.run(
                    ["gcloud", "auth", "print-access-token"],
                    capture_output=True,
                    text=True
                )
                access_token = token_result.stdout.strip()
                
                for agent in existing_agents:
                    logger.info(f"Deleting existing engine: {agent.resource_name}...")
                    try:
                        # Extract ID from resource name
                        # projects/{project}/locations/{location}/reasoningEngines/{id}
                        parts = agent.resource_name.split('/')
                        engine_id = parts[5]
                        
                        # Use REST API with force=true to delete child resources
                        url = f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project}/locations/{location}/reasoningEngines/{engine_id}"
                        headers = {"Authorization": f"Bearer {access_token}"}
                        params = {"force": "true"}
                        
                        response = requests.delete(url, headers=headers, params=params)
                        
                        if response.status_code == 200:
                            logger.info(f"✅ Deleted {agent.resource_name} successfully")
                        else:
                            logger.warning(f"⚠️ Failed to delete {agent.resource_name}: {response.status_code} - {response.text}")
                            
                        # Rate limit: 10 writes/min = 1 per 6 seconds
                        # We sleep briefly to be safe, though usually we don't have that many to delete if this runs regularly
                        time.sleep(6)
                        
                    except Exception as e:
                        logger.error(f"Failed to delete existing engine {agent.resource_name}: {e}")
            else:
                logger.info("No existing agents found. Proceeding with creation.")
                
        except Exception as e:
            logger.error(f"Error during cleanup of existing agents: {e}", exc_info=True)
            # Proceed anyway, creation might still work or fail if quota exceeded

    logger.info(f"Creating new Reasoning Engine for {display_name}...")
    try:
        # Prepare kwargs for create()
        create_kwargs = {
            "requirements": requirements,
            "extra_packages": extra_packages,
            "display_name": display_name,
        }
        # Only add gcs_dir_name if supported (check SDK version or just try)
        # Assuming it is supported as per user request
        if gcs_dir_name:
             create_kwargs["gcs_dir_name"] = gcs_dir_name

        remote_agent = ReasoningEngine.create(
            app,
            **create_kwargs
        )
        
        logger.info(f"Successfully created: {remote_agent.resource_name}")
        return remote_agent
        
    except Exception as e:
        logger.error(f"Failed to create new Reasoning Engine {display_name}: {e}", exc_info=True)
        raise
