import { SlashCommandBuilder } from "discord.js";
import { BRAND, embed, isoStamp, money } from "../format.js";
import { describeScopes } from "../permissions.js";

export const account = {
  data: new SlashCommandBuilder()
    .setName("account")
    .setDescription("Show the partner account this bot is connected to"),
  scopes: "account.read",
  async run({ interaction, api }) {
    const me = await api.me();
    const view = embed(`Partner account: ${me.username}`, BRAND)
      .setDescription(me.brand?.name ? `Trading as **${me.brand.name}**` : "No brand name set yet.")
      .addFields(
        { name: "Balance", value: money(me.balance_usd), inline: true },
        { name: "Discount", value: `${me.discount_pct}%`, inline: true },
        { name: "Customers", value: String(me.stats?.customers ?? 0), inline: true },
        { name: "Keys in stock", value: String(me.stats?.keys_unused ?? 0), inline: true },
        { name: "Keys active", value: String(me.stats?.keys_active ?? 0), inline: true },
        { name: "Spent all time", value: money(me.stats?.spent_usd), inline: true }
      );

    if (me.brand?.store_url) view.setURL(me.brand.store_url);
    await interaction.editReply({ embeds: [view] });
  },
};

export const plans = {
  data: new SlashCommandBuilder()
    .setName("plans")
    .setDescription("List every plan you can buy, with your discounted price"),
  scopes: "account.read",
  async run({ interaction, api }) {
    const result = await api.plans();
    const rows = result.data ?? [];

    if (!rows.length) {
      await interaction.editReply({ content: "No plans are available right now." });
      return;
    }

    const view = embed("Plans", BRAND).setDescription(
      rows
        .map(
          (p) =>
            `**${p.product} · ${p.label}** \`${p.id}\`\n${p.days} days · ${money(p.your_price_usd)} for you · list ${money(
              p.list_price_usd
            )} · you save ${money(p.saving_usd)}`
        )
        .join("\n\n")
    );

    await interaction.editReply({ embeds: [view] });
  },
};

export const stats = {
  data: new SlashCommandBuilder()
    .setName("stats")
    .setDescription("Headline numbers for the partner account"),
  scopes: "account.read",
  async run({ interaction, api }) {
    const s = await api.stats();
    const view = embed("Stats", BRAND).addFields(
      { name: "Keys issued", value: String(s.keys_total), inline: true },
      { name: "In stock", value: String(s.keys_unused), inline: true },
      { name: "Active", value: String(s.keys_active), inline: true },
      { name: "Expired", value: String(s.keys_expired), inline: true },
      { name: "Customers", value: String(s.customers), inline: true },
      { name: "Balance", value: money(s.balance_usd), inline: true },
      { name: "Spent all time", value: money(s.spent_usd), inline: true },
      { name: "HWID resets (30d)", value: String(s.hwid_resets_30d), inline: true }
    );
    await interaction.editReply({ embeds: [view] });
  },
};

export const domains = {
  data: new SlashCommandBuilder()
    .setName("domains")
    .setDescription("Show your white-label domains and whether they are live"),
  scopes: "domains.read",
  async run({ interaction, api }) {
    const result = await api.domains();
    const rows = result.data ?? [];

    if (!rows.length) {
      await interaction.editReply({
        content: `No domains set up yet. Add one at https://partners.dmarebrands.st/partners/branding\nPoint a CNAME at \`${result.cname_target ?? "the target shown in the panel"}\`.`,
      });
      return;
    }

    const view = embed("Your domains", BRAND).setDescription(
      rows
        .map((d) => {
          const state = d.live ? "Live" : `Not live yet (${d.status} / ssl ${d.ssl_status})`;
          const checked = d.checked_at ? ` · checked ${isoStamp(d.checked_at)}` : "";
          const error = d.last_error ? `\n${d.last_error}` : "";
          return `**${d.hostname}** · ${d.kind}\n${state}${checked}${error}`;
        })
        .join("\n\n")
    );

    if (result.cname_target) view.setFooter({ text: `CNAME target: ${result.cname_target}` });
    await interaction.editReply({ embeds: [view] });
  },
};

export const whoami = {
  data: new SlashCommandBuilder()
    .setName("whoami")
    .setDescription("Show what this bot will let you do"),
  scopes: null,
  async run({ interaction, granted }) {
    const view = embed("Your access", BRAND).setDescription(
      granted.size
        ? `You have these scopes:\n\`${describeScopes(granted)}\``
        : "None of your roles are configured for this bot, so every command will be refused."
    );
    await interaction.editReply({ embeds: [view] });
  },
};
