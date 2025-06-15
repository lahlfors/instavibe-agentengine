# agents/app/common/client.py
from .types import AgentCard # Relative import
class A2ACardResolver:
    def __init__(self, address: str):
        self.address = address
        print(f"DEBUG: A2ACardResolver initialized with {address}") # Debug print
    def get_agent_card(self) -> AgentCard | None:
        print("DEBUG: get_agent_card called for {self.address}") # Debug print
        # In a real scenario, this would fetch the card via HTTP
        return AgentCard(name="DummyCardFromResolver", address=self.address, description="A dummy agent card from resolver") # Placeholder
print("DEBUG: common.client loaded") # Debug print
