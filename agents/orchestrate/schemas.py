"""
Schema definitions for Agent-to-Agent communication.

Defines Pydantic models for input/output validation when communicating
with specialist agents via the A2A protocol.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Any


class PlannerInput(BaseModel):
    """Input schema for the Planner Agent."""
    user_request: str = Field(description="The user's event planning request")
    num_friends: Optional[int] = Field(default=None, description="Number of friends attending")
    location: Optional[str] = Field(default=None, description="Preferred location or city")


class Venue(BaseModel):
    """A venue in an event plan."""
    name: str
    address: str
    latitude: float
    longitude: float
    description: Optional[str] = None


class PlannerOutput(BaseModel):
    """Output schema for the Planner Agent."""
    event_title: str = Field(description="Title of the planned event")
    description: str = Field(description="Description of the event")
    venues: List[Venue] = Field(description="List of venues in the plan")
    invite_message: str = Field(description="Suggested invite message")


class SocialInput(BaseModel):
    """Input schema for the Social Agent."""
    user_id: str = Field(description="ID of the user to analyze")
    include_friends: bool = Field(default=True, description="Whether to include friend list")
    include_events: bool = Field(default=True, description="Whether to include event history")


class SocialOutput(BaseModel):
    """Output schema for the Social Agent."""
    user_name: str
    friend_count: int
    recent_posts: List[str]
    attended_events: List[str]
    summary: str = Field(description="Summary of social activity")


class PlatformInput(BaseModel):
    """Input schema for the Platform MCP Client Agent."""
    query: str = Field(description="Natural language query for the platform tools")


class PlatformOutput(BaseModel):
    """Output schema for the Platform MCP Client Agent."""
    response: str = Field(description="Response from the platform tools")
    tool_calls: Optional[List[Any]] = Field(default=None, description="List of tool calls made")
