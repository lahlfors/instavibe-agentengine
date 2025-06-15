# agents/app/common/server.py
import os
from dotenv import load_dotenv
import asyncio
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer # Using http.server for simplicity
from urllib.parse import urlparse, parse_qs # Keep for query param parsing if needed for health checks
import json
import logging # Ensure logging is imported

# Removed ADK-specific imports: AgentCard, AgentTaskManager
from agents.app.common.graph_state import OrchestratorState # For creating initial state
from agents.app.graph_builder import build_graph # To load the LangGraph app

logger = logging.getLogger(__name__)
# Configure basic logging for the module.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')


class LangGraphServer:
    """
    A simple HTTP server to expose the LangGraph application.
    Replaces the ADK-specific A2AServer.
    For production use, a more robust framework like FastAPI or Flask is recommended.
    """
    def __init__(self, host: str = "localhost", port: int = 8080):
        # Load .env file from the root project directory
        dotenv_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
        if os.path.exists(dotenv_path):
            load_dotenv(dotenv_path=dotenv_path)
            logging.info("LangGraphServer: .env file loaded.")
        else:
            logging.warning(f"LangGraphServer: .env file not found at {dotenv_path}. Required API keys might be missing.")

        try:
            self.graph_app = build_graph()
            logging.info("LangGraph application built successfully.")
        except Exception as e:
            logging.error(f"Failed to build LangGraph application: {e}", exc_info=True)
            self.graph_app = None # Ensure graph_app is None if build fails

        # Cloud Run compatibility for port and host
        _cloud_run_port_str = os.environ.get("PORT")
        if _cloud_run_port_str:
            try:
                self.port = int(_cloud_run_port_str)
                logging.info(f"Using Cloud Run PORT: {self.port}")
            except ValueError:
                logging.warning(f"Invalid Cloud Run PORT value '{_cloud_run_port_str}', falling back to constructor port {port}.")
                self.port = port
            self.host = "0.0.0.0" # For Cloud Run, host must be '0.0.0.0'
            logging.info(f"Using Cloud Run host: {self.host}")
        else:
            self.port = port
            self.host = host

        logging.info(f"LangGraphServer configured for host '{self.host}' and port {self.port}")
        self.server = None

    def start(self):
        if not self.graph_app:
            logging.error("LangGraph application not loaded. Server cannot start.")
            return

        if self.server:
            logging.warning("Server already started.")
            return

        # Define a local class for the request handler to access self.graph_app
        class LangGraphRequestHandler(BaseHTTPRequestHandler):
            _graph_app_instance = self.graph_app # Closure for graph_app

            def do_GET(self):
                if self.path == '/health':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Not Found")

            async def _invoke_graph_async(self, initial_state: OrchestratorState):
                # Configuration for the graph invocation, if any (e.g., recursion limit)
                config = {"recursion_limit": 25}
                # LangGraph's ainvoke is async
                final_state = await self._graph_app_instance.ainvoke(initial_state.dict(), config=config)
                return final_state

            def do_POST(self):
                if self.path == '/invoke':
                    content_length = int(self.headers['Content-Length'])
                    post_data_bytes = self.rfile.read(content_length)
                    try:
                        post_data_dict = json.loads(post_data_bytes.decode('utf-8'))
                        user_request = post_data_dict.get("user_request")

                        if not user_request:
                            self.send_response(400)
                            self.send_header('Content-type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps({"error": "Missing 'user_request' in JSON body"}).encode('utf-8'))
                            return

                        logging.info(f"Received invocation request for LangGraph: {user_request[:100]}...")

                        # Create initial state for the graph
                        # Note: OrchestratorState fields default to None if not provided here.
                        initial_state = OrchestratorState(user_request=user_request)

                        # http.server is synchronous, so we run the async graph invocation
                        # in a new event loop. This is a simplified approach.
                        # For production, use an async framework like FastAPI.
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            result_state = loop.run_until_complete(self._invoke_graph_async(initial_state))
                        finally:
                            loop.close()

                        final_output = result_state.get("final_output", "No final_output in result state.")
                        # The final_output from orchestrator_nodes.output_node should already be a JSON string.
                        # If it's a dict, it needs to be dumped. For now, assume it's a string.

                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        # Assuming final_output is already a JSON string. If it's a dict: json.dumps(final_output).encode...
                        self.wfile.write(final_output.encode('utf-8') if isinstance(final_output, str) else json.dumps(final_output).encode('utf-8'))

                    except json.JSONDecodeError:
                        logging.warning("Invalid JSON received for /invoke.", exc_info=True)
                        self.send_response(400)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode('utf-8'))
                    except Exception as e:
                        logging.error(f"Error processing /invoke request: {e}", exc_info=True)
                        self.send_response(500)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Internal server error", "detail": str(e)}).encode('utf-8'))
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Not Found")

        try:
            self.server = HTTPServer((self.host, self.port), LangGraphRequestHandler)
            logging.info(f"LangGraphServer starting on http://{self.host}:{self.port}")
            self.server.serve_forever()
        except Exception as e:
            logging.error(f"Could not start LangGraphServer: {e}", exc_info=True)
            self.server = None
        finally:
            if self.server:
                self.server.server_close()
                logging.info("LangGraphServer stopped.")
                self.server = None

    def stop(self):
        if self.server:
            logging.info("LangGraphServer stopping...")
            self.server.shutdown() # Should be called from another thread
            # self.server.server_close() # server_close() is called in finally block of start()
        else:
            logging.info("LangGraphServer not running or already stopped.")

# Example usage (optional, for direct execution)
if __name__ == '__main__':
    logging.info("Starting LangGraphServer directly for testing...")
    # Note: Ensure .env is in the correct relative path if running this directly
    # For example, if .env is in project root, and this file is agents/app/common/server.py
    # load_dotenv might need to be called here with correct path for direct execution.
    # The __init__ already handles .env loading assuming a certain structure.

    # This direct execution is for local testing.
    # In a real deployment, you might use a WSGI/ASGI server or Cloud Run.
    server = LangGraphServer(host="localhost", port=8080)
    try:
        server.start()
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received, stopping server...")
    finally:
        server.stop()
