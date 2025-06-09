# agents/app/common/types.py
class AgentCard:
    def __init__(self, name=None, description=None, url=None, version=None, defaultInputModes=None, defaultOutputModes=None, capabilities=None, skills=None):
        self.name = name
        self.description = description
        self.url = url
        self.version = version
        self.defaultInputModes = defaultInputModes
        self.defaultOutputModes = defaultOutputModes
        self.capabilities = capabilities
        self.skills = skills
class AgentCapabilities:
    def __init__(self, streaming=False):
        self.streaming = streaming
class AgentSkill:
    def __init__(self, id=None, name=None, description=None, tags=None, examples=None):
        self.id = id
        self.name = name
        self.description = description
        self.tags = tags
        self.examples = examples
class Message: pass
class TaskState: pass
class Task: pass
class TaskSendParams: pass
class TextPart: pass
class DataPart: pass
class Part: pass
class TaskStatusUpdateEvent: pass
print("DEBUG: common.types loaded") # Debug print
