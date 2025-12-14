import logging
import os
import json
import httpx
from typing import Optional, Dict, Any, AsyncGenerator
from google.auth import default
from google.auth.transport.requests import Request
from google.adk.agents import Agent as AdkAgent, InvocationContext
from google.genai.types import Content, Part
from google.adk.events import Event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentCard:
    """
    Represents a simplified Agent Card for governance.
    """
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.name = data.get("name")
        self.description = data.get("description")
        self.capabilities = data.get("capabilities", [])
        self.addresses = data.get("addresses", [])
        self.auth_scheme = data.get("security", {}).get("type", "oauth2")

    @property
    def endpoint_url(self) -> Optional[str]:
        for addr in self.addresses:
            if addr.get("protocol") == "http_json" or addr.get("protocol") == "vertex_api":
                return addr.get("url")
        return None

async def fetch_agent_card(resource_name: str) -> AgentCard:
    """
    Fetches and adapts the Agent Card from a Vertex AI Reasoning Engine resource.
    """
    logger.info(f"Fetching Agent Card for: {resource_name}")
    
    # 1. Parse Resource Name
    try:
        parts = resource_name.split('/')
        # projects/{project}/locations/{location}/reasoningEngines/{id}
        # 0        1         2          3          4                5
        location = parts[3]
    except IndexError:
        raise ValueError(f"Invalid resource name format: {resource_name}")

    # 2. Fetch Resource Definition via Vertex AI API
    credentials, _ = default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    if not credentials.valid:
        credentials.refresh(Request())
        
    api_url = f"https://{location}-aiplatform.googleapis.com/v1beta1/{resource_name}"
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(api_url, headers=headers)
        
        if response.status_code != 200:
            raise RuntimeError(f"Failed to fetch Reasoning Engine details: {response.status_code} - {response.text}")
            
        re_data = response.json()
        
    # 3. Adapt to Agent Card
    card_data = {
        "name": re_data.get("displayName", resource_name),
        "description": re_data.get("description", "Vertex AI Reasoning Engine"),
        "addresses": [
            {
                "protocol": "vertex_api",
                "url": f"https://{location}-aiplatform.googleapis.com/v1beta1/{resource_name}:query"
            }
        ],
        "security": {
            "type": "oauth2",
            "scope": "https://www.googleapis.com/auth/cloud-platform"
        },
        "capabilities": [
            {"name": "query", "description": "Execute a query against the agent"}
        ]
    }
    
    logger.info(f"Synthesized Agent Card for {resource_name}")
    return AgentCard(card_data)

def validate_agent_card(card: AgentCard):
    """
    Implements Zero Trust validation logic.
    """
    logger.info(f"Validating Agent Card: {card.name}")
    
    # 1. Endpoint Integrity Check
    if not card.endpoint_url:
        raise ValueError("Agent Card missing valid endpoint URL")
        
    if "googleapis.com" not in card.endpoint_url:
        raise ValueError(f"Untrusted endpoint domain: {card.endpoint_url}")
        
    # 2. Authentication Check
    if card.auth_scheme != "oauth2":
        raise ValueError(f"Unsupported authentication scheme: {card.auth_scheme}")
        
    logger.info("Agent Card validation passed.")

class GovernedReasoningEngineAgent(AdkAgent):
    """
    A client for Vertex AI Reasoning Engines that implements the Governed A2A flow.
    Replaces RemoteA2aAgent for Vertex AI targets.
    """
    resource_name: str
    name: str
    agent_card: Optional[AgentCard] = None
    _client: Optional[httpx.AsyncClient] = None
    
    def __init__(self, resource_name: str, name: str, **kwargs):
        super().__init__(resource_name=resource_name, name=name, **kwargs)
        self._client = None
        
    def __getstate__(self):
        state = self.__dict__.copy()
        state['_client'] = None  # Don't pickle the client
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._client = None  # Restore as None

    async def initialize(self):
        """Performs Discovery and Validation."""
        try:
            # 1. Discovery
            self.agent_card = await fetch_agent_card(self.resource_name)
            
            # 2. Validation
            validate_agent_card(self.agent_card)
            
            # Setup Client
            self._client = httpx.AsyncClient(timeout=60.0)
            
        except Exception as e:
            logger.error(f"Governance Failure for {self.name}: {e}")
            raise

    async def run_async(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """
        Executes the task using the governed flow with robust stream handling.
        """
        if not self.agent_card:
            await self.initialize()

        # 3. Authorization (Acquire Token)
        credentials, _ = default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        if not credentials.valid:
            credentials.refresh(Request())

        headers = {
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json"
        }

        # 4. Task Execution (Vertex AI :query)
        endpoint = self.agent_card.endpoint_url

        # Extract user prompt from context
        user_prompt = ""
        if ctx.user_content and ctx.user_content.parts:
            user_prompt = ctx.user_content.parts[0].text

        # Prepare Payload (Standard input schema)
        # REMOVED: "config" key that caused the unexpected keyword argument error
        payload = {
            "input": {
                "input": user_prompt
            }
        }

        logger.info(f"Streaming request to {self.name} at {endpoint}")

        try:
            # 1. Open the stream context
            async with self._client.stream("POST", endpoint, headers=headers, json=payload, timeout=90.0) as response:
                
                # 2. Check for Errors FIRST (The Unhappy Path)
                if response.status_code != 200:
                    # Explicitly read the error body from the stream
                    error_body = await response.aread()
                    error_text = error_body.decode()
                    
                    logger.error(f"Vertex AI Error {response.status_code}: {error_text}")
                    yield Event(
                        invocation_id=ctx.invocation_id,
                        author=self.name,
                        content=Content(parts=[Part(text=f"Error {response.status_code}: {error_text}")])
                    )
                    return  # Stop processing

                # 3. Process Success (The Happy Path)
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue  # Skip keep-alive newlines

                    try:
                        # Vertex AI often returns "data: {...}" for SSE
                        clean_line = line.removeprefix("data: ").strip()

                        if clean_line == "[DONE]":
                            break

                        data = json.loads(clean_line)

                        # Extract text based on standard schemas
                        text_chunk = None

                        # Check for ADK Event format
                        if 'content' in data:
                            yield Event(
                                invocation_id=ctx.invocation_id,
                                author=self.name,
                                content=Content(**data.get('content', {}))
                            )
                            continue

                        # Check for standard Reasoning Engine format
                        elif 'output' in data:
                            text_chunk = str(data['output'])

                        # Fallback
                        else:
                            text_chunk = str(data)

                        if text_chunk:
                            yield Event(
                                invocation_id=ctx.invocation_id,
                                author=self.name,
                                content=Content(parts=[Part(text=text_chunk)])
                            )

                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse stream line: {line}")

        except Exception as e:
            logger.error(f"Stream Connection Failure: {e}", exc_info=True)
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=Content(parts=[Part(text=f"Connection Error: {e}")])
            )