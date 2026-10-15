import { account, domains, plans, stats, whoami } from "./account.js";
import { balance, ledger, topup } from "./billing.js";
import { keys, redemptions } from "./keys.js";
import { customers, hwid, online } from "./customers.js";
import { changelog, status, updates } from "./status.js";
import { brand } from "./brand.js";
import { activity, tickets } from "./support.js";
import { accountinfo } from "./accountinfo.js";
import { webhooks } from "./webhooks.js";

export const COMMANDS = [
  account,
  plans,
  stats,
  balance,
  ledger,
  topup,
  keys,
  redemptions,
  customers,
  online,
  hwid,
  accountinfo,
  domains,
  status,
  updates,
  changelog,
  brand,
  webhooks,
  tickets,
  activity,
  whoami,
];

export const BY_NAME = new Map(COMMANDS.map((command) => [command.data.name, command]));

export function scopeFor(command, subcommand) {
  if (command.scopes === null || command.scopes === undefined) return null;
  if (typeof command.scopes === "string") return command.scopes;
  return command.scopes[subcommand] ?? null;
}
