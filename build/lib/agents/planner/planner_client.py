import adk
import asyncio
import os
from dotenv import load_dotenv
from agents.app.utils.communication import call_agent_capability

# Load environment variables from the root .env file.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# In a real scenario, the proxy's URL would be discovered or configured.
# For this example, we'll register it manually.
# The URL should be the one for the Cloud Run proxy service.
PROXY_URL = os.environ.get("PLANNER_AGENT_URL", "http://localhost:8081")
adk.agents.register(name='planner_agent-v1', agent_card_url=f'{PROXY_URL}/.well-known/agent.json')

async def get_plans_via_proxy(data_to_share: dict):
    """
    Finds the planner agent proxy and invokes its 'get_plans' capability.
    """
    try:
        print("Invoking 'get_plans' via proxy...")
        response_data = await call_agent_capability(
            source_agent="planner_client",
            target_agent="planner_agent-v1",
            capability="get_plans",
            prompt=data_to_share
        )
        print("✓ Call via proxy successful! Response:", response_data)
        return response_data
    except Exception as e:
        print(f"✗ An error occurred: {e}")
        return None

async def main():
    """
    Main function to run the test client.
    """
    print("--- Running A2A Test Client for Planner Agent ---")
    data = {"query": "Plan Something for me in San Francisco this weekend on wine and fashion"}
    await get_plans_via_proxy(data)
    print("--- Test Client Finished ---")

if __name__ == '__main__':
  # To run this, you would first need to run the proxy service, e.g.,
  # uvicorn agents.planner.proxy:app --port 8081
  # And ensure the BACKEND_AGENT_URL environment variable is set for the proxy.
  asyncio.run(main())
