import os
import asyncio
from google.adk.agents import LlmAgent
from google.adk.tools import google_search
from opentelemetry import trace
from common.observability import setup_observability
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
        response = await self.model_client.generate_content_async(prompt_content)

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
        with tracer.start_as_current_span("a2a.planner.plan") as span:
            span.set_attribute("agent.name", self.name)
            span.set_attribute("user.prompt", kwargs.get("message", ""))
            span.set_attribute("request.data", str(kwargs))
            logger.info(f"Handling plan request: {kwargs}")

            try:
                response = super().__call__(**kwargs)
                span.set_attribute("agent.final_response", str(response))
                span.set_attribute("response.data", str(response))
                span.set_status(trace.StatusCode.OK)
                return response
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.StatusCode.ERROR, str(e))
                raise

def create_agent(model: str):
    AGENT_NAME = "planner_agent"
    AGENT_INSTRUCTION = '''

            You are a specialized AI assistant tasked with generating creative and fun plan suggestions.

            **Request:**
            For the upcoming weekend, specifically from **[START_DATE_YYYY-MM-DD]** to **[END_DATE_YYYY-MM-DD]**, in the location specified as **[TARGET_LOCATION_NAME_OR_CITY_STATE]** (if latitude/longitude are provided, use these: Lat: **[TARGET_LATITUDE]**, Lon: **[TARGET_LONGITUDE]**), please generate **[NUMBER_OF_PLANS_TO_GENERATE, e.g., 3]** distinct planning suggestions.

            **Constraints and Guidelines for Suggestions:**
            1.  **Creativity & Fun:** Plans should be engaging, memorable, and offer a good experience for a date.
            2.  **Budget:** All generated plans should aim for a moderate budget (conceptually "$$"), meaning they should be affordable yet offer good value, without being overly cheap or extravagant. This budget level should be *reflected in the choice of activities and venues*, but **do not** explicitly state "Budget: $$" in the `plan_description`.
            3.  **Interest Alignment:**
                *   Consider the following user interests: **[COMMA_SEPARATED_LIST_OF_INTERESTS, e.g., outdoors, arts & culture, foodie, nightlife, unique local events, live music, active/sports]**. Tailor suggestions specifically to these where possible. The plan should *embody* these interests.
                *   **Fallback:** If specific events or venues perfectly matching all listed user interests cannot be found for the specified weekend, you should create a creative and fun generic dating plan that is still appealing, suitable for the location, and adheres to the moderate budget. This plan should still sound exciting and fun, even if it's more general.
            4.  **Current & Specific:** Prioritize finding specific, current events, festivals, pop-ups, or unique local venues operating or happening during the specified weekend dates. If exact current events cannot be found, suggest appealing evergreen options or implement the fallback generic plan.
            5.  **Location Details:** For each place or event mentioned within a plan, you MUST provide its name, precise latitude, precise longitude, and a brief, helpful description.

            **Output Format:**
            Return your response *exclusively* as a single JSON object. This object should contain a top-level key, "fun_plans", which holds a plan objects. Each plan object in the list must strictly adhere to the following structure:

            --json--
            {
              "plan_description": "A summary of the overall plan, consisting of **exactly three sentences**. Craft these sentences in a friendly, enthusiastic, and conversational tone, as if you're suggesting this awesome idea to a close friend. Make it sound exciting and personal, highlighting the positive aspects and appeal of the plan without explicitly mentioning budget or listing interest categories.",
              "locations_and_activities": [
                  {
                  "name": "Name of the specific place or event",
                  "latitude": 0.000000,  // Replace with actual latitude
                  "longitude": 0.000000, // Replace with actual longitude
                  "description": "A brief description of this place/event, why it's suitable for a date, and any specific details for the weekend (e.g., opening hours, event time)."
                  }
                  // Add more location/activity objects here if the plan involves multiple stops/parts
              ]
            }

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
