"""
Lazy-Loading Client Factory for A2A Communication

Solves the critical pickling problem when deploying to Vertex AI Agent Engine
by deferring httpx.AsyncClient creation until runtime.

Based on Section 4.3 of the Secure A2A reference architecture.
"""

import logging
import httpx
from typing import Optional, List
from a2a.client import ClientFactory, ClientConfig
from a2a.types import TransportProtocol
from .auth_handler import GoogleAuthRefresh

logger = logging.getLogger(__name__)


class LazyAuthClientFactory(ClientFactory):
    """
    A custom Factory for creating A2A Clients with Lazy Loading and Secure Auth.
    
    The Problem:
    ------------
    The standard RemoteA2aAgent initializes its httpx client immediately in __init__.
    This causes deployment failures on Vertex AI because httpx.AsyncClient contains
    thread locks (_thread.RLock) and SSL contexts that cannot be pickled.
    
    The Solution:
    -------------
    This factory stores only pickleable configuration (strings, lists) and creates
    the heavyweight httpx.AsyncClient ONLY when it is actually needed at runtime,
    ensuring the agent object remains pickleable during the build/deploy phase.
    
    Architecture:
    -------------
    - __init__: Stores config as primitive types (pickleable)
    - create(): Creates httpx client JIT (Just-In-Time) when first A2A call is made
    - __getstate__/__setstate__: Ensures client is not pickled
    
    Attributes:
        scopes: OAuth2 scopes for authentication (pickleable list of strings)
        timeout: HTTP timeout in seconds (pickleable float)
        proxy_url: Optional proxy URL for VPC-SC environments (pickleable string)
    
    Example:
        config = ClientConfig(supported_transports=[TransportProtocol.http_json])
        factory = LazyAuthClientFactory(config, scopes=['https://www.googleapis.com/auth/cloud-platform'])
        # At this point, no httpx client exists yet - object is pickleable
        
        # Later, when deployed to Agent Engine and invoke() is called:
        client = factory.create(agent_card)  # NOW the httpx client is created
    """
    
    def __init__(
        self, 
        config: ClientConfig, 
        scopes: Optional[List[str]] = None,
        timeout: float = 60.0,
        proxy_url: Optional[str] = None
    ):
        """
        Initialize factory with pickleable configuration only.
        
        Args:
            config: A2A client configuration
            scopes: OAuth2 scopes for authentication
            timeout: HTTP request timeout in seconds
            proxy_url: Optional HTTP proxy for VPC-SC environments
        """
        super().__init__(config)
        
        # Store ONLY pickleable primitives
        self.scopes = scopes or ['https://www.googleapis.com/auth/cloud-platform']
        self.timeout = timeout
        self.proxy_url = proxy_url
        
        logger.debug("LazyAuthClientFactory initialized (no httpx client yet)")

    def create(self, card, consumers=None, interceptors=None):
        """
        Creates (or retrieves cached) HTTP client with authentication injection.
        
        This method is called by the ADK runtime when an A2A invocation occurs.
        It performs Just-In-Time initialization of the httpx client.
        
        Flow:
        -----
        1. Check if httpx client already exists in config
        2. If not, create it NOW (not during __init__)
        3. Inject GoogleAuthRefresh for automatic token management
        4. Register A2A transport protocols
        5. Proceed with standard ADK client creation
        
        Args:
            card: Agent Card from the remote agent
            consumers: Optional message consumers
            interceptors: Optional request interceptors
            
        Returns:
            A2A client instance ready for communication
        """
        # HACK: Proactively fix URL encoding on the agent card itself.
        # This ensures all downstream consumers (including the parent class) get the correct URL.
        if hasattr(card, 'url') and card.url and '.run.app' in card.url and '%3A' in card.url:
            original_url = card.url
            card.url = original_url.replace('%3A', ':')
            logger.warning(f"Patched card URL from {original_url} to {card.url} to fix encoding issue.")
        # HACK: Proactively fix URL encoding on the agent card itself.
        # This ensures all downstream consumers (including the parent class) get the correct URL.
        if hasattr(card, 'url') and card.url and '.run.app' in card.url and '%3A' in card.url:
            original_url = card.url
            card.url = original_url.replace('%3A', ':')
            logger.warning(f"Patched card URL from {original_url} to {card.url} to fix encoding issue.")
        # HACK: Proactively fix URL encoding on the agent card itself.
        # This ensures all downstream consumers (including the parent class) get the correct URL.
        if hasattr(card, 'url') and card.url and '.run.app' in card.url and '%3A' in card.url:
            original_url = card.url
            card.url = original_url.replace('%3A', ':')
            logger.warning(f"Patched card URL from {original_url} to {card.url} to fix encoding issue.")
        # CRITICAL DEBUG: URL Patching for Cloud Run A2A endpoints
        # This ensures all downstream consumers (including the parent class) get the correct URL.
        print(f"[CLIENT_FACTORY] DEBUG: Initial card.url: {getattr(card, 'url', 'N/A')}", flush=True)
        logger.info(f"DEBUG: Initial card.url: {getattr(card, 'url', 'N/A')}")
        
        if hasattr(card, 'url') and card.url and '.run.app' in card.url and '%3A' in card.url:
            original_url = card.url
            card.url = original_url.replace('%3A', ':')
            print(f"[CLIENT_FACTORY] ✅ PATCHED: {original_url} -> {card.url}", flush=True)
            logger.warning(f"DEBUG: Patched card URL from {original_url} to {card.url} to fix encoding issue.")
        else:
            print(f"[CLIENT_FACTORY] INFO: card.url did not need patching.", flush=True)
            logger.info("DEBUG: card.url did not need patching.")

        # Check if the client is already initialized in the configuration
        if not self._config.httpx_client:
            print(f"[CLIENT_FACTORY] Initializing httpx client (JIT)", flush=True)
            logger.info("🔧 Initializing LazyAuthClientFactory httpx client (JIT)")
            
            # Determine if we're calling a Cloud Run service or a GCP API
            # Cloud Run URLs end with .run.app
            target_url = card.url if hasattr(card, 'url') else None
            print(f"[CLIENT_FACTORY] target_url: {target_url}", flush=True)
            logger.info(f"DEBUG: target_url for auth handler: {target_url}")
            
            use_id_token = target_url and '.run.app' in target_url
            
            if use_id_token:
                logger.info(f"🔐 Detected Cloud Run target: {target_url}")
                logger.info(f"   Using ID token authentication with audience: {target_url}")
                # For Cloud Run, we use ID tokens with the service URL as audience
                auth_handler = GoogleAuthRefresh(target_audience=target_url, scopes=self.scopes)
            else:
                logger.info(f"🔐 Detected GCP API target")
                logger.info(f"   Using Access token authentication with scopes: {self.scopes}")
                # For GCP APIs (like Vertex AI), we use access tokens with scopes
                auth_handler = GoogleAuthRefresh(scopes=self.scopes)
            
            # Build httpx client configuration
            httpx_config = {
                'timeout': self.timeout,
                'headers': {'Content-Type': 'application/json'},
                'auth': auth_handler,
            }
            
            # Add proxy configuration if in VPC-SC environment
            if self.proxy_url:
                httpx_config['proxies'] = self.proxy_url
                logger.info(f"Configured HTTP proxy: {self.proxy_url}")
            
            # Create the AsyncClient with the auth handler
            # We set a generous timeout (60s) because agent reasoning can be slow.
            self._config.httpx_client = httpx.AsyncClient(**httpx_config)
            
            # Register supported transports (JSON-RPC over HTTP is standard for A2A)
            self._register_defaults(self._config.supported_transports)
            
            logger.info("✅ HTTP client created and configured for A2A")
        
        # Proceed with the standard ADK client creation logic
        try:
            return super().create(card, consumers, interceptors)
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"❌ ClientFactory.create failed: {error_msg}")
            logger.error(f"   Card name: {card.name}")
            logger.error(f"   Card preferred_transport: {card.preferred_transport}")
            logger.error(f"   Card URL: {card.url}")
            logger.error(f"   Client supported_transports: {self._config.supported_transports}")
            
            # Fallback for "no compatible transports found" error
            if "no compatible transports" in error_msg:
                logger.warning(f"⚠️ Transport resolution failed for {card.name}. Attempting HTTP+JSON fallback.")
                
                # ALWAYS attempt HTTP+JSON fallback since we're using inline cards
                logger.info(f"🔄 Fallback: Manually creating RestTransport for {card.name}")
                from a2a.client.base_client import BaseClient
                from a2a.client.transports.rest import RestTransport
                
                # Use the card's URL directly
                transport_url = card.url
                logger.info(f"   Using transport URL: {transport_url}")

                # HACK: Workaround for Cloud Run A2A URL encoding issue
                # The httpx client or an upstream library is incorrectly encoding
                # the colon in "message:send" to "message%3Asend".
                # This explicitly decodes it before it's used.
                if '.run.app' in transport_url:
                    old_url = transport_url
                    transport_url = transport_url.replace('%3A', ':')
                    if old_url != transport_url:
                        logger.warning(f"   FIX: Decoded URL from {old_url} to {transport_url}")
                
                # Manually create RestTransport
                transport = RestTransport(
                    httpx_client=self._config.httpx_client,
                    card=card,
                    url=transport_url,
                    interceptors=interceptors or []
                )
                
                all_consumers = self._consumers.copy()
                if consumers:
                    all_consumers.extend(consumers)
                    
                client = BaseClient(
                    card=card,
                    config=self._config,
                    transport=transport,
                    consumers=all_consumers,
                    middleware=interceptors or []
                )
                
                logger.info(f"✅ Fallback successful for {card.name}")
                return client
            
            # Re-raise if not a transport error
            logger.error(f"   Not a transport error, re-raising")
            raise

    def __getstate__(self):
        """
        Custom pickling to exclude the httpx client.
        
        Returns:
            State dictionary with only pickleable attributes
        """
        state = self.__dict__.copy()
        # Ensure no httpx client sneaks into the pickle
        if '_config' in state and hasattr(state['_config'], 'httpx_client'):
            state['_config'].httpx_client = None
        logger.debug("LazyAuthClientFactory __getstate__ called (client excluded)")
        return state

    def __setstate__(self, state):
        """
        Custom unpickling to restore state.
        
        Args:
            state: Pickled state dictionary
        """
        self.__dict__.update(state)
        # Ensure client is None after unpickling
        if hasattr(self._config, 'httpx_client'):
            self._config.httpx_client = None
        logger.debug("LazyAuthClientFactory __setstate__ called (client will be created on first use)")
