import pickle
import sys
sys.path.append('.')
# Since we are emptying the __init__.py, we need to do a direct import
from agents.platform_mcp_client.agent import PlatformMCPClientAgent

# 1. Instantiate the agent with a valid server address and name
print("Instantiating PlatformMCPClientAgent...")
# The agent name must be a valid Python identifier.
agent_before_setup = PlatformMCPClientAgent(name="test_agent", mcp_server_address="dummy:8080")
print("Agent instantiated.")

# 2. Test pickling *before* calling set_up()
print("\n--- Testing pickling BEFORE set_up() ---")
try:
    pickled_agent_before = pickle.dumps(agent_before_setup)
    print("✅ SUCCESS: Agent IS pickleable before set_up().")
    # Optional: Test unpickling
    unpickled_agent = pickle.loads(pickled_agent_before)
    print("✅ SUCCESS: Agent can be unpickled before set_up().")
except Exception as e:
    print(f"❌ FAILURE: Pickling failed before set_up(): {e}")

# 3. Call the set_up() method
print("\nCalling agent.set_up()...")
agent_before_setup.set_up()
print("agent.set_up() finished.")


# 4. Test pickling *after* calling set_up()
print("\n--- Testing pickling AFTER set_up() ---")
try:
    pickled_agent_after = pickle.dumps(agent_before_setup)
    print("✅ SUCCESS: Agent IS pickleable after set_up().")
    # Optional: Test unpickling
    unpickled_agent_after = pickle.loads(pickled_agent_after)
    print("✅ SUCCESS: Agent can be unpickled after set_up().")
except Exception as e:
    print(f"❌ FAILURE: Pickling failed after set_up(): {e}")
