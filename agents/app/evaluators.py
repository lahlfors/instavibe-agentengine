from google.cloud import trace_v1
from google.api_core import exceptions
import logging
import os

def evaluate_tool_choice(instance: dict) -> dict:
    """
    Fetches an OTel trace and evaluates if the correct tool was called.

    This evaluator is designed to work with an EvalCase that has a `metadata`
    field containing the `trace_id` and ground truth information.
    """
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "your-fallback-project-id")

    metadata = instance.get("metadata", {})
    trace_id = metadata.get("trace_id")
    expected_tool = metadata.get("ground_truth_tool")

    if not trace_id or not expected_tool:
        return {"tool_choice_accuracy": 0.0, "explanation": "Missing trace_id or ground_truth_tool in metadata."}

    try:
        trace_client = trace_v1.TraceServiceClient()
        request = trace_v1.GetTraceRequest(project_id=project_id, trace_id=trace_id)
        trace_data = trace_client.get_trace(request=request)

        # Find all spans with a tool.name attribute
        tool_spans = [
            span for span in trace_data.spans if "tool.name" in span.attributes
        ]

        if not tool_spans:
            return {"tool_choice_accuracy": 0.0, "explanation": "No tool call found in trace."}

        # Check if the expected tool was called
        found_span = None
        found_tool_names = []
        for span in tool_spans:
            tool_name = span.attributes["tool.name"].string_value
            found_tool_names.append(tool_name)
            if tool_name == expected_tool:
                found_span = span

        if found_span:
            # Tool was found, now check inputs if specified
            expected_sentiment = metadata.get("ground_truth_sentiment")
            if expected_sentiment:
                actual_sentiment_attr = found_span.attributes.get("tool.input.sentiment")
                if actual_sentiment_attr and actual_sentiment_attr.string_value == expected_sentiment:
                    return {"tool_choice_accuracy": 1.0, "explanation": "Correctly chose tool and inputs."}
                else:
                    actual_sentiment = actual_sentiment_attr.string_value if actual_sentiment_attr else "Not found"
                    return {"tool_choice_accuracy": 0.0, "explanation": f"Correct tool, but wrong input. Expected sentiment: '{expected_sentiment}', Got: '{actual_sentiment}'"}

            # Correct tool, no input validation requested for this instance
            if len(found_tool_names) > 1:
                 return {"tool_choice_accuracy": 1.0, "explanation": f"Correctly chose {expected_tool}, but also called other tools: {found_tool_names}"}
            return {"tool_choice_accuracy": 1.0, "explanation": f"Correctly chose tool: {expected_tool}"}
        else:
            # Expected tool was not found
            return {"tool_choice_accuracy": 0.0, "explanation": f"Incorrect tool(s). Expected: {expected_tool}, Got: {found_tool_names}"}

    except exceptions.NotFound:
        return {"tool_choice_accuracy": 0.0, "explanation": f"Trace ID not found: {trace_id}"}
    except Exception as e:
        return {"tool_choice_accuracy": 0.0, "explanation": f"Error processing trace: {str(e)}"}
