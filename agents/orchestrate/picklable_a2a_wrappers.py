"""
Picklable wrappers for RemoteA2aAgent deployment to Agent Engine.

Based on Google Cloud Japan's proven pattern for lazy initialization:
https://github.com/google-cloud-japan/sa-ml-workshop/blob/main/blog/Agentic-workflow-AgentEngine-A2A.ipynb

The key insight is to defer httpx.AsyncClient creation until runtime (not in __init__),
which makes these classes picklable and deployable to Vertex AI Agent Engine.
"""
import httpx
from google.auth import default
from google.auth.transport.requests import Request
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from a2a.client import ClientFactory, ClientConfig
from a2a.types import TransportProtocol


class GoogleAuthRefresh(httpx.Auth):
    """
    Custom auth handler that automatically refreshes Google Cloud credentials.
    
    This ensures that authentication tokens are always valid when making
    requests to Agent Engine A2A endpoints.
    """
    
    def __init__(self, scopes):
        """Initialize with Google Cloud credentials."""
        self.credentials, _ = default(scopes=scopes)
        self.transport_request = Request()
        self.credentials.refresh(self.transport_request)
    
    def auth_flow(self, request):
        """
        Refresh token if needed and add authorization header.
        
        This is called automatically by httpx for each request.
        """
        if not self.credentials.valid:
            self.credentials.refresh(self.transport_request)
        request.headers['Authorization'] = f'Bearer {self.credentials.token}'
        yield request


class PicklableClientFactory(ClientFactory):
    """
    Lazy-initialize httpx client at runtime to make factory picklable.
    
    The httpx.AsyncClient is NOT created in __init__, which would cause
    pickling errors. Instead, it's created when needed in the create() method.
    """
    
    def create(self, card, consumers=None, interceptors=None):
        """
        Create A2A client lazily when needed, not during initialization.
        
        This deferred creation allows the factory to be pickled and
        deployed to Agent Engine without errors.
        """
        if not self._config.httpx_client:
            # Create client HERE (at runtime), not in __init__
            self._config.httpx_client = httpx.AsyncClient(
                timeout=60,
                headers={'Content-Type': 'application/json'},
                auth=GoogleAuthRefresh(scopes=['https://www.googleapis.com/auth/cloud-platform'])
            )
            self._register_defaults(self._config.supported_transports)
        return super().create(card, consumers, interceptors)


class PicklableRemoteA2aAgent(RemoteA2aAgent):
    """
    Lazy-initialize httpx client at runtime to make agent picklable.
    
    The httpx.AsyncClient is NOT created in __init__, which would cause
    pickling errors. Instead, it's created when needed via _ensure_httpx_client().
    """
    
    async def _ensure_httpx_client(self) -> httpx.AsyncClient:
        """
        Create httpx client lazily when needed, not during initialization.
        
        This deferred creation allows the agent to be pickled and
        deployed to Agent Engine without errors.
        """
        if not self._httpx_client:
            # Create client HERE (at runtime), not in __init__
            self._httpx_client = httpx.AsyncClient(
                timeout=60,
                headers={'Content-Type': 'application/json'},
                auth=GoogleAuthRefresh(scopes=['https://www.googleapis.com/auth/cloud-platform'])
            )
        return self._httpx_client
