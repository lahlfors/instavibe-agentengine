# common/observability.py
import logging
import os
import sys
import google.auth
import google.auth.transport.requests
import grpc
from google.auth.transport.grpc import AuthMetadataPlugin
from dotenv import load_dotenv

from opentelemetry import trace, propagate, metrics
# OTLPSpanExporter is NOT imported, assuming AdkApp handles Cloud Trace export
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

import google.cloud.logging

from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

load_dotenv()

def setup_observability():
    """
    Sets up ADDITIONAL OpenTelemetry features, augmenting the base Cloud Trace
    export expected to be set up by AdkApp(enable_tracing=True).

    This includes:
    - Console span exporter.
    - OTLP Metrics exporter to Google Cloud.
    - Additional Resource attributes.
    - Google Cloud Logging integration.
    - Various OpenTelemetry instrumentations.
    """
    service_name = os.environ.get("SERVICE_NAME", "my_adk_agent")
    # Keep standard logging as it's independent of OTel
    # Note: AdkApp or other parts of the system might also configure logging.
    # Consider a more centralized logging config if needed.
    logger = logging.getLogger(__name__)
    if not logger.hasHandlers():
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
            stream=sys.stderr,
            force=True
        )
    logger.info("--- common.observability.setup_observability started ---")

    try:
        credentials, project_id = google.auth.default()
        logger.info(f"Google Cloud credentials fetched for project: {project_id}")
    except google.auth.exceptions.DefaultCredentialsError:
        logger.error(
            "Google Cloud credentials not found. Observability setup limited.",
            exc_info=True
        )
        return

    # --- Get the current TracerProvider (potentially set up by AdkApp) ---
    tracer_provider = trace.get_tracer_provider()

    # --- Resource Configuration ---
    additional_resource = Resource(attributes={
        "service.name": service_name,
        "gcp.project_id": project_id
    })
    if isinstance(tracer_provider, TracerProvider):
        # --- WARNING: Brittle Resource Merging ---
        # The OpenTelemetry SDK does not provide a public API to update
        # the resource on an already initialized TracerProvider.
        # This direct modification of the private _resource attribute
        # might break in future SDK versions.
        existing_resource = tracer_provider.resource
        merged_resource = existing_resource.merge(additional_resource)
        tracer_provider._resource = merged_resource
        logger.info("Merged additional attributes into existing TracerProvider resource.")
    else:
        logger.warning("TracerProvider is not an SDK TracerProvider. Cannot merge resources. AdkApp tracing might not be enabled as expected.")
        # Fallback: create a new provider. This might conflict if AdkApp initializes later.
        tracer_provider = TracerProvider(resource=additional_resource)
        trace.set_tracer_provider(tracer_provider)
        logger.info("Created a new TracerProvider as none was found.")
    current_resource = tracer_provider.resource

    # --- Idempotent Console Span Processor ---
    if isinstance(tracer_provider, TracerProvider):
        has_console_exporter = any(
            isinstance(p, BatchSpanProcessor) and isinstance(p.span_exporter, ConsoleSpanExporter)
            for p in getattr(tracer_provider, "_span_processors", [])
        )
        if not has_console_exporter:
            tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.info("OpenTelemetry ConsoleSpanExporter added.")
        else:
            logger.info("ConsoleSpanExporter already configured.")

    # --- OTLP Metrics Setup to Google Cloud ---
    try:
        request = google.auth.transport.requests.Request()
        auth_metadata_plugin = AuthMetadataPlugin(credentials=credentials, request=request)
        ssl_creds = grpc.ssl_channel_credentials()
        channel_creds = grpc.composite_channel_credentials(
            ssl_creds,
            grpc.metadata_call_credentials(auth_metadata_plugin),
        )

        otlp_metric_exporter = OTLPMetricExporter(
            endpoint="telemetry.googleapis.com:443",
            credentials=channel_creds,
        )
        metric_reader = PeriodicExportingMetricReader(otlp_metric_exporter)
        meter_provider = MeterProvider(
            resource=current_resource,
            metric_readers=[metric_reader]
        )
        metrics.set_meter_provider(meter_provider)
        logger.info("MeterProvider configured with OTLP Metric Reader to telemetry.googleapis.com.")
    except Exception as e:
        logger.error(f"Failed to configure OTLP MeterProvider: {e}", exc_info=True)

    # --- Global Propagator ---
    propagate.set_global_textmap(TraceContextTextMapPropagator())
    logger.info("Global TextMap propagator set to TraceContextTextMapPropagator.")

    # --- Google Cloud Logging Integration ---
    try:
        logging_client = google.cloud.logging.Client(project=project_id, credentials=credentials)
        logging_client.setup_logging(log_level=logging.INFO)
        logger.info("Google Cloud Logging client setup complete, integrating with Python logging.")
    except Exception as e:
        logger.error(f"Failed to configure Google Cloud Logging: {e}", exc_info=True)

    # --- OpenTelemetry Instrumentations ---
    try:
        VertexAIInstrumentor().instrument()
        logger.info("VertexAIInstrumentor enabled.")
        RequestsInstrumentor().instrument()
        logger.info("RequestsInstrumentor enabled.")
        GrpcInstrumentorClient().instrument()
        logger.info("GrpcInstrumentorClient enabled.")
        AioHttpClientInstrumentor().instrument()
        logger.info("AioHttpClientInstrumentor enabled.")
    except Exception as e:
        logger.error(f"Error enabling OpenTelemetry instrumentors: {e}", exc_info=True)

    logger.info(f"Custom observability setup complete for service: {service_name}")
