"""
Agent Card wrapper for Planner Agent.

This module adds A2A Agent Card support to the existing Planner Agent
without modifying the core agent logic.
"""

import logging
from typing import Any, Dict
from agents.planner.agent import root_agent as planner_agent
from agents.common.secure_a2a import create_planner_agent_card, serve_agent_card_as_query_response

logger = logging.getLogger(__name__)

# Create the Agent Card
PLANNER_AGENT_CARD = create_planner_agent_card()


class PlannerAgentWithCard:
    """
    Wrapper that adds Agent Card support to the Planner Agent.
    
    This allows the agent to respond to A2A discovery requests
    while maintaining all existing functionality.
    """
    
    def __init__(self, **kwargs):
        # NOTE: We don't instantiate planner_agent instance here
        # The wrapper IS the agent as far as Vertex AI is concerned
        # We just store the underlying agent reference
        self.agent = planner_agent
        self._kwargs = kwargs  # Store for future use if needed
        
    def query(self, input: str = "", **kwargs) -> Any:
        """
        Enhanced query method with Agent Card support.
        
        If the request is for the Agent Card (via ?get_agent_card parameter),
        returns the card. Otherwise, delegates to the underlying agent.
        """
        # Check if this is an Agent Card request
        if kwargs.get('get_agent_card') or input == "GET_AGENT_CARD":
            logger.info("Returning Agent Card for Planner Agent")
            return serve_agent_card_as_query_response(PLANNER_AGENT_CARD)
        
        # Otherwise, delegate to the real agent
        return self.agent.query(input=input, **kwargs)
    
    def set_up(self, **kwargs):
        """Delegate setup to underlying agent."""
        return self.agent.set_up(**kwargs)
    
    def __getattr__(self, name):
        """Proxy all other attributes to the underlying agent."""
        return getattr(self.agent, name)


# Export the class for deployment (deploy_all.py will instantiate it)
root_agent = PlannerAgentWithCard
