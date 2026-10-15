from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any
from urllib.parse import quote

import aiohttp
from yarl import URL

TIMEOUT_SECONDS = 15
FILE_TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3
IN_PROGRESS_WAIT_SECONDS = 60
LONGEST_RETRY_SECONDS = 30

FRIENDLY = {
    "unauthorized": "The bot's API key was rejected. It may have been revoked.",
    "insufficient_balance": "Not enough balance on the partner account.",
    "forbidden": "That partner account is no longer active.",
    "not_found": "Nothing matched that.",
    "conflict": "That is not possible in the current state.",
    "invalid_request": "One of the values was out of range.",
    "rate_limited": "The API is rate limiting us. Try again in a moment.",
    "unavailable": "Something the API relies on is not answering. Try again shortly.",
    "server_error": "The API had a problem. Try again shortly.",
}

PURCHASE_RUNNING = "That purchase is still going through. Check /keys list in a minute before buying again."
STILL_RUNNING = "That is still going through. Give it a minute and check before trying again."


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
        self.purchase = False


def _part(value: Any) -> str:
    text = str(value)
    if text in ("", ".", ".."):
        raise ApiError(404, "not_found", FRIENDLY["not_found"])
    return quote(text, safe="")


def _seconds(header: str | None) -> float | None:
    try:
        value = float(header or "")
    except ValueError:
        return None
    return value if 0 < value < float("inf") else None


def _count(header: str | None, current: int | None) -> int | None:
    if header is None:
        return current
    try:
        return int(float(header))
    except (ValueError, OverflowError):
        return current


def _wait(err: ApiError, left: float) -> float:
    return min(max(err.retry_after or 2, 1), 10, left)


def _file_name(disposition: str | None) -> str:
    match = re.search(r'filename="([^"]+)"', disposition or "")
    return match.group(1) if match else "account-info.zip"


def friendly(err: BaseException) -> str:
    if isinstance(err, ApiError):
        if err.code == "in_progress":
            return PURCHASE_RUNNING if err.purchase else STILL_RUNNING
        return err.message or FRIENDLY.get(err.code, "The request failed.")
    if isinstance(err, asyncio.TimeoutError):
        return "The API did not respond in time. Try again."
    return "Could not reach the API. Try again shortly."


