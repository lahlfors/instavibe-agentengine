# adk_mcp_server.py
import asyncio
import json
import uvicorn
import os
import logging
from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor # For OTLP export
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter # CHANGED: Using OTLP gRPC Exporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME as OTEL_SERVICE_NAME_KEY
from opentelemetry.instrumentation.logging import LoggingInstrumentor
# Corrected import: setup_google_cloud_logging is the standardized name
from agents.app.utils.logging_setup import setup_google_cloud_logging
# Comments updated to reflect OTLP usage for direct export

from mcp import types as mcp_types
from mcp.server.lowlevel import Server

from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Mount, Route


from google.adk.tools.function_tool import FunctionTool


from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type

from instavibe import create_event,create_post # instavibe.py also needs logging setup

# from opentelemetry.propagate import set_global_textmap_propagator # REMOVED: Incorrect import
# GcpCloudTraceFormatPropagator REMOVED - Deprecated
# from opentelemetry.propagators.composite import CompositePropagator # REMOVED: Unused import
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator # This is correct

# Load environment variables from the root .env file first.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# Define service name for observability
SERVICE_NAME = "tools-mcp-server"
LOG_LEVEL = logging.INFO # Or logging.DEBUG, or from env var

# 0. Configure Global Propagator
# Using W3C TraceContextTextMapPropagator for trace context propagation.
# Correct method is trace.set_propagator()
# trace.set_propagator(TraceContextTextMapPropagator()) # This will be set after TracerProvider

# If you need baggage or other propagators, use CompositePropagator:
# trace.set_propagator(
#     CompositePropagator([
#         TraceContextTextMapPropagator(),
#         # BaggagePropagator(), # Example if baggage is used
#     ])
# )

# 1. Initialize OpenTelemetry Tracer Provider
# Configure an OTLP exporter to send traces to a local OpenTelemetry Collector via gRPC.
# The Collector (running as a sidecar) will then export to Google Cloud Trace.
# Default OTLP gRPC endpoint is localhost:4317. `insecure=True` is used for localhost communication.
otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)

# The BatchSpanProcessor processes spans in batches before exporting.
span_processor = BatchSpanProcessor(otlp_exporter)

resource = Resource(attributes={
    OTEL_SERVICE_NAME_KEY: SERVICE_NAME,
    "service.instance.id": f"{SERVICE_NAME}-worker-{os.getpid()}" # Added service.instance.id
})

# Add the span processor to the TracerProvider.
provider = TracerProvider(resource=resource, active_span_processor=span_processor)
trace.set_tracer_provider(provider)

# Set the global propagator using the correct API
trace.set_global_propagator(TraceContextTextMapPropagator())

# 2. Instrument logging for OpenTelemetry
LoggingInstrumentor().instrument(set_logging_format=True)

# 3. Then setup Google Cloud logging
setup_google_cloud_logging(log_level=LOG_LEVEL, service_name=SERVICE_NAME)

# Get logger AFTER setup
logger = logging.getLogger(__name__)
logger.info(f"'{SERVICE_NAME}' initialized with OpenTelemetry and Cloud Logging.")

APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("APP_PORT", 8080))
logger.info(f"MCP Server configured to run on {APP_HOST}:{APP_PORT}")


event_tool = FunctionTool(create_event)
post_tool = FunctionTool(create_post)

available_tools = {
    event_tool.name: event_tool,
    post_tool.name: post_tool,
}

# Create a named MCP Server instance
app = Server("adk-tool-mcp-server")
sse = SseServerTransport("/messages/")


@app.list_tools()
async def list_tools() -> list[mcp_types.Tool]:
  """MCP handler to list available tools."""
  # Convert the ADK tool's definition to MCP format
  mcp_tool_schema_event = adk_to_mcp_tool_type(event_tool)
  mcp_tool_schema_post = adk_to_mcp_tool_type(post_tool)
  logger.info(f"MCP Server: Received list_tools request. Advertising tools: '{mcp_tool_schema_event.name}', '{mcp_tool_schema_post.name}'.")
  logger.debug(f"Event tool schema: {mcp_tool_schema_event}, Post tool schema: {mcp_tool_schema_post}")
  return [mcp_tool_schema_event,mcp_tool_schema_post]

@app.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[mcp_types.TextContent | mcp_types.ImageContent | mcp_types.EmbeddedResource]:
  """MCP handler to execute a tool call."""
  logger.info(f"MCP Server: Received call_tool request for '{name}' with args: {arguments}")

  # Look up the tool by name in our dictionary
  tool_to_call = available_tools.get(name)
  if tool_to_call:
    try:
      logger.debug(f"Executing ADK tool '{name}' with arguments: {arguments}")
      adk_response = await tool_to_call.run_async(
          args=arguments,
          tool_context=None, # Consider if a mock or minimal context is needed
      )
      logger.info(f"MCP Server: ADK tool '{name}' executed successfully.")
      logger.debug(f"ADK response for tool '{name}': {adk_response}")

      response_text = json.dumps(adk_response) # Keep it compact for MCP transport
      return [mcp_types.TextContent(type="text", text=response_text)]

    except Exception as e:
      logger.error(f"MCP Server: Error executing ADK tool '{name}': {e}", exc_info=True)
      error_text = json.dumps({"error": f"Failed to execute tool '{name}': {str(e)}"})
      return [mcp_types.TextContent(type="text", text=error_text)]
  else:
      logger.warning(f"MCP Server: Tool '{name}' not found.")
      error_text = json.dumps({"error": f"Tool '{name}' not implemented."})
      return [mcp_types.TextContent(type="text", text=error_text)]

# --- MCP Remote Server ---
async def handle_sse(request):
  """Runs the MCP server over standard input/output."""
  # Use the stdio_server context manager from the MCP library
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
  logger.info("Launching MCP Server exposing ADK tools...")
  try:
    # Ensure APP_PORT is an integer for uvicorn
    uvicorn_port = APP_PORT if isinstance(APP_PORT, int) else int(str(APP_PORT))
    # Pass log_config=None to uvicorn if using global logging setup,
    # or configure uvicorn's logging separately if needed.
    # For now, relying on our global setup.
    asyncio.run(uvicorn.run(starlette_app, host=APP_HOST, port=uvicorn_port, log_config=None))
  except KeyboardInterrupt:
    logger.info("MCP Server stopped by user.")
  except Exception as e:
    logger.critical(f"MCP Server encountered a critical error at startup/runtime: {e}", exc_info=True)
  finally:
    logger.info("MCP Server process exiting.")
# --- End MCP Server ---