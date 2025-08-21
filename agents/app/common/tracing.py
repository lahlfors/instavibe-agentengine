from functools import wraps
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
import inspect

def trace_function_enhanced(tracer: trace.Tracer, span_name: str = None, system_name: str = "UnknownSystem"):
    """
    A decorator to trace a function or method, capturing details and handling prompt extraction.

    Args:
        tracer: The OpenTelemetry tracer instance.
        span_name: Optional. The name for the span. Defaults to func.__qualname__.
        system_name: Optional. Identifier for the system for GenAI conventions.
    """

    def decorator(func):
        # Check if the function is a method by inspecting the first argument name
        sig = inspect.signature(func)
        first_param = next(iter(sig.parameters.values()), None)
        is_method = first_param and first_param.name == 'self'

        @wraps(func)
        def wrapper(*args, **kwargs):
            name = span_name or func.__qualname__
            with tracer.start_as_current_span(name) as span:
                span.set_attribute("function.name", func.__name__)
                span.set_attribute("function.qualname", func.__qualname__)
                span.set_attribute("function.is_method", is_method)

                # --- Prompt Extraction ---
                prompt = None
                if "prompt" in kwargs:
                    prompt = kwargs["prompt"]
                elif isinstance(kwargs.get("data"), dict):
                    prompt = kwargs["data"].get("prompt")
                else:
                    prompt_arg_index = 1 if is_method else 0
                    if len(args) > prompt_arg_index:
                        candidate = args[prompt_arg_index]
                        if isinstance(candidate, str):
                            prompt = candidate
                        elif isinstance(candidate, dict):
                             prompt = candidate.get("prompt")

                if prompt and isinstance(prompt, str):
                    span.set_attribute("agent.prompt", prompt)
                    # Align with OpenTelemetry Semantic Conventions for GenAI
                    span.set_attribute("gen_ai.system", system_name)
                    span.set_attribute("gen_ai.request.prompt", prompt)

                # --- Execution & Error Handling ---
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    # Optionally trace result:
                    # span.set_attribute("function.result", str(result)) # Be cautious with large results
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise
        return wrapper
    return decorator
