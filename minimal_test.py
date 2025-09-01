import vertexai
from vertexai import agent_engines
import os
import logging

logging.basicConfig(level=logging.INFO)

PROJECT = os.getenv("COMMON_GOOGLE_CLOUD_PROJECT", "laah-genai")
LOCATION = "us-central1"

try:
    print(f"Initializing Vertex AI for project={PROJECT}, location={LOCATION}")
    vertexai.init(project=PROJECT, location=LOCATION)
    print("Vertex AI initialized.")

    # Test with a known or non-existent agent ID
    test_agent_id = "orchestrate_agent" # Or any agent_id used in your config
    list_filter = f'labels.agent_id="{test_agent_id}"'

    print(f"Using filter: [{list_filter}]")

    agents = list(agent_engines.list(filter=list_filter))
    print(f"SUCCESS: Found {len(agents)} agents for ID '{test_agent_id}'.")
    for agent in agents:
        print(f"  - {agent.resource_name} (Display: {agent.display_name}, Labels: {agent.labels})")

except Exception as e:
    logging.error(f"ERROR during minimal test: {e}", exc_info=True)
