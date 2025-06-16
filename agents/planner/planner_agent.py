import os
import json
from dotenv import load_dotenv
from typing import TypedDict, Optional, List, Dict, Any # Added TypedDict, List

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage, ToolMessage # Added BaseMessage, ToolMessage
from langchain_core.tools import tool
from langchain_community.tools import GoogleSearchAPIWrapper
from langgraph.graph import StateGraph, END # Added StateGraph, END
import logging # Added logging

# Load environment variables from the root .env file.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# Logger setup
logger = logging.getLogger(__name__)

class PlannerGraphState(TypedDict):
    user_request: str
    instruction_prompt: str
    messages: List[BaseMessage]
    llm_response: Optional[Any]  # Can hold AIMessage or content string
    tool_calls: Optional[List[Any]]
    tool_outputs: Optional[List[Dict[str, Any]]]
    parsed_json_output: Optional[Dict[str, Any]]
    error_message: Optional[str]
    recursion_depth: int

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


class PlannerAgent:
  """An agent to help user planning a night out with its desire location, using LangGraph."""

  def __init__(self):
    # LLM and tools are initialized as before
    self.llm = ChatGoogleGenerativeAI(model="gemini-pro", temperature=0.7)
    self.search_tool = get_google_search_tool() # Assuming get_google_search_tool remains
    self.graph = self._build_planner_graph()

  def _build_planner_graph(self) -> StateGraph:
      graph_builder = StateGraph(PlannerGraphState)

      # Define Nodes
      graph_builder.add_node("prepare_prompt", self._prepare_prompt_node)
      graph_builder.add_node("invoke_llm", self._invoke_llm_node)
      graph_builder.add_node("execute_tools", self._execute_tools_node)
      graph_builder.add_node("parse_llm_response", self._parse_llm_response_node)

      # Define Edges
      graph_builder.set_entry_point("prepare_prompt")
      graph_builder.add_edge("prepare_prompt", "invoke_llm")
      graph_builder.add_conditional_edges(
          "invoke_llm",
          self._should_call_tools_router,
          {
              "call_tools": "execute_tools",
              "parse_response": "parse_llm_response",
              END: END # In case of immediate error from LLM
          }
      )
      graph_builder.add_edge("execute_tools", "invoke_llm") # Loop back to LLM after tool execution
      graph_builder.add_edge("parse_llm_response", END)

      return graph_builder.compile()

    # Node: Prepare Prompt
    def _prepare_prompt_node(self, state: PlannerGraphState) -> PlannerGraphState:
        logger.info("---Node: Preparing Prompt---")
        # If messages are already populated (e.g. from tool execution), append. Otherwise, create.
        if not state.get("messages"):
            messages = [
                SystemMessage(content=state["instruction_prompt"]),
                HumanMessage(content=state["user_request"])
            ]
        else: # Append tool outputs to existing messages
            messages = list(state["messages"]) # Make a mutable copy
            if state.get("tool_outputs"):
                for tool_output in state["tool_outputs"]:
                    messages.append(ToolMessage(content=tool_output["output"], tool_call_id=tool_output["tool_call_id"]))

        return {**state, "messages": messages, "tool_outputs": None} # Clear tool_outputs after processing

    # Node: Invoke LLM
    async def _invoke_llm_node(self, state: PlannerGraphState) -> Dict[str, Any]:
        logger.info(f"---Node: Invoking LLM (Depth: {state['recursion_depth']})---")
        if state['recursion_depth'] > 5: # Max tool call recursion
            logger.warning("Max recursion depth for tool calls reached.")
            return {**state, "error_message": "Max recursion depth for tool calls reached."}

        messages = state["messages"]
        try:
            # response = await self.llm.ainvoke(messages, tools=[self.search_tool]) # If using direct tool binding
            # Forcing tool choice example (if needed, otherwise remove `tool_choice`):
            # response = await self.llm.ainvoke(messages, tools=[self.search_tool], tool_choice=[{"type": "function", "function": {"name": "google_search"}}])
            response = await self.llm.ainvoke(messages, tools=[self.search_tool])

            logger.debug(f"LLM Response: {response}")
            return {**state, "llm_response": response, "tool_calls": response.tool_calls, "recursion_depth": state['recursion_depth'] + 1}
        except Exception as e:
            logger.error(f"LLM invocation error: {e}")
            return {**state, "error_message": f"LLM invocation failed: {str(e)}"}

    # Router: Should Call Tools?
    def _should_call_tools_router(self, state: PlannerGraphState) -> str:
        logger.info("---Router: Checking for Tool Calls---")
        if state.get("error_message"): # If invoke_llm_node had an error
            return END
        if state.get("tool_calls"):
            logger.info(f"Tool calls present: {state['tool_calls']}")
            return "call_tools"
        logger.info("No tool calls. Proceeding to parse response.")
        return "parse_response"

    # Node: Execute Tools
    def _execute_tools_node(self, state: PlannerGraphState) -> Dict[str, Any]:
        logger.info("---Node: Executing Tools---")
        tool_calls = state.get("tool_calls", [])
        tool_outputs = []
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})
            tool_call_id = tool_call.get("id") # LangChain uses 'id' for tool_call_id
            logger.info(f"Executing tool: {tool_name} with args: {tool_args} and ID: {tool_call_id}")

            output = None
            error = None
            try:
                if tool_name == "google_search":
                    # Ensure args are passed correctly; GoogleSearchAPIWrapper might expect a string query directly
                    query_arg = tool_args.get("query", "") # Assuming the LLM provides args like {"query": "search term"}
                    if not isinstance(query_arg, str):
                        error = "Invalid arguments for google_search: query must be a string."
                    else:
                        output = self.search_tool.invoke({"query": query_arg}) # search_tool is already a LangChain @tool
                else:
                    error = f"Unknown tool: {tool_name}"
            except Exception as e:
                logger.error(f"Error executing tool {tool_name}: {e}")
                error = str(e)

            if error:
                tool_outputs.append({"tool_call_id": tool_call_id, "output": json.dumps({"error": error})})
            else:
                tool_outputs.append({"tool_call_id": tool_call_id, "output": output if isinstance(output, str) else json.dumps(output)})

        return {**state, "tool_outputs": tool_outputs, "tool_calls": None, "messages": state.get("messages", []) + [state["llm_response"]]} # Add AIMessage with tool_calls to history

    # Node: Parse Final LLM Response (when no tool calls are made)
    def _parse_llm_response_node(self, state: PlannerGraphState) -> Dict[str, Any]:
        logger.info("---Node: Parsing Final LLM Response---")
        llm_response = state.get("llm_response")

        if not llm_response or not hasattr(llm_response, 'content'):
             logger.error("No LLM response content to parse.")
             return {**state, "error_message": "No LLM response content to parse."}

        llm_output = llm_response.content
        logger.debug(f"LLM Output (raw) for parsing: {llm_output}")
        try:
            json_part = llm_output
            if "--json--" in llm_output:
                json_part = llm_output.split("--json--")[1].strip()
            elif llm_output.startswith("```json"):
                json_part = llm_output[7:].strip()
                if json_part.endswith("```"):
                    json_part = json_part[:-3].strip()
            elif llm_output.startswith("```"):
                json_part = llm_output[3:].strip()
                if json_part.endswith("```"):
                    json_part = json_part[:-3].strip()

            # Further attempt to find JSON if not clean
            if not json_part.startswith("{") and not json_part.startswith("["):
                json_start_index = json_part.find('{')
                json_end_index = json_part.rfind('}')
                if json_start_index != -1 and json_end_index != -1 and json_start_index < json_end_index:
                    json_part = json_part[json_start_index : json_end_index+1]

            logger.info(f"Attempting to parse JSON part: {json_part}")
            parsed_output = json.loads(json_part)
            logger.info("Successfully parsed LLM output.")
            return {**state, "parsed_json_output": parsed_output, "error_message": None}
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from LLM: {e}. Raw output: {llm_output}")
            return {**state, "error_message": f"Failed to parse LLM output as JSON. Raw output: {llm_output}"}

  # get_processing_message is removed.

  async def async_query(self, query: str, **kwargs: Any) -> Dict[str, Any]:
      logger.info(f"PlannerAgent received query for LangGraph: {query}")
      initial_state: PlannerGraphState = {
          "user_request": query,
          "instruction_prompt": INSTRUCTION_PROMPT, # Global INSTRUCTION_PROMPT
          "messages": [],
          "llm_response": None,
          "tool_calls": None,
          "tool_outputs": None,
          "parsed_json_output": None,
          "error_message": None,
          "recursion_depth": 0,
      }
      try:
          # Configuration for the graph invocation, e.g., recursion limit
          config = {"recursion_limit": 10}
          final_state = await self.graph.ainvoke(initial_state, config=config)

          if final_state.get("error_message"):
              logger.error(f"PlannerAgent graph execution resulted in an error: {final_state['error_message']}")
              return {"output": final_state.get("parsed_json_output"), "error": final_state["error_message"]}

          if final_state.get("parsed_json_output") is not None:
              return {"output": final_state["parsed_json_output"]}
          else:
              logger.warning("PlannerAgent graph execution finished without a final output or an error message.")
              return {"output": None, "error": "No output or error message produced by the planner graph."}

      except Exception as e:
          import traceback
          error_msg = f"An unexpected error occurred during planner graph invocation: {str(e)}"
          logger.error(f"{error_msg}\n{traceback.format_exc()}")
          return {"output": None, "error": error_msg}