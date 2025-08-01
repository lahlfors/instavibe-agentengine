import adk
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables from the root .env file.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# In a real scenario, the proxy's URL would be discovered or configured.
# For this example, we'll register it manually.
# The URL should be the one for the Cloud Run proxy service.
SOCIAL_PROXY_URL = os.environ.get("SOCIAL_AGENT_URL", "http://localhost:8080")
adk.agents.register(name='social-agent-v1', agent_card_url=f'{SOCIAL_PROXY_URL}/.well-known/agent.json')

# Register the platform mcp client proxy
PLATFORM_MCP_PROXY_URL = os.environ.get("PLATFORM_MCP_AGENT_URL", "http://localhost:8082")
adk.agents.register(name='platform-mcp-client-v1', agent_card_url=f'{PLATFORM_MCP_PROXY_URL}/.well-known/agent.json')


async def share_via_proxy(data_to_share: dict):
    """
    Finds the social agent proxy and invokes its 'share' capability.
    """
    try:
        print(f"Attempting to find agent 'social-agent-v1'...")
        agent = adk.agents.find('social-agent-v1')
        if not agent:
            raise ValueError("Agent 'social-agent-v1' not found. Is the proxy running and registered?")

        print("Agent found. Getting 'share' capability...")
        share_capability = agent.a2a.get_capability('share')
        if not share_capability:
            raise ValueError("Capability 'share' not available on the agent.")

        print("Invoking 'share' via proxy...")
        response_data = await share_capability.invoke(data_to_share)
        print("✓ Call via proxy successful! Response:", response_data)
        return response_data
    except Exception as e:
        print(f"✗ An error occurred: {e}")
        return None

async def main():
    """
    Main function to run the test client.
    """
    print("--- Running A2A Test Client for Social Agent ---")
    data_to_share = {"message": "Hello from the test client!"}
    await share_via_proxy(data_to_share)

    print("\n--- Running A2A Test Client for Platform MCP Client Agent ---")
    post_data = {"author_name": "test_user", "text": "This is a test post", "sentiment": "positive"}
    await create_post_via_proxy(post_data)

    print("\n--- Test Client Finished ---")


async def create_post_via_proxy(data_to_share: dict):
    """
    Finds the platform mcp client proxy and invokes its 'create_post' capability.
    """
    try:
        print(f"Attempting to find agent 'platform-mcp-client-v1'...")
        agent = adk.agents.find('platform-mcp-client-v1')
        if not agent:
            raise ValueError("Agent 'platform-mcp-client-v1' not found. Is the proxy running and registered?")

        print("Agent found. Getting 'create_post' capability...")
        create_post_capability = agent.a2a.get_capability('create_post')
        if not create_post_capability:
            raise ValueError("Capability 'create_post' not available on the agent.")

        print("Invoking 'create_post' via proxy...")
        response_data = await create_post_capability.invoke(data_to_share)
        print("✓ Call via proxy successful! Response:", response_data)
        return response_data
    except Exception as e:
        print(f"✗ An error occurred: {e}")
        return None

if __name__ == '__main__':
  # To run this, you would first need to run the proxy services, e.g.,
  # uvicorn agents.social.proxy:app --port 8080
  # uvicorn agents.platform_mcp_client.proxy:app --port 8082
  # And ensure the BACKEND_AGENT_URL environment variable is set for the proxies.
  asyncio.run(main())
