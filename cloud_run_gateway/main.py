import os
from google import adk
from google.adk.a2a import to_a2a
import google.auth
import google.auth.transport.requests
import httpx
import logging
import json

logging.basicConfig(level=logging.INFO)

# Fetch backend agent URLs from environment variables
SOCIAL_AGENT_URL = os.environ.get("SOCIAL_AGENT_URL")
PLANNER_AGENT_URL = os.environ.get("PLANNER_AGENT_URL")
MCP_AGENT_URL = os.environ.get("MCP_AGENT_URL")

# Basic check
if not all([SOCIAL_AGENT_URL, PLANNER_AGENT_URL, MCP_AGENT_URL]):
    raise ValueError("Missing one or more backend agent URL env variables (SOCIAL_AGENT_URL, PLANNER_AGENT_URL, MCP_AGENT_URL)")

class GenericVertexForwarder(adk.Capability):
    """
    A capability that forwards requests to a specific backend Vertex AI Agent and action.
    """
    def __init__(self, backend_url: str, action: str):
        if not backend_url:
            raise ValueError(f"Backend URL not provided for action {action}")
        self.backend_url = backend_url
        self.action = action
        super().__init__()

    async def invoke(self, data: dict, context: adk.CapabilityContext) -> dict:
        vertex_payload = {"input": {"action": self.action, "data": data}}
        logging.info(f"Unified Gateway: action '{self.action}' to {self.backend_url}")

        try:
            credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
            auth_req = google.auth.transport.requests.Request()
            if not credentials.valid or credentials.expired:
                credentials.refresh(auth_req)

            headers = {'Authorization': f'Bearer {credentials.token}', 'Content-Type': 'application/json'}
            # TODO: Add trace context propagation headers

            async with httpx.AsyncClient() as client:
                response = await client.post(self.backend_url, headers=headers, json=vertex_payload, timeout=60)
                response.raise_for_status()
                return response.json().get("output", {})
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text
            try: # Attempt to parse JSON error from backend
                error_detail = e.response.json()
            except json.JSONDecodeError:
                pass
            logging.error(f"Backend agent error for action '{self.action}': {e.response.status_code} - {error_detail}")
            raise adk.CapabilityError(f"Backend agent error for action '{self.action}': {e.response.status_code}")
        except Exception as e:
            logging.exception(f"Error in Unified Gateway for action {self.action}: {e}")
            raise adk.CapabilityError(f"Gateway error for {self.action}: {str(e)}")

# Define the root agent for the unified proxy
unified_proxy_agent = adk.Agent(
    name="Unified Agent Gateway",
    description="Proxies requests to various backend agents on Vertex AI.",
    capabilities={
        # Social Agent Capabilities
        "social_share": GenericVertexForwarder(SOCIAL_AGENT_URL, "share"),
        "social_get_profile": GenericVertexForwarder(SOCIAL_AGENT_URL, "get_profile"),

        # Planner Agent Capabilities
        "planner_get_plans": GenericVertexForwarder(PLANNER_AGENT_URL, "get_plans"),

        # MCP Client Capabilities
        "mcp_create_post": GenericVertexForwarder(MCP_AGENT_URL, "create_post"),
        "mcp_create_event": GenericVertexForwarder(MCP_AGENT_URL, "create_event"),
    }
)

# Use to_a2a() to generate the web server application
app = to_a2a(unified_proxy_agent)
