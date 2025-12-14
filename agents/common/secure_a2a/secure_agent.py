"""
Secure Remote A2A Agent Wrapper

High-level wrapper that abstracts the complexity of secure A2A communication
from agent developers.

Based on Section 4.4 of the Secure A2A reference architecture.
"""

import logging
from typing import Optional, List, Any
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from a2a.client import ClientConfig
from a2a.types import TransportProtocol
from .client_factory import LazyAuthClientFactory

logger = logging.getLogger(__name__)


class SecureRemoteA2aAgent(RemoteA2aAgent):
    """
    A production-ready wrapper for RemoteA2aAgent with dynamic card discovery.
    
    This class abstracts the complexity of the ClientFactory and AuthHandler
    from the main agent logic. The developer simply provides the agent card URL
    and all security/serialization handling is automatic.
    
    Key Features:
    -------------
    - Dynamic AgentCard discovery from /.well-known/agent.json
    - Automatic OIDC token management (no API keys needed)
    - Lazy httpx client initialization (pickling-safe)
    - W3C trace context propagation
    - Configurable timeouts and retry policies
    - VPC-SC proxy support
    
    Security Model:
    ---------------
    This agent uses the service account identity of the Vertex AI Agent Engine
    runtime to authenticate to remote agents. No static credentials are stored.
    
    Example:
        planner = SecureRemoteA2aAgent(
            name="planner_agent",
            description="Creates fun, personalized event plans",
            agent_card_url="https://planner-agent.../well-known/agent.json"
        )
        
        # Later, in the orchestrator:
        result = await planner.invoke("Plan a birthday in Seattle")
    """
    
    def __init__(
        self, 
        name: str, 
        description: str, 
        agent_card_url: str,
        scopes: Optional[List[str]] = None,
        timeout: float = 60.0,
        proxy_url: Optional[str] = None
    ):
        """
        Initialize the secure A2A agent with dynamic card discovery.
        
        Args:
            name: Internal identifier for this agent
            description: Human-readable description of agent capabilities
            agent_card_url: URL to fetch the AgentCard (e.g., https://.../.well-known/agent.json)
            scopes: OAuth2 scopes for auth (defaults to cloud-platform)
            timeout: HTTP request timeout in seconds
            proxy_url: Optional HTTP proxy URL for VPC-SC environments
        """
        # Save configuration parameters for unpickling
        self._scopes = scopes
        self._timeout = timeout
        self._proxy_url = proxy_url
        self._agent_card_url = agent_card_url

        
        # 1. Configure the A2A Client Preference
        # Use JSON-RPC transport to match the to_a2a server protocol
        client_config = ClientConfig(
            supported_transports=[TransportProtocol.jsonrpc],
            use_client_preference=True,
        )
        
        # 2. Instantiate our Lazy Factory
        # We assign it immediately, but it won't create the heavy httpx client
        # until 'invoke' is called.
        self._a2a_client_factory = LazyAuthClientFactory(
            config=client_config,
            scopes=scopes,
            timeout=timeout,
            proxy_url=proxy_url
        )
        
        logger.info(f"🔐 Initializing SecureRemoteA2aAgent: {name}")
        logger.info(f"   Agent Card URL: {agent_card_url}")
        logger.debug(f"   OAuth Scopes: {scopes or ['cloud-platform']}")
        
        # 3. Initialize the Parent Class (RemoteA2aAgent)
        # Pass the URL string - RemoteA2aAgent will fetch the card lazily at runtime
        # CRITICAL FIX: Pass our custom factory so it's used instead of the default one
        super().__init__(
            name=name,
            description=description,
            agent_card=agent_card_url,  # Pass URL string for dynamic resolution
            a2a_client_factory=self._a2a_client_factory
        )

        
        logger.info(f"✅ SecureRemoteA2aAgent '{name}' ready (lazy card discovery)")

    def __setstate__(self, state):
        """
        Called when unpickling. Recreate the _a2a_client_factory.
        
        This is critical because _a2a_client_factory contains unpickleable objects 
        (like httpx.AsyncClient) and must be recreated on the server.
        """
        # Restore all the basic attributes
        self.__dict__.update(state)
        
        # Recreate the client factory with the same configuration
        # (it will be lazy-initialized when first used)
        from a2a.client import ClientConfig
        from a2a.types import TransportProtocol
        
        client_config = ClientConfig(
            supported_transports=[TransportProtocol.jsonrpc],
            use_client_preference=True,
        )
        
        # Recreate the factory (lazy, so no heavy initialization yet)
        self._a2a_client_factory = LazyAuthClientFactory(
            config=client_config,
            scopes=getattr(self, '_scopes', None),
            timeout=getattr(self, '_timeout', 60.0),
            proxy_url=getattr(self, '_proxy_url', None)
        )
        
        logger.info(f"🔄 SecureRemoteA2aAgent '{self.name}' restored after unpickling")

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (f"SecureRemoteA2aAgent(name='{self.name}', "
                f"description='{self.description[:50]}...', "
                f"agent_card_url='{self._agent_card_url}')")
