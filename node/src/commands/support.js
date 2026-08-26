import { SlashCommandBuilder } from "discord.js";
import { BAD, BRAND, GOOD, WARN, chunk, embed, isoStamp } from "../format.js";

const STATUS_TONE = { open: WARN, answered: GOOD, resolved: GOOD, closed: BRAND };
const CATEGORIES = ["billing", "technical", "account", "integration", "other"];
const PRIORITIES = ["low", "normal", "high", "urgent"];

function line(t) {
  const unread = t.unread ? " · unread reply" : "";
  return `\`${t.ref}\` · **${t.subject}**\n${t.status} · ${t.priority} · ${t.messages} message(s)${unread}\nLast activity ${isoStamp(t.last_message_at)}`;
}

export const tickets = {
  data: new SlashCommandBuilder()
    .setName("tickets")
    .setDescription("Your support threads with us")
    .addSubcommand((s) =>
      s
        .setName("list")
        .setDescription("List your tickets")
        .addStringOption((o) =>
          o
            .setName("status")
            .setDescription("Narrow it down")
            .addChoices(
              { name: "all", value: "all" },
              { name: "open", value: "open" },
              { name: "answered", value: "answered" },
              { name: "resolved", value: "resolved" },
              { name: "closed", value: "closed" }
            )
        )
        .addStringOption((o) => o.setName("search").setDescription("Match subject or reference"))
    )
    .addSubcommand((s) =>
      s
        .setName("read")
        .setDescription("Read one thread")
        .addStringOption((o) => o.setName("ref").setDescription("Ticket reference").setRequired(true))
    )
    .addSubcommand((s) =>
      s
        .setName("open")
        .setDescription("Open a new ticket")
        .addStringOption((o) => o.setName("subject").setDescription("Short subject").setRequired(true))
        .addStringOption((o) => o.setName("body").setDescription("What is going on").setRequired(true))
        .addStringOption((o) =>
          o
            .setName("category")
            .setDescription("Defaults to other")
            .addChoices(...CATEGORIES.map((c) => ({ name: c, value: c })))
        )
        .addStringOption((o) =>
          o
            .setName("priority")
            .setDescription("Defaults to normal")
            .addChoices(...PRIORITIES.map((p) => ({ name: p, value: p })))
        )
    )
    .addSubcommand((s) =>
      s
        .setName("reply")
        .setDescription("Reply to a thread")
        .addStringOption((o) => o.setName("ref").setDescription("Ticket reference").setRequired(true))
        .addStringOption((o) => o.setName("body").setDescription("Your message").setRequired(true))
    )
    .addSubcommand((s) =>
      s
        .setName("close")
        .setDescription("Close a thread you no longer need")
        .addStringOption((o) => o.setName("ref").setDescription("Ticket reference").setRequired(true))
    ),
  scopes: {
    list: "tickets.read",
    read: "tickets.read",
    open: "tickets.write",
    reply: "tickets.write",
    close: "tickets.write",
  },
  async run({ interaction, api }) {
    const sub = interaction.options.getSubcommand();
    const ref = (interaction.options.getString("ref") ?? "").trim().toUpperCase();

    if (sub === "list") {
      const result = await api.listTickets({
        status: interaction.options.getString("status") ?? undefined,
        search: interaction.options.getString("search") ?? undefined,
      });
      const rows = result.tickets ?? [];
      if (!rows.length) {
        await interaction.editReply({ content: "No tickets match that." });
        return;
      }
      const parts = chunk(rows.map(line));
      await interaction.editReply({
        embeds: [embed(`Tickets (${rows.length})`, BRAND).setDescription(parts[0])],
      });
      return;
    }

    if (sub === "read") {
      const t = await api.getTicket(ref);
      const thread = (t.thread ?? [])
        .map((m) => `**${m.role === "partner" ? m.author ?? "you" : "support"}** · ${isoStamp(m.created_at)}\n${m.body}`)
        .join("\n\n");
      const view = embed(`${t.ref} · ${t.subject}`, STATUS_TONE[t.status] ?? BRAND).setDescription(
        `${t.status} · ${t.priority} · ${t.category}\n\n${chunk([thread])[0] ?? "No messages yet."}`
      );
      await interaction.editReply({ embeds: [view] });
      return;
    }

    if (sub === "open") {
      const made = await api.createTicket({
        subject: interaction.options.getString("subject"),
        body: interaction.options.getString("body"),
        category: interaction.options.getString("category") ?? undefined,
        priority: interaction.options.getString("priority") ?? undefined,
      });
      await interaction.editReply({
        embeds: [
          embed("Ticket opened", GOOD).setDescription(
            `\`${made.ref}\` · **${made.subject}**\nWe will reply in this thread. Check it with \`/tickets read ref:${made.ref}\`.`
          ),
        ],
      });
      return;
    }

    if (sub === "reply") {
      const t = await api.replyTicket(ref, interaction.options.getString("body"));
      await interaction.editReply({
        embeds: [
          embed("Reply sent", GOOD).setDescription(`\`${t.ref ?? ref}\` now has ${t.messages ?? "more"} message(s).`),
        ],
      });
      return;
    }

    const closed = await api.closeTicket(ref);
    await interaction.editReply({
      embeds: [embed("Ticket closed", BAD).setDescription(`\`${closed.ref ?? ref}\` is closed.`)],
    });
  },
};

export const activity = {
  data: new SlashCommandBuilder()
    .setName("activity")
    .setDescription("Recent activity on your partner account")
    .addIntegerOption((o) =>
      o.setName("limit").setDescription("How many events, 1 to 200").setMinValue(1).setMaxValue(200)
    ),
  scopes: "activity.read",
  async run({ interaction, api }) {
    const result = await api.activity({
      limit: interaction.options.getInteger("limit") ?? 15,
    });
    const events = result.events ?? [];

    if (!events.length) {
      await interaction.editReply({ content: "Nothing has happened yet." });
      return;
    }

    const parts = chunk(
      events.map((e) => {
        const who = e.actor?.username ? ` by ${e.actor.username}` : "";
        const about = e.target?.username ? ` · ${e.target.username}` : "";
        return `\`${e.action}\`${who}${about}\n${isoStamp(e.created_at)}`;
      })
    );

    await interaction.editReply({
      embeds: [embed("Recent activity", BRAND).setDescription(parts[0])],
    });
  },
};
