import { SCOPES } from "./config.js";

export function scopesFor(member, roleScopes) {
  const granted = new Set();
  if (!member) return granted;

  const roleIds = member.roles?.cache ? [...member.roles.cache.keys()] : [];
  for (const roleId of roleIds) {
    const scopes = roleScopes.get(roleId);
    if (!scopes) continue;
    for (const scope of scopes) granted.add(scope);
  }
  return granted;
}

export function allows(granted, needed) {
  return granted.has(needed);
}

export function describeScopes(granted) {
  if (!granted.size) return "none";
  return SCOPES.filter((scope) => granted.has(scope)).join(", ");
}

export function deniedMessage(needed) {
  return `You do not have permission to do that. This command needs the \`${needed}\` scope, which your roles do not grant.`;
}
