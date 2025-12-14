"""
Agent Card wrapper for Platform MCP Client Agent.

This module adds A2A Agent Card support to the existing Platform MCP Client Agent
without modifying the core agent logic. The Agent Card is dynamically generated
based on loaded MCP tools.
"""

import logging
from typing import Any
from agents.platform_mcp_client.agent import root_agent as platform_agent
from agents.common.secure_a2a import create_platform_agent_card, serve_agent_card_as_query_response

logger = logging.getLogger(__name__)


class PlatformAgentWithCard:
    """
    Wrapper that adds Agent Card support to the Platform MCP Client Agent.
    
    This allows the agent to respond to A2A discovery requests with
    a dynamically-generated card based on currently loaded MCP tools.
    """
    
    def __init__(self, **kwargs):
        self.agent = platform_agent
        self._kwargs = kwargs
        
    def query(self, input: str = "", **kwargs) -> Any:
        """
        Enhanced query method with Agent Card support.
        
        If the request is for the Agent Card (via ?get_agent_card parameter),
        generates and returns the card based on current MCP tools.
        Otherwise, delegates to the underlying agent.
        """
        # Check if this is an Agent Card request
        if kwargs.get('get_agent_card') or input == "GET_AGENT_CARD":
            logger.info("Generating dynamic Agent Card for Platform MCP Client Agent")
            
            # Get currently loaded MCP tools
            mcp_tools = getattr(self.agent, '_mcp_tools', None)
            
            # Generate card dynamically
            card = create_platform_agent_card(mcp_tools)
            
            return serve_agent_card_as_query_response(card)
        
        # Otherwise, delegate to the real agent
        return self.agent.query(input=input, **kwargs)
    
    def set_up(self, **kwargs):
        """Delegate setup to underlying agent."""
        return self.agent.set_up(**kwargs)
    
    def __getattr__(self, name):
        """Proxy all other attributes to the underlying agent."""
        return getattr(self.agent, name)


# Export the class for deployment (deploy_all.py will instantiate it)
root_agent = PlatformAgentWithCard