def _error(status: int, text: str, request_id: str | None, retry_after: float | None) -> ApiError:
    payload: dict[str, Any] = {}
    if text:
        try:
            parsed = json.loads(text)
            payload = parsed if isinstance(parsed, dict) else {}
        except ValueError:
            payload = {}
    error = payload.get("error") or {}
    return ApiError(
        status,
        error.get("code", "server_error"),
        error.get("message", f"HTTP {status}"),
        request_id,
        retry_after,
    )


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
                    "user-agent": "dmarebrands-discord-bot/1.3 (+python)",
                },
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _track(self, res: aiohttp.ClientResponse) -> None:
        self.remaining = _count(res.headers.get("x-ratelimit-remaining"), self.remaining)
        self.reset_in = _count(res.headers.get("x-ratelimit-reset"), self.reset_in)

    def _url(self, path: str) -> URL:
        return URL(f"{URL(self.api_base)}{path}", encoded=True)

    async def send(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        idempotent: bool = False,
        key: str | None = None,
    ) -> dict[str, Any]:
        params = {}
        for name, value in (query or {}).items():
            if value is None or value == "":
                continue
            params[name] = str(value)

        headers = {"idempotency-key": key} if key else None
        safe = method == "GET" or idempotent or bool(key)
        session = await self.session()
        url = self._url(path)
        last_error: BaseException | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                async with session.request(method, url, params=params, json=body, headers=headers) as res:
                    self._track(res)
                    request_id = res.headers.get("x-request-id")
                    retry_after = _seconds(res.headers.get("retry-after"))
                    text = await res.text(errors="replace")

                    if res.status < 400:
                        if not text:
                            return {}
                        try:
                            parsed = json.loads(text)
                        except ValueError:
                            return {}
                        return parsed if isinstance(parsed, dict) else {}

                    if res.status == 429 and attempt < MAX_ATTEMPTS and (retry_after or 2) <= LONGEST_RETRY_SECONDS:
                        await asyncio.sleep(max(retry_after or 2, 1))
                        continue

                    if res.status >= 500 and attempt < MAX_ATTEMPTS and safe:
                        await asyncio.sleep(attempt * 0.5)
                        continue

                    raise _error(res.status, text, request_id, retry_after)

            except ApiError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_error = err
                if not safe or attempt >= MAX_ATTEMPTS:
                    raise
                await asyncio.sleep(attempt * 0.5)

        if last_error:
            raise last_error
        raise RuntimeError("Request failed")

    async def request(self, method: str, path: str, **options: Any) -> dict[str, Any]:
        if not options.get("key"):
            return await self.send(method, path, **options)
        give_up_at = time.monotonic() + IN_PROGRESS_WAIT_SECONDS
        while True:
            try:
                return await self.send(method, path, **options)
            except ApiError as err:
                if err.code != "in_progress":
                    raise
                left = give_up_at - time.monotonic()
                if left <= 0:
                    raise
                await asyncio.sleep(_wait(err, left))

    async def file(self, path: str) -> dict[str, Any]:
        session = await self.session()
        async with session.get(
            self._url(path),
            headers={"accept": "application/zip, application/json"},
            timeout=aiohttp.ClientTimeout(total=FILE_TIMEOUT_SECONDS),
        ) as res:
            self._track(res)
            if res.status >= 400:
                raise _error(
                    res.status,
                    await res.text(errors="replace"),
                    res.headers.get("x-request-id"),
                    _seconds(res.headers.get("retry-after")),
                )
            return {
                "name": _file_name(res.headers.get("content-disposition")),
                "data": await res.read(),
                "sha256": res.headers.get("x-content-sha256"),
            }

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

    async def stats_daily(self, days: int | None = None) -> dict[str, Any]:
        return await self.request("GET", "/stats/daily", query={"days": days})

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
        in_progress: ApiError | None = None
        while True:
            try:
                return await self.send("POST", "/keys", body=body, idempotent=bool(reference))
            except ApiError as err:
                if err.code == "in_progress":
                    err.purchase = True
                    left = give_up_at - time.monotonic()
                    if left <= 0:
                        raise
                    in_progress = err
                    await asyncio.sleep(_wait(err, left))
                    continue
                if in_progress is None or (err.status < 500 and err.status != 429):
                    raise
                raise in_progress from err
            except Exception as err:
                if in_progress is None:
                    raise
                raise in_progress from err

    async def get_key(self, code: str) -> dict[str, Any]:
        return await self.request("GET", f"/keys/{_part(code)}")

    async def refund_key(self, code: str, key: str | None = None) -> dict[str, Any]:
        return await self.request("DELETE", f"/keys/{_part(code)}", key=key)

    async def reset_by_key(self, code: str, key: str | None = None) -> dict[str, Any]:
        return await self.request("POST", f"/keys/{_part(code)}/reset-hwid", key=key)

    async def redemptions(self, *, since: int | None = None, limit: int | None = None) -> dict[str, Any]:
        return await self.request("GET", "/redemptions", query={"since": since, "limit": limit})

    async def list_customers(self, *, search: str | None = None, limit: int | None = None) -> dict[str, Any]:
        return await self.request("GET", "/customers", query={"search": search, "limit": limit})

    async def online(self) -> dict[str, Any]:
        return await self.request("GET", "/customers/online")

    async def get_customer(self, ref: int | str) -> dict[str, Any]:
        return await self.request("GET", f"/customers/{_part(ref)}")

    async def customer_keys(self, ref: int | str) -> dict[str, Any]:
        return await self.request("GET", f"/customers/{_part(ref)}/keys")

    async def reset_by_customer(self, ref: int | str, key: str | None = None) -> dict[str, Any]:
        return await self.request("POST", f"/customers/{_part(ref)}/reset-hwid", key=key)

    async def coins(self) -> dict[str, Any]:
        return await self.request("GET", "/coins")

    async def start_topup(self, amount_usd: float, coin: str, key: str | None = None) -> dict[str, Any]:
        return await self.request("POST", "/topups", body={"amount_usd": amount_usd, "coin": coin}, key=key)

    async def topups(self, limit: int | None = None) -> dict[str, Any]:
        return await self.request("GET", "/topups", query={"limit": limit})

    async def get_topup(self, ref: str) -> dict[str, Any]:
        return await self.request("GET", f"/topups/{_part(ref)}")

    async def list_account_info(self, *, status: str | None = None, limit: int | None = None) -> dict[str, Any]:
        return await self.request("GET", "/account-info", query={"status": status, "limit": limit})

    async def request_account_info(
        self,
        *,
        code: str,
        reason: str,
        reference: str | None = None,
        note: str | None = None,
        key: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"key": code, "reason": reason}
        if reference:
            body["reference"] = reference
        if note:
            body["note"] = note
        return await self.request("POST", "/account-info", body=body, key=key)

    async def get_account_info(self, ref: str) -> dict[str, Any]:
        return await self.request("GET", f"/account-info/{_part(ref)}")

    async def download_account_info(self, ref: str) -> dict[str, Any]:
        return await self.file(f"/account-info/{_part(ref)}/download")

    async def domains(self) -> dict[str, Any]:
        return await self.request("GET", "/domains")

    async def status(self, product: str | None = None) -> dict[str, Any]:
        return await self.request("GET", "/status", query={"product": product})

    async def updates(self, product: str | None = None) -> dict[str, Any]:
        return await self.request("GET", "/updates", query={"product": product})

    async def changelogs(
        self,
        *,
        product: str | None = None,
        lang: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return await self.request("GET", "/changelogs", query={"product": product, "lang": lang, "limit": limit})

    async def brand(self) -> dict[str, Any]:
        return await self.request("GET", "/brand")

    async def update_brand(self, patch: dict[str, Any], key: str | None = None) -> dict[str, Any]:
        return await self.request("PATCH", "/brand", body=patch, key=key)

    async def webhooks(self) -> dict[str, Any]:
        return await self.request("GET", "/webhooks")

    async def test_webhook(self, hook_id: int, key: str | None = None) -> dict[str, Any]:
        return await self.request("POST", f"/webhooks/{_part(hook_id)}/test", key=key)

    async def set_webhook_enabled(self, hook_id: int, enabled: bool, key: str | None = None) -> dict[str, Any]:
        return await self.request("PATCH", f"/webhooks/{_part(hook_id)}", body={"enabled": enabled}, key=key)

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
        key: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"subject": subject, "body": body}
        if category:
            payload["category"] = category
        if priority:
            payload["priority"] = priority
        return await self.request("POST", "/tickets", body=payload, key=key)

    async def get_ticket(self, ref: str) -> dict[str, Any]:
        return await self.request("GET", f"/tickets/{_part(ref)}")

    async def mark_ticket_read(self, ref: str) -> dict[str, Any]:
        return await self.request("POST", f"/tickets/{_part(ref)}/read")

    async def reply_ticket(self, ref: str, body: str, key: str | None = None) -> dict[str, Any]:
        return await self.request("POST", f"/tickets/{_part(ref)}/reply", body={"body": body}, key=key)

    async def close_ticket(self, ref: str) -> dict[str, Any]:
        return await self.request("POST", f"/tickets/{_part(ref)}/close")

    async def activity(self, *, limit: int | None = None, before: int | None = None) -> dict[str, Any]:
        return await self.request("GET", "/activity", query={"limit": limit, "before": before})
