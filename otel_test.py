import os
import logging
import time

# Set env vars for gRPC debugging
os.environ['GRPC_TRACE'] = 'all'
os.environ['GRPC_VERBOSITY'] = 'debug'

# Set a dummy service name for observability
os.environ['SERVICE_NAME'] = 'otel-test'

# It's important to set up the environment variables before this import
from common.observability import setup_observability

# Configure basic logging to see the output from the observability module
logging.basicConfig(level=logging.INFO)

print("--- Running OpenTelemetry Test Script ---")
setup_observability()
print("--- setup_observability() called. Waiting for exporters... ---")

# Keep the script running for a bit to allow background exporters to send data
time.sleep(10)

print("--- Test script finished. ---")
