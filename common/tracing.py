import logging
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def configure_tracer(service_name: str):
    """Configures the OpenTelemetry SDK to send traces to Google Cloud."""
    # Check if a TracerProvider is already configured.
    # The default is a ProxyTracerProvider, so if it's anything else,
    # it has been configured.
    if not isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider):
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
