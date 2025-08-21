from opentelemetry import trace
from google.adk.agents import Agent

# Get a tracer for this module
tracer = trace.get_tracer(__name__)

class TracedLlmAgent(Agent):
    """A wrapper agent that adds OpenTelemetry tracing to another agent."""

    def __init__(self, wrapped_agent: Agent):
        # Store the agent we're wrapping
        self.wrapped_agent = wrapped_agent
        # Copy over necessary attributes from the wrapped agent
        super().__init__(
            name=f"traced_{wrapped_agent.name}",
            model=getattr(wrapped_agent, "model", None) # Safely get model
        )
        if hasattr(wrapped_agent, 'model'):
             self.model = wrapped_agent.model

    def invoke(self, prompt: str) -> str:
        """Wraps the invoke call with a trace span."""
        span_name = f"{self.wrapped_agent.name}.invoke"

        with tracer.start_as_current_span(span_name) as span:
            # Add the prompt and other details as attributes to the span
            span.set_attribute("agent.name", self.wrapped_agent.name)
            if hasattr(self.wrapped_agent, 'model'):
                 span.set_attribute("agent.model", self.wrapped_agent.model)
            span.set_attribute("agent.prompt", prompt)

            # Align with OpenTelemetry Semantic Conventions for GenAI
            span.set_attribute("gen_ai.system", "instavibe")
            span.set_attribute("gen_ai.operation.name", "invoke")
            span.set_attribute("gen_ai.request.prompt", prompt)
            if hasattr(self.wrapped_agent, 'model'):
               span.set_attribute("gen_ai.request.model", self.wrapped_agent.model)

            try:
                # Call the original agent's logic
                result = self.wrapped_agent.invoke(prompt)
                span.set_attribute("agent.result", result)
                span.set_attribute("gen_ai.response.completions.0.content", result)
                return result
            except Exception as e:
                # Record exceptions in the trace
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise
