import { SlashCommandBuilder } from "discord.js";
import { BRAND, embed, isoStamp, money } from "../format.js";

const KIND_LABEL = {
  topup: "Top-up",
  purchase: "Keys bought",
  refund: "Refund",
  adjust: "Adjustment",
};

export const balance = {
  data: new SlashCommandBuilder()
    .setName("balance")
    .setDescription("Show the partner balance and how to top it up"),
  scopes: "billing.read",
  async run({ interaction, api }) {
    const b = await api.balance();
    const view = embed("Balance", BRAND)
      .addFields(
        { name: "Available", value: money(b.balance_usd), inline: true },
        { name: "Your discount", value: `${b.discount_pct}%`, inline: true }
      )
      .setDescription(
        b.topup
          ? `Top up between ${money(b.topup.min_usd)} and ${money(b.topup.max_usd)} at ${b.topup.url}`
          : "Top up from the partner panel."
      );
    await interaction.editReply({ embeds: [view] });
  },
};

export const ledger = {
  data: new SlashCommandBuilder()
    .setName("ledger")
    .setDescription("Recent movements on the partner balance")
    .addIntegerOption((option) =>
      option
        .setName("limit")
        .setDescription("How many entries to show (1-25, default 10)")
        .setMinValue(1)
        .setMaxValue(25)
    ),
  scopes: "billing.read",
  async run({ interaction, api }) {
    const limit = interaction.options.getInteger("limit") ?? 10;
    const result = await api.ledger(limit);
    const rows = result.data ?? [];

    if (!rows.length) {
      await interaction.editReply({ content: "Nothing on the ledger yet." });
      return;
    }

    const view = embed("Ledger", BRAND).setDescription(
      rows
        .map((entry) => {
          const amount = Number(entry.amount_usd);
          const sign = amount >= 0 ? "+" : "−";
          const label = KIND_LABEL[entry.kind] ?? entry.kind;
          return `${sign}${money(Math.abs(amount)).slice(1)} · **${label}** · ${isoStamp(
            entry.created_at
          )}\n${entry.note || "No note"} · balance after ${money(entry.balance_after_usd)}`;
        })
        .join("\n\n")
    );

    await interaction.editReply({ embeds: [view] });
  },
};
