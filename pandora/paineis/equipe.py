# -*- coding: utf-8 -*-
"""Formações de 5 slots (`ViewEquipe`): Party e Fusão.

Parte de `pandora.paineis` (dividido por tela em 2026-11-10); de fora do
pacote, continuar usando `from pandora import paineis` e `paineis.<nome>`."""
import asyncio
import discord
from pandora import db
from pandora import cidade, consulta, itens, series_favoritas, torre
from pandora.ui_base import ViewPandora
from pandora.paineis.comum import (
    _TETO_OPCOES_DROPDOWN_LOJA,
    _ViewEscolherAlvo,
    _ViewFiltrarCategoria,
    _ViewSelecionarPersonagem,
    _descricao_personagem_dropdown,
    _fmt_numero,
)


class ViewEquipe(ViewPandora):
    """Painel de Party (2026-08-29) - SEM `/party` nem `/pandora party`, só
    alcançável pelo botão 👥 Party do hub (mesmo modelo do `Grupos` do LA -
    zero comando raiz). `tipo` fixo em "party" - a Vitrine (que reaproveitava
    a MESMA tabela via `tipo="vitrine"`) foi REMOVIDA em 2026-09-03,
    substituída em espírito por 💖 Personagens Favoritas
    (`pandora.personagens_favoritas`) - `colecao_equipe` continua genérica
    por `tipo`, sem migração (linhas antigas com `tipo="vitrine"`, se
    existirem, ficam órfãs e inertes).

    🔥 SEM botão por slot numerado (2026-08-29, corrigido depois do
    usuário perguntar "ter q selecionar 1 por vez em cada slot tem alguma
    utilidade?") - conferi o `GruposPanel.cs` do LA de verdade: lá não
    existe conceito de slot NENHUM, é só adicionar/remover de um conjunto
    de até 5 (`grupos_add_sel`/`grupos_rem_sel`, cada um com 1 select).
    Como nada no ERIS hoje lê a POSIÇÃO da Party pra decidir algo (sem
    Torre/formação ainda - só o CONJUNTO de quem tá lá dentro importa pro
    bloqueio de Merge), copiei o modelo do LA: 2 botões (Adicionar/
    Remover), a coluna `posicao` do banco continua existindo por baixo
    (`db.definir_posicao_equipe` exige um número), só parou de aparecer
    na UI - a próxima posição LIVRE é escolhida sozinha."""

    def __init__(self, guild_id, autor_id, tipo="party", titulo="Sua Party", ao_fundir=None):
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        self.tipo = tipo
        self.titulo = titulo
        self._ao_fundir = ao_fundir
        self._montar()

    def _montar(self):
        self.clear_items()
        equipe = db.obter_equipe(self.guild_id, self.autor_id, self.tipo)
        cheio = len(equipe) >= db.MAX_POSICOES_EQUIPE
        adicionar = discord.ui.Button(label="Adicionar", emoji="➕", style=discord.ButtonStyle.success, disabled=cheio, row=0)
        adicionar.callback = self._abrir_adicionar
        self.add_item(adicionar)
        remover = discord.ui.Button(label="Remover", emoji="➖", style=discord.ButtonStyle.danger, disabled=not equipe, row=0)
        remover.callback = self._abrir_remover
        self.add_item(remover)
        limpar = discord.ui.Button(label="Limpar tudo", emoji="🗑️", style=discord.ButtonStyle.danger, disabled=not equipe, row=0)
        limpar.callback = self._limpar
        self.add_item(limpar)
        if self._ao_fundir is not None:
            fusao = discord.ui.Button(
                label="Fusão", emoji="🧬", style=discord.ButtonStyle.primary,
                disabled=not cheio, row=0,
            )
            fusao.callback = self._executar_fusao
            self.add_item(fusao)

    def formatar(self):
        equipe = db.obter_equipe(self.guild_id, self.autor_id, self.tipo)

        def linha(personagem):
            power, nivel, categoria = torre.power_personagem(personagem, self.guild_id, self.autor_id)
            icone = torre.icone_categoria(categoria)
            return f"{icone} - {consulta.linha_personagem(personagem)} · Nv.{nivel} · CP {_fmt_numero(power)}"

        texto = consulta.formatar_equipe(self.titulo, equipe, db.MAX_POSICOES_EQUIPE, formatador_linha=linha)
        if self._ao_fundir is not None and len(equipe) < db.MAX_POSICOES_EQUIPE:
            texto += "\n\nPreencha os 5 slots para liberar a Fusão."
        return texto

    async def _somente_autor(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.autor_id:
            await interaction.response.send_message("Esse painel não é seu.", ephemeral=True)
            return False
        return True

    async def _abrir_adicionar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        equipe = db.obter_equipe(self.guild_id, self.autor_id, self.tipo)
        vagas = db.MAX_POSICOES_EQUIPE - len(equipe)
        if vagas <= 0:
            await interaction.response.send_message(f"{self.titulo} já está cheia.", ephemeral=True)
            return
        ja_selecionados = {p["id"] for p in equipe.values()}
        candidatos = [p for p in db.colecao_do_usuario(self.guild_id, self.autor_id) if p["id"] not in ja_selecionados]
        if self._ao_fundir is not None:
            ids_party = {p["id"] for p in db.obter_equipe(self.guild_id, self.autor_id, "party").values()}
            candidatos = [p for p in candidatos if p["id"] not in ids_party]
            if equipe:
                raridade = next(iter(equipe.values()))["raridade"]
                candidatos = [p for p in candidatos if p["raridade"] == raridade]
        if not candidatos:
            await interaction.response.send_message("Você não tem mais nenhuma personagem compatível disponível.", ephemeral=True)
            return

        async def prosseguir(interaction_filtro: discord.Interaction, categoria):
            # 🔥 `defer()` ANTES de qualquer trabalho síncrono (2026-09-03,
            # achado do usuário: "Ao selecionar role da personagem p por
            # na pt, GAIA n responde a tempo") - mesma classe de bug
            # (trabalho bloqueante antes do 1º ack) já corrigida várias
            # vezes nesta sessão. Interação de Select vira `deferred_
            # message_update` (edita a MESMA mensagem do filtro) - `edit_
            # original_response` no lugar de `response.edit_message`/
            # `send_message` depois.
            await interaction_filtro.response.defer()
            # 🔥 1 SÓ `_contexto_lote` reaproveitado pros 3 passos - filtro,
            # ordenação e descrição do dropdown (2026-09-06, achado do
            # usuário: "apos colocar a role, demora um pouco p aparecer as
            # personagens daquela role") - antes, filtrar por categoria
            # chamava `torre.categoria_personagem(p)` (que faz sua PRÓPRIA
            # consulta `db.categoria_combate_da_classe`) UMA VEZ POR
            # PERSONAGEM candidata, mesmo repetindo a mesma classe centenas
            # de vezes (exatamente o padrão "44 Guerreiro = 44 conexões
            # SQLite idênticas" já identificado e corrigido em outros
            # pontos deste arquivo/`cidade.py`, nunca corrigido aqui) -
            # `ordenar_por_power` então abria OUTRA consulta em lote pra se
            # ordenar, e por fim uma 3ª só pra descrever o dropdown. Agora
            # é 1 consulta em lote só, reaproveitada nos 3 passos.
            contexto_lote = await asyncio.to_thread(torre._contexto_lote, self.guild_id, self.autor_id)
            if categoria is None:
                filtrados = candidatos
            else:
                cache_classe = contexto_lote[2]
                filtrados = [
                    p for p in candidatos
                    if cache_classe.get(p.get("classe"), (None, None, None))[1] == categoria
                ]
            # 🔥 ordena por CP ANTES de cortar em 25 (2026-08-30, pedido do
            # usuário: "Todo dropdwon q listar waifu, sempre ordene pelas
            # com maior CP/popularidade") - via thread (2026-08-30,
            # achado do usuário: "GAIA não respondeu a tempo" repetido,
            # mesma causa das outras varreduras de coleção inteira).
            filtrados = (await asyncio.to_thread(
                torre.ordenar_por_power, filtrados, self.guild_id, self.autor_id, contexto_lote,
            ))[:25]
            if not filtrados:
                await interaction_filtro.followup.send(f"Não há personagem compatível na role {categoria}.", ephemeral=True)
                return
            max_values = min(vagas, len(filtrados))
            if self._ao_fundir is not None and not equipe:
                max_values = 1
            view = _ViewSelecionarPersonagem(
                filtrados, f"Escolha até {max_values} personagem(ns)...", self._adicionar_selecionados,
                min_values=1, max_values=max_values,
                descricao=lambda p: _descricao_personagem_dropdown(p, self.guild_id, self.autor_id, contexto_lote),
            )
            await interaction_filtro.edit_original_response(content="Selecione:", view=view)

        # 🔥 EDIT da própria mensagem do painel, não uma nova (2026-08-30,
        # achado do usuário: "ao remover da party n atualiza os slots") -
        # antes o select abria como mensagem SEPARADA (`send_message`) e a
        # confirmação subsequente editava SÓ essa mensagem nova, nunca a do
        # painel original - o painel ficava com os slots antigos até o
        # usuário reabrir o hub. Agora é 1 mensagem só, editada em cada
        # etapa (mesmo padrão da Prova de Soulmate) - o filtro de role é só
        # mais uma etapa na mesma mensagem.
        view_filtro = _ViewFiltrarCategoria(prosseguir)
        await interaction.response.edit_message(
            content="Filtrar por role (opcional, ajuda a achar quem falta pro andar da Torre):", view=view_filtro,
        )

    async def _adicionar_selecionados(self, interaction: discord.Interaction, personagens):
        # 🔥 `defer()` ANTES do `to_thread` (2026-09-03, mesmo achado do
        # filtro de role acima: "GAIA n responde a tempo") - `cidade.
        # atualizar_snapshot_bonus`/`series_favoritas.recalcular_bonus`
        # são documentados como CARO (varrem a coleção inteira) e rodavam
        # ANTES de qualquer resposta à interação.
        await interaction.response.defer()
        equipe = db.obter_equipe(self.guild_id, interaction.user.id, self.tipo)
        vagas_livres = (posicao for posicao in range(1, db.MAX_POSICOES_EQUIPE + 1) if posicao not in equipe)
        for personagem in personagens:
            posicao = next(vagas_livres, None)
            if posicao is None:
                break
            db.definir_posicao_equipe(self.guild_id, interaction.user.id, self.tipo, posicao, personagem["id"])
        if self.tipo == "party":
            await asyncio.to_thread(cidade.atualizar_snapshot_bonus, self.guild_id, interaction.user.id)
            await asyncio.to_thread(series_favoritas.recalcular_bonus, self.guild_id, interaction.user.id)
        self._montar()
        await interaction.edit_original_response(content=self.formatar(), view=self)

    async def _abrir_remover(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        equipe = db.obter_equipe(self.guild_id, self.autor_id, self.tipo)
        if not equipe:
            await interaction.response.send_message("Sua Party está vazia.", ephemeral=True)
            return
        # 🔥 `defer()` ANTES do `to_thread` (2026-09-03) - `ordenar_por_
        # power`/`_contexto_lote` rodavam síncronos ANTES de responder.
        await interaction.response.defer()
        membros = await asyncio.to_thread(torre.ordenar_por_power, list(equipe.values()), self.guild_id, self.autor_id)
        contexto_lote = await asyncio.to_thread(torre._contexto_lote, self.guild_id, self.autor_id)
        view = _ViewSelecionarPersonagem(
            membros, f"Escolha quem remover de {self.titulo}...", self._remover_selecionados, min_values=1, max_values=len(membros),
            descricao=lambda p: _descricao_personagem_dropdown(p, self.guild_id, self.autor_id, contexto_lote),
        )
        await interaction.edit_original_response(content="Selecione:", view=view)

    async def _remover_selecionados(self, interaction: discord.Interaction, personagens):
        await interaction.response.defer()
        equipe = db.obter_equipe(self.guild_id, interaction.user.id, self.tipo)
        posicao_por_personagem_id = {p["id"]: posicao for posicao, p in equipe.items()}
        for personagem in personagens:
            posicao = posicao_por_personagem_id.get(personagem["id"])
            if posicao is not None:
                db.remover_posicao_equipe(self.guild_id, interaction.user.id, self.tipo, posicao)
        if self.tipo == "party":
            await asyncio.to_thread(cidade.atualizar_snapshot_bonus, self.guild_id, interaction.user.id)
            await asyncio.to_thread(series_favoritas.recalcular_bonus, self.guild_id, interaction.user.id)
        self._montar()
        await interaction.edit_original_response(content=self.formatar(), view=self)

    async def _limpar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        await interaction.response.defer()
        db.limpar_equipe(self.guild_id, self.autor_id, self.tipo)
        if self.tipo == "party":
            await asyncio.to_thread(cidade.atualizar_snapshot_bonus, self.guild_id, self.autor_id)
            await asyncio.to_thread(series_favoritas.recalcular_bonus, self.guild_id, self.autor_id)
        self._montar()
        await interaction.edit_original_response(content=self.formatar(), view=self)

    async def _executar_fusao(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        equipe = db.obter_equipe(self.guild_id, self.autor_id, self.tipo)
        if len(equipe) != db.MAX_POSICOES_EQUIPE:
            await interaction.response.send_message("Preencha os 5 slots antes de iniciar a Fusão.", ephemeral=True)
            return
        await self._ao_fundir(interaction, list(equipe.values()))

def _fluxo_comprar_item_view(guild_id, autor_id, chave):
    """Fábrica de callback pra comprar 1 item da Loja em quantidade (1-25) -
    extraído de `ViewLoja` (2026-09-06, pedido do usuário: "Coloca a opção
    comprar e usar Upgrade de Construção no painel da cidade") pra ser
    reaproveitado também por `ViewCidadeHub` (só o item "upgrade_
    construcao"), sem duplicar o dropdown de quantidade/preço total. Recebe
    `guild_id`/`autor_id` explícitos (em vez de `self`) porque as 2 views
    que chamam isso não têm nenhuma outra coisa em comum entre si."""
    dados = itens.CATALOGO_ITENS[chave]

    async def _callback(interaction: discord.Interaction):
        if str(interaction.user.id) != autor_id:
            await interaction.response.send_message("Esse painel não é seu.", ephemeral=True)
            return
        saldo = db.saldo_wishards(guild_id, interaction.user.id)

        async def _confirmar(interacao_confirmacao, quantidade):
            ok, mensagem = itens.comprar_item(guild_id, interacao_confirmacao.user.id, chave, quantidade)
            await interacao_confirmacao.response.edit_message(content=mensagem, view=None)

        async def _cancelar(interacao_cancelamento):
            await interacao_cancelamento.response.edit_message(content="Cancelado.", view=None)

        view = _ViewEscolherAlvo(
            "Quantidade", 0, _TETO_OPCOES_DROPDOWN_LOJA,
            lambda quantidade: itens.custo_total_item(guild_id, interaction.user.id, chave, quantidade),
            "WiShards", _confirmar, _cancelar, saldo_atual=saldo,
        )
        await interaction.response.send_message(
            f"{dados['nome']} - {dados['descricao']}\nEscolha a quantidade:", view=view, ephemeral=True,
        )
    return _callback


def _fluxo_usar_upgrade_construcao(guild_id, autor_id):
    """Fábrica de callback pra "Usar Upgrade de Construção" (escolhe a ÁREA,
    depois ATÉ QUAL NÍVEL subir, em lote) - extraído de `ViewInventarioHub.
    _usar_construcao` (2026-09-06, mesmo pedido acima) pra ser reaproveitado
    também por `ViewCidadeHub`, sem duplicar o fluxo de 2 passos."""
    async def _callback(interaction: discord.Interaction):
        if str(interaction.user.id) != autor_id:
            await interaction.response.send_message("Esse painel não é seu.", ephemeral=True)
            return
        teto = db.teto_atual_construcao(guild_id, autor_id)
        niveis = db.niveis_construcoes(guild_id, autor_id)
        select = discord.ui.Select(
            placeholder="Escolha a área...",
            options=[
                discord.SelectOption(label=f"{area} (Nível {niveis.get(area, 0)}/{teto})", value=area)
                for area in itens.AREAS_CONSTRUCAO
            ],
        )

        async def _callback_select(interacao_sel: discord.Interaction):
            area = interacao_sel.data["values"][0]
            nivel_atual = db.nivel_construcao(guild_id, interacao_sel.user.id, area)
            teto_atual = db.teto_atual_construcao(guild_id, interacao_sel.user.id)
            if nivel_atual >= teto_atual:
                await interacao_sel.response.edit_message(
                    content=f"{area} já está no teto atual (Nível {teto_atual}) - suba as outras áreas até lá pro teto aumentar.",
                    view=None,
                )
                return
            disponivel = db.quantidade_item(guild_id, interacao_sel.user.id, "upgrade_construcao")

            async def _confirmar(interacao_confirmacao, alvo):
                ok, mensagem = itens.usar_upgrade_construcao(
                    guild_id, interacao_confirmacao.user.id, area, alvo - nivel_atual,
                )
                if ok:
                    # 🔥 Achado ao implementar "Upar Construção" (2026-09-07) -
                    # este fluxo (item, de graça) nunca chamava isto, então o
                    # bônus de CP da Party só refletia o novo Nível de
                    # Construção na PRÓXIMA visita à Cidade, não na hora.
                    await asyncio.to_thread(cidade.atualizar_snapshot_bonus, guild_id, interacao_confirmacao.user.id)
                await interacao_confirmacao.response.edit_message(content=mensagem, view=None)

            async def _cancelar(interacao_cancelamento):
                await interacao_cancelamento.response.edit_message(content="Cancelado.", view=None)

            view_alvo = _ViewEscolherAlvo(
                area, nivel_atual, teto_atual, lambda alvo: alvo - nivel_atual,
                "Upgrade(s) de Construção", _confirmar, _cancelar, saldo_atual=disponivel,
            )
            await interacao_sel.response.edit_message(content=f"Escolha até qual Nível subir {area}:", view=view_alvo)

        select.callback = _callback_select
        view_select = ViewPandora(timeout=900)
        view_select.add_item(select)
        await interaction.response.send_message("Escolha onde aplicar o Upgrade de Construção:", view=view_select, ephemeral=True)
    return _callback


def _fluxo_upar_construcao_direto(guild_id, autor_id):
    """Fábrica de callback pra "Upar Construção" (paga WiShards DIRETO,
    sem item/Loja no meio - 2026-09-07, pedido do usuário: "Vamos tirar
    esse item da loja e permitir o jogador upar diretamente a
    construção") - mesmo fluxo de 2 passos de `_fluxo_usar_upgrade_
    construcao` (escolhe a ÁREA, depois até qual Nível), só troca
    "quantos itens tenho" por "quanto WiShards tenho" e `itens.
    usar_upgrade_construcao` por `itens.upar_construcao`."""
    async def _callback(interaction: discord.Interaction):
        if str(interaction.user.id) != autor_id:
            await interaction.response.send_message("Esse painel não é seu.", ephemeral=True)
            return
        teto = db.teto_atual_construcao(guild_id, autor_id)
        niveis = db.niveis_construcoes(guild_id, autor_id)
        areas_disponiveis = [
            area for area in itens.AREAS_CONSTRUCAO
            if niveis.get(area, 0) < teto
        ]
        select = discord.ui.Select(
            placeholder="Escolha a área...",
            options=[
                discord.SelectOption(label=f"{area} (Nível {niveis.get(area, 0)}/{teto})", value=area)
                for area in areas_disponiveis
            ],
        )

        async def _callback_select(interacao_sel: discord.Interaction):
            area = interacao_sel.data["values"][0]
            nivel_atual = db.nivel_construcao(guild_id, interacao_sel.user.id, area)
            teto_atual = db.teto_atual_construcao(guild_id, interacao_sel.user.id)
            if nivel_atual >= teto_atual:
                await interacao_sel.response.edit_message(
                    content=f"{area} já está no teto atual (Nível {teto_atual}) - suba as outras áreas até lá pro teto aumentar.",
                    view=None,
                )
                return
            saldo = db.saldo_wishards(guild_id, interacao_sel.user.id)

            async def _confirmar(interacao_confirmacao, alvo):
                ok, mensagem = itens.upar_construcao(
                    guild_id, interacao_confirmacao.user.id, area, alvo - nivel_atual,
                )
                if ok:
                    await asyncio.to_thread(cidade.atualizar_snapshot_bonus, guild_id, interacao_confirmacao.user.id)
                await interacao_confirmacao.response.edit_message(content=mensagem, view=None)

            async def _cancelar(interacao_cancelamento):
                await interacao_cancelamento.response.edit_message(content="Cancelado.", view=None)

            view_alvo = _ViewEscolherAlvo(
                area, nivel_atual, teto_atual, lambda alvo: itens.custo_total_construcao(nivel_atual, alvo - nivel_atual),
                "WiShards", _confirmar, _cancelar, saldo_atual=saldo,
            )
            await interacao_sel.response.edit_message(content=f"Escolha até qual Nível subir {area}:", view=view_alvo)

        select.callback = _callback_select
        view_select = ViewPandora(timeout=900)
        view_select.add_item(select)
        await interaction.response.send_message("Escolha onde upar - o preço é o mesmo pra todas as áreas, por faixa de 10 níveis:", view=view_select, ephemeral=True)
    return _callback
