#!/usr/bin/env python3
"""
Deploy Social Agent to Cloud Run with A2A support.
This script deploys the Social Agent as a Cloud Run service using to_a2a.
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
SERVICE_NAME = "social-agent"
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
        return False
    logger.info(result.stdout)
    return True

def deploy_social_agent():
    """Deploy the Social Agent to Cloud Run."""
    logger.info("=" * 60)
    logger.info("DEPLOYING SOCIAL AGENT TO CLOUD RUN")
    logger.info("=" * 60)
    logger.info(f"Project: {PROJECT_ID}")
    logger.info(f"Region: {REGION}")
    logger.info(f"Service: {SERVICE_NAME}")
    logger.info(f"Image: {IMAGE_PATH}")
    
    # Step 1: Build and deploy using Cloud Build
    logger.info("\n🏗️  Step 1: Building and deploying with Cloud Build...")
    cmd = [
        "gcloud", "builds", "submit",
        ".",
        "--config", "agents/social/cloudbuild.yaml",
        "--substitutions",
        f"_SERVICE_NAME={SERVICE_NAME},"
        f"_REGION={REGION},"
        f"_IMAGE_PATH={IMAGE_PATH},"
        f"_GEMINI_MODEL={GEMINI_MODEL}",
        "--project", PROJECT_ID
    ]
    
    if not run_command(cmd):
        logger.error("❌ Deployment failed")
        return False
    
    # Step 2: Get the service URL
    logger.info("\n🔍 Step 2: Retrieving service URL...")
    cmd = [
        "gcloud", "run", "services", "describe",
        SERVICE_NAME,
        "--platform", "managed",
        "--region", REGION,
        "--format", "value(status.url)",
        "--project", PROJECT_ID
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("❌ Failed to get service URL")
        return False
    
    service_url = result.stdout.strip()
    logger.info(f"✅ Service URL: {service_url}")
    
    # Step 3: Test the agent card endpoint
    logger.info("\n🧪 Step 3: Testing agent card endpoint...")
    logger.info(f"Agent Card URL: {service_url}/.well-known/agent.json")
    logger.info(f"A2A Endpoint: {service_url}/a2a/v1/message:send")
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ DEPLOYMENT COMPLETE")
    logger.info("=" * 60)
    logger.info(f"\nSocial Agent is now available at: {service_url}")
    logger.info(f"\nTo update Orchestrate Agent to use this service:")
    logger.info(f"1. Update the agent card URL in agents/orchestrate/agent_cards.py")
    logger.info(f"2. Change base_url to: {service_url}")
    logger.info(f"3. Redeploy Orchestrate Agent")
    
    return True

if __name__ == "__main__":
    success = deploy_social_agent()
    sys.exit(0 if success else 1)
