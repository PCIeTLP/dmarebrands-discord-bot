import { REST, Routes } from "discord.js";
import { loadConfig } from "../src/config.js";
import { COMMANDS, scopeFor } from "../src/commands/index.js";
import { PartnerApi, friendly } from "../src/api.js";
import { GROUPS, SCOPES } from "../src/config.js";

let problems = 0;

function ok(label, detail = "") {
  console.log(`  PASS  ${label}${detail ? `  (${detail})` : ""}`);
}

function bad(label, detail = "") {
  problems += 1;
  console.log(`  FAIL  ${label}${detail ? `  (${detail})` : ""}`);
}

console.log("\nchecking your .env");
const config = loadConfig();
ok("env parsed", `${config.roleScopes.size} role(s) configured`);

console.log("\nchecking the partner API");
const api = new PartnerApi(config);
try {
  const me = await api.me();
  ok("API key works", `${me.username}, balance $${me.balance_usd}, ${me.discount_pct}% off`);
} catch (err) {
  bad("API key rejected", friendly(err));
}

console.log("\nchecking Discord");
const rest = new REST({ version: "10" }).setToken(config.token);
try {
  const app = await rest.get(Routes.currentApplication());
  ok("token works", `application ${app.name}`);
  if (app.id !== config.appId) {
    bad("DISCORD_APP_ID does not match this token", `token belongs to ${app.id}`);
  } else {
    ok("DISCORD_APP_ID matches the token");
  }
} catch (err) {
  bad("token rejected", err?.message ?? String(err));
}

try {
  const commands = await rest.get(Routes.applicationGuildCommands(config.appId, config.guildId));
  if (commands.length) {
    ok("commands registered in the guild", `${commands.length} found`);
  } else {
    bad("no commands registered yet", "run: npm run register");
  }
} catch (err) {
  if (err?.status === 403 || err?.status === 404) {
    bad("cannot read guild commands", "is the bot in that guild with applications.commands?");
  } else {
    bad("guild lookup failed", err?.message ?? String(err));
  }
}

console.log("\nchecking permission wiring");
const covered = new Set();
for (const scopes of config.roleScopes.values()) {
  for (const scope of scopes) covered.add(scope);
}

for (const command of COMMANDS) {
  const subs = command.data.options?.filter((o) => o.toJSON?.().type === 1) ?? [];
  const names = subs.length ? subs.map((s) => s.toJSON().name) : [undefined];
  for (const sub of names) {
    const needed = scopeFor(command, sub);
    const label = sub ? `/${command.data.name} ${sub}` : `/${command.data.name}`;
    if (!needed) {
      ok(`${label} needs no scope`);
    } else if (covered.has(needed)) {
      ok(`${label} usable`, needed);
    } else {
      bad(`${label} is unreachable`, `no role grants ${needed}`);
    }
  }
}

const unknown = [...covered].filter((scope) => !SCOPES.includes(scope));
if (unknown.length) bad("unknown scopes granted", unknown.join(", "));

console.log("\nrole groups in use");
for (const [group, scopes] of Object.entries(GROUPS)) {
  const ids = [...config.roleScopes.entries()]
    .filter(([, granted]) => scopes.every((s) => granted.has(s)))
    .map(([id]) => id);
  console.log(`  ${group.padEnd(14)} ${ids.length ? ids.join(", ") : "(none)"}`);
}

console.log(problems === 0 ? "\nEverything looks good.\n" : `\n${problems} problem(s) to fix.\n`);
process.exitCode = problems === 0 ? 0 : 1;
