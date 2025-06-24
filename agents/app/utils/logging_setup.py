import logging
import os
import google.cloud.logging as cloud_logging
from google.cloud.logging_v2.handlers import CloudLoggingHandler

# Initialize a module-level logger for this utility
logger = logging.getLogger(__name__)

def setup_cloud_logging(
    logger_to_configure: logging.Logger = logging.getLogger(),
    log_level: int = logging.INFO,
    gcp_log_name: str = "application_log", # Default GCP log stream name
    debug_local: bool = True # If True, keeps console output for local debug
):
    """
    Sets up Google Cloud Logging for the provided logger.

    Args:
        logger_to_configure: The specific logger instance to configure.
                             Defaults to the root logger.
        log_level: The minimum logging level to capture (e.g., logging.INFO, logging.DEBUG).
        gcp_log_name: The name for the log stream in Google Cloud Logging.
        debug_local: If True, ensures that logs also go to console (stderr)
                       which is useful for local development/debugging.
                       If False, only Cloud Logging handler is attached (unless
                       other handlers were already present).
    """
    try:
        # Check if running in a GCP environment where ADC are likely available
        # or if local gcloud auth is set up.
        # A more robust check might involve trying to instantiate the client
        # and catching auth errors, but this is a common pattern.
        running_in_gcp = os.environ.get("GOOGLE_CLOUD_PROJECT") is not None

        # Instantiate a client. This will use Application Default Credentials.
        client = cloud_logging.Client()

        # Create a CloudLoggingHandler
        # The 'name' parameter here sets the log stream name in GCP
        cloud_handler = CloudLoggingHandler(client, name=gcp_log_name)
        cloud_handler.setLevel(log_level) # Set the level for the cloud handler

        # Configure the target logger
        logger_to_configure.setLevel(log_level) # Set the overall level for the logger itself

        # Check if a CloudLoggingHandler is already attached to this specific logger
        # to avoid duplicate handlers if this function is called multiple times on the same logger.
        has_cloud_handler = any(isinstance(h, CloudLoggingHandler) for h in logger_to_configure.handlers)

        if not has_cloud_handler:
            logger_to_configure.addHandler(cloud_handler)
            logger.info(
                f"CloudLoggingHandler configured for logger '{logger_to_configure.name}' "
                f"at level {logging.getLevelName(log_level)} to GCP log '{gcp_log_name}'."
            )
        else:
            logger.info(
                f"CloudLoggingHandler already exists for logger '{logger_to_configure.name}'."
            )

        # For local debugging, ensure console output is still present
        # This setup assumes that if not running in GCP, or if debug_local is True,
        # we want to ensure there's a console handler.
        # If running locally and no other handlers are configured,
        # basicConfig might be needed, or we add a StreamHandler.
        # However, client.setup_logging() is more comprehensive if we want to use that.
        # Let's simplify: if debug_local is true, and no stream handlers are present, add one.
        if debug_local:
            has_stream_handler = any(isinstance(h, logging.StreamHandler) and \
                                     not isinstance(h, CloudLoggingHandler) \
                                     for h in logger_to_configure.handlers)
            if not has_stream_handler:
                console_handler = logging.StreamHandler()
                console_handler.setLevel(log_level)
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
                console_handler.setFormatter(formatter)
                logger_to_configure.addHandler(console_handler)
                logger.info(
                    f"Added StreamHandler to logger '{logger_to_configure.name}' for local debugging."
                )

        # Alternative: Simpler setup using client.setup_logging()
        # This helper attaches a Cloud Logging handler to Python's root logger.
        # client.setup_logging(log_level=log_level)
        # logger.info(f"Google Cloud Logging (via setup_logging()) configured at level: {logging.getLevelName(log_level)}")

    except Exception as e:
        # Fallback or error logging if Cloud Logging setup fails
        # This might happen due to auth issues, especially locally without gcloud auth.
        logger.error(f"Failed to set up Google Cloud Logging: {e}", exc_info=True)
        logger.warning("Logging will proceed with standard Python logging configuration (if any).")
        # Optionally, ensure a basic console logger is set up as a fallback
        if not logger_to_configure.handlers:
            logging.basicConfig(level=log_level)
            logger.info("Basic logging configured as fallback.")

