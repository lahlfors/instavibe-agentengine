import os
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from common.tracing import configure_tracer

def setup_telemetry(app, service_name):
    """
    Sets up OpenTelemetry for a Flask application.
    """
    # Use an env var to determine if tracing should be enabled.
    if os.getenv("ADK_TRACE_TO_CLOUD", "false").lower() == "true":
        configure_tracer(service_name=service_name)

        # Instrument Flask and Requests
        FlaskInstrumentor().instrument_app(app)
        RequestsInstrumentor().instrument()

        print(f"OpenTelemetry tracing enabled for {service_name} via common config.")
