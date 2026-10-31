"""actions.json(OpenAPI 3.1) → 실행 가능한 Operation 레지스트리.

- path key 에 쿼리가 붙어 있는 경우('/api/products?item=')는 path='/api/products', query='item' 으로 분리한다.
- 요청 본문은 원문 스키마(additionalProperties:false 포함)로 사전 검증한다.
- 41개(GET 23 + 업무 POST 17 + reset 1)가 아니면 import 시점에 실패한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import jsonschema

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ACTIONS_JSON = os.path.join(DATA_DIR, "actions.json")
ACTIONS_SHA256 = "20082b8f76e41f5d6f8e2a66be927f80e12540883e36198587ff93f64278911e"
RESET_OP_ID = "resetMyActionData"
TC_HEADER = "X-Aitop100-Test-Case-Id"
TC_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


class RequestValidationError(ValueError):
    pass


@dataclass
class Operation:
    op_id: str
    method: str
    raw_path: str
    path: str
    path_params: list[str]
    query_param: str | None
    body_schema: dict | None
    response_schema: dict | None
    summary: str
    description: str
    tag: str
    example_params: dict[str, Any] = field(default_factory=dict)

    @property
    def is_reset(self) -> bool:
        return self.op_id == RESET_OP_ID

    @property
    def is_post(self) -> bool:
        return self.method == "POST"

    @property
    def tool_name(self) -> str:
        # API-07 → API_07 (OpenAI function name 규칙: ^[a-zA-Z0-9_-]+$)
        return self.op_id.replace("-", "_")

    def build(self, params: dict[str, Any] | None, body: dict | None) -> tuple[str, dict[str, str], dict | None]:
        """(url_path, query, body) 를 만들고 원문 스키마로 검증한다."""
        params = dict(params or {})
        path = self.path
        for p in self.path_params:
            v = params.pop(p, None)
            if v is None or str(v).strip() == "":
                raise RequestValidationError(f"{self.op_id}: 경로 파라미터 '{p}' 누락")
            path = path.replace("{" + p + "}", quote(str(v).strip(), safe=""))
        query: dict[str, str] = {}
        if self.query_param:
            v = params.pop(self.query_param, None)
            if v is None or str(v).strip() == "":
                raise RequestValidationError(f"{self.op_id}: 검색 파라미터 '{self.query_param}' 누락")
            query[self.query_param] = str(v).strip()
        if params:
            raise RequestValidationError(f"{self.op_id}: 지원하지 않는 파라미터 {sorted(params)}")
        if self.method == "GET":
            if body:
                raise RequestValidationError(f"{self.op_id}: 조회에는 본문을 보내지 않는다")
            return path, query, None
        if self.is_reset:
            return path, query, None
        body = {} if body is None else body
        if not isinstance(body, dict):
            raise RequestValidationError(f"{self.op_id}: 본문은 객체여야 한다")
        try:
            jsonschema.validate(body, self.body_schema or {"type": "object", "additionalProperties": False})
        except jsonschema.ValidationError as e:
            raise RequestValidationError(f"{self.op_id}: 본문 스키마 위반 — {e.message}") from None
        return path, query, body


def _resolve(schema: Any, components: dict) -> Any:
    if isinstance(schema, dict):
        if "$ref" in schema:
            name = schema["$ref"].split("/")[-1]
            return _resolve(components[name], components)
        return {k: _resolve(v, components) for k, v in schema.items()}
    if isinstance(schema, list):
        return [_resolve(x, components) for x in schema]
    return schema


def file_sha256(path: str = ACTIONS_JSON) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_operations(path: str = ACTIONS_JSON) -> dict[str, Operation]:
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    comps = spec["components"]["schemas"]
    ops: dict[str, Operation] = {}
    for raw_path, methods in spec["paths"].items():
        base, _, q = raw_path.partition("?")
        query_param = q.rstrip("=") or None
        path_params = re.findall(r"{(\w+)}", base)
        for method, op in methods.items():
            body_schema = None
            rb = op.get("requestBody")
            if rb:
                body_schema = _resolve(rb["content"]["application/json"]["schema"], comps)
            resp = None
            for code in ("200", "204"):
                r = op.get("responses", {}).get(code, {})
                c = r.get("content", {}).get("application/json")
                if c:
                    resp = _resolve(c["schema"], comps)
                    break
            examples = {}
            for prm in op.get("parameters", []):
                if prm.get("in") in ("path", "query"):
                    ex = prm.get("example", (prm.get("schema") or {}).get("example"))
                    if ex is not None:
                        examples[prm["name"]] = ex
            o = Operation(
                op_id=op["operationId"], method=method.upper(), raw_path=raw_path, path=base,
                path_params=path_params, query_param=query_param, body_schema=body_schema,
                response_schema=resp, summary=op.get("summary", ""), description=op.get("description") or "",
                tag=(op.get("tags") or [""])[0], example_params=examples)
            if o.op_id in ops:
                raise RuntimeError(f"operationId 중복: {o.op_id}")
            ops[o.op_id] = o
    gets = [o for o in ops.values() if o.method == "GET"]
    posts = [o for o in ops.values() if o.method == "POST" and not o.is_reset]
    resets = [o for o in ops.values() if o.is_reset]
    if (len(gets), len(posts), len(resets)) != (23, 17, 1):
        raise RuntimeError(f"Operation 계수 불일치: GET {len(gets)} / POST {len(posts)} / reset {len(resets)}")
    expected = {f"API-{i:02d}" for i in range(1, 41)}
    missing = expected - set(ops)
    if missing:
        raise RuntimeError(f"누락된 operation: {sorted(missing)}")
    return ops


OPERATIONS: dict[str, Operation] = load_operations()
BUSINESS_OPERATIONS: dict[str, Operation] = {k: v for k, v in OPERATIONS.items() if not v.is_reset}
BY_TOOL_NAME: dict[str, Operation] = {v.tool_name: v for v in BUSINESS_OPERATIONS.values()}


def receipt_id(op: Operation, result: dict | None) -> str | None:
    """POST 응답에서 접수번호 필드를 꺼낸다(필드명은 응답 스키마에 따라 다름)."""
    if not isinstance(result, dict):
        return None
    for k in ("request_id", "refund_id", "memo_id", "escalation_id"):
        if result.get(k):
            return str(result[k])
    return None
