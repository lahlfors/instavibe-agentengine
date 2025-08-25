import logging
import os
from traceloop.sdk import Traceloop
from google.cloud.logging_v2.resource import Resource as GcpResource

def setup_observability(service_name: str):
    """
    Sets up OpenTelemetry for a service, including Cloud Trace and structured
    logging.
    """
    # Initialize OpenLLMetry for auto-instrumentation
    os.environ["TRACELOOP_SERVICE_NAME"] = service_name
    Traceloop.init()

    logging.info(f"OpenTelemetry Tracer configured for service: {service_name}")

    # --- Structured Logging Setup ---
    # a "Resource" identifies your application
    from google.cloud.logging_v2.handlers import CloudLoggingHandler
    import google.cloud.logging

    # Instantiates a client
    client = google.cloud.logging.Client()

    # A "Resource" identifies your application. The "service.name" is crucial
    # as it's how you'll filter for your agent's traces in Cloud Trace.
    gcp_resource = GcpResource(
        type="cloud_run_revision",
        labels={
            "service_name": service_name,
            "project_id": os.environ.get("COMMON_GOOGLE_CLOUD_PROJECT", "unknown"),
        },
    )

    # Retrieves a Cloud Logging handler based on the environment
    # you're running in and integrates the handler with the
    # Python logging module. By default this captures all logs
    # at INFO level and higher.
    handler = CloudLoggingHandler(client, resource=gcp_resource)
    google.cloud.logging.handlers.setup_logging(handler)
    logging.info("Structured logging configured.")
