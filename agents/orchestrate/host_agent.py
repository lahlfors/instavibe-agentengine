import sys
import asyncio
import functools
import json
import os # Ensure os is imported
import uuid
import threading
from typing import List, Optional, Callable
import logging


from google.genai import types
import base64

from google.adk import Agent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.tool_context import ToolContext
# Removed:
# from agents.app.remote.remote_agent_connection import (
    # RemoteAgentConnections,
    # TaskUpdateCallback
# )
# from agents.app.common.client import A2ACardResolver
# from agents.app.common.types import (
    # AgentCard,
    # Message,
    # TaskState,
    # Task,
    # TaskSendParams,
    # TextPart,
    # DataPart,
    # Part,
    # TaskStatusUpdateEvent,
# )

# Placeholder for a2a-python imports - to be added when SDK usage is implemented
# from a2a import /* ... necessary a2a-python client and type imports ... */

logger = logging.getLogger(__name__)

class HostAgent:
  """The orchestrate agent.

  This is the agent responsible for choosing which remote agents to send
  tasks to and coordinate their work.
  """

  def __init__(
      self,
      remote_agent_addresses: List[str],
      # task_callback: TaskUpdateCallback | None = None # This callback was for the old system
  ):
    logger.info(f"HostAgent initializing with remote_agent_addresses: {remote_agent_addresses}")
    # self.task_callback = task_callback # Removed

    # Store addresses for later use with a2a-python SDK
    self.remote_agent_addresses = remote_agent_addresses

    # These will be replaced by a2a-python SDK mechanisms
    # self.remote_agent_connections: dict[str, RemoteAgentConnections] = {} # Removed
    # self.cards: dict[str, AgentCard] = {} # Removed

    # Placeholder for a2a-python client initialization
    # self.a2a_client = a2a.Client(...) # Example

    # The self.agents string will need to be populated differently,
    # likely by querying discoverable agents via a2a-python post-initialization
    # or if addresses are resource names, fetching their details.
    self.agents_metadata: list[dict] = [] # Store agent metadata (name, description) for list_remote_agents
    # TODO: Implement discovery of agent capabilities using a2a-python
    # and populate self.agents_metadata. This might be an async method
    # called after HostAgent instantiation, or done when list_remote_agents is called.
    # For now, if remote_agent_addresses are full resource names, we might parse them,
    # or rely on a discovery mechanism provided by a2a-python.
    # Example:
    # if self.remote_agent_addresses:
    #   logger.info("Attempting to populate agents_metadata from remote_agent_addresses (placeholder).")
    #   # This is a placeholder, actual fetching/discovery will use a2a-python
    #   for addr in self.remote_agent_addresses:
    #       # Assuming addr might be a resource name like "projects/X/locations/Y/reasoningEngines/Z"
    #       # Or an ID that a2a-python can resolve.
    #       # For now, just making a dummy entry.
    #       agent_name_from_addr = addr.split("/")[-1] if "/" in addr else addr
    #       self.agents_metadata.append({"name": agent_name_from_addr, "description": f"Agent at {addr} (description to be fetched)"})

    self._update_agents_string_from_metadata() # Initialize self.agents string
    logger.debug(f"Initial self.agents string: {self.agents}")

  def _update_agents_string_from_metadata(self):
    """Helper to update the self.agents string from self.agents_metadata."""
    agent_info_json_strings = []
    for agent_meta in self.agents_metadata:
        # Assuming agent_meta is a dict like {"name": "agent_name", "description": "agent_desc"}
        agent_info_json_strings.append(json.dumps(agent_meta))
    self.agents = '\n'.join(agent_info_json_strings)
    logger.debug(f"Updated self.agents string: {self.agents}")

  # Removed register_agent_card, as agent registration/discovery will be handled by a2a-python
  # def register_agent_card(self, card: AgentCard):
    # logger.info(f"Registering new agent card: {card.name if card else 'None'}")
    # if not card or not card.name:
      # logger.warning("Attempted to register an invalid or unnamed card.")
      # return

    # remote_connection = RemoteAgentConnections(card)
    # self.remote_agent_connections[card.name] = remote_connection
    # self.cards[card.name] = card
    # self._update_agents_string()
    # logger.info(f"Agent card '{card.name}' registered successfully.")

  def create_agent(self) -> Agent:
    logger.info("Creating ADK Agent instance for HostAgent")
    # project_id, location, and model_config_kwargs are removed as LlmAgent will use
    # values from vertexai.init() or environment variables.
    agent_instance = Agent(
        model="gemini-2.0-flash-001", # Updated model name
        name="orchestrate_agent",
        instruction=self.root_instruction,
        before_model_callback=self.before_model_callback,
        description=(
            "This agent orchestrates the decomposition of the user request into"
            " tasks that can be performed by the child agents."
        ),
        tools=[
            self.list_remote_agents,
            self.send_task,
        ]
        # model_kwargs removed
    )
    logger.info(f"ADK Agent '{agent_instance.name}' created with tools: {[tool.__name__ for tool in agent_instance.tools]}")
    return agent_instance

  def root_instruction(self, context: ReadonlyContext) -> str:
    logger.debug(f"Generating root_instruction. Current context state: {context.state}")
    current_agent_state = self.check_state(context)
    logger.debug(f"Current agent for instruction: {current_agent_state}")
    # Important: self.agents string should be up-to-date via _update_agents_string()
    # Ensure it's called if cards can change dynamically during agent's lifetime outside of register_agent_card
    instruction_string = f"""

    You are an expert AI Orchestrator. Your primary responsibility is to intelligently interpret user requests, plan the necessary sequence of actions if multiple steps are involved, and delegate them to the most appropriate specialized remote agents. You do not perform the tasks yourself but manage their assignment, sequence, and can monitor their status.

    Core Workflow & Decision Making:

    1.  **Understand User Intent & Complexity:**
        *   Carefully analyze the user's request to determine the core task(s) they want to achieve. Pay close attention to keywords and the overall goal.
        *   **Identify if the request requires a single agent or a sequence of actions from multiple agents.** For example, "Analyze John Doe's profile and then create a positive post about his recent event attendance" would require two agents in sequence.

    2.  **Agent Discovery & Selection:**
        *   Use `list_remote_agents` to get an up-to-date list of available remote agents and understand their specific capabilities (e.g., what kind of requests each agent is designed to handle and what data they output).
        *   Based on the user's intent:
            *   For **single-step requests**, select the single most appropriate agent.
            *   For **multi-step requests**, identify all necessary agents and determine the logical order of their execution.

    3.  **Task Planning & Sequencing (for Multi-Step Requests):**
        *   Before delegating, outline the sequence of agent tasks.
        *   Identify dependencies: Does Agent B need information from Agent A's completed task?
        *   Plan to execute tasks sequentially if there are dependencies, waiting for the completion of a prerequisite task before initiating the next one.

    4.  **Task Delegation & Management:**
        *   **For New Single Requests or the First Step in a Sequence:** Use `create_task`. Your `create_task` call MUST include:
            *   The `remote_agent_name` you've selected.
            *   The `user_request` or all necessary parameters extracted from the user's input, formatted in a way the target agent will understand.
        *   **For Subsequent Steps in a Sequence:**
            *   Wait for the preceding task to complete (you may need to use `check_pending_task_states` to confirm completion).
            *   Once the prerequisite task is done, gather any necessary output from it.
            *   Then, use `create_task` for the next agent in the sequence, providing it with the user's original relevant intent and any necessary data obtained from the previous agent's task.
        *   **For Ongoing Interactions with an Active Agent (within a single step):** If the user is providing follow-up information related to a task *currently assigned* to a specific agent, use the `update_task` tool.
        *   **Monitoring:** Use `check_pending_task_states` to check the status of any delegated tasks, especially when managing sequences or if the user asks for an update.

    **Communication with User:**

    *   When you delegate a task (or the first task in a sequence), clearly inform the user which remote agent is handling it.
    *   For multi-step requests, you can optionally inform the user of the planned sequence (e.g., "Okay, first I'll ask the 'Social Profile Agent' to analyze the profile, and then I'll have the 'Instavibe Posting Agent' create the post.").
    *   If waiting for a task in a sequence to complete, you can inform the user (e.g., "The 'Social Profile Agent' is currently processing. I'll proceed with the post once that's done.").
    *   If the user's request is ambiguous, if necessary information is missing for any agent in the sequence, or if you are unsure about the plan, proactively ask the user for clarification.
    *   Rely strictly on your tools and the information they provide.

    **Important Reminders:**
    *   Always prioritize selecting the correct agent(s) based on their documented purpose.
    *   Ensure all information required by the chosen remote agent is included in the `create_task` or `update_task` call, including outputs from previous agents if it's a sequential task.
    *   Focus on the most recent parts of the conversation for immediate context, but maintain awareness of the overall goal, especially for multi-step requests.

    Agents:
    {self.agents}

    Current agent: {current_agent_state['active_agent']}
    """
    # Log the full instruction string at DEBUG level if it's very long
    logger.debug(f"Full root instruction generated (first 200 chars): {instruction_string[:200]}...")
    return instruction_string

  
  def check_state(self, context: ReadonlyContext):
    state = context.state
    logger.debug(f"check_state called. Current state: {state}")
    active_agent_name = "None"
    if ('session_id' in state and
        'session_active' in state and
        state['session_active'] and
        'agent' in state):
      active_agent_name = state["agent"]
      logger.debug(f"Active session detected. Session ID: {state['session_id']}, Agent: {active_agent_name}")
      return {"active_agent": f'{active_agent_name}'}
    logger.debug("No active session or agent found in state.")
    return {"active_agent": active_agent_name}

  def before_model_callback(self, callback_context: CallbackContext, llm_request):
    state = callback_context.state
    logger.debug(f"before_model_callback called. Current state: {state}")
    if 'session_active' not in state or not state['session_active']:
      logger.info("No active session, ensuring session_id exists and marking session_active=True.")
      if 'session_id' not in state:
        new_session_id = str(uuid.uuid4())
        state['session_id'] = new_session_id
        logger.info(f"New session_id generated: {new_session_id}")
      state['session_active'] = True
    logger.debug(f"LLM Request (first 200 chars of messages if exist): {str(llm_request)[:200]}")


  def list_remote_agents(self):
    """List the available remote agents you can use to delegate the task."""
    logger.info("list_remote_agents tool called.")

    # TODO: Implement dynamic discovery of agents using a2a-python SDK here
    # This might involve calling an a2a-python method to get a list of
    # discoverable agents and then populating/updating self.agents_metadata.
    # For example:
    # discovered_agents = await self.a2a_client.discover_agents() # Assuming async discovery
    # new_metadata = []
    # for agent_details in discovered_agents: # Process results from SDK
    #    new_metadata.append({"name": agent_details.name, "description": agent_details.description})
    # self.agents_metadata = new_metadata
    # self._update_agents_string_from_metadata() # Update the string for the prompt too

    if not self.agents_metadata:
      logger.warning("No remote agent metadata available to list (self.agents_metadata is empty).")
      # Optionally, attempt discovery here if not done in __init__ or if a refresh is needed.
      # For now, returning a message indicating no agents are found.
      return "No remote agents are currently discovered or configured. Please check the system configuration."

    logger.info(f"Returning {len(self.agents_metadata)} remote agents from current metadata.")
    logger.debug(f"Remote agent list (from metadata): {self.agents_metadata}")
    return self.agents_metadata

  async def send_task(
      self,
      agent_name: str, # This might become an agent_id or resource_name
      message: str,    # The core message/query for the target agent
      tool_context: ToolContext):
    """Sends a task to a remote agent using the a2a-python SDK.

    Args:
      agent_name: The identifier of the target agent.
      message: The message payload for the agent.
      tool_context: The ADK tool context.

    Returns:
      The response from the remote agent, adapted for the ADK tool output.
    """
    logger.info(f"send_task tool called. Target agent: '{agent_name}'. Message (first 100 chars): '{message[:100]}...'")
    logger.debug(f"Full message for send_task to '{agent_name}': {message}")

    state = tool_context.state
    # The 'agent' in state might still be useful for context, or a2a might have its own task/session tracking.
    state['current_target_agent'] = agent_name

    # TODO: Initialize a2a-python client if not already done (e.g., in __init__ or lazily)
    # if not hasattr(self, 'a2a_client') or not self.a2a_client:
    #   self.a2a_client = A2AClient(...) # Example initialization
    #   logger.info("a2a-python client initialized in send_task (lazy).")

    # TODO: Resolve agent_name to an address/ID that a2a-python can use, if not already.
    # target_agent_address = self._resolve_agent_address(agent_name) # Example helper
    # if not target_agent_address:
    #   logger.error(f"Could not resolve address for agent '{agent_name}'.")
    #   return f"Error: Agent '{agent_name}' not found or address unknown."

    # TODO: Construct the message payload according to a2a-python SDK's requirements.
    # This will replace TaskSendParams, common.types.Message, etc.
    # It might involve specifying content type, handling sessions, etc.
    # Example (highly speculative):
    # a2a_message_payload = A2AMessage(
    #     content=message,
    #     # session_id=state.get('a2a_session_id_for_agent_name'), # a2a-python might handle session continuity
    #     # metadata= { ... }
    # )

    raw_a2a_response = None
    try:
      logger.info(f"Sending task to remote agent '{agent_name}' via a2a-python SDK.")
      # TODO: Replace with actual a2a-python SDK call
      # raw_a2a_response = await self.a2a_client.send_message(
      # target_agent_address, # or agent_name directly if SDK supports it
      # a2a_message_payload
      # )
      # Faking a response for now to allow further refactoring of processing logic
      logger.warning("A2A SDK CALL IS A PLACEHOLDER. Simulating a response.")
      raw_a2a_response = { # Simulated response structure
          "status": "COMPLETED", # or "FAILED", "INPUT_REQUIRED"
          "content": [{"type": "text", "text": f"Simulated response from {agent_name} for: {message}"}],
          "error": None,
          "session_id": state.get('session_id', 'dummy_session'), # a2a might return its own session context
          # "artifacts": [] # If a2a-python handles artifacts separately
      }
      if not raw_a2a_response: # Check if SDK call itself failed to return anything
          logger.error(f"No response received from a2a-python SDK for agent '{agent_name}'.")
          return "Error: No response from communication SDK."

      logger.info(f"Received response from agent '{agent_name}' via a2a-python.")
      logger.debug(f"Raw a2a response from '{agent_name}': {str(raw_a2a_response)[:500]}")

    except Exception as e:
      # TODO: Catch specific a2a-python exceptions
      logger.error(f"Exception during a2a-python SDK call to '{agent_name}': {e}", exc_info=True)
      return f"Error communicating with agent {agent_name}: {str(e)}"

    # TODO: Adapt response processing based on the actual structure of raw_a2a_response
    # The old logic for TaskState (COMPLETED, CANCELED, FAILED, INPUT_REQUIRED) needs to be mapped.

    # Example mapping (highly speculative):
    a2a_status = raw_a2a_response.get("status")
    current_session_id = state.get('session_id', 'unknown_session') # ADK session

    if a2a_status == "COMPLETED": # Assuming a2a-python uses such strings
        state['session_active'] = False # If task is complete, ADK session might become inactive for this agent
        logger.debug(f"ADK Session active for '{current_session_id}' with '{agent_name}' set to False (task completed).")
    elif a2a_status == "INPUT_REQUIRED":
        state['session_active'] = True # ADK session remains active
        logger.info(f"Task for '{agent_name}' requires more input (a2a status). Escalating.")
        tool_context.actions.skip_summarization = True
        tool_context.actions.escalate = True
    elif a2a_status == "FAILED":
        state['session_active'] = False
        error_detail = raw_a2a_response.get("error", {}).get("message", "Unknown error from agent")
        logger.error(f"Task for agent '{agent_name}' failed (a2a status). Error: {error_detail}")
        # ADK tools expect to return data, not raise exceptions typically, unless it's a critical tool failure.
        # The LLM will see this returned error message.
        return f"Agent {agent_name} task failed: {error_detail}"
    elif a2a_status == "CANCELED": # If a2a-python has a canceled state
        state['session_active'] = False
        logger.warning(f"Task for agent '{agent_name}' was canceled (a2a status).")
        return f"Agent {agent_name} task was canceled."
    else: # Other statuses or unknown
        state['session_active'] = True # Default to active if unsure, or map appropriately
        logger.warning(f"Unhandled or unknown task status '{a2a_status}' from agent '{agent_name}'. Assuming session active.")

    # TODO: Adapt artifact and content processing based on a2a-python response structure.
    # The `_convert_a2a_parts_for_adk` function will replace `convert_parts`.
    # It needs to handle text, data, and file artifacts from the a2a_response.
    response_parts_for_adk = []
    if raw_a2a_response.get("content"):
        logger.debug(f"Processing content parts from a2a response for agent '{agent_name}'")
        response_parts_for_adk.extend(self._convert_a2a_parts_for_adk(raw_a2a_response["content"], tool_context))

    # Example: if a2a-python has a separate artifacts list
    # if raw_a2a_response.get("artifacts"):
    #   logger.debug(f"Processing artifacts from a2a response for agent '{agent_name}'")
    #   response_parts_for_adk.extend(self._convert_a2a_artifacts_for_adk(raw_a2a_response["artifacts"], tool_context))

    logger.info(f"send_task for '{agent_name}' (a2a) processed. Returning {len(response_parts_for_adk)} ADK parts.")
    logger.debug(f"send_task for '{agent_name}' (a2a) final ADK response parts: {response_parts_for_adk}")

    if not response_parts_for_adk:
        # If there was a status but no content, provide a status message.
        return f"Task status with agent {agent_name}: {a2a_status if a2a_status else 'No content in response'}"

    return response_parts_for_adk

  def _convert_a2a_parts_for_adk(self, a2a_parts: list, tool_context: ToolContext) -> list:
    """Converts parts from an a2a-python response to ADK compatible output parts."""
    adk_output_parts = []
    logger.debug(f"_convert_a2a_parts_for_adk called with {len(a2a_parts)} a2a parts.")
    for i, a2a_part in enumerate(a2a_parts):
        # TODO: Adapt this based on the actual structure of a2a_part from the SDK
        # Assuming a2a_part is a dict like {"type": "text", "text": "...", "mime_type": "...", "uri": "..."}
        part_type = a2a_part.get("type")
        logger.debug(f"Converting a2a part {i+1}/{len(a2a_parts)}: Type '{part_type}'")

        if part_type == "text":
            text_content = a2a_part.get("text", "")
            adk_output_parts.append(text_content) # ADK tools often return simple strings for text
            logger.debug(f"Converted a2a text part to ADK string: {text_content[:100]}")
        elif part_type == "data": # Or "json", "structured_data" etc.
            data_content = a2a_part.get("data", {}) # Assuming it's JSON serializable
            adk_output_parts.append(data_content) # ADK tools can return dicts
            logger.debug(f"Converted a2a data part to ADK dict: {str(data_content)[:100]}")
        elif part_type == "file" or a2a_part.get("uri"): # Handling files via URI or embedded
            # This part is highly dependent on how a2a-python represents files/artifacts
            file_uri = a2a_part.get("uri")
            file_name = a2a_part.get("name", "unknown_file")
            mime_type = a2a_part.get("mime_type", "application/octet-stream")

            if file_uri:
                # If a2a-python provides a URI (e.g., GCS URI for an artifact)
                # ADK might expect a direct link or a structured dict.
                # For simplicity, returning a dict that the LLM can interpret.
                file_artifact_info = {
                    "file_name": file_name,
                    "mime_type": mime_type,
                    "uri": file_uri,
                    "source": "a2a_artifact"
                }
                adk_output_parts.append(file_artifact_info)
                logger.info(f"Converted a2a file URI part to ADK dict: {file_artifact_info}")
                # If ADK's tool_context needs to save this as an artifact:
                # try:
                #   # This is hypothetical, ADK's save_artifact might need actual bytes or a specific format
                #   # tool_context.save_artifact(file_name, genai_file_part_from_uri)
                #   logger.info(f"Artifact '{file_name}' from URI registered with tool_context (hypothetical).")
                # except Exception as e_artifact:
                #   logger.warning(f"Could not save URI artifact '{file_name}' to tool_context: {e_artifact}")

            elif a2a_part.get("bytes_base64"): # If file bytes are embedded (less common for large files)
                try:
                    file_bytes = base64.b64decode(a2a_part["bytes_base64"])
                    logger.debug(f"Decoded {len(file_bytes)} bytes for embedded file '{file_name}'.")

                    # Create a GenAI Part for ADK's save_artifact
                    genai_file_part = types.Part(
                        inline_data=types.Blob(mime_type=mime_type, data=file_bytes)
                    )
                    if tool_context and hasattr(tool_context, 'save_artifact'):
                        tool_context.save_artifact(file_name, genai_file_part)
                        logger.info(f"Saved embedded artifact '{file_name}' to tool_context.")
                        if hasattr(tool_context, 'actions'):
                            tool_context.actions.skip_summarization = True
                            tool_context.actions.escalate = True
                            logger.debug(f"Set skip_summarization/escalate for embedded artifact '{file_name}'.")

                        # Return info about the saved artifact
                        adk_output_parts.append({"artifact_saved_id": file_name, "mime_type": mime_type})
                    else:
                        logger.warning(f"Could not save embedded artifact '{file_name}': tool_context issue.")
                        adk_output_parts.append({"error": f"Could not process embedded file {file_name}"})
                except Exception as e_b64:
                    logger.error(f"Error decoding base64 for embedded file '{file_name}': {e_b64}")
                    adk_output_parts.append({"error": f"Error decoding file {file_name}"})
            else:
                logger.warning(f"Unknown file part structure in a2a response: {a2a_part}")
                adk_output_parts.append({"error": f"Unknown file structure for {file_name}"})
        else:
            logger.warning(f"Encountered unknown a2a part type: {part_type}. Part: {str(a2a_part)[:100]}")
            adk_output_parts.append(f"Unknown part type from agent: {part_type}")

    return adk_output_parts

# Removed old convert_parts and convert_part methods
# def convert_parts(parts: list[Part], tool_context: ToolContext): ...
# def convert_part(part: Part, tool_context: ToolContext): ...
