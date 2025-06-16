# agents/orchestrate/main_orchestrator_service.py
import logging
import os
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

# Attempt to load OrchestrateServiceAgent. Ensure correct relative import path.
try:
    from agents.orchestrate.orchestrate_service_agent import OrchestrateServiceAgent
except ImportError:
    # Fallback for different execution contexts
    from orchestrate.orchestrate_service_agent import OrchestrateServiceAgent

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
AGENT_NAME = "orchestrator"
AGENT_DESCRIPTION = "Orchestrator Agent Service - main entry point for agent system."

# --- Request and Response Models (Pydantic) ---
class AgentInvokeRequest(BaseModel):
    query: str
    session_id: Optional[str] = None # session_id is used by OrchestrateServiceAgent

class AgentInvokeResponse(BaseModel):
    output: Optional[Any] = None
    error: Optional[str] = None

# --- FastAPI Application ---
app = FastAPI(
    title=f"{AGENT_NAME.capitalize()} Agent Service",
    description=AGENT_DESCRIPTION,
)

# --- Agent Instance ---
# OrchestrateServiceAgent's __init__ no longer takes remote_agent_addresses_str.
# The A2AClient it uses internally will get URLs from environment variables.
try:
    orchestrator_agent_instance = OrchestrateServiceAgent()
    logger.info(f"{AGENT_NAME.capitalize()}ServiceAgent initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize {AGENT_NAME.capitalize()}ServiceAgent: {e}", exc_info=True)
    orchestrator_agent_instance = None

# --- API Endpoints ---
@app.post(f"/agents/{AGENT_NAME}/invoke", response_model=AgentInvokeResponse)
async def invoke_agent_endpoint(request_data: AgentInvokeRequest) -> AgentInvokeResponse:
    logger.info(f"/{AGENT_NAME}/invoke endpoint called with query: {request_data.query[:100]}...")
    if not orchestrator_agent_instance:
        logger.error("OrchestrateServiceAgent not initialized. Cannot process request.")
        raise HTTPException(status_code=500, detail="OrchestrateServiceAgent not initialized. Service is unavailable.")

    try:
        # Call the agent's async_query method
        agent_response_dict = await orchestrator_agent_instance.async_query(
            query=request_data.query,
            session_id=request_data.session_id # Pass session_id
        )

        output_data = agent_response_dict.get("output")
        error_message = agent_response_dict.get("error")

        if error_message:
            logger.warning(f"{AGENT_NAME.capitalize()}ServiceAgent returned an error: {error_message}")
            return AgentInvokeResponse(output=output_data, error=str(error_message))

        logger.info(f"{AGENT_NAME.capitalize()}ServiceAgent call successful.")
        return AgentInvokeResponse(output=output_data, error=None)

    except Exception as e:
        logger.error(f"Unexpected error in {AGENT_NAME} agent endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error in {AGENT_NAME} agent: {str(e)}")

# --- Main block for running the service ---
if __name__ == "__main__":
    import uvicorn
    # For local testing, ensure PLANNER_AGENT_SERVICE_URL, SOCIAL_AGENT_SERVICE_URL,
    # and PLATFORM_AGENT_SERVICE_URL are set in the environment if testing A2A calls.
    logger.info("For local testing of the Orchestrator service with A2A calls, ensure downstream agent service URLs (PLANNER_AGENT_SERVICE_URL, etc.) are set in your environment.")
    service_port = int(os.environ.get("ORCHESTRATOR_AGENT_PORT", 8000)) # e.g., 8000 for orchestrator
    logger.info(f"Starting {AGENT_NAME.capitalize()} Agent Service on port {service_port}...")
    uvicorn.run(app, host="0.0.0.0", port=service_port)
