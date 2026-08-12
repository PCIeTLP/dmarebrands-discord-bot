import { REST, Routes } from "discord.js";
import { loadConfig } from "../src/config.js";
import { COMMANDS } from "../src/commands/index.js";

const config = loadConfig();
const clear = process.argv.includes("--clear");
const rest = new REST({ version: "10" }).setToken(config.token);

const body = clear ? [] : COMMANDS.map((command) => command.data.toJSON());

try {
  const result = await rest.put(
    Routes.applicationGuildCommands(config.appId, config.guildId),
    { body }
  );

  if (clear) {
    console.log(`Removed every command from guild ${config.guildId}.`);
  } else {
    console.log(`Registered ${result.length} commands in guild ${config.guildId}:`);
    for (const command of result) console.log(`  /${command.name}`);
    console.log("\nGuild commands appear immediately. Reload Discord if you do not see them.");
  }
} catch (err) {
  console.error("\nRegistration failed.");
  if (err?.status === 401) {
    console.error("Discord rejected the token. Check DISCORD_TOKEN.");
  } else if (err?.status === 403) {
    console.error(
      "The bot is not in that guild, or was invited without the applications.commands scope.\n" +
        `Invite it again: https://discord.com/oauth2/authorize?client_id=${config.appId}&scope=bot%20applications.commands&permissions=0`
    );
  } else if (err?.status === 404) {
    console.error("Unknown application or guild. Check DISCORD_APP_ID and DISCORD_GUILD_ID.");
  } else {
    console.error(err?.message ?? err);
  }
  process.exit(1);
}
