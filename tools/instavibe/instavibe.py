import requests
import json
import os
import logging # Added
from dotenv import load_dotenv

# Get logger. Since this module is used by mcp_server.py,
# it will use the logging setup from there if mcp_server.py is the entry point.
# If this module were run or imported standalone, it would need its own setup.
logger = logging.getLogger(__name__)

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
BASE_URL = os.environ.get("TOOLS_INSTAVIBE_BASE_URL")
if not BASE_URL:
    logger.warning("TOOLS_INSTAVIBE_BASE_URL environment variable is not set. API calls will likely fail.")

def create_post(author_name: str, text: str, sentiment: str, base_url: str = BASE_URL):
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
        requests.exceptions.RequestException: If there's an issue with the network request (e.g., connection error, timeout).
    """
    url = f"{base_url}/posts"
    headers = {"Content-Type": "application/json"}
    payload = {
        "author_name": author_name,
        "text": text,
        "sentiment": sentiment
    }

    try:
        logger.info(f"Sending create_post request to {url} for author '{author_name}'. Sentiment: {sentiment}.")
        logger.debug(f"Payload for create_post: {payload}")
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        logger.info(f"Successfully created post for author '{author_name}'. Status Code: {response.status_code}")
        return response.json()
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error creating post for '{author_name}': {e}. Response: {e.response.text if e.response else 'N/A'}", exc_info=True)
        return {"error": str(e), "details": e.response.text if e.response else "No response body"}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error creating post for '{author_name}': {e}", exc_info=True)
        return {"error": str(e)}
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON response from {url} for create_post. Response text: {response.text if 'response' in locals() else 'N/A'}", exc_info=True)
        return {"error": "JSONDecodeError", "details": response.text if 'response' in locals() else "No response object"}

def create_event(event_name: str, description: str, event_date: str, locations: list, attendee_names: list[str], base_url: str = BASE_URL):
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
        requests.exceptions.RequestException: If there's an issue with the network request (e.g., connection error, timeout).
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
        logger.info(f"Sending create_event request to {url} for event '{event_name}'. Attendees: {attendee_names}.")
        logger.debug(f"Payload for create_event: {payload}")
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        logger.info(f"Successfully created event '{event_name}'. Status Code: {response.status_code}")
        return response.json()
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error creating event '{event_name}': {e}. Response: {e.response.text if e.response else 'N/A'}", exc_info=True)
        return {"error": str(e), "details": e.response.text if e.response else "No response body"}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error creating event '{event_name}': {e}", exc_info=True)
        return {"error": str(e)}
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON response from {url} for create_event. Response text: {response.text if 'response' in locals() else 'N/A'}", exc_info=True)
        return {"error": "JSONDecodeError", "details": response.text if 'response' in locals() else "No response object"}




  
