# This file previously defined the AgentTaskManager class (and potentially
# AgentWithTaskManager or similar), which served as a base class for agents
# in an older Agent Development Kit (ADK) framework.
#
# With the refactoring to a LangGraph-based architecture, agents no longer
# inherit from AgentTaskManager. The responsibilities of task handling and
# request processing are now managed by the LangGraph runtime and the
# individual agent (node) implementations.
#
# This file's contents have been removed as they are no longer needed.
# Consider fully deleting this file if it remains unused and unreferenced.

import logging
logging.info("agents.app.common.task_manager.py is now empty. Its previous ADK-specific classes have been removed.")
