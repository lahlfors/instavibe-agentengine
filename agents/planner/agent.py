import sys
import google.cloud.aiplatform

# --- START: Agent Environment Debugging Code ---
# This code will run when the agent container starts on Vertex AI.
# print("--- AGENT SERVER-SIDE ENVIRONMENT CHECK ---")
# print(f"Python Version Used by Agent: {sys.version}")
# print(f"Agent's google-cloud-aiplatform SDK Version: {google.cloud.aiplatform.__version__}")
# print("--- AGENT INITIALIZATION CONTINUING ---")
# --- END: Agent Environment Debugging Code ---

import os
import logging # Added
from dotenv import load_dotenv
from google.adk.agents import LlmAgent as Agent # Use LlmAgent alias for clarity
# from google.adk.models.google_llm import GoogleLlm # Removed import
from google.adk.tools import google_search

from agents.app.utils.logging_setup import setup_google_cloud_logging # Import the new utility
from agents.app.utils.tracing import setup_global_tracer # Assuming this sets up OTEL tracer

# Initialize OpenTelemetry Tracer Provider first
# Use a specific service name for traces and logs in GCP
SERVICE_NAME = "planner-agent"
setup_global_tracer(service_name=SERVICE_NAME)

# Then setup logging
LOG_LEVEL = logging.INFO # Or logging.DEBUG, or from env var
setup_google_cloud_logging(log_level=LOG_LEVEL, service_name=SERVICE_NAME)

# Initialize logger at the module level AFTER setup
logger = logging.getLogger(__name__)

# Load environment variables from the root .env file.
# This is important so that any underlying ADK or Google library calls
# (e.g., for API keys for google_search, or project/location for Vertex AI)
# can pick up the correct configuration.
logger.info("Loading environment variables for planner agent definition...")
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
logger.info("Environment variables loaded.")

# project_id, location, and model_config_kwargs are removed as LlmAgent will use
# values from vertexai.init() or environment variables.

# Define model name string - ensure this is the desired model
MODEL_NAME = "gemini-2.0-flash-001" # Updated deprecated model
AGENT_NAME = "location_search_agent" # Consistent name from before
logger.info(f"Defining Planner ADK Agent: Name='{AGENT_NAME}', Model='{MODEL_NAME}'")

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
              "description": "A brief description of this place/event, why it's suitable for the date, and any specific details for the weekend (e.g., opening hours, event time)."
              }
              // Add more location/activity objects here if the plan involves multiple stops/parts
          ]
        }

    """
root_tools = [google_search] # Assuming this was the original definition
logger.debug(f"Planner ADK Agent tools: {[tool.name for tool in root_tools if hasattr(tool, 'name')]}")

logger.info("Instantiating Planner ADK LlmAgent...")
root_agent = Agent(
    name=AGENT_NAME,
    model=MODEL_NAME,
    description="Agent tasked with generating creative and fun event plan suggestions", # Kept original description
    instruction=AGENT_INSTRUCTION,
    tools=root_tools
    # NO model_kwargs
)
logger.info(f"Planner ADK LlmAgent '{root_agent.name}' instantiated successfully.")
