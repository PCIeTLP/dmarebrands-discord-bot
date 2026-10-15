import { SlashCommandBuilder } from "discord.js";
import { BAD, BRAND, GOOD, WARN, chunk, clip, embed, isoStamp } from "../format.js";

const TONE = {
  undetected: GOOD,
  updating: WARN,
  offline: WARN,
  detected: BAD,
  discontinued: BAD,
};

const HEADLINE = {
  undetected: "Up and safe to use",
  updating: "Updating",
  offline: "Temporarily offline",
  detected: "Detected, tell people to stop",
  discontinued: "Discontinued",
};

export const status = {
  data: new SlashCommandBuilder()
    .setName("status")
    .setDescription("Show whether a product is up, and whether customer keys are frozen")
    .addStringOption((o) =>
      o.setName("product").setDescription("Limit it to one product, for example rust")
    ),
  scopes: "status.read",
  async run({ interaction, api }) {
    const wanted = interaction.options.getString("product") ?? undefined;
    const result = await api.status(wanted);
    const rows = result.products ?? [];

    if (!rows.length) {
      await interaction.editReply({ content: "No products came back." });
      return;
    }

    const worst = rows.find((p) => p.status !== "undetected") ?? rows[0];
    const view = embed("Product status", TONE[worst.status] ?? BRAND).setDescription(
      rows
        .map((p) => {
          const head = HEADLINE[p.status] ?? p.status;
          const beta = p.beta ? " · beta" : "";
          const frozen = p.frozen ? "\nKeys are frozen, so nobody is losing time." : "";
          const sale = p.sellable ? "" : "\nThis one cannot be sold any more.";
          const note = p.message ? `\n${p.message}` : "";
          const seen = p.updated_at ? `\nChanged ${isoStamp(p.updated_at)}` : "";
          return `**${p.label}** · ${head}${beta}${frozen}${sale}${note}${seen}`;
        })
        .join("\n\n")
    );

    await interaction.editReply({ embeds: [view] });
  },
};

const LANGUAGES = [
  { name: "English", value: "en" },
  { name: "Русский", value: "ru" },
  { name: "中文", value: "zh" },
];

export const changelog = {
  data: new SlashCommandBuilder()
    .setName("changelog")
    .setDescription("What changed in the latest loader and product releases")
    .addStringOption((o) =>
      o.setName("product").setDescription("loader, or a product such as rust. Leave it empty for all")
    )
    .addStringOption((o) => o.setName("language").setDescription("Language of the notes").addChoices(...LANGUAGES))
    .addIntegerOption((o) =>
      o.setName("limit").setDescription("How many releases (1-10, default 5)").setMinValue(1).setMaxValue(10)
    ),
  scopes: "status.read",
  async run({ interaction, api }) {
    const product = interaction.options.getString("product")?.trim().toLowerCase() || undefined;
    const lang = interaction.options.getString("language") ?? "en";
    const limit = interaction.options.getInteger("limit") ?? 5;
    const result = await api.changelogs({ product, lang, limit });
    const rows = result.data ?? [];

    if (!rows.length) {
      await interaction.editReply({ content: "No release notes yet." });
      return;
    }

    const entries = rows.map((r) => {
      const from = r.previous_version ? ` (from ${r.previous_version})` : "";
      const notes = r.notes ? clip(r.notes, 700) : "_No notes for this release._";
      return `**${r.label} ${r.version}**${from} · ${isoStamp(r.created_at)}\n${notes}\n`;
    });

    await interaction.editReply({ embeds: [embed("Release notes", BRAND).setDescription(chunk(entries)[0])] });
  },
};

export const updates = {
  data: new SlashCommandBuilder()
    .setName("updates")
    .setDescription("Show the latest game build and the recent patch notes")
    .addStringOption((o) =>
      o.setName("product").setDescription("Which game, rust or wardogs. Defaults to rust")
    ),
  scopes: "status.read",
  async run({ interaction, api }) {
    const wanted = interaction.options.getString("product") ?? undefined;
    const result = await api.updates(wanted);
    const build = result.current_build;
    const notes = (result.updates ?? []).slice(0, 5);

    const view = embed(`Game updates · ${result.game ?? wanted ?? "rust"}`, BRAND);
    view.setDescription(
      build
        ? `Current build **${build.buildid}**${build.at ? ` · ${isoStamp(build.at)}` : ""}` +
            (result.average_gap_days ? `\nUsually about ${result.average_gap_days} days between builds.` : "")
        : "No build information yet."
    );

    if (notes.length) {
      view.addFields({
        name: "Recent notes",
        value: notes.map((n) => `[${n.title}](${n.url}) · ${n.date}`).join("\n").slice(0, 1024),
      });
    }

    await interaction.editReply({ embeds: [view] });
  },
};
