import { SlashCommandBuilder } from "discord.js";
import { BAD, BRAND, GOOD, WARN, codeBlock, embed, isoStamp, money, stamp, stateLabel } from "../format.js";
import { confirm } from "../confirm.js";

const FILTER_LABEL = {
  all: "everything",
  unused: "in stock",
  active: "active",
  expired: "expired",
};

const FILTERS = [
  { name: "All", value: "all" },
  { name: "In stock", value: "unused" },
  { name: "Active", value: "active" },
  { name: "Expired", value: "expired" },
];

function keyLine(key) {
  const owner = key.customer ? ` · ${key.customer.username}` : "";
  const expiry = key.expires_at ? ` · expires ${stamp(key.expires_at)}` : "";
  return `\`${key.code}\` · ${stateLabel(key.state)} · ${key.days}d ${key.product}${owner}${expiry}`;
}

export const keys = {
  data: new SlashCommandBuilder()
    .setName("keys")
    .setDescription("Buy, inspect and refund your keys")
    .addSubcommand((sub) =>
      sub
        .setName("list")
        .setDescription("List keys you have issued")
        .addStringOption((option) =>
          option.setName("filter").setDescription("Which keys to show").addChoices(...FILTERS)
        )
        .addStringOption((option) =>
          option.setName("search").setDescription("Match a key code or customer username")
        )
        .addIntegerOption((option) =>
          option
            .setName("limit")
            .setDescription("How many to show (1-25, default 15)")
            .setMinValue(1)
            .setMaxValue(25)
        )
    )
    .addSubcommand((sub) =>
      sub
        .setName("buy")
        .setDescription("Buy new keys against the partner balance")
        .addStringOption((option) =>
          option
            .setName("plan")
            .setDescription("Which plan to buy")
            .setRequired(true)
            .setAutocomplete(true)
        )
        .addIntegerOption((option) =>
          option
            .setName("count")
            .setDescription("How many keys (1-25, default 1)")
            .setMinValue(1)
            .setMaxValue(25)
        )
    )
    .addSubcommand((sub) =>
      sub
        .setName("info")
        .setDescription("Look up a single key")
        .addStringOption((option) =>
          option.setName("code").setDescription("The key code").setRequired(true)
        )
    )
    .addSubcommand((sub) =>
      sub
        .setName("refund")
        .setDescription("Refund an unredeemed key back to your balance")
        .addStringOption((option) =>
          option.setName("code").setDescription("The key code").setRequired(true)
        )
    ),

  scopes: {
    list: "keys.read",
    info: "keys.read",
    buy: "keys.buy",
    refund: "keys.refund",
  },

  async autocomplete({ interaction, api }) {
    let choices = [];
    try {
      const result = await api.plans();
      choices = (result.data ?? []).map((plan) => ({
        name: `${plan.label} - ${money(plan.your_price_usd)} (${plan.id})`.slice(0, 100),
        value: plan.id,
      }));
    } catch {
      choices = [];
    }

    const typed = (interaction.options.getFocused() ?? "").toLowerCase();
    const filtered = typed
      ? choices.filter((c) => c.value.toLowerCase().includes(typed) || c.name.toLowerCase().includes(typed))
      : choices;

    await interaction.respond(filtered.slice(0, 25));
  },

  async run(ctx) {
    const sub = ctx.interaction.options.getSubcommand();
    if (sub === "list") return listKeys(ctx);
    if (sub === "buy") return buyKeys(ctx);
    if (sub === "info") return keyInfo(ctx);
    if (sub === "refund") return refundKey(ctx);
  },
};

async function listKeys({ interaction, api }) {
  const filter = interaction.options.getString("filter") ?? "all";
  const search = interaction.options.getString("search") ?? undefined;
  const limit = interaction.options.getInteger("limit") ?? 15;

  const result = await api.listKeys({ filter, search, limit });
  const rows = result.data ?? [];

  if (!rows.length) {
    await interaction.editReply({ content: "No keys matched that." });
    return;
  }

  const view = embed(`Keys - ${FILTER_LABEL[filter] ?? "everything"}`, BRAND)
    .setDescription(rows.map(keyLine).join("\n"))
    .setFooter({ text: `${rows.length} shown` });

  await interaction.editReply({ embeds: [view] });
}

