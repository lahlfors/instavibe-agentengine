# agents/app/agent_engine_app.py
import datetime
import json
import inspect
import logging # Keep logging import
import os
from dotenv import load_dotenv
from typing import Any, Dict, List, Optional, Type, Union
import time

import google.auth
import vertexai
import google.api_core.exceptions
from google.cloud import logging as google_cloud_logging
from vertexai import agent_engines
from vertexai.preview import reasoning_engines
from agents.app.utils.gcs import create_bucket_if_not_exists
# from common.observability import setup_observability # Assuming this is handled elsewhere

LRO_TIMEOUT = 360  # Seconds to wait for LRO completion (6 minutes)

def deploy_agent_engine_app(
    project: str,
    location: str,
    agent_object: Union[reasoning_engines.ReasoningEngine, Type[reasoning_engines.ReasoningEngine]],
    display_name: str,
    labels: Dict[str, str],
    requirements: Optional[List[str]] = None,
    extra_packages: Optional[List[str]] = None,
    # enable_tracing: bool = True, # This seems to be unused in this function
) -> reasoning_engines.ReasoningEngine:
    """Deploys or updates a reasoning engine app."""
    logging.info(f"--- Preparing to deploy/update: {display_name} in {project}/{location} ---")

    validated_extra_packages = []
    if extra_packages:
        for path in extra_packages:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Extra package path not found: {path}")
            validated_extra_packages.append(path)
    logging.info(f"Validated extra packages: {validated_extra_packages}")

    logging.info(f"Looking for existing agent with display name: '{display_name}'")
    remote_agents = reasoning_engines.ReasoningEngine.list(
        project=project, location=location,
        filter=f'display_name="{display_name}"'
    )
    logging.info(f"Found {len(remote_agents)} existing agents matching the display name.")

    try:
        if remote_agents:
            if len(remote_agents) > 1:
                logging.warning(f"Found {len(remote_agents)} agents with display_name='{display_name}'. This indicates a potential name collision. Skipping update for {display_name}.")
                raise RuntimeError(f"Multiple agents found for display_name: {display_name}")

            remote_agent = remote_agents[0]
            logging.info(f"Found existing agent: {remote_agent.name}. Attempting to update it.")

            agent_class = agent_object if inspect.isclass(agent_object) else type(agent_object)
            update_needed = False
            if remote_agent.spec != agent_class:
                 remote_agent.spec = agent_class
                 logging.info(f"Updating spec to: {agent_class}")
                 update_needed = True

            if requirements and remote_agent.requirements != requirements:
                remote_agent.requirements = requirements
                logging.info("Updating requirements.")
                update_needed = True
            if validated_extra_packages and remote_agent.extra_packages != validated_extra_packages:
                remote_agent.extra_packages = validated_extra_packages
                logging.info("Updating extra_packages.")
                update_needed = True

            if update_needed:
                logging.info("Calling remote_agent.update()")
                # The update method on the instance should handle the LRO.
                remote_agent.update(update_mask=["spec", "requirements", "extra_packages"]) # Specify update mask
                logging.info(f"Update operation started. Waiting for completion for {LRO_TIMEOUT} seconds...")
                remote_agent.result(timeout=LRO_TIMEOUT) # Wait for the LRO to complete
                logging.info(f"Agent '{display_name}' ({remote_agent.name}) update LRO finished.")
                remote_agent.refresh() # Refresh to get the latest state
                logging.info(f"Agent state after update: {remote_agent.resource_state}")
            else:
                logging.info(f"No changes detected for agent '{display_name}'. Skipping update.")

            return remote_agent
        else:
            logging.info("No existing agent found. Creating a new one.")
            create_kwargs = {
                "display_name": display_name,
                "labels": labels,
                "spec": agent_object if inspect.isclass(agent_object) else type(agent_object),
            }
            if requirements:
                create_kwargs["requirements"] = requirements
            if validated_extra_packages:
                create_kwargs["extra_packages"] = validated_extra_packages

            logging.info(f"Calling ReasoningEngine.create with keys: {create_kwargs.keys()}")
            new_agent = reasoning_engines.ReasoningEngine.create(**create_kwargs)
            logging.info(f"Create operation started for {new_agent.display_name} ({new_agent.name}). Waiting for completion for {LRO_TIMEOUT} seconds...")
            new_agent.result(timeout=LRO_TIMEOUT) # Wait for the LRO to complete
            logging.info(f"Agent '{display_name}' create LRO finished.")
            new_agent.refresh() # Refresh to get the latest state
            logging.info(f"Agent state after create: {new_agent.resource_state}")
            return new_agent

    except google.api_core.exceptions.GoogleAPICallError as e:
        logging.error(f"!!! API Call error during agent {display_name} deployment: {e}", exc_info=True)
        raise
    except TimeoutError:
        logging.error(f"!!! Timeout waiting for agent {display_name} operation to complete after {LRO_TIMEOUT} seconds.", exc_info=True)
        raise
    except Exception as e:
         logging.error(f"An unexpected error occurred during agent {display_name} deployment: {e}", exc_info=True)
         raise


