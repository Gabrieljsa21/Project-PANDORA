# -*- coding: utf-8 -*-
"""Bases de `discord.ui.View`/`Modal` do PANDORA. Toda View e todo Modal
do pacote herdam daqui, pra que uma exceção num callback vire uma
mensagem pro jogador e uma linha no log, em vez de só "Esta interação
falhou" sem pista nenhuma."""
import discord

from pandora.registro import log

MENSAGEM_ERRO_INTERACAO = (
    "Algo deu errado ao processar essa ação. Tente de novo; "
    "se continuar, avise quem cuida do bot."
)


async def avisar_erro_de_interacao(interaction, erro, origem):
    log.error(
        " [PANDORA] Erro em %s (user=%s)", origem, getattr(interaction.user, "id", "?"),
        exc_info=(type(erro), erro, erro.__traceback__),
    )
    try:
        if interaction.response.is_done():
            await interaction.followup.send(MENSAGEM_ERRO_INTERACAO, ephemeral=True)
        else:
            await interaction.response.send_message(MENSAGEM_ERRO_INTERACAO, ephemeral=True)
    except discord.HTTPException:
        pass  # interação expirada: o erro já está no log, não há mais onde avisar


class ViewPandora(discord.ui.View):
    async def on_error(self, interaction, error, item):
        rotulo = getattr(item, "label", None) or getattr(item, "placeholder", None) or type(item).__name__
        await avisar_erro_de_interacao(interaction, error, f"{type(self).__name__} / {rotulo}")


class ModalPandora(discord.ui.Modal):
    async def on_error(self, interaction, error):
        await avisar_erro_de_interacao(interaction, error, type(self).__name__)
