from __future__ import annotations

import discord


class Confirm(discord.ui.View):
    def __init__(self, user_id: int, confirm_label: str, danger: bool = False) -> None:
        super().__init__(timeout=30)
        self.user_id = user_id
        self.value: bool | None = None

        self.yes.label = confirm_label
        self.yes.style = discord.ButtonStyle.danger if danger else discord.ButtonStyle.success

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "That confirmation is not yours.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = False
        await interaction.response.defer()
        self.stop()


async def ask(
    interaction: discord.Interaction,
    view_embed: discord.Embed,
    confirm_label: str = "Confirm",
    danger: bool = False,
) -> bool:
    view = Confirm(interaction.user.id, confirm_label, danger)
    await interaction.edit_original_response(embed=view_embed, view=view)
    await view.wait()

    if view.value is None:
        view_embed.set_footer(text="Timed out. Nothing was done.")
        await interaction.edit_original_response(embed=view_embed, view=None)

    return view.value is True
