# agents/app/common/task_manager.py
class AgentTaskManager:
    def __init__(self, agent: any = None):
        self.agent = agent
        print(f"DEBUG: AgentTaskManager initialized with agent: {agent}") # Debug print
    async def handle_request(self, request_data: dict):
        print(f"DEBUG: AgentTaskManager handling request: {request_data}") # Debug print
        return {"status": "processed", "result": "placeholder_result"}
print("DEBUG: common.task_manager loaded") # Debug print
