import logging
from agents.app.utils.communication import call_agent_capability

# A helper function to reduce repetition
async def _call_instavibe_tool(tool_name: str, arguments: dict):
    """Helper to call a tool on the instavibe MCP server via the client agent."""
    logging.info(f"Social Agent: A2A call to '{tool_name}' with args: {arguments}")
    response = await call_agent_capability(
        source_agent="social_agent",
        target_agent="Platform MCP Client Agent",
        capability="call_mcp_tool",
        prompt={"tool_name": tool_name, "arguments": arguments}
    )
    if response and isinstance(response, dict) and response.get("error"):
        logging.error(f"Error from platform_mcp_client_agent for tool '{tool_name}': {response['error']}")
        return None
    return response

async def get_person_attended_events(person_id: str) -> list[dict] | None:
    """
    Fetches events attended by a specific person by calling the platform_mcp_client_agent.
    """
    return await _call_instavibe_tool(
        tool_name="get_person_attended_events",
        arguments={"person_id": person_id}
    )

async def get_person_id_by_name(name: str) -> str | None:
    """
    Fetches the person_id for a given name by calling the platform_mcp_client_agent.
    """
    # This tool returns a dict like {'person_id': '...'}
    response = await _call_instavibe_tool(
        tool_name="get_person_id_by_name",
        arguments={"name": name}
    )
    return response.get("person_id") if response else None


async def get_person_posts(person_id: str) -> list[dict] | None:
    """
    Fetches posts written by a specific person by calling the platform_mcp_client_agent.
    """
    return await _call_instavibe_tool(
        tool_name="get_person_posts",
        arguments={"person_id": person_id}
    )


async def get_person_friends(person_id: str) -> list[dict] | None:
    """
    Fetches friends for a specific person by calling the platform_mcp_client_agent.
    """
    return await _call_instavibe_tool(
        tool_name="get_person_friends",
        arguments={"person_id": person_id}
    )