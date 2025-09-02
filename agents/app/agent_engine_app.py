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
# from vertexai import agent_engines # This seems to be for the older Agent Engine
from vertexai.preview import reasoning_engines
from agents.app.utils.gcs import create_bucket_if_not_exists
# from common.observability import setup_observability # Assuming this is handled elsewhere

LRO_TIMEOUT = 360  # Seconds to wait for LRO completion (6 minutes)

def deploy_agent_engine_app(
    project: str,
    location: str,
    agent_object: Any, # Your actual agent class or instance
    display_name: str,
    labels: Dict[str, str], # Labels will be ignored in create/update calls
    requirements: Optional[List[str]] = None,
    extra_packages: Optional[List[str]] = None,
) -> reasoning_engines.ReasoningEngine:
    """Deploys or updates a Vertex AI Reasoning Engine."""
    logging.info(f"--- Preparing to deploy/update Reasoning Engine: {display_name} in {project}/{location} ---")

    # vertexai.init(project=project, location=location) # Usually init once at the start of deploy_all.py

    validated_extra_packages = []
    if extra_packages:
        for path in extra_packages:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Extra package path not found: {path}")
            validated_extra_packages.append(path)
    logging.info(f"Validated extra packages: {validated_extra_packages}")

    logging.info(f"Looking for existing Reasoning Engine with display name: '{display_name}'")
    remote_agents = reasoning_engines.ReasoningEngine.list(
        project=project, location=location,
        filter=f'display_name="{display_name}"'
    )
    logging.info(f"Found {len(remote_agents)} existing engines matching the display name.")

    try:
        if remote_agents:
            if len(remote_agents) > 1:
                logging.warning(f"Found {len(remote_agents)} engines with display_name='{display_name}'. Skipping update.")
                raise RuntimeError(f"Multiple engines found for display_name: {display_name}")

            remote_agent = remote_agents[0]
            logging.info(f"Found existing Reasoning Engine: {remote_agent.name} ({remote_agent.display_name}). Attempting to update.")

            # Prepare update arguments
            update_kwargs = {
                "reasoning_engine": agent_object,
                "requirements": requirements,
                "extra_packages": validated_extra_packages,
                "display_name": display_name,
                # "labels": labels, # --- Temporarily removed ---
            }
            # Remove keys with None values to avoid overwriting existing values unexpectedly
            update_kwargs = {k: v for k, v in update_kwargs.items() if v is not None}

            if not update_kwargs:
                 logging.info("No updates to apply.")
                 return remote_agent

            logging.info(f"Calling remote_agent.update() with keys: {update_kwargs.keys()}")
            updated_agent = remote_agent.update(**update_kwargs)
            logging.info(f"Update operation started. Waiting for completion for {LRO_TIMEOUT} seconds...")
            updated_agent.result(timeout=LRO_TIMEOUT)
            logging.info(f"Engine '{display_name}' ({updated_agent.name}) update LRO finished.")
            updated_agent.refresh()
            logging.info(f"Engine state after update: {updated_agent.resource_state}")
            return updated_agent
        else:
            logging.info("No existing Reasoning Engine found. Creating a new one.")
            create_kwargs = {
                "reasoning_engine": agent_object, # Use 'reasoning_engine' not 'spec'
                "display_name": display_name,
                # "labels": labels, # --- Temporarily removed ---
            }
            if requirements:
                create_kwargs["requirements"] = requirements
            if validated_extra_packages:
                create_kwargs["extra_packages"] = validated_extra_packages

            logging.info(f"Calling ReasoningEngine.create with keys: {create_kwargs.keys()}")
            new_agent = reasoning_engines.ReasoningEngine.create(**create_kwargs)
            logging.info(f"Create operation started for {new_agent.display_name} ({new_agent.name}). Waiting for completion for {LRO_TIMEOUT} seconds...")
            new_agent.result(timeout=LRO_TIMEOUT)
            logging.info(f"Engine '{display_name}' create LRO finished.")
            new_agent.refresh()
            logging.info(f"Engine state after create: {new_agent.resource_state}")
            return new_agent

    except google.api_core.exceptions.GoogleAPICallError as e:
        logging.error(f"!!! API Call error during Reasoning Engine {display_name} deployment: {e}", exc_info=True)
        raise
    except TimeoutError:
        logging.error(f"!!! Timeout waiting for Reasoning Engine {display_name} operation to complete after {LRO_TIMEOUT} seconds.", exc_info=True)
        raise
    except Exception as e:
         logging.error(f"An unexpected error occurred during Reasoning Engine {display_name} deployment: {e}", exc_info=True)
         raise
