import logging
import os
import json
import httpx
from typing import Optional, Dict, Any, AsyncGenerator
from google.auth import default
from google.auth.transport.requests import Request
from google.adk.agents import Agent, InvocationContext
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
    
    Since Vertex AI RE doesn't serve /.well-known/agent.json, we:
    1. Fetch the resource definition via Vertex AI API
    2. Adapt it into an Agent Card structure
    """
    logger.info(f"Fetching Agent Card for: {resource_name}")
    
    # 1. Parse Resource Name
    # projects/{project}/locations/{location}/reasoningEngines/{id}
    try:
        parts = resource_name.split('/')
        project_id = parts[1]
        location = parts[3]
        resource_id = parts[5]
    except IndexError:
        raise ValueError(f"Invalid resource name format: {resource_name}")

    # 2. Fetch Resource Definition via Vertex AI API
    # We use Google Auth to make an authenticated request
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
    # We synthesize an Agent Card based on the RE metadata
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

def validate_agent_card(card: AgentCard, expected_project: Optional[str] = None):
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

from google.adk.agents import Agent as AdkAgent

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
        # Initialize Pydantic model
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
        Executes the task using the governed flow.
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
            
        payload = {
            "message": user_prompt
            # We could pass session_id etc if needed
        }
        
        logger.info(f"Sending governed request to {self.name} at {endpoint}")
        
        try:
            response = await self._client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            
            # 5. Response Processing
            # Vertex AI returns a list of events/chunks
            # We need to stream them back as ADK Events
            
            # Note: The :query endpoint might return a single JSON response or stream
            # For simplicity, we assume standard JSON response for now (non-streaming HTTP)
            # If we need streaming, we'd use stream=True and parse SSE/JSON-stream
            
            data = response.json()
            
            # The response from :query is typically a list of events/objects
            # We iterate and yield them
            if isinstance(data, list):
                for item in data:
                    # Convert to ADK Event if possible, or wrap text
                    if isinstance(item, dict):
                        # Try to extract text
                        text = None
                        if 'content' in item and 'parts' in item['content']:
                             text = item['content']['parts'][0].get('text')
                        elif 'output' in item:
                             text = str(item['output'])
                             
                        if text:
                            yield Event(
                                invocation_id=ctx.invocation_id,
                                author=self.name,
                                content=Content(parts=[Part(text=text)])
                            )
            else:
                # Single object
                yield Event(
                    invocation_id=ctx.invocation_id,
                    author=self.name,
                    content=Content(parts=[Part(text=str(data))])
                )
                
        except Exception as e:
            logger.error(f"Task Execution Failure: {e}")
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=Content(parts=[Part(text=f"Error: {e}")])
            )
