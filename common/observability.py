# common/observability.py
import os
import logging
import threading
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.semconv.resource import ResourceAttributes
import google.auth

# Corrected imports for logging, using the private _logs module structure
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

log = logging.getLogger(__name__)

def _get_project_id():
    try:
        _, project_id = google.auth.default()
        return project_id
    except google.auth.exceptions.DefaultCredentialsError:
        return os.getenv("COMMON_GOOGLE_CLOUD_PROJECT", "unknown")

def get_otel_collector_endpoint(project_id, location, collector_service_name="otel-collector"):
    """Dynamically discovers the OTel Collector endpoint from a Cloud Run service."""
    try:
        # Import is deferred to avoid dependency issues in environments that don't need it.
        from google.cloud import run_v2
        client = run_v2.ServicesClient()
        service_path = client.service_path(project_id, location, collector_service_name)
        response = client.get_service(name=service_path)
        if response.uri:
            # Remove https:// and append gRPC port
            return response.uri.replace("https://", "") + ":4317"
        log.error(f"Cloud Run service '{collector_service_name}' found, but URI is empty.")
        return None
    except ImportError:
        log.error("google.cloud.run_v2 not found, service discovery failed. Please provide OTEL_COLLECTOR_ENDPOINT directly.")
        return None
    except Exception as e:
        log.error(f"Failed to get URL for Cloud Run service '{collector_service_name}' in {location}: {e}", exc_info=False)
        return None

def setup_observability(service_name_suffix="service", disable_export=False, endpoint_override=None):
    """
    Configures OpenTelemetry for traces, metrics, and logs.

    This function is idempotent. It checks if the providers are already
    configured before attempting to set them up.
    """
    if disable_export:
        log.info("Telemetry export is disabled for this run.")
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        return

    project_id = _get_project_id()
    location = os.getenv("COMMON_GOOGLE_CLOUD_LOCATION", "us-central1")
    service_name = os.getenv("OTEL_SERVICE_NAME", f"instavibe-{service_name_suffix}")

    # Prioritize endpoint_override, then environment variable, then discovery.
    OTEL_COLLECTOR_ENDPOINT = endpoint_override or os.getenv("OTEL_COLLECTOR_ENDPOINT")

    if not OTEL_COLLECTOR_ENDPOINT:
        log.info("OTEL_COLLECTOR_ENDPOINT not set and no override provided, attempting to discover from Cloud Run...")
        OTEL_COLLECTOR_ENDPOINT = get_otel_collector_endpoint(project_id, location)

    if not OTEL_COLLECTOR_ENDPOINT:
        log.error("Failed to determine OTEL_COLLECTOR_ENDPOINT. OTEL Exporters will not be configured.")
        logging.basicConfig(level=logging.INFO)
        return

    log.info(f"Configuring OpenTelemetry with collector endpoint: {OTEL_COLLECTOR_ENDPOINT}")

    resource = Resource.create({
        ResourceAttributes.SERVICE_NAME: service_name,
        ResourceAttributes.CLOUD_REGION: location,
        ResourceAttributes.CLOUD_PROVIDER: "gcp",
        ResourceAttributes.CLOUD_ACCOUNT_ID: project_id,
    })

    # --- TRACES ---
    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)
        otlp_span_exporter = OTLPSpanExporter(endpoint=OTEL_COLLECTOR_ENDPOINT, insecure=True)
        tracer_provider.add_span_processor(BatchSpanProcessor(otlp_span_exporter))
        log.info("Configured new TracerProvider.")
    else:
        log.info("TracerProvider already configured.")

    # --- METRICS ---
    if not isinstance(metrics.get_meter_provider(), MeterProvider):
        otlp_metric_exporter = OTLPMetricExporter(endpoint=OTEL_COLLECTOR_ENDPOINT, insecure=True)
        metric_reader = PeriodicExportingMetricReader(otlp_metric_exporter)
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)
        log.info("Configured new MeterProvider.")
    else:
        log.info("MeterProvider already configured.")

    # --- LOGS ---
    OTEL_HANDLER_NAME = "otel_logging_handler"
    root_logger = logging.getLogger()
    if not any(h.name == OTEL_HANDLER_NAME for h in root_logger.handlers):
        logger_provider = LoggerProvider(resource=resource)
        exporter = OTLPLogExporter(endpoint=OTEL_COLLECTOR_ENDPOINT, insecure=True)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
        handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
        handler.name = OTEL_HANDLER_NAME
        root_logger.addHandler(handler)
        log.info("Configured new LoggingHandler.")
    else:
        log.info("LoggingHandler already configured.")

    log.info("OpenTelemetry configuration check complete.")


def get_trace_context():
    """
    Returns a dictionary with the current trace and span ID for log correlation.
    To be used as `logging.info("...", extra=get_trace_context())`.
    """
    span = trace.get_current_span()
    if not span.is_recording():
        return {}
    span_context = span.get_span_context()
    trace_id = span_context.trace_id
    span_id = span_context.span_id

    # Return empty dict if trace_id or span_id are invalid
    if trace_id == 0 or span_id == 0:
        return {}

    project_id = _get_project_id()
    return {
        "logging.googleapis.com/trace": f"projects/{project_id}/traces/{trace.format_trace_id(trace_id)}",
        "logging.googleapis.com/spanId": trace.format_span_id(span_id),
    }

def get_meter(name):
    """Returns a meter from the global meter provider."""
    return metrics.get_meter(name)