if __name__ == "__main__":
    # Setup basic logging for the script execution
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    )
    import argparse

    parser = argparse.ArgumentParser(description="Deploy agent engine app to Vertex AI")
    parser.add_argument(
        "--project",
        default=os.environ.get("COMMON_GOOGLE_CLOUD_PROJECT"),
        help="GCP project ID (defaults to COMMON_GOOGLE_CLOUD_PROJECT from .env or application default credentials)",
    )
    parser.add_argument(
        "--location",
        default="us-central1",
        help="GCP region (defaults to us-central1)",
    )
    parser.add_argument(
        "--agent-name",
        default="orchestrate_agent",
        help="Name for the agent engine",
    )
    parser.add_argument(
        "--requirements-file",
        default="./requirements.txt",
        help="Path to requirements.txt file",
    )
    parser.add_argument(
        "--extra-packages",
        nargs="+",
        default=["./app", "./orchestrate", "./common", "./a2a_common-0.1.0-py3-none-any.whl"],
        help="Additional packages to include",
    )
    parser.add_argument(
        "--set-env-vars",
        help="Comma-separated list of environment variables in KEY=VALUE format",
    )
    parser.add_argument(
        "--enable-tracing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable OpenTelemetry tracing via AdkApp and apply custom OTel setup from common.observability",
    )
    args = parser.parse_args()

    # --- Parse and Set Environment Variables ---
    # Parse environment variables if provided
    env_vars = None
    if args.set_env_vars:
        env_vars = {}
        for pair_raw in args.set_env_vars.split(";"): # Use semicolon as the outer delimiter
            pair = pair_raw.strip() # Remove leading/trailing whitespace
            if not pair: # Skip empty pairs (e.g., from double semicolons)
                continue
            try:
                key, value = pair.split("=", 1)
                env_vars[key.strip()] = value # Store with stripped key
                # os.environ[key.strip()] = value # AgentEngineApp handles env_vars
                logging.info(f"Parsed environment variable for agent: {key.strip()}={value}")
            except ValueError:
                # Warn if a pair doesn't contain '='
                logging.warning(f"Skipping invalid environment variable pair: '{pair}'")
    # --- End Parse and Set Environment Variables ---

    if not args.project:
        _, args.project = google.auth.default()

    # --- Initialize Custom OpenTelemetry ---
    # The call to setup_observability is now handled within deploy_agent_engine_app
    # to ensure it runs after AdkApp initializes the TracerProvider.
    if not args.enable_tracing:
        logging.info("AdkApp tracing and custom OpenTelemetry setup skipped.")

    agent_labels = {"agent_id": args.agent_name}

    logging.info("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║   🤖 DEPLOYING AGENT TO VERTEX AI AGENT ENGINE 🤖         ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
