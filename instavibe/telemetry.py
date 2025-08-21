import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

def setup_telemetry(app):
    """
    Sets up OpenTelemetry for the Flask application.
    """
    if os.getenv("ADK_TRACE_TO_CLOUD", "false").lower() == "true":
        # Create a resource to identify the service
        resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "instavibe-app")})

        # Create a tracer provider
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)

        # Create an OTLP exporter
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        if otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        else:
            # Default to Google Cloud Trace if no endpoint is specified
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
            otlp_exporter = CloudTraceSpanExporter()

        # Add a span processor to the tracer provider
        tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        # Instrument Flask and Requests
        FlaskInstrumentor().instrument_app(app)
        RequestsInstrumentor().instrument()

        print(f"OpenTelemetry tracing enabled for instavibe-app, exporting to: {otlp_endpoint or 'Google Cloud Trace'}")
