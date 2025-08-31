import cloudpickle
from agents.platform_mcp_client.agent import PlatformMCPClientAgent
import sys
import traceback
import pprint

print(f"Python version: {sys.version}")

try:
    print("Testing agent cloudpickling BEFORE set_up...")
    agent_before = PlatformMCPClientAgent(name="test_agent", mcp_server_address="dummy:8080")
    pickled_agent_before = cloudpickle.dumps(agent_before)
    unpickled_agent_before = cloudpickle.loads(pickled_agent_before)
    print("Agent IS cloudpickleable before set_up()")
except Exception as e:
    print(f"Cloudpickling failed before set_up(): {type(e).__name__}: {e}")
    traceback.print_exc()

print("-" * 20)

try:
    print("\nTesting agent cloudpickling AFTER set_up...")
    agent_after = PlatformMCPClientAgent(name="test_agent", mcp_server_address="dummy:8080")
    agent_after.set_up()
    print("Agent set_up complete.")

    # --- Deeper Inspection ---
    print("\n--- Inspecting agent state before pickling ---")
    print("--- dir(agent_after): ---")
    pprint.pprint(dir(agent_after))
    print("\n--- vars(agent_after): ---")
    # Use pprint for better readability
    pprint.pprint(vars(agent_after))
    print("--- End of inspection ---\n")


    # Try to dump and load
    pickled_agent_after = cloudpickle.dumps(agent_after)
    print("Cloudpickle dump successful.")
    unpickled_agent_after = cloudpickle.loads(pickled_agent_after)
    print("Cloudpickle load successful.")
    print("Agent IS cloudpickleable after set_up()")
except Exception as e:
    print(f"Cloudpickling failed after set_up(): {type(e).__name__}: {e}")
    traceback.print_exc()
