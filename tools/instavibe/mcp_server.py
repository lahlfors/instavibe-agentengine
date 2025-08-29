import os
from fastmcp import FastMCP
import json
import logging
from dotenv import load_dotenv
import aiohttp
from agents.app.utils.communication import call_http_endpoint
from common.observability import setup_observability
from opentelemetry import trace
from opentelemetry.semconv.ai import SpanAttributes as AISpanAttributes

setup_observability("mcp-tool-server")
tracer = trace.get_tracer(__name__)

# Get port from environment variable, default to 8080 for Cloud Run
port = int(os.environ.get("PORT", 8080))
host = "0.0.0.0"

# Initialize MCP Server
mcp_server = FastMCP(
    name="mcp-tool-server"
    # Other Server constructor arguments if needed
)

# --- Register your MCP tools and resources here ---
# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
BASE_URL = os.environ.get("TOOLS_INSTAVIBE_BASE_URL")

@mcp_server.tool()
async def create_post(author_name: str, text: str, sentiment: str, base_url: str = BASE_URL):
    """
    Sends a POST request to the /posts endpoint to create a new post.
    """
    with tracer.start_as_current_span("tool.create_post") as span:
        span.set_attribute(AISpanAttributes.GEN_AI_TOOL_NAME, "create_post")
        tool_params = {
            "author_name": author_name,
            "text": text,
            "sentiment": sentiment,
        }
        span.set_attribute(AISpanAttributes.GEN_AI_TOOL_PARAMETERS, json.dumps(tool_params))
        url = f"{base_url}/posts"
        headers = {"Content-Type": "application/json"}
        payload = {
            "author_name": author_name,
            "text": text,
            "sentiment": sentiment
        }

        try:
            response = await call_http_endpoint(
                source_agent="instavibe_tool",
                target_service="instavibe_app",
                http_method="POST",
                url=url,
                headers=headers,
                json=payload
            )
            print(f"Successfully created post.")
            span.set_attribute(AISpanAttributes.OUTPUT_VALUE, json.dumps(response))
            return response
        except aiohttp.ClientError as e:
            print(f"Error creating post: {e}")
            span.record_exception(e)
            return None
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON response from {url}.")
            span.record_exception(e)
            return None

@mcp_server.tool()
async def create_event(event_name: str, description: str, event_date: str, locations: list, attendee_names: list[str], base_url: str = BASE_URL):
    """
    Sends a POST request to the /events endpoint to create a new event registration.
    """
    with tracer.start_as_current_span("tool.create_event") as span:
        span.set_attribute(AISpanAttributes.GEN_AI_TOOL_NAME, "create_event")
        tool_params = {
            "event_name": event_name,
            "description": description,
            "event_date": event_date,
            "locations": locations,
            "attendee_names": attendee_names,
        }
        span.set_attribute(AISpanAttributes.GEN_AI_TOOL_PARAMETERS, json.dumps(tool_params))
        url = f"{base_url}/events"
        headers = {"Content-Type": "application/json"}
        payload = {
            "event_name": event_name,
            "description": description,
            "event_date": event_date,
            "locations": locations,
            "attendee_names": attendee_names,
        }

        try:
            response = await call_http_endpoint(
                source_agent="instavibe_tool",
                target_service="instavibe_app",
                http_method="POST",
                url=url,
                headers=headers,
                json=payload
            )
            print(f"Successfully created event registration.")
            span.set_attribute(AISpanAttributes.OUTPUT_VALUE, json.dumps(response))
            return response
        except aiohttp.ClientError as e:
            print(f"Error creating event registration: {e}")
            span.record_exception(e)
            return None
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON response from {url}.")
            span.record_exception(e)
            return None


