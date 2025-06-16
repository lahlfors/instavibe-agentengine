# agents/app/common/a2a_client.py
import httpx
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class A2AClient:
    def __init__(self):
        self.agent_base_urls = {
            "planner": os.environ.get("PLANNER_AGENT_SERVICE_URL"),
            "social": os.environ.get("SOCIAL_AGENT_SERVICE_URL"),
            "platform": os.environ.get("PLATFORM_AGENT_SERVICE_URL")
            # Orchestrator won't call itself via A2AClient in this model,
            # but if it were to call other orchestrators, it would be added here.
        }
        # Log missing URLs during initialization as a warning
        for agent_name, url in self.agent_base_urls.items():
            if not url:
                logger.warning(f"A2AClient: Service URL for agent '{agent_name}' is not configured via environment variable ({agent_name.upper()}_AGENT_SERVICE_URL).")

    async def invoke_agent(self, agent_name: str, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        # Agent Engine hosted agents will have their own specific URL format.
        # This client needs to be robust to different URL formats provided by env vars.
        # The URL fetched from env var IS the full invokable URL for the Agent Engine endpoint.

        target_url = self.agent_base_urls.get(agent_name.lower())
        if not target_url:
            logger.error(f"A2AClient: Service URL for agent '{agent_name}' is not configured.")
            return {"output": None, "error": f"A2AClient: Service URL for agent '{agent_name}' not configured."}

        # The request payload structure here assumes a generic JSON body.
        # If Agent Engine's generic HTTP wrapper for deployed agent objects
        # expects a specific format (e.g., {"instance": {"query": ...}} or {"inputs": ...}),
        # this payload needs to be adapted. This is a KEY ADAPTATION POINT.
        # For now, using the simple {"query": ..., "session_id": ...} structure.
        # This will need to be verified against Agent Engine's "Use an agent" documentation.

        # Construct the payload for Agent Engine's :query method, which expects an "input" key.
        input_params: Dict[str, Any] = {"query": query}
        if session_id:
            input_params["session_id"] = session_id

        request_payload_for_engine = {"input": input_params}

        logger.debug(f"A2AClient: Invoking agent '{agent_name}' at URL '{target_url}'. Payload: {request_payload_for_engine}")
        logger.info(f"A2AClient: Invoking agent '{agent_name}' at URL '{target_url}' with query: '{query[:100]}...'") # Keep high-level info log

        # Note on Authentication:
        # When calling Google Cloud APIs (like a deployed Agent Engine endpoint),
        # httpx.AsyncClient() will typically use Application Default Credentials (ADC)
        # if run in a GCP environment (e.g., Cloud Run, GCE, GKE).
        # For local development, ensure ADC is set up via `gcloud auth application-default login`.
        # No explicit token handling is usually needed in the client code itself if ADC is configured.
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(target_url, json=request_payload_for_engine, timeout=120.0) # Longer timeout

                if 200 <= response.status_code < 300:
                    try:
                        # Assume the Agent Engine :query endpoint directly returns the
                        # agent's output dictionary, e.g., {"output": ..., "error": ...}
                        response_json = response.json()
                        logger.debug(f"A2AClient: Successfully received response from {agent_name}. JSON: {response_json}")
                        return response_json
                    except Exception as e:
                        logger.error(f"A2AClient: Failed to decode JSON response from {agent_name} (status {response.status_code}). Response text: {response.text[:500]}", exc_info=True)
                        return {"output": None, "error": f"A2AClient: Failed to decode/parse JSON from {agent_name}. Details: {str(e)}"}
                else:
                    error_details = response.text[:500] # Limit error detail length
                    logger.error(f"A2AClient: Call to {agent_name} failed with status {response.status_code}. Details: {error_details}")
                    try:
                        error_json = response.json()
                        # Check for Vertex-style error messages
                        if "error" in error_json and isinstance(error_json["error"], dict) and "message" in error_json["error"]:
                            error_details = error_json["error"]["message"]
                        elif "error" in error_json and isinstance(error_json["error"], str): # Simpler error string
                            error_details = error_json["error"]
                        elif "detail" in error_json: # FastAPI validation errors
                            error_details = str(error_json["detail"])
                    except Exception:
                        pass
                    return {"output": None, "error": f"A2AClient: Call to {agent_name} failed (status {response.status_code}). Details: {error_details}"}

        except httpx.RequestError as e:
            logger.error(f"A2AClient: Network error during call to {agent_name} at {target_url}. Error: {str(e)}", exc_info=True)
            return {"output": None, "error": f"A2AClient: Network error calling {agent_name}: {str(e)}"}
        except Exception as e:
            logger.error(f"A2AClient: Unexpected error during call to {agent_name}. Error: {str(e)}", exc_info=True)
            return {"output": None, "error": f"A2AClient: Unexpected error calling {agent_name}: {str(e)}"}
