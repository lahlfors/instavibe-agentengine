# In tools/instavibe/mcp_server.py

import logging
import os
import sys
from dotenv import load_dotenv

# ======================= CORRECTED ORDER =======================
# 1. Add project root to path
sys.path.append('.')

# 2. Load environment variables first
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# 3. Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)
# ===============================================================

logger.info("--- mcp_server.py: Logging configured ---")

import asyncio
import json
import uvicorn
# import inspect # No longer needed for tool discovery
from opentelemetry import trace
# from google.adk.tools.function_tool import FunctionTool # No longer needed
from mcp.server.fastmcp.starlette_app_factory import create_app
from mcp import types as mcp_types

logger.info("--- mcp_server.py: Attempting to import instavibe... ---")
try:
    import instavibe
    logger.info("--- mcp_server.py: Successfully IMPORTED instavibe ---")
except Exception as e:
    logger.error(f"--- mcp_server.py: FAILED to import instavibe ---", exc_info=True)
    sys.exit(1) # Exit if tools cannot be loaded

# Setup Observability (Assuming tracer is configured elsewhere or to be added)
tracer = trace.get_tracer(__name__)

# Create the MCP application instance using the factory
# Pass the instavibe module to the factory for tool discovery
app = create_app(tools=[instavibe])
logger.info(f"MCP Server: App created. Found tools: {list(app.tools.keys())}")


@app.list_tools()
async def list_tools() -> list[mcp_types.Tool]:
    """MCP handler to list available tools."""
    with tracer.start_as_current_span("list_tools") as span:
        # Get tools directly from the app's registry
        mcp_tool_schemas = list(app.tools.values())
        span.set_attribute("tool.count", len(mcp_tool_schemas))
        logger.info(f"MCP Server: Advertising {len(mcp_tool_schemas)} tools: {list(app.tools.keys())}")
        return mcp_tool_schemas

@app.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[mcp_types.TextContent | mcp_types.ImageContent | mcp_types.EmbeddedResource]:
    """MCP handler to execute a tool call."""
    with tracer.start_as_current_span("call_tool") as span:
        span.set_attribute("tool.name", name)
        span.set_attribute("tool.arguments", str(arguments))
        logger.info(f"MCP Server: Received call_tool request for '{name}' with args: {arguments}")

        # Get the tool from the framework's registry
        tool_to_call = app.tools.get(name)
        if tool_to_call:
            try:
                logger.info(f"MCP Server: Calling tool '{name}' function")
                # The app.tools entry contains the schema and the function
                # We call the .func attribute which is the decorated async function
                result = await tool_to_call.func(**arguments)
                response_text = json.dumps(result, indent=2)

                logger.info(f"MCP Server: Tool '{name}' executed successfully.")
                span.set_status(trace.StatusCode.OK)
                return [mcp_types.TextContent(type="text", text=response_text)]
            except Exception as e:
                logger.error(f"MCP Server: Error executing tool '{name}': {e}", exc_info=True)
                span.record_exception(e)
                span.set_status(trace.StatusCode.ERROR, str(e))
                error_text = json.dumps({"error": f"Failed to execute tool '{name}': {str(e)}"})
                return [mcp_types.TextContent(type="text", text=error_text)]
        else:
            logger.warning(f"MCP Server: Tool '{name}' not found in app.tools.")
            span.set_status(trace.StatusCode.ERROR, f"Tool not found: {name}")
            error_text = json.dumps({"error": f"Tool '{name}' not found."})
            return [mcp_types.TextContent(type="text", text=error_text)]

if __name__ == "__main__":
    logger.info(f"Starting MCP Server on port {os.environ.get('PORT', 8080)}")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
