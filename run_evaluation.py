# In a script to run evaluation, e.g., run_evaluation.py
import vertexai
from vertexai.preview.evaluation import EvalTask
from agents.app.evaluators import evaluate_tool_choice # Import your custom function
import os

PROJECT_ID = "laah-genai" # Your GCP Project ID
LOCATION = "us-central1"  # Your agent's region

vertexai.init(project=PROJECT_ID, location=LOCATION)

# The agent_id from your deployment labels or Reasoning Engine ID
AGENT_ID = "social_agent_main"
REASONING_ENGINE_NAME = f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{AGENT_ID}"

# GCS path to your evaluation dataset
DATASET_URI = "gs://your-bucket-name/eval_dataset.jsonl"

eval_task = EvalTask(
    dataset=DATASET_URI,
    metrics=[evaluate_tool_choice], # Pass your custom evaluator function
    experiment="social-agent-tool-choice-eval-v2", # Name for the experiment run
)

# Run the evaluation against your deployed agent (e.g., Reasoning Engine)
# The Evaluation Service will call the Reasoning Engine for each 'input_text' in the dataset.
# NOTE: The custom evaluator uses the trace_id *from the dataset*, it does not need the trace from this new run.
# The instance_config here is just to fulfill the API requirements,
# but our evaluator logic relies on the pre-existing trace_ids.
result = eval_task.execute(
     instance_config={"reasoning_engine": REASONING_ENGINE_NAME}
)

print("Evaluation run complete.")
print(result.metrics)
# print(result.html()) # To get a link to the results
