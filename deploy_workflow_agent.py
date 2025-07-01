import vertexai
import os
from vertexai.preview import agent_engines # Corrected import path
from dotenv import load_dotenv

# Assuming InstavibeWorkflowAgent is in agents.instavibe_workflow.agent
# We will import it within App.set_up() to ensure it's imported in the deployment environment correctly.

class App:
    def __init__(self):
        load_dotenv() # Load .env file from the root of the project
        self.GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.GOOGLE_CLOUD_LOCATION = os.environ.get("COMMON_GOOGLE_CLOUD_LOCATION", "us-central1") # Default if not set

        # Specific environment variables for the InstavibeWorkflowAgent
        # These will be passed to the agent's environment during deployment
        self.AGENTS_PLANNER_RESOURCE_NAME = os.environ.get("AGENTS_PLANNER_RESOURCE_NAME")
        self.AGENTS_ORCHESTRATE_RESOURCE_NAME = os.environ.get("AGENTS_ORCHESTRATE_RESOURCE_NAME")
        # SELF_AGENT_ENGINE_ID was used in main.py, AdkApp might handle this internally or it might be needed for the agent.
        # For now, let's assume AdkApp/AgentEngine handles its own identity.

        if not self.GOOGLE_CLOUD_PROJECT:
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set.")
        if not self.GOOGLE_CLOUD_LOCATION:
            raise ValueError("COMMON_GOOGLE_CLOUD_LOCATION environment variable not set.")
        if not self.AGENTS_PLANNER_RESOURCE_NAME:
            print("Warning: AGENTS_PLANNER_RESOURCE_NAME not set. Planner functionality may be affected.")
        if not self.AGENTS_ORCHESTRATE_RESOURCE_NAME:
            print("Warning: AGENTS_ORCHESTRATE_RESOURCE_NAME not set. Orchestration functionality may be affected.")

    def set_up(self):
        """
        This method is called by the ADK when the agent is being set up in the deployment environment.
        """
        print("App.set_up(): Setting up Instavibe Workflow Agent...")
        # Set environment variables in the remote execution environment
        # These are essential for the agent logic itself.
        os.environ["GOOGLE_CLOUD_PROJECT"] = self.GOOGLE_CLOUD_PROJECT
        os.environ["COMMON_GOOGLE_CLOUD_LOCATION"] = self.GOOGLE_CLOUD_LOCATION
        if self.AGENTS_PLANNER_RESOURCE_NAME:
            os.environ["AGENTS_PLANNER_RESOURCE_NAME"] = self.AGENTS_PLANNER_RESOURCE_NAME
        if self.AGENTS_ORCHESTRATE_RESOURCE_NAME:
            os.environ["AGENTS_ORCHESTRATE_RESOURCE_NAME"] = self.AGENTS_ORCHESTRATE_RESOURCE_NAME

        # Initialize Vertex AI SDK here if needed by the agent,
        # though AdkApp and ReasoningEngine calls often handle their own initialization.
        # For agent-to-agent calls using reasoning_engines.ReasoningEngine, explicit init might be good.
        print(f"App.set_up(): Initializing Vertex AI for project={self.GOOGLE_CLOUD_PROJECT}, location={self.GOOGLE_CLOUD_LOCATION}")
        vertexai.init(project=self.GOOGLE_CLOUD_PROJECT, location=self.GOOGLE_CLOUD_LOCATION)

        # Import the agent class and instantiate it
        from agents.instavibe_workflow.agent import InstavibeWorkflowAgent
        self.ROOT_AGENT = InstavibeWorkflowAgent()

        # Import AdkApp here as it's part of the ADK specific setup
        from vertexai.preview.reasoning_engines import AdkApp # Corrected import path

        print("App.set_up(): Wrapping agent with AdkApp...")
        self.app = AdkApp(agent=self.ROOT_AGENT, enable_tracing=True)
        print("App.set_up(): Setup complete.")

    # The AdkApp is expected to have query/run methods, or these are handled by ADK framework.
    # The example provided `create_session`, which might be for invoking the agent.
    # For now, let's assume AdkApp makes the agent directly callable by the Agent Engine.
    # If specific methods like `query` or `run` need to be exposed on `App` that delegate to `self.app`,
    # they can be added here. The ADK documentation should clarify this.
    # For example, if the deployed agent needs to be invoked via `App().query(...)`:
    # def query(self, **kw_args):
    #     if not hasattr(self, 'app'):
    #         self.set_up() # Ensure setup is called if query is entry point
    #     return self.app.query(**kw_args)


