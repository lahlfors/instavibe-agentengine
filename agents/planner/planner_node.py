import os
import json
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field # For defining expected output structure
from langchain_core.tools import tool # If creating a custom LangChain tool for search
from langchain_community.tools import GoogleSearchAPIWrapper # For Google Search
from langchain_core.messages import HumanMessage, SystemMessage

from agents.app.common.graph_state import OrchestratorState

# Load environment variables from the root .env file.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
# Ensure GOOGLE_API_KEY is set in .env for GenAI
# Ensure GOOGLE_CSE_ID and GOOGLE_API_KEY are set for Google Search if using GoogleSearchAPIWrapper

# Copied from agents/planner/agent.py
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

# Define Output Structure
class LocationActivity(BaseModel):
    name: str
    latitude: float
    longitude: float
    description: str

class FunPlan(BaseModel):
    plan_description: str
    locations_and_activities: list[LocationActivity]

class PlannerOutput(BaseModel):
    fun_plans: list[FunPlan]

# Google Search Tool Definition
search_tool = None
try:
    search = GoogleSearchAPIWrapper()

    @tool("google_search")
    def google_search_tool(query: str) -> str:
        """Performs a Google search and returns results."""
        return search.run(query)
    search_tool = google_search_tool
except Exception as e:
    print(f"Error setting up Google Search tool: {e}. Search will not be available.")
    # Define a dummy tool if setup fails to avoid breaking the agent
    @tool("google_search")
    def google_search_tool_dummy(query: str) -> str:
        """Dummy Google Search tool. Returns a placeholder message."""
        return "Google Search is not available."
    search_tool = google_search_tool_dummy

def execute_planner_node(state: OrchestratorState) -> dict:
    print("---Executing Planner Node---")
    try:
        # 1. Initialize LLM
        # Ensure GEMINI_API_KEY is loaded via load_dotenv or set in environment
        # TODO: Make model configurable, potentially from state or global config
        llm = ChatGoogleGenerativeAI(model="gemini-pro", temperature=0.7)

        # 2. Prepare input for the prompt
        if not state.current_task_description:
            print("Error: No task description provided for planner node.")
            return {
                "error_message": "No task description provided for planner node.",
                "current_agent_name": "planner"
            }

        user_input_for_prompt = state.current_task_description
        print(f"Received user input for prompt: {user_input_for_prompt}")

        # 3. Create messages for the LLM
        # The INSTRUCTION_PROMPT serves as the system message.
        # The user_input_for_prompt (derived from state.current_task_description) is the human message.
        messages = [
            SystemMessage(content=INSTRUCTION_PROMPT),
            HumanMessage(content=user_input_for_prompt)
        ]

        # 4. Invoke LLM
        # The current setup does not explicitly bind tools for a direct tool-calling loop by the LLM.
        # The INSTRUCTION_PROMPT expects the LLM to generate JSON directly, implying it has access
        # to necessary information or can synthesize it based on its training.
        # If the LLM needs to perform searches, the prompt should guide it to request them,
        # or a more complex agent executor structure would be needed.
        print("Invoking LLM...")
        response = llm.invoke(messages)
        llm_output = response.content

        print(f"LLM Output (raw): {llm_output}")

        # 5. Parse LLM output
        try:
            # The prompt asks for "--json--" tags, but the LLM might not always include them,
            # or might include them with other text. We should try to extract the JSON part.
            if "--json--" in llm_output:
                json_part = llm_output.split("--json--")[1].strip()
            else:
                # Try to find JSON block if tags are missing
                json_start_index = llm_output.find('{')
                json_end_index = llm_output.rfind('}')
                if json_start_index != -1 and json_end_index != -1 and json_start_index < json_end_index:
                    json_part = llm_output[json_start_index : json_end_index+1]
                else: # Assume the whole output is JSON if no clear delimiters
                    json_part = llm_output

            print(f"Attempting to parse JSON part: {json_part}")
            parsed_output = json.loads(json_part)

            # Optional: Validate with Pydantic model PlannerOutput
            # try:
            #     PlannerOutput.model_validate(parsed_output) # Use model_validate for dict
            #     print("LLM output validated against PlannerOutput model.")
            # except Exception as pydantic_error:
            #     print(f"Pydantic validation error: {pydantic_error}")
            #     return {
            #         "error_message": f"LLM output failed Pydantic validation: {pydantic_error}. Output: {json_part}",
            #         "current_agent_name": "planner"
            #     }

        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from LLM: {e}")
            error_message = f"Failed to parse LLM output as JSON. Raw output: {llm_output}"
            # Log a snippet of the problematic output for easier debugging
            if len(llm_output) > 200:
                error_message += f" (Snippet: {llm_output[:100]}...{llm_output[-100:]})"
            else:
                error_message += f" (Full output: {llm_output})"

            return {
                "error_message": error_message,
                "current_agent_name": "planner"
            }

        print(f"Successfully parsed LLM output.")
        return {"intermediate_output": parsed_output, "current_agent_name": "planner"}

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in planner node: {e}\n{error_trace}")
        return {
            "error_message": f"An unexpected error occurred in the planner node: {str(e)}",
            "current_agent_name": "planner"
        }
