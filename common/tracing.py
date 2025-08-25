# in common/tracing.py

import logging
from opentelemetry import trace
from opentelemetry.exporter.gcp.trace import GcpSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# A simple flag to prevent this from running more than once.
_is_configured = False

def configure_tracer(service_name: str):
    """Configures the OpenTelemetry SDK to send traces to Google Cloud."""
    global _is_configured
    if _is_configured:
        return

    try:
        # A "Resource" identifies your application. The "service.name" is crucial
        # as it's how you'll filter for your agent's traces in Cloud Trace.
        resource = Resource(attributes={"service.name": service_name})

        # Set up the TracerProvider, which is the core of the SDK.
        tracer_provider = TracerProvider(resource=resource)

        # The GcpSpanExporter is what sends the trace data to Google Cloud.
        exporter = GcpSpanExporter()

        # The BatchSpanProcessor groups spans together before sending them.
        processor = BatchSpanProcessor(exporter)
        tracer_provider.add_span_processor(processor)

        # Register the configured provider as the global one.
        trace.set_tracer_provider(tracer_provider)

        _is_configured = True
        logging.info(f"OpenTelemetry Tracer configured for service: {service_name}")

    except Exception as e:
        logging.error(f"Failed to configure OpenTelemetry Tracer: {e}")
