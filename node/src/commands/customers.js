import { SlashCommandBuilder } from "discord.js";
import { BRAND, GOOD, WARN, embed, isoStamp, stamp } from "../format.js";
import { confirm } from "../confirm.js";

function machineLines(customer) {
  if (!customer.machines?.length) return "Nothing bound right now.";
  return customer.machines
    .map((m) => `**${m.scope}** — bound ${isoStamp(m.bound_at)} · last seen ${isoStamp(m.last_seen)}`)
    .join("\n");
}

export const customers = {
  data: new SlashCommandBuilder()
    .setName("customers")
    .setDescription("Look up the people who redeemed your keys")
    .addSubcommand((sub) =>
      sub
        .setName("list")
        .setDescription("List your customers")
        .addStringOption((option) =>
          option.setName("search").setDescription("Match a username")
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
        .setName("info")
        .setDescription("Look up one customer by id")
        .addIntegerOption((option) =>
          option.setName("id").setDescription("The customer id").setRequired(true).setMinValue(1)
        )
    ),

  scopes: {
    list: "customers.read",
    info: "customers.read",
  },

  async run(ctx) {
    const sub = ctx.interaction.options.getSubcommand();
    if (sub === "list") return listCustomers(ctx);
    if (sub === "info") return customerInfo(ctx);
  },
};

async function listCustomers({ interaction, api }) {
  const search = interaction.options.getString("search") ?? undefined;
  const limit = interaction.options.getInteger("limit") ?? 15;

  const result = await api.listCustomers({ search, limit });
  const rows = result.data ?? [];

  if (!rows.length) {
    await interaction.editReply({ content: "No customers matched that." });
    return;
  }

  const view = embed("Customers", BRAND)
    .setDescription(
      rows
        .map((c) => {
          const state = c.active ? `active until ${stamp(c.expires_at)}` : "expired";
          const bound = c.machines?.length ? ` · ${c.machines.length} machine(s)` : "";
          return `**${c.username}** (id ${c.id}) — ${state} · ${c.keys} key(s)${bound}`;
        })
        .join("\n")
    )
    .setFooter({ text: `${rows.length} shown` });

  await interaction.editReply({ embeds: [view] });
}

async function customerInfo({ interaction, api }) {
  const id = interaction.options.getInteger("id", true);
  const customer = await api.getCustomer(id);

  const view = embed(`Customer ${customer.username}`, customer.active ? GOOD : WARN)
    .addFields(
      { name: "Id", value: String(customer.id), inline: true },
      { name: "Access", value: customer.active ? "Active" : "Expired", inline: true },
      { name: "Keys redeemed", value: String(customer.keys), inline: true },
      { name: "Product", value: customer.product ?? "none", inline: true },
      {
        name: "Expires",
        value: customer.expires_at ? stamp(customer.expires_at) : "n/a",
        inline: true,
      },
      { name: "Joined", value: isoStamp(customer.created_at), inline: true }
    )
    .addFields({ name: "Machines", value: machineLines(customer) });

  await interaction.editReply({ embeds: [view] });
}

export const hwid = {
  data: new SlashCommandBuilder()
    .setName("hwid")
    .setDescription("Clear a customer's hardware lock so they can move machine")
    .addSubcommand((sub) =>
      sub
        .setName("key")
        .setDescription("Reset by key code")
        .addStringOption((option) =>
          option.setName("code").setDescription("The key they redeemed").setRequired(true)
        )
    )
    .addSubcommand((sub) =>
      sub
        .setName("customer")
        .setDescription("Reset by customer id")
        .addIntegerOption((option) =>
          option.setName("id").setDescription("The customer id").setRequired(true).setMinValue(1)
        )
    ),

  scopes: {
    key: "hwid.reset",
    customer: "hwid.reset",
  },

  async run(ctx) {
    const sub = ctx.interaction.options.getSubcommand();
    if (sub === "key") return resetByKey(ctx);
    if (sub === "customer") return resetByCustomer(ctx);
  },
};

async function resetByKey({ interaction, api, log }) {
  const code = interaction.options.getString("code", true).trim();
  const key = await api.getKey(code);

  if (!key.customer) {
    await interaction.editReply({
      embeds: [
        embed("Nobody to reset", WARN).setDescription(
          "That key has not been redeemed yet, so there is no machine bound to it."
        ),
      ],
    });
    return;
  }

  const preview = embed("Confirm this reset", WARN).setDescription(
    `This clears every hardware lock on **${key.customer.username}** (id ${key.customer.id}).\n` +
      "They will be able to bind a new machine on their next launch."
  );

  const go = await confirm(interaction, { view: preview, confirmLabel: "Reset machine" });
  if (!go) {
    await interaction.editReply({
      embeds: [embed("Cancelled", BRAND).setDescription("Nothing was cleared.")],
      components: [],
    });
    return;
  }

  const result = await api.resetByKey(code);
  await interaction.editReply({
    embeds: [
      embed("Machine reset", GOOD).setDescription(
        `Cleared ${result.cleared} lock${result.cleared === 1 ? "" : "s"} for **${key.customer.username}**.`
      ),
    ],
    components: [],
  });
  await log(`**${interaction.user.tag}** reset HWID for ${key.customer.username} via key \`${code}\``);
}

async function resetByCustomer({ interaction, api, log }) {
  const id = interaction.options.getInteger("id", true);
  const customer = await api.getCustomer(id);

  const preview = embed("Confirm this reset", WARN).setDescription(
    `This clears every hardware lock on **${customer.username}** (id ${customer.id}).\n` +
      "They will be able to bind a new machine on their next launch."
  );

  const go = await confirm(interaction, { view: preview, confirmLabel: "Reset machine" });
  if (!go) {
    await interaction.editReply({
      embeds: [embed("Cancelled", BRAND).setDescription("Nothing was cleared.")],
      components: [],
    });
    return;
  }

  const result = await api.resetByCustomer(id);
  await interaction.editReply({
    embeds: [
      embed("Machine reset", GOOD).setDescription(
        `Cleared ${result.cleared} lock${result.cleared === 1 ? "" : "s"} for **${customer.username}**.`
      ),
    ],
    components: [],
  });
  await log(`**${interaction.user.tag}** reset HWID for ${customer.username} (id ${id})`);
}
