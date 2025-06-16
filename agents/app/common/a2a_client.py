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
        request_payload: Dict[str, Any] = {"query": query}
        if session_id:
            request_payload["session_id"] = session_id

        # Placeholder for the actual request structure Agent Engine expects.
        # This might be e.g. {"instances": [{"query": query, "session_id": session_id}]}
        # or just `request_payload` if the agent method signature matches.
        # For a deployed LangGraph/Agent, it's often a dict with a key like 'input' or 'question'.
        # Let's assume for now the agent method exposed by AgentEngine can take `query` and `session_id`
        # perhaps as part of a single JSON object in the request.
        # The official documentation for "Use an agent" for the specific type of deployed agent (LangGraph, custom class) is crucial here.
        # For a custom class with an `async_query(self, query, session_id=None)` method,
        # Agent Engine might map the JSON body directly to these parameters or expect them under a specific key.

        logger.info(f"A2AClient: Invoking agent '{agent_name}' at URL '{target_url}' with query: '{query[:100]}...'")

        try:
            async with httpx.AsyncClient() as client:
                # The exact payload structure sent to Agent Engine needs verification.
                # If Agent Engine expects `{"instances": [payload]}`, then adjust `json=actual_payload_for_agent_engine`.
                # For now, sending the payload directly.
                response = await client.post(target_url, json=request_payload, timeout=120.0) # Longer timeout for cold starts / complex agents

                if 200 <= response.status_code < 300:
                    try:
                        # Agent Engine might wrap the agent's actual output.
                        # E.g., {"predictions": [agent_actual_output]}
                        # The `agent_actual_output` should be {"output": ..., "error": ...}
                        response_json = response.json()
                        # This parsing needs to be robust based on Agent Engine's actual response structure.
                        # If it's like {"predictions": [{"output": "...", "error": "..."}]}, extract that.
                        if "predictions" in response_json and isinstance(response_json["predictions"], list) and len(response_json["predictions"]) > 0:
                            agent_internal_response = response_json["predictions"][0]
                            if isinstance(agent_internal_response, dict):
                                return agent_internal_response
                            else: # If the prediction isn't the dict we expect
                                logger.warning(f"A2AClient: Unexpected prediction format from {agent_name}: {agent_internal_response}")
                                return {"output": agent_internal_response, "error": None} # Pass it through as output
                        else:
                            # If no "predictions" key, assume the response is directly the agent's output dict
                            logger.debug(f"A2AClient: Response from {agent_name} does not have 'predictions' key, assuming direct response. JSON: {response_json}")
                            return response_json # This should be {"output": ..., "error": ...}
                    except Exception as e:
                        logger.error(f"A2AClient: Failed to decode or parse JSON response from {agent_name} (status {response.status_code}). Response text: {response.text[:500]}", exc_info=True)
                        return {"output": None, "error": f"A2AClient: Failed to decode/parse JSON from {agent_name}. Details: {str(e)}"}
                else:
                    error_details = response.text[:500]
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
