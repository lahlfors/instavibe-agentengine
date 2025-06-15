import os
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn

# It's good practice to load .env before other application imports
# if they rely on environment variables at import time.
# Adjust path if main.py is moved relative to .env
# Assuming main.py is in 'agents/', .env is in the parent directory ('../.env')
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    print("Loaded .env file from:", dotenv_path)
else:
    print(f".env file not found at: {dotenv_path}, ensure it exists at the repository root.")


from app.graph_builder import build_graph # Assuming graph_builder is in agents/app/
from app.common.graph_state import OrchestratorState # Assuming graph_state is in agents/app/common/

# Initialize FastAPI app
app = FastAPI(
    title="LangGraph Orchestrator Service",
    description="Service to run the LangGraph-based refactoring agent orchestrator.",
    version="1.0.0"
)

# Build the LangGraph application when the FastAPI app starts
# This makes it available globally within the app context
langgraph_app = None
try:
    print("Attempting to build LangGraph application...")
    langgraph_app = build_graph()
    if langgraph_app:
        print("LangGraph application built successfully.")
    else:
        print("LangGraph application build_graph() returned None.")
except Exception as e:
    import traceback
    print(f"Error building LangGraph application during FastAPI startup: {e}\n{traceback.format_exc()}")
    # langgraph_app remains None, endpoint will raise HTTPException

class UserRequestInput(BaseModel):
    user_request: str
    session_id: str | None = None # Optional session_id from client

@app.post("/invoke_graph", response_model=OrchestratorState) # Using OrchestratorState as response_model
async def invoke_graph_endpoint(payload: UserRequestInput = Body(...)):
    if not langgraph_app:
        raise HTTPException(status_code=500, detail="Graph application not initialized or build failed.")

    print(f"Received request for session '{payload.session_id}': {payload.user_request}")

    # Prepare initial state for the graph
    # Ensure all fields defined in OrchestratorState are present.
    initial_state = {
        "user_request": payload.user_request,
        "session_id": payload.session_id,
        "current_task_description": payload.user_request, # Initial task is the user request itself
        "intermediate_output": None,
        "final_output": None,
        "current_agent_name": "entry_point", # Start with entry_point
        "error_message": None,
        "route": None,
    }

    # Validate that initial_state conforms to OrchestratorState structure.
    # If OrchestratorState is a Pydantic model, this could be done by:
    # validated_initial_state = OrchestratorState(**initial_state).dict()
    # However, LangGraph nodes currently expect dicts. We pass the dict directly.

    try:
        # Configuration for the graph invocation
        config = {"recursion_limit": 25} # Default recursion limit
        if payload.session_id:
            # Ensure thread_id is a string if used; session_id is already string or None
            config["configurable"] = {"thread_id": payload.session_id}
            print(f"Using session_id '{payload.session_id}' for configurable thread_id.")
        else:
            # For requests without a session_id, a default or unique thread_id might be needed
            # if persistence is enabled by default. For now, no thread_id if no session_id.
            print("No session_id provided, running without specific thread_id for persistence.")

        print(f"Invoking graph with initial state: {initial_state} and config: {config}")
        # Using await for asynchronous invocation with ainvoke
        final_state = await langgraph_app.ainvoke(initial_state, config=config)

        print(f"Graph invocation completed. Final state: {final_state}")
        # OrchestratorState is a Pydantic model, so it should be directly returnable
        # if FastAPI handles Pydantic model serialization correctly.
        return final_state # FastAPI will serialize this Pydantic model (if OrchestratorState is one) or dict
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error invoking graph: {e}\n{error_trace}")
        # Return a valid OrchestratorState-like structure even in case of error,
        # populated with the error message.
        error_response_state = {
            **initial_state, # Start with the initial state
            "error_message": f"Error invoking graph: {str(e)}",
            "final_output": json.dumps({"error": f"Error invoking graph: {str(e)}", "trace": error_trace}) if 'json' in globals() else f"Error: {str(e)}", # Ensure json is imported or handle
            "current_agent_name": "error_handler_invoke", # Indicate where error was caught
        }
        # This will not match response_model=OrchestratorState if it's not a valid state.
        # For now, raise HTTPException, but ideally, map to OrchestratorState.
        raise HTTPException(status_code=500, detail=f"Error invoking graph: {str(e)}. Trace: {error_trace}")


@app.get("/")
async def root():
    return {"message": "LangGraph Orchestrator Service is running. Use /invoke_graph to interact."}

if __name__ == "__main__":
    # Get port from environment variable or default to 8080
    default_port = 8080
    try:
        port = int(os.environ.get("PORT", default_port))
        if not (1024 <= port <= 65535): # Basic port validation
            print(f"Warning: PORT environment variable '{os.environ.get('PORT')}' is invalid. Using default {default_port}.")
            port = default_port
    except ValueError:
        print(f"Warning: PORT environment variable '{os.environ.get('PORT')}' is not a valid integer. Using default {default_port}.")
        port = default_port

    print(f"Starting Uvicorn server on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
