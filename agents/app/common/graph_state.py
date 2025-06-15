from typing import Optional, Any
from pydantic import BaseModel

class OrchestratorState(BaseModel):
    """
    Represents the shared state of the LangGraph-based orchestrator.
    This Pydantic model is passed between nodes, and each node can update
    specific fields.
    """
    user_request: str #: The initial request from the user.
    current_task_description: Optional[str] = None #: The specific task description for the currently targeted agent/node.
    intermediate_output: Optional[Any] = None #: Output from the last executed agent/node, used for routing or as input to the next.
    final_output: Optional[str] = None #: The final, user-facing output, typically a JSON string, set by the `output_node`.
    session_id: Optional[str] = None #: A unique identifier for the session, generated at the entry point.
    current_agent_name: Optional[str] = None #: Name of the agent/node that last modified the state.
    error_message: Optional[str] = None #: Any error message set by a node if processing fails.
    route: Optional[str] = None  #: Stores the name of the next node to execute, decided by the planner_router_node.
