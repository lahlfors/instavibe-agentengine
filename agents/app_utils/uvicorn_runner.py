# agents/app_utils/uvicorn_runner.py
import asyncio
import threading
import uvicorn
from typing import Callable # For Callable type hint
import logging

logger = logging.getLogger(__name__)
if not logger.handlers: # Avoid duplicate basicConfig
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())

def start_uvicorn_in_thread(asgi_app: Callable, host: str, port: int):
    """
    Starts the Uvicorn server in a separate daemon thread.
    Args:
        asgi_app: The ASGI application callable (e.g., result of A2AServer.build()).
        host: The host to bind Uvicorn to.
        port: The port to bind Uvicorn to.
    """
    # Each thread needs its own event loop if using asyncio.run like this.
    # However, uvicorn.Server().serve() when run in a separate thread
    # often manages its own loop or integrates with the one set by asyncio.run.
    # The key is that uvicorn.run or server.serve is blocking in the context of the thread.

    def run_server_sync():
        # It's generally safer for the thread to create and manage its own loop
        # if it's doing significant async work directly with asyncio.
        # However, uvicorn.run itself can often handle this.
        # For simplicity and common patterns with uvicorn in a thread:
        logger.info(f"Uvicorn thread: Starting server on {host}:{port} for app {getattr(asgi_app, '__name__', type(asgi_app).__name__)}")
        try:
            uvicorn.run(asgi_app, host=host, port=port, log_level="info")
        except Exception as e:
            logger.error(f"Uvicorn thread: Error running server on {host}:{port}: {e}", exc_info=True)
        finally:
            logger.info(f"Uvicorn thread: Server on {host}:{port} has shut down.")

    thread = threading.Thread(target=run_server_sync, daemon=True)
    thread.start()
    logger.info(f"Uvicorn server thread for {host}:{port} initiated.")
    return thread
