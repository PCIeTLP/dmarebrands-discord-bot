import { Client, Events, GatewayIntentBits, MessageFlags } from "discord.js";
import { loadConfig } from "./config.js";
import { ApiError, PartnerApi, friendly } from "./api.js";
import { BY_NAME, scopeFor } from "./commands/index.js";
import { allows, deniedMessage, scopesFor } from "./permissions.js";
import { errorEmbed } from "./format.js";

const config = loadConfig();
const api = new PartnerApi(config);

const client = new Client({ intents: [GatewayIntentBits.Guilds] });

async function logAction(text) {
  if (!config.logChannelId) return;
  try {
    const channel = await client.channels.fetch(config.logChannelId);
    if (channel && "send" in channel) await channel.send(text);
  } catch {}
}

async function handleAutocomplete(interaction) {
  const command = BY_NAME.get(interaction.commandName);
  if (!command?.autocomplete) {
    await interaction.respond([]).catch(() => {});
    return;
  }
  try {
    await command.autocomplete({ interaction, api, config });
  } catch {
    await interaction.respond([]).catch(() => {});
  }
}

async function handleCommand(interaction) {
  const command = BY_NAME.get(interaction.commandName);
  if (!command) return;

  if (interaction.guildId !== config.guildId) {
    await interaction.reply({
      content: "This bot only works in the server it was set up for.",
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  const granted = scopesFor(interaction.member, config.roleScopes);
  const subcommand = interaction.options.getSubcommand(false) ?? undefined;
  const needed = scopeFor(command, subcommand);

  if (needed && !allows(granted, needed)) {
    await interaction.reply({
      content: deniedMessage(needed),
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  await interaction.deferReply(config.ephemeral ? { flags: MessageFlags.Ephemeral } : {});

  try {
    await command.run({ interaction, api, config, granted, log: logAction });
  } catch (err) {
    const message = friendly(err);
    const detail =
      err instanceof ApiError && err.requestId ? `\nRequest id: \`${err.requestId}\`` : "";

    if (!(err instanceof ApiError)) {
      console.error(`[${interaction.commandName}]`, err);
    }

    await interaction
      .editReply({ embeds: [errorEmbed(message + detail)], components: [] })
      .catch(() => {});
  }
}

client.once(Events.ClientReady, async (ready) => {
  console.log(`Logged in as ${ready.user.tag}`);

  try {
    const me = await api.me();
    console.log(`Partner API connected as ${me.username} · balance $${me.balance_usd}`);
  } catch (err) {
    console.error(`\nThe partner API rejected the bot's key: ${friendly(err)}`);
    console.error("Fix DMAREBRANDS_API_KEY in your .env, then restart.\n");
  }

  console.log(`Serving ${BY_NAME.size} commands in guild ${config.guildId}`);
});

client.on(Events.InteractionCreate, async (interaction) => {
  try {
    if (interaction.isAutocomplete()) return await handleAutocomplete(interaction);
    if (interaction.isChatInputCommand()) return await handleCommand(interaction);
  } catch (err) {
    console.error("interaction failed", err);
  }
});

client.on(Events.Error, (err) => console.error("client error", err));

process.on("unhandledRejection", (err) => console.error("unhandled rejection", err));

client.login(config.token).catch((err) => {
  console.error(`\nCould not log in to Discord: ${err.message}`);
  console.error("Check DISCORD_TOKEN in your .env.\n");
  process.exit(1);
});
