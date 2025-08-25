# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import json
import uvicorn
import os
from dotenv import load_dotenv
import inspect
import logging
from opentelemetry import trace
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type
from common.observability import setup_observability
import instavibe
import sys
sys.path.append('.')

from mcp import types as mcp_types
from mcp.server.lowlevel import Server

from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Mount, Route

# Load environment variables from the root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# Configure basic logging at the top of your script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configure OpenTelemetry Tracer
setup_observability(service_name="mcp-server")
tracer = trace.get_tracer(__name__)

APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("APP_PORT", 8080))


# --- Dynamic Tool Discovery ---
available_tools = {
    name: FunctionTool(func)
    for name, func in inspect.getmembers(instavibe, inspect.iscoroutinefunction)
}
logging.info(f"MCP Server: Discovered tools: {list(available_tools.keys())}")

# Create a named MCP Server instance
app = Server("adk-tool-mcp-server")
sse = SseServerTransport("/messages/")


@app.list_tools()
async def list_tools() -> list[mcp_types.Tool]:
    """MCP handler to list available tools."""
    with tracer.start_as_current_span("list_tools") as span:
        mcp_tool_schemas = [
            adk_to_mcp_tool_type(tool) for tool in available_tools.values()
        ]
        span.set_attribute("tool.count", len(mcp_tool_schemas))
        logging.info(f"MCP Server: Advertising {len(mcp_tool_schemas)} tools.")
        return mcp_tool_schemas

@app.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[mcp_types.TextContent | mcp_types.ImageContent | mcp_types.EmbeddedResource]:
    """MCP handler to execute a tool call."""
    with tracer.start_as_current_span("call_tool") as span:
        span.set_attribute("tool.name", name)
        span.set_attribute("tool.arguments", str(arguments))
        logging.info(f"MCP Server: Received call_tool request for '{name}' with args: {arguments}")

        tool_to_call = available_tools.get(name)
        if tool_to_call:
            try:
                adk_response = await tool_to_call.run_async(
                    args=arguments,
                    tool_context=None,
                )
                logging.info(f"MCP Server: ADK tool '{name}' executed successfully.")
                span.set_attribute("tool.response", str(adk_response))
                span.set_status(trace.StatusCode.OK)

                response_text = json.dumps(adk_response, indent=2)
                return [mcp_types.TextContent(type="text", text=response_text)]

            except Exception as e:
                logging.error(f"MCP Server: Error executing ADK tool '{name}': {e}", exc_info=True)
                span.record_exception(e)
                span.set_status(trace.StatusCode.ERROR, str(e))
                error_text = json.dumps({"error": f"Failed to execute tool '{name}': {str(e)}"})
                return [mcp_types.TextContent(type="text", text=error_text)]
        else:
            logging.warning(f"MCP Server: Tool '{name}' not found.")
            span.set_status(trace.StatusCode.ERROR, f"Tool '{name}' not found.")
            error_text = json.dumps({"error": f"Tool '{name}' not implemented."})
            return [mcp_types.TextContent(type="text", text=error_text)]

async def handle_sse(request):
    """Runs the MCP server over standard input/output."""
    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await app.run(
            streams[0], streams[1], app.create_initialization_options()
        )

starlette_app = Starlette(
    debug=True,
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ],
)

if __name__ == "__main__":
    logging.info("Launching MCP Server exposing ADK tools...")
    try:
        uvicorn_port = APP_PORT if isinstance(APP_PORT, int) else int(str(APP_PORT))
        asyncio.run(uvicorn.run(starlette_app, host=APP_HOST, port=uvicorn_port))
    except KeyboardInterrupt:
        logging.info("\nMCP Server stopped by user.")
    except Exception as e:
        logging.error(f"MCP Server encountered an error: {e}", exc_info=True)
    finally:
        logging.info("MCP Server process exiting.")
