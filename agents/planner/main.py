"""
Planner Agent - Cloud Run A2A Server

Exposes the Planner Agent via standard A2A protocol using ADK's to_a2a().
"""

import os
import logging
import asyncio
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from agents.planner.agent import root_agent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get service URL from Cloud Run environment
service_name = os.getenv("K_SERVICE", "planner-agent")
region = os.getenv("CLOUD_RUN_REGION", "us-central1")
project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "laah-genai")

# Construct the Cloud Run URL
service_url = os.getenv(
    "SERVICE_URL",
    f"https://{service_name}-placeholder.{region}.run.app"
)

logger.info(f"🚀 Initializing Planner Agent A2A Server")
logger.info(f"   Service URL: {service_url}")
logger.info(f"   Project: {project_id}")
logger.info(f"   Region: {region}")

# Initialize the agent's model client BEFORE creating the A2A app
# This ensures the model is ready when requests come in
logger.info("🔧 Initializing Planner Agent model_client...")
try:
    # Use nest_asyncio to allow running async in sync context (common in Cloud Run)
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(root_agent._async_set_up())
    logger.info("✅ Planner Agent model_client initialized!")
except Exception as e:
    logger.error(f"❌ Failed to initialize model_client: {e}", exc_info=True)

# Parse host from service_url for card generation
from urllib.parse import urlparse
parsed = urlparse(service_url)
host = parsed.netloc
port = 443 if parsed.scheme == "https" else 80

# Create the A2A application - card is auto-generated with JSONRPC transport
app = to_a2a(
    root_agent,
    host=host,
    port=port,
    protocol=parsed.scheme
)

logger.info(f"✅ Planner Agent A2A Server initialized")
logger.info(f"   Agent Card URL: {service_url}/.well-known/agent.json")

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8080"))
    logger.info(f"🌐 Starting Planner Agent server on port {port}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True
    )
