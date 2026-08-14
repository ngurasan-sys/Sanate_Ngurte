import sys
import backend.app

sys.modules["app"] = backend.app
import backend.app.core.event_bus
sys.modules["app.core"] = backend.app.core
sys.modules["app.core.event_bus"] = backend.app.core.event_bus
