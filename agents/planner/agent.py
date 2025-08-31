import os
import sys
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.tools import google_search
from opentelemetry import trace
from common.observability import setup_observability
import logging

# --- START: Agent Environment Debugging Code ---
# This code will run when the agent container starts on Vertex AI.
print("--- AGENT SERVER-SIDE ENVIRONMENT CHECK ---")
print(f"Python Version Used by Agent: {sys.version}")
# print(f"Agent's google-cloud-aiplatform SDK Version: {google.cloud.aiplatform.__version__}")
print("--- AGENT INITIALIZATION CONTINUING ---")
# --- END: Agent Environment Debugging Code ---

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)

class PlannerAgent(LlmAgent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def set_up(self):
        logger.info("Initializing PlannerAgent and Observability...")
        setup_observability()
        logger.info("PlannerAgent setup complete.")
        return self

    def __call__(self, **kwargs):
        with tracer.start_as_current_span("a2a.planner.plan") as span:
            span.set_attribute("request.data", str(kwargs))
            logger.info(f"Handling plan request: {kwargs}")

            try:
                response = super().__call__(**kwargs)
                span.set_attribute("response.data", str(response))
                span.set_status(trace.StatusCode.OK)
                return response
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.StatusCode.ERROR, str(e))
                raise

def create_agent():
    MODEL_NAME = "gemini-1.5-flash"
    AGENT_NAME = "planner_agent"
    AGENT_INSTRUCTION = """

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

        """

    return PlannerAgent(
        name=AGENT_NAME,
        model=MODEL_NAME,
        description="Agent that creates plans",
        instruction=AGENT_INSTRUCTION,
        tools=[google_search]
    )

root_agent = create_agent()
