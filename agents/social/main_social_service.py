# agents/social/main_social_service.py
import logging
import os
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

# Attempt to load SocialAgent. Ensure correct relative import path.
# Assuming main_social_service.py is in agents/social/
try:
    from agents.social.social_agent import SocialAgent
except ImportError:
    # Fallback for different execution contexts
    from social.social_agent import SocialAgent


# --- Logging Setup ---
logging.basicConfig(level=logging.INFO) # Basic logging config
logger = logging.getLogger(__name__)

# --- Configuration ---
AGENT_NAME = "social"
AGENT_DESCRIPTION = "Social Agent for profile analysis and summarization."

# --- Request and Response Models (Pydantic) ---
class AgentInvokeRequest(BaseModel):
    query: str
    session_id: Optional[str] = None

class AgentInvokeResponse(BaseModel):
    output: Optional[Any] = None
    error: Optional[str] = None

# --- FastAPI Application ---
app = FastAPI(
    title=f"{AGENT_NAME.capitalize()} Agent Service",
    description=AGENT_DESCRIPTION,
)

# --- Agent Instance ---
try:
    social_agent_instance = SocialAgent()
    logger.info(f"{AGENT_NAME.capitalize()}Agent initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize {AGENT_NAME.capitalize()}Agent: {e}", exc_info=True)
    social_agent_instance = None

# --- API Endpoints ---
@app.post(f"/agents/{AGENT_NAME}/invoke", response_model=AgentInvokeResponse)
async def invoke_agent_endpoint(request_data: AgentInvokeRequest) -> AgentInvokeResponse:
    logger.info(f"/{AGENT_NAME}/invoke endpoint called with query: {request_data.query[:100]}...")
    if not social_agent_instance:
        logger.error("SocialAgent not initialized. Cannot process request.")
        raise HTTPException(status_code=500, detail="SocialAgent not initialized. Service is unavailable.")

    try:
        agent_response_dict = await social_agent_instance.async_query(
            query=request_data.query,
        )

        output_data = agent_response_dict.get("output")
        error_message = agent_response_dict.get("error")

        if error_message:
            logger.warning(f"{AGENT_NAME.capitalize()}Agent returned an error: {error_message}")
            return AgentInvokeResponse(output=output_data, error=str(error_message))

        logger.info(f"{AGENT_NAME.capitalize()}Agent call successful.")
        return AgentInvokeResponse(output=output_data, error=None)

    except Exception as e:
        logger.error(f"Unexpected error in {AGENT_NAME} agent endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error in {AGENT_NAME} agent: {str(e)}")

# --- Main block for running the service ---
if __name__ == "__main__":
    import uvicorn
    service_port = int(os.environ.get("SOCIAL_AGENT_PORT", 8002)) # Different default port
    logger.info(f"Starting {AGENT_NAME.capitalize()} Agent Service on port {service_port}...")
    uvicorn.run(app, host="0.0.0.0", port=service_port)
