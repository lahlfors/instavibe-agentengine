import logging
import os
import google.auth
from google.auth.transport import grpc as transport_grpc
from google.auth.transport import requests as transport_requests
from google.cloud.logging_v2.handlers import CloudLoggingHandler
from google.cloud.logging_v2.resource import Resource as GcpResource
import google.cloud.logging
from opentelemetry import trace, propagate
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider, export
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


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
    gcp_resource = GcpResource(
        type="cloud_run_revision",
        labels={
            "service_name": service_name,
            "project_id": project_id,
        },
    )

    client = google.cloud.logging.Client(credentials=credentials, project=project_id)
    handler = CloudLoggingHandler(client, resource=gcp_resource)
    google.cloud.logging.handlers.setup_logging(handler)
    logging.info("Structured logging configured.")
