import os
import sys
from vertexai.preview.reasoning_engines import AdkApp

# Ensure the current directory is in the path to allow relative imports if needed by main
sys.path.insert(0, os.path.dirname(__file__))
from main import app as workflow_flask_app # Import the Flask app

def load_requirements(base_dir):
    """Loads requirements from requirements.txt in the given base_dir."""
    requirements = []
    requirements_path = os.path.join(base_dir, "requirements.txt")
    if os.path.exists(requirements_path):
        with open(requirements_path, 'r', encoding='utf-8') as f:
            requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    else:
        print(f"Warning: requirements.txt not found at {requirements_path}")
    return requirements

def deploy_instavibe_workflow_agent_main_func(
    project_id: str,
    region: str, # maps to location
    base_dir: str, # This will be 'agents/instavibe_workflow'
    # These will be passed via additional_deploy_args from deploy_all.py
    agent_display_name: str,
    self_reasoning_engine_id_for_env: str,
    planner_re_name: str | None,
    orchestrate_re_name: str | None
):
    """
    Main deployment function for the Instavibe Workflow Agent (AdkApp-style).
    This function is called by deploy_all.py's deploy_agent_with_forced_update.
    It defines and returns the AdkApp instance for the workflow agent.
    """
    print(f"--- Defining AdkApp for Instavibe Workflow Agent ---")
    print(f"  Base directory for this agent: {base_dir}")
    print(f"  Project: {project_id}, Region: {region}")
    print(f"  Display Name for AdkApp/RE: {agent_display_name}")
    print(f"  SELF_AGENT_ENGINE_ID for runtime: {self_reasoning_engine_id_for_env}")
    print(f"  Planner RE Name for runtime: {planner_re_name}")
    print(f"  Orchestrate RE Name for runtime: {orchestrate_re_name}")

    agent_requirements = load_requirements(base_dir)
    print(f"  AdkApp requirements loaded: {agent_requirements}")

    runtime_env_vars = {
        "GOOGLE_CLOUD_PROJECT": project_id,
        "COMMON_GOOGLE_CLOUD_LOCATION": region,
        "SELF_AGENT_ENGINE_ID": self_reasoning_engine_id_for_env,
        "PLANNER_AGENT_RESOURCE_NAME": planner_re_name if planner_re_name else "",
        "ORCHESTRATE_AGENT_RESOURCE_NAME": orchestrate_re_name if orchestrate_re_name else "",
        "PORT": "8080", # Default port inside the container
    }
    print(f"  Runtime environment variables for AdkApp: {runtime_env_vars}")

    # extra_packages: path to agent.py, relative to AdkApp's understanding of its root.
    # If AdkApp packages the directory of `agent_engine` (main.py), and agent.py is a sibling,
    # it might be found automatically. Explicitly listing it is safer.
    # The path should be what AdkApp expects when it stages files.
    # If base_dir is 'agents/instavibe_workflow', then 'agent.py' is correct.
    extra_packages_list = [os.path.join(base_dir, 'agent.py')]
    # Verify paths for extra_packages if issues arise with ADK packaging.
    # For example, if ADK's context is the repo root, it might need 'agents/instavibe_workflow/agent.py'.
    # However, AdkApp usually makes paths relative to the agent_engine's file or a specified app_dir.
    # Given deploy_all.py calls this with base_dir = 'agents/instavibe_workflow',
    # and AdkApp's agent_engine points to main:app within that dir,
    # extra_packages=['agent.py'] (relative to main.py) should be correct.
    # Or, to be very explicit from repo root if ADK stages from there:
    # extra_packages_list = ['agents/instavibe_workflow/agent.py']
    # The AdkApp's `extra_packages` are relative to the directory containing the `agent_engine` file.

    print(f"  Extra packages for AdkApp: {extra_packages_list}")


    app_config = AdkApp(
        agent_engine=workflow_flask_app, # The imported Flask app object
        display_name=agent_display_name,
        requirements=agent_requirements,
        # extra_packages should contain paths to additional Python files or directories
        # that need to be included in the deployment package, relative to the main app file.
        # Since agent.py is in the same directory as main.py and main.py uses "from .agent",
        # ADK should package agent.py automatically.
        # Explicitly: extra_packages=['agent.py']
        # Or if InstavibeWorkflowAgent was in a sub-module: extra_packages=['submodule']
        extra_packages=['agent.py'],
        description="Instavibe Workflow Agent (Flask AdkApp for orchestration)",
        env_vars=runtime_env_vars
    )
    print(f"  AdkApp instance for '{agent_display_name}' created.")

    # The agent_engines.create() call will be handled by deploy_agent_with_forced_update in deploy_all.py
    # This function just needs to return the AdkApp configuration object.
    return app_config
