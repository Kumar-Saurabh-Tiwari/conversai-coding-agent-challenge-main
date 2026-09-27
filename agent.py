"""
TOOLS
Pre-read the task's named source files and injected test, then expose the model's
small edit/read/test actions through the supplied tools only.

LOOP
Use one model call for an initial focused patch, run tests, and spend later calls
on failure-driven repairs. The prompt carries the latest tool result verbatim.

FAILURE HANDLING
Malformed actions and tool exceptions become feedback. Patches are delegated to
the atomic patch API, so a bad replacement does not partially modify a file.

STOPPING
Return immediately after a passing test run or an explicit finish; otherwise
stop at the five-call model budget with the latest outcome.
"""

from __future__ import annotations

import json
import re
from typing import Any


SYSTEM_PROMPT = """
You are a precise coding agent working inside a large Python repository.

Solve the user's task by inspecting files, making a focused source-code change,
and running tests. Return exactly one JSON object on every turn.

Available actions:
{"action":"list_files"}
{"action":"read_file","path":"relative/path.py"}
{"action":"write_file","path":"relative/path.py","content":"complete file"}
{"action":"patch_file","path":"relative/path.py","replacements":[{"old":"exact existing text","new":"replacement text"}]}
{"action":"run_tests"}
{"action":"finish","summary":"what happened"}

`patch_file` is preferred for large files. Each replacement may include an
optional 1-based `occurrence` when its old text appears more than once.

Rules:
- The user task and an initial context packet are supplied before this turn.
- Implement the smallest root-cause fix in the named source file; never edit tests.
- Preserve existing APIs, nearby style, and behavior outside the bug.
- Prefer patch_file with exact surrounding text. Do not merely describe a patch.
- If the named function delegates behavior, read one directly related helper before
    editing. Do not spend turns listing the whole repository.
- After an edit, tests run automatically. If they fail, use the traceback to repair
    the implementation, not to explain the failure.
- A passing visible test is not enough: retain the requested edge-case behavior
    and ordinary behavior described in the task.
- Return exactly one JSON object, with no markdown or commentary.
""".strip()


def _source_paths(task: str) -> list[str]:
    paths = re.findall(r"(?:src|pytest)[/\\][A-Za-z0-9_./\\-]+\.py", task)
    result: list[str] = []
    for path in paths:
        normalized = path.replace("\\", "/")
        if normalized not in result:
            result.append(normalized)
    return result


def _context(task: str, tools: Any) -> str:
    pieces = []
    for path in _source_paths(task):
        try:
            pieces.append(f"SOURCE {path}:\n{tools.read_file(path)}")
        except Exception as error:
            pieces.append(f"SOURCE {path}: READ_ERROR {error}")
    try:
        pieces.append(f"VISIBLE TEST:\n{tools.read_file('tests/test_task.py')}")
    except Exception as error:
        pieces.append(f"VISIBLE TEST: READ_ERROR {error}")
    return "\n\n".join(pieces)


def parse_action(response: str) -> dict[str, Any]:
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    value = json.loads(text)
    if not isinstance(value, dict) or not isinstance(value.get("action"), str):
        raise ValueError("Expected a JSON object containing an action")
    return value


def execute_action(action: dict[str, Any], tools: Any) -> str:
    name = action["action"]
    if name == "list_files":
        return tools.list_files()
    if name == "read_file":
        return tools.read_file(str(action.get("path", "")))
    if name == "write_file":
        return tools.write_file(
            str(action.get("path", "")),
            str(action.get("content", "")),
        )
    if name == "patch_file":
        replacements = action.get("replacements")
        if not isinstance(replacements, list):
            raise ValueError("patch_file requires a replacements list")
        return tools.patch_file(str(action.get("path", "")), replacements)
    if name == "run_tests":
        return tools.run_tests()
    if name == "finish":
        return str(action.get("summary", "Finished"))
    raise ValueError(f"Unknown action: {name}")


def solve(task: str, tools: Any, llm: Any) -> str:
    context = _context(task, tools)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"TASK:\n{task}\n\nINITIAL CONTEXT:\n{context}\n\n"
                "Choose the next concrete action. Begin by implementing the fix."
            ),
        },
    ]

    for _ in range(5):
        try:
            response = llm.ask(messages)
        except Exception as error:
            return f"MODEL_ERROR: {error}"
        messages.append({"role": "assistant", "content": response})
        try:
            action = parse_action(response)
            if action["action"] == "finish":
                result = tools.run_tests()
                if result.startswith("Exit code: 0"):
                    return str(action.get("summary", "Finished"))
                messages.append({"role": "user", "content": f"Tool result:\n{result}"})
                continue
            result = execute_action(action, tools)
            if action["action"] in {"write_file", "patch_file"}:
                test_result = tools.run_tests()
                result = f"{result}\n\nAUTOMATIC TEST RUN:\n{test_result}"
                if test_result.startswith("Exit code: 0"):
                    return "Implemented the fix and tests pass"
            if action["action"] == "run_tests" and result.startswith("Exit code: 0"):
                return "Implemented the fix and tests pass"
        except Exception as error:
            result = f"ACTION_ERROR: {type(error).__name__}: {error}"
        messages.append({"role": "user", "content": f"Tool result:\n{result}"})

    return "Model-call limit reached; latest tool result was provided to the model"
