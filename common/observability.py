# common/observability.py
import os
import logging
import google.auth
import google.auth.transport.grpc
import google.auth.transport.requests
from google.auth.transport.grpc import AuthMetadataPlugin
import grpc

from opentelemetry import trace, metrics, propagate
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter, BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as GRPCOTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter as GRPCOTLPMetricExporter
from opentelemetry.propagate import set_textmap
from opentelemetry.propagators.b3 import B3MultiPropagator

# Import Instrumentors
from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient

logger = logging.getLogger(__name__)

def setup_observability():
    logger.info("--- common.observability.setup_observability started ---")

    # 1. Define Resources
    project_id = "unknown"
    creds = None
    try:
        credentials, project_id = google.auth.default()
        logger.info(f"Google Cloud project ID fetched: {project_id}")
        creds = credentials
    except Exception as e:
        logger.warning(f"Could not fetch Google Cloud credentials: {e}")
        # Early exit if creds are essential, or handle lack of creds in exporters
        return

    service_name = os.environ.get("SERVICE_NAME", "default-service")
    resource = Resource.create({
        "service.name": service_name,
        "gcp.project_id": project_id,
    })

    # Create gRPC channel credentials
    channel_creds = None
    if creds:
        try:
            request_creds = google.auth.transport.requests.Request()
            auth_metadata_plugin = AuthMetadataPlugin(
                credentials=creds, request=request_creds
            )
            channel_creds = grpc.composite_channel_credentials(
                grpc.ssl_channel_credentials(),
                grpc.metadata_call_credentials(auth_metadata_plugin),
            )
            logger.info("gRPC channel credentials created.")
        except Exception as e:
            logger.error(f"Failed to create gRPC channel credentials: {e}")
            # Depending on requirements, you might still proceed without OTLP exporters

    # 2. Configure Tracing
    tracer_provider = SdkTracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)
    logger.info("New OpenTelemetry SDK TracerProvider created and set globally.")

    # Console Exporter
    console_exporter = ConsoleSpanExporter()
    tracer_provider.add_span_processor(SimpleSpanProcessor(console_exporter))
    logger.info("OpenTelemetry ConsoleSpanExporter added.")

    # OTLP Exporter to Google Cloud for Traces
    if channel_creds:
        try:
            otlp_trace_exporter = GRPCOTLPSpanExporter(
                endpoint="telemetry.googleapis.com:443",
                credentials=channel_creds  # Use channel_creds here
            )
            tracer_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))
            logger.info("OpenTelemetry OTLPSpanExporter to telemetry.googleapis.com added for traces.")
        except Exception as e:
            logger.error(f"Failed to setup OTLPSpanExporter for traces: {e}")
    else:
        logger.warning("Skipping OTLP trace exporter setup due to missing channel credentials.")

    # 3. Configure Metrics
    if channel_creds:
        try:
            otlp_metric_exporter = GRPCOTLPMetricExporter(
                endpoint="telemetry.googleapis.com:443",
                credentials=channel_creds  # Use channel_creds here
            )
            metric_reader = PeriodicExportingMetricReader(otlp_metric_exporter)
            meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
            metrics.set_meter_provider(meter_provider)
            logger.info("MeterProvider configured with OTLP Metric Reader.")
        except Exception as e:
            logger.error(f"Failed to setup MeterProvider: {e}")
    else:
        logger.warning("Skipping OTLP metric exporter setup due to missing channel credentials.")

    # 4. Configure Propagation
    set_textmap(B3MultiPropagator())
    logger.info("Global TextMap propagator set to B3MultiPropagator.")

    # 5. Instrument libraries
    logger.info("Enabling OpenTelemetry Instrumentations...")
    try:
        VertexAIInstrumentor().instrument()
        logger.info("VertexAIInstrumentor enabled.")
    except Exception as e:
        logger.error(f"Error enabling VertexAIInstrumentor: {e}")
    try:
        RequestsInstrumentor().instrument()
        logger.info("RequestsInstrumentor enabled.")
    except Exception as e:
        logger.error(f"Error enabling RequestsInstrumentor: {e}")
    try:
        AioHttpClientInstrumentor().instrument()
        logger.info("AioHttpClientInstrumentor enabled.")
    except Exception as e:
        logger.error(f"Error enabling AioHttpClientInstrumentor: {e}")
    try:
        GrpcInstrumentorClient().instrument()
        logger.info("GrpcInstrumentorClient enabled.")
    except Exception as e:
        logger.error(f"Error enabling GrpcInstrumentorClient: {e}")

    logger.info(f"Custom observability setup complete for service: {service_name}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    setup_observability()
