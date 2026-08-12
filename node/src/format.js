import { EmbedBuilder } from "discord.js";

export const BRAND = 0x4f46e5;
export const GOOD = 0x22c55e;
export const WARN = 0xf59e0b;
export const BAD = 0xef4444;

export function money(value) {
  const n = Number(value ?? 0);
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function stamp(seconds) {
  if (seconds === null || seconds === undefined) return "never";
  const n = Number(seconds);
  if (!Number.isFinite(n) || n <= 0) return "never";
  return `<t:${Math.floor(n)}:R>`;
}

export function isoStamp(value) {
  if (!value) return "unknown";
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) return "unknown";
  return `<t:${Math.floor(ms / 1000)}:R>`;
}

export function stateLabel(state) {
  if (state === "unused") return "In stock";
  if (state === "active") return "Active";
  if (state === "expired") return "Expired";
  return state ?? "unknown";
}

export function embed(title, colour = BRAND) {
  return new EmbedBuilder().setTitle(title).setColor(colour).setTimestamp(new Date());
}

export function errorEmbed(message) {
  return new EmbedBuilder().setTitle("That did not work").setDescription(message).setColor(BAD);
}

export function chunk(lines, max = 4000) {
  const pages = [];
  let current = "";
  for (const line of lines) {
    const next = current ? `${current}\n${line}` : line;
    if (next.length > max) {
      if (current) pages.push(current);
      current = line.length > max ? `${line.slice(0, max - 1)}…` : line;
    } else {
      current = next;
    }
  }
  if (current) pages.push(current);
  return pages.length ? pages : ["Nothing to show."];
}

export function codeBlock(text, lang = "") {
  return `\`\`\`${lang}\n${text}\n\`\`\``;
}
