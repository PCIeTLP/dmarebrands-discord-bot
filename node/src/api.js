const TIMEOUT_MS = 15_000;
const FILE_TIMEOUT_MS = 60_000;
const MAX_ATTEMPTS = 3;
const IN_PROGRESS_WAIT_MS = 60_000;
const LONGEST_RETRY_SECONDS = 30;

export class ApiError extends Error {
  constructor(status, code, message, requestId, retryAfter) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId ?? null;
    this.retryAfter = retryAfter ?? null;
    this.purchase = false;
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
  unavailable: "Something the API relies on is not answering. Try again shortly.",
  server_error: "The API had a problem. Try again shortly.",
};

const PURCHASE_RUNNING = "That purchase is still going through. Check /keys list in a minute before buying again.";
const STILL_RUNNING = "That is still going through. Give it a minute and check before trying again.";

export function friendly(err) {
  if (err instanceof ApiError) {
    if (err.code === "in_progress") return err.purchase ? PURCHASE_RUNNING : STILL_RUNNING;
    return err.message || FRIENDLY[err.code] || "The request failed.";
  }
  if (err instanceof Error && err.name === "AbortError") {
    return "The API did not respond in time. Try again.";
  }
  return "Could not reach the API. Try again shortly.";
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function seconds(header) {
  const value = Number(header);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function part(value) {
  const text = String(value);
  if (text === "" || text === "." || text === "..") throw new ApiError(404, "not_found", FRIENDLY.not_found);
  return encodeURIComponent(text);
}

function waitFor(err, left) {
  return Math.min(Math.min(Math.max(err.retryAfter ?? 2, 1), 10) * 1000, left);
}

function fileName(disposition) {
  const match = /filename="([^"]+)"/.exec(disposition ?? "");
  return match ? match[1] : "account-info.zip";
}

export class PartnerApi {
  constructor({ apiKey, apiBase }) {
    this.apiKey = apiKey;
    this.apiBase = apiBase;
    this.remaining = null;
    this.resetIn = null;
  }

  headers(extra = {}) {
    return {
      authorization: `Bearer ${this.apiKey}`,
      accept: "application/json",
      "user-agent": "dmarebrands-discord-bot/1.3 (+node)",
      ...extra,
    };
  }

  track(res) {
    const limitRemaining = res.headers.get("x-ratelimit-remaining");
    if (limitRemaining !== null) this.remaining = Number(limitRemaining);
    const limitReset = res.headers.get("x-ratelimit-reset");
    if (limitReset !== null) this.resetIn = Number(limitReset);
  }

  async send(method, path, { query, body, idempotent = false, key } = {}) {
    const url = new URL(`${this.apiBase}${path}`);
    if (query) {
      for (const [name, value] of Object.entries(query)) {
        if (value === undefined || value === null || value === "") continue;
        url.searchParams.set(name, String(value));
      }
    }

    const safe = method === "GET" || idempotent || Boolean(key);
    let lastError = null;

    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

      try {
        const res = await fetch(url, {
          method,
          headers: this.headers({
            ...(key ? { "idempotency-key": key } : {}),
            ...(body ? { "content-type": "application/json" } : {}),
          }),
          body: body ? JSON.stringify(body) : undefined,
          signal: controller.signal,
        });

        this.track(res);
        const requestId = res.headers.get("x-request-id");
        const retryAfter = seconds(res.headers.get("retry-after"));
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

        if (res.status === 429 && attempt < MAX_ATTEMPTS && (retryAfter ?? 2) <= LONGEST_RETRY_SECONDS) {
          await sleep(Math.max(retryAfter ?? 2, 1) * 1000);
          continue;
        }

        if (res.status >= 500 && attempt < MAX_ATTEMPTS && safe) {
          await sleep(attempt * 500);
          continue;
        }

        throw new ApiError(res.status, code, message, requestId, retryAfter);
      } catch (err) {
        if (err instanceof ApiError) throw err;
        lastError = err;
        if (!safe || attempt >= MAX_ATTEMPTS) throw err;
        await sleep(attempt * 500);
      } finally {
        clearTimeout(timer);
      }
    }

