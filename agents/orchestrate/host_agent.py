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
from agents.app.remote.remote_agent_connection import (
    RemoteAgentConnections,
    TaskUpdateCallback
)
from agents.app.common.client import A2ACardResolver
from agents.app.common.types import (
    AgentCard,
    Message,
    TaskState,
    Task,
    TaskSendParams,
    TextPart,
    DataPart,
    Part,
    TaskStatusUpdateEvent,
)

logger = logging.getLogger(__name__)

class HostAgent:
  """The orchestrate agent.

  This is the agent responsible for choosing which remote agents to send
  tasks to and coordinate their work.
  """

  def __init__(
      self,
      remote_agent_addresses: List[str],
      task_callback: TaskUpdateCallback | None = None
  ):
    logger.info(f"HostAgent initializing with remote_agent_addresses: {remote_agent_addresses}")
    self.task_callback = task_callback
    self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
    self.cards: dict[str, AgentCard] = {}
    if remote_agent_addresses:
      for address in remote_agent_addresses:
        try:
          logger.debug(f"Resolving agent card for address: {address}")
          card_resolver = A2ACardResolver(address)
          card = card_resolver.get_agent_card()
          if card and card.name:
            remote_connection = RemoteAgentConnections(card)
            self.remote_agent_connections[card.name] = remote_connection
            self.cards[card.name] = card
            logger.info(f"Registered remote agent: {card.name} at {address}")
          else:
            logger.warning(f"Could not resolve card or card name for address: {address}")
        except Exception as e:
          logger.error(f"Error initializing remote agent connection for address {address}: {e}", exc_info=True)
    else:
      logger.warning("HostAgent initialized with no remote_agent_addresses.")

    self._update_agents_string()
    logger.debug(f"Initial self.agents string: {self.agents}")

  def _update_agents_string(self):
    """Helper to update the self.agents string."""
    agent_info = []
    for ra_card in self.cards.values(): # Iterate over cards directly
      agent_info.append(json.dumps({"name": ra_card.name, "description": ra_card.description}))
    self.agents = '\n'.join(agent_info)
    logger.debug(f"Updated self.agents string: {self.agents}")

  def register_agent_card(self, card: AgentCard):
    logger.info(f"Registering new agent card: {card.name if card else 'None'}")
    if not card or not card.name:
      logger.warning("Attempted to register an invalid or unnamed card.")
      return

    remote_connection = RemoteAgentConnections(card)
    self.remote_agent_connections[card.name] = remote_connection
    self.cards[card.name] = card
    self._update_agents_string()
    logger.info(f"Agent card '{card.name}' registered successfully.")

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
    if not self.remote_agent_connections:
      logger.warning("No remote agent connections available to list.")
      return []

    remote_agent_info = []
    for card_name, card in self.cards.items():
      info = {"name": card.name, "description": card.description}
      remote_agent_info.append(info)
      logger.debug(f"Adding agent to list: {info}")

    logger.info(f"Returning {len(remote_agent_info)} remote agents.")
    logger.debug(f"Remote agent list: {remote_agent_info}")
    return remote_agent_info

  async def send_task(
      self,
      agent_name: str,
      message: str,
      tool_context: ToolContext):
    """Sends a task either streaming (if supported) or non-streaming.

    This will send a message to the remote agent named agent_name.

    Args:
      agent_name: The name of the agent to send the task to.
      message: The message to send to the agent for the task.
      tool_context: The tool context this method runs in.

    Yields:
      A dictionary of JSON data.
    """
    logger.info(f"send_task tool called. Target agent: '{agent_name}'. Message (first 100 chars): '{message[:100]}...'")
    logger.debug(f"Full message for send_task to '{agent_name}': {message}")
    logger.debug(f"Tool context state at send_task call: {tool_context.state if tool_context else 'None'}")

    if agent_name not in self.remote_agent_connections:
      logger.error(f"Agent '{agent_name}' not found in remote_agent_connections.")
      raise ValueError(f"Agent {agent_name} not found")

    state = tool_context.state
    state['agent'] = agent_name # Record current agent being interacted with

    card = self.cards.get(agent_name)
    if not card:
        logger.error(f"Card for agent '{agent_name}' not found in self.cards, though connection exists.")
        raise ValueError(f"Card for agent {agent_name} not found")

    client = self.remote_agent_connections[agent_name]
    if not client:
      logger.error(f"Client not available for agent '{agent_name}' in remote_agent_connections.")
      raise ValueError(f"Client not available for {agent_name}")

    # Ensure taskId, sessionId, and messageId are properly managed
    taskId = state.get('task_id')
    if not taskId:
        taskId = str(uuid.uuid4())
        state['task_id'] = taskId
        logger.info(f"Generated new taskId: {taskId} for agent '{agent_name}' within session {state.get('session_id')}")
    else:
        logger.info(f"Using existing taskId: {taskId} for agent '{agent_name}' within session {state.get('session_id')}")

    sessionId = state.get('session_id')
    if not sessionId:
        sessionId = str(uuid.uuid4())
        state['session_id'] = sessionId
        logger.warning(f"session_id was not in state for send_task, generated new one: {sessionId}")

    # Reconstruct metadata handling similar to original logic
    request_metadata = state.get('input_message_metadata', {}).copy()
    messageId = request_metadata.get('message_id', str(uuid.uuid4()))
    if 'message_id' not in request_metadata: # if it was generated
        request_metadata['message_id'] = messageId
        logger.info(f"Generated new messageId: {messageId} for this task part.")
    request_metadata.update({'conversation_id': sessionId}) # Ensure conversation_id is present

    task_send_params = TaskSendParams(
        id=taskId,
        sessionId=sessionId,
        message=Message(
            role="user",
            parts=[TextPart(text=message)],
            metadata=request_metadata,
        ),
        acceptedOutputModes=["text", "text/plain", "image/png"],
        metadata={'conversation_id': sessionId, 'orchestrator_task_id': taskId},
    )
    logger.debug(f"Constructed TaskSendParams for agent '{agent_name}': {task_send_params}")

    # Variable to hold the task response object from the remote agent
    actual_task_response: Optional[Task] = None
    try:
      logger.info(f"Sending task to remote agent '{agent_name}' (Client: {client})")
      actual_task_response = await client.send_task(task_send_params, self.task_callback)
      logger.info(f"Received response from remote agent '{agent_name}'. Task object: {'Exists' if actual_task_response else 'None'}")
      logger.debug(f"Full task response object from '{agent_name}': {actual_task_response}")
    except Exception as e:
      logger.error(f"Exception during client.send_task to '{agent_name}': {e}", exc_info=True)
      raise # Re-raise to allow ADK or caller to handle

    # Restore original logic for processing the task response
    if actual_task_response and actual_task_response.status:
      logger.info(f"Task status from '{agent_name}': {actual_task_response.status.state}")
      logger.debug(f"Full task status details: {actual_task_response.status}")
      state['session_active'] = actual_task_response.status.state not in [
          TaskState.COMPLETED,
          TaskState.CANCELED,
          TaskState.FAILED,
          TaskState.UNKNOWN,
      ]
      logger.debug(f"Session active for '{sessionId}' set to: {state['session_active']}")

      if actual_task_response.status.state == TaskState.INPUT_REQUIRED:
        logger.info(f"Task for '{agent_name}' requires more input. Escalating.")
        tool_context.actions.skip_summarization = True
        tool_context.actions.escalate = True
      elif actual_task_response.status.state == TaskState.CANCELED:
        logger.warning(f"Task '{taskId}' for agent '{agent_name}' was canceled.")
        raise ValueError(f"Agent {agent_name} task {taskId} is cancelled") # Original behavior
      elif actual_task_response.status.state == TaskState.FAILED:
        error_detail = actual_task_response.status.error.message if actual_task_response.status.error else "Unknown error"
        logger.error(f"Task '{taskId}' for agent '{agent_name}' failed. Error: {error_detail}")
        raise ValueError(f"Agent {agent_name} task {taskId} failed: {error_detail}") # Original behavior
    else:
      logger.warning(f"Received no task object or no status from '{agent_name}'. Task: {actual_task_response}")
      state['session_active'] = False # Original behavior
      logger.info(f"Session active for '{sessionId}' set to False due to invalid/missing task status.")

    response_parts_to_return = []
    if actual_task_response and actual_task_response.status and actual_task_response.status.message:
      logger.debug(f"Processing message parts from task status for agent '{agent_name}'")
      response_parts_to_return.extend(convert_parts(actual_task_response.status.message.parts, tool_context))

    if actual_task_response and actual_task_response.artifacts:
      logger.debug(f"Processing artifacts for agent '{agent_name}'")
      for artifact in actual_task_response.artifacts:
        response_parts_to_return.extend(convert_parts(artifact.parts, tool_context))

    logger.info(f"send_task for '{agent_name}' processed. Returning {len(response_parts_to_return)} parts.")
    logger.debug(f"send_task for '{agent_name}' final response parts: {response_parts_to_return}")
    return response_parts_to_return

