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

    def __init__(self, agent: AdkAgentType):
        """
        LIGHTWEIGHT initialization for pickleability.
        
        We create the wrapper but DO NOT call set_up(). This keeps the 
        object "cold" so it can be pickled and uploaded to Agent Engine.
        
        Args:
            agent: The ADK agent to wrap
        """
        # Create the real AdkApp internally (lightweight, picklable)
        self._internal_app = AdkApp(agent=agent)
        
        # Track initialization state
        self._is_initialized = False

    def _ensure_app_ready(self):
        """
        Ensures the internal AdkApp is set up.
        
        This method is called lazily on the server-side when a method is first invoked.
        It prevents unpicklable objects (like thread locks from set_up()) from being
        created during client-side initialization.
        """
        if not self._is_initialized:
            logger.info("Lazily initializing AdkApp on the server...")
            self._internal_app.set_up()
            self._is_initialized = True
            logger.info("AdkApp initialized.")

    def _ensure_app_ready(self):
        """
        Lazy initialization hook for the Picklable A2A Protocol.
        
        This method hydrates the internal app (creating runners, locks, 
        session services, and A2A client connections) ONLY when running 
        inside the remote container, NOT during pickle/upload.
        
        This is critical for multi-agent workflows where a supervisor agent
        needs to connect to worker agents. If we initialized connections in
        __init__, the supervisor couldn't be pickled.
        
        Returns:
            The initialized internal AdkApp instance
        """
        if not self._is_initialized:
            # NOW we can safely create thread locks, gRPC channels, etc.
            # because we're running on the server, not in the deployment script
            self._internal_app.set_up()
            self._is_initialized = True
        return self._internal_app

    def query(
        self,
        *,
        message: Union[str, Dict[str, Any]] = "",
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
            message: The query message (str or dict)
            user_id: User identifier (default: "default-user")
            session_id: Optional session ID
            run_config: Optional run configuration
            **kwargs: Additional arguments
            
        Yields:
            Events from the agent's async stream
        """
        # 1. Warm up the app (Connect to sub-agents/databases NOW)
        app = self._ensure_app_ready()
        
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

        # 3. Call the internal async method
        async_gen = app.async_stream_query(
            message=message,
            user_id=user_id,
            session_id=session_id,
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
) -> Optional[ReasoningEngine]:
    """ Deploys or updates a Reasoning Engine. If force_update is True, deletes existing engine first. """

    vertexai.init(project=project, location=location)

    logger.info(f"Wrapping ADK agent '{agent_object.name}' in VertexAdkProxy for deployment.")
    try:
        app = VertexAdkProxy(agent=agent_object)
    except Exception as e:
        logger.error(f"Failed to create VertexAdkProxy: {e}", exc_info=True)
        raise

    logger.info(f"Checking for existing Reasoning Engine: '{display_name}'")
    existing_agent = find_existing_reasoning_engine(
        display_name=display_name, project=project, location=location
    )

    if existing_agent:
        if force_update:
            logger.info(f"Force update requested. Deleting existing engine: {existing_agent.resource_name}")
            try:
                existing_agent.delete()
                logger.info("Existing engine deleted successfully.")
                existing_agent = None # Clear it so we create a new one
            except Exception as e:
                logger.error(f"Failed to delete existing engine: {e}")
                # We might want to raise here, or try to create anyway (which might fail if name conflict, but RE names are IDs)
                # Usually REs are identified by ID, but we look up by display name.
                # If delete fails, we probably shouldn't proceed, but let's try.
        else:
            logger.info(f"Found existing engine: {existing_agent.resource_name}. Reusing it.")
            return existing_agent

    logger.info(f"Creating new Reasoning Engine for {display_name}...")
    try:
        remote_agent = ReasoningEngine.create(
            app,
            requirements=requirements,
            extra_packages=extra_packages,
            display_name=display_name,
        )
        
        logger.info(f"Successfully created: {remote_agent.resource_name}")
        return remote_agent
        
    except Exception as e:
        logger.error(f"Failed to create new Reasoning Engine {display_name}: {e}", exc_info=True)
        raise
