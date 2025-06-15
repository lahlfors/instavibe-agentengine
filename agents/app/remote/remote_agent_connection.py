# agents/app/remote/remote_agent_connection.py
import httpx # Added
import json # Added
from ..common.types import AgentCard, Task, TaskSendParams, Message, Part, TextPart # Relative import, added Message, Part, TextPart for potential future use
from typing import Callable

TaskUpdateCallback = Callable[[dict], None] # Placeholder type

class RemoteAgentConnections:
    def __init__(self, card: AgentCard):
        self.card = card
        print(f"DEBUG: RemoteAgentConnections initialized for card: {self.card.name if self.card else 'None'}") # Debug print

    async def send_task(self, request: TaskSendParams, callback: TaskUpdateCallback | None = None) -> Task | None:
        print(f"DEBUG: RemoteAgentConnections sending task to {self.card.address if self.card else 'no card'}")

        if not self.card or not self.card.address:
            print("ERROR: Agent card or address is missing.")
            return None

        target_url = f"{self.card.address}:query"
        print(f"DEBUG: Target URL for agent call: {target_url}")

        text_input = None
        if request and request.message and request.message.parts and len(request.message.parts) > 0:
            # Assuming the first part is TextPart and contains the primary input.
            # This is a simplification. A real implementation would handle various Part types.
            if isinstance(request.message.parts[0], TextPart) and hasattr(request.message.parts[0], 'text'):
                 text_input = request.message.parts[0].text
            elif hasattr(request.message.parts[0], 'text'): # Fallback if not strictly TextPart but has text
                 text_input = request.message.parts[0].text


        if not text_input:
            # Fallback: try to get text from a simple dict structure if parts[0] is a dict
            # This is to accommodate current placeholder structures for TaskSendParams
            if request and request.message and request.message.parts and len(request.message.parts) > 0:
                part_zero = request.message.parts[0]
                if isinstance(part_zero, dict) and 'text' in part_zero:
                    text_input = part_zero['text']
                # If it's an object with a text attribute (but not TextPart, caught above)
                elif hasattr(part_zero, 'text') and not isinstance(part_zero, TextPart):
                     text_input = part_zero.text


        if not text_input:
            print("ERROR: No text input found in request.message.parts[0].text")
            # Check if request.input can be used directly (if it's a simple string)
            if request and hasattr(request, 'input') and isinstance(request.input, str):
                text_input = request.input
                print(f"DEBUG: Using request.input as text_input: {text_input}")
            else:
                print("ERROR: No suitable text input found in request.input either.")
                return None # Or handle as appropriate, e.g., send empty input if allowed by target

        payload = {"input": text_input}
        print(f"DEBUG: Payload for agent call: {json.dumps(payload)}")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(target_url, json=payload, timeout=30.0)
                response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

                response_data = response.json()
                print(f"DEBUG: Received response: {response_data}")

                # This is a highly simplified mock Task object creation
                # A real implementation would need to map the actual response structure to the Task structure.
                # Assuming response structure like: {"message": {"parts": [{"text": "some response"}]}}
                if response_data.get("message", {}).get("parts", []) and \
                   len(response_data["message"]["parts"]) > 0 and \
                   response_data["message"]["parts"][0].get("text"):
                    # Placeholder: a real Task object would be constructed here from response_data
                    print(f"DEBUG: Text part found in response: {response_data['message']['parts'][0]['text']}")
                    # task_response = Task(...) # Create Task object from response_data
                    # For now, just returning an empty Task as per instructions for successful call
                    if callback:
                        callback({"update": "task_completed_placeholder", "data": response_data})
                    return Task()
                else:
                    print(f"DEBUG: Received response with no expected text part: {response_data}")
                    if callback:
                        callback({"update": "task_completed_with_no_text_placeholder", "data": response_data})
                    return Task() # Return empty task as per instructions

            except httpx.HTTPStatusError as e:
                print(f"ERROR: HTTP error occurred: {e.response.status_code} - {e.response.text}")
                # Example for future: return Task(status=TaskStatus(state=TaskState.FAILED, error_message=str(e)))
                if callback:
                    callback({"update": "task_failed_http_error", "error": str(e)})
                return None
            except httpx.RequestError as e:
                print(f"ERROR: Request error occurred: {e}")
                if callback:
                    callback({"update": "task_failed_request_error", "error": str(e)})
                return None
            except json.JSONDecodeError as e:
                print(f"ERROR: Failed to decode JSON response: {e}")
                if callback:
                    callback({"update": "task_failed_json_error", "error": str(e)})
                return None
            except Exception as e: # Catch any other unexpected errors
                print(f"ERROR: An unexpected error occurred: {e}")
                if callback:
                    callback({"update": "task_failed_unexpected_error", "error": str(e)})
                return None

print("DEBUG: remote.remote_agent_connection loaded") # Debug print
