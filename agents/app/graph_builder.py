from langgraph.graph import StateGraph, END
from agents.app.common.graph_state import OrchestratorState # Assuming this is a TypedDict or Pydantic model compatible with LangGraph
from agents.orchestrate.orchestrator_nodes import (
    entry_point_node,
    planner_router_node,
    output_node, # This is the actual function for the 'final_output_node'
    error_handler_node
)
from agents.planner.planner_node import execute_planner_node
from agents.social.social_exec_node import execute_social_node
from agents.platform_mcp_client.platform_exec_node import execute_platform_node

def build_graph():
    print("---Building Graph---")
    # Define the StateGraph with the OrchestratorState
    # LangGraph typically uses TypedDict for state. If OrchestratorState is Pydantic,
    # it needs to be compatible or converted (e.g. using .dict() and .parse_obj()).
    # For now, we assume direct compatibility or that OrchestratorState is effectively a TypedDict.
    workflow = StateGraph(OrchestratorState)

    # Add nodes to the graph
    # Ensure node names are consistent with their definitions and usage in edges/routing.
    workflow.add_node("entry_point", entry_point_node)
    workflow.add_node("planner_router", planner_router_node)
    workflow.add_node("planner_agent", execute_planner_node)
    workflow.add_node("social_agent", execute_social_node)
    workflow.add_node("platform_agent", execute_platform_node)
    workflow.add_node("error_handler", error_handler_node)
    workflow.add_node("final_output_node", output_node) # Using the imported 'output_node' function

    # Define edges

    # 1. Entry point
    workflow.set_entry_point("entry_point")

    # 2. From entry_point to planner_router or error_handler
    # Entry point node itself can set 'route' to 'error_handler' if user_request is missing
    def route_from_entry(state: OrchestratorState) -> str:
        print(f"---Routing from entry_point. Error: {state.get('error_message')}---")
        if state.get('error_message'):
            return "error_handler"
        return "planner_router"

    workflow.add_conditional_edges(
        "entry_point",
        route_from_entry,
        {
            "planner_router": "planner_router",
            "error_handler": "error_handler"
        }
    )

    # 3. Conditional edges from planner_router
    def decide_next_route(state: OrchestratorState) -> str:
        route = state.get('route') # This 'route' is set by planner_router_node's LLM call
        error_message = state.get('error_message') # Error message might be set by planner_router itself

        print(f"---Deciding next route from planner_router. Route: '{route}', Error: '{error_message}'---")

        if error_message and route != "final_responder": # If router or a previous step set an error
            # And it's not an error that should just be reported (e.g. "planner failed, going to final_responder")
            # This check might need refinement depending on how errors are propagated vs. explicit routing to final_responder with error info.
            # If planner_router itself decided 'error_handler', 'route' will be 'error_handler'.
            print(f"Error message present ('{error_message}'), routing to error_handler.")
            return "error_handler"

        if route == "planner":
            print("Routing to planner_agent.")
            return "planner_agent"
        elif route == "social":
            print("Routing to social_agent.")
            return "social_agent"
        elif route == "platform":
            print("Routing to platform_agent.")
            return "platform_agent"
        elif route == "final_responder":
            print("Routing to final_output_node.")
            return "final_output_node"
        elif route == "error_handler": # If router explicitly chose error_handler
            print("Routing to error_handler as per router's decision.")
            return "error_handler"
        else:
            print(f"Unknown or invalid route '{route}' from planner_router. Defaulting to error_handler.")
            state['error_message'] = f"Invalid route '{route}' decided by planner_router."
            return "error_handler"

    workflow.add_conditional_edges(
        "planner_router",
        decide_next_route,
        {
            "planner_agent": "planner_agent",
            "social_agent": "social_agent",
            "platform_agent": "platform_agent",
            "final_output_node": "final_output_node",
            "error_handler": "error_handler",
        }
    )

    # 4. From specialized agents back to planner_router for next decision
    workflow.add_edge("planner_agent", "planner_router")
    workflow.add_edge("social_agent", "planner_router")
    workflow.add_edge("platform_agent", "planner_router")

    # 5. From error_handler to final_output_node (to display the error)
    # The error_handler_node itself now sets route to "final_responder",
    # so this edge might be redundant if the graph uses that for conditional routing.
    # However, an explicit edge from error_handler to final_output_node is clearer.
    # Let's ensure error_handler_node's output is handled correctly by final_output_node.
    # The error_handler_node sets "intermediate_output" with error details.
    workflow.add_edge("error_handler", "final_output_node")

    # 6. End node
    # final_output_node is the last step that prepares the 'final_output' field in the state.
    # After this node, the graph should end.
    workflow.add_edge("final_output_node", END)

    # Compile the graph
    try:
        app = workflow.compile()
        print("---Graph Compiled Successfully---")
        return app
    except Exception as e:
        print(f"---Error Compiling Graph: {e}---")
        import traceback
        print(traceback.format_exc())
        raise

if __name__ == "__main__":
    # This is for basic testing of graph compilation and structure.
    from dotenv import load_dotenv
    import os

    # Ensure correct path to .env, assuming graph_builder.py is in agents/app/
    # So, ../../.env from agents/app/
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    print(f"Loading .env from: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)

    # Check if API key is loaded (optional, for info)
    # print(f"GOOGLE_API_KEY loaded: {'GOOGLE_API_KEY' in os.environ and bool(os.environ['GOOGLE_API_KEY'])}")

    graph_app = None
    try:
        graph_app = build_graph()
    except Exception as e:
        print(f"Failed to build graph in __main__: {e}")
        # Optional: exit or further error handling

    if graph_app:
        print("\nGraph built successfully. To run, you would invoke `graph_app.invoke(initial_state, config)`.")
        print("Example: final_state = graph_app.invoke({'user_request': 'Plan a trip to Paris.'}, {'recursion_limit': 10})")
        print("Then inspect final_state.get('final_output') or final_state['final_output']")
        print("\n---Simulating a graph run (conceptual)---")
        # This is a conceptual simulation. A real run needs actual invocation.
        # The following is a placeholder for how one might invoke and what to expect.

        # Example initial state
        initial_input_state = OrchestratorState(
            user_request="Can you plan a fun weekend in San Francisco for me, interested in food and parks?",
            current_task_description=None, # Will be set by entry_point
            intermediate_output=None,
            final_output=None,
            session_id=None, # Will be set by entry_point
            current_agent_name=None,
            error_message=None,
            route=None
        )

        print(f"Conceptual initial input: {initial_input_state}")
        print("If you were to run: `final_state = graph_app.invoke(initial_input_state, {'recursion_limit': 15})`")
        print("You would then check `final_state['final_output']` for the result from the output_node.")
        print("Note: Running the actual invocation here would require all API keys to be correctly set up and might incur costs.")
        print("Consider writing a separate test script for full invocation.")

    else:
        print("Graph building failed. Cannot proceed with example run.")
