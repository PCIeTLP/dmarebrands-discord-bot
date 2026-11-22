import { SlashCommandBuilder } from "discord.js";
import { BAD, BRAND, GOOD, WARN, clock, codeBlock, embed, isoStamp, money } from "../format.js";

const KIND_LABEL = {
  topup: "Top-up",
  purchase: "Keys bought",
  refund: "Refund",
  adjust: "Adjustment",
  payment: "Payment",
  usage: "Keys used",
};

function dueLine(invoice) {
  if (!invoice) return null;
  const state = invoice.stock_locked
    ? "unused credit keys are locked"
    : invoice.overdue
      ? "buying is paused"
      : `due ${isoStamp(invoice.due_at)}`;
  return `Invoice \`${invoice.number}\`: **${money(invoice.due_usd)}** still due, ${state}. Pay it with \`/invoice pay\`.`;
}

export const balance = {
  data: new SlashCommandBuilder()
    .setName("balance")
    .setDescription("Show the partner balance or credit and how to pay"),
  scopes: "billing.read",
  async run({ interaction, api }) {
    const b = await api.balance();
    const billing = b.billing ?? null;

    if (billing?.mode === "credit") {
      const view = embed("Monthly credit", billing.buying_paused ? WARN : BRAND)
        .addFields(
          { name: "Available", value: money(b.available_usd), inline: true },
          { name: "Credit limit", value: money(billing.credit_limit_usd), inline: true },
          { name: "Your discount", value: `${b.discount_pct}%`, inline: true },
          { name: "Unused stock on credit", value: money(billing.stock_usd), inline: true },
          { name: "Used, not paid yet", value: money(billing.used_unpaid_usd), inline: true },
          {
            name: "Next invoice",
            value: billing.period_ends_at ? isoStamp(billing.period_ends_at) : "not scheduled",
            inline: true,
          }
        )
        .setDescription(
          dueLine(billing.open_invoice) ??
            "Keys are charged when a customer redeems them, on the invoice issued on the 1st of each month."
        );
      await interaction.editReply({ embeds: [view] });
      return;
    }

    const view = embed("Balance", BRAND)
      .addFields(
        { name: "Available", value: money(b.balance_usd), inline: true },
        { name: "Your discount", value: `${b.discount_pct}%`, inline: true }
      )
      .setDescription(
        dueLine(billing?.open_invoice) ??
          (b.topup
            ? `Top up between ${money(b.topup.min_usd)} and ${money(b.topup.max_usd)} at ${b.topup.url}`
            : "Top up from the partner panel.")
      );
    await interaction.editReply({ embeds: [view] });
  },
};

const INVOICE_STATE = {
  open: "Unpaid",
  paid: "Paid",
};

function invoiceState(inv) {
  if (inv.status === "paid") return INVOICE_STATE.paid;
  if (inv.stock_locked) return "Keys locked";
  if (inv.overdue) return "Due";
  return INVOICE_STATE.open;
}

function invoiceTone(inv) {
  if (inv.status === "paid") return GOOD;
  if (inv.stock_locked) return BAD;
  return WARN;
}

function day(value) {
  return value ? String(value).slice(0, 10) : "?";
}

function lastDay(value) {
  const ms = Date.parse(value ?? "");
  return Number.isNaN(ms) ? "?" : new Date(ms - 1000).toISOString().slice(0, 10);
}

export const invoice = {
  data: new SlashCommandBuilder()
    .setName("invoice")
    .setDescription("Monthly credit invoices")
    .addSubcommand((sub) => sub.setName("list").setDescription("Your recent invoices"))
    .addSubcommand((sub) =>
      sub
        .setName("show")
        .setDescription("One invoice with its lines")
        .addStringOption((option) =>
          option.setName("number").setDescription("The invoice number, like INV-202611-K7QD").setRequired(true)
        )
    )
    .addSubcommand((sub) =>
      sub
        .setName("pay")
        .setDescription("Open a payment for what is still due on an invoice")
        .addStringOption((option) =>
          option.setName("number").setDescription("The invoice number, like INV-202611-K7QD").setRequired(true)
        )
        .addStringOption((option) =>
          option.setName("coin").setDescription("Which coin to pay with").setRequired(true).setAutocomplete(true)
        )
        .addNumberOption((option) =>
          option.setName("amount").setDescription("Pay part of it, from 20. Leave empty to pay everything due").setMinValue(1)
        )
    ),

  scopes: {
    list: "billing.read",
    show: "billing.read",
    pay: "billing.topup",
  },

  async autocomplete(ctx) {
    return topup.autocomplete(ctx);
  },

  async run(ctx) {
    const sub = ctx.interaction.options.getSubcommand();
    if (sub === "pay") return payInvoice(ctx);
    if (sub === "show") return showInvoice(ctx);
    return listInvoices(ctx);
  },
};

