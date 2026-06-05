from __future__ import annotations

import json
import os
import re
import subprocess
import time
import http.client
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


MAX_API_TOOL_CALLS = 24
MAX_TOOL_READ_CHARS = 12000
MAX_TOOL_SEARCH_MATCHES = 20
MAX_TOOL_WINDOW_CHARS = 12000
DEFAULT_TEX_COMMAND = "/opt/homebrew/bin/tectonic"
MAX_COMPILE_OUTPUT_CHARS = 4000
MAX_API_HTTP_RETRIES = 2


@dataclass(frozen=True)
class ApiConfig:
    api_key: str
    base_url: str
    model: str
    timeout: int = 600
    max_tokens: int = 16000


@dataclass(frozen=True)
class AgentResult:
    role: str
    backend: str
    returncode: int
    status: str
    elapsed_sec: float
    files_written: list[str] = field(default_factory=list)
    error: str = ""


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def api_config_from_env(env_path: Path, model: str | None, timeout: int, max_tokens: int) -> ApiConfig:
    env = load_env(env_path)
    key = os.environ.get("OPENAI_API_KEY_GPT") or env.get("OPENAI_API_KEY_GPT")
    base = os.environ.get("OPENAI_BASE_URL_GPT") or env.get("OPENAI_BASE_URL_GPT")
    resolved_model = model or os.environ.get("OPENAI_MODEL_GPT") or env.get("OPENAI_MODEL_GPT") or "gpt-5.5"
    if not key or not base:
        raise RuntimeError(f"Missing OPENAI_API_KEY_GPT or OPENAI_BASE_URL_GPT in {env_path}")
    return ApiConfig(api_key=key, base_url=base.rstrip("/"), model=resolved_model, timeout=timeout, max_tokens=max_tokens)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8")


def stream_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _file_limit(relative_path: str) -> int:
    if relative_path.endswith("context_pack/context.md"):
        return 10000
    if relative_path.endswith("context_pack/context.yaml"):
        return 3000
    if "/prompts/" in relative_path:
        return 4000
    if "/patterns/" in relative_path:
        return 3000
    if "/rubrics/" in relative_path:
        return 3000
    return 2000


def _resolve_allowed(run_dir: Path, allowed_files: list[str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    root = run_dir.resolve()
    for item in allowed_files:
        rel = Path(item)
        if rel.is_absolute() or ".." in rel.parts:
            continue
        path = (run_dir / rel).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            continue
        if path.exists() and path.is_file():
            text = read_text(path)
            limit = _file_limit(item)
            resolved[item] = text[:limit]
    return resolved


def _allowed_file_paths(run_dir: Path, allowed_files: list[str]) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    root = run_dir.resolve()
    for item in allowed_files:
        rel = Path(item)
        if rel.is_absolute() or ".." in rel.parts:
            continue
        path = (run_dir / rel).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            continue
        if path.exists() and path.is_file():
            resolved[item] = path
    return resolved


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _normalize_contract(output_contract: dict[str, Any]) -> dict[str, str]:
    files = output_contract.get("files") if isinstance(output_contract, dict) else None
    if isinstance(files, dict):
        return {str(key): str(value) for key, value in files.items()}
    if isinstance(files, list):
        return {str(item): "text" for item in files}
    return {}


def _safe_write_contract_files(run_dir: Path, files: dict[str, Any], allowed_outputs: dict[str, str]) -> list[str]:
    root = run_dir.resolve()
    written: list[str] = []
    for rel, value in files.items():
        if rel not in allowed_outputs:
            raise ValueError(f"API agent attempted undeclared output: {rel}")
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            raise ValueError(f"Unsafe output path: {rel}")
        path = (run_dir / rel_path).resolve()
        path.relative_to(root)
        if not isinstance(value, str):
            value = yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
        write_text(path, value)
        written.append(rel)
    return written


def _post_chat_completion(config: ApiConfig, payload: dict[str, Any], deadline: float | None = None) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(MAX_API_HTTP_RETRIES + 1):
        request_timeout = config.timeout
        if deadline is not None:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"API agent timed out after {config.timeout} seconds")
            request_timeout = max(1, min(config.timeout, remaining))
        request = urllib.request.Request(
            config.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504, 524} or attempt >= MAX_API_HTTP_RETRIES:
                break
            sleep_for = 1 + attempt
            if deadline is not None:
                sleep_for = min(sleep_for, max(0, deadline - time.time()))
                if sleep_for <= 0:
                    raise TimeoutError(f"API agent timed out after {config.timeout} seconds")
            time.sleep(sleep_for)
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            last_error = exc
            if attempt >= MAX_API_HTTP_RETRIES:
                break
            sleep_for = 1 + attempt
            if deadline is not None:
                sleep_for = min(sleep_for, max(0, deadline - time.time()))
                if sleep_for <= 0:
                    raise TimeoutError(f"API agent timed out after {config.timeout} seconds")
            time.sleep(sleep_for)
    assert last_error is not None
    raise last_error


def _api_tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "list_allowed_files",
                "description": "List relative paths the agent may read.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_allowed_file",
                "description": "Read one allowed file by relative path. Output is size-limited.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file_window",
                "description": "Read a line window from one allowed file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer", "minimum": 1},
                        "line_count": {"type": "integer", "minimum": 1, "maximum": 240},
                    },
                    "required": ["path", "start_line", "line_count"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_allowed_files",
                "description": "Search allowed text files with a regular expression and return matching line snippets.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "path": {"type": "string", "description": "Optional allowed relative path to search in."},
                    },
                    "required": ["pattern"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_output_file",
                "description": "Write a declared output file. Only output_contract paths are writable.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "validate_yaml",
                "description": "Validate that an allowed readable file or declared output file contains parseable YAML.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_gate",
                "description": "Run a small deterministic safety gate. Supported gate_name values: file_exists, yaml_valid.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "gate_name": {"type": "string", "enum": ["file_exists", "yaml_valid"]},
                        "path": {"type": "string"},
                    },
                    "required": ["gate_name", "path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compile_latex",
                "description": "Compile a LaTeX file inside the run directory with the configured tectonic command. No arbitrary shell is allowed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "timeout": {"type": "integer", "minimum": 1, "maximum": 300},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "finish",
                "description": "Finish the role after all required outputs have been written.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["done", "failed"]},
                        "summary": {"type": "string"},
                    },
                    "required": ["status", "summary"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def _json_tool_output(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _declared_output_exists(run_dir: Path, rel: str) -> bool:
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        return False
    try:
        path = (run_dir / rel_path).resolve()
        path.relative_to(run_dir.resolve())
    except ValueError:
        return False
    return path.exists() and path.is_file()


def _contract_outputs_ready(run_dir: Path, outputs: dict[str, str]) -> tuple[bool, str]:
    for rel in outputs:
        if not _declared_output_exists(run_dir, rel):
            return False, f"missing output: {rel}"
        if rel.lower().endswith((".yaml", ".yml")):
            path = (run_dir / Path(rel)).resolve()
            result = _validate_yaml_tool(path)
            if not result.get("ok"):
                return False, f"invalid yaml output {rel}: {result.get('error', 'invalid yaml')}"
    return True, ""


def _parse_tool_args(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if raw == "":
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Tool arguments must be a JSON object")
    return parsed


def _resolve_tool_path(
    run_dir: Path,
    rel: str,
    allowed_paths: dict[str, Path],
    allowed_outputs: dict[str, str],
) -> tuple[Path | None, str | None]:
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        return None, f"unsafe path: {rel}"
    if rel in allowed_paths:
        return allowed_paths[rel], None
    if rel in allowed_outputs:
        path = (run_dir / rel_path).resolve()
        try:
            path.relative_to(run_dir.resolve())
        except ValueError:
            return None, f"unsafe path: {rel}"
        return path, None
    return None, f"path is neither readable nor declared output: {rel}"


def _validate_yaml_tool(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"ok": False, "error": "file does not exist"}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        return {"ok": True, "parsed_type": type(data).__name__}
    except yaml.YAMLError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _compile_latex_tool(run_dir: Path, path: Path, timeout: int) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"ok": False, "compiled": False, "error": "file does not exist"}
    if path.suffix.lower() != ".tex":
        return {"ok": False, "compiled": False, "error": "compile_latex only accepts .tex files"}
    timeout = max(1, min(300, int(timeout)))
    command = [DEFAULT_TEX_COMMAND, str(path.name)]
    try:
        completed = subprocess.run(
            command,
            cwd=path.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return {
            "ok": completed.returncode == 0,
            "compiled": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "")[-MAX_COMPILE_OUTPUT_CHARS:],
            "stderr": (completed.stderr or "")[-MAX_COMPILE_OUTPUT_CHARS:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "compiled": False,
            "returncode": 124,
            "stdout": stream_text(exc.stdout)[-MAX_COMPILE_OUTPUT_CHARS:],
            "stderr": stream_text(exc.stderr)[-MAX_COMPILE_OUTPUT_CHARS:] + f"\nTimed out after {timeout} seconds.",
        }


def _execute_api_tool(
    name: str,
    args: dict[str, Any],
    run_dir: Path,
    allowed_paths: dict[str, Path],
    allowed_outputs: dict[str, str],
    files_written: list[str],
) -> dict[str, Any]:
    if name == "list_allowed_files":
        return {"ok": True, "allowed_files": sorted(allowed_paths)}
    if name == "read_allowed_file":
        rel = str(args.get("path", ""))
        path = allowed_paths.get(rel)
        if path is None:
            return {"ok": False, "error": f"not an allowed readable file: {rel}"}
        text = read_text(path)
        limit = min(_file_limit(rel), MAX_TOOL_READ_CHARS)
        return {"ok": True, "path": rel, "content": text[:limit], "truncated": len(text) > limit}
    if name == "read_file_window":
        rel = str(args.get("path", ""))
        path = allowed_paths.get(rel)
        if path is None:
            return {"ok": False, "error": f"not an allowed readable file: {rel}"}
        start_line = max(1, int(args.get("start_line", 1)))
        line_count = max(1, min(240, int(args.get("line_count", 80))))
        lines = read_text(path).splitlines()
        selected = "\n".join(lines[start_line - 1 : start_line - 1 + line_count])
        truncated = len(selected) > MAX_TOOL_WINDOW_CHARS
        return {
            "ok": True,
            "path": rel,
            "start_line": start_line,
            "line_count": line_count,
            "content": selected[:MAX_TOOL_WINDOW_CHARS],
            "truncated": truncated,
        }
    if name == "search_allowed_files":
        pattern = str(args.get("pattern", ""))
        rel_filter = args.get("path")
        if not pattern:
            return {"ok": False, "error": "pattern is required"}
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            return {"ok": False, "error": f"invalid regex: {exc}"}
        matches: list[dict[str, Any]] = []
        search_items = allowed_paths.items()
        if rel_filter:
            rel = str(rel_filter)
            path = allowed_paths.get(rel)
            search_items = [(rel, path)] if path is not None else []
        for rel, path in search_items:
            for index, line in enumerate(read_text(path).splitlines(), start=1):
                if regex.search(line):
                    matches.append({"path": rel, "line": index, "text": line[:500]})
                    if len(matches) >= MAX_TOOL_SEARCH_MATCHES:
                        return {"ok": True, "matches": matches, "truncated": True}
        return {"ok": True, "matches": matches, "truncated": False}
    if name == "write_output_file":
        rel = str(args.get("path", ""))
        content = args.get("content", "")
        if not isinstance(content, str):
            content = yaml.safe_dump(content, sort_keys=False, allow_unicode=True)
        written = _safe_write_contract_files(run_dir, {rel: content}, allowed_outputs)
        files_written.extend(item for item in written if item not in files_written)
        return {"ok": True, "written": written}
    if name == "validate_yaml":
        rel = str(args.get("path", ""))
        path, error = _resolve_tool_path(run_dir, rel, allowed_paths, allowed_outputs)
        if error or path is None:
            return {"ok": False, "error": error}
        return _validate_yaml_tool(path)
    if name == "run_gate":
        gate_name = str(args.get("gate_name", ""))
        rel = str(args.get("path", ""))
        path, error = _resolve_tool_path(run_dir, rel, allowed_paths, allowed_outputs)
        if error or path is None:
            return {"ok": False, "gate": gate_name, "status": "failed", "error": error}
        if gate_name == "file_exists":
            ok = path.exists() and path.is_file()
            return {"ok": ok, "gate": gate_name, "status": "passed" if ok else "failed", "path": rel}
        if gate_name == "yaml_valid":
            result = _validate_yaml_tool(path)
            return {
                "ok": bool(result.get("ok")),
                "gate": gate_name,
                "status": "passed" if result.get("ok") else "failed",
                **result,
            }
        return {"ok": False, "gate": gate_name, "status": "failed", "error": f"unsupported gate: {gate_name}"}
    if name == "compile_latex":
        rel = str(args.get("path", ""))
        path, error = _resolve_tool_path(run_dir, rel, allowed_paths, allowed_outputs)
        if error or path is None:
            return {"ok": False, "compiled": False, "error": error}
        timeout = int(args.get("timeout", 120))
        return _compile_latex_tool(run_dir, path, timeout)
    if name == "finish":
        status = str(args.get("status", "done"))
        return {"ok": status == "done", "status": status, "summary": str(args.get("summary", ""))}
    return {"ok": False, "error": f"unknown tool: {name}"}


def codex_command(run_dir: Path, prompt: str, codex_binary: str = "codex", ignore_user_config: bool = False) -> list[str]:
    command = [
        codex_binary,
        "-a",
        "never",
        "exec",
        "--ephemeral",
        "--sandbox",
        "workspace-write",
        "-C",
        str(run_dir.resolve()),
        prompt,
    ]
    if ignore_user_config:
        command.insert(command.index("--sandbox"), "--ignore-user-config")
    return command


def run_codex_agent(
    role: str,
    run_dir: Path,
    prompt: str,
    timeout: int,
    codex_binary: str = "codex",
    ignore_user_config: bool = False,
) -> AgentResult:
    start = time.time()
    logs = run_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    command = codex_command(run_dir, prompt, codex_binary=codex_binary, ignore_user_config=ignore_user_config)
    write_yaml(logs / f"codex_command_{role}.yaml", {"command": command[:-1] + ["<prompt omitted>"]})
    try:
        completed = subprocess.run(command, cwd=run_dir, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        write_text(logs / f"{role}.stdout.log", completed.stdout or "")
        write_text(logs / f"{role}.stderr.log", completed.stderr or "")
        return AgentResult(
            role=role,
            backend="codex",
            returncode=completed.returncode,
            status="done" if completed.returncode == 0 else "failed",
            elapsed_sec=round(time.time() - start, 3),
        )
    except subprocess.TimeoutExpired as exc:
        write_text(logs / f"{role}.stdout.log", stream_text(exc.stdout))
        write_text(logs / f"{role}.stderr.log", stream_text(exc.stderr) + f"\nTimed out after {timeout} seconds.\n")
        return AgentResult(role=role, backend="codex", returncode=124, status="timeout", elapsed_sec=round(time.time() - start, 3), error="timeout")


def run_api_agent(
    role: str,
    run_dir: Path,
    prompt: str,
    allowed_files: list[str],
    output_contract: dict[str, Any],
    config: ApiConfig,
) -> AgentResult:
    start = time.time()
    logs = run_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    allowed_paths = _allowed_file_paths(run_dir, allowed_files)
    outputs = _normalize_contract(output_contract)
    system_prompt = f"""You are an API-backed scientific writing agent running role `{role}`.

Use the provided tools to inspect allowed files and write declared outputs.
Do not rely on memory for paper-specific facts. Read the relevant files before writing.
You may only read files returned by `list_allowed_files`.
You may only write files listed in OUTPUT_CONTRACT_JSON.
Call `finish` after all required outputs are written.
Before calling `finish`, call `validate_yaml` or `run_gate` with
`gate_name: yaml_valid` for every declared output path ending in `.yaml`.

For any output path ending in `.yaml`, make the file content valid JSON-compatible
YAML. Prefer JSON objects/lists as the file content when unsure. Do not use
unquoted plain scalar values containing colons, because downstream gates parse
these files with a strict YAML parser.

Keep outputs compact and contract-focused. For planning files, prefer 5-8
high-value anchors/items per required field, short phrases over paragraphs, and
avoid long explanatory prose unless the task explicitly requires it.

TASK_PROMPT:
{prompt}

OUTPUT_CONTRACT_JSON:
{json.dumps(outputs, ensure_ascii=False)}
"""
    write_text(logs / f"{role}.api_prompt.txt", system_prompt)
    messages: list[dict[str, Any]] = [{"role": "user", "content": system_prompt}]
    tools = _api_tool_schemas()
    files_written: list[str] = []
    yaml_outputs = {rel for rel in outputs if rel.lower().endswith((".yaml", ".yml"))}
    validated_yaml_outputs: set[str] = set()
    raw_messages: list[dict[str, Any]] = []
    deadline = start + config.timeout
    try:
        for step in range(MAX_API_TOOL_CALLS):
            if time.time() >= deadline:
                raise TimeoutError(f"API agent timed out after {config.timeout} seconds")
            payload = {
                "model": config.model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0,
                "max_tokens": config.max_tokens,
            }
            data = _post_chat_completion(config, payload, deadline=deadline)
            message = data["choices"][0]["message"]
            raw_messages.append(message)
            tool_calls = message.get("tool_calls") or []
            content = str(message.get("content") or "")
            if tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": message.get("content"),
                        "tool_calls": tool_calls,
                    }
                )
                finish_status: str | None = None
                for call in tool_calls:
                    function = call.get("function") or {}
                    name = str(function.get("name") or "")
                    args = _parse_tool_args(function.get("arguments"))
                    tool_result = _execute_api_tool(name, args, run_dir, allowed_paths, outputs, files_written)
                    rel = str(args.get("path", ""))
                    if name == "validate_yaml" and tool_result.get("ok") and rel in yaml_outputs:
                        validated_yaml_outputs.add(rel)
                    if name == "run_gate" and args.get("gate_name") == "yaml_valid" and tool_result.get("ok") and rel in yaml_outputs:
                        validated_yaml_outputs.add(rel)
                    if name == "finish":
                        missing_outputs = [
                            rel for rel in outputs if rel not in files_written and not _declared_output_exists(run_dir, rel)
                        ]
                        missing_validation = [
                            rel for rel in yaml_outputs if rel not in validated_yaml_outputs and _declared_output_exists(run_dir, rel)
                        ]
                        if missing_outputs:
                            tool_result = {
                                "ok": False,
                                "status": "needs_outputs",
                                "missing_outputs": missing_outputs,
                                "message": "Write all declared output files before finish.",
                            }
                        elif missing_validation:
                            tool_result = {
                                "ok": False,
                                "status": "needs_validation",
                                "missing_yaml_validation": missing_validation,
                                "message": "Call validate_yaml or run_gate yaml_valid on YAML outputs before finish.",
                            }
                        else:
                            finish_status = str(tool_result.get("status") or "done")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id"),
                            "name": name,
                            "content": _json_tool_output(tool_result),
                        }
                    )
                if finish_status is not None:
                    write_text(logs / f"{role}.api_raw.txt", json.dumps(raw_messages, ensure_ascii=False, indent=2))
                    status = "done" if finish_status == "done" else "failed"
                    return AgentResult(
                        role=role,
                        backend="api",
                        returncode=0 if status == "done" else 1,
                        status=status,
                        elapsed_sec=round(time.time() - start, 3),
                        files_written=files_written,
                    )
                continue

            write_text(logs / f"{role}.api_raw.txt", json.dumps(raw_messages, ensure_ascii=False, indent=2))
            if content:
                parsed = _extract_json(content)
                files = parsed.get("files")
                if not isinstance(files, dict):
                    raise ValueError("API response must contain object field `files`")
                files_written = _safe_write_contract_files(run_dir, files, outputs)
                missing_outputs = [
                    rel for rel in outputs if rel not in files_written and not _declared_output_exists(run_dir, rel)
                ]
                if missing_outputs:
                    raise ValueError(f"API response did not write declared outputs: {', '.join(missing_outputs)}")
                invalid_yaml_outputs: list[str] = []
                for rel in yaml_outputs:
                    path, error = _resolve_tool_path(run_dir, rel, allowed_paths, outputs)
                    result = {"ok": False, "error": error} if error or path is None else _validate_yaml_tool(path)
                    if not result.get("ok"):
                        invalid_yaml_outputs.append(f"{rel}: {result.get('error', 'invalid yaml')}")
                if invalid_yaml_outputs:
                    raise ValueError("API response wrote invalid YAML output(s): " + "; ".join(invalid_yaml_outputs))
                return AgentResult(
                    role=role,
                    backend="api",
                    returncode=0,
                    status="done",
                    elapsed_sec=round(time.time() - start, 3),
                    files_written=files_written,
                )
            raise ValueError("API response contained neither tool_calls nor content")
        raise TimeoutError(f"Exceeded max API tool calls: {MAX_API_TOOL_CALLS}")
    except Exception as exc:
        write_text(logs / f"{role}.api_raw.txt", json.dumps(raw_messages, ensure_ascii=False, indent=2))
        write_text(logs / f"{role}.api_error.txt", f"{type(exc).__name__}: {exc}\n")
        ready, ready_error = _contract_outputs_ready(run_dir, outputs)
        if ready:
            return AgentResult(
                role=role,
                backend="api",
                returncode=0,
                status="done",
                elapsed_sec=round(time.time() - start, 3),
                files_written=[rel for rel in outputs if _declared_output_exists(run_dir, rel)],
                error=f"recovered_after_output_write: {type(exc).__name__}: {exc}",
            )
        if ready_error:
            write_text(logs / f"{role}.api_error.txt", f"{type(exc).__name__}: {exc}\n{ready_error}\n")
        return AgentResult(role=role, backend="api", returncode=1, status="failed", elapsed_sec=round(time.time() - start, 3), error=f"{type(exc).__name__}: {exc}")


def run_agent(
    role: str,
    run_dir: Path,
    prompt: str,
    allowed_files: list[str],
    output_contract: dict[str, Any],
    backend: str,
    timeout: int,
    codex_binary: str = "codex",
    ignore_user_config: bool = False,
    api_config: ApiConfig | None = None,
) -> AgentResult:
    if backend == "codex":
        return run_codex_agent(role, run_dir, prompt, timeout, codex_binary=codex_binary, ignore_user_config=ignore_user_config)
    if backend == "api":
        if api_config is None:
            raise RuntimeError("api_config is required for API agent backend")
        return run_api_agent(role, run_dir, prompt, allowed_files, output_contract, api_config)
    raise ValueError(f"Unsupported agent backend: {backend}")
