from typing import Optional, Any
from pydantic import BaseModel

class OrchestratorState(BaseModel):
    """
    Represents the state of the orchestrator at any given point.
    """
    user_request: str
    current_task_description: Optional[str] = None
    intermediate_output: Optional[Any] = None
    final_output: Optional[str] = None
    session_id: Optional[str] = None
    current_agent_name: Optional[str] = None
    error_message: Optional[str] = None
    route: Optional[str] = None  # Stores the name of the next node to execute
