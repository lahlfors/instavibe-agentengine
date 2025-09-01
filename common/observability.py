# common/observability.py

import logging
import os
from typing import Final

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

# A fallback name if the service name isn't set in the environment
DEFAULT_SERVICE_NAME: Final[str] = "my-adk-app"

log = logging.getLogger(__name__)


def setup_observability():
    """
    Initializes a standard, centralized OpenTelemetry pipeline.

    This function checks for an existing standard TracerProvider and, if one
    is not found, it configures a new one with a consistent resource,
    standard exporters, and default instrumentation.

    It is designed to be idempotent, so it can be safely called at the
    beginning of any application entry point.
    """
    # Check if a standard provider is already configured. If so, do nothing.
    if isinstance(trace.get_tracer_provider(), SdkTracerProvider):
        log.info("A standard SdkTracerProvider is already configured.")
        return

    # 1. Define a consistent Resource for all telemetry signals.
    resource = Resource.create(
        {
            "service.name": os.getenv("SERVICE_NAME", DEFAULT_SERVICE_NAME),
            "gcp.project_id": os.getenv("GOOGLE_CLOUD_PROJECT"),
        }
    )

    # 2. Create and set the standard SdkTracerProvider.
    # This will overwrite any non-standard provider set by other libraries.
    log.warning("No standard SdkTracerProvider found. Initializing a new one.")
    provider = SdkTracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    # 3. Configure Exporters and Processors.
    # Export to the console for easy local debugging.
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    # Export to an OTLP endpoint for production-grade tracing.
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

    log.info("SdkTracerProvider configured with Console and OTLP exporters.")

    # 4. Apply standard instrumentation for common libraries.
    RequestsInstrumentor().instrument()
    log.info("Standard library instrumentation for 'requests' has been applied.")
