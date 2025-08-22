import json
import os
from dotenv import load_dotenv
import aiohttp
from agents.app.utils.communication import call_http_endpoint

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
BASE_URL = os.environ.get("TOOLS_INSTAVIBE_BASE_URL")

async def create_post(author_name: str, text: str, sentiment: str, base_url: str = BASE_URL):
    """
    Sends a POST request to the /posts endpoint to create a new post.

    Args:
        author_name (str): The name of the post's author.
        text (str): The content of the post.
        sentiment (str): The sentiment associated with the post (e.g., 'positive', 'negative', 'neutral').
        base_url (str, optional): The base URL of the API. Defaults to BASE_URL.

    Returns:
        dict: The JSON response from the API if the request is successful.
              Returns None if an error occurs.

    Raises:
        aiohttp.ClientError: If there's an issue with the network request (e.g., connection error, timeout).
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
        # Optionally re-raise the exception if the caller needs to handle it
        # raise e
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from {url}.")
        return None

async def create_event(event_name: str, description: str, event_date: str, locations: list, attendee_names: list[str], base_url: str = BASE_URL):
    """
    Sends a POST request to the /events endpoint to create a new event registration.

    Args:
        event_name (str): The name of the event.
        description (str): The detailed description of the event.
        event_date (str): The date and time of the event (ISO 8601 format recommended, e.g., "2025-06-10T09:00:00Z").
        locations (list): A list of location dictionaries. Each dictionary should contain:
                          'name' (str), 'description' (str, optional),
                          'latitude' (float), 'longitude' (float),
                          'address' (str, optional).
        attendee_names (list[str]): A list of names of the people attending the event.
        base_url (str, optional): The base URL of the API. Defaults to BASE_URL.

    Returns:
        dict: The JSON response from the API if the request is successful.
              Returns None if an error occurs.

    Raises:
        aiohttp.ClientError: If there's an issue with the network request (e.g., connection error, timeout).
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
        # Optionally re-raise the exception if the caller needs to handle it
        # raise e
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from {url}.")
        return None


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
        # The API returns {"person_id": "..."} on success
        return response.get('person_id') if response else None
    except aiohttp.ClientError as e:
        print(f"Error getting person ID by name: {e}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from {url}.")
        return None

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
