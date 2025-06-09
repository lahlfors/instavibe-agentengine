import os
import os
from google.cloud import aiplatform as vertexai # Standard alias
from vertexai import reasoning_engines as VertexAIReasoningEngine # Specific import for ReasoningEngine
from google.cloud.aiplatform_v1.types import ReasoningEngine as ReasoningEngineGAPIC
from google.cloud.aiplatform_v1.types import ReasoningEngineSpec
# ReasoningEngineSpecPackageSpec is expected to be an attribute of ReasoningEngineSpec

# AdkApp and PlannerAgent are for local execution or if PlannerAgent has specific ADK interop.
from agents.planner.planner_agent import PlannerAgent
from vertexai.preview.reasoning_engines import AdkApp


def deploy_planner_main_func(project_id: str, region: str, base_dir: str):
    """
    Deploys the Planner Agent as a Vertex AI Reasoning Engine.

    Args:
        project_id: The Google Cloud project ID.
        region: The Google Cloud region for deployment.
        base_dir: The base directory of the repository, used to find requirements.txt.
    """
    # aiplatform.init should be called by the caller (e.g., deploy_all.py)
    # vertexai.init(project=project_id, location=region)

    display_name = "Planner Agent"
    description = """This agent helps users plan activities and events, considering their interests, budget, and location. It can generate creative and fun plan suggestions."""

    # Construct the path to requirements.txt relative to the base_dir
    requirements_file_path = os.path.join(base_dir, "agents/planner/requirements.txt")
    requirements_list = []
    if os.path.exists(requirements_file_path):
        with open(requirements_file_path, "r") as f:
            requirements_list = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    else:
        print(f"Warning: Requirements file not found at {requirements_file_path}. Proceeding with empty requirements for deployment.")

    # Use ReasoningEngineSpec.PackageSpec
    current_package_spec = ReasoningEngineSpec.PackageSpec(
        python_module_name="agents.planner.agent",  # Module containing the ADK agent
        requirements=requirements_list
    )

    reasoning_engine_spec = ReasoningEngineSpec(
        package_spec=current_package_spec
    )

    gapic_reasoning_engine_config = ReasoningEngineGAPIC(
        display_name=display_name,
        description=description,
        spec=reasoning_engine_spec
        # operation_metadata will be populated by the SDK
    )

    print(f"Deploying Planner Agent as Reasoning Engine to project {project_id} in {region}...")
    # VertexAIReasoningEngine.create uses the project and location from aiplatform.init()
    deployed_agent_resource = VertexAIReasoningEngine.create(reasoning_engine=gapic_reasoning_engine_config)

    print(f"Planner Agent (Reasoning Engine) deployed successfully: {deployed_agent_resource.name}")
    print(f"Deployed Reasoning Engine Name: {deployed_agent_resource.name}")
    print(f"Resource ID: {deployed_agent_resource.resource_id}")
    # You could return deployed_agent_resource.name or other identifiers if needed by the caller.
    return deployed_agent_resource


if __name__ == "__main__":
    # This block is for local execution or testing of the AdkApp.
    # It's not directly used by deploy_all.py for cloud deployment.
    print("Running Planner Agent locally using AdkApp...")

    # For local execution, AdkApp typically needs an instance of the agent.
    # PlannerAgent itself is a ReasoningEngine.
    planner_reasoning_engine_instance = PlannerAgent()

    app = AdkApp(
        agent=planner_reasoning_engine_instance,
        enable_tracing=True,
    )

    # To run this locally (example):
    # 1. Ensure you have necessary environment variables or gcloud auth.
    # 2. (Optional) If you need to simulate project_id/region for local logic that might use them:
    #    mock_project_id = "your-local-project"
    #    mock_region = "your-local-region"
    #    vertexai.init(project=mock_project_id, location=mock_region) # For local context if needed by agent

    # The AdkApp doesn't deploy to Vertex AI; it serves locally.
    # To test the cloud deployment function directly (requires auth and project/region):
    # deploy_planner_main_func(project_id="your-gcp-project", region="us-central1", base_dir=".")

    # If you want to run the ADK app server:
    # app.serve() # This would typically be `adk serve` or `python -m adk serve` from CLI
    print("AdkApp configured. To run locally, use 'adk run' or 'adk serve' pointing to this file or the agent.")
    print("Or, if you have a main() in PlannerAgent for local execution, call that.")
    # Example: If PlannerAgent had a main method for local interaction:
    # planner_reasoning_engine_instance.main()
