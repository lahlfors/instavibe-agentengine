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
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

load_dotenv()

def setup_observability():
    """Sets up ADDITIONAL custom OpenTelemetry features.
    Assumes AdkApp(enable_tracing=True) handles base Cloud Trace export.
    """
    logger = logging.getLogger(__name__)
    logger.info("Initializing custom OpenTelemetry components from common.observability...")

    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        logger.warning("TracerProvider not yet initialized. Customizations might not apply as expected.")
        # Optionally, initialize a basic provider, but be cautious about conflicts with AdkApp
        # trace.set_tracer_provider(TracerProvider())
        # provider = trace.get_tracer_provider()

    # Example: Add a custom Span Processor
    # from .observability_utils import MyCustomSpanProcessor
    # processor = MyCustomSpanProcessor()
    # provider.add_span_processor(processor)
    # logger.info("Added MyCustomSpanProcessor.")

    # Example: Add custom resource attributes
    # from opentelemetry.sdk.resources import get_aggregated_resources, Resource
    # extra_resource = Resource({"my.custom.attr": "value"})
    # trace.get_tracer_provider().resource = get_aggregated_resources([
    #     trace.get_tracer_provider().resource,
    #     extra_resource
    # ])
    # logger.info("Merged custom OpenTelemetry Resource attributes.")

    logger.info("Custom OpenTelemetry components initialized.")
