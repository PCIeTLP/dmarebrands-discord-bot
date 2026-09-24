from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import quote

import aiohttp

TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3
IN_PROGRESS_WAIT_SECONDS = 60

FRIENDLY = {
    "unauthorized": "The bot's API key was rejected. It may have been revoked.",
    "insufficient_balance": "Not enough balance on the partner account.",
    "forbidden": "That partner account is no longer active.",
    "not_found": "Nothing matched that.",
    "conflict": "That is not possible in the current state.",
    "in_progress": "That purchase is still going through. Check /keys list in a minute before buying again.",
    "invalid_request": "One of the values was out of range.",
    "rate_limited": "The API is rate limiting us. Try again in a moment.",
    "server_error": "The API had a problem. Try again shortly.",
}


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        request_id: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id
        self.retry_after = retry_after


def _part(value: Any) -> str:
    return quote(str(value), safe="")


def friendly(err: BaseException) -> str:
    if isinstance(err, ApiError):
        if err.code == "in_progress":
            return FRIENDLY["in_progress"]
        return err.message or FRIENDLY.get(err.code, "The request failed.")
    if isinstance(err, asyncio.TimeoutError):
        return "The API did not respond in time. Try again."
    return "Could not reach the API. Try again shortly."


class PartnerApi:
    def __init__(self, api_key: str, api_base: str) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self._session: aiohttp.ClientSession | None = None
        self.remaining: int | None = None
        self.reset_in: int | None = None

    async def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS),
                headers={
                    "authorization": f"Bearer {self.api_key}",
                    "accept": "application/json",
                    "user-agent": "dmarebrands-discord-bot/1.0 (+python)",
                },
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        idempotent: bool = False,
    ) -> dict[str, Any]:
        params = {}
        for key, value in (query or {}).items():
            if value is None or value == "":
                continue
            params[key] = str(value)

        session = await self.session()
        url = f"{self.api_base}{path}"
        last_error: BaseException | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                async with session.request(method, url, params=params, json=body) as res:
                    remaining = res.headers.get("x-ratelimit-remaining")
                    if remaining is not None:
                        self.remaining = int(remaining)
                    reset = res.headers.get("x-ratelimit-reset")
                    if reset is not None:
                        self.reset_in = int(reset)

                    request_id = res.headers.get("x-request-id")
                    text = await res.text()

                    payload: dict[str, Any] | None = None
                    if text:
                        try:
                            import json

                            parsed = json.loads(text)
                            payload = parsed if isinstance(parsed, dict) else None
                        except ValueError:
                            payload = None

                    if res.status < 400:
                        return payload or {}

                    error = (payload or {}).get("error") or {}
                    code = error.get("code", "server_error")
                    message = error.get("message", f"HTTP {res.status}")

                    if res.status == 429 and attempt < MAX_ATTEMPTS:
                        retry_after = int(res.headers.get("retry-after", "2") or 2)
                        await asyncio.sleep(min(max(retry_after, 1), 30))
                        continue

                    if res.status >= 500 and attempt < MAX_ATTEMPTS and (method == "GET" or idempotent):
                        await asyncio.sleep(attempt * 0.5)
                        continue

                    wait_hint = res.headers.get("retry-after") or ""
                    raise ApiError(
                        res.status, code, message, request_id, float(wait_hint) if wait_hint.isdigit() else None
                    )

            except ApiError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_error = err
                if (method != "GET" and not idempotent) or attempt >= MAX_ATTEMPTS:
                    raise
                await asyncio.sleep(attempt * 0.5)

        if last_error:
            raise last_error
        raise RuntimeError("Request failed")

    async def me(self) -> dict[str, Any]:
        return await self.request("GET", "/me")

    async def plans(self) -> dict[str, Any]:
        return await self.request("GET", "/plans")

    async def balance(self) -> dict[str, Any]:
        return await self.request("GET", "/balance")

    async def ledger(self, limit: int | None = None) -> dict[str, Any]:
        return await self.request("GET", "/ledger", query={"limit": limit})

    async def stats(self) -> dict[str, Any]:
        return await self.request("GET", "/stats")

    async def list_keys(
        self,
        *,
        filter: str | None = None,
        search: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return await self.request("GET", "/keys", query={"filter": filter, "search": search, "limit": limit})

    async def buy_keys(self, plan: str, count: int, reference: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"plan": plan, "count": count}
        if reference:
            body["reference"] = reference
        give_up_at = time.monotonic() + IN_PROGRESS_WAIT_SECONDS
        while True:
            try:
                return await self.request("POST", "/keys", body=body, idempotent=bool(reference))
            except ApiError as err:
                if err.code != "in_progress" or time.monotonic() >= give_up_at:
                    raise
                await asyncio.sleep(min(max(err.retry_after or 2, 1), 10))

    async def get_key(self, code: str) -> dict[str, Any]:
        return await self.request("GET", f"/keys/{_part(code)}")

    async def refund_key(self, code: str) -> dict[str, Any]:
        return await self.request("DELETE", f"/keys/{_part(code)}")

    async def reset_by_key(self, code: str) -> dict[str, Any]:
        return await self.request("POST", f"/keys/{_part(code)}/reset-hwid")

    async def list_customers(self, *, search: str | None = None, limit: int | None = None) -> dict[str, Any]:
        return await self.request("GET", "/customers", query={"search": search, "limit": limit})

    async def get_customer(self, ref: int | str) -> dict[str, Any]:
        return await self.request("GET", f"/customers/{_part(ref)}")

    async def reset_by_customer(self, ref: int | str) -> dict[str, Any]:
        return await self.request("POST", f"/customers/{_part(ref)}/reset-hwid")

    async def domains(self) -> dict[str, Any]:
        return await self.request("GET", "/domains")

    async def status(self, product: str | None = None) -> dict[str, Any]:
        return await self.request("GET", "/status", query={"product": product})

    async def updates(self, product: str | None = None) -> dict[str, Any]:
        return await self.request("GET", "/updates", query={"product": product})

    async def brand(self) -> dict[str, Any]:
        return await self.request("GET", "/brand")

    async def update_brand(self, patch: dict[str, Any]) -> dict[str, Any]:
        return await self.request("PATCH", "/brand", body=patch)

    async def list_tickets(
        self,
        *,
        status: str | None = None,
        search: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return await self.request(
            "GET", "/tickets", query={"status": status, "search": search, "limit": limit}
        )

    async def create_ticket(
        self,
        *,
        subject: str,
        body: str,
        category: str | None = None,
        priority: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"subject": subject, "body": body}
        if category:
            payload["category"] = category
        if priority:
            payload["priority"] = priority
        return await self.request("POST", "/tickets", body=payload)

    async def get_ticket(self, ref: str) -> dict[str, Any]:
        return await self.request("GET", f"/tickets/{_part(ref)}")

    async def reply_ticket(self, ref: str, body: str) -> dict[str, Any]:
        return await self.request("POST", f"/tickets/{_part(ref)}/reply", body={"body": body})

    async def close_ticket(self, ref: str) -> dict[str, Any]:
        return await self.request("POST", f"/tickets/{_part(ref)}/close")

    async def activity(self, *, limit: int | None = None, before: int | None = None) -> dict[str, Any]:
        return await self.request("GET", "/activity", query={"limit": limit, "before": before})
