import asyncio
import threading
import uvicorn
import logging

# It's good practice to have a logger for utility modules as well.
logger = logging.getLogger(__name__)

def start_uvicorn_in_thread(a2a_app, host: str, port: int):
    """
    Starts a Uvicorn server in a separate daemon thread to run an ASGI application.

    Args:
        a2a_app: The ASGI application (e.g., A2AStarletteApplication instance) to run.
        host: The host address for Uvicorn to bind to (e.g., "0.0.0.0").
        port: The port number for Uvicorn to listen on.
    """
    loop = asyncio.new_event_loop()

    def run_server_sync():
        asyncio.set_event_loop(loop)
        try:
            logger.info(f"Starting Uvicorn server in thread on {host}:{port} for app: {type(a2a_app).__name__}")
            config = uvicorn.Config(a2a_app, host=host, port=port, log_level="info", loop="asyncio")
            server = uvicorn.Server(config)
            # server.run() # This is blocking and not async
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
