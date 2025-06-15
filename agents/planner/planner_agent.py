import os
import json
from dotenv import load_dotenv
from typing import Any, Dict, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_community.utilities import GoogleSearchAPIWrapper # Corrected import path
import logging

# Load environment variables from the root .env file.
# Ensure this is called before any modules that might need these variables at import time.
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
else:
    logging.warning(f".env file not found at {dotenv_path}. PlannerAgent may not have required API keys.")

# Instruction Prompt for the Planner
INSTRUCTION_PROMPT = """

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

# Google Search Tool Definition
# Global variable for the search tool to initialize it once.
search_tool_instance = None

def get_google_search_tool():
    global search_tool_instance
    if search_tool_instance is None:
        try:
            search = GoogleSearchAPIWrapper() # GOOGLE_API_KEY and GOOGLE_CSE_ID must be in env
            @tool("google_search")
            def google_search_tool_func(query: str) -> str:
                """Performs a Google search and returns results."""
                return search.run(query)
            search_tool_instance = google_search_tool_func
            logging.info("Google Search tool initialized successfully for PlannerAgent.")
        except Exception as e:
            logging.error(f"Error setting up Google Search tool in PlannerAgent: {e}. Search will not be available.", exc_info=True)
            @tool("google_search")
            def google_search_tool_dummy(query: str) -> str:
                """Dummy Google Search tool. Returns a placeholder message because initialization failed."""
                return "Google Search is not available due to an initialization error."
            search_tool_instance = google_search_tool_dummy
    return search_tool_instance


class PlannerAgent: # Removed AgentTaskManager inheritance
  """
  An agent to help users plan activities, outings, or events by generating creative suggestions.
  It interacts with an LLM based on a detailed instruction prompt.
  """

  def __init__(self):
    # super().__init__() # Removed call to AgentTaskManager's init
    self.llm = ChatGoogleGenerativeAI(model="gemini-pro", temperature=0.7) # TODO: Make model and temperature configurable
    self.search_tool = get_google_search_tool() # Initializes the search tool (once)
    logging.info("PlannerAgent initialized with Gemini Pro LLM and Google Search tool.")

  # get_processing_message method removed as it was likely part of AgentTaskManager interface

  async def async_query(self, query: str, **kwargs) -> Dict[str, Any]:
    """
    Handles the user's request for planning by invoking an LLM with a specific prompt.

    Args:
        query: The user's request or current task description for planning.
        **kwargs: Additional keyword arguments (currently not used but included for potential future flexibility).

    Returns:
        A dictionary containing either "output" with the parsed LLM response (JSON)
        or "error" with an error message if processing fails.
    """
    logging.info(f"PlannerAgent received query for async_query: '{query[:100]}...'") # Log snippet of query

    try:
        # 1. Prepare input for the prompt (query is typically current_task_description from OrchestratorState)
        user_input_for_prompt = query

        # 2. Create messages for the LLM
        messages = [
            SystemMessage(content=INSTRUCTION_PROMPT),
            HumanMessage(content=user_input_for_prompt)
        ]

        # 3. Invoke LLM
        # Note: The INSTRUCTION_PROMPT implies the LLM should generate JSON directly.
        # If the LLM needs to use tools like Google Search, the prompt should guide it
        # to request searches, or a LangChain agent executor with tool binding would be needed.
        # For this refactoring, we are keeping the direct LLM call. The self.search_tool
        # is available if this agent's capabilities are expanded to use tools autonomously.
        logging.info("Invoking LLM for PlannerAgent...")
        # The current INSTRUCTION_PROMPT expects the LLM to generate JSON directly.
        # It does not guide the LLM to use tools like Google Search.
        response = await self.llm.ainvoke(messages)
        llm_output = response.content
        logging.info(f"LLM Output (raw) in PlannerAgent: {llm_output[:500]}...") # Log snippet

        # 4. Parse LLM output
        try:
            # Attempt to extract JSON part, accommodating potential markdown or other text
            if "--json--" in llm_output: # Check for explicit delimiter
                json_part = llm_output.split("--json--")[1].strip()
            else: # Fallback to finding the first '{' and last '}'
                json_start_index = llm_output.find('{')
                json_end_index = llm_output.rfind('}')
                if json_start_index != -1 and json_end_index != -1 and json_start_index < json_end_index:
                    json_part = llm_output[json_start_index : json_end_index+1]
                else: # If no clear JSON structure is found
                    json_part = llm_output # Assume the whole output might be JSON or malformed

            logging.info(f"Attempting to parse JSON part in PlannerAgent: {json_part[:500]}...") # Log snippet
            parsed_output = json.loads(json_part)

            # TODO: Consider Pydantic validation here if a schema for the expected output is defined.
            # from your_pydantic_models import PlannerOutput # Example
            # try:
            #   PlannerOutput.model_validate(parsed_output)
            #   logging.info("LLM output successfully validated against Pydantic model.")
            # except ValidationError as ve:
            #   logging.warning(f"Pydantic validation error for LLM output: {ve}")
            #   # Decide if this should be a hard error or just a warning
            #   return {"output": None, "error": f"LLM output failed Pydantic validation: {ve}. Raw: {json_part}"}

            logging.info("Successfully parsed LLM output in PlannerAgent.")
            return {"output": parsed_output}

        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON from LLM in PlannerAgent: {e}. Raw JSON part: {json_part}", exc_info=True)
            error_message = f"Failed to parse LLM output as JSON. Error: {e}. Received: {json_part[:200]}..."
            return {"output": None, "error": error_message}

    except Exception as e:
        logging.error(f"Error in PlannerAgent async_query: {e}", exc_info=True)
        return {"output": None, "error": f"An unexpected error occurred in PlannerAgent: {str(e)}"}