if __name__ == "__main__":
    # Example usage:
    # To configure the root logger:
    # setup_cloud_logging(log_level=logging.DEBUG, gcp_log_name="my_root_app_log")
    # logging.info("This is an info from root logger.")
    # logging.debug("This is a debug from root logger.")

    # To configure a specific logger:
    my_custom_logger = logging.getLogger("my_module")
    setup_cloud_logging(logger_to_configure=my_custom_logger, log_level=logging.INFO, gcp_log_name="my_module_log")
    my_custom_logger.info("This is an info from my_module.")
    my_custom_logger.error("This is an error from my_module.")

    # Example of a logger that might not have the cloud handler if not explicitly configured
    other_logger = logging.getLogger("other_module")
    other_logger.info("This info from other_module might only go to console if root logger was not cloud-configured or if it has its own basicConfig.")

    # If you used client.setup_logging() on the root logger, all loggers would inherit by default.
    # The current setup_cloud_logging function targets a specific logger instance.
    # For a general application setup, configuring the root logger is often the goal.
    # Let's refine setup_cloud_logging to be more like client.setup_logging() but with options.

    print("\n--- Refined Example ---")
    # For most app-wide setups, configuring the root logger is common.
    # The `client.setup_logging()` is often the simplest way.
    # Let's make our utility primarily use that, but keep the targeted approach as an option or internal detail.

    def setup_global_cloud_logging(log_level: int = logging.INFO, service_name: str = "python-app"):
        """
        Sets up Google Cloud Logging globally using client.setup_logging().
        This attaches a Cloud Logging handler to Python's root logger.
        It also ensures that trace IDs and span IDs are picked up by the handler.

        Args:
            log_level: The minimum logging level to capture.
            service_name: Name for the log stream in GCP, often app/service name.
        """
        try:
            client = cloud_logging.Client()
            # The setup_logging() method adds a handler to the root logger.
            # It also ensures that the handler can pick up trace_id, span_id, etc.
            # from OpenTelemetry context if available.
            # The `name` of the log stream in GCP is typically derived from the service
            # when running on GCP, or can be specified. The `CloudLoggingHandler`
            # allows a `name` parameter. `setup_logging` itself doesn't directly expose it.
            # However, the logs will be associated with the GCP resource.
            # For more control over the log name, manually adding CloudLoggingHandler is better.
            # Let's stick to the more controlled manual addition for now.

            # Reverting to the manual handler addition for more control over log name
            # and to ensure we can make it debug_local friendly.

            root_logger = logging.getLogger() # Get the root logger

            # Set overall level for the root logger.
            # Handlers can have their own more restrictive levels.
            current_root_level = root_logger.getEffectiveLevel()
            if current_root_level == logging.NOTSET or current_root_level > log_level:
                 root_logger.setLevel(log_level)

            has_cloud_handler = any(isinstance(h, CloudLoggingHandler) for h in root_logger.handlers)

            if not has_cloud_handler:
                cloud_handler = CloudLoggingHandler(client, name=service_name) # `name` here is the log name in GCP
                cloud_handler.setLevel(log_level) # Cloud handler respects this level
                root_logger.addHandler(cloud_handler)
                logger.info(
                    f"Global CloudLoggingHandler configured for root logger "
                    f"at level {logging.getLevelName(log_level)} to GCP log '{service_name}'."
                )
            else:
                 logger.info("Global CloudLoggingHandler already configured for root logger.")

            # Ensure console output for local dev / easy debugging
            # This is important if `client.setup_logging()` isn't used which might also add a console handler.
            has_stream_handler = any(isinstance(h, logging.StreamHandler) and \
                                     not isinstance(h, CloudLoggingHandler) \
                                     for h in root_logger.handlers)
            if not has_stream_handler and os.environ.get("ENV", "development") == "development": # Example condition
                console_handler = logging.StreamHandler()
                console_formatter = logging.Formatter(
                    fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s (Trace: %(otelTraceID)s Span: %(otelSpanID)s)",
                    datefmt="%Y-%m-%d %H:%M:%S"
                )
                console_handler.setFormatter(console_formatter)
                console_handler.setLevel(log_level)
                root_logger.addHandler(console_handler)
                logger.info("Added StreamHandler to root logger for local debugging with trace info.")

            # Make sure all loggers propagate to the root logger's handlers
            # unless they have explicitly set propagate = False
            for logger_name in logging.Logger.manager.loggerDict:
                logging.getLogger(logger_name).propagate = True


        except Exception as e:
            logger.error(f"Failed to set up global Google Cloud Logging: {e}", exc_info=True)
            logger.warning("Logging will proceed with standard Python logging configuration.")
            if not logging.getLogger().handlers: # Check if root logger has any handlers
                logging.basicConfig(
                    level=log_level,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s (Trace: %(otelTraceID)s Span: %(otelSpanID)s)"
                )
                logger.info("Basic logging configured as fallback for root logger.")


    # Using the global setup for testing
    setup_global_cloud_logging(log_level=logging.DEBUG, service_name="my-global-app")

    logging.info("Root logger: Info message after global setup.")
    logging.debug("Root logger: Debug message after global setup.")

    module_logger = logging.getLogger("module_test")
    module_logger.info("Module logger: Info message, should use global setup.")
    module_logger.debug("Module logger: Debug message, should use global setup.")

    # To make otelTraceID and otelSpanID work with basicConfig or StreamHandler formatter:
    # You need to integrate OpenTelemetry's LoggingInstrumentor if not already done by ADK
    # or ensure the trace context is manually added to LogRecords.
    # The google-cloud-logging handler does this automatically.
    # For standard StreamHandler, you'd need to:
    # 1. Add OpenTelemetry Logging Instrumentation:
    #    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    #    LoggingInstrumentor().instrument(set_logging_format=True) # set_logging_format adds trace/span to LogRecord
    # 2. Then your formatter can use %(otelTraceID)s etc.
    # (Assuming LoggingInstrumentor is called elsewhere in app setup, e.g. with tracing init)

    # The `google-cloud-logging` handler itself will automatically add
    # `logging.googleapis.com/trace` and `spanId` fields to the JSON payload
    # it sends to GCP, which is the primary goal for GCP integration.
    # The custom formatter for console_handler is for local visibility.

