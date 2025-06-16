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
        }
        # Log missing URLs during initialization as a warning
        for agent_name, url in self.agent_base_urls.items():
            if not url:
                logger.warning(f"A2AClient: Service URL for agent '{agent_name}' is not configured via environment variable ({agent_name.upper()}_AGENT_SERVICE_URL).")

    async def invoke_agent(self, agent_name: str, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        base_url = self.agent_base_urls.get(agent_name.lower()) # Ensure agent_name is consistently cased
        if not base_url:
            logger.error(f"A2AClient: Service URL for agent '{agent_name}' is not configured.")
            return {"output": None, "error": f"A2AClient: Service URL for agent '{agent_name}' not configured."}

        # Construct endpoint based on the Step 2 definition
        endpoint = f"{base_url}/agents/{agent_name.lower()}/invoke"

        request_payload: Dict[str, Any] = {"query": query}
        if session_id:
            request_payload["session_id"] = session_id

        logger.debug(f"A2AClient: Invoking agent '{agent_name}' at endpoint '{endpoint}' with query: '{query[:100]}...'")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(endpoint, json=request_payload, timeout=60.0) # Increased timeout

                # Check if the response is successful, then try to parse JSON
                if 200 <= response.status_code < 300:
                    try:
                        return response.json()
                    except Exception as e: # Catches JSONDecodeError and others if response not valid JSON
                        logger.error(f"A2AClient: Failed to decode JSON response from {agent_name} (status {response.status_code}). Response text: {response.text[:500]}")
                        return {"output": None, "error": f"A2AClient: Failed to decode JSON response from {agent_name}. Details: {str(e)}"}
                else:
                    # Handle HTTP errors (4xx, 5xx)
                    error_details = response.text[:500] # Limit error detail length
                    logger.error(f"A2AClient: Call to {agent_name} failed with status {response.status_code}. Details: {error_details}")
                    # Attempt to parse error from JSON response if possible, conforming to our expected error structure
                    try:
                        error_json = response.json()
                        if "error" in error_json and error_json["error"]:
                            error_details = error_json["error"]
                        elif "detail" in error_json and error_json["detail"]: # FastAPI validation errors often use "detail"
                             error_details = str(error_json["detail"])
                    except Exception:
                        pass # Stick with text if JSON parsing fails or no structured error
                    return {"output": None, "error": f"A2AClient: Call to {agent_name} failed with status {response.status_code}. Details: {error_details}"}

        except httpx.RequestError as e:
            logger.error(f"A2AClient: Network error during call to {agent_name} at {endpoint}. Error: {str(e)}")
            return {"output": None, "error": f"A2AClient: Network error calling {agent_name}: {str(e)}"}
        except Exception as e:
            logger.error(f"A2AClient: Unexpected error during call to {agent_name}. Error: {str(e)}", exc_info=True)
            return {"output": None, "error": f"A2AClient: Unexpected error calling {agent_name}: {str(e)}"}