@mcp_server.tool()
async def get_person_id_by_name(name: str, base_url: str = BASE_URL):
    """
    Fetches a person's ID by their name by calling the API.
    """
    with tracer.start_as_current_span("tool.get_person_id_by_name") as span:
        span.set_attribute(AISpanAttributes.GEN_AI_TOOL_NAME, "get_person_id_by_name")
        tool_params = {"name": name}
        span.set_attribute(AISpanAttributes.GEN_AI_TOOL_PARAMETERS, json.dumps(tool_params))
        url = f"{base_url}/api/person/by_name/{name}"
        try:
            response = await call_http_endpoint(
                source_agent="instavibe_tool",
                target_service="instavibe_app",
                http_method="GET",
                url=url,
                headers={},
                json={}
            )
            person_id = response.get('person_id') if response else None
            span.set_attribute(AISpanAttributes.OUTPUT_VALUE, person_id)
            return person_id
        except aiohttp.ClientError as e:
            print(f"Error getting person ID by name: {e}")
            span.record_exception(e)
            return None
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON response from {url}.")
            span.record_exception(e)
            return None

@mcp_server.tool()
async def get_person_attended_events(person_id: str, base_url: str = BASE_URL):
    """
    Fetches events attended by a person by calling the API.
    """
    with tracer.start_as_current_span("tool.get_person_attended_events") as span:
        span.set_attribute(AISpanAttributes.GEN_AI_TOOL_NAME, "get_person_attended_events")
        tool_params = {"person_id": person_id}
        span.set_attribute(AISpanAttributes.GEN_AI_TOOL_PARAMETERS, json.dumps(tool_params))
        url = f"{base_url}/api/person/{person_id}/attended_events"
        try:
            response = await call_http_endpoint(
                source_agent="instavibe_tool",
                target_service="instavibe_app",
                http_method="GET",
                url=url,
                headers={},
                json={}
            )
            span.set_attribute(AISpanAttributes.OUTPUT_VALUE, json.dumps(response))
            return response
        except aiohttp.ClientError as e:
            print(f"Error getting attended events: {e}")
            span.record_exception(e)
            return None
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON response from {url}.")
            span.record_exception(e)
            return None

@mcp_server.tool()
async def get_person_posts(person_id: str, base_url: str = BASE_URL):
    """
    Fetches posts by a person by calling the API.
    """
    with tracer.start_as_current_span("tool.get_person_posts") as span:
        span.set_attribute(AISpanAttributes.GEN_AI_TOOL_NAME, "get_person_posts")
        tool_params = {"person_id": person_id}
        span.set_attribute(AISpanAttributes.GEN_AI_TOOL_PARAMETERS, json.dumps(tool_params))
        url = f"{base_url}/api/person/{person_id}/posts"
        try:
            response = await call_http_endpoint(
                source_agent="instavibe_tool",
                target_service="instavibe_app",
                http_method="GET",
                url=url,
                headers={},
                json={}
            )
            span.set_attribute(AISpanAttributes.OUTPUT_VALUE, json.dumps(response))
            return response
        except aiohttp.ClientError as e:
            print(f"Error getting person posts: {e}")
            span.record_exception(e)
            return None
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON response from {url}.")
            span.record_exception(e)
            return None

@mcp_server.tool()
async def get_person_friends(person_id: str, base_url: str = BASE_URL):
    """
    Fetches friends of a person by calling the API.
    """
    with tracer.start_as_current_span("tool.get_person_friends") as span:
        span.set_attribute(AISpanAttributes.GEN_AI_TOOL_NAME, "get_person_friends")
        tool_params = {"person_id": person_id}
        span.set_attribute(AISpanAttributes.GEN_AI_TOOL_PARAMETERS, json.dumps(tool_params))
        url = f"{base_url}/api/person/{person_id}/friends"
        try:
            response = await call_http_endpoint(
                source_agent="instavibe_tool",
                target_service="instavibe_app",
                http_method="GET",
                url=url,
                headers={},
                json={}
            )
            span.set_attribute(AISpanAttributes.OUTPUT_VALUE, json.dumps(response))
            return response
        except aiohttp.ClientError as e:
            print(f"Error getting person friends: {e}")
            span.record_exception(e)
            return None
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON response from {url}.")
            span.record_exception(e)
            return None

# --- Start the server using FastMCP's runner ---
if __name__ == "__main__":
    print(f"--- MCP Server '{mcp_server.name}' starting on {host}:{port} ---")
    mcp_server.run(transport="http", host=host, port=port)