async function listInvoices({ interaction, api }) {
  const result = await api.invoices({ limit: 12 });
  const rows = result.data ?? [];
  if (!rows.length) {
    await interaction.editReply({ content: "No invoices yet." });
    return;
  }
  const view = embed("Invoices", BRAND).setDescription(
    rows
      .map(
        (inv) =>
          `\`${inv.number}\` · ${day(inv.period_start)} to ${lastDay(inv.period_end)} · ${money(inv.amount_usd)} · ${invoiceState(inv)}${
            inv.status === "open" ? ` · ${money(inv.due_usd)} due` : ""
          }`
      )
      .join("\n")
  );
  await interaction.editReply({ embeds: [view] });
}

async function showInvoice({ interaction, api }) {
  const number = interaction.options.getString("number", true).trim().toUpperCase();
  const inv = await api.getInvoice(number);
  const used = (inv.lines ?? []).filter((line) => line.kind === "usage");
  const view = embed(`Invoice ${inv.number}`, invoiceTone(inv))
    .addFields(
      { name: "Amount", value: money(inv.amount_usd), inline: true },
      { name: "Paid", value: money(inv.paid_usd), inline: true },
      { name: "Still due", value: money(inv.due_usd), inline: true },
      { name: "Period", value: `${day(inv.period_start)} to ${lastDay(inv.period_end)}`, inline: true },
      { name: "State", value: invoiceState(inv), inline: true },
      { name: "Due", value: isoStamp(inv.due_at), inline: true }
    )
    .setDescription(
      used.length
        ? used
            .map((line) => `${line.qty} × ${line.duration ?? ""} ${line.product ?? ""} at ${money(line.unit_usd)} · ${money(Math.abs(line.amount_usd))}`)
            .join("\n")
        : "No keys used in this period."
    );
  await interaction.editReply({ embeds: [view] });
}

async function payInvoice({ interaction, api, log }) {
  const number = interaction.options.getString("number", true).trim().toUpperCase();
  const coin = interaction.options.getString("coin", true).trim().toLowerCase();
  const amount = interaction.options.getNumber("amount");
  const t = await api.payInvoice(number, coin, `discord:${interaction.id}`, amount ? Math.round(amount * 100) / 100 : null);
  await interaction.editReply({ embeds: [topupView(t, `Payment for ${number}`).setDescription(payment(t))] });
  await log(`**${interaction.user.tag}** opened a ${money(t.amount_usd)} payment for invoice ${number}`);
}

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

const STATE_LABEL = {
  waiting: "Waiting for payment",
  confirming: "Payment seen, confirming",
  partially_paid: "Part paid",
  paid: "Paid, crediting now",
  credited: "On your balance",
  expired: "Expired",
  failed: "Failed",
  refunded: "Refunded",
};

const STATE_TONE = {
  waiting: WARN,
  confirming: WARN,
  partially_paid: WARN,
  paid: GOOD,
  credited: GOOD,
  expired: BAD,
  failed: BAD,
  refunded: BAD,
};

function coinAmount(pay) {
  return `${pay.amount ?? "?"} ${String(pay.currency ?? "").toUpperCase()}`;
}

function payment(t) {
  const pay = t.pay ?? {};
  const lines = [`Send exactly **${coinAmount(pay)}** to`, codeBlock(pay.address ?? "no address yet")];
  if (pay.extra_id) lines.push(`Memo or tag: \`${pay.extra_id}\`. The payment needs it.`);
  if (t.expires_at) lines.push(`Pay before ${clock(t.expires_at)}.`);
  lines.push(`Or pay on the checkout page, with a QR code: ${t.checkout_url}`);
  return lines.join("\n");
}

