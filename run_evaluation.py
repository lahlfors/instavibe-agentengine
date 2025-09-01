import vertexai
from vertexai.preview.evaluation import EvalTask
from agents.app.evaluators import evaluate_tool_choice # Import your custom function
import os

PROJECT_ID = "laah-genai"
LOCATION = "us-central1"
AGENT_ID = "social_agent_main" # Your Reasoning Engine ID
DATASET_URI = "gs://your-bucket-name/eval_dataset_adk.json" # Path to your dataset

vertexai.init(project=PROJECT_ID, location=LOCATION)

eval_task = EvalTask(
    dataset=DATASET_URI,
    metrics=[evaluate_tool_choice], # Pass your evaluator function here
    experiment="social-agent-tool-choice-eval-v3",
)

# NOTE: The custom evaluator uses the `trace_id` from the dataset, not from this new run.
# The `instance_config` is required by the API but our logic bypasses its output.
result = eval_task.execute(
    instance_config={
        "reasoning_engine": f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{AGENT_ID}"
    }
)

print(result.metrics)
print(result.html()) # Link to detailed results in the Cloud Console
