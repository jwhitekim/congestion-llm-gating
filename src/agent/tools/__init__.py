"""
향후 LLM tool-use 확장을 위한 관측 도구 레지스트리.

현재 논문 구현에서는 TOOL_ONLY가 비어 있어 도구를 호출하지 않는다.
새 도구 추가 방법: 이 패키지에 파일을 하나 추가하고 함수에
@register_tool(...)을 붙이면 된다. 이 파일이나 loop.py는 건드릴 필요 없다.
"""

import importlib
import pkgutil

_REGISTRY: dict[str, dict] = {}


def register_tool(name: str, description: str, input_schema: dict):
    def decorator(func):
        _REGISTRY[name] = {
            "schema": {
                "name": name,
                "description": description,
                "input_schema": input_schema,
            },
            "func": func,
        }
        return func

    return decorator


def execute_tool(name: str, facts, **kwargs) -> dict:
    entry = _REGISTRY.get(name)
    if entry is None:
        return {"error": f"Unknown tool: {name}"}
    return entry["func"](facts, **kwargs)


# 패키지 내 모든 모듈을 임포트해 @register_tool 데코레이터가 실행되게 한다.
for _, _module_name, _ in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module_name}")

TOOLS = [entry["schema"] for entry in _REGISTRY.values()]
