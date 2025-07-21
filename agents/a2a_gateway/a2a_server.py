# a2a_server.py (Enhanced for multiple backends)
import os
import uvicorn
import uuid
from starlette.applications import Starlette
from a2a.core import AgentCard, AgentExecutor, AgentSkill, RequestContext, TaskUpdater
from a2a.server.starlette import A2AStarletteApplication
import asyncio
from typing import Dict

from google.cloud import aiplatform
from vertexai.reasoning_engines import ReasoningEngine
import vertexai

# --- Configuration ---
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
LOCATION = os.environ.get("GCP_REGION")

# Dict mapping skill IDs to Agent Engine Resource Names
AGENT_ENGINE_ENDPOINTS = {
    "analyze_data": os.environ.get("ADK_AGENT_ANALYZER"),
    "generate_report": os.environ.get("ADK_AGENT_REPORTER"),
    "send_notification": os.environ.get("ADK_AGENT_NOTIFIER"),
}

if not all([PROJECT_ID, LOCATION]):
    raise ValueError("Missing GCP_PROJECT_ID or GCP_REGION")
if not all(AGENT_ENGINE_ENDPOINTS.values()):
    raise ValueError("Missing ADK Agent environment variables")

vertexai.init(project=PROJECT_ID, location=LOCATION)

# --- A2A AgentExecutor Implementation ---
class MultiADKProxyExecutor(AgentExecutor):
    def __init__(self, endpoints: Dict[str, str]):
        self.engines: Dict[str, ReasoningEngine] = {}
        for skill, resource_name in endpoints.items():
            if resource_name:
                self.engines[skill] = ReasoningEngine(resource_name)
        print(f"Initialized engines for: {list(self.engines.keys())}")

    async def execute(self, context: RequestContext, updater: TaskUpdater):
        user_input = context.get_user_input()
        skill_id = context.get_skill_id()  # Assuming skill_id is passed

        if not user_input:
            await updater.complete()
            return

        target_engine = self.engines.get(skill_id)
        if not target_engine:
            await updater.add_artifact({"error": f"Unknown skill ID: {skill_id}"})
            await updater.complete()
            return

        await updater.update_status({"detail": f"Routing to ADK agent for skill: {skill_id}"})

        try:
            # Call the target ADK agent
            response = target_engine.query(input=user_input)
            await updater.add_artifact({"result": response})
        except Exception as e:
            print(f"Error calling Agent Engine for {skill_id}: {e}")
            await updater.add_artifact({"error": str(e)})
        finally:
            await updater.complete()

# --- A2A Application Setup ---
my_a2a_executor = MultiADKProxyExecutor(AGENT_ENGINE_ENDPOINTS)

agent_card = AgentCard(
    agent_id=str(uuid.uuid4()),
    agent_name="Multi-Agent A2A Gateway",
    description="Routes A2A requests to specialized ADK agents.",
    endpoint=os.environ.get("CLOUD_RUN_URL", "https://your-a2a-gateway.a.run.app"),
    skills=[
        AgentSkill(id="analyze_data", description="Analyzes input data."),
        AgentSkill(id="generate_report", description="Generates a report from data."),
        AgentSkill(id="send_notification", description="Sends a notification."),
    ]
)

a2a_app = A2AStarletteApplication(
    agent_executor=my_a2a_executor,
    agent_card=agent_card,
)

app = Starlette()
app.mount("/a2a", a2a_app)

@app.get("/")
async def root(request):
    return {"message": "Multi-Agent A2A Gateway Running"}

# Uvicorn command for Dockerfile: ["uvicorn", "a2a_server:app", "--host", "0.0.0.0", "--port", "8080"]
