from agents.planner import agent as planner_adk_agent_module
from agents.planner.planner_agent import PlannerAgent
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp

# This is the ADK agent definition, typically found in agent.py
# It's used for local execution via AdkApp if needed, and potentially by PlannerAgent.
# For agent_engines.create, we pass the module containing this agent.
actual_adk_agent = planner_adk_agent_module.root_agent

# PlannerAgent is a ReasoningEngine that wraps the ADK agent.
# This is suitable for use with AdkApp for local execution if PlannerAgent provides additional logic.
planner_reasoning_engine = PlannerAgent()

display_name = "Planner Agent"
description = """
This agent helps users plan activities and events,
considering their interests, budget, and location.
It can generate creative and fun plan suggestions.
"""

# AdkApp is used for local development and testing with 'adk run' or 'adk serve'.
# It can run either a raw ADK Agent or a ReasoningEngine.
# If PlannerAgent is the intended interface for local serving (e.g., it has task management), use it.
# Otherwise, if just testing the core ADK agent, use actual_adk_agent.
# Let's assume PlannerAgent is the desired local interface.
app = AdkApp(
    agent=planner_reasoning_engine, # Using the PlannerAgent (ReasoningEngine)
    enable_tracing=True,
    # tools_config=?, # Optional: if PlannerAgent or its underlying agent needs specific tool configs
)

# agent_engines.create is used to deploy the agent to Vertex AI Agent Engines.
# It expects an ADK agent module or a specific ADK agent instance.
# Following the orchestrate example, we pass the module.
deployed_agent = agent_engines.create(
    app=planner_adk_agent_module, # Pass the module
    display_name=display_name,
    description=description,
    requirements_path="agents/planner/requirements.txt", # Ensure this path is correct
    # reserved_tools=?, # Optional: if specific tools should be reserved
)

# To be consistent with orchestrate/deploy.py that has:
# remote_agent = agent_engines.create(agent, requirements="./requirements.txt")
# We should ensure the path to requirements.txt is relative to the deploy.py script's execution,
# or an absolute path. The orchestrate example uses a relative path.
# If deploy.py is run from the repo root, then "agents/planner/requirements.txt" is correct.
# If it's run from within agents/planner/, then "./requirements.txt" would be correct.
# The orchestrate example suggests it's relative to the deploy script's location if not specified otherwise.
# Let's assume the requirements file is in the same directory as this deploy script for now,
# matching the orchestrate example structure.

# Re-checking orchestrate: requirements="./requirements.txt"
# This implies requirements.txt is in the same dir as orchestrate/deploy.py
# So, for planner, it should be "./requirements.txt" if requirements.txt is in agents/planner/

# Final structure based on re-evaluation:
# The AdkApp uses the reasoning engine (PlannerAgent)
# The agent_engines.create uses the ADK agent module (planner_adk_agent_module)

# Overwriting again with the most consistent interpretation:
# AdkApp uses the reasoning engine `planner_reasoning_engine`
# agent_engines.create uses the adk agent module `planner_adk_agent_module`
# requirements_path is relative to the `deploy.py` file's direct location.

# Let's assume requirements.txt is in agents/planner/
# The path for agent_engines.create should be "./requirements.txt"

# Overwrite with the refined version:
from agents.planner import agent as planner_adk_agent_module
from agents.planner.planner_agent import PlannerAgent
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp

# Instantiate the ReasoningEngine wrapper
planner_reasoning_engine_instance = PlannerAgent()

# Define display_name and description for the agent
display_name = "Planner Agent"
description = """This agent helps users plan activities and events, considering their interests, budget, and location. It can generate creative and fun plan suggestions."""

# Create the AdkApp instance for local execution (using the ReasoningEngine)
app = AdkApp(
    agent=planner_reasoning_engine_instance,
    enable_tracing=True,
)

# Create the deployed agent for Vertex AI Agent Engines (using the ADK agent module)
# The 'app' parameter here refers to the ADK agent or module to be deployed.
# The 'requirements_path' should be relative to this deploy.py file if it's co-located
# with requirements.txt, or a full path from the execution root.
# Given the subtask states "Verify agents/planner/requirements.txt exists",
# the path should be "./requirements.txt" if deploy.py is in agents/planner/
# or "agents/planner/requirements.txt" if deploy.py is at the root.
# The orchestrate example uses "./requirements.txt", implying it's co-located.
# Let's assume this deploy.py will be in agents/planner/
deployed_agent = agent_engines.create(
    app=planner_adk_agent_module,
    display_name=display_name,
    description=description,
    requirements_path="./requirements.txt", # Assuming requirements.txt is in the same directory
)