function topupView(t, title) {
  return embed(title, STATE_TONE[t.state] ?? BRAND).addFields(
    { name: "Amount", value: money(t.amount_usd), inline: true },
    { name: "State", value: STATE_LABEL[t.state] ?? t.state, inline: true },
    { name: "Reference", value: `\`${t.ref}\``, inline: true }
  );
}

export const topup = {
  data: new SlashCommandBuilder()
    .setName("topup")
    .setDescription("Add money to the partner balance with crypto")
    .addSubcommand((sub) =>
      sub
        .setName("start")
        .setDescription("Open a payment for your balance")
        .addNumberOption((option) =>
          option
            .setName("amount")
            .setDescription("Dollars to add, 20 to 10000")
            .setRequired(true)
            .setMinValue(20)
            .setMaxValue(10000)
        )
        .addStringOption((option) =>
          option.setName("coin").setDescription("Which coin to pay with").setRequired(true).setAutocomplete(true)
        )
    )
    .addSubcommand((sub) =>
      sub
        .setName("status")
        .setDescription("Check where a top-up stands")
        .addStringOption((option) =>
          option.setName("ref").setDescription("The top-up reference").setRequired(true)
        )
    )
    .addSubcommand((sub) => sub.setName("list").setDescription("Your recent top-ups")),

  scopes: {
    start: "billing.topup",
    status: "billing.read",
    list: "billing.read",
  },

  async autocomplete({ interaction, api }) {
    const result = await api.coins();
    const typed = (interaction.options.getFocused() ?? "").toLowerCase();
    const coins = (result.data ?? [])
      .filter(
        (c) =>
          !typed ||
          [c.code, c.ticker, c.name, c.network].some((value) => String(value ?? "").toLowerCase().includes(typed))
      )
      .sort((a, b) => Number(b.popular) - Number(a.popular));

    await interaction.respond(
      coins.slice(0, 25).map((c) => ({
        name: `${c.ticker}${c.network ? ` on ${c.network}` : ""} · ${c.name}`.slice(0, 100),
        value: c.code,
      }))
    );
  },

  async run(ctx) {
    const sub = ctx.interaction.options.getSubcommand();
    if (sub === "start") return startTopup(ctx);
    if (sub === "status") return topupStatus(ctx);
    return listTopups(ctx);
  },
};

async function startTopup({ interaction, api, log }) {
  const amount = Math.round(interaction.options.getNumber("amount", true) * 100) / 100;
  const coin = interaction.options.getString("coin", true).trim().toLowerCase();
  const t = await api.startTopup(amount, coin, `discord:${interaction.id}`);

  await interaction.editReply({ embeds: [topupView(t, "Top-up opened").setDescription(payment(t))] });
  await log(
    `**${interaction.user.tag}** opened a ${money(t.amount_usd)} top-up in ${String(t.pay?.currency ?? coin).toUpperCase()}`
  );
}

async function topupStatus({ interaction, api }) {
  const ref = interaction.options.getString("ref", true).trim().toUpperCase();
  const t = await api.getTopup(ref);
  const view = topupView(t, `Top-up ${t.ref}`);

  if (t.state === "waiting" || t.state === "partially_paid") {
    view.setDescription(payment(t));
  } else if (t.state === "credited") {
    view.setDescription("The money is on your balance.");
  }
  view.addFields({ name: "Opened", value: isoStamp(t.created_at), inline: true });

  await interaction.editReply({ embeds: [view] });
}

async function listTopups({ interaction, api }) {
  const result = await api.topups(10);
  const rows = result.data ?? [];

  if (!rows.length) {
    await interaction.editReply({ content: "No top-ups yet. Start one with `/topup start`." });
    return;
  }

  const view = embed("Recent top-ups", BRAND).setDescription(
    rows
      .map(
        (t) =>
          `\`${t.ref}\` · ${money(t.amount_usd)} · ${STATE_LABEL[t.state] ?? t.state} · ${String(t.pay?.currency ?? "").toUpperCase()} · ${isoStamp(t.created_at)}`
      )
      .join("\n")
  );

  await interaction.editReply({ embeds: [view] });
}
