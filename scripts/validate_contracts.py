#!/usr/bin/env python3
"""Validate T0 contracts using only the Python standard library.

This deliberately supports the JSON Schema keywords used by this repository;
T1 may add a standards-complete OpenAPI/JSON-Schema validator to CI. Keeping T0
dependency-free makes the frozen examples immediately verifiable.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


class ContractValidationError(ValueError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"cannot load {path.relative_to(ROOT)}: {exc}") from exc


def _pointer(document: Any, fragment: str) -> Any:
    value = document
    if not fragment:
        return value
    if not fragment.startswith("/"):
        raise ContractValidationError(f"unsupported JSON pointer #{fragment}")
    for raw in fragment[1:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def resolve_ref(ref: str, schema_path: Path, root_schema: Any) -> tuple[Any, Path, Any]:
    if ref.startswith("#"):
        return _pointer(root_schema, ref[1:]), schema_path, root_schema
    file_part, _, fragment = ref.partition("#")
    target_path = (schema_path.parent / file_part).resolve()
    if not target_path.is_relative_to(CONTRACTS.resolve()):
        raise ContractValidationError(f"reference escapes contracts directory: {ref}")
    target = load_json(target_path)
    return _pointer(target, fragment), target_path, target


def _matches_type(instance: Any, expected: str) -> bool:
    return {
        "null": instance is None,
        "boolean": isinstance(instance, bool),
        "integer": isinstance(instance, int) and not isinstance(instance, bool),
        "number": isinstance(instance, (int, float)) and not isinstance(instance, bool),
        "string": isinstance(instance, str),
        "array": isinstance(instance, list),
        "object": isinstance(instance, dict),
    }[expected]


def _check_format(value: str, name: str, where: str) -> None:
    if name == "uuid":
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise ContractValidationError(f"{where}: invalid UUID") from exc
    elif name == "date-time":
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContractValidationError(f"{where}: invalid ISO date-time") from exc


def validate(
    instance: Any,
    schema: dict[str, Any],
    schema_path: Path,
    root_schema: dict[str, Any] | None = None,
    where: str = "$",
) -> None:
    root_schema = schema if root_schema is None else root_schema

    if "$ref" in schema:
        target, target_path, target_root = resolve_ref(schema["$ref"], schema_path, root_schema)
        validate(instance, target, target_path, target_root, where)
        return

    for candidate in schema.get("allOf", []):
        validate(instance, candidate, schema_path, root_schema, where)

    if "oneOf" in schema:
        successes = 0
        reasons: list[str] = []
        for candidate in schema["oneOf"]:
            try:
                validate(instance, candidate, schema_path, root_schema, where)
                successes += 1
            except ContractValidationError as exc:
                reasons.append(str(exc))
        if successes != 1:
            raise ContractValidationError(
                f"{where}: expected exactly one oneOf match, got {successes}; "
                + " | ".join(reasons[:3])
            )

    condition = schema.get("if")
    if condition is not None:
        try:
            validate(instance, condition, schema_path, root_schema, where)
        except ContractValidationError:
            branch = schema.get("else")
        else:
            branch = schema.get("then")
        if branch is not None:
            validate(instance, branch, schema_path, root_schema, where)

    if "const" in schema and instance != schema["const"]:
        raise ContractValidationError(f"{where}: expected constant {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise ContractValidationError(f"{where}: {instance!r} is not an allowed value")

    expected_types = schema.get("type")
    if expected_types is not None:
        names = [expected_types] if isinstance(expected_types, str) else expected_types
        if not any(_matches_type(instance, name) for name in names):
            raise ContractValidationError(
                f"{where}: expected type {names}, got {type(instance).__name__}"
            )

    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            raise ContractValidationError(f"{where}: string is too short")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise ContractValidationError(f"{where}: string is too long")
        if "pattern" in schema and re.fullmatch(schema["pattern"], instance) is None:
            raise ContractValidationError(f"{where}: string does not match {schema['pattern']}")
        if "format" in schema:
            _check_format(instance, schema["format"], where)

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if instance < schema.get("minimum", instance):
            raise ContractValidationError(f"{where}: number is below minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            raise ContractValidationError(f"{where}: number is above maximum")

    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            raise ContractValidationError(f"{where}: array has too few items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise ContractValidationError(f"{where}: array has too many items")
        if schema.get("uniqueItems"):
            canonical = [json.dumps(item, sort_keys=True) for item in instance]
            if len(canonical) != len(set(canonical)):
                raise ContractValidationError(f"{where}: array items are not unique")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(instance):
                validate(item, schema["items"], schema_path, root_schema, f"{where}[{index}]")

    if isinstance(instance, dict):
        required = schema.get("required", [])
        missing = [name for name in required if name not in instance]
        if missing:
            raise ContractValidationError(f"{where}: missing required keys {missing}")
        properties = schema.get("properties", {})
        for name, value in instance.items():
            child_where = f"{where}.{name}"
            if name in properties:
                validate(value, properties[name], schema_path, root_schema, child_where)
            elif schema.get("additionalProperties") is False:
                raise ContractValidationError(f"{child_where}: additional property is forbidden")
            elif isinstance(schema.get("additionalProperties"), dict):
                validate(
                    value, schema["additionalProperties"], schema_path, root_schema, child_where
                )


def _walk_refs(value: Any, path: Path, root: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref":
                resolve_ref(child, path, root)
            else:
                _walk_refs(child, path, root)
    elif isinstance(value, list):
        for child in value:
            _walk_refs(child, path, root)


def validate_openapi(path: Path) -> None:
    document = load_json(path)
    if document.get("openapi") != "3.1.0":
        raise ContractValidationError("openapi.json: expected OpenAPI 3.1.0")
    if document.get("info", {}).get("version") != "v1.0.0-draft.1":
        raise ContractValidationError("openapi.json: contract version mismatch")
    required_paths = {
        "/guest-sessions/",
        "/game-definitions/",
        "/solo-matches/",
        "/rooms/",
        "/rooms/{room_id}/join/",
        "/rooms/{room_id}/ready/",
        "/rooms/{room_id}/start/",
        "/matches/{match_id}/guesses/",
        "/matches/{match_id}/snapshot/",
        "/matches/{match_id}/leave/",
        "/matches/{match_id}/rematch/",
    }
    missing = required_paths - set(document.get("paths", {}))
    if missing:
        raise ContractValidationError(f"openapi.json: missing paths {sorted(missing)}")
    operation_ids: list[str] = []
    for path_item in document["paths"].values():
        for method, operation in path_item.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                if "operationId" not in operation or "responses" not in operation:
                    raise ContractValidationError(
                        "openapi.json: operation lacks operationId/responses"
                    )
                operation_ids.append(operation["operationId"])
    if len(operation_ids) != len(set(operation_ids)):
        raise ContractValidationError("openapi.json: duplicate operationId")
    _walk_refs(document, path, document)


def _assert_no_private_keys(value: Any, where: str) -> None:
    forbidden = {"secret", "opponent_guess", "opponent_feedback"}
    if isinstance(value, dict):
        leaked = forbidden & set(value)
        if leaked:
            raise ContractValidationError(f"{where}: forbidden private keys {sorted(leaked)}")
        for key, child in value.items():
            _assert_no_private_keys(child, f"{where}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_private_keys(child, f"{where}[{index}]")


def validate_contracts() -> int:
    manifest_path = CONTRACTS / "manifest.json"
    manifest = load_json(manifest_path)
    if manifest.get("contract_version") != "v1.0.0-draft.1":
        raise ContractValidationError("manifest: unexpected contract version")
    validate_openapi(CONTRACTS / manifest["openapi"])

    count = 0
    for entry in manifest.get("fixtures", []):
        fixture_path = CONTRACTS / entry["path"]
        schema_path = CONTRACTS / entry["schema"]
        fixture = load_json(fixture_path)
        schema = load_json(schema_path)
        validate(fixture, schema, schema_path)
        if "/events/" in entry["path"] or "/snapshots/" in entry["path"]:
            _assert_no_private_keys(fixture, entry["path"])
        count += 1
    return count


def main() -> int:
    try:
        count = validate_contracts()
    except ContractValidationError as exc:
        print(f"Contract validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Contract validation passed: 1 OpenAPI document, {count} canonical fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
