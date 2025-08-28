import os
import logging
import asyncio
from dotenv import load_dotenv
from typing import Any, Dict, Optional, AsyncGenerator
from google.adk.agents import LlmAgent, InvocationContext
from google.adk.events import Event
from google.adk.tools import google_search
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
import sys
sys.path.append('.')
from common.observability import setup_observability
setup_observability(service_name="planner_agent")

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
tracer = trace.get_tracer(__name__)

class PlannerAgent(LlmAgent):
    """An agent that helps users plan a night out."""

    def __init__(self, name: str = "planner_agent") -> None:
        super().__init__(
            name=name,
            model="gemini-2.0-flash-001",
            description="Agent tasked with generating creative and fun event plan suggestions",
            instruction="""

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

        """,
            tools=[google_search]
        )

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        with tracer.start_as_current_span("PlannerAgent.run") as span:
            try:
                async for event in super()._run_async_impl(ctx):
                    if event.is_final_response():
                        if event.content and event.content.parts:
                            final_output = event.content.parts[0].text
                            span.set_attribute("gen_ai.assistant.message", final_output)
                        if event.usage_metadata:
                            prompt_tokens = event.usage_metadata.prompt_token_count
                            completion_tokens = event.usage_metadata.candidates_token_count
                            total_tokens = event.usage_metadata.total_token_count
                            input_cost = float(os.getenv("GEMINI_2_0_FLASH_INPUT_COST", "0.10"))
                            output_cost = float(os.getenv("GEMINI_2_0_FLASH_OUTPUT_COST", "0.30"))
                            cost = (prompt_tokens * input_cost / 1000000) + (completion_tokens * output_cost / 1000000)
                            span.set_attribute("gen_ai.usage.prompt_tokens", prompt_tokens)
                            span.set_attribute("gen_ai.usage.completion_tokens", completion_tokens)
                            span.set_attribute("gen_ai.usage.total_tokens", total_tokens)
                            span.set_attribute("gen_ai.usage.cost", cost)
                    yield event
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                logging.error(f"Error during PlannerAgent execution: {e}", exc_info=True)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
