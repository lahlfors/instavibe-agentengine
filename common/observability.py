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
from opentelemetry.propagators.b3 import B3MultiFormat

# === ADD THESE IMPORTS for LOGGING ===
from opentelemetry import _logs as otel_logs
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.cloud_logging import CloudLoggingExporter
# === END ADD ===

# Import Instrumentors
from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient

log = logging.getLogger(__name__)

def setup_observability():
    log.info("--- common.observability.setup_observability started ---")

    # 1. Define Resources
    project_id = "unknown"
    creds = None
    try:
        credentials, project_id = google.auth.default(
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        log.info(f"Google Cloud project ID fetched: {project_id}")
        creds = credentials
    except Exception as e:
        log.warning(f"Could not fetch Google Cloud credentials: {e}")
        return

    service_name = os.environ.get("SERVICE_NAME", "default-service")
    resource = Resource.create({
        "service.name": service_name,
        "gcp.project_id": project_id,
    })

    # Create gRPC channel credentials for OTLP
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
            log.info("gRPC channel credentials created.")
        except Exception as e:
            log.error(f"Failed to create gRPC channel credentials: {e}")

    # 2. Configure Tracing
    tracer_provider = SdkTracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)
    log.info("New OpenTelemetry SDK TracerProvider created and set globally.")

    tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    log.info("OpenTelemetry ConsoleSpanExporter added.")

    if channel_creds:
        try:
            otlp_trace_exporter = GRPCOTLPSpanExporter(
                credentials=channel_creds
            )
            tracer_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))
            log.info("OpenTelemetry OTLPSpanExporter to telemetry.googleapis.com added for traces.")
        except Exception as e:
            log.error(f"Failed to setup OTLPSpanExporter for traces: {e}")
    else:
        log.warning("Skipping OTLP trace exporter setup due to missing channel credentials.")

    # 3. Configure Metrics
    if channel_creds:
        try:
            otlp_metric_exporter = GRPCOTLPMetricExporter(
                credentials=channel_creds
            )
            metric_reader = PeriodicExportingMetricReader(otlp_metric_exporter)
            meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
            metrics.set_meter_provider(meter_provider)
            log.info("MeterProvider configured with OTLP Metric Reader.")
        except Exception as e:
            log.error(f"Failed to setup MeterProvider: {e}")
    else:
        log.warning("Skipping OTLP metric exporter setup due to missing channel credentials.")

    # === ADD THIS SECTION for LOGGING ===
    try:
        logger_provider = LoggerProvider(resource=resource)
        set_logger_provider(logger_provider)
        # CloudLoggingExporter uses google.auth.default() internally
        gcp_logging_exporter = CloudLoggingExporter()
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(gcp_logging_exporter)
        )
        log.info("OpenTelemetry CloudLoggingExporter added.")
    except Exception as e:
        log.error(f"Failed to setup CloudLoggingExporter: {e}")
    # === END ADD ===

    # 4. Configure Propagation
    propagate.set_global_textmap(B3MultiFormat())
    log.info("Global TextMap propagator set to B3MultiPropagator.")

    # 5. Instrument libraries
    log.info("Enabling OpenTelemetry Instrumentations...")
    # ... (instrumentors as before) ...

    log.info(f"Custom observability setup complete for service: {service_name}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Enable GRPC verbose logging for debugging
    # os.environ['GRPC_TRACE'] = 'all'
    # os.environ['GRPC_VERBOSITY'] = 'debug'
    setup_observability()
    # Example OTel log:
    otel_logger = otel_logs.get_logger(__name__)
    otel_logger.info("This is an OpenTelemetry log message.")
