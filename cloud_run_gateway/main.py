import os
import logging
import json
from fastapi import FastAPI, HTTPException
from authlib.integrations.httpx_client import AsyncOAuth2Client
import google.auth
from google.auth.exceptions import RefreshError

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
    "social_share": ("social", "share"),
    "social_get_profile": ("social", "get_profile"),
    "planner_get_plans": ("planner", "get_plans"),
    "mcp_create_post": ("mcp", "create_post"),
    "mcp_create_event": ("mcp", "create_event"),
}

# --- Reusable Forwarding Logic with Authlib ---

# A global dictionary to hold initialized clients for each service
# This acts as a simple connection pool.
_clients = {}

async def get_authed_client(service_name: str) -> AsyncOAuth2Client:
    """
    Initializes and returns an authenticated AsyncOAuth2Client for a given service.
    This function uses Application Default Credentials (ADC).
    """
    if service_name in _clients:
        return _clients[service_name]

    logging.info(f"Initializing new authenticated client for '{service_name}' service...")
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    # Authlib requires a token dictionary. We construct one.
    # The google-auth library will manage the refresh token internally for ADC.
    token = {
        "access_token": credentials.token,
        "token_type": "Bearer",
    }

    client = AsyncOAuth2Client(
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        token_endpoint=credentials.token_uri,
        token=token,
    )

    _clients[service_name] = client
    return client

async def forward_request(service_name: str, action: str, data: dict):
    """
    Forwards a request to the specified backend agent using an authenticated client.
    """
    backend_url = SERVICE_URLS.get(service_name)
    if not backend_url:
        raise HTTPException(status_code=500, detail=f"Service URL for '{service_name}' not configured.")

    client = await get_authed_client(service_name)
    vertex_payload = {"input": {"action": action, "data": data}}
    logging.info(f"Gateway forwarding action '{action}' to {backend_url}")

    try:
        response = await client.post(backend_url, json=vertex_payload, timeout=60)
        response.raise_for_status()
        return response.json().get("output", {})
    except RefreshError as e:
        logging.error(f"Authlib token refresh failed for '{service_name}': {e}")
        # Clear the faulty client so a new one is created on next request
        if service_name in _clients:
            del _clients[service_name]
        raise HTTPException(status_code=503, detail="Authentication token could not be refreshed.")
    except Exception as e:
        logging.exception(f"Unexpected error forwarding to '{service_name}'.")
        raise HTTPException(status_code=500, detail=f"Gateway error: {str(e)}")


# --- FastAPI Application ---
app = FastAPI(
    title="Unified Agent Gateway",
    description="A centralized proxy for requests to backend agents on Vertex AI.",
)

# Dynamically create an endpoint for each capability in the map
for capability_name, (service, action) in CAPABILITY_MAP.items():
    # This function uses a closure to capture the correct service and action
    def create_endpoint(service_name=service, action_name=action):
        async def endpoint_func(data: dict):
            return await forward_request(service_name, action_name, data)
        return endpoint_func

    app.post(f"/{capability_name}", name=capability_name)(create_endpoint())

@app.on_event("shutdown")
async def shutdown_event():
    logging.info("Shutting down gateway, closing all shared HTTP clients...")
    for client in _clients.values():
        await client.aclose()
    logging.info("All shared HTTP clients closed.")

@app.get("/health")
def health_check():
    return {"status": "ok"}
