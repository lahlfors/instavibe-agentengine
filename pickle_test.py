import sys
import os
import traceback
import pprint
import cloudpickle
import asyncio

# --- Set up the dummy class and monkey-patch ---

class DummyAgent:
    def __init__(self, name, mcp_server_address, api_key_secret=None, description="", instruction="", global_instruction="", model="", **kwargs):
        self.name = name
        self.mcp_server_address = mcp_server_address
        self.api_key_secret = api_key_secret
        self.description = description
        self.instruction = instruction
        self.global_instruction = global_instruction
        self.model = model

# Monkey-patch the real Agent class before importing the agent
import google.adk.agents
google.adk.agents.Agent = DummyAgent

from agents.platform_mcp_client.agent import PlatformMCPClientAgent

async def main():
    print(f"Python version: {sys.version}")

    try:
        print("Testing agent cloudpickling with Dummy Base Class...")
        agent_instance = PlatformMCPClientAgent(
            name="test_agent",
            mcp_server_address="http://dummy.url"
        )

        try:
            await agent_instance.set_up()
        except Exception as e:
            print(f"Agent set_up failed as expected: {e}")

        print("Agent set_up complete (or failed as expected).")

        # Try to dump and load
        pickled_agent = cloudpickle.dumps(agent_instance)
        print("Cloudpickle dump successful.")
        unpickled_agent = cloudpickle.loads(pickled_agent)
        print("Cloudpickle load successful.")
        print("✅ SUCCESS: Agent IS cloudpickleable with Dummy Base Class.")

    except Exception as e:
        print(f"❌ FAILURE: Cloudpickling failed with Dummy Base Class: {type(e).__name__}: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
