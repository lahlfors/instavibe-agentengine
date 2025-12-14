"""
Agent Card wrapper for Social Agent.

This module adds A2A Agent Card support to the existing Social Agent
without modifying the core agent logic.
"""

import logging
from typing import Any
from agents.social.agent import root_agent as social_agent
from agents.common.secure_a2a import create_social_agent_card, serve_agent_card_as_query_response

logger = logging.getLogger(__name__)

# Create the Agent Card
SOCIAL_AGENT_CARD = create_social_agent_card()


class SocialAgentWithCard:
    """
    Wrapper that adds Agent Card support to the Social Agent.
    
    This allows the agent to respond to A2A discovery requests
    while maintaining all existing functionality.
    """
    
    def __init__(self, **kwargs):
        self.agent = social_agent
        self._kwargs = kwargs
        
    def query(self, input: str = "", **kwargs) -> Any:
        """
        Enhanced query method with Agent Card support.
        
        If the request is for the Agent Card (via ?get_agent_card parameter),
        returns the card. Otherwise, delegates to the underlying agent.
        """
        # Check if this is an Agent Card request
        if kwargs.get('get_agent_card') or input == "GET_AGENT_CARD":
            logger.info("Returning Agent Card for Social Agent")
            return serve_agent_card_as_query_response(SOCIAL_AGENT_CARD)
        
        # Otherwise, delegate to the real agent
        return self.agent.query(**kwargs)
    
    def set_up(self, **kwargs):
        """Delegate setup to underlying agent."""
        return self.agent.set_up(**kwargs)
    
    def __getattr__(self, name):
        """Proxy all other attributes to the underlying agent."""
        return getattr(self.agent, name)


# Export the class for deployment (deploy_all.py will instantiate it) 
root_agent = SocialAgentWithCard