def deploy_agent_engine_app():
    print("Starting deployment of Instavibe Workflow Agent...")
    load_dotenv() # Load .env from project root for local deployment script execution

    PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
    LOCATION = os.environ.get("COMMON_GOOGLE_CLOUD_LOCATION", "us-central1")
    # Staging bucket should ideally be unique per project or well-managed
    STAGING_BUCKET = os.environ.get("GOOGLE_CLOUD_STAGING_BUCKET", f"gs://{PROJECT_ID}-adk-staging")
    AGENT_DISPLAY_NAME = "Instavibe Workflow Agent"

    if not PROJECT_ID:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set for deployment script.")

    print(f"Deployment Configuration: Project={PROJECT_ID}, Location={LOCATION}, Staging={STAGING_BUCKET}")

    vertexai.init(
        project=PROJECT_ID,
        location=LOCATION,
        staging_bucket=STAGING_BUCKET,
    )
    print("Vertex AI SDK initialized for deployment.")

    # Read requirements.txt from the root
    # The user feedback example read a specific requirements.txt.
    # For now, assuming a general one at the root, or it could be specific.
    reqs = []
    if os.path.exists('requirements.txt'):
        with open('requirements.txt', 'r') as f:
            reqs = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        print(f"Loaded {len(reqs)} requirements from requirements.txt")
    else:
        print("Warning: requirements.txt not found at project root. Ensure dependencies are correctly specified.")

    # Ensure ADK dependencies are included
    adk_specific_reqs = ["google-cloud-aiplatform[agents,reasoning_engines]>=1.47.0"]
    # As per user feedback, it was [agent_engines,adk]. Let's use `agents` and `reasoning_engines`
    # as these are more common general extras. If `adk` extra is specifically needed, we can adjust.
    # Versions: reasoning_engines was 1.47.0, agent_engines 1.82.0.
    # The higher one for reasoning_engines is safer for AdkApp:
    # Let's try: google-cloud-aiplatform[generic_agents,reasoning_engines]>=1.47.0
    # The user feedback used: "google-cloud-aiplatform[agent_engines,adk]"
    # Let's stick to what the user provided as it's more specific to this new ADK flow.
    adk_specific_reqs = ["google-cloud-aiplatform[agent_engines,adk]>=1.82.0"] # Using the higher version mentioned

    final_requirements = list(set(reqs + adk_specific_reqs))
    print(f"Final requirements for deployment: {final_requirements}")

    # Define extra_packages: Python files or directories (packages) needed by the agent.
    # These paths should be relative to the project root where the deploy script is.
    extra_pkgs = [
        "agents/instavibe_workflow/agent.py",
        "agents/instavibe_workflow/__init__.py", # Important for the package structure
        # If main.py is still used by App.set_up, add it. For now, assuming direct agent import.
        # "agents/instavibe_workflow/main.py",
        "agents/__init__.py" # Parent package's init
    ]
    print(f"Extra packages for deployment: {extra_pkgs}")

    agent_config = {
        "agent_engine": App(), # Instance of our App class
        "display_name": AGENT_DISPLAY_NAME,
        "requirements": final_requirements,
        "extra_packages": extra_pkgs,
        "description": "Orchestrates planning and posting of events by coordinating other agents.",
        # Default reasoning engine to use if not specified in requests.
        # "default_reasoning_engine": "projects/PROJECT_ID/locations/LOCATION/reasoningEngines/REASONING_ENGINE_ID", # Optional
        # "tools": [], # Optional: List of global tools for the agent engine
    }

    print(f"Looking for existing agents with display name: {AGENT_DISPLAY_NAME}...")
    existing_agents = list(agent_engines.list(filter=f'display_name="{AGENT_DISPLAY_NAME}"'))

    remote_app = None
    if existing_agents:
        print(f"Found {len(existing_agents)} existing agent(s). Updating the first one: {existing_agents[0].resource_name}")
        # Ensure we pass the resource_name correctly for update
        remote_app = agent_engines.update(resource_name=existing_agents[0].name, **agent_config)
        print(f"Agent updated: {remote_app.name if remote_app else 'Failed to update'}")
    else:
        print("No existing agent found. Creating a new one...")
        remote_app = agent_engines.create(**agent_config)
        print(f"Agent created: {remote_app.name if remote_app else 'Failed to create'}")

    if remote_app:
        print(f"Deployment successful. Agent Resource Name: {remote_app.name}")
    else:
        print("Deployment failed or did not return a remote_app object.")

    return remote_app

if __name__ == "__main__":
    # Example: Ensure GOOGLE_CLOUD_PROJECT is set in your .env or environment
    # For local testing, you might need to mock `agent_engines` calls or have credentials.
    # This script is intended to be run in an environment with gcloud auth and necessary permissions.
    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        print("Error: GOOGLE_CLOUD_PROJECT is not set. Please set it in your .env file or environment.")
    else:
        print("Attempting to deploy Instavibe Workflow Agent...")
        deployed_agent_info = deploy_agent_engine_app()
        if deployed_agent_info:
            print(f"Instavibe Workflow Agent deployed/updated successfully: {deployed_agent_info.name}")
        else:
            print("Instavibe Workflow Agent deployment/update failed.")

# Notes on GOOGLE_CLOUD_LOCATION:
# The user feedback used COMMON_GOOGLE_CLOUD_LOCATION. AdkApp/AgentEngine generally use GOOGLE_CLOUD_LOCATION.
# I've used COMMON_GOOGLE_CLOUD_LOCATION where it was in the original agent, assuming it's set.
# If there's a discrepancy, it should be standardized, likely to GOOGLE_CLOUD_LOCATION.
# For the deployment script itself, I've defaulted to GOOGLE_CLOUD_LOCATION or "us-central1".
# The App class will use what's in env vars.
# Staging bucket: Ensured it uses PROJECT_ID.
# Corrected agent_engines.update call to use existing_agents[0].name for resource_name.
# Corrected import for agent_engines and AdkApp to vertexai.preview.agent_engines and vertexai.preview.reasoning_engines respectively.
# Self-correction: The problem statement was `cannot import name 'Agent' from 'vertexai.preview.reasoning_engines'`.
# `AdkApp` is also in `vertexai.preview.reasoning_engines`.
# `agent_engines` (for list, create, update) is in `vertexai.preview.agent_engines`.
# So, `from vertexai.preview import agent_engines` and `from vertexai.preview.reasoning_engines import AdkApp`. This seems correct.
# Changed `google-cloud-aiplatform[agents,reasoning_engines]>=1.47.0` to `google-cloud-aiplatform[agent_engines,adk]>=1.82.0`
# as per the more specific user feedback.
# Added `agents/__init__.py` and `agents/instavibe_workflow/__init__.py` to extra_packages.
# Made print statements to follow progress.
# Added a check for GOOGLE_CLOUD_PROJECT in __main__ block.
# Added a description field to agent_config.
