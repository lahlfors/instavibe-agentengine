import logging
import os
import google.cloud.logging as cloud_logging
from google.cloud.logging_v2.handlers import CloudLoggingHandler
from opentelemetry.trace import get_current_span # To check for active span

# Initialize a module-level logger for this utility
logger = logging.getLogger(__name__)

def setup_google_cloud_logging(
    log_level: int = logging.INFO,
    service_name: str = "python-app", # Default GCP log stream name (will be overridden by callers)
    force_console_debug: bool = False # If true, always add console handler for debug
):
    """
    Sets up Google Cloud Logging globally by adding a CloudLoggingHandler
    to Python's root logger. Also includes OpenTelemetry trace correlation.

    Args:
        log_level: The minimum logging level for both cloud and console.
        service_name: Name for the log stream in Google Cloud Logging. This will also
                      be used as the 'gcp_log_name'.
        force_console_debug: If True, always adds a console handler for local
                             debugging, regardless of GCP environment.
                             Useful for seeing logs locally even if deployed.
    """
    try:
        # Attempt to instantiate the GCP Logging client
        # project_id will be sourced from COMMON_GOOGLE_CLOUD_PROJECT env var or ADC
        client = cloud_logging.Client()

        root_logger = logging.getLogger()

        # Set overall level for the root logger.
        current_root_level = root_logger.getEffectiveLevel()
        # Adjust root logger level only if the new level is more verbose
        # or if the root logger hasn't been configured (level is NOTSET).
        # This prevents making logging less verbose if it was already set higher.
        if current_root_level == logging.NOTSET or log_level < current_root_level :
            root_logger.setLevel(log_level)
            logger.debug(f"Set root logger level to {logging.getLevelName(log_level)}")
        else:
            logger.debug(f"Root logger level already {logging.getLevelName(current_root_level)} (or more verbose). Not changing to {logging.getLevelName(log_level)}.")


        # Configure Cloud Logging Handler
        # Use service_name as the gcp_log_name for the CloudLoggingHandler
        gcp_log_name = service_name
        has_cloud_handler = any(isinstance(h, CloudLoggingHandler) for h in root_logger.handlers)

        if not has_cloud_handler:
            cloud_handler = CloudLoggingHandler(client, name=gcp_log_name)
            cloud_handler.setLevel(log_level) # Cloud handler respects this level
            root_logger.addHandler(cloud_handler)
            logger.info(
                f"Google Cloud Logging handler configured for root logger "
                f"at level {logging.getLevelName(log_level)} to GCP log '{gcp_log_name}'."
            )
        else:
            logger.info(f"Google Cloud Logging handler already configured for root logger (log name: '{gcp_log_name}').")

        # Configure Console Handler for local development or forced debugging
        is_local_env = os.environ.get("ENV", "development").lower() == "development"

        if force_console_debug or is_local_env:
            has_console_handler = any(
                isinstance(h, logging.StreamHandler) and \
                not isinstance(h, CloudLoggingHandler) \
                for h in root_logger.handlers
            )
            if not has_console_handler:
                console_handler = logging.StreamHandler()
                log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                try:
                    if get_current_span().get_span_context().is_valid:
                         log_format += " (Trace: %(otelTraceID)s Span: %(otelSpanID)s)"
                except Exception:
                    pass

                console_formatter = logging.Formatter(fmt=log_format, datefmt="%Y-%m-%d %H:%M:%S")
                console_handler.setFormatter(console_formatter)
                console_handler.setLevel(log_level) # Console handler also respects this level
                root_logger.addHandler(console_handler)
                logger.info(
                    f"Console StreamHandler added to root logger at level {logging.getLevelName(log_level)}."
                )
            else:
                logger.info("Console StreamHandler already exists on root logger or not added due to environment/force_console_debug settings.")

        # Ensure all other loggers propagate to the root logger's handlers by default
        # This is generally the default behavior unless propagate is explicitly set to False.
        # This loop can be verbose but ensures it if there's doubt.
        for logger_name_in_manager in logging.Logger.manager.loggerDict:
            managed_logger = logging.getLogger(logger_name_in_manager)
            if not managed_logger.propagate and managed_logger is not root_logger and managed_logger is not logger:
                # Avoid setting propagate on the root logger itself or this utility's logger if it has specific handlers.
                managed_logger.propagate = True
                logger.debug(f"Set propagate=True for logger '{logger_name_in_manager}'.")

    except Exception as e:
        logger.error(f"Failed to set up Google Cloud Logging for service '{service_name}': {e}", exc_info=True)
        if not logging.getLogger().handlers: # Check if root logger has ANY handlers
            logging.basicConfig(
                level=log_level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            logger.warning(
                "Basic console logging configured as fallback due to Cloud Logging setup error."
            )

# To ensure otelTraceID and otelSpanID are available in LogRecord for the console handler,
# OpenTelemetry's LoggingInstrumentor should be initialized before this setup function is called:
#
# from opentelemetry.instrumentation.logging import LoggingInstrumentor
# LoggingInstrumentor().instrument(set_logging_format=True)
#
# This call should happen once during application startup, ideally alongside other
# OpenTelemetry setup (like tracer provider configuration).
# This utility (logging_setup.py) assumes that if LoggingInstrumentor is active,
# the trace and span ID fields will be available on LogRecord objects.
