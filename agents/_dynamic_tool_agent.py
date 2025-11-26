# agents/_dynamic_tool_agent.py
"""Base class for agents that load their tools dynamically.

The original ``PlatformMCPClientAgent`` fetched its toolset from an MCP server
inside its ``__async_set_up`` method.  By extracting that behaviour into a
shared base we can reuse the same pattern for any future agents that need
runtime‑loaded tools (e.g., a future analytics agent).
"""

from __future__ import annotations

from typing import Any, List

from google.adk.agents import Agent
from pydantic import PrivateAttr


class DynamicToolAgent(Agent):
    """Agent subclass that provides a ``tools`` property backed by a private list.

    Sub‑classes should implement an async ``_load_tools`` method that populates
    ``self._dynamic_tools``.  The base class supplies a ``tools`` getter that the
    ADK runtime uses when routing calls.
    """

    _dynamic_tools: List[Any] = PrivateAttr(default_factory=list)

    @property
    def tools(self) -> List[Any]:
        """Expose the dynamically loaded tools to the ADK framework."""
        return self._dynamic_tools

    async def _load_tools(self) -> None:
        """Placeholder – concrete agents must override this to populate tools.

        The default implementation does nothing, which is safe for agents that
        do not require dynamic tooling.
        """
        return None
