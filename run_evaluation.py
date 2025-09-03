import os
import json
import logging

import vertexai
from google.cloud import storage
from opentelemetry import trace

from common.observability import setup_observability, get_trace_context

# --- Configuration ---
# Set a distinct service name for the evaluation process
os.environ["OTEL_SERVICE_NAME"] = "instavibe-evaluation-suite"

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "laah-genai")
LOCATION = "us-central1"
AGENT_ID = "social_agent_main" # Your Reasoning Engine ID
# This should be a JSONL file where each line is a dictionary with a "prompt" key.
DATASET_URI = "gs://your-bucket-name/eval_dataset_adk.json"

# --- Initialization ---
# Ensure OTEL_COLLECTOR_ENDPOINT is set in the environment where this script runs
# to point to your collector on Cloud Run.
setup_observability()

tracer = trace.get_tracer(__name__)
log = logging.getLogger(__name__)

vertexai.init(project=PROJECT_ID, location=LOCATION)

def download_gcs_jsonl(gcs_uri: str) -> list[dict]:
    """Downloads a JSONL file from GCS and returns a list of dictionaries."""
    log.info(f"Downloading dataset from {gcs_uri}")
    storage_client = storage.Client()
    bucket_name = gcs_uri.split("/")[2]
    blob_name = "/".join(gcs_uri.split("/")[3:])
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    content = blob.download_as_text()
    return [json.loads(line) for line in content.strip().split("\n")]

def main():
    """
    Runs the evaluation by sending prompts from a dataset to a reasoning engine
    and capturing OpenTelemetry traces for each interaction.
    """
    log.info("--- Starting Instavibe Evaluation Suite ---")

    try:
        from vertexai.preview import reasoning_engines
        agent_resource_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{AGENT_ID}"
        log.info(f"Connecting to Reasoning Engine: {agent_resource_name}")
        agent = reasoning_engines.get(agent_resource_name)
        log.info("Successfully connected to Reasoning Engine.")
    except Exception as e:
        log.error(f"Failed to initialize Reasoning Engine: {e}", exc_info=True)
        return

    try:
        dataset = download_gcs_jsonl(DATASET_URI)
        log.info(f"Successfully loaded {len(dataset)} test cases from dataset.")
    except Exception as e:
        log.error(f"Failed to load dataset from {DATASET_URI}: {e}", exc_info=True)
        return

    for i, test_case in enumerate(dataset):
        prompt = test_case.get("prompt")
        test_case_id = test_case.get("id", f"case_{i+1}")

        if not prompt:
            log.warning(f"Skipping test case {test_case_id} due to missing 'prompt'.")
            continue

        with tracer.start_as_current_span("eval_test_case") as case_span:
            case_span.set_attribute("test_case.id", test_case_id)
            log.info(f"Running test case {test_case_id}", extra=get_trace_context())

            try:
                with tracer.start_as_current_span("call_agent") as agent_span:
                    agent_span.set_attribute("eval.prompt", prompt)
                    log.info("Calling agent for evaluation.", extra=get_trace_context())

                    # The agent call itself will generate child spans.
                    # This parent span groups the agent interaction within the test case.
                    response = agent.query(input=prompt)

                    # You can optionally log the response or parts of it
                    log.info(f"Agent response received for {test_case_id}.", extra=get_trace_context())
                    agent_span.set_attribute("eval.response.summary", str(response)[:256]) # Log a summary

            except Exception as e:
                log.error(f"Error calling agent for test case {test_case_id}: {e}", exc_info=True)
                case_span.record_exception(e)
                case_span.set_status(trace.Status(trace.StatusCode.ERROR, description=str(e)))

    log.info("--- Evaluation run complete ---", extra=get_trace_context())


if __name__ == "__main__":
    main()
