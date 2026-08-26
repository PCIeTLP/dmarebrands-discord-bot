const TIMEOUT_MS = 15_000;
const MAX_ATTEMPTS = 3;

export class ApiError extends Error {
  constructor(status, code, message, requestId) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId ?? null;
  }
}

const FRIENDLY = {
  unauthorized: "The bot's API key was rejected. It may have been revoked.",
  insufficient_balance: "Not enough balance on the partner account.",
  forbidden: "That partner account is no longer active.",
  not_found: "Nothing matched that.",
  conflict: "That is not possible in the current state.",
  invalid_request: "One of the values was out of range.",
  rate_limited: "The API is rate limiting us. Try again in a moment.",
  server_error: "The API had a problem. Try again shortly.",
};

export function friendly(err) {
  if (err instanceof ApiError) {
    return err.message || FRIENDLY[err.code] || "The request failed.";
  }
  if (err instanceof Error && err.name === "AbortError") {
    return "The API did not respond in time. Try again.";
  }
  return "Could not reach the API. Try again shortly.";
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export class PartnerApi {
  constructor({ apiKey, apiBase }) {
    this.apiKey = apiKey;
    this.apiBase = apiBase;
    this.remaining = null;
    this.resetIn = null;
  }

  async request(method, path, { query, body } = {}) {
    const url = new URL(`${this.apiBase}${path}`);
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value === undefined || value === null || value === "") continue;
        url.searchParams.set(key, String(value));
      }
    }

    let lastError = null;

    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

      try {
        const res = await fetch(url, {
          method,
          headers: {
            authorization: `Bearer ${this.apiKey}`,
            accept: "application/json",
            "user-agent": "dmarebrands-discord-bot/1.0 (+node)",
            ...(body ? { "content-type": "application/json" } : {}),
          },
          body: body ? JSON.stringify(body) : undefined,
          signal: controller.signal,
        });

        const limitRemaining = res.headers.get("x-ratelimit-remaining");
        if (limitRemaining !== null) this.remaining = Number(limitRemaining);
        const limitReset = res.headers.get("x-ratelimit-reset");
        if (limitReset !== null) this.resetIn = Number(limitReset);

        const requestId = res.headers.get("x-request-id");
        const text = await res.text();

        let payload = null;
        if (text) {
          try {
            payload = JSON.parse(text);
          } catch {
            payload = null;
          }
        }

        if (res.ok) return payload ?? {};

        const code = payload?.error?.code ?? "server_error";
        const message = payload?.error?.message ?? `HTTP ${res.status}`;

        if (res.status === 429 && attempt < MAX_ATTEMPTS) {
          const retryAfter = Number(res.headers.get("retry-after") ?? 2);
          await sleep(Math.min(Math.max(retryAfter, 1), 30) * 1000);
          continue;
        }

        if (res.status >= 500 && attempt < MAX_ATTEMPTS && method === "GET") {
          await sleep(attempt * 500);
          continue;
        }

        throw new ApiError(res.status, code, message, requestId);
      } catch (err) {
        if (err instanceof ApiError) throw err;
        lastError = err;
        const retryable = method === "GET" && attempt < MAX_ATTEMPTS;
        if (!retryable) throw err;
        await sleep(attempt * 500);
      } finally {
        clearTimeout(timer);
      }
    }

    throw lastError ?? new Error("Request failed");
  }

  me() {
    return this.request("GET", "/me");
  }

  plans() {
    return this.request("GET", "/plans");
  }

  balance() {
    return this.request("GET", "/balance");
  }

  ledger(limit) {
    return this.request("GET", "/ledger", { query: { limit } });
  }

  stats() {
    return this.request("GET", "/stats");
  }

  listKeys({ filter, search, limit } = {}) {
    return this.request("GET", "/keys", { query: { filter, search, limit } });
  }

  buyKeys(plan, count) {
    return this.request("POST", "/keys", { body: { plan, count } });
  }

  getKey(code) {
    return this.request("GET", `/keys/${encodeURIComponent(code)}`);
  }

  refundKey(code) {
    return this.request("DELETE", `/keys/${encodeURIComponent(code)}`);
  }

  resetByKey(code) {
    return this.request("POST", `/keys/${encodeURIComponent(code)}/reset-hwid`);
  }

  listCustomers({ search, limit } = {}) {
    return this.request("GET", "/customers", { query: { search, limit } });
  }

  getCustomer(ref) {
    return this.request("GET", `/customers/${encodeURIComponent(String(ref))}`);
  }

  resetByCustomer(ref) {
    return this.request("POST", `/customers/${encodeURIComponent(String(ref))}/reset-hwid`);
  }

  domains() {
    return this.request("GET", "/domains");
  }

  status(product) {
    return this.request("GET", "/status", { query: { product } });
  }

  updates() {
    return this.request("GET", "/updates");
  }

  brand() {
    return this.request("GET", "/brand");
  }

  updateBrand(patch) {
    return this.request("PATCH", "/brand", { body: patch });
  }

  listTickets({ status, search, limit } = {}) {
    return this.request("GET", "/tickets", { query: { status, search, limit } });
  }

  createTicket({ subject, body, category, priority }) {
    return this.request("POST", "/tickets", { body: { subject, body, category, priority } });
  }

  getTicket(ref) {
    return this.request("GET", `/tickets/${encodeURIComponent(ref)}`);
  }

  replyTicket(ref, body) {
    return this.request("POST", `/tickets/${encodeURIComponent(ref)}/reply`, { body: { body } });
  }

  closeTicket(ref) {
    return this.request("POST", `/tickets/${encodeURIComponent(ref)}/close`);
  }

  activity({ limit, before } = {}) {
    return this.request("GET", "/activity", { query: { limit, before } });
  }
}
