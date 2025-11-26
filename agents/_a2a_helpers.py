# agents/_a2a_helpers.py
"""Utility helpers for creating remote A2A agents.

This module centralises the construction of :class:`PicklableRemoteA2aAgent` objects
so that transport configuration, client factory creation and any future authentication
logic live in a single place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from a2a.client import ClientConfig
from a2a.types import TransportProtocol
from agents.orchestrate.picklable_a2a_wrappers import PicklableRemoteA2aAgent, PicklableClientFactory


@dataclass
class RemoteAgentConfig:
    """Configuration for a remote A2A‑enabled agent.

    The URLs can be supplied via environment variables or a JSON config file.
    ``resource_name`` is the A2A resource identifier (e.g. ``projects/.../agents/...``).
    """

    resource_name: str
    # Future fields such as auth tokens can be added here.

    @classmethod
    def from_env(cls, env_var: str) -> "RemoteAgentConfig":
        """Load the resource name from an environment variable.

        ``env_var`` is the name of the environment variable that holds the A2A address.
        If the variable is missing or empty, a ``ValueError`` is raised – this makes the
        orchestrator fail fast during start‑up rather than silently using a ``None`` URL.
        """
        url = os.getenv(env_var, "")
        if not url:
            raise ValueError(f"Environment variable {env_var} is not set or empty.")
        return cls(resource_name=url)


def make_remote_agent(config: RemoteAgentConfig) -> PicklableRemoteA2aAgent:
    """Factory that returns a ready‑to‑use ``PicklableRemoteA2aAgent``.

    The function creates a ``PicklableClientFactory`` with HTTP transport – the same
    configuration used throughout the codebase – and then builds the remote agent.
    """
    client_factory = PicklableClientFactory(
        ClientConfig(
            supported_transports=[TransportProtocol.http_json],
            httpx_client=None,  # lazy initialisation for picklability
        )
    )
    return PicklableRemoteA2aAgent(
        name="remote_agent",  # Generic name as this helper seems unused/generic
        agent_card=config.resource_name,
        a2a_client_factory=client_factory
    )
