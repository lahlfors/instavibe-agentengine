import os
import asyncio
import uuid
import logging
from typing import Optional, Any, AsyncGenerator
from google.adk.agents import LlmAgent
from google.adk.tools import google_search
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig
from opentelemetry import trace

# Agent Card support for A2A discovery
# Removed inline Agent Card support - now handled by A2aAgent deployment
# from agents.common.secure_a2a import create_planner_agent_card, serve_agent_card_as_query_response
create_planner_agent_card = None
serve_agent_card_as_query_response = None

try:
    from agents.common.observability import setup_observability
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from agents.common.observability import setup_observability

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)

class PlannerAgent(LlmAgent):
    display_name: Optional[str] = None
    otel_collector_endpoint: Optional[str] = None
    model_client: Any = None

    def __post_init__(self):
        super().__post_init__()
        if self.model:
            # Initialize Vertex AI
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "laah-genai")
            location = os.getenv("CLOUD_RUN_REGION", "us-central1")
            vertexai.init(project=project_id, location=location)
            self.model_client = GenerativeModel(self.model)
        else:
            print("WARNING: PlannerAgent initialized without a model name.")

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """This is the main, streaming entry point for the agent."""
        logger.info(f"Entering _run_async_impl for {self.name}")
        
        # Debug logging for tools state
        try:
            logger.info(f"Type of self.tools: {type(self.tools)}")
            logger.info(f"Value of self.tools: {self.tools}")
            if hasattr(self, '_tools'):
                logger.info(f"Type of self._tools: {type(self._tools)}")
                logger.info(f"Value of self._tools: {self._tools}")
            else:
                logger.info("self._tools does not exist")
        except Exception as e:
            logger.error(f"Error inspecting tools: {e}", exc_info=True)
        
        # Extract invocation_id from context
        invocation_id = ctx.invocation_id
        
        if not self.model_client:
            yield Event(
                invocation_id=invocation_id,
                author=self.name, 
                content=types.Content(parts=[types.Part(text="Model client not initialized")])
            )
            return

        # This reuses the single, shared client
        # Extract text from ctx.user_content (google.genai.types) for compatibility 
        # with self.model_client (google.generativeai)
        prompt_text = ""
        if ctx.user_content and ctx.user_content.parts:
            for part in ctx.user_content.parts:
                if hasattr(part, 'text') and part.text:
                    prompt_text += part.text + "\n"
        
        # Configure JSON mode to guarantee structured output
        generation_config = GenerationConfig(
            response_mime_type="application/json",
            temperature=0.7
        )
        
        response = await self.model_client.generate_content_async(
            [prompt_text],  # Vertex AI expects a list
            generation_config=generation_config
        )

        # Debugging logging for TypeError
        try:
            content_obj = response.candidates[0].content
            logger.info(f"Content object type: {type(content_obj)}")
            if hasattr(content_obj, 'parts'):
                logger.info(f"Content parts type: {type(content_obj.parts)}")
                try:
                    logger.info(f"Length of content parts: {len(content_obj.parts)}")
                except TypeError as te:
                    logger.error(f"Error getting len of content.parts: {te}", exc_info=True)
                    logger.info(f"content_obj.parts is: {content_obj.parts}")
                    logger.info(f"dir(content_obj): {dir(content_obj)}")
            else:
                logger.warning("Content object has no 'parts' attribute")

            # Yield the full response event with invocation_id
            yield Event(
                invocation_id=invocation_id,
                author=self.name, 
                content=content_obj
            )
        except Exception as e:
            logger.error(f"Error inspecting response content: {e}", exc_info=True)
            raise

    async def _async_set_up(self, **kwargs):
        logger.info(f"--- Running _async_set_up for {self.__class__.__name__} ---")
        os.environ["OTEL_SERVICE_NAME"] = self.name
        setup_observability(endpoint_override=self.otel_collector_endpoint)
        
        # Initialize model_client if missing (critical for unpickled agents)
        if not self.model_client and self.model:
             logger.info(f"Initializing model_client for {self.model}")
             project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "laah-genai")
             location = os.getenv("CLOUD_RUN_REGION", "us-central1")
             vertexai.init(project=project_id, location=location)
             self.model_client = GenerativeModel(self.model)
              
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

    def query(self, input: str, **kwargs):
        """
        Synchronous wrapper for streaming.
        SDK's inspect module detects 'def' + 'yield' and registers as mode='stream'.
        The 'input' argument is explicitly named so Vertex AI adds it to the API schema.
        """
        # Removed inline Agent Card handling - now served by A2aAgent at .well-known endpoint
        # The A2aAgent deployment automatically exposes the Agent Card
        
        # Normal query processing
        yield f"Planning event: {input}"
        
        with tracer.start_as_current_span("a2a.planner.plan") as span:
            # Simplified: input is now directly a string from the client
            message_text = input

            span.set_attribute("agent.name", self.name)
            span.set_attribute("user.prompt", message_text)
            span.set_attribute("request.data", str(kwargs))
            logger.info(f"Handling plan request: input={message_text} kwargs={kwargs}")

            try:
                # Use asyncio.run() to bridge sync to async safely
                # This handles loop creation/cleanup automatically and is safer in threaded contexts
                
                # Create invocation context from kwargs
                ctx = InvocationContext(
                    user_content=types.Content(parts=[types.Part(text=message_text)]),
                    session=None,
                    invocation_id=str(uuid.uuid4()),
                    metadata=kwargs
                )
                
                async def run_and_collect():
                    events = []
                    async for event in self._run_async_impl(ctx):
                        events.append(event)
                    return events

                # Run the async generator and collect all events
                # Note: This collects all events in memory before yielding. 
                # For true streaming in sync context, we'd need a different approach, 
                # but asyncio.run is blocking anyway.
                events = asyncio.run(run_and_collect())
                
                for event in events:
                    yield event
                
                span.set_status(trace.StatusCode.OK)
                    
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.StatusCode.ERROR, str(e))
                logger.error(f"Error in query: {e}", exc_info=True)
                raise

def create_agent(model: str):
    logger.info(f"[PLANNER] create_agent called with model={model}")
    print(f"[PLANNER DEBUG] create_agent called with model={model}")
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
print(f"[PLANNER MODULE] Creating root_agent with model={gemini_model}")
logger.info(f"[PLANNER MODULE] Creating root_agent with model={gemini_model}")
root_agent = create_agent(model=gemini_model)
