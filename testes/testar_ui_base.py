"""Erro em callback de View/Modal vira aviso pro jogador, não silêncio."""
import asyncio
import inspect

import discord

from pandora import consulta, economia, gacha, paineis, ui_base


class _Resposta:
    def __init__(self, ja_respondida):
        self._ja_respondida = ja_respondida
        self.enviadas = []

    def is_done(self):
        return self._ja_respondida

    async def send_message(self, texto, ephemeral=False):
        self.enviadas.append((texto, ephemeral))


class _Followup:
    def __init__(self):
        self.enviadas = []

    async def send(self, texto, ephemeral=False):
        self.enviadas.append((texto, ephemeral))


class _Interacao:
    def __init__(self, ja_respondida):
        self.response = _Resposta(ja_respondida)
        self.followup = _Followup()
        self.user = type("U", (), {"id": 123})()


def _disparar(ja_respondida):
    interacao = _Interacao(ja_respondida)

    async def rodar():
        view = ui_base.ViewPandora(timeout=None)
        await view.on_error(interacao, RuntimeError("falha de teste"), object())

    asyncio.run(rodar())
    return interacao


def testar_erro_antes_de_responder_usa_a_resposta_da_interacao():
    interacao = _disparar(ja_respondida=False)
    assert interacao.response.enviadas == [(ui_base.MENSAGEM_ERRO_INTERACAO, True)]
    assert interacao.followup.enviadas == []


def testar_erro_depois_do_defer_usa_followup():
    interacao = _disparar(ja_respondida=True)
    assert interacao.followup.enviadas == [(ui_base.MENSAGEM_ERRO_INTERACAO, True)]


def testar_todas_as_views_do_pacote_herdam_da_base():
    for modulo in (consulta, economia, gacha, paineis):
        for nome, classe in inspect.getmembers(modulo, inspect.isclass):
            if issubclass(classe, discord.ui.View):
                assert issubclass(classe, ui_base.ViewPandora), f"{modulo.__name__}.{nome}"
            if issubclass(classe, discord.ui.Modal):
                assert issubclass(classe, ui_base.ModalPandora), f"{modulo.__name__}.{nome}"
