import logging
import os
import json
import sys
import google.auth
from google.auth.transport import grpc as transport_grpc
from google.auth.transport import requests as transport_requests
from opentelemetry import trace, propagate
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider, export
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


class JsonFormatter(logging.Formatter):
    def __init__(self, project_id: str):
        super().__init__()
        self.project_id = project_id

    def format(self, record):
        log_record = {
            "message": record.getMessage(),
            "severity": record.levelname,
            "timestamp": self.formatTime(record, self.datefmt),
            "logger": record.name,
        }

        # Add OpenTelemetry Trace Context
        span = trace.get_current_span()
        if span != trace.INVALID_SPAN:
            span_context = span.get_span_context()
            if span_context.is_valid:
                log_record["logging.googleapis.com/trace"] = f"projects/{self.project_id}/traces/{format(span_context.trace_id, '032x')}"
                log_record["logging.googleapis.com/spanId"] = format(span_context.span_id, "016x")
                log_record["logging.googleapis.com/trace_sampled"] = span_context.trace_flags.sampled

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


def setup_observability(service_name: str):
    """
    Sets up OpenTelemetry for a service, including Cloud Trace and structured
    logging.
    """
    try:
        credentials, project_id = google.auth.default()
    except google.auth.exceptions.DefaultCredentialsError:
        logging.error(
            "Google Cloud credentials not found. Please run 'gcloud auth application-default login' or set up the environment."
        )
        return

    # --- OpenTelemetry Tracing Setup ---
    resource = Resource(
        attributes={
            SERVICE_NAME: service_name,
            "gcp.project_id": project_id,
        }
    )

    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    # Console Exporter for local debugging
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    logging.info("OpenTelemetry ConsoleSpanExporter configured.")

    # OTLP Exporter for Google Cloud Trace
    try:
        request = transport_requests.Request()
        channel = transport_grpc.secure_authorized_channel(
            credentials, request, "cloudtrace.googleapis.com:443"
        )
        otlp_exporter = OTLPSpanExporter(channel=channel)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logging.info("OpenTelemetry OTLPSpanExporter configured for Google Cloud Trace.")
    except Exception as e:
        logging.error(f"Failed to configure OTLP Exporter: {e}")

    # Set the global propagator to W3C format
    propagate.set_global_textmap(
        TraceContextTextMapPropagator()
    )

    logging.info(
        f"OpenTelemetry Tracer configured for service: {service_name} in project {project_id}"
    )

    # --- Structured Logging Setup ---
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(project_id=project_id))

    logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)
    logger = logging.getLogger(__name__)
    logger.info("Structured logging configured.")
