import "dotenv/config";

const SNOWFLAKE = /^\d{17,20}$/;

export const SCOPES = [
  "account.read",
  "billing.read",
  "keys.read",
  "keys.buy",
  "keys.refund",
  "customers.read",
  "hwid.reset",
  "domains.read",
];

export const GROUPS = {
  ROLES_ADMIN: SCOPES,
  ROLES_KEYS: ["account.read", "keys.read", "keys.buy", "keys.refund", "customers.read"],
  ROLES_HWID: ["hwid.reset", "keys.read", "customers.read"],
  ROLES_BILLING: ["account.read", "billing.read"],
  ROLES_READ: ["account.read", "keys.read", "customers.read", "domains.read"],
};

class ConfigError extends Error {}

function required(name) {
  const value = (process.env[name] ?? "").trim();
  if (!value) throw new ConfigError(`${name} is missing from your .env`);
  return value;
}

function snowflake(name) {
  const value = required(name);
  if (!SNOWFLAKE.test(value)) {
    throw new ConfigError(`${name} must be a Discord ID (17-20 digits), got "${value}"`);
  }
  return value;
}

function idList(name) {
  const raw = (process.env[name] ?? "").trim();
  if (!raw) return [];
  const parts = raw
    .split(/[,\s]+/)
    .map((p) => p.trim())
    .filter(Boolean);

  const bad = parts.filter((p) => !SNOWFLAKE.test(p));
  if (bad.length) {
    throw new ConfigError(`${name} contains invalid role IDs: ${bad.join(", ")}`);
  }
  return parts;
}

function optionalSnowflake(name) {
  const raw = (process.env[name] ?? "").trim();
  if (!raw) return null;
  if (!SNOWFLAKE.test(raw)) {
    throw new ConfigError(`${name} must be a Discord ID (17-20 digits), got "${raw}"`);
  }
  return raw;
}

function buildRoleScopes() {
  const map = new Map();
  let total = 0;

  for (const [envName, scopes] of Object.entries(GROUPS)) {
    for (const roleId of idList(envName)) {
      total += 1;
      const current = map.get(roleId) ?? new Set();
      for (const scope of scopes) current.add(scope);
      map.set(roleId, current);
    }
  }

  if (!total) {
    throw new ConfigError(
      "No roles configured. Set at least one of ROLES_ADMIN, ROLES_KEYS, ROLES_HWID, ROLES_BILLING or ROLES_READ."
    );
  }

  return map;
}

function load() {
  const base = (process.env.DMAREBRANDS_API_BASE ?? "https://api.dmarebrands.st/v1").trim();

  let parsed;
  try {
    parsed = new URL(base);
  } catch {
    throw new ConfigError(`DMAREBRANDS_API_BASE is not a valid URL: "${base}"`);
  }
  if (parsed.protocol !== "https:" && parsed.hostname !== "localhost" && parsed.hostname !== "127.0.0.1") {
    throw new ConfigError("DMAREBRANDS_API_BASE must use https so your API key is never sent in the clear.");
  }

  const apiKey = required("DMAREBRANDS_API_KEY");
  if (!apiKey.startsWith("dmarebrands_live_")) {
    throw new ConfigError(
      'DMAREBRANDS_API_KEY does not look right. Partner keys start with "dmarebrands_live_". Create one at https://partners.dmarebrands.st/partners/api'
    );
  }

  return {
    token: required("DISCORD_TOKEN"),
    appId: snowflake("DISCORD_APP_ID"),
    guildId: snowflake("DISCORD_GUILD_ID"),
    apiKey,
    apiBase: base.replace(/\/+$/, ""),
    roleScopes: buildRoleScopes(),
    logChannelId: optionalSnowflake("LOG_CHANNEL_ID"),
    ephemeral: (process.env.EPHEMERAL ?? "true").toLowerCase() !== "false",
  };
}

export function loadConfig() {
  try {
    return load();
  } catch (err) {
    if (err instanceof ConfigError) {
      console.error(`\nConfiguration problem: ${err.message}\n`);
      console.error("Copy .env.example to .env and fill it in, then try again.\n");
      process.exit(1);
    }
    throw err;
  }
}
