import os
import uvicorn
from mcp.server.fastmcp.server import Server
import json
import logging
from dotenv import load_dotenv
import aiohttp
from agents.app.utils.communication import call_http_endpoint

# Get port from environment variable, default to 8080 for Cloud Run
port = int(os.environ.get("PORT", 8080))
host = "0.0.0.0"

# Initialize MCP Server
mcp_server = Server(
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
        return response
    except aiohttp.ClientError as e:
        print(f"Error creating post: {e}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from {url}.")
        return None

@mcp_server.tool()
async def create_event(event_name: str, description: str, event_date: str, locations: list, attendee_names: list[str], base_url: str = BASE_URL):
    """
    Sends a POST request to the /events endpoint to create a new event registration.
    """
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
        return response
    except aiohttp.ClientError as e:
        print(f"Error creating event registration: {e}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from {url}.")
        return None


@mcp_server.tool()
async def get_person_id_by_name(name: str, base_url: str = BASE_URL):
    """
    Fetches a person's ID by their name by calling the API.
    """
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
        return response.get('person_id') if response else None
    except aiohttp.ClientError as e:
        print(f"Error getting person ID by name: {e}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from {url}.")
        return None

@mcp_server.tool()
async def get_person_attended_events(person_id: str, base_url: str = BASE_URL):
    """
    Fetches events attended by a person by calling the API.
    """
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
        return response
    except aiohttp.ClientError as e:
        print(f"Error getting attended events: {e}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from {url}.")
        return None

@mcp_server.tool()
async def get_person_posts(person_id: str, base_url: str = BASE_URL):
    """
    Fetches posts by a person by calling the API.
    """
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
        return response
    except aiohttp.ClientError as e:
        print(f"Error getting person posts: {e}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from {url}.")
        return None

@mcp_server.tool()
async def get_person_friends(person_id: str, base_url: str = BASE_URL):
    """
    Fetches friends of a person by calling the API.
    """
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
        return response
    except aiohttp.ClientError as e:
        print(f"Error getting person friends: {e}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from {url}.")
        return None

# Get the Starlette app instance from the MCP Server instance
app = mcp_server.app

# --- Start the server using Uvicorn ---
if __name__ == "__main__":
    print(f"--- MCP Server '{mcp_server.name}' starting Uvicorn on {host}:{port} ---")
    uvicorn.run(app, host=host, port=port)
