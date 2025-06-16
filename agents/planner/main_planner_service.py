# agents/planner/main_planner_service.py
import logging
import os
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

# Attempt to load PlannerAgent. Ensure correct relative import path.
# Assuming main_planner_service.py is in agents/planner/
try:
    from agents.planner.planner_agent import PlannerAgent
except ImportError:
    # Fallback for different execution contexts (e.g. if path is already in agents/)
    from planner.planner_agent import PlannerAgent


# --- Logging Setup ---
logging.basicConfig(level=logging.INFO) # Basic logging config
logger = logging.getLogger(__name__)

# --- Configuration ---
AGENT_NAME = "planner"
AGENT_DESCRIPTION = "Planner Agent for generating event plans."

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
# Instantiate the agent. This should be done once if the agent is stateless
# or designed to be a singleton. If it has state per request, instantiation might
# need to be inside the endpoint. PlannerAgent seems suitable for single instantiation.
try:
    planner_agent_instance = PlannerAgent()
    logger.info(f"{AGENT_NAME.capitalize()}Agent initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize {AGENT_NAME.capitalize()}Agent: {e}", exc_info=True)
    planner_agent_instance = None # Handle cases where initialization might fail

# --- API Endpoints ---
@app.post(f"/agents/{AGENT_NAME}/invoke", response_model=AgentInvokeResponse)
async def invoke_agent_endpoint(request_data: AgentInvokeRequest) -> AgentInvokeResponse:
    logger.info(f"/{AGENT_NAME}/invoke endpoint called with query: {request_data.query[:100]}...")
    if not planner_agent_instance:
        logger.error("PlannerAgent not initialized. Cannot process request.")
        raise HTTPException(status_code=500, detail="PlannerAgent not initialized. Service is unavailable.")

    try:
        # Call the agent's async_query method
        # Pass session_id if it's part of kwargs the agent expects
        agent_response_dict = await planner_agent_instance.async_query(
            query=request_data.query,
            # Example of passing session_id if the underlying agent uses it in kwargs:
            # session_id=request_data.session_id
        )

        output_data = agent_response_dict.get("output")
        error_message = agent_response_dict.get("error")

        if error_message:
            logger.warning(f"{AGENT_NAME.capitalize()}Agent returned an error: {error_message}")
            # Return 200 OK with error in body, as per defined interface,
            # unless a specific HTTP error is more appropriate.
            return AgentInvokeResponse(output=output_data, error=str(error_message))

        logger.info(f"{AGENT_NAME.capitalize()}Agent call successful.")
        return AgentInvokeResponse(output=output_data, error=None)

    except Exception as e:
        logger.error(f"Unexpected error in {AGENT_NAME} agent endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error in {AGENT_NAME} agent: {str(e)}")

# --- Main block for running the service (e.g., with Uvicorn) ---
if __name__ == "__main__":
    import uvicorn
    # Default port, can be overridden by environment variable for flexibility
    service_port = int(os.environ.get("PLANNER_AGENT_PORT", 8001))
    logger.info(f"Starting {AGENT_NAME.capitalize()} Agent Service on port {service_port}...")
    uvicorn.run(app, host="0.0.0.0", port=service_port)