    throw lastError ?? new Error("Request failed");
  }

  async request(method, path, options = {}) {
    if (!options.key) return this.send(method, path, options);
    const giveUpAt = performance.now() + IN_PROGRESS_WAIT_MS;
    for (;;) {
      try {
        return await this.send(method, path, options);
      } catch (err) {
        if (!(err instanceof ApiError) || err.code !== "in_progress") throw err;
        const left = giveUpAt - performance.now();
        if (left <= 0) throw err;
        await sleep(waitFor(err, left));
      }
    }
  }

  async file(path) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FILE_TIMEOUT_MS);
    try {
      const res = await fetch(new URL(`${this.apiBase}${path}`), {
        headers: this.headers({ accept: "application/zip, application/json" }),
        signal: controller.signal,
      });
      this.track(res);
      if (!res.ok) {
        let payload = null;
        try {
          payload = JSON.parse(await res.text());
        } catch {
          payload = null;
        }
        throw new ApiError(
          res.status,
          payload?.error?.code ?? "server_error",
          payload?.error?.message ?? `HTTP ${res.status}`,
          res.headers.get("x-request-id"),
          seconds(res.headers.get("retry-after"))
        );
      }
      return {
        name: fileName(res.headers.get("content-disposition")),
        data: Buffer.from(await res.arrayBuffer()),
        sha256: res.headers.get("x-content-sha256"),
      };
    } finally {
      clearTimeout(timer);
    }
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

  statsDaily(days) {
    return this.request("GET", "/stats/daily", { query: { days } });
  }

  listKeys({ filter, search, limit } = {}) {
    return this.request("GET", "/keys", { query: { filter, search, limit } });
  }

  async buyKeys(plan, count, reference) {
    const giveUpAt = performance.now() + IN_PROGRESS_WAIT_MS;
    let inProgress = null;
    for (;;) {
      try {
        return await this.send("POST", "/keys", {
          body: { plan, count, ...(reference ? { reference } : {}) },
          idempotent: Boolean(reference),
        });
      } catch (err) {
        if (err instanceof ApiError && err.code === "in_progress") {
          err.purchase = true;
          const left = giveUpAt - performance.now();
          if (left <= 0) throw err;
          inProgress = err;
          await sleep(waitFor(err, left));
          continue;
        }
        const answered = err instanceof ApiError && err.status < 500 && err.status !== 429;
        throw inProgress && !answered ? inProgress : err;
      }
    }
  }

  getKey(code) {
    return this.request("GET", `/keys/${part(code)}`);
  }

  refundKey(code, key) {
    return this.request("DELETE", `/keys/${part(code)}`, { key });
  }

  resetByKey(code, key) {
    return this.request("POST", `/keys/${part(code)}/reset-hwid`, { key });
  }

  redemptions({ since, limit } = {}) {
    return this.request("GET", "/redemptions", { query: { since, limit } });
  }

  listCustomers({ search, limit } = {}) {
    return this.request("GET", "/customers", { query: { search, limit } });
  }

  online() {
    return this.request("GET", "/customers/online");
  }

  getCustomer(ref) {
    return this.request("GET", `/customers/${part(ref)}`);
  }

  customerKeys(ref) {
    return this.request("GET", `/customers/${part(ref)}/keys`);
  }

  resetByCustomer(ref, key) {
    return this.request("POST", `/customers/${part(ref)}/reset-hwid`, { key });
  }

  coins() {
    return this.request("GET", "/coins");
  }

  startTopup(amountUsd, coin, key) {
    return this.request("POST", "/topups", { body: { amount_usd: amountUsd, coin }, key });
  }

  topups(limit) {
    return this.request("GET", "/topups", { query: { limit } });
  }

  getTopup(ref) {
    return this.request("GET", `/topups/${part(ref)}`);
  }

  listAccountInfo({ status, limit } = {}) {
    return this.request("GET", "/account-info", { query: { status, limit } });
  }

  requestAccountInfo({ code, reason, reference, note }, key) {
    return this.request("POST", "/account-info", {
      body: { key: code, reason, ...(reference ? { reference } : {}), ...(note ? { note } : {}) },
      key,
    });
  }

  getAccountInfo(ref) {
    return this.request("GET", `/account-info/${part(ref)}`);
  }

  downloadAccountInfo(ref) {
    return this.file(`/account-info/${part(ref)}/download`);
  }

  domains() {
    return this.request("GET", "/domains");
  }

  status(product) {
    return this.request("GET", "/status", { query: { product } });
  }

  updates(product) {
    return this.request("GET", "/updates", { query: { product } });
  }

  changelogs({ product, lang, limit } = {}) {
    return this.request("GET", "/changelogs", { query: { product, lang, limit } });
  }

  brand() {
    return this.request("GET", "/brand");
  }

  updateBrand(patch, key) {
    return this.request("PATCH", "/brand", { body: patch, key });
  }

  webhooks() {
    return this.request("GET", "/webhooks");
  }

  testWebhook(id, key) {
    return this.request("POST", `/webhooks/${part(id)}/test`, { key });
  }

  setWebhookEnabled(id, enabled, key) {
    return this.request("PATCH", `/webhooks/${part(id)}`, { body: { enabled }, key });
  }

  listTickets({ status, search, limit } = {}) {
    return this.request("GET", "/tickets", { query: { status, search, limit } });
  }

  createTicket({ subject, body, category, priority }, key) {
    return this.request("POST", "/tickets", { body: { subject, body, category, priority }, key });
  }

  getTicket(ref) {
    return this.request("GET", `/tickets/${part(ref)}`);
  }

  markTicketRead(ref) {
    return this.request("POST", `/tickets/${part(ref)}/read`);
  }

  replyTicket(ref, body, key) {
    return this.request("POST", `/tickets/${part(ref)}/reply`, { body: { body }, key });
  }

  closeTicket(ref) {
    return this.request("POST", `/tickets/${part(ref)}/close`);
  }

  activity({ limit, before } = {}) {
    return this.request("GET", "/activity", { query: { limit, before } });
  }
}
