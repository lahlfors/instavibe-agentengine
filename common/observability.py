import logging
import os
import sys
import google.auth
import google.auth.transport.requests
import grpc
from google.auth.transport.grpc import AuthMetadataPlugin
from dotenv import load_dotenv

from opentelemetry import trace, propagate, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
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
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient, GrpcInstrumentorServer

load_dotenv()

def setup_observability():
    service_name = os.environ.get("SERVICE_NAME", "my_adk_agent")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        stream=sys.stderr,
        force=True
    )
    logger = logging.getLogger(service_name)
    logger.info("--- setup_observability started ---")
    try:
        credentials, project_id = google.auth.default()
        logger.info(f"Google Cloud credentials fetched for project: {project_id}")
    except google.auth.exceptions.DefaultCredentialsError:
        logger.error(
            "Google Cloud credentials not found. Please run 'gcloud auth application-default login' or set up the environment.",
            exc_info=True
        )
        return

    resource = Resource(attributes={"service.name": service_name, "gcp.project_id": project_id})

    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)
    tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    logger.info("OpenTelemetry ConsoleSpanExporter configured.")

    meter_provider = MeterProvider(resource=resource)
    metrics.set_meter_provider(meter_provider)

    try:
        request = google.auth.transport.requests.Request()
        auth_metadata_plugin = AuthMetadataPlugin(credentials=credentials, request=request)
        ssl_creds = grpc.ssl_channel_credentials()
        channel_creds = grpc.composite_channel_credentials(
            ssl_creds,
            grpc.metadata_call_credentials(auth_metadata_plugin),
        )
        logger.debug(f"Type of channel_creds for OTLP exporters: {type(channel_creds)}")

        otlp_trace_exporter = OTLPSpanExporter(
            endpoint="telemetry.googleapis.com:443",
            credentials=channel_creds,
        )
        tracer_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))

        otlp_metric_exporter = OTLPMetricExporter(
            endpoint="telemetry.googleapis.com:443",
            credentials=channel_creds,
        )
        reader = PeriodicExportingMetricReader(otlp_metric_exporter)
        meter_provider.add_metric_reader(reader)

        logger.info("OpenTelemetry OTLP Trace and Metric exporters configured for telemetry.googleapis.com.")
    except Exception as e:
        logger.error(f"Failed to configure OTLP Exporters: {e}", exc_info=True)

    propagate.set_global_textmap(TraceContextTextMapPropagator())

    try:
        logging_client = google.cloud.logging.Client(project=project_id, credentials=credentials)
        logging_client.setup_logging(log_level=logging.INFO)
        logger.info("Google Cloud Logging client setup complete.")
    except Exception as e:
        logger.error(f"Failed to configure Google Cloud Logging: {e}")

    try:
        VertexAIInstrumentor().instrument()
        logger.info("VertexAIInstrumentor enabled.")
        RequestsInstrumentor().instrument()
        logger.info("RequestsInstrumentor enabled.")
        GrpcInstrumentorClient().instrument()
        GrpcInstrumentorServer().instrument()
        logger.info("GrpcInstrumentor enabled.")
    except Exception as e:
        logger.error(f"Error enabling OpenTelemetry instrumentors: {e}")

    logger.info(f"Observability setup complete for service: {service_name} in project {project_id}")
