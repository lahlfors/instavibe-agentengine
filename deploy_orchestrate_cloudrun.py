#!/usr/bin/env python3
"""
Deploy Orchestrate Agent to Cloud Run with correct agent URLs.
"""

import os
import subprocess
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "laah-genai")
REGION = "us-central1"
SERVICE_NAME = "orchestrate-agent"
IMAGE_PATH = f"{REGION}-docker.pkg.dev/{PROJECT_ID}/instavibe-images/{SERVICE_NAME}:latest"
GEMINI_MODEL = os.getenv("COMMON_GEMINI_MODEL", "gemini-2.0-flash-exp")

def run_command(cmd, cwd="."):
    """Execute a shell command and return the result."""
    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Command failed with exit code {result.returncode}")
        logger.error(f"STDOUT: {result.stdout}")
        logger.error(f"STDERR: {result.stderr}")
        return None
    return result.stdout.strip()

def get_service_url(service_name):
    """Get the URL of a Cloud Run service."""
    cmd = [
        "gcloud", "run", "services", "describe",
        service_name,
        "--platform", "managed",
        "--region", REGION,
        "--format", "value(status.url)",
        "--project", PROJECT_ID
    ]
    return run_command(cmd)

def deploy_orchestrate_agent():
    """Deploy the Orchestrate Agent to Cloud Run."""
    logger.info("=" * 60)
    logger.info("DEPLOYING ORCHESTRATE AGENT TO CLOUD RUN")
    logger.info("=" * 60)
    
    # Step 1: Fetch Agent URLs
    logger.info("\n🔍 Step 1: Fetching Agent URLs...")
    
    planner_url = get_service_url("planner-agent")
    if not planner_url:
        logger.error("❌ Failed to get Planner Agent URL")
        return False
    logger.info(f"  Planner Agent: {planner_url}")
    
    social_url = get_service_url("social-agent") or ""
    logger.info(f"  Social Agent: {social_url}")
    
    platform_url = get_service_url("platform-mcp-client-agent") or ""
    logger.info(f"  Platform Agent: {platform_url}")
    
    otel_url = get_service_url("otel-collector") or ""
    if otel_url and not otel_url.endswith(":4317"):
        otel_url = f"{otel_url}:4317"
    logger.info(f"  OTel Collector: {otel_url}")

    mcp_url = get_service_url("mcp-tool-server") or ""
    logger.info(f"  MCP Server: {mcp_url}")

    # Step 2: Build and deploy using Cloud Build
    logger.info("\n🏗️  Step 2: Building and deploying with Cloud Build...")
    
    # We need to pass the Orchestrate Agent URL itself if it exists, or placeholder
    # But Cloud Run assigns it. The script usually passes it for self-reference if needed.
    # Let's try to get existing one, or empty.
    orchestrate_url = get_service_url("orchestrate-agent") or ""
    
    cmd = [
        "gcloud", "builds", "submit",
        ".",
        "--config", "agents/orchestrate/cloudbuild.yaml",
        "--substitutions",
        f"_SERVICE_NAME={SERVICE_NAME},"
        f"_REGION={REGION},"
        f"_IMAGE_PATH={IMAGE_PATH},"
        f"_GEMINI_MODEL={GEMINI_MODEL},"
        f"_PLANNER_AGENT_URL={planner_url},"
        f"_SOCIAL_AGENT_URL={social_url},"
        f"_PLATFORM_MCP_CLIENT_AGENT_URL={platform_url},"
        f"_ORCHESTRATE_AGENT_URL={orchestrate_url},"
        f"_OTEL_COLLECTOR_ENDPOINT={otel_url},"
        f"_MCP_SERVER_ADDRESS={mcp_url},"
        f"_GOOGLE_CLOUD_PROJECT={PROJECT_ID},"
        f"_CLOUD_RUN_REGION={REGION}",
        "--project", PROJECT_ID
    ]
    
    if run_command(cmd) is None:
        logger.error("❌ Deployment failed")
        return False
    
    # Step 3: Get the service URL (verify)
    logger.info("\n🔍 Step 3: Retrieving service URL...")
    new_url = get_service_url(SERVICE_NAME)
    if not new_url:
        logger.error("❌ Failed to get service URL")
        return False
    
    logger.info(f"✅ Service URL: {new_url}")
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ DEPLOYMENT COMPLETE")
    logger.info("=" * 60)
    
    return True

if __name__ == "__main__":
    success = deploy_orchestrate_agent()
    sys.exit(0 if success else 1)
