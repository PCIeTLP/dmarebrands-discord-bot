import { SlashCommandBuilder } from "discord.js";
import { BAD, BRAND, GOOD, WARN, chunk, embed, isoStamp } from "../format.js";

function hookLine(h) {
  const kind = h.kind === "updates" ? "update notes" : "status changes";
  const state = h.enabled ? "on" : "paused";
  const sent = h.last_sent_at ? `last post ${isoStamp(h.last_sent_at)}` : "nothing posted yet";
  const error = h.last_error ? `\nLast error: ${h.last_error}` : "";
  return `**#${h.id} ${h.label || "Unnamed webhook"}** · ${kind} · ${state}\n${(h.products ?? []).join(", ")} · ${sent}${error}`;
}

function idOption(sub, name, description) {
  return sub
    .setName(name)
    .setDescription(description)
    .addIntegerOption((option) =>
      option.setName("id").setDescription("The webhook number from /webhooks list").setRequired(true).setMinValue(1)
    );
}

export const webhooks = {
  data: new SlashCommandBuilder()
    .setName("webhooks")
    .setDescription("Your Discord webhooks for status changes and update notes")
    .addSubcommand((sub) => sub.setName("list").setDescription("List your webhooks"))
    .addSubcommand((sub) => idOption(sub, "test", "Send a test post through a webhook"))
    .addSubcommand((sub) => idOption(sub, "pause", "Stop a webhook posting for now"))
    .addSubcommand((sub) => idOption(sub, "resume", "Turn a paused webhook back on")),

  scopes: {
    list: "brand.read",
    test: "brand.write",
    pause: "brand.write",
    resume: "brand.write",
  },

  async run({ interaction, api, log }) {
    const sub = interaction.options.getSubcommand();

    if (sub === "list") {
      const result = await api.webhooks();
      const rows = result.data ?? [];
      if (!rows.length) {
        await interaction.editReply({
          content: "No webhooks yet. Add one on the Webhooks page of the partner panel.",
        });
        return;
      }
      await interaction.editReply({
        embeds: [
          embed(`Webhooks (${rows.length} of ${result.max ?? 10})`, BRAND).setDescription(chunk(rows.map(hookLine))[0]),
        ],
      });
      return;
    }

    const id = interaction.options.getInteger("id", true);
    const key = `discord:${interaction.id}`;

    if (sub === "test") {
      const result = await api.testWebhook(id, key);
      const view = result.sent
        ? embed("Test post sent", GOOD).setDescription(`Check the channel webhook #${id} posts to.`)
        : embed("Discord refused the test post", BAD).setDescription(
            `${result.error ?? "No reason given."}${result.paused ? "\nThe webhook has been paused. Fix it in Discord, then run `/webhooks resume`." : ""}`
          );
      await interaction.editReply({ embeds: [view] });
      return;
    }

    const on = sub === "resume";
    const hook = await api.setWebhookEnabled(id, on, key);
    await interaction.editReply({
      embeds: [
        embed(on ? "Webhook back on" : "Webhook paused", on ? GOOD : WARN).setDescription(
          `**#${hook.id} ${hook.label || "Unnamed webhook"}** ${on ? "posts again." : "will not post until you resume it."}`
        ),
      ],
    });
    await log(`**${interaction.user.tag}** ${on ? "resumed" : "paused"} webhook #${hook.id}`);
  },
};
