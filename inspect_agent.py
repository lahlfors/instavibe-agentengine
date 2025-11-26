import inspect
from vertexai.preview import reasoning_engines
from agents.orchestrate.orchestrate_service_agent import OrchestrateServiceAgent

AdkApp = reasoning_engines.AdkApp

print("\nInspecting AdkApp...")
print(f"AdkApp type: {type(AdkApp)}")
print(f"AdkApp dir: {dir(AdkApp)}")

from agents.planner.agent import PlannerAgent

try:
    print("\nInspecting AdkApp instance wrapping PlannerAgent...")
    planner = PlannerAgent(name="planner", model="gemini-pro")
    app_planner = AdkApp(agent=planner)
    print(f"App (Planner) dir: {dir(app_planner)}")
    
    if hasattr(app_planner, 'query'):
        print(f"FOUND query on AdkApp(Planner) instance: {app_planner.query}")
    else:
        print("Did NOT find query on AdkApp(Planner) instance.")

    print("\nInspecting AdkApp instance wrapping OrchestrateServiceAgent...")
    agent = OrchestrateServiceAgent(name="test", model="gemini-pro")
    app = AdkApp(agent=agent)
    print(f"App (Orchestrate) dir: {dir(app)}")
    
    if hasattr(app, 'query'):
        print(f"FOUND query on AdkApp(Orchestrate) instance: {app.query}")
    else:
        print("Did NOT find query on AdkApp(Orchestrate) instance.")

except Exception as e:
    print(f"Error inspecting AdkApp instance: {e}")
