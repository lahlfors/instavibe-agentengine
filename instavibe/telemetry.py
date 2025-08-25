import os
import sys
sys.path.append('.')
from common.tracing import configure_tracer
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

def setup_telemetry(app):
    """
    Sets up OpenTelemetry for the Flask application using the central config.
    """
    # Use an env var to determine if tracing should be enabled.
    if os.getenv("ADK_TRACE_TO_CLOUD", "false").lower() == "true":
        # Configure the tracer with a specific service name
        configure_tracer(service_name="instavibe-app")

        # Instrument Flask and Requests
        FlaskInstrumentor().instrument_app(app)
        RequestsInstrumentor().instrument()

        print("OpenTelemetry tracing enabled for instavibe-app via common config.")
