import { account, domains, plans, stats, whoami } from "./account.js";
import { balance, ledger } from "./billing.js";
import { keys } from "./keys.js";
import { customers, hwid } from "./customers.js";
import { status, updates } from "./status.js";
import { brand } from "./brand.js";
import { activity, tickets } from "./support.js";

export const COMMANDS = [
  account,
  plans,
  stats,
  balance,
  ledger,
  keys,
  customers,
  hwid,
  domains,
  status,
  updates,
  brand,
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
