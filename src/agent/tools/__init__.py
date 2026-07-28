"""
향후 LLM tool-use 확장을 위한 관측 도구 레지스트리.

현재 논문 구현에서는 등록된 도구가 없고 provider/loop의 tool-use 경로도
제거돼 있어 LLM이 외부 도구를 호출하지 않는다. 이 registry는 도구 파일을
자동 등록하는 기반만 제공하며, 파일과 @register_tool(...)을 추가하는 것만으로
LLM tool-use가 활성화되지는 않는다.
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
