from opentelemetry import trace
from google.adk import agents
import aiohttp

# Get a tracer for your agent's module
tracer = trace.get_tracer(__name__)

async def call_agent_capability(source_agent: str, target_agent: str, capability: str, prompt: dict) -> dict:
    """
    A wrapper to trace an A2A call between agents.
    """
    # Create a span with a descriptive name
    with tracer.start_as_current_span(f"a2a.{capability}") as span:
        print(f"Starting trace for A2A call from {source_agent} to {target_agent}")

        # --- Add Rich Attributes for Protocol and Routing ---
        span.set_attribute("messaging.system", "adk-a2a") # Protocol identifier
        span.set_attribute("messaging.operation", "invoke")
        span.set_attribute("agent.source", source_agent)
        span.set_attribute("agent.target", target_agent)
        span.set_attribute("agent.capability", capability)

        # --- Add Rich Attributes for Prompt and Payload ---
        span.set_attribute("gen_ai.prompt.content", str(prompt))

        try:
            # --- Your actual agent communication logic goes here ---
            agent = agents.find(target_agent)
            if not agent:
                raise ValueError(f"Agent '{target_agent}' not found.")

            capability_obj = agent.a2a.get_capability(capability)
            if not capability_obj:
                raise ValueError(f"Capability '{capability}' not available on agent '{target_agent}'.")

            response = await capability_obj.invoke(prompt)
            span.set_attribute("gen_ai.response.content", str(response))

            if hasattr(response, 'candidates') and response.candidates:
                thought_summaries = []
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'thought') and part.thought and hasattr(part, 'text') and part.text:
                        thought_summaries.append(part.text)
                if thought_summaries:
                    span.set_attribute("reasoning.thoughts", "\n".join(thought_summaries))

            span.set_attribute("response.text", str(response))
            span.set_status(trace.StatusCode.OK)
            return response

        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, f"A2A call failed: {e}")
            raise


async def call_http_endpoint(source_agent: str, target_service: str, http_method: str, url: str, headers: dict, json: dict) -> dict:
    """
    A wrapper to trace an HTTP call to an external service.
    """
    # Create a span with a descriptive name
    with tracer.start_as_current_span(f"http.{http_method.lower()}") as span:
        print(f"Starting trace for HTTP call from {source_agent} to {target_service}")

        # --- Add Rich Attributes for Protocol and Routing ---
        span.set_attribute("messaging.system", "http") # Protocol identifier
        span.set_attribute("messaging.operation", http_method.upper())
        span.set_attribute("agent.source", source_agent)
        span.set_attribute("agent.target", target_service)
        span.set_attribute("http.url", url)

        # --- Add Rich Attributes for Prompt and Payload ---
        span.set_attribute("prompt.text", str(json))

        try:
            # --- Your actual HTTP call logic goes here ---
            async with aiohttp.ClientSession() as session:
                async with session.request(method=http_method, url=url, headers=headers, json=json) as response:
                    response.raise_for_status()
                    response_data = await response.json()

            span.set_attribute("response.text", str(response_data))
            span.set_status(trace.StatusCode.OK)
            return response_data

        except aiohttp.ClientError as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, f"HTTP call failed: {e}")
            raise
