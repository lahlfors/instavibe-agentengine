import logging
import os
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def setup_observability(service_name: str):
    """
    Sets up OpenTelemetry for a service, including Cloud Trace and structured
    logging.
    """
    # --- Cloud Trace Setup ---
    # Check if a TracerProvider is already configured.
    if not isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider):
        # The provider is already configured, so we do nothing.
        return

    # A "Resource" identifies your application. The "service.name" is crucial
    # as it's how you'll filter for your agent's traces in Cloud Trace.
    resource = Resource(attributes={"service.name": service_name})

    # Set up the TracerProvider, which is the core of the SDK.
    tracer_provider = TracerProvider(resource=resource)

    # The OTLPSpanExporter is what sends the trace data to Google Cloud.
    exporter = OTLPSpanExporter()

    # The BatchSpanProcessor groups spans together before sending them.
    processor = BatchSpanProcessor(exporter)
    tracer_provider.add_span_processor(processor)

    # Register the configured provider as the global one.
    trace.set_tracer_provider(tracer_provider)

    logging.info(f"OpenTelemetry Tracer configured for service: {service_name}")

    # --- Structured Logging Setup ---
    # a "Resource" identifies your application
    from google.cloud.logging_v2.handlers import CloudLoggingHandler
    import google.cloud.logging

    # Instantiates a client
    client = google.cloud.logging.Client()

    # Retrieves a Cloud Logging handler based on the environment
    # you're running in and integrates the handler with the
    # Python logging module. By default this captures all logs
    # at INFO level and higher.
    handler = CloudLoggingHandler(client, resource=resource)
    google.cloud.logging.handlers.setup_logging(handler)
    logging.info("Structured logging configured.")
