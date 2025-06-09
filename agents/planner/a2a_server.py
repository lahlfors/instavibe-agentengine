from a2a_common.common.server import A2AServer
from a2a_common.common.types import AgentCard, AgentCapabilities, AgentSkill
from a2a_common.common.task_manager import AgentTaskManager
from planner.planner_agent import PlannerAgent

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# For AgentCard URL - this should be the public URL of the Cloud Run service
# It will be injected as an environment variable by Cloud Run/Vertex deployment
PUBLIC_URL = os.environ.get("AGENT_PUBLIC_URL", "http://localhost:placeholder_port")

def main():
    try:
        current_adk_agent = PlannerAgent()

        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
            id="night_out_planner",
            name="Night out planner",
            description="Generates fun plan suggestions.",
            tags=["instavibe"],
            examples=["Plan a night out in Boston"],
        )
        agent_card = AgentCard(
            name="NightOut Planner Agent",
            description="Generates fun plan suggestions.",
            url=PUBLIC_URL,
            version="1.0.0",
            defaultInputModes=getattr(current_adk_agent, 'SUPPORTED_CONTENT_TYPES', ["text/plain"]),
            defaultOutputModes=getattr(current_adk_agent, 'SUPPORTED_CONTENT_TYPES', ["text/plain"]),
            capabilities=capabilities,
            skills=[skill],
        )
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=current_adk_agent),
        )
        logger.info(f"Attempting to start server for Agent Card: {agent_card.name} at {PUBLIC_URL}")
        server.start()
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}", exc_info=True)
        exit(1)

if __name__ == "__main__":
    main()