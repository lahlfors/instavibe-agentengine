# In a new file, e.g., agents/app/evaluators.py
from google.cloud import trace_v1
from google.api_core import exceptions
import logging
import os

def evaluate_tool_choice(instance: dict) -> dict:
    """
    An evaluator function that checks if the correct tool was called
    by inspecting OpenTelemetry trace data.

    Args:
        instance: A dictionary representing one row from the evaluation dataset.
                  It must contain 'trace_id' and 'ground_truth_tool'.

    Returns:
        A dictionary with the metric name 'tool_choice_accuracy' and the score (1.0 or 0.0).
    """
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") # Or hardcode for testing
    if not project_id:
        # Fallback, replace with your project ID
        project_id = "laah-genai"
        logging.warning(f"GOOGLE_CLOUD_PROJECT env var not set, using fallback: {project_id}")

    trace_id = instance.get("trace_id")
    expected_tool = instance.get("ground_truth_tool")

    if not trace_id or not expected_tool:
        return {"tool_choice_accuracy": 0.0, "explanation": "Missing trace_id or ground_truth_tool in dataset."}

    try:
        trace_client = trace_v1.TraceServiceClient()
        request = trace_v1.GetTraceRequest(project_id=project_id, trace_id=trace_id)
        trace = trace_client.get_trace(request=request)

        found_tools = []
        for span in trace.spans:
            if "tool.name" in span.attributes:
                actual_tool = span.attributes["tool.name"].string_value
                found_tools.append(actual_tool)
                if actual_tool == expected_tool:
                    # Additional checks can be added here, e.g., on tool.input attributes
                    return {"tool_choice_accuracy": 1.0, "explanation": f"Correctly chose tool: {actual_tool}"}

        if found_tools:
            return {"tool_choice_accuracy": 0.0, "explanation": f"Incorrect tool(s). Expected: {expected_tool}, Got: {found_tools}"}
        else:
            return {"tool_choice_accuracy": 0.0, "explanation": "No tool call with 'tool.name' attribute found in trace."}

    except exceptions.NotFound:
        logging.warning(f"Trace not found for project {project_id}, trace_id: {trace_id}")
        return {"tool_choice_accuracy": 0.0, "explanation": f"Trace ID not found: {trace_id}"}
    except Exception as e:
        logging.error(f"Error processing trace {trace_id}: {e}", exc_info=True)
        return {"tool_choice_accuracy": 0.0, "explanation": f"Error during trace processing: {str(e)}"}
