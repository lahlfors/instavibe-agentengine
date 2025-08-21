import os
from dotenv import load_dotenv
from . import agent

# Load environment variables from the root .env file.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# The root_agent is now the main export of this module.
# The PlannerAgent class has been removed as it is no longer needed
# when deploying the agent using the AgentEngineApp framework.
root_agent = agent.root_agent