from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import AgentDocsError
from .paths import config_path, validate_alias, validate_branch_name, validate_doc_path, validate_repo_url


VALID_MODES = {"readOnly", "pr"}
VALID_PROVIDERS = {"github"}


@dataclass(frozen=True)
class DocConfig:
    alias: str
    repo: str
    branch: str = "main"
    provider: str = "github"
    mode: str = "readOnly"
    path: str = ""


@dataclass(frozen=True)
class AgentDocsConfig:
    version: int
    docs: dict[str, DocConfig]


def empty_config() -> AgentDocsConfig:
    return AgentDocsConfig(version=1, docs={})


def load_config(project_root: Path, *, required: bool = True) -> AgentDocsConfig:
    path = config_path(project_root)
    if not path.exists():
        if required:
            raise AgentDocsError("Missing .agent-docs.yml. Run 'agent-docs init' first.")
        return empty_config()
    data = _load_yaml(path)
    return parse_config(data, project_root)


def save_config(project_root: Path, config: AgentDocsConfig) -> None:
    config_path(project_root).write_text(_dump_config(config), encoding="utf-8")


def parse_config(data: Any, project_root: Path) -> AgentDocsConfig:
    if not isinstance(data, dict):
        raise AgentDocsError(".agent-docs.yml must contain a YAML object.")
    version = data.get("version")
    if version != 1:
        raise AgentDocsError(".agent-docs.yml must set version: 1.")
    raw_docs = data.get("docs", {})
    if raw_docs is None:
        raw_docs = {}
    if not isinstance(raw_docs, dict):
        raise AgentDocsError(".agent-docs.yml docs must be a mapping.")

    docs: dict[str, DocConfig] = {}
    for alias, raw_doc in raw_docs.items():
        if not isinstance(alias, str) or not isinstance(raw_doc, dict):
            raise AgentDocsError("Each docs entry must be a mapping keyed by alias.")
        validate_alias(alias)
        repo = _required_str(raw_doc, "repo", alias)
        branch = _optional_str(raw_doc, "branch", "main")
        provider = _optional_str(raw_doc, "provider", "github")
        mode = _optional_str(raw_doc, "mode", "readOnly")
        raw_path = _optional_str(raw_doc, "path", f".agent-docs/{alias}")
        validate_repo_url(repo)
        validate_branch_name(branch)
        if provider not in VALID_PROVIDERS:
            raise AgentDocsError(f"Unsupported provider for {alias}: {provider}.")
        if mode not in VALID_MODES:
            raise AgentDocsError(f"Unsupported mode for {alias}: {mode}.")
        validate_doc_path(project_root, raw_path, alias)
        docs[alias] = DocConfig(
            alias=alias,
            repo=repo,
            branch=branch,
            provider=provider,
            mode=mode,
            path=raw_path,
        )
    return AgentDocsConfig(version=1, docs=docs)


def add_doc(config: AgentDocsConfig, doc: DocConfig, project_root: Path) -> AgentDocsConfig:
    validate_alias(doc.alias)
    validate_repo_url(doc.repo)
    validate_branch_name(doc.branch)
    if doc.provider not in VALID_PROVIDERS:
        raise AgentDocsError(f"Unsupported provider: {doc.provider}.")
    if doc.mode not in VALID_MODES:
        raise AgentDocsError(f"Unsupported mode: {doc.mode}.")
    validate_doc_path(project_root, doc.path or f".agent-docs/{doc.alias}", doc.alias)
    docs = dict(config.docs)
    docs[doc.alias] = DocConfig(
        alias=doc.alias,
        repo=doc.repo,
        branch=doc.branch,
        provider=doc.provider,
        mode=doc.mode,
        path=doc.path or f".agent-docs/{doc.alias}",
    )
    return AgentDocsConfig(version=1, docs=docs)


def remove_doc(config: AgentDocsConfig, alias: str) -> AgentDocsConfig:
    if alias not in config.docs:
        raise AgentDocsError(f"Unknown docs alias: {alias}.")
    docs = dict(config.docs)
    del docs[alias]
    return AgentDocsConfig(version=1, docs=docs)


def _required_str(raw_doc: dict[str, Any], key: str, alias: str) -> str:
    value = raw_doc.get(key)
    if not isinstance(value, str) or not value:
        raise AgentDocsError(f"Docs entry {alias} must set {key}.")
    return value


def _optional_str(raw_doc: dict[str, Any], key: str, default: str) -> str:
    value = raw_doc.get(key, default)
    if not isinstance(value, str) or not value:
        raise AgentDocsError(f"Docs field {key} must be a non-empty string.")
    return value


def _load_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-not-found]

        return yaml.safe_load(text)
    except ModuleNotFoundError:
        return _load_v1_yaml(text)


def _load_v1_yaml(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    docs: dict[str, Any] = {}
    result["docs"] = docs
    current_alias: str | None = None
    in_docs = False

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.strip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if indent == 0:
            key, value = _split_yaml_pair(line)
            if key == "version":
                result["version"] = int(value)
            elif key == "docs":
                in_docs = True
            else:
                result[key] = value
        elif in_docs and indent == 2:
            key, value = _split_yaml_pair(line)
            if value:
                raise AgentDocsError("Invalid docs YAML: alias entries must be mappings.")
            current_alias = key
            docs[current_alias] = {}
        elif in_docs and indent == 4 and current_alias:
            key, value = _split_yaml_pair(line)
            docs[current_alias][key] = value
        else:
            raise AgentDocsError("Unsupported .agent-docs.yml format.")
    return result


def _split_yaml_pair(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise AgentDocsError("Unsupported .agent-docs.yml format.")
    key, value = line.split(":", 1)
    return key.strip(), _unquote(value.strip())


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _dump_config(config: AgentDocsConfig) -> str:
    lines = ["version: 1", "docs:"]
    for alias in sorted(config.docs):
        doc = config.docs[alias]
        lines.extend(
            [
                f"  {alias}:",
                f"    repo: {_quote(doc.repo)}",
                f"    branch: {_quote(doc.branch)}",
                f"    provider: {_quote(doc.provider)}",
                f"    mode: {_quote(doc.mode)}",
                f"    path: {_quote(doc.path or f'.agent-docs/{alias}')}",
            ]
        )
    return "\n".join(lines) + "\n"


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
