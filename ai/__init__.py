## Project_QLE/ai/__init__.py
from .gemini_interpreter import GeminiInterpreter
from .map_generator import property_map, isopach_map, structure_map

try:
    from .interpreter import AIInterpreter
except ImportError as exc:
    class AIInterpreter:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "AIInterpreter requires the Anthropic SDK. "
                "Install it with `pip install anthropic` or use GeminiInterpreter instead."
            ) from exc

__all__ = [
    "AIInterpreter", "GeminiInterpreter",
    "property_map", "isopach_map", "structure_map",
]