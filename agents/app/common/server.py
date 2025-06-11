# agents/app/common/server.py
import os
from dotenv import load_dotenv
import asyncio
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer # Using http.server for simplicity
from urllib.parse import urlparse, parse_qs
import json

from .types import AgentCard # Relative import
from .task_manager import AgentTaskManager # Relative import

logger = logging.getLogger(__name__)

class A2AServer:
    def __init__(self, agent_card: AgentCard, task_manager: AgentTaskManager, host: str = "localhost", port: int = 8080):
        self.agent_card = agent_card
        self.task_manager = task_manager

        # Load .env file from the root project directory
        load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

        # Cloud Run compatibility:
        # PORT environment variable is set by Cloud Run.
        # Agent-specific A2A_HOST/A2A_PORT should be resolved by the caller and passed in via host/port args.
        _cloud_run_port_str = os.environ.get("PORT")
        if _cloud_run_port_str:
            try:
                self.port = int(_cloud_run_port_str)
                logger.info(f"Using Cloud Run PORT: {self.port}")
            except ValueError:
                logger.warning(f"Invalid Cloud Run PORT value '{_cloud_run_port_str}', falling back to constructor port {port}.")
                self.port = port
            # For Cloud Run, host must be '0.0.0.0' to be accessible from outside the container.
            self.host = "0.0.0.0"
            logger.info(f"Using Cloud Run host: {self.host}")
        else:
            # Not running in Cloud Run (or PORT not set), use provided host/port arguments.
            self.port = port
            self.host = host

        logger.info(f"A2AServer configured for host '{self.host}' and port {self.port}")
        self.server = None # Will be initialized in start()

    def start(self):
        if self.server:
            logger.warning("Server already started.")
            return

        # Simple HTTP server for demonstration
        # A real implementation would use Flask, FastAPI, or similar with ADK integrations
        class RequestHandler(BaseHTTPRequestHandler):
            # Reference to outer class members
            _agent_card = self.agent_card
            _task_manager = self.task_manager

            def do_GET(self):
                if self.path == '/agent-card':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    # A real AgentCard would have a to_dict() method or similar
                    card_dict = {
                        "name": self._agent_card.name,
                        "description": self._agent_card.description,
                        "url": self._agent_card.url,
                        "version": self._agent_card.version,
                        # Add other fields as necessary
                    }
                    self.wfile.write(json.dumps(card_dict).encode('utf-8'))
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Not Found")

            async def _handle_task_async(self, post_data_dict):
                # This is where ADK's task processing logic would integrate
                return await self._task_manager.handle_request(post_data_dict)

            def do_POST(self):
                if self.path == '/handle-task': # Example endpoint
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    try:
                        post_data_dict = json.loads(post_data.decode('utf-8'))
                        logger.info(f"Received task data: {post_data_dict}")

                        # For simplicity, running async within sync handler
                        # A proper async framework (FastAPI, Quart) would handle this better
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        result = loop.run_until_complete(self._handle_task_async(post_data_dict))
                        loop.close()

                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps(result).encode('utf-8'))
                    except json.JSONDecodeError:
                        self.send_response(400)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode('utf-8'))
                    except Exception as e:
                        logger.error(f"Error handling task: {e}", exc_info=True)
                        self.send_response(500)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Internal server error"}).encode('utf-8'))
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Not Found")

        try:
            self.server = HTTPServer((self.host, self.port), RequestHandler)
            logger.info(f"A2AServer starting on http://{self.host}:{self.port}")
            self.server.serve_forever()
        except Exception as e:
            logger.error(f"Could not start A2AServer: {e}", exc_info=True)
            self.server = None # Ensure server is None if start failed
        finally:
            if self.server:
                self.server.server_close()
                logger.info("A2AServer stopped.")
                self.server = None

    def stop(self):
        if self.server:
            logger.info("A2AServer stopping...")
            self.server.shutdown() # Graceful shutdown
        else:
            logger.info("A2AServer not running or already stopped.")
print("DEBUG: common.server loaded with Cloud Run compatibility") # Debug print
