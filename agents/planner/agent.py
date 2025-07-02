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

from typing import Optional # Added
from pydantic import Field # Added

SERVICE_NAME = "planner-agent"
# This environment variable can be picked up by AgentEngineApp if it's set before AgentEngineApp.set_up() is called.
# This is relevant for Step 2 of the plan (service-specific names).
os.environ["AGENT_SERVICE_NAME"] = SERVICE_NAME

logger = logging.getLogger(__name__) # Get logger after base setup

# Load environment variables from the root .env file.
logger.info(f"Loading .env variables for {SERVICE_NAME}...")
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
logger.info(".env variables loaded.")

import httpx # For MCP client calls
import json
from typing import AsyncIterable, Dict, Any, AsyncGenerator

# Define model name string - ensure this is the desired model
MODEL_NAME = "gemini-2.0-flash-001" # Updated deprecated model
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

class PlannerAgent(Agent):
    mcp_server_url: Optional[str] = None
    # Exclude http_client from Pydantic model schema, validation, and serialization
    http_client: Optional[httpx.Client] = Field(default=None, exclude=True)


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mcp_server_url = os.environ.get("AGENTS_PLANNER_MCP_SERVER_URL") # Ensure this is set in .env
        if not self.mcp_server_url:
            logger.warning("AGENTS_PLANNER_MCP_SERVER_URL is not set. MCP tool calls will fail.")
            # You might want to raise an error here if MCP is critical
        self.http_client = httpx.Client()
        # self.mcp_tools = self._get_mcp_tools() # Dynamic tool discovery can be added later

    # def _get_mcp_tools(self): # Example for dynamic tool discovery
    #     if not self.mcp_server_url: return []
    #     try:
    #         response = self.http_client.get(f"{self.mcp_server_url}/tools/list")
    #         response.raise_for_status()
    #         return response.json()
    #     except httpx.RequestError as e:
    #         logger.error(f"Error getting MCP tools: {e}")
    #         return []
    #     except json.JSONDecodeError as e:
    #         logger.error(f"Error decoding MCP tools list: {e}")
    #         return []

    def _call_mcp_tool(self, tool_name: str, tool_arguments: dict) -> dict:
        if not self.mcp_server_url:
            return {"error": "MCP_SERVER_URL not configured for PlannerAgent"}
        try:
            logger.info(f"Calling MCP tool: {tool_name} with args: {tool_arguments}")
            response = self.http_client.post(f"{self.mcp_server_url}/tools/call/{tool_name}", json=tool_arguments, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            logger.error(f"Error calling MCP tool {tool_name}: {e}", exc_info=True)
            return {"error": f"Error calling MCP tool {tool_name}: {str(e)}"}
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response from MCP tool {tool_name}: {e}", exc_info=True)
            return {"error": f"Error decoding JSON response from MCP tool {tool_name}: {str(e)}"}

    async def _stream_mcp_tool(self, tool_name: str, tool_arguments: dict) -> AsyncIterable[dict]:
        if not self.mcp_server_url:
            yield {"error": "MCP_SERVER_URL not configured for PlannerAgent"}
            return
        try:
            logger.info(f"Streaming MCP tool: {tool_name} with args: {tool_arguments}")
            async with httpx.AsyncClient(timeout=30.0) as client: # Use AsyncClient for streaming
                async with client.stream("POST", f"{self.mcp_server_url}/tools/call/{tool_name}", json=tool_arguments) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        # Assuming chunks are JSON objects or can be processed as such.
                        # This might need adjustment based on actual MCP streaming format.
                        try:
                            yield {"response_chunk": json.loads(chunk.decode("utf-8"))}
                        except json.JSONDecodeError:
                            yield {"response_chunk": chunk.decode("utf-8")} # Send as raw string if not JSON
        except httpx.RequestError as e:
            logger.error(f"Error streaming MCP tool {tool_name}: {e}", exc_info=True)
            yield {"error": f"Error streaming MCP tool {tool_name}: {str(e)}"}
        except Exception as e: # Catch other potential errors during streaming
            logger.error(f"Unexpected error streaming MCP tool {tool_name}: {e}", exc_info=True)
            yield {"error": f"Unexpected error streaming MCP tool {tool_name}: {str(e)}"}


    def _prepare_plan_prompt(self, query_details: Dict[str, Any]) -> str:
        prompt = AGENT_INSTRUCTION
        prompt = prompt.replace("[START_DATE_YYYY-MM-DD]", query_details.get("start_date", "this weekend"))
        prompt = prompt.replace("[END_DATE_YYYY-MM-DD]", query_details.get("end_date", "this weekend"))
        prompt = prompt.replace("[TARGET_LOCATION_NAME_OR_CITY_STATE]", query_details.get("location", "the specified area"))
        prompt = prompt.replace("[TARGET_LATITUDE]", str(query_details.get("latitude", "")))
        prompt = prompt.replace("[TARGET_LONGITUDE]", str(query_details.get("longitude", "")))
        prompt = prompt.replace("[NUMBER_OF_PLANS_TO_GENERATE, e.g., 3]", str(query_details.get("num_plans", "1")))
        prompt = prompt.replace("[COMMA_SEPARATED_LIST_OF_INTERESTS, e.g., outdoors, arts & culture, foodie, nightlife, unique local events, live music, active/sports]",
                                query_details.get("interests", "general fun activities"))
        return prompt

    def invoke(self, input_data: dict) -> dict:
        logger.info(f"PlannerAgent invoke called with input_data: {input_data}")
        if "tool_name" in input_data:
            tool_name = input_data["tool_name"]
            tool_arguments = input_data.get("tool_arguments", {})
            return self._call_mcp_tool(tool_name, tool_arguments)
        elif "query_details" in input_data: # For generating plans
            query_details = input_data["query_details"]
            prompt = self._prepare_plan_prompt(query_details)
            logger.debug(f"Constructed prompt for invoke: {prompt[:500]}...")
            try:
                # super().invoke is the LlmAgent's method to call the LLM
                response_str = super().invoke(prompt)
                logger.info(f"LLM invoked. Full response string length: {len(response_str)}")
                logger.debug(f"Full response from LLM: {response_str[:500]}...")
                # The ADK agent should return a JSON serializable dict.
                # If the LLM already returns valid JSON string for "fun_plans", parse and return.
                # Otherwise, wrap it.
                try:
                    parsed_response = json.loads(response_str)
                    return parsed_response # Assuming LLM returns the full JSON structure expected
                except json.JSONDecodeError:
                    logger.warning(f"LLM response was not valid JSON. Returning as raw text. Response: {response_str[:200]}")
                    return {"response": response_str} # Fallback
            except Exception as e:
                logger.error(f"Error during LLM invocation: {e}", exc_info=True)
                return {"error": f"Error during LLM invocation: {str(e)}"}
        elif "query" in input_data: # Generic query
             # Fallback for simple queries if not plan generation or tool call
            prompt = input_data["query"]
            logger.debug(f"Handling generic query: {prompt}")
            try:
                response_str = super().invoke(prompt)
                return {"response": response_str}
            except Exception as e:
                logger.error(f"Error during generic LLM invocation: {e}", exc_info=True)
                return {"error": f"Error during generic LLM invocation: {str(e)}"}
        else:
            logger.warning(f"Invalid input_data structure for invoke: {input_data}")
            return {"error": "Invalid input data structure. Expecting 'tool_name' or 'query_details' or 'query'."}

    async def stream(self, input_data: dict) -> AsyncIterable[dict]:
        logger.info(f"PlannerAgent stream called with input_data: {input_data}")
        if "tool_name" in input_data:
            tool_name = input_data["tool_name"]
            tool_arguments = input_data.get("tool_arguments", {})
            async for chunk in self._stream_mcp_tool(tool_name, tool_arguments):
                yield chunk # Already a dict with "response_chunk" or "error"
        elif "query_details" in input_data: # For streaming plans
            query_details = input_data["query_details"]
            prompt = self._prepare_plan_prompt(query_details)
            logger.debug(f"Constructed prompt for stream: {prompt[:500]}...")
            try:
                # Assuming super().stream() or similar method exists for LlmAgent for streaming from LLM
                # If not, this needs to be implemented, e.g., by calling invoke and then processing.
                # For now, let's adapt the existing generate_plan_stream logic here.
                # This example assumes the LLM response for plans is a single JSON containing all plans.
                # We then parse it and stream individual plans.

                # ADK LlmAgent.invoke is synchronous. To make this truly async for LLM streaming,
                # the underlying model call in LlmAgent would need to support async streaming.
                # For this refactor, we'll keep the existing behavior of invoking once and then streaming parts.
                loop = asyncio.get_event_loop()
                full_response_str = await loop.run_in_executor(None, super().invoke, prompt)

                logger.info(f"LLM invoked for streaming. Full response string length: {len(full_response_str)}")
                logger.debug(f"Full response from LLM for streaming: {full_response_str[:500]}...")

                response_json = json.loads(full_response_str)
                plans = response_json.get("fun_plans", [])

                if not plans:
                    logger.warning("No 'fun_plans' found in the LLM response for streaming.")
                    yield {"warning": "No plans generated.", "details": full_response_str}
                    return

                logger.info(f"Found {len(plans)} plans to stream.")
                for i, plan_object in enumerate(plans):
                    yield {"plan_chunk": plan_object} # Yield each plan as a dict
                    logger.debug(f"Streamed plan {i+1}")
                    await asyncio.sleep(0)

            except json.JSONDecodeError as e:
                logger.error(f"JSONDecodeError in stream (plan generation): {e}. Response: {full_response_str if 'full_response_str' in locals() else 'N/A'}", exc_info=True)
                yield {"error": "Failed to parse LLM response as JSON for plan streaming", "details": str(e)}
            except Exception as e:
                logger.error(f"Exception in stream (plan generation): {e}", exc_info=True)
                yield {"error": f"An unexpected error occurred during plan streaming: {str(e)}"}
        elif "query" in input_data: # Generic query streaming
            prompt = input_data["query"]
            logger.debug(f"Handling generic query for streaming: {prompt}")
            # This is a placeholder. Actual LLM streaming would involve model.generate_content(..., stream=True)
            # and iterating over chunks from the model.
            # For LlmAgent, if super().stream() is not available, this needs more thought.
            # For now, mimic simple chunking.
            try:
                # Placeholder for actual LLM streaming logic if LlmAgent supports it directly
                # If LlmAgent's 'invoke' is the only way, then true streaming from LLM isn't happening here.
                # response_str = super().invoke(prompt) # This would be non-streaming
                # yield {"response_chunk": response_str} # Then yield the whole thing

                # Let's assume a conceptual super().stream() or adapt
                current_response = ""
                for chunk_text in [f"ADK agent processing query: '{prompt}'", "... still thinking ...", "Final answer part."]:
                    current_response += chunk_text + " "
                    yield {"response_chunk": chunk_text}
                    await asyncio.sleep(0.1) # Simulate delay
                logger.info(f"Finished streaming generic query. Full conceptual response: {current_response.strip()}")

            except Exception as e:
                logger.error(f"Error during generic query streaming: {e}", exc_info=True)
                yield {"error": f"Error during generic query streaming: {str(e)}"}
        else:
            logger.warning(f"Invalid input_data structure for stream: {input_data}")
            yield {"error": "Invalid input data structure for stream. Expecting 'tool_name' or 'query_details' or 'query'."}

# --- Root Agent Instance ---
logger.info("Instantiating PlannerAgent...")

# Define root_tools before using it in PlannerAgent instantiation
# google_search is imported from google.adk.tools
root_tools = [google_search]

def get_planner_root_agent():
    """Instantiates and returns the PlannerAgent."""
    logger.info("Instantiating PlannerAgent via get_planner_root_agent...")
    agent_instance = PlannerAgent(
        name=ADK_AGENT_NAME,
        model=MODEL_NAME,
        description="Agent tasked with generating creative and fun event plan suggestions, and can call MCP tools.",
        instruction=AGENT_INSTRUCTION, # Base instruction for LLM, not directly used by tool calls
        tools=root_tools # Original tools like google_search, MCP tools are handled via _call_mcp_tool
    )
    logger.info(f"PlannerAgent '{agent_instance.name}' instantiated successfully by get_planner_root_agent.")
    return agent_instance

# root_agent = PlannerAgent(...) # Deferred instantiation

logger.info(f"PlannerAgent module loaded. Call get_planner_root_agent() to instantiate.")


# --- Old Streaming Functionality (to be deprecated/removed after refactoring stream method) ---
# Keep generate_plan_stream if it's directly used by A2A server initially,
# but the goal is to move its logic into PlannerAgent.stream
async def generate_plan_stream(query_details: Dict[str, Any], planner_agent_instance: PlannerAgent) -> AsyncGenerator[str, None]:
    """
    Generates plans by invoking the planner_agent_instance's stream method
    and yields JSON string representations of each plan object or chunk.
    This function now acts as a wrapper around planner_agent_instance.stream
    to maintain compatibility if a2a_server calls this specific function name.
    """
    logger.info(f"Legacy generate_plan_stream called with query_details: {query_details}")
    # The input_data for the new stream method should match what it expects
    input_data_for_stream = {"query_details": query_details}
    async for item_dict in planner_agent_instance.stream(input_data_for_stream):
        yield json.dumps(item_dict) # Ensure it yields JSON strings as per original
