"""
Google Cloud Authentication Handler for A2A Communication

Implements automatic token refresh and trace propagation for secure
Agent-to-Agent calls using OIDC tokens.

Based on Section 4.2 of the Secure A2A reference architecture.
"""

import logging
import httpx
import google.auth
import google.auth.transport.requests
from google.oauth2 import service_account
from opentelemetry import trace
from typing import Optional

logger = logging.getLogger(__name__)


class GoogleAuthRefresh(httpx.Auth):
    """
    Custom HTTPX Authentication class that manages Google Cloud OIDC/OAuth2 tokens.
    
    This class solves the 'stale token' problem. Long-running agents may encounter
    token expiration (typically 1 hour for OIDC tokens). This handler automatically
    refreshes the credential before each request if it is near expiration.
    
    Features:
    - Auto-refresh on expiry or within 60s of expiration
    - W3C trace context propagation for distributed tracing
    - Support for both service account and user credentials
    - Thread-safe credential management
    
    Attributes:
        scopes: OAuth2 scopes required (usually cloud-platform)
        target_audience: Specific URL of the target service for OIDC tokens
        credentials: The underlying Google Auth credentials object
        project_id: Discovered GCP project ID
    
    Example:
        auth = GoogleAuthRefresh(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        client = httpx.AsyncClient(auth=auth)
        response = await client.get('https://agent-endpoint.com')
    """
    
    def __init__(
        self, 
        target_audience: Optional[str] = None, 
        scopes: Optional[list] = None
    ):
        """
        Initialize the auth handler.
        
        Args:
            target_audience: The specific URL for OIDC audience claim (for Cloud Run services)
            scopes: List of OAuth2 scopes (for GCP APIs like Vertex AI)
        """
        self.scopes = scopes or ['https://www.googleapis.com/auth/cloud-platform']
        self.target_audience = target_audience
        
        # Initialize the credentials using Application Default Credentials (ADC).
        # In Vertex AI Agent Engine, this automatically discovers the runtime's Service Account.
        try:
            # If target_audience is provided, we need ID token credentials for Cloud Run
            if target_audience:
                logger.debug(f"Initializing ID token credentials for audience: {target_audience}")
                import google.auth.transport.requests
                from google.oauth2 import service_account
                import google.auth
                
                # Get the default credentials
                credentials, project_id = google.auth.default()
                
                # Create ID token credentials
                if hasattr(credentials, 'signer'):
                    # Service account credentials - can generate ID tokens
                    from google.auth.transport.requests import Request
                    self.credentials = credentials
                    self.project_id = project_id
                    self.use_id_token = True
                    logger.debug(f"Using service account for ID token generation")
                else:
                    # User credentials or other - fall back to access token
                    logger.warning(f"Credentials do not support ID token generation, falling back to access token")
                    self.credentials, self.project_id = google.auth.default(scopes=self.scopes)
                    self.use_id_token = False
            else:
                # No audience - use access token with scopes
                self.credentials, self.project_id = google.auth.default(scopes=self.scopes)
                self.use_id_token = False
                
            logger.debug(f"Initialized Google Auth for project: {self.project_id}")
            logger.debug(f"Auth mode: {'ID Token' if self.use_id_token else 'Access Token'}")
        except Exception as e:
            logger.error(f"Failed to initialize Google Auth credentials: {e}")
            raise
        
        # Create a transport request object used for refreshing the token
        self.request = google.auth.transport.requests.Request()

    def _is_near_expiry(self, threshold_seconds: int = 60) -> bool:
        """
        Check if the token is expired or will expire soon.
        
        Args:
            threshold_seconds: Refresh if expiry is within this many seconds
            
        Returns:
            True if token needs refresh, False otherwise
        """
        if not self.credentials.expiry:
            return False
            
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        threshold = now + timedelta(seconds=threshold_seconds)
        
        return self.credentials.expiry <= threshold

    def _get_current_trace_context(self) -> Optional[str]:
        """
        Extract current W3C trace context for propagation.
        
        Returns:
            W3C traceparent header value, or None if no active span
        """
        try:
            span = trace.get_current_span()
            if not span or not span.get_span_context().is_valid:
                return None
                
            ctx = span.get_span_context()
            trace_id = format(ctx.trace_id, '032x')
            span_id = format(ctx.span_id, '016x')
            flags = '01' if ctx.trace_flags.sampled else '00'
            
            return f"00-{trace_id}-{span_id}-{flags}"
        except Exception as e:
            logger.debug(f"Could not extract trace context: {e}")
            return None

    def auth_flow(self, request: httpx.Request):
        """
        The interceptor method called by HTTPX before sending a request.
        
        This method:
        1. Checks if credentials are valid or near expiry
        2. Refreshes credentials if needed
        3. Generates ID token (for Cloud Run) or uses Access token (for GCP APIs)
        4. Injects the Authorization header
        5. Propagates trace context for observability
        
        Args:
            request: The HTTP request to authenticate
            
        Yields:
            The modified request with auth headers
        """
        try:
            # 1. Refresh credentials if they are expired or near expiry
            if not self.credentials.valid or self._is_near_expiry():
                logger.debug("Credentials invalid or near expiry. Initiating refresh...")
                self.credentials.refresh(self.request)
                logger.debug("Credential refresh complete")
            
            # 2. Retrieve the token
            if self.use_id_token and hasattr(self, 'target_audience') and self.target_audience:
                # Generate ID token for Cloud Run service-to-service auth
                logger.debug(f"Generating ID token for audience: {self.target_audience}")
                from google.oauth2 import id_token
                import google.auth.transport.requests
                
                # Get ID token
                auth_req = google.auth.transport.requests.Request()
                token = id_token.fetch_id_token(auth_req, self.target_audience)
                logger.debug("ID token generated successfully")
            else:
                # Use access token for GCP APIs (e.g., Vertex AI)
                token = self.credentials.token
                logger.debug("Using access token")
            
            if not token:
                raise ValueError("Failed to obtain valid token from credentials")
            
            # 3. Inject the Authorization header
            request.headers["Authorization"] = f"Bearer {token}"
            
            # 4. Propagate trace context for distributed tracing
            if trace_context := self._get_current_trace_context():
                request.headers["traceparent"] = trace_context
                logger.debug(f"Injected trace context: {trace_context[:20]}...")
            
            # 5. Log the request details
            logger.info(f"🚀 Sending Authenticated Request: {request.method} {request.url}")

            # 6. Yield the modified request back to the client
            yield request
            
        except google.auth.exceptions.GoogleAuthError as e:
            logger.error(f"Authentication failed during token refresh: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in auth flow: {str(e)}")
            raise
