import os
import logging
import json
import httpx
from google import auth
from google.auth.transport.httpx import AsyncAuthorizedHttp

# Corrected ADK imports
from google import adk
from google.adk.a2a import to_a2a
from google.adk.core import Agent, Capability, CapabilityContext, CapabilityError

# --- Configuration ---
logging.basicConfig(level=logging.INFO)

# 1. Define backend service URLs from environment variables
SERVICE_URLS = {
    "social": os.environ.get("SOCIAL_AGENT_URL"),
    "planner": os.environ.get("PLANNER_AGENT_URL"),
    "mcp": os.environ.get("MCP_AGENT_URL"),
}

# 2. Check if all required environment variables are set
missing_envs = [k for k, v in SERVICE_URLS.items() if not v]
if missing_envs:
    raise ValueError(f"Missing environment variables for services: {', '.join(missing_envs)}")

# 3. Map public capability names to backend services and actions
CAPABILITY_MAP = {
    # Public Name: (Service Key, Backend Action)
    "social_share": ("social", "share"),
    "social_get_profile": ("social", "get_profile"),
    "planner_get_plans": ("planner", "get_plans"),
    "mcp_create_post": ("mcp", "create_post"),
    "mcp_create_event": ("mcp", "create_event"),
}

# --- Shared HTTP Client & Capability ---

class GenericVertexForwarder(Capability):
    """
    A reusable capability that forwards requests to a specific backend
    Vertex AI Agent using a shared, authenticated httpx client.
    """
    def __init__(self, client: httpx.AsyncClient, backend_url: str, action: str):
        self.client = client
        self.backend_url = backend_url
        self.action = action
        super().__init__()

    async def invoke(self, data: dict, context: CapabilityContext) -> dict:
        """Constructs the Vertex AI payload and forwards the request."""
        vertex_payload = {"input": {"action": self.action, "data": data}}
        logging.info(f"Gateway forwarding action '{self.action}' to {self.backend_url}")

        try:
            # The AsyncAuthorizedHttp client automatically handles the 'Authorization' header.
            response = await self.client.post(
                self.backend_url, json=vertex_payload, timeout=60
            )
            response.raise_for_status()
            # Safely get the 'output' key.
            return response.json().get("output", {})
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text
            try:
                error_detail = e.response.json()
            except json.JSONDecodeError:
                pass
            logging.error(
                f"Backend error for action '{self.action}'. Status: {e.response.status_code}. Details: {error_detail}"
            )
            raise CapabilityError(
                message=f"Backend agent failed for action '{self.action}' with status {e.response.status_code}.",
                details={"backend_response": error_detail}
            )
        except Exception as e:
            logging.exception(f"Unexpected gateway error for action '{self.action}'.")
            raise CapabilityError(f"Gateway error processing action '{self.action}': {str(e)}")

# --- Agent Definition ---

def create_authorized_client() -> httpx.AsyncClient:
    """Creates an httpx client that automatically handles Google Cloud authentication."""
    credentials, project = auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    return AsyncAuthorizedHttp(credentials)

def build_agent() -> tuple[Agent, httpx.AsyncClient]:
    """Builds the unified proxy agent and its capabilities, returns agent and client."""
    client = create_authorized_client()
    capabilities = {}
    for name, (service, action) in CAPABILITY_MAP.items():
        backend_url = SERVICE_URLS.get(service)
        if not backend_url:
            logging.warning(f"Skipping capability '{name}' because service URL for '{service}' is not set.")
            continue
        capabilities[name] = GenericVertexForwarder(client, backend_url, action)
        logging.info(f"Registered capability '{name}' -> {backend_url} (action: {action})")

    agent = Agent(
        name="Unified Agent Gateway",
        description="A centralized proxy for requests to backend agents on Vertex AI.",
        capabilities=capabilities,
    )
    return agent, client

# Create the agent and expose it as an A2A web application
unified_proxy_agent, shared_client = build_agent()
app = to_a2a(unified_proxy_agent)

# Add a shutdown event to gracefully close the shared HTTP client
@app.on_event("shutdown")
async def shutdown_event():
    logging.info("Shutting down gateway, closing shared HTTP client...")
    await shared_client.aclose()
    logging.info("Shared HTTP client closed.")
