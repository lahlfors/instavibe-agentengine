# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# mypy: disable-error-code="attr-defined"
import datetime
import json
import logging # Keep logging import
import os
from dotenv import load_dotenv
from typing import Any, Dict

import google.auth
import vertexai
import google.api_core.exceptions # For specific exception handling
from google.cloud import logging as google_cloud_logging
from vertexai import agent_engines
from vertexai.preview import reasoning_engines
from agents.app.utils.gcs import create_bucket_if_not_exists
from common.observability import setup_observability
from vertexai.preview.reasoning_engines import AdkApp

# Load environment variables from the root .env file
# This should be among the first imports to ensure variables are available globally.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

GOOGLE_CLOUD_PROJECT = os.environ.get("COMMON_GOOGLE_CLOUD_PROJECT")

def deploy_agent_engine_app(
    project: str,
    location: str,
    agent_object: Any,
    display_name: str,
    labels: Dict[str, str],
    requirements: list[str],
    extra_packages: list[str] = [],
    env_vars: Dict[str, str] | None = None,
    enable_tracing: bool = True,
) -> agent_engines.AgentEngine:
    """Deploys or updates an ADK Agent on Vertex AI Agent Engine using AdkApp."""
    logging.info(f"--- Preparing to deploy/update: {display_name} ---")

    staging_bucket = f"gs://{project}-agent-engine"
    create_bucket_if_not_exists(bucket_name=staging_bucket, project=project, location=location)
    vertexai.init(project=project, location=location, staging_bucket=staging_bucket)

    logging.info(f"Instantiating AdkApp for {display_name} with enable_tracing=False")
    agent_engine = AdkApp(
        agent=agent_object,
        env_vars=env_vars,
        enable_tracing=False,
    )

    agent_config = {
        "display_name": display_name,
        "description": f"Agent: {display_name}",
        "labels": labels,
        "requirements": requirements,
        "extra_packages": extra_packages,
        "spec": agent_engine,
    }
    agent_config.pop('labels', None)
    # ... log_config ...

    try:
        list_filter = f'display_name="{display_name}"'
        logging.info(f"Checking for existing agent with filter: {list_filter}")
        existing_agents = list(agent_engines.list(filter=list_filter))

        if len(existing_agents) > 1:
            logging.warning(f"Found {len(existing_agents)} agents with display_name='{display_name}'. This indicates a potential name collision. Skipping update for {display_name}.")
            raise RuntimeError(f"Multiple agents found for display_name: {display_name}")
        elif existing_agents:
            remote_agent = existing_agents[0]
            logging.info(f"Attempting to update existing agent: {display_name} ({remote_agent.resource_name})")
            remote_agent.spec = agent_engine
            remote_agent.update()
            logging.info(f"Agent '{display_name}' updated successfully.")
        else:
            logging.info(f"Attempting to create new agent: {display_name}")
            remote_agent = reasoning_engines.ReasoningEngine.create(
                **agent_config
            )
            logging.info(f"Agent '{display_name}' created successfully.")

        config = {
            "remote_agent_engine_id": remote_agent.resource_name,
            "deployment_timestamp": datetime.datetime.now().isoformat(),
        }
        config_file = "deployment_metadata.json"

        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        logging.info(f"Agent Engine ID written to {config_file}")

        return remote_agent
    except google.api_core.exceptions.InvalidArgument as e:
         logging.error(f"!!! InvalidArgument error during agent deployment for '{display_name}' ... {e}")
         raise
    except Exception as e:
         logging.error(f"An unexpected error occurred during agent deployment for '{display_name}': {e}", exc_info=True)
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
        default=GOOGLE_CLOUD_PROJECT, # This will now correctly use COMMON_GOOGLE_CLOUD_PROJECT from .env
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
        default=["./app","./orchestrate","./a2a_common-0.1.0-py3-none-any.whl"],
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

    # The following section is commented out because this script is now
    # a generic deployment utility. The actual agent deployment is orchestrated
    # by deploy_all.py, which dynamically loads the agent and calls
    # deploy_agent_engine_app.
    #
    # from orchestrate.agent import root_agent
    # with open(args.requirements_file) as f:
    #     requirements = f.read().strip().split("\n")
    #
    # deploy_agent_engine_app(
    #     project=args.project,
    #     location=args.location,
    #     agent_object=root_agent,
    #     display_name=args.agent_name,
    #     labels=agent_labels, # Pass labels
    #     requirements=requirements,
    #     extra_packages=.extra_packages,
    #     env_vars=env_vars,
    #     enable_tracing=args.enable_tracing,
    # )
