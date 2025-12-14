"""
Secure Agent-to-Agent (A2A) Communication Infrastructure

This module provides production-grade components for secure A2A communication
on Vertex AI Agent Engine, implementing the patterns from Google's A2A protocol
with enterprise-ready authentication, lazy loading, and observability.

Key Components:
- GoogleAuthRefresh: Auto-refreshing OIDC auth handler
- LazyAuthClientFactory: Picklable client factory with JIT initialization
- SecureRemoteA2aAgent: High-level wrapper for A2A client agents with dynamic card discovery

Usage:
    from agents.common.secure_a2a import SecureRemoteA2aAgent
    
    planner = SecureRemoteA2aAgent(
        name="planner_agent",
        description="Creates event plans",
        agent_card_url="https://planner-agent.../.well-known/agent.json"
    )
"""

from .auth_handler import GoogleAuthRefresh
from .client_factory import LazyAuthClientFactory
from .secure_agent import SecureRemoteA2aAgent
from .retry import invoke_with_retry, CircuitBreaker

__all__ = [
    'GoogleAuthRefresh',
    'LazyAuthClientFactory',
    'SecureRemoteA2aAgent',
    'invoke_with_retry',
    'CircuitBreaker',
]
