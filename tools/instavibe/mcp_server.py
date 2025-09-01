import os
import logging
from dotenv import load_dotenv
import json
import aiohttp
from opentelemetry import trace, propagate
import opentelemetry.semconv._incubating.attributes.gen_ai_attributes as ai_semconv
from common.observability import setup_observability
from agents.app.utils.communication import call_http_endpoint
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

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

@mcp_server.tool()
async def create_post(author_name: str, text: str, sentiment: str, base_url: str = BASE_URL, *, headers: dict = get_http_headers()):
    """
    Sends a POST request to the /posts endpoint to create a new post.
    """
    parent_context = extract_parent_context(headers)
    with tracer.start_as_current_span("tool.create_post", context=parent_context) as span:
        span.set_attribute("tool.name", "create_post")
        span.set_attribute("tool.input.author_name", author_name)
        span.set_attribute("tool.input.text", text)
        span.set_attribute("tool.input.sentiment", sentiment)
        url = f"{base_url}/posts"
        http_headers = {"Content-Type": "application/json"}
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
                headers=http_headers,
                json=payload
            )
            logger.info(f"Successfully created post for {author_name}.")
            span.set_attribute("tool.output", json.dumps(response))
            span.set_attribute("tool.execution.status", "success")
            span.set_status(trace.Status(trace.StatusCode.OK))
            return response
        except aiohttp.ClientError as e:
            logger.error(f"Error creating post: {e}")
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="AIOHTTP ClientError"))
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response from {url}: {e}")
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="JSONDecodeError"))
            return None
        except Exception as e:
            logger.error(f"Unexpected error in create_post: {e}", exc_info=True)
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="Unexpected error"))
            return None

@mcp_server.tool()
async def create_event(event_name: str, description: str, event_date: str, locations: list, attendee_names: list[str], base_url: str = BASE_URL, *, headers: dict = get_http_headers()):
    """
    Sends a POST request to the /events endpoint to create a new event registration.
    """
    parent_context = extract_parent_context(headers)
    with tracer.start_as_current_span("tool.create_event", context=parent_context) as span:
        span.set_attribute("tool.name", "create_event")
        span.set_attribute("tool.input.event_name", event_name)
        span.set_attribute("tool.input.description", description)
        span.set_attribute("tool.input.event_date", event_date)
        span.set_attribute("tool.input.locations", json.dumps(locations))
        span.set_attribute("tool.input.attendee_names", json.dumps(attendee_names))
        url = f"{base_url}/events"
        http_headers = {"Content-Type": "application/json"}
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
                headers=http_headers,
                json=payload
            )
            logger.info(f"Successfully created event registration for {event_name}.")
            span.set_attribute("tool.output", json.dumps(response))
            span.set_attribute("tool.execution.status", "success")
            span.set_status(trace.Status(trace.StatusCode.OK))
            return response
        except aiohttp.ClientError as e:
            logger.error(f"Error creating event registration: {e}")
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="AIOHTTP ClientError"))
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response from {url}: {e}")
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="JSONDecodeError"))
            return None
        except Exception as e:
            logger.error(f"Unexpected error in create_event: {e}", exc_info=True)
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="Unexpected error"))
            return None

@mcp_server.tool()
async def get_person_id_by_name(name: str, base_url: str = BASE_URL, *, headers: dict = get_http_headers()):
    """
    Fetches a person's ID by their name by calling the API.
    """
    parent_context = extract_parent_context(headers)
    with tracer.start_as_current_span("tool.get_person_id_by_name", context=parent_context) as span:
        span.set_attribute("tool.name", "get_person_id_by_name")
        span.set_attribute("tool.input.name", name)
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
            span.set_attribute("tool.output", person_id or "")
            span.set_attribute("tool.execution.status", "success")
            span.set_status(trace.Status(trace.StatusCode.OK))
            return person_id
        except aiohttp.ClientError as e:
            logger.error(f"Error getting person ID by name: {e}")
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="AIOHTTP ClientError"))
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response from {url}: {e}")
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="JSONDecodeError"))
            return None
        except Exception as e:
            logger.error(f"Unexpected error in get_person_id_by_name: {e}", exc_info=True)
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="Unexpected error"))
            return None

@mcp_server.tool()
async def get_person_attended_events(person_id: str, base_url: str = BASE_URL, *, headers: dict = get_http_headers()):
    """
    Fetches events attended by a person by calling the API.
    """
    parent_context = extract_parent_context(headers)
    with tracer.start_as_current_span("tool.get_person_attended_events", context=parent_context) as span:
        span.set_attribute("tool.name", "get_person_attended_events")
        span.set_attribute("tool.input.person_id", person_id)
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
            span.set_attribute("tool.output", json.dumps(response))
            span.set_attribute("tool.execution.status", "success")
            span.set_status(trace.Status(trace.StatusCode.OK))
            return response
        except aiohttp.ClientError as e:
            logger.error(f"Error getting attended events: {e}")
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="AIOHTTP ClientError"))
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response from {url}: {e}")
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="JSONDecodeError"))
            return None
        except Exception as e:
            logger.error(f"Unexpected error in get_person_attended_events: {e}", exc_info=True)
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="Unexpected error"))
            return None

@mcp_server.tool()
async def get_person_posts(person_id: str, base_url: str = BASE_URL, *, headers: dict = get_http_headers()):
    """
    Fetches posts by a person by calling the API.
    """
    parent_context = extract_parent_context(headers)
    with tracer.start_as_current_span("tool.get_person_posts", context=parent_context) as span:
        span.set_attribute("tool.name", "get_person_posts")
        span.set_attribute("tool.input.person_id", person_id)
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
            span.set_attribute("tool.output", json.dumps(response))
            span.set_attribute("tool.execution.status", "success")
            span.set_status(trace.Status(trace.StatusCode.OK))
            return response
        except aiohttp.ClientError as e:
            logger.error(f"Error getting person posts: {e}")
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="AIOHTTP ClientError"))
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response from {url}: {e}")
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="JSONDecodeError"))
            return None
        except Exception as e:
            logger.error(f"Unexpected error in get_person_posts: {e}", exc_info=True)
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="Unexpected error"))
            return None

@mcp_server.tool()
async def get_person_friends(person_id: str, base_url: str = BASE_URL, *, headers: dict = get_http_headers()):
    """
    Fetches friends of a person by calling the API.
    """
    parent_context = extract_parent_context(headers)
    with tracer.start_as_current_span("tool.get_person_friends", context=parent_context) as span:
        span.set_attribute("tool.name", "get_person_friends")
        span.set_attribute("tool.input.person_id", person_id)
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
            span.set_attribute("tool.output", json.dumps(response))
            span.set_attribute("tool.execution.status", "success")
            span.set_status(trace.Status(trace.StatusCode.OK))
            return response
        except aiohttp.ClientError as e:
            logger.error(f"Error getting person friends: {e}")
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="AIOHTTP ClientError"))
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response from {url}: {e}")
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="JSONDecodeError"))
            return None
        except Exception as e:
            logger.error(f"Unexpected error in get_person_friends: {e}", exc_info=True)
            span.record_exception(e)
            span.set_attribute("tool.execution.status", "failed")
            span.set_status(trace.Status(trace.StatusCode.ERROR, description="Unexpected error"))
            return None

if __name__ == "__main__":
    logger.info(f"--- MCP Server '{mcp_server.name}' starting on {host}:{port} ---")
    mcp_server.run(transport="http", host=host, port=port)
