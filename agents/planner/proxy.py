import os
import adk
from adk.a2a import to_a2a
import requests
import json
import google.auth
import google.auth.transport.requests

# Fetch the backend agent's URL from an environment variable
BACKEND_AGENT_URL = os.environ.get("BACKEND_AGENT_URL")
if not BACKEND_AGENT_URL:
    raise ValueError("BACKEND_AGENT_URL environment variable not set (e.g., https://<loc>-aiplatform.googleapis.com/v1beta1/projects/<proj>/locations/<loc>/reasoningEngines/<id>:query)")

class VertexForwarderCapability(adk.Capability):
    """Base class for capabilities that forward to Vertex AI."""
    async def invoke(self, data: dict, context: adk.CapabilityContext) -> dict:
        action = context.capability_name # Use the capability name as the action
        vertex_payload = {"input": {"action": action, "data": data}}

        try:
            credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
            auth_req = google.auth.transport.requests.Request()
            credentials.refresh(auth_req)
            headers = {'Authorization': f'Bearer {credentials.token}', 'Content-Type': 'application/json'}
            # Consider adding trace context propagation headers if needed

            response = requests.post(BACKEND_AGENT_URL, headers=headers, json=vertex_payload, timeout=60)
            response.raise_for_status()
            return response.json().get("output", {})
        except requests.exceptions.RequestException as e:
            # Log error
            raise adk.CapabilityError(f"Error calling backend agent for action '{action}': {e}")
        except Exception as e:
            raise adk.CapabilityError(f"Unexpected error in proxy for action '{action}': {e}")

# Define the root agent for the proxy
proxy_agent = adk.Agent(
    name="Planner Agent Proxy",
    description="Proxies requests to the backend Planner Agent on Vertex AI.",
    capabilities={
        "get_plans": VertexForwarderCapability(),
    }
)

# Use to_a2a() to generate the complete web server application for Cloud Run
# This will handle JSON-RPC requests and serve the agent card.
app = to_a2a(proxy_agent)
