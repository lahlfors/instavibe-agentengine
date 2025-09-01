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
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter, BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as GRPCOTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter as GRPCOTLPMetricExporter
from opentelemetry.propagators.b3 import B3MultiFormat

# Import Instrumentors
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

def setup_observability():
    log.info("--- common.observability.setup_observability started ---")

    # Define Resources
    project_id = "unknown"
    creds = None
    try:
        _, project_id = google.auth.default()
        log.info(f"Google Cloud project ID fetched: {project_id}")
        creds = google.auth.default()[0]
    except Exception as e:
        log.warning(f"Could not fetch Google Cloud credentials: {e}")

    service_name = os.environ.get("SERVICE_NAME", "default-service")
    resource = Resource.create({
        "service.name": service_name,
        "gcp.project_id": project_id,
    })

    # Configure Tracing
    tracer_provider = SdkTracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)
    log.info("New OpenTelemetry SDK TracerProvider created and set globally.")

    # Add Exporters to the active SdkTracerProvider
    # Console Exporter
    console_exporter = ConsoleSpanExporter()
    tracer_provider.add_span_processor(SimpleSpanProcessor(console_exporter))
    log.info("OpenTelemetry ConsoleSpanExporter added.")

    # OTLP Exporter to Google Cloud
    try:
        otlp_trace_exporter = GRPCOTLPSpanExporter(
            endpoint="telemetry.googleapis.com:443",
            credentials=creds
        )
        tracer_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))
        log.info("OpenTelemetry OTLPSpanExporter to telemetry.googleapis.com added.")
    except Exception as e:
        log.error(f"Failed to setup OTLPSpanExporter for traces: {e}")

    # Configure Metrics
    try:
        otlp_metric_exporter = GRPCOTLPMetricExporter(
            endpoint="telemetry.googleapis.com:443",
            credentials=creds
        )
        metric_reader = PeriodicExportingMetricReader(otlp_metric_exporter)
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)
        log.info("MeterProvider configured with OTLP Metric Reader.")
    except Exception as e:
        log.error(f"Failed to setup MeterProvider: {e}")

    # Configure Propagation
    # Using the updated set_textmap instead of the deprecated set_global_textmap_propagator
    propagate.set_global_textmap(B3MultiFormat())
    log.info("Global TextMap propagator set to B3MultiPropagator.")

    # Instrument libraries
    log.info("Enabling OpenTelemetry Instrumentations...")
    try:
        VertexAIInstrumentor().instrument()
        log.info("VertexAIInstrumentor enabled.")
    except Exception as e:
        log.error(f"Error enabling VertexAIInstrumentor: {e}")
    try:
        RequestsInstrumentor().instrument()
        log.info("RequestsInstrumentor enabled.")
    except Exception as e:
        log.error(f"Error enabling RequestsInstrumentor: {e}")
    try:
        AioHttpClientInstrumentor().instrument()
        log.info("AioHttpClientInstrumentor enabled.")
    except Exception as e:
        log.error(f"Error enabling AioHttpClientInstrumentor: {e}")

    try:
        GrpcInstrumentorClient().instrument()
        log.info("GrpcInstrumentorClient enabled.")
    except Exception as e:
        log.error(f"Error enabling GrpcInstrumentorClient: {e}")
    log.info(f"Custom observability setup complete for service: {service_name}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    setup_observability()
