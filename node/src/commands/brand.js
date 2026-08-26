import { SlashCommandBuilder } from "discord.js";
import { BRAND, embed } from "../format.js";

function linkLine(label, url, isPublic) {
  if (!url) return `**${label}** · not until your menu domain is live`;
  return `**${label}** · ${isPublic ? "public" : "sign in required"}\n${url}`;
}

export const brand = {
  data: new SlashCommandBuilder()
    .setName("brand")
    .setDescription("Read or change your white-label branding")
    .addSubcommand((s) => s.setName("show").setDescription("Show your branding and public links"))
    .addSubcommand((s) =>
      s
        .setName("set")
        .setDescription("Change your branding. Only the options you fill in are touched")
        .addStringOption((o) => o.setName("name").setDescription("Brand name, up to 48 characters"))
        .addStringOption((o) => o.setName("primary").setDescription("Brand colour, like #7c5cff"))
        .addStringOption((o) => o.setName("accent").setDescription("Second colour, like #22d3ee"))
        .addStringOption((o) => o.setName("store_url").setDescription("Where your Extend button goes"))
        .addBooleanOption((o) =>
          o.setName("public_features").setDescription("Let anyone open your features page")
        )
        .addBooleanOption((o) =>
          o.setName("public_guide").setDescription("Let anyone open your setup guide")
        )
    ),
  scopes: { show: "brand.read", set: "brand.write" },
  async run({ interaction, api }) {
    const sub = interaction.options.getSubcommand();

    if (sub === "set") {
      const patch = {};
      for (const field of ["name", "primary", "accent", "store_url"]) {
        const value = interaction.options.getString(field);
        if (value !== null) patch[field] = value;
      }
      for (const field of ["public_features", "public_guide"]) {
        const value = interaction.options.getBoolean(field);
        if (value !== null) patch[field] = value;
      }

      if (!Object.keys(patch).length) {
        await interaction.editReply({ content: "Fill in at least one option to change something." });
        return;
      }

      const saved = await api.updateBrand(patch);
      await interaction.editReply({
        embeds: [
          embed("Branding saved", BRAND).setDescription(
            `Changed ${Object.keys(patch).join(", ")}.\n\n` +
              `**${saved.name ?? "No name set"}**\n` +
              linkLine("Features", saved.features_url, saved.public_features) +
              "\n" +
              linkLine("Setup guide", saved.guide_url, saved.public_guide)
          ),
        ],
      });
      return;
    }

    const b = await api.brand();
    const view = embed("Your branding", BRAND)
      .setDescription(
        `**${b.name ?? "No name set"}**\n` +
          linkLine("Features", b.features_url, b.public_features) +
          "\n" +
          linkLine("Setup guide", b.guide_url, b.public_guide)
      )
      .addFields(
        { name: "Brand colour", value: b.primary ?? "not set", inline: true },
        { name: "Second colour", value: b.accent ?? "not set", inline: true },
        { name: "Logo", value: b.has_logo ? "uploaded" : "none", inline: true },
        { name: "Store link", value: b.store_url ?? "not set" }
      );

    await interaction.editReply({ embeds: [view] });
  },
};
