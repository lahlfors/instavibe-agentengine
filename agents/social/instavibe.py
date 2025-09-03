from datetime import datetime
from tools.instavibe import instavibe as instavibe_client

async def get_person_attended_events(person_id: str) -> list[dict] | None:
    """
    Fetches events attended by a specific person by calling the instavibe tool.
    """
    print(f"Social Agent: Fetching attended events for person_id: {person_id}")
    return await instavibe_client.get_person_attended_events(person_id=person_id)

async def get_person_id_by_name(name: str) -> str | None:
    """
    Fetches the person_id for a given name by calling the instavibe tool.
    """
    print(f"Social Agent: Fetching person_id for name: {name}")
    return await instavibe_client.get_person_id_by_name(name=name)


async def get_person_posts(person_id: str) -> list[dict] | None:
    """
    Fetches posts written by a specific person by calling the instavibe tool.
    """
    print(f"Social Agent: Fetching posts for person_id: {person_id}")
    return await instavibe_client.get_person_posts(person_id=person_id)


async def get_person_friends(person_id: str) -> list[dict] | None:
    """
    Fetches friends for a specific person by calling the instavibe tool.
    """
    print(f"Social Agent: Fetching friends for person_id: {person_id}")
    return await instavibe_client.get_person_friends(person_id=person_id)