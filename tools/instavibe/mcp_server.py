import os
import logging
from dotenv import load_dotenv
import json
import aiohttp
from opentelemetry import trace, propagate
from common.observability import setup_observability
from agents.app.utils.communication import call_http_endpoint
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
import functools

load_dotenv()
os.environ["SERVICE_NAME"] = os.environ.get("SERVICE_NAME", "mcp-tool-server")
setup_observability()

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

port = int(os.environ.get("PORT", 8080))
host = "0.0.0.0"

BASE_URL = os.environ.get("TOOLS_INSTAVIBE_BASE_URL")

mcp_server = FastMCP(name="mcp-tool-server")
logger.info("FastMCP server initialized.")

def extract_parent_context(headers: dict):
    """Helper to extract trace context from FastMCP request headers."""
    if headers:
        try:
            return propagate.extract(headers)
        except Exception as e:
            logger.debug(f"Could not extract parent context from headers: {e}")
    return None

def instrument_tool(tool_name: str):
    """
    A decorator that wraps a tool function with OpenTelemetry span creation,
    attribute recording, and exception handling.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            headers = kwargs.get("headers", {})
            parent_context = extract_parent_context(headers)

            with tracer.start_as_current_span(f"tool.{tool_name}", context=parent_context) as span:
                span.set_attribute("tool.name", tool_name)
                # Log input arguments automatically
                for key, value in kwargs.items():
                    if key != "headers": # Don't log headers
                        if isinstance(value, (list, dict)):
                            span.set_attribute(f"tool.input.{key}", json.dumps(value))
                        else:
                            span.set_attribute(f"tool.input.{key}", str(value))

                try:
                    # Execute the actual tool logic
                    result = await func(*args, **kwargs)

                    # On success
                    span.set_attribute("tool.output", json.dumps(result))
                    span.set_attribute("tool.execution.status", "success")
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    return result
                except Exception as e:
                    # On any failure
                    logger.error(f"Error in tool '{tool_name}': {e}", exc_info=True)
                    span.record_exception(e)
                    span.set_attribute("tool.execution.status", "failed")
                    span.set_status(trace.Status(trace.StatusCode.ERROR, description=str(e)))
                    return None
        return wrapper
    return decorator

@mcp_server.tool()
@instrument_tool("create_post")
async def create_post(author_name: str, text: str, sentiment: str, base_url: str = BASE_URL, *, headers: dict = get_http_headers()):
    """
    Sends a POST request to the /posts endpoint to create a new post.
    (Instrumentation is handled by the decorator).
    """
    url = f"{base_url}/posts"
    http_headers = {"Content-Type": "application/json"}
    payload = {
        "author_name": author_name,
        "text": text,
        "sentiment": sentiment
    }
    response = await call_http_endpoint(
        source_agent="instavibe_tool",
        target_service="instavibe_app",
        http_method="POST",
        url=url,
        headers=http_headers,
        json=payload
    )
    logger.info(f"Successfully created post for {author_name}.")
    return response

@mcp_server.tool()
@instrument_tool("create_event")
async def create_event(event_name: str, description: str, event_date: str, locations: list, attendee_names: list[str], base_url: str = BASE_URL, *, headers: dict = get_http_headers()):
    """
    Sends a POST request to the /events endpoint to create a new event registration.
    (Instrumentation is handled by the decorator).
    """
    url = f"{base_url}/events"
    http_headers = {"Content-Type": "application/json"}
    payload = {
        "event_name": event_name,
        "description": description,
        "event_date": event_date,
        "locations": locations,
        "attendee_names": attendee_names,
    }
    response = await call_http_endpoint(
        source_agent="instavibe_tool",
        target_service="instavibe_app",
        http_method="POST",
        url=url,
        headers=http_headers,
        json=payload
    )
    logger.info(f"Successfully created event registration for {event_name}.")
    return response

@mcp_server.tool()
@instrument_tool("get_person_id_by_name")
async def get_person_id_by_name(name: str, base_url: str = BASE_URL, *, headers: dict = get_http_headers()):
    """
    Fetches a person's info by their name by calling the API. Returns the full JSON response.
    (Instrumentation is handled by the decorator).
    """
    url = f"{base_url}/api/person/by_name/{name}"
    response = await call_http_endpoint(
        source_agent="instavibe_tool",
        target_service="instavibe_app",
        http_method="GET",
        url=url,
        headers={},
        json={}
    )
    return response

@mcp_server.tool()
@instrument_tool("get_person_attended_events")
async def get_person_attended_events(person_id: str, base_url: str = BASE_URL, *, headers: dict = get_http_headers()):
    """
    Fetches events attended by a person by calling the API.
    (Instrumentation is handled by the decorator).
    """
    url = f"{base_url}/api/person/{person_id}/attended_events"
    response = await call_http_endpoint(
        source_agent="instavibe_tool",
        target_service="instavibe_app",
        http_method="GET",
        url=url,
        headers={},
        json={}
    )
    return response

@mcp_server.tool()
@instrument_tool("get_person_posts")
async def get_person_posts(person_id: str, base_url: str = BASE_URL, *, headers: dict = get_http_headers()):
    """
    Fetches posts by a person by calling the API.
    (Instrumentation is handled by the decorator).
    """
    url = f"{base_url}/api/person/{person_id}/posts"
    response = await call_http_endpoint(
        source_agent="instavibe_tool",
        target_service="instavibe_app",
        http_method="GET",
        url=url,
        headers={},
        json={}
    )
    return response

@mcp_server.tool()
@instrument_tool("get_person_friends")
async def get_person_friends(person_id: str, base_url: str = BASE_URL, *, headers: dict = get_http_headers()):
    """
    Fetches friends of a person by calling the API.
    (Instrumentation is handled by the decorator).
    """
    url = f"{base_url}/api/person/{person_id}/friends"
    response = await call_http_endpoint(
        source_agent="instavibe_tool",
        target_service="instavibe_app",
        http_method="GET",
        url=url,
        headers={},
        json={}
    )
    return response

if __name__ == "__main__":
    logger.info(f"--- MCP Server '{mcp_server.name}' starting on {host}:{port} ---")
    mcp_server.run(transport="http", host=host, port=port)
