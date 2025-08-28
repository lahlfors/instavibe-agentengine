import os
import logging
import asyncio
from dotenv import load_dotenv
from typing import Any, Dict, Optional, AsyncGenerator
from pydantic import BaseModel
from google.adk.agents import LoopAgent, LlmAgent, BaseAgent
from google.adk.tools import Tool
from .instavibe import get_person_posts,get_person_friends,get_person_id_by_name,get_person_attended_events
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from google.adk.agents.callback_context import CallbackContext
from opentelemetry import trace
import sys
sys.path.append('.')
from common.observability import setup_observability
setup_observability(service_name="social-agent")

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
tracer = trace.get_tracer(__name__)
log = logging.getLogger(__name__)

class GetPersonPostsArgs(BaseModel):
    person_id: str

class GetPersonFriendsArgs(BaseModel):
    person_id: str

class GetPersonIdByNameArgs(BaseModel):
    name: str

class GetPersonAttendedEventsArgs(BaseModel):
    person_id: str

class SocialAgent(LoopAgent):
    """An agent that handles social profile analysis."""

    def __init__(self, name: str = "social-agent") -> None:
        super().__init__(
            name=name,
            description="Find everyone's social profile on events, post and friends",
            max_iterations=10,
            after_agent_callback=self.modify_output_after_agent
        )
        self.sub_agents = self._create_sub_agents()

    def _create_sub_agents(self) -> list:
        profile_agent = LlmAgent(
            name="profile_agent",
            model="gemini-2.0-flash-001",
            description=(
                "Agent to answer questions about the this person's social profile. User will ask person's profile using their name, make sure to fetch the id before getting other data."
            ),
            instruction=(
                "You are a helpful agent who can answer user questions about this person's social profile."
            ),
            tools=[
                Tool(
                    name="get_person_posts",
                    function=get_person_posts,
                    description="Get posts by a person.",
                    args_schema=GetPersonPostsArgs,
                ),
                Tool(
                    name="get_person_friends",
                    function=get_person_friends,
                    description="Get friends of a person.",
                    args_schema=GetPersonFriendsArgs,
                ),
                Tool(
                    name="get_person_id_by_name",
                    function=get_person_id_by_name,
                    description="Get person ID by name.",
                    args_schema=GetPersonIdByNameArgs,
                ),
                Tool(
                    name="get_person_attended_events",
                    function=get_person_attended_events,
                    description="Get events attended by a person.",
                    args_schema=GetPersonAttendedEventsArgs,
                ),
            ]
        )

        summary_agent = LlmAgent(
            name="summary_agent",
            model="gemini-2.0-flash-001",
            description=(
                "Generate a comprehensive social summary as a single, cohesive paragraph. This summary should cover the activities, posts, friend networks, and event participation of one or more individuals. If multiple profiles are analyzed, the paragraph must also identify and integrate any common ground found between them."
            ),
            instruction=(
                """
                Your primary task is to synthesize social profile information into a single, comprehensive paragraph.

                    **Input Scope & Default Behavior:**
                    *   If specific individuals are named by the user, focus your analysis on them.
                    *   **If no individuals are specified, or if the request is general, assume the user wants an analysis of *all relevant profiles available in the current dataset/context*.**

                    **For each profile (whether specified or determined by default), you must analyze:**

                    1.  **Post Analysis:**
                        *   Systematically review their posts (e.g., content, topics, frequency, engagement).
                        *   Identify recurring themes, primary interests, and expressed sentiments.

                    2.  **Friendship Relationship Analysis:**
                        *   Examine their connections/friends list.
                        *   Identify key relationships, mutual friends (especially if comparing multiple profiles), and the general structure of their social network.

                    3.  **Event Participation Analysis:**
                        *   Investigate their past (and if available, upcoming) event participation.
                        *   Note the types of events, frequency of attendance, and any notable roles (e.g., organizer, speaker).

                    **Output Generation (Single Paragraph):**

                    *   **Your entire output must be a single, cohesive summary paragraph.**
                        *   **If analyzing a single profile:** This paragraph will detail their activities, interests, and social connections based on the post, friend, and event analysis.
                        *   **If analyzing multiple profiles:** This paragraph will synthesize the key findings regarding posts, friends, and events for each individual. Crucially, it must then seamlessly integrate or conclude with an identification and description of the common ground found between them (e.g., shared interests from posts, overlapping event attendance, mutual friends). The aim is a unified narrative within this single paragraph.

                    **Key Considerations:**
                    *   Base your summary strictly on the available data.
                    *   If data for a specific category (posts, friends, events) is missing or sparse for a profile, you may briefly acknowledge this within the narrative if relevant.
                        """
                ),
            output_key="summary"
        )

        check_agent = LlmAgent(
            name="check_agent",
            model="gemini-2.0-flash-001",
            description=(
                "Check if everyone's social profile are summarized and has been generated. Output 'completed' or 'pending'."
            ),
            output_key="summary_status"
        )

        class CheckCondition(BaseAgent):
            async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
                log.info(f"Summary: {ctx.session.state.get('summary')}")

                status = ctx.session.state.get("summary_status", "fail").strip()
                is_done = (status == "completed")

                yield Event(author=self.name, actions=EventActions(escalate=is_done))

        return [
            profile_agent,
            summary_agent,
            check_agent,
            CheckCondition(name="Checker")
        ]

    def modify_output_after_agent(self, callback_context: CallbackContext) -> Optional[types.Content]:
        agent_name = callback_context.agent_name
        invocation_id = callback_context.invocation_id
        current_state = callback_context.state.to_dict()
        current_user_content = callback_context.user_content
        print(f"[Callback] Exiting agent: {agent_name} (Inv: {invocation_id})")
        print(f"[Callback] Current summary_status: {current_state.get('summary_status')}")
        print(f"[Callback] Current Content: {current_user_content}")

        status = current_state.get("summary_status").strip()
        is_done = (status == "completed")

        final_summary = current_state.get("summary")
        print(f"[Callback] final_summary: {final_summary}")
        if final_summary and is_done and isinstance(final_summary, str):
            log.info(f"[Callback] Found final summary, constructing output Content.")
            return types.Content(role="model", parts=[types.Part(text=final_summary.strip())])
        else:
            log.warning("[Callback] No final summary found in state or it's not a string.")
            return None
