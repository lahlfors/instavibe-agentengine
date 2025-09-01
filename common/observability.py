# common/observability.py

import logging
import os
from typing import Final, List, Tuple, Optional

import google.auth
import google.auth.transport.requests
import grpc
from google.auth.transport import grpc as google_auth_transport_grpc
from google.auth.transport import requests as google_auth_transport_requests
from google.auth.transport.grpc import AuthMetadataPlugin # Corrected import

from opentelemetry import trace, metrics, propagate
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
# from opentelemetry.propagators.cloud_trace_propagator import CloudTraceFormatPropagator # Alternative for GCP

import google.cloud.logging

from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

# A fallback name if the service name isn't set in the environment
DEFAULT_SERVICE_NAME: Final[str] = "my-adk-app"
GOOGLE_CLOUD_SCOPE: Final[List[str]] = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/trace.append",
    "https://www.googleapis.com/auth/monitoring.write",
    "https://www.googleapis.com/auth/logging.write",
]

log = logging.getLogger(__name__)

_OTEL_INITIALIZED = False

def _get_gcp_credentials() -> Tuple[Optional[google.auth.credentials.Credentials], Optional[str]]:
    try:
        credentials, project_id = google.auth.default(scopes=GOOGLE_CLOUD_SCOPE)
        if not project_id:
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        log.info(f"Google Cloud credentials fetched for project: {project_id}")
        return credentials, project_id
    except Exception as e:
        log.warning(f"Could not fetch Google Cloud credentials: {e}. GCP-specific exporters will be skipped.")
        return None, os.getenv("GOOGLE_CLOUD_PROJECT")

def _create_grpc_channel(credentials: google.auth.credentials.Credentials, endpoint: str) -> grpc.Channel:
    request = google.auth.transport.requests.Request()
    auth_metadata_plugin = AuthMetadataPlugin(credentials=credentials, request=request)
    ssl_creds = grpc.ssl_channel_credentials()
    return grpc.secure_channel(
        endpoint,
        grpc.composite_channel_credentials(
            ssl_creds,
            grpc.metadata_call_credentials(auth_metadata_plugin),
        ),
    )

def setup_observability():
    """
    Initializes a standard, centralized OpenTelemetry pipeline for Google Cloud.

    This function ensures a standard SdkTracerProvider is used, configures
    exporters for Traces (Console, OTLP to Cloud Trace) and Metrics (OTLP to
    Cloud Monitoring), integrates with Cloud Logging, and applies common instrumentations.

    It is designed to be idempotent.
    """
    global _OTEL_INITIALIZED
    if _OTEL_INITIALIZED:
        log.info("OpenTelemetry already initialized. Skipping setup.")
        return

    log.info("--- common.observability.setup_observability started ---")

    credentials, project_id = _get_gcp_credentials()

    # 1. Define a consistent Resource for all telemetry signals.
    resource_attrs = {
        "service.name": os.getenv("SERVICE_NAME", DEFAULT_SERVICE_NAME),
    }
    if project_id:
        resource_attrs["gcp.project_id"] = project_id
    else:
         log.warning("GOOGLE_CLOUD_PROJECT not set, 'gcp.project_id' attribute will be missing.")

    resource = Resource.create(resource_attrs)

    # --- TRACE CONFIGURATION ---
    current_provider = trace.get_tracer_provider()
    if not isinstance(current_provider, SdkTracerProvider):
        log.warning(
            f"No standard SdkTracerProvider found (type: {type(current_provider).__name__}). "
            "Initializing a new one. This will overwrite any non-standard provider."
        )
        provider = SdkTracerProvider(resource=resource)
        trace.set_tracer_provider(provider)
    else:
        log.info("A standard SdkTracerProvider is already configured.")
        provider = current_provider
        # Note: We are not attempting to merge resources with an existing provider.
        # The first successful initialization dictates the Resource.

    # Add Span Processors (only if not already added - basic check)
    if not hasattr(provider, '_is_ duckie_configured'):
        # Export to the console for easy local debugging.
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        log.info("ConsoleSpanExporter added to TracerProvider.")

        # Export to Google Cloud Trace via OTLP
        if credentials:
            try:
                grpc_channel = _create_grpc_channel(credentials, "telemetry.googleapis.com:443")
                otlp_trace_exporter = OTLPSpanExporter(channel=grpc_channel)
                provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))
                log.info("OTLPSpanExporter for Cloud Trace added to TracerProvider.")
            except Exception as e:
                log.error(f"Failed to setup OTLPSpanExporter for traces: {e}", exc_info=True)
        else:
            log.warning("Skipping OTLP Trace Exporter: No Google Cloud credentials.")
        setattr(provider, '_is_ duckie_configured', True)

    # --- METRIC CONFIGURATION ---
    if not isinstance(metrics.get_meter_provider(), MeterProvider):
        metric_readers = []
        if credentials:
            try:
                grpc_channel_metrics = _create_grpc_channel(credentials, "telemetry.googleapis.com:443")
                otlp_metric_exporter = OTLPMetricExporter(channel=grpc_channel_metrics)
                metric_reader = PeriodicExportingMetricReader(otlp_metric_exporter)
                metric_readers.append(metric_reader)
                log.info("OTLPMetricExporter for Cloud Monitoring added.")
            except Exception as e:
                log.error(f"Failed to setup OTLPMetricExporter for metrics: {e}", exc_info=True)
        else:
            log.warning("Skipping OTLP Metric Exporter: No Google Cloud credentials.")

        meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)
        metrics.set_meter_provider(meter_provider)
        log.info("MeterProvider configured and set as global.")
    else:
        log.info("A MeterProvider is already configured.")

    # --- PROPAGATION ---
    propagate.set_textmap(TraceContextTextMapPropagator())
    # Alternate: propagate.set_textmap(CloudTraceFormatPropagator())
    log.info("Global TextMap propagator set to TraceContextTextMapPropagator.")

    # --- Google Cloud Logging Integration ---
    try:
        if credentials and project_id:
            logging_client = google.cloud.logging.Client(project=project_id, credentials=credentials)
            logging_client.setup_logging(log_level=logging.INFO)
            # Re-fetch logger to ensure it's a cloud logger
            logging.info("Google Cloud Logging client setup complete, integrating with Python logging.")
        else:
            log.warning("Skipping Google Cloud Logging integration: Missing credentials or project ID.")
    except Exception as e:
        log.error(f"Failed to configure Google Cloud Logging: {e}", exc_info=True)

    # --- APPLY INSTRUMENTATION ---
    log.info("Applying standard library instrumentations...")
    try: RequestsInstrumentor().instrument()
    except Exception as e: log.error(f"Failed to instrument Requests: {e}")
    try: VertexAIInstrumentor().instrument()
    except Exception as e: log.error(f"Failed to instrument VertexAI: {e}")
    try: AioHttpClientInstrumentor().instrument()
    except Exception as e: log.error(f"Failed to instrument AioHttpClient: {e}")
    try: GrpcInstrumentorClient().instrument()
    except Exception as e: log.error(f"Failed to instrument GrpcInstrumentorClient: {e}")

    _OTEL_INITIALIZED = True
    log.info(f"Observability setup complete for service: {resource.attributes.get('service.name')}")
