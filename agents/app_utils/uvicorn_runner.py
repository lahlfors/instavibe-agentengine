import asyncio
import threading
import uvicorn
import logging

# It's good practice to have a logger for utility modules as well.
logger = logging.getLogger(__name__)

# Import A2AServer for type hinting
from python_a2a.server import A2AServer

def start_uvicorn_in_thread(a2a_app: A2AServer, host: str, port: int):
    """
    Starts a Uvicorn server in a separate daemon thread to run an ASGI application.

    Args:
        a2a_app: The A2AServer instance (which has a .build() method returning an ASGI app).
        host: The host address for Uvicorn to bind to (e.g., "0.0.0.0").
        port: The port number for Uvicorn to listen on.
    """
    loop = asyncio.new_event_loop()

    def run_server_sync():
        asyncio.set_event_loop(loop)
        try:
            # If a2a_app is an A2AServer instance, call build() to get the ASGI app
            app_to_run = a2a_app
            if hasattr(a2a_app, 'build') and callable(a2a_app.build):
                app_to_run = a2a_app.build()
                logger.info(f"Called .build() on A2AServer, running type: {type(app_to_run).__name__}")

            logger.info(f"Starting Uvicorn server in thread on {host}:{port} for app: {type(app_to_run).__name__}")
            config = uvicorn.Config(app_to_run, host=host, port=port, log_level="info", loop="asyncio")
            server = uvicorn.Server(config)
            loop.run_until_complete(server.serve())
        except Exception as e:
            logger.error(f"Error running Uvicorn server in thread: {e}", exc_info=True)
        finally:
            logger.info(f"Uvicorn server thread on {host}:{port} stopping.")
            # loop.close() # Be careful with closing loops run by other threads if not managed properly

    thread = threading.Thread(target=run_server_sync, daemon=True)
    thread.start()
    logger.info(f"Uvicorn server thread started for {host}:{port}.")
    return thread
