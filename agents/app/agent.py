from google.adk.agents import BaseAgent
from google.genai.types import Content, Part
from google.adk.events import Event
from google.adk.agents.invocation_context import InvocationContext
from google.generativeai import GenerativeModel
from typing import Any, AsyncIterator

class AppAgent(BaseAgent):
    """
    A simple agent that includes the Pydantic v1 fix
    to prevent client session leaks.
    """

    # 1. Declare the model_client field
    model_client: Any = None

    # 2. Add the __post_init__ hook
    def __post_init__(self):
        """(Pydantic v1) Runs after model is initialized."""
        super().__post_init__()  # Call the parent's post_init
        if self.model:
            self.model_client = GenerativeModel(self.model)
        else:
            print(f"WARNING: {self.__class__.__name__} initialized without a model name.")

    # 3. Example run method using the shared client
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncIterator[Event]:

        if not self.model_client:
            yield Event(author=self.name, content=Content(parts=[Part(text="AppAgent: Model client not initialized")]))
            return

        # Example: Get user's prompt
        user_prompt = ""
        if ctx.user_content and ctx.user_content.parts:
            user_prompt = ctx.user_content.parts[0].text

        # 4. Use self.model_client directly
        response = await self.model_client.generate_content_async(
            f"You are a helpful app agent. User said: {user_prompt}"
        )

        yield Event(author=self.name, content=response.candidates[0].content)

# This is what the loader looks for
root_agent = AppAgent(
    model="gemini-1.5-flash"
)
