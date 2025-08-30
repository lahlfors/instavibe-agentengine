import logging
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.cloud_logging import CloudLoggingExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
import google.auth
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider as SdkLoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

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

    # --- OpenTelemetry Logging Setup ---
    logger_provider = SdkLoggerProvider(resource=resource)
    set_logger_provider(logger_provider)

    # Exporter for Cloud Logging
    logging_exporter = CloudLoggingExporter()
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(logging_exporter))

    handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)

    logging.info(
        f"OpenTelemetry Tracer and Logger configured for service: {service_name} in project {project_id}"
    )

    # --- Auto-instrumentation ---
    VertexAIInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)
    RequestsInstrumentor().instrument()

    logging.info("Observability setup complete.")
