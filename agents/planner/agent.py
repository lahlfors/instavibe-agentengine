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

from dotenv import load_dotenv
from google.adk.agents import LlmAgent as Agent # Use LlmAgent alias for clarity
# from google.adk.models.google_llm import GoogleLlm # Removed import
from google.adk.tools import google_search

# Logging and tracing are now handled by the base AgentEngineApp.
# We still need a logger for this specific module.
# And SERVICE_NAME for context if needed, or for environment variable for AgentEngineApp.

SERVICE_NAME = "planner-agent"
# This environment variable can be picked up by AgentEngineApp if it's set before AgentEngineApp.set_up() is called.
# This is relevant for Step 2 of the plan (service-specific names).
os.environ["AGENT_SERVICE_NAME"] = SERVICE_NAME

logger = logging.getLogger(__name__) # Get logger after base setup

# Load environment variables from the root .env file.
logger.info(f"Loading .env variables for {SERVICE_NAME}...")
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
logger.info(".env variables loaded.")

# project_id, location, and model_config_kwargs are removed as LlmAgent will use
# values from vertexai.init() or environment variables.

# Define model name string - ensure this is the desired model
MODEL_NAME = "gemini-2.0-flash-001" # Updated deprecated model
# AGENT_NAME is the name for the ADK Agent instance, SERVICE_NAME is for observability
ADK_AGENT_NAME = "location_search_agent"
logger.info(f"Defining Planner ADK Agent: Name='{ADK_AGENT_NAME}', Model='{MODEL_NAME}', Service Context: '{SERVICE_NAME}'")

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
    name=ADK_AGENT_NAME, # Corrected variable name
    model=MODEL_NAME,
    description="Agent tasked with generating creative and fun event plan suggestions", # Kept original description
    instruction=AGENT_INSTRUCTION,
    tools=root_tools
    # NO model_kwargs
)
logger.info(f"Planner ADK LlmAgent '{root_agent.name}' instantiated successfully.")

# --- Streaming Functionality ---
import asyncio
import json
from typing import AsyncGenerator, Dict, Any

async def generate_plan_stream(query_details: Dict[str, Any], planner_agent_instance: Agent) -> AsyncGenerator[str, None]:
    """
    Generates plans by invoking the planner_agent_instance and streams individual plans from the response.

    Args:
        query_details: A dictionary containing details for constructing the prompt,
                       e.g., {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD",
                              "location": "City, State", "latitude": "0.0", "longitude": "0.0",
                              "num_plans": "3", "interests": "outdoors, foodie"}
        planner_agent_instance: The instantiated ADK LlmAgent for the planner.

    Yields:
        str: A JSON string representation of each individual plan object.
    """
    logger.info(f"generate_plan_stream called with query_details: {query_details}")

    # Construct the prompt from AGENT_INSTRUCTION and query_details
    prompt = AGENT_INSTRUCTION # Start with the base instruction

    # Replace placeholders - ensure defaults or handling for missing optional keys
    prompt = prompt.replace("[START_DATE_YYYY-MM-DD]", query_details.get("start_date", "this weekend"))
    prompt = prompt.replace("[END_DATE_YYYY-MM-DD]", query_details.get("end_date", "this weekend"))
    prompt = prompt.replace("[TARGET_LOCATION_NAME_OR_CITY_STATE]", query_details.get("location", "the specified area"))
    prompt = prompt.replace("[TARGET_LATITUDE]", str(query_details.get("latitude", "")))
    prompt = prompt.replace("[TARGET_LONGITUDE]", str(query_details.get("longitude", "")))
    prompt = prompt.replace("[NUMBER_OF_PLANS_TO_GENERATE, e.g., 3]", str(query_details.get("num_plans", "1")))
    prompt = prompt.replace("[COMMA_SEPARATED_LIST_OF_INTERESTS, e.g., outdoors, arts & culture, foodie, nightlife, unique local events, live music, active/sports]",
                            query_details.get("interests", "general fun activities"))

    logger.debug(f"Constructed prompt for streaming: {prompt[:500]}...") # Log beginning of prompt

    try:
        loop = asyncio.get_event_loop()
        # ADK LlmAgent.invoke is synchronous, so run in executor
        full_response_str = await loop.run_in_executor(None, planner_agent_instance.invoke, prompt)

        logger.info(f"Planner agent invoked. Full response string length: {len(full_response_str)}")
        logger.debug(f"Full response from planner agent: {full_response_str[:500]}...")

        response_json = json.loads(full_response_str)

        plans = response_json.get("fun_plans", [])
        if not plans:
            logger.warning("No 'fun_plans' found in the LLM response.")
            yield json.dumps({"warning": "No plans generated.", "details": full_response_str})
            return

        logger.info(f"Found {len(plans)} plans to stream.")
        for i, plan_object in enumerate(plans):
            yield json.dumps(plan_object)
            logger.debug(f"Yielded plan {i+1}")
            await asyncio.sleep(0) # Allow other tasks to run, good practice for async generators

    except json.JSONDecodeError as e:
        logger.error(f"JSONDecodeError in generate_plan_stream: {e}. Response: {full_response_str}", exc_info=True)
        yield json.dumps({"error": "Failed to parse LLM response as JSON", "details": str(e)})
    except Exception as e:
        logger.error(f"Exception in generate_plan_stream: {e}", exc_info=True)
        yield json.dumps({"error": f"An unexpected error occurred during plan generation: {str(e)}"})
