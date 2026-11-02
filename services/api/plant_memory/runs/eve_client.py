"""Thin HTTP client for the eve agent runtime (apps/agent).

Endpoints (eve HTTP API):
  POST /eve/v1/session                 {message, outputSchema?, operationId?}      -> {sessionId, turnId}
  POST /eve/v1/session/:id             {message | answers, idempotencyKey?}         -> {turnId}
  POST /eve/v1/session/:id/cancel      {turnId}
  GET  /eve/v1/session/:id/stream?cursor=N   NDJSON event stream

The API authenticates with a short-lived run-scoped JWT (HS256) that the agent channel verifies.
"""

from __future__ import annotations

import json
from typing import Iterator

import httpx

from ..config import get_settings


class EveError(RuntimeError):
    pass


class EveClient:
    def __init__(self, token: str, base_url: str | None = None, timeout: float = 30.0):
        s = get_settings()
        self.base = (base_url or s.agent_base_url).rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self.timeout = timeout

    def _post(self, path: str, body: dict) -> dict:
        try:
            r = httpx.post(f"{self.base}{path}", json=body, headers=self.headers, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise EveError(f"agent runtime unreachable: {exc}") from exc
        if r.status_code >= 400:
            raise EveError(f"agent runtime {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else {}

    def create_session(self, message: str, *, output_schema: dict | None = None, operation_id: str | None = None) -> dict:
        body: dict = {"message": message}
        if output_schema:
            body["outputSchema"] = output_schema
        if operation_id:
            body["operationId"] = operation_id
        return self._post("/eve/v1/session", body)

    def send_message(self, session_id: str, message: str, *, idempotency_key: str | None = None) -> dict:
        body: dict = {"message": message}
        if idempotency_key:
            body["idempotencyKey"] = idempotency_key
        return self._post(f"/eve/v1/session/{session_id}", body)

    def send_answers(self, session_id: str, answers: dict, *, idempotency_key: str | None = None) -> dict:
        body: dict = {"answers": answers}
        if idempotency_key:
            body["idempotencyKey"] = idempotency_key
        return self._post(f"/eve/v1/session/{session_id}", body)

    def cancel(self, session_id: str, turn_id: str | None = None) -> dict:
        return self._post(f"/eve/v1/session/{session_id}/cancel", {"turnId": turn_id} if turn_id else {})

    def stream(self, session_id: str, cursor: int = 0, read_timeout: float = 120.0) -> Iterator[tuple[int, dict]]:
        """Yields (cursor, event). Cursor is the count of NDJSON lines consumed, used for resumption."""
        url = f"{self.base}/eve/v1/session/{session_id}/stream"
        try:
            with httpx.stream("GET", url, params={"cursor": cursor}, headers=self.headers, timeout=httpx.Timeout(self.timeout, read=read_timeout)) as r:
                if r.status_code >= 400:
                    raise EveError(f"stream {r.status_code}")
                for line in r.iter_lines():
                    if not line.strip():
                        continue
                    cursor += 1
                    try:
                        yield cursor, json.loads(line)
                    except json.JSONDecodeError:
                        yield cursor, {"type": "unparseable", "raw": line[:500]}
        except httpx.HTTPError as exc:
            raise EveError(f"stream interrupted: {exc}") from exc
