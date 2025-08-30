import logging
import os
import google.auth
import google.auth.transport.requests as google_auth_requests
import google.auth.grpc as google_auth_grpc
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from google.cloud.logging_v2.handlers import GCPLogExporter

def setup_observability(service_name: str):
    """
    Sets up OpenTelemetry for a service, including Cloud Trace, integrated
    logging, and automatic instrumentation for Google Cloud services.
    """
    try:
        credentials, project_id = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except google.auth.exceptions.DefaultCredentialsError:
        logging.error(
            "Google Cloud credentials not found. Please configure your environment."
        )
        return

    # --- OpenTelemetry Tracing Setup ---
    resource = Resource(
        attributes={
            "service.name": service_name,
            "gcp.project_id": project_id,
        }
    )

    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    # Create an authenticated gRPC channel to the OTLP endpoint
    request = google_auth_requests.Request()
    channel = google_auth_grpc.secure_authorized_channel(
        credentials, request, "otlp.googleapis.com:443"
    )
    otlp_span_exporter = OTLPSpanExporter(channel=channel)
    provider.add_span_processor(BatchSpanProcessor(otlp_span_exporter))

    logging.info(
        f"OpenTelemetry Tracer configured for service: {service_name} in project {project_id}"
    )

    # --- Auto-instrumentation ---
    # Instrument Vertex AI
    VertexAIInstrumentor().instrument()
    logging.info("VertexAIInstrumentor enabled.")

    # --- Integrated Logging Setup ---
    # Instrument standard logging to automatically add trace context
    LoggingInstrumentor().instrument(set_logging_format=True)

    # Configure a handler to export logs to Google Cloud Logging
    # The GCPLogExporter will automatically handle formatting and sending logs
    # to Google Cloud Logging, enriched with trace context.
    gcp_log_exporter = GCPLogExporter()

    # Get the root logger and add the GCP handler.
    root_logger = logging.getLogger()
    root_logger.addHandler(gcp_log_exporter)
    root_logger.setLevel(logging.INFO)

    logging.info("Observability setup complete. Logs are now integrated with Cloud Trace.")