# Final simplified version for the utility file - focusing on the global setup approach
# as it's most common for application-wide logging to GCP.
# The initial `setup_cloud_logging` function was good for targeting specific loggers,
# but `setup_global_cloud_logging` is more aligned with typical app setup.
# I'll use the refined `setup_global_cloud_logging` as the main function in the util.

final_utility_code = """\
import logging
import os
import google.cloud.logging as cloud_logging
from google.cloud.logging_v2.handlers import CloudLoggingHandler
from opentelemetry.trace import get_current_span # To check for active span

# Initialize a module-level logger for this utility
logger = logging.getLogger(__name__)

def setup_google_cloud_logging(
    log_level: int = logging.INFO,
    service_name: str = "python-app",
    force_console_debug: bool = False # If true, always add console handler for debug
):
    \"\"\"
    Sets up Google Cloud Logging globally by adding a CloudLoggingHandler
    to Python's root logger. Also includes OpenTelemetry trace correlation.

    Args:
        log_level: The minimum logging level for both cloud and console.
        service_name: Name for the log stream in Google Cloud Logging.
        force_console_debug: If True, always adds a console handler for local
                             debugging, regardless of GCP environment.
                             Useful for seeing logs locally even if deployed.
    \"\"\"
    try:
        # Attempt to instantiate the GCP Logging client
        client = cloud_logging.Client()

        root_logger = logging.getLogger()

        # Set overall level for the root logger.
        # This ensures that messages of this level or higher are processed by the logger.
        # Handlers can have their own levels, but they won't receive messages
        # below what the logger itself is set to.
        current_root_level = root_logger.getEffectiveLevel()
        if current_root_level == logging.NOTSET or current_root_level > log_level:
            root_logger.setLevel(log_level)
            logger.debug(f"Set root logger level to {logging.getLevelName(log_level)}")
        else:
            # If root logger is already set to a more verbose level, keep it.
            # If it's set to a less verbose level, our log_level might not be effective for all messages.
            # Forcing it to the specified log_level ensures our handlers receive messages correctly.
            root_logger.setLevel(log_level)
            logger.debug(f"Root logger level already {logging.getLevelName(current_root_level)}, adjusted to {logging.getLevelName(log_level)} if more verbose.")


        # Configure Cloud Logging Handler
        has_cloud_handler = any(isinstance(h, CloudLoggingHandler) for h in root_logger.handlers)
        if not has_cloud_handler:
            cloud_handler = CloudLoggingHandler(client, name=service_name)
            cloud_handler.setLevel(log_level) # Cloud handler respects this level
            root_logger.addHandler(cloud_handler)
            logger.info(
                f"Google Cloud Logging handler configured for root logger "
                f"at level {logging.getLevelName(log_level)} to GCP log '{service_name}'."
            )
        else:
            logger.info("Google Cloud Logging handler already configured for root logger.")

        # Configure Console Handler for local development or forced debugging
        # Check if running in a typical local/dev environment or if forced
        is_local_env = os.environ.get("ENV", "development").lower() == "development"

        if force_console_debug or is_local_env:
            has_console_handler = any(
                isinstance(h, logging.StreamHandler) and \
                not isinstance(h, CloudLoggingHandler) \
                for h in root_logger.handlers
            )
            if not has_console_handler:
                console_handler = logging.StreamHandler()
                # Attempt to use a formatter that includes trace IDs if OpenTelemetry is active
                # These fields (otelTraceID, otelSpanID) are added to LogRecord by OpenTelemetry's LoggingInstrumentor
                log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                try:
                    # Check if OpenTelemetry context is active, then add trace info to format
                    if get_current_span().get_span_context().is_valid:
                         log_format += " (Trace: %(otelTraceID)s Span: %(otelSpanID)s)"
                except Exception:
                    # OpenTelemetry not active or context not available
                    pass # Keep basic format

                console_formatter = logging.Formatter(fmt=log_format, datefmt="%Y-%m-%d %H:%M:%S")
                console_handler.setFormatter(console_formatter)
                console_handler.setLevel(log_level)
                root_logger.addHandler(console_handler)
                logger.info(
                    f"Console StreamHandler added to root logger at level {logging.getLevelName(log_level)}."
                )
            else:
                logger.info("Console StreamHandler already exists on root logger or not added due to environment/force_console_debug settings.")

        # Ensure all other loggers propagate to the root logger's handlers by default
        for logger_name_in_manager in logging.Logger.manager.loggerDict:
            managed_logger = logging.getLogger(logger_name_in_manager)
            if not managed_logger.propagate:
                managed_logger.propagate = True
                logger.debug(f"Set propagate=True for logger '{logger_name_in_manager}'.")

    except Exception as e:
        logger.error(f"Failed to set up Google Cloud Logging: {e}", exc_info=True)
        # Fallback to basic console logging if no handlers are configured on root
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=log_level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            logger.warning(
                "Basic console logging configured as fallback due to Cloud Logging setup error."
            )

# To ensure otelTraceID and otelSpanID are available in LogRecord for the console handler,
# OpenTelemetry's LoggingInstrumentor should be initialized:
#
# from opentelemetry.instrumentation.logging import LoggingInstrumentor
# LoggingInstrumentor().instrument(set_logging_format=True)
#
# This call should happen once during application startup, ideally alongside other
# OpenTelemetry setup (like tracer provider configuration).
# The ADK might handle this; if not, it needs to be added to the main app entry points.
# For this utility, we just try to use the fields if they are present.
"""

# I will use the `final_utility_code` for the file.
# Removing the __main__ block and the first draft of setup_cloud_logging.
# The function to be imported will be `setup_google_cloud_logging`.
