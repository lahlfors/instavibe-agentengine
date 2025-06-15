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
import logging

# Configure basic logging for the module if it's used standalone or for setup visibility
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
# More robust logger setup for this specific file:
logger = logging.getLogger(__name__)
if not logger.handlers: # Add a handler if none are configured, to ensure output
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def build_graph():
    logger.info("---Building Graph---")
    # Define the StateGraph with the OrchestratorState
    # OrchestratorState is a Pydantic model, which is compatible with LangGraph.
    workflow = StateGraph(OrchestratorState)

    # Add nodes to the graph
    logger.info("Adding nodes to the graph...")
    workflow.add_node("entry_point", entry_point_node)
    logger.info("Node 'entry_point' added.")
    workflow.add_node("planner_router", planner_router_node)
    logger.info("Node 'planner_router' added.")
    workflow.add_node("planner_agent", execute_planner_node)
    logger.info("Node 'planner_agent' added.")
    workflow.add_node("social_agent", execute_social_node)
    logger.info("Node 'social_agent' added.")
    workflow.add_node("platform_agent", execute_platform_node)
    logger.info("Node 'platform_agent' added.")
    workflow.add_node("error_handler", error_handler_node)
    logger.info("Node 'error_handler' added.")
    workflow.add_node("final_output_node", output_node) # Using the imported 'output_node' function
    logger.info("Node 'final_output_node' added.")

    # Define edges
    logger.info("Defining edges for the graph...")

    # 1. Entry point
    logger.info("Setting entry point to 'entry_point'.")
    workflow.set_entry_point("entry_point")

    # 2. From entry_point to planner_router or error_handler
    # Entry point node itself can set 'route' to 'error_handler' if user_request is missing
    def route_from_entry(state: OrchestratorState) -> str:
        # Access Pydantic model fields using attribute access
        error_msg = state.error_message
        logger.info(f"---Routing from entry_point. Error: {error_msg}---")
        if error_msg:
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
    logger.info("Added conditional edges from 'entry_point' to 'planner_router' or 'error_handler'.")

    # 3. Conditional edges from planner_router
    def decide_next_route(state: OrchestratorState) -> str:
        # Access Pydantic model fields using attribute access
        route = state.route
        error_message = state.error_message

        logger.info(f"---Deciding next route from planner_router. Route: '{route}', Error: '{error_message}'---")

        if error_message and route != "final_responder":
            logger.info(f"Error message present ('{error_message}'), routing to error_handler.")
            return "error_handler"

        if route == "planner":
            logger.info("Routing to planner_agent.")
            return "planner_agent"
        elif route == "social":
            logger.info("Routing to social_agent.")
            return "social_agent"
        elif route == "platform":
            logger.info("Routing to platform_agent.")
            return "platform_agent"
        elif route == "final_responder":
            logger.info("Routing to final_output_node.")
            return "final_output_node"
        elif route == "error_handler":
            logger.info("Routing to error_handler as per router's decision.")
            return "error_handler"
        else:
            logger.warning(f"Unknown or invalid route '{route}' from planner_router. Defaulting to error_handler.")
            # Direct mutation of state (e.g., state.error_message = ...) in a conditional function is not standard.
            # The preceding node (planner_router_node) should ideally set this error_message if it detects an invalid route.
            # If this path is taken, the error_handler_node should be robust enough to set a generic error.
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
    logger.info("Added conditional edges from 'planner_router'.")

    # 4. From specialized agents back to planner_router for next decision
    workflow.add_edge("planner_agent", "planner_router")
    logger.info("Added edge from 'planner_agent' to 'planner_router'.")
    workflow.add_edge("social_agent", "planner_router")
    logger.info("Added edge from 'social_agent' to 'planner_router'.")
    workflow.add_edge("platform_agent", "planner_router")
    logger.info("Added edge from 'platform_agent' to 'planner_router'.")

    # 5. From error_handler to final_output_node (to display the error)
    # The error_handler_node itself now sets route to "final_responder",
    # so this edge might be redundant if the graph uses that for conditional routing.
    # However, an explicit edge from error_handler to final_output_node is clearer.
    # Let's ensure error_handler_node's output is handled correctly by final_output_node.
    # The error_handler_node sets "intermediate_output" with error details.
    workflow.add_edge("error_handler", "final_output_node")
    logger.info("Added edge from 'error_handler' to 'final_output_node'.")

    # 6. End node
    # final_output_node is the last step that prepares the 'final_output' field in the state.
    # After this node, the graph should end.
    workflow.add_edge("final_output_node", END)
    logger.info("Added edge from 'final_output_node' to END.")

    # Compile the graph
    logger.info("Compiling the graph...")
    try:
        app = workflow.compile()
        logger.info("---Graph Compiled Successfully---")
        return app
    except Exception as e:
        logger.error(f"---Error Compiling Graph: {e}---", exc_info=True)
        raise

if __name__ == "__main__":
    # This __main__ block is for basic testing of graph compilation and structure.
    # Uses the logger configured at the top of this file.
    logger.info("Executing graph_builder.py as __main__ for testing.")

    from dotenv import load_dotenv
    import os

    # Ensure correct path to .env
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    logger.info(f"Attempting to load .env from: {dotenv_path}") # Use the file-specific logger
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path)
        logger.info(".env file loaded successfully.")
    else:
        logger.warning(f".env file not found at {dotenv_path}. Required environment variables might not be set.")

    # Example: Check if a specific environment variable expected by nodes is present
    # api_key = os.environ.get("SOME_API_KEY")
    # if not api_key:
    #     logger.warning("SOME_API_KEY environment variable is not set. Node execution requiring this key might fail.")

    graph_app = None
    try:
        logger.info("Attempting to build graph in __main__...")
        graph_app = build_graph()
    except Exception as e:
        logger.error(f"Failed to build graph in __main__: {e}", exc_info=True)

    if graph_app:
        logger.info("Graph built successfully in __main__.")
        logger.info("To run the graph, you would typically invoke `graph_app.invoke(initial_state_dict, config)`.")
        logger.info("Example: final_state = graph_app.invoke(initial_input_state.model_dump(), {'recursion_limit': 10})")
        logger.info("Inspect `final_state['final_output']` for the result.")

        logger.info("---Conceptual Graph Invocation Example---")
        # Example initial state using the Pydantic model
        initial_input_state = OrchestratorState(
            user_request="Plan a fun weekend in San Francisco, focus on parks and local food spots."
            # Other fields will use their default values (None or as defined in Pydantic model)
        )

        logger.info(f"Conceptual initial input state (as model_dump): {initial_input_state.model_dump()}")
        logger.info("To perform an actual run: `final_state = graph_app.invoke(initial_input_state.model_dump(), {'recursion_limit': 15})`")
        logger.info("Then, you would check `final_state.get('final_output')` or access other fields from the resulting state dictionary.")
        logger.info("Note: A real invocation would execute all node logic, potentially making external API calls if nodes are designed to do so.")
        logger.info("For comprehensive testing, consider creating dedicated test files (e.g., using pytest) that can mock external services if needed.")

    else:
        logger.error("Graph building failed in __main__. Cannot provide invocation example.")