def convert_parts(parts: list[Part], tool_context: ToolContext):
  logger.debug(f"convert_parts called with {len(parts)} parts.")
  rval = []
  for i, p in enumerate(parts):
    logger.debug(f"Converting part {i+1}/{len(parts)}: Type '{p.type if hasattr(p, 'type') else 'Unknown type'}'")
    converted = convert_part(p, tool_context)
    logger.debug(f"Converted part {i+1} to: {type(converted)} (Value snippet: {str(converted)[:100]}...)")
    rval.append(converted)
  return rval

def convert_part(part: Part, tool_context: ToolContext):
  # Ensure part is not None and has a 'type' attribute
  if not part or not hasattr(part, 'type'):
    logger.warning(f"convert_part received invalid part: {part}")
    return f"Unknown type: Invalid part object"

  logger.debug(f"Converting part of type: {part.type}")
  if part.type == "text":
    logger.debug(f"Text part content (first 100 chars): {part.text[:100] if hasattr(part, 'text') else 'N/A'}")
    return part.text
  elif part.type == "data":
    logger.debug(f"Data part content (type): {type(part.data if hasattr(part, 'data') else None)}")
    logger.debug(f"Data part content (value snippet): {str(part.data)[:100] if hasattr(part, 'data') else 'N/A'}")
    return part.data
  elif part.type == "file":
    if not hasattr(part, 'file') or not part.file:
        logger.warning("File part received but 'part.file' attribute is missing or None.")
        return "Error: Invalid file part structure"

    file_id = part.file.name if hasattr(part.file, 'name') else 'unknown_file'
    mime_type = part.file.mimeType if hasattr(part.file, 'mimeType') else 'application/octet-stream'
    logger.info(f"Processing file part: ID '{file_id}', MIME Type '{mime_type}'")

    if not hasattr(part.file, 'bytes') or part.file.bytes is None:
        logger.warning(f"File part '{file_id}' has no 'bytes' attribute or bytes are None.")
        # Depending on how ADK handles this, you might return an error or a placeholder
        return f"Error: File part '{file_id}' has no content"

    try:
      file_bytes = base64.b64decode(part.file.bytes)
      logger.debug(f"Decoded {len(file_bytes)} bytes for file '{file_id}'.")
    except Exception as e:
      logger.error(f"Error base64 decoding file bytes for '{file_id}': {e}", exc_info=True)
      return f"Error decoding file content for {file_id}"

    genai_file_part = types.Part(
      inline_data=types.Blob(
        mime_type=mime_type,
        data=file_bytes))

    if tool_context and hasattr(tool_context, 'save_artifact'):
      tool_context.save_artifact(file_id, genai_file_part)
      logger.info(f"Saved artifact '{file_id}' to tool_context.")
      if hasattr(tool_context, 'actions'):
        tool_context.actions.skip_summarization = True
        tool_context.actions.escalate = True
        logger.debug(f"Set skip_summarization and escalate to True for file artifact '{file_id}'.")
    else:
        logger.warning(f"Could not save artifact '{file_id}': tool_context is None or missing save_artifact/actions.")

    return DataPart(data = {"artifact-file-id": file_id}) # Return a DataPart as per original logic

  logger.warning(f"Encountered unknown part type: {part.type}")
  return f"Unknown type: {part.type}"
