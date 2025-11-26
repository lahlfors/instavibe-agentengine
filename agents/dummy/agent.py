"""Pure synchronous dummy agent for control testing.

This agent has NO async code whatsoever, no ADK base classes,
and a simple synchronous query method to test if the deployment
environment can handle pure sync agents.
"""

class DummyAgent:
    """Vanilla Python class with no ADK inheritance."""
    
    def __init__(self, name: str = "dummy_agent", **kwargs):
        self.name = name
        # Store any kwargs for compatibility
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def query(self, input: str = "", **kwargs):
        """
        Pure synchronous query method.
        NO async, NO yield, just a simple return.
        """
        message = kwargs.get("message", input)
        return f"DummyAgent echo: {message}"
    
    def set_up(self, **kwargs):
        """Optional setup method for compatibility."""
        return self


# Module-level instance for deployment
root_agent = DummyAgent(name="dummy_agent")
