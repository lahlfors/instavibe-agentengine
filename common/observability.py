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

from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricsExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from opentelemetry.propagators.b3 import B3MultiFormat

from opentelemetry import _logs as otel_logs
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.gcp.logging import CloudLoggingExporter

from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient

log = logging.getLogger(__name__)

def setup_observability():
    log.info("--- common.observability.setup_observability started ---")
    # ... (all the setup code as in the previous version) ...
    # 1. Define Resources
    project_id = "laah-genai"
    creds = None
    try:
        scopes = [
            'https://www.googleapis.com/auth/cloud-platform',
            'https://www.googleapis.com/auth/trace.append',
            'https://www.googleapis.com/auth/monitoring.write',
            'https://www.googleapis.com/auth/logging.write'
        ]
        credentials, project_id = google.auth.default(scopes=scopes)
        log.info(f"Google Cloud project ID fetched: {project_id}")

        scoped_credentials = credentials.with_quota_project(project_id)
        log.info(f"Set quota project to: {scoped_credentials.quota_project_id}")
        creds = scoped_credentials
    except Exception as e:
        log.warning(f"Could not fetch Google Cloud credentials: {e}", exc_info=True)
        return None, None # Return None if setup fails

    service_name = os.environ.get("SERVICE_NAME", "default-service")
    resource = Resource.create({
        "service.name": service_name,
        "gcp.project_id": project_id,
    })

    # Create gRPC channel credentials for OTLP Traces
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
            log.error(f"Failed to create gRPC channel credentials: {e}", exc_info=True)

    # 2. Configure Tracing
    tracer_provider = SdkTracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)
    tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    if channel_creds:
        try:
            otlp_trace_exporter = GRPCOTLPSpanExporter(
                endpoint="telemetry.googleapis.com:443",
                credentials=channel_creds
            )
            tracer_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))
            log.info("OpenTelemetry OTLPSpanExporter to telemetry.googleapis.com added for traces.")
        except Exception as e:
            log.error(f"Failed to setup OTLPSpanExporter for traces: {e}", exc_info=True)

    # 3. Configure Metrics
    meter_provider = MeterProvider(resource=resource)
    try:
        monitoring_exporter = CloudMonitoringMetricsExporter(project_id=project_id)
        metric_reader = PeriodicExportingMetricReader(monitoring_exporter)
        # Recreate MeterProvider with the reader
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)
        log.info("MeterProvider configured with CloudMonitoringMetricsExporter.")
    except Exception as e:
        log.error(f"Failed to setup MeterProvider with CloudMonitoringMetricsExporter: {e}", exc_info=True)
        metrics.set_meter_provider(meter_provider) # Set base provider even if exporter fails

    # 4. Configure Logging
    try:
        logger_provider = LoggerProvider(resource=resource)
        set_logger_provider(logger_provider)
        gcp_logging_exporter = CloudLoggingExporter()
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(gcp_logging_exporter)
        )
        log.info("OpenTelemetry CloudLoggingExporter added.")
    except Exception as e:
        log.error(f"Failed to setup CloudLoggingExporter: {e}", exc_info=True)

    # ... (Propagation and Instrumentors) ...
    propagate.set_global_textmap(B3MultiFormat())
    log.info("Enabling OpenTelemetry Instrumentations...")
    try: VertexAIInstrumentor().instrument()
    except Exception as e: log.error(f"Error enabling VertexAIInstrumentor: {e}")
    try: RequestsInstrumentor().instrument()
    except Exception as e: log.error(f"Error enabling RequestsInstrumentor: {e}")
    try: AioHttpClientInstrumentor().instrument()
    except Exception as e: log.error(f"Error enabling AioHttpClientInstrumentor: {e}")
    try: GrpcInstrumentorClient().instrument()
    except Exception as e: log.error(f"Error enabling GrpcInstrumentorClient: {e}")

    log.info(f"Custom observability setup complete for service: {service_name}")

    # --- RETURN THE PROVIDERS ---
    return trace.get_tracer_provider(), metrics.get_meter_provider()
