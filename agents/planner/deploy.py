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
from vertexai import ReasoningEngine as VertexAIReasoningEngine
from google.cloud.aiplatform_v1.types import ReasoningEngine as ReasoningEngineGAPIC
from google.cloud.aiplatform_v1.types import ReasoningEngineSpec
from google.cloud.aiplatform_v1.types import ReasoningEngineSpecPackageSpec
# from google.cloud.aiplatform_v1.types import ReasoningEngineSpecDeploymentSpec # Optional, if not used
# from google.cloud.aiplatform_v1.types import MachineSpec # Optional, if not used
import os
from vertexai.preview.reasoning_engines import AdkApp # Keep AdkApp if used for local testing

# Instantiate the ReasoningEngine wrapper (if still needed for AdkApp)
planner_reasoning_engine_instance = PlannerAgent()

# Define display_name and description for the agent
display_name = "Planner Agent"
description = """This agent helps users plan activities and events, considering their interests, budget, and location. It can generate creative and fun plan suggestions."""

# Create the AdkApp instance for local execution (using the ReasoningEngine)
# This part can remain if AdkApp is used for local testing/serving
app = AdkApp(
    agent=planner_reasoning_engine_instance,
    enable_tracing=True,
)

# Read requirements.txt
requirements_list = []
# This script is run with cwd="agents/planner" by deploy_all.py
requirements_file_path = "./requirements.txt"
if os.path.exists(requirements_file_path):
    with open(requirements_file_path, "r") as f:
        requirements_list = [line.strip() for line in f if line.strip() and not line.startswith('#')]
else:
    print(f"Warning: Requirements file not found at {requirements_file_path}. Proceeding with empty requirements for deployment.")

# New deployment logic using ReasoningEngine
reasoning_engine_package_spec = ReasoningEngineSpecPackageSpec(
    python_module_name="agents.planner.agent", # planner_adk_agent_module is agents.planner.agent
    requirements=requirements_list
)

reasoning_engine_spec = ReasoningEngineSpec(
    package_spec=reasoning_engine_package_spec
    # Example of adding deployment_spec if needed in the future:
    # deployment_spec=ReasoningEngineSpecDeploymentSpec(
    #     machine_spec=MachineSpec(machine_type="n1-standard-2"),
    # )
)

gapic_reasoning_engine_config = ReasoningEngineGAPIC(
    display_name=display_name,
    description=description,
    spec=reasoning_engine_spec
)

print("Deploying Planner Agent as Reasoning Engine...")
# The high-level SDK's .create() method typically infers project and location
# if aiplatform.init() was called. Ensure aiplatform.init() is called somewhere before this,
# or pass project and location explicitly if the SDK requires it and they are not inferred.
# For this change, we assume project and location are handled (e.g., by `gcloud auth application-default login` and `gcloud config set project`)
# or aiplatform.init() is called in a higher-level script like deploy_all.py or by the environment.
deployed_agent_resource = VertexAIReasoningEngine.create(reasoning_engine=gapic_reasoning_engine_config)

print(f"Planner Agent (Reasoning Engine) deployed successfully: {deployed_agent_resource.name}")
# Constructing the console link (ensure location and project are correctly inferred or passed)
# project_id = deployed_agent_resource.project # or client.project if available
# location = deployed_agent_resource.location # or client.location
# print(f"View in console: https://console.cloud.google.com/vertex-ai/reasoning-engines/locations/{location}/reasoning-engines/{deployed_agent_resource.resource_id}?project={project_id}")
# For now, let's print the available info:
print(f"Deployed Reasoning Engine Name: {deployed_agent_resource.name}")
print(f"Resource ID: {deployed_agent_resource.resource_id}")

# Ensure any downstream code that used 'deployed_agent' now uses 'deployed_agent_resource'.
# For example, if the script was returning 'deployed_agent', it should now return 'deployed_agent_resource'.
# The original script didn't explicitly return it, but this is a good practice reminder.
