import { AttachmentBuilder, SlashCommandBuilder } from "discord.js";
import { BAD, BRAND, GOOD, WARN, chunk, embed, isoStamp } from "../format.js";

const REASONS = [
  { name: "Chargeback", value: "chargeback" },
  { name: "Payment dispute", value: "dispute" },
  { name: "Fraud report", value: "fraud" },
  { name: "Something else", value: "other" },
];

const REASON_LABEL = Object.fromEntries(REASONS.map((reason) => [reason.value, reason.name]));

const STATUS_LABEL = {
  pending: "Waiting for approval",
  approved: "Ready to download",
  declined: "Declined",
};

const STATUS_TONE = { pending: WARN, approved: GOOD, declined: BAD };

const ATTACH_LIMIT = 8 * 1024 * 1024;

function line(r) {
  return (
    `\`${r.ref}\` · **${r.customer?.username ?? "unknown"}** · \`${r.key}\`\n` +
    `${REASON_LABEL[r.reason] ?? r.reason} · ${STATUS_LABEL[r.status] ?? r.status} · ${isoStamp(r.created_at)}`
  );
}

function found(summary) {
  return [
    `${summary.website_sign_ins} website sign-ins · ${summary.loader_sign_ins} loader sign-ins`,
    `${summary.downloads} downloads · ${summary.game_sessions} game sessions`,
    `${summary.ip_addresses} IP addresses · ${summary.machines} machines · ${summary.active_days} active days`,
    summary.first_use ? `First use ${isoStamp(summary.first_use)} · last seen ${isoStamp(summary.last_seen)}` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

export const accountinfo = {
  data: new SlashCommandBuilder()
    .setName("accountinfo")
    .setDescription("A customer's account history, for chargebacks and disputes")
    .addSubcommand((sub) =>
      sub
        .setName("request")
        .setDescription("Ask for the account history of whoever redeemed a key")
        .addStringOption((option) =>
          option.setName("key").setDescription("A key from your stock that the customer redeemed").setRequired(true)
        )
        .addStringOption((option) =>
          option.setName("reason").setDescription("Why you need it").setRequired(true).addChoices(...REASONS)
        )
        .addStringOption((option) =>
          option.setName("reference").setDescription("Your order or dispute ID").setMaxLength(64)
        )
        .addStringOption((option) =>
          option.setName("note").setDescription("Anything we should know").setMaxLength(2000)
        )
    )
    .addSubcommand((sub) =>
      sub
        .setName("status")
        .setDescription("Check a request, and get the zip once it is approved")
        .addStringOption((option) =>
          option.setName("ref").setDescription("The ticket reference, like TKT-8H2QMD").setRequired(true)
        )
    )
    .addSubcommand((sub) =>
      sub
        .setName("list")
        .setDescription("Your recent requests")
        .addStringOption((option) =>
          option
            .setName("status")
            .setDescription("Narrow it down")
            .addChoices(
              { name: "all", value: "all" },
              { name: "pending", value: "pending" },
              { name: "approved", value: "approved" },
              { name: "declined", value: "declined" }
            )
        )
    ),

  scopes: {
    request: "accountinfo.request",
    status: "accountinfo.read",
    list: "accountinfo.read",
  },

  async run(ctx) {
    const sub = ctx.interaction.options.getSubcommand();
    if (sub === "request") return requestInfo(ctx);
    if (sub === "status") return infoStatus(ctx);
    return listInfo(ctx);
  },
};

async function requestInfo({ interaction, api, log }) {
  const made = await api.requestAccountInfo(
    {
      code: interaction.options.getString("key", true).trim(),
      reason: interaction.options.getString("reason", true),
      reference: interaction.options.getString("reference")?.trim() || undefined,
      note: interaction.options.getString("note")?.trim() || undefined,
    },
    `discord:${interaction.id}`
  );

  const view = embed("Request sent", WARN)
    .setDescription(
      `We check every request before the zip is made. Check on it with \`/accountinfo status ref:${made.ref}\`. ` +
        `Our replies show up in \`/tickets read ref:${made.ref}\`.`
    )
    .addFields(
      { name: "Reference", value: `\`${made.ref}\``, inline: true },
      { name: "Customer", value: made.customer?.username ?? "unknown", inline: true },
      { name: "Key", value: `\`${made.key}\``, inline: true }
    );

  await interaction.editReply({ embeds: [view] });
  await log(
    `**${interaction.user.tag}** asked for account info on ${made.customer?.username ?? "a customer"} (\`${made.ref}\`)`
  );
}

async function infoStatus({ interaction, api }) {
  const ref = interaction.options.getString("ref", true).trim().toUpperCase();
  const r = await api.getAccountInfo(ref);

  const view = embed(`Account info ${r.ref}`, STATUS_TONE[r.status] ?? BRAND).addFields(
    { name: "Status", value: STATUS_LABEL[r.status] ?? r.status, inline: true },
    { name: "Customer", value: r.customer?.username ?? "unknown", inline: true },
    { name: "Key", value: `\`${r.key}\``, inline: true },
    { name: "Reason", value: REASON_LABEL[r.reason] ?? r.reason, inline: true },
    { name: "Asked", value: isoStamp(r.created_at), inline: true }
  );
  if (r.reference) view.addFields({ name: "Your reference", value: r.reference, inline: true });
  if (r.status === "declined" && r.decline_reason) view.setDescription(r.decline_reason);
  if (r.summary) view.addFields({ name: "What we found", value: found(r.summary) });

  if (r.status !== "approved" || !r.download) {
    await interaction.editReply({ embeds: [view] });
    return;
  }

  if (Number(r.download.bytes) > ATTACH_LIMIT) {
    view.setDescription("The zip is too big to attach here. Download it from the ticket in the partner panel.");
    await interaction.editReply({ embeds: [view] });
    return;
  }

  const file = await api.downloadAccountInfo(ref);
  view.setFooter({ text: `SHA-256 ${file.sha256 ?? r.download.sha256}` });
  await interaction.editReply({ embeds: [view], files: [new AttachmentBuilder(file.data, { name: file.name })] });
}

async function listInfo({ interaction, api }) {
  const status = interaction.options.getString("status") ?? "all";
  const result = await api.listAccountInfo({ status, limit: 15 });
  const rows = result.data ?? [];

  if (!rows.length) {
    await interaction.editReply({ content: "No account info requests match that." });
    return;
  }

  await interaction.editReply({
    embeds: [embed(`Account info requests (${rows.length})`, BRAND).setDescription(chunk(rows.map(line))[0])],
  });
}
