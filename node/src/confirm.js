import { ActionRowBuilder, ButtonBuilder, ButtonStyle, ComponentType } from "discord.js";

const TIMEOUT_MS = 30_000;

export async function confirm(interaction, { view, confirmLabel = "Confirm", danger = false }) {
  const yes = new ButtonBuilder()
    .setCustomId("confirm")
    .setLabel(confirmLabel)
    .setStyle(danger ? ButtonStyle.Danger : ButtonStyle.Success);

  const no = new ButtonBuilder()
    .setCustomId("cancel")
    .setLabel("Cancel")
    .setStyle(ButtonStyle.Secondary);

  const row = new ActionRowBuilder().addComponents(yes, no);
  const message = await interaction.editReply({ embeds: [view], components: [row] });

  try {
    const press = await message.awaitMessageComponent({
      componentType: ComponentType.Button,
      time: TIMEOUT_MS,
      filter: (i) => i.user.id === interaction.user.id,
    });

    await press.deferUpdate();
    return press.customId === "confirm";
  } catch {
    await interaction
      .editReply({
        embeds: [view.setFooter({ text: "Timed out. Nothing was done." })],
        components: [],
      })
      .catch(() => {});
    return false;
  }
}
