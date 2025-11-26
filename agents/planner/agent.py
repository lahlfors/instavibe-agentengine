import os
import asyncio
from google.adk.agents import LlmAgent
from google.adk.tools import google_search
from opentelemetry import trace
try:
    from agents.common.observability import setup_observability
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from agents.common.observability import setup_observability
import logging
from google.generativeai import GenerativeModel # Added import
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from typing import AsyncGenerator
from google.genai import types
tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)

from typing import Optional, Any

class PlannerAgent(LlmAgent):
    display_name: Optional[str] = None
    otel_collector_endpoint: Optional[str] = None
    model_client: Any = None

    def __post_init__(self):
        super().__post_init__()
        if self.model:
            self.model_client = GenerativeModel(self.model)
        else:
            print("WARNING: PlannerAgent initialized without a model name.")

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """This is the main, streaming entry point for the agent."""
        if not self.model_client:
            yield Event(author=self.name, content=types.Content(parts=[types.Part(text="Model client not initialized")]))
            return

        # This reuses the single, shared client
        prompt_content = ctx.user_content
        
        # Configure JSON mode to guarantee structured output
        from google.genai.types import GenerateContentConfig
        
        generation_config = GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.7
        )
        
        response = await self.model_client.generate_content_async(
            prompt_content,
            config=generation_config
        )

        # Yield the full response event
        yield Event(author=self.name, content=response.candidates[0].content)

    async def __async_set_up(self, **kwargs):
        logger.info(f"--- Running _async_set_up for {self.__class__.__name__} ---")
        os.environ["OTEL_SERVICE_NAME"] = self.name
        setup_observability(endpoint_override=self.otel_collector_endpoint)
        logger.info(f"{self.__class__.__name__} async setup complete.")

    def set_up(self, **kwargs):
        """A synchronous wrapper for the async setup."""
        logger.info(f"Sync set_up called for {self.__class__.__name__}")
        try:
            asyncio.run(self._async_set_up(**kwargs))
            logger.info(f"set_up completed for {self.__class__.__name__}.")
        except Exception as e:
            logger.error(f"Error during set_up for {self.__class__.__name__}: {e}", exc_info=True)
            raise
        return self

    def query(self, **kwargs):
        """
        Synchronous wrapper for streaming.
        SDK's inspect module detects 'def' + 'yield' and registers as mode='stream'.
        """
        with tracer.start_as_current_span("a2a.planner.plan") as span:
            span.set_attribute("agent.name", self.name)
            span.set_attribute("user.prompt", kwargs.get("message", ""))
            span.set_attribute("request.data", str(kwargs))
            logger.info(f"Handling plan request: {kwargs}")

            try:
                # Create event loop for bridging async to sync
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Create invocation context from kwargs
                    # LlmAgent's __call__ creates this, we need to replicate it
                    ctx = InvocationContext(
                        user_content=types.Content(parts=[types.Part(text=kwargs.get("message", ""))]),
                        session=None,
                        metadata=kwargs
                    )
                    
                    # Get the async generator from _run_async_impl
                    async_gen = self._run_async_impl(ctx)
                    
                    # Bridge: synchronously iterate over async generator and yield events
                    while True:
                        try:
                            event = loop.run_until_complete(async_gen.__anext__())
                            # Yield the event for streaming
                            yield event
                        except StopAsyncIteration:
                            break
                    
                    span.set_status(trace.StatusCode.OK)
                    
                finally:
                    loop.close()
                    
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.StatusCode.ERROR, str(e))
                logger.error(f"Error in query: {e}", exc_info=True)
                raise

def create_agent(model: str):
    AGENT_NAME = "planner_agent"
    AGENT_INSTRUCTION = '''
You are a specialized event planning agent that creates fun, personalized plans.

**Input Format:**
You receive structured requests in this format:
```
CREATE EVENT PLAN

USER_NAME: <name>
FRIENDS: <comma-separated friend names>
DATE: <YYYY-MM-DD>
LOCATION: <city or preference>
```

**Your Task:**
Create a complete event plan as JSON. The JSON mode is enabled, so your response MUST be valid JSON.

**Required JSON Structure:**
{
  "event_name": "Catchy event title (e.g., 'Sarah's Seattle Adventure')",
  "event_description": "2-3 enthusiastic sentences describing the plan",
  "friends_name_list": ["Friend1", "Friend2", "Friend3"],
  "locations_and_activities": [
    {
      "name": "Specific venue name",
      "address": "Complete street address",
      "latitude": 47.608013,
      "longitude": -122.335167,
      "description": "Why this venue fits the plan and what they'll do here"
    }
  ],
  "post_to_go_out": "Casual, exciting 2-3 sentence invite message for the group"
}

**Planning Guidelines:**
1. **Make Assumptions**: Work with the info provided - don't ask questions
2. **Moderate Budget**: Assume $$ range unless location suggests otherwise  
3. **2-4 Venues**: Include dinner + activity/entertainment + optional nightcap
4. **Real Places**: Use actual venues when possible, or realistic generic options
5. **Accurate Coordinates**: Lat/long should be approximately correct for the area
6. **Group-Friendly**: Suitable for friends hanging out together
7. **Date-Aware**: Consider day of week, holidays, seasons

**Examples:**

Input: "USER_NAME: Alice, FRIENDS: Bob, Charlie, DATE: 2025-12-05, LOCATION: Boston"
Output JSON:
{
  "event_name": "Alice's Boston Night Out",
  "event_description": "An amazing evening exploring Boston's North End food scene and live music! Start with authentic Italian at Giacomo's, then head to The Sinclair for local bands and craft cocktails.",
  "friends_name_list": ["Bob", "Charlie"],
  "locations_and_activities": [
    {
      "name": "Giacomo's Ristorante",
      "address": "355 Hanover St, Boston, MA 02113",
      "latitude": 42.365147,
      "longitude": -71.054035,
      "description": "Legendary North End Italian spot famous for seafood pasta - perfect for kicking off the night"
    },
    {
      "name": "The Sinclair",
      "address": "52 Church St, Cambridge, MA 02138",
      "latitude": 42.374356,
      "longitude": -71.119170,
      "description": "Harvard Square music venue with great indie/rock shows and a full bar"
    }
  ],
  "post_to_go_out": "Hey Bob and Charlie! Epic Boston night planned for Dec 5th - Italian feast at Giacomo's followed by live music at The Sinclair. Who's in?"
}

**Remember:**
- JSON mode is ON - output MUST be valid JSON
- Never ask clarifying questions - create a plan with what you have
- Be enthusiastic and specific
'''


    return PlannerAgent(
        name=AGENT_NAME,
        model=model,
        description="Agent that creates plans",
        instruction=AGENT_INSTRUCTION,
        tools=[google_search]
    )

gemini_model = os.getenv("COMMON_GEMINI_MODEL", "gemini-2.5-flash")
root_agent = create_agent(model=gemini_model)
