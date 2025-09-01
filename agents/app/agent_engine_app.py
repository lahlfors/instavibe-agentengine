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
import inspect
import logging # Keep logging import
import os
from dotenv import load_dotenv
from typing import Any, Dict, List, Optional, Type, Union

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
    agent_object: Union[reasoning_engines.ReasoningEngine, Type[reasoning_engines.ReasoningEngine]],
    display_name: str,
    labels: Dict[str, str],
    requirements: Optional[List[str]] = None,
    extra_packages: Optional[List[str]] = None,
    enable_tracing: bool = True,
) -> reasoning_engines.ReasoningEngine:
    """Deploys or updates a reasoning engine app."""
    logging.info(f"Looking for existing agent with display name: {display_name}")
    remote_agents = reasoning_engines.ReasoningEngine.list(
        project=project, location=location,
        filter=f'display_name="{display_name}"'
    )

    validated_extra_packages = []
    if extra_packages:
        for path in extra_packages:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Extra package path not found: {path}")
            validated_extra_packages.append(path)

    if remote_agents:
        remote_agent = remote_agents[0]
        logging.info(f"Found existing agent: {remote_agent.name}. Updating it.")

        # IMPORTANT: You can't update labels. They are immutable.
        # We only update the spec and packages.
        if inspect.isclass(agent_object):
            remote_agent.spec = agent_object
        else:
            remote_agent.spec = type(agent_object)

        if requirements:
            remote_agent.requirements = requirements
        if validated_extra_packages:
            remote_agent.extra_packages = validated_extra_packages

        # Call update with no arguments.
        remote_agent.update()
        return remote_agent
    else:
        logging.info("No existing agent found. Creating a new one.")
        # IMPORTANT: Pass labels ONLY during creation.
        create_kwargs = {
            "display_name": display_name,
            "labels": labels,
            "spec": agent_object if inspect.isclass(agent_object) else type(agent_object),
        }
        if requirements:
            create_kwargs["requirements"] = requirements
        if validated_extra_packages:
            create_kwargs["extra_packages"] = validated_extra_packages

        return reasoning_engines.ReasoningEngine.create(**create_kwargs)


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