async function buyKeys({ interaction, api, log }) {
  const plan = interaction.options.getString("plan", true);
  const count = interaction.options.getInteger("count") ?? 1;

  const planList = await api.plans();
  const chosen = (planList.data ?? []).find((p) => p.id === plan);

  if (!chosen) {
    await interaction.editReply({
      content: `There is no plan called \`${plan}\`. Run \`/plans\` to see what is available.`,
    });
    return;
  }

  const total = Math.round(chosen.your_price_usd * count * 100) / 100;
  const balance = await api.balance();

  if (Number(balance.balance_usd) < total) {
    await interaction.editReply({
      embeds: [
        embed("Not enough balance", BAD).setDescription(
          `${count} × ${chosen.label} costs ${money(total)} but the account only has ${money(
            balance.balance_usd
          )}.`
        ),
      ],
    });
    return;
  }

  const preview = embed("Confirm this purchase", WARN).setDescription(
    `**${count} × ${chosen.label}** (${chosen.days} days)\n` +
      `${money(chosen.your_price_usd)} each · **${money(total)}** total\n` +
      `Balance after: ${money(Number(balance.balance_usd) - total)}`
  );

  const go = await confirm(interaction, { view: preview, confirmLabel: `Buy for ${money(total)}` });
  if (!go) {
    await interaction.editReply({
      embeds: [embed("Cancelled", BRAND).setDescription("No keys were bought.")],
      components: [],
    });
    return;
  }

  const bought = await api.buyKeys(plan, count);
  const codes = (bought.data ?? []).map((k) => k.code);

  const done = embed(`Bought ${codes.length} key${codes.length === 1 ? "" : "s"}`, GOOD)
    .setDescription(codeBlock(codes.join("\n")))
    .addFields(
      { name: "Spent", value: money(bought.spent_usd), inline: true },
      { name: "Balance", value: money(bought.balance_usd), inline: true }
    );

  await interaction.editReply({ embeds: [done], components: [] });
  await log(
    `**${interaction.user.tag}** bought ${codes.length} × ${chosen.label} for ${money(bought.spent_usd)}`
  );
}

async function keyInfo({ interaction, api }) {
  const code = interaction.options.getString("code", true).trim();
  const key = await api.getKey(code);

  const view = embed(`Key ${key.code}`, BRAND).addFields(
    { name: "State", value: stateLabel(key.state), inline: true },
    { name: "Product", value: `${key.days}d ${key.product}`, inline: true },
    { name: "Cost", value: money(key.cost_usd), inline: true },
    { name: "Created", value: isoStamp(key.created_at), inline: true },
    { name: "Redeemed", value: key.redeemed_at ? stamp(key.redeemed_at) : "not yet", inline: true },
    { name: "Expires", value: key.expires_at ? stamp(key.expires_at) : "n/a", inline: true }
  );

  if (key.customer) {
    view.addFields({
      name: "Customer",
      value: `${key.customer.username} (id ${key.customer.id})`,
    });
  }

  await interaction.editReply({ embeds: [view] });
}

async function refundKey({ interaction, api, log }) {
  const code = interaction.options.getString("code", true).trim();
  const key = await api.getKey(code);

  if (key.state !== "unused") {
    await interaction.editReply({
      embeds: [
        embed("Cannot refund that", BAD).setDescription(
          "Only keys still in stock can be refunded. That one has already been redeemed."
        ),
      ],
    });
    return;
  }

  const preview = embed("Confirm this refund", WARN).setDescription(
    `\`${key.code}\` · ${key.days}d ${key.product}\n` +
      `This destroys the key and puts **${money(key.cost_usd)}** back on the balance.\n` +
      "It cannot be undone and the code will stop working immediately."
  );

  const go = await confirm(interaction, {
    view: preview,
    confirmLabel: `Refund ${money(key.cost_usd)}`,
    danger: true,
  });
  if (!go) {
    await interaction.editReply({
      embeds: [embed("Cancelled", BRAND).setDescription("The key was left alone.")],
      components: [],
    });
    return;
  }

  const result = await api.refundKey(code);
  const done = embed("Refunded", GOOD)
    .setDescription(`\`${result.code}\` is gone.`)
    .addFields(
      { name: "Returned", value: money(result.refunded_usd), inline: true },
      { name: "Balance", value: money(result.balance_usd), inline: true }
    );

  await interaction.editReply({ embeds: [done], components: [] });
  await log(`**${interaction.user.tag}** refunded \`${result.code}\` for ${money(result.refunded_usd)}`);
}
