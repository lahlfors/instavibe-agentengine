import os
import json
from dotenv import load_dotenv
from typing import Any, Dict, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_community.tools import GoogleSearchAPIWrapper

from common.task_manager import AgentTaskManager

# Load environment variables from the root .env file.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

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
            search = GoogleSearchAPIWrapper()
            @tool("google_search")
            def google_search_tool_func(query: str) -> str:
                """Performs a Google search and returns results."""
                return search.run(query)
            search_tool_instance = google_search_tool_func
        except Exception as e:
            print(f"Error setting up Google Search tool in PlannerAgent: {e}. Search will not be available.")
            @tool("google_search")
            def google_search_tool_dummy(query: str) -> str:
                """Dummy Google Search tool. Returns a placeholder message."""
                return "Google Search is not available."
            search_tool_instance = google_search_tool_dummy
    return search_tool_instance


class PlannerAgent(AgentTaskManager):
  """An agent to help user planning a night out with its desire location."""

  def __init__(self):
    super().__init__()
    # Initialize LLM and tools here if they are to be reused across multiple calls in a session.
    # For now, LLM is initialized per call in async_query for simplicity.
    self.llm = ChatGoogleGenerativeAI(model="gemini-pro", temperature=0.7) # TODO: Make model configurable
    self.search_tool = get_google_search_tool()


  def get_processing_message(self) -> str:
      return "Processing the planning request..."

  async def async_query(self, query: str, **kwargs) -> Dict[str, Any]:
    """Handles the user's request for planning directly."""
    print(f"PlannerAgent received query: {query}")

    try:
        # 1. Prepare input for the prompt (query is current_task_description)
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
        # For this refactoring, we are keeping the direct LLM call as in planner_node.py.
        # The `self.search_tool` is available if we evolve this to an agent executor.
        print("Invoking LLM for PlannerAgent...")
        # response = await self.llm.ainvoke(messages, tools=[self.search_tool]) # If using tools
        response = await self.llm.ainvoke(messages) # Direct call without explicit tool binding for now
        llm_output = response.content
        print(f"LLM Output (raw) in PlannerAgent: {llm_output}")

        # 4. Parse LLM output
        try:
            if "--json--" in llm_output:
                json_part = llm_output.split("--json--")[1].strip()
            else:
                json_start_index = llm_output.find('{')
                json_end_index = llm_output.rfind('}')
                if json_start_index != -1 and json_end_index != -1 and json_start_index < json_end_index:
                    json_part = llm_output[json_start_index : json_end_index+1]
                else:
                    json_part = llm_output

            print(f"Attempting to parse JSON part in PlannerAgent: {json_part}")
            parsed_output = json.loads(json_part)

            # TODO: Optional Pydantic validation (models would need to be defined/imported)
            # e.g., PlannerOutput.model_validate(parsed_output)

            print("Successfully parsed LLM output in PlannerAgent.")
            return {"output": parsed_output}

        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from LLM in PlannerAgent: {e}")
            error_message = f"Failed to parse LLM output as JSON. Raw output: {llm_output}"
            # Consider logging the full output for debugging if necessary
            return {"output": None, "error": error_message}

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in PlannerAgent async_query: {e}\n{error_trace}")
        return {"output": None, "error": f"An unexpected error occurred: {str(e)}"}