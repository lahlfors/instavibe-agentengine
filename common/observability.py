import logging
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.gcp.logging import GcpLoggingSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
import google.auth

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
    resource = Resource.create({"service.name": service_name, "gcp.project_id": project_id})

    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    # Exporter for Cloud Trace via OTLP
    otlp_trace_exporter = OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))

    # Exporter for Cloud Logging
    gcp_logging_exporter = GcpLoggingSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(gcp_logging_exporter))

    logging.info(
        f"OpenTelemetry Tracer configured for service: {service_name} in project {project_id}"
    )

    # --- Auto-instrumentation ---
    VertexAIInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)
    RequestsInstrumentor().instrument()

    logging.info("Observability setup complete.")
