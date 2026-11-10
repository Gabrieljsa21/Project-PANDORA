# -*- coding: utf-8 -*-
"""Loja (comprar, garantir raridade, itens, upgrades) e Trocas.

Parte de `pandora.paineis` (dividido por tela em 2026-11-10); de fora do
pacote, continuar usando `from pandora import paineis` e `paineis.<nome>`."""
import asyncio
import json
import re
import discord
from pandora import db
from pandora import batalha, economia, gacha, itens, torre
from pandora.ui_base import ModalPandora, ViewPandora
from pandora.paineis.comum import (
    _COR_HUB,
    _TETO_OPCOES_DROPDOWN_LOJA,
    _ViewConfirmar,
    _ViewEscolherAlvo,
    _descricao_personagem_dropdown,
    _descricao_personagem_livre_dropdown,
    _fmt_numero,
)
from pandora.paineis.personagem import (
    _sufixo_aviso_sem_classe,
)
from pandora.paineis.equipe import (
    _fluxo_comprar_item_view,
)


class ViewLoja(ViewPandora):
    """Painel da Loja (2026-08-29) - `/loja` deixa de existir como comando
    NESTA leva; alcançável só pelo botão 🛒 do hub. 3 ações de sempre
    (`/loja ver+comprar`, `/loja garantir`, `/loja upgrade`), cada uma
    reaproveitando as MESMAS funções de `db`/`economia` que os comandos
    antigos já chamavam."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        comprar = discord.ui.Button(label="Comprar", emoji="🛍️", style=discord.ButtonStyle.primary, row=0)
        comprar.callback = self._abrir_comprar
        self.add_item(comprar)
        garantir = discord.ui.Button(label="Garantir raridade", emoji="🎯", style=discord.ButtonStyle.primary, row=0)
        garantir.callback = self._abrir_garantir
        self.add_item(garantir)
        # Rolls e claims são recompensas automáticas da Progressão; não há
        # mais compra desses limites na Loja.
        # 🔥 Progressão Global da conta (2026-08-30, análise do usuário
        # Seção 7: "a loja também será uma das principais formas de
        # transformar WiShards em crescimento permanente") - SEM nível
        # máximo, mesmo espírito dos 2 upgrades acima (que perderam o teto
        # em 2026-09-03).
        treinamento = discord.ui.Button(label="Treinamento da Coleção", emoji="🏋️", style=discord.ButtonStyle.success, row=1)
        treinamento.callback = self._treinamento_global
        self.add_item(treinamento)
        potencial = discord.ui.Button(label="Maestria da Coleção", emoji="📊", style=discord.ButtonStyle.success, row=1)
        potencial.callback = self._potencial_colecao
        self.add_item(potencial)
        # 🔥 "Slot de Série Favorita" removido daqui (2026-09-06, pedido do
        # usuário: "Pode remover a opção de Slot de Serie Favorita na
        # loja") - duplicava o próprio botão "Comprar slot" já existente
        # dentro da tela "❤️ Séries Favoritas" (`_ViewSeriesFavoritas.
        # _comprar_slot`, mesmo preço/tabela), sem nenhuma vantagem extra;
        # o slot de Waifu nunca teve essa duplicata na Loja pra começar.
        # 🔥 Itens direto como botão, sem o "Itens" -> dropdown intermediário
        # (2026-09-03, pedido do usuário: "como temos poucos itens, pode
        # tirar eles de dentro do dropdown e por como botão direto na
        # loja") - `ITENS_LOJA` já exclui Roll/Claim Permanente (removidos
        # da Loja no mesmo pedido, ver `itens.ITENS_LOJA`), sobrando 5
        # itens - cabem numa linha só.
        for chave, dados in itens.ITENS_LOJA.items():
            botao_item = discord.ui.Button(label=dados["nome"][:80], style=discord.ButtonStyle.primary, row=2)
            botao_item.callback = _fluxo_comprar_item_view(self.guild_id, self.autor_id, chave)
            self.add_item(botao_item)

    async def _somente_autor(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.autor_id:
            await interaction.response.send_message("Essa loja não é sua.", ephemeral=True)
            return False
        return True

    async def _abrir_comprar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        view = _ViewEscolherRaridadeLoja(self, acao="comprar")
        await interaction.response.send_message("Escolha a raridade:", view=view, ephemeral=True)

    async def _abrir_garantir(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        view = _ViewEscolherRaridadeLoja(self, acao="garantir")
        await interaction.response.send_message("Escolha a raridade mínima garantida:", view=view, ephemeral=True)

    async def _upgrade(self, interaction: discord.Interaction):
        """Sem nível máximo (2026-09-03, pedido do usuário: "vamos remover
        limite de compra de upgrade de rolls e claims") - mesmo dropdown de
        "Treinamento Global"/"Potencial da Coleção", pula vários níveis de
        uma vez, já mostrando custo total + saldo."""
        if not await self._somente_autor(interaction):
            return
        nivel_atual = db.nivel_upgrade_rolls(self.guild_id, interaction.user.id)
        saldo = db.saldo_wishards(self.guild_id, interaction.user.id)

        async def _confirmar(interacao_confirmacao, alvo):
            ok, mensagem = db.comprar_upgrade_rolls_ate(self.guild_id, interacao_confirmacao.user.id, alvo)
            await interacao_confirmacao.response.edit_message(content=mensagem, view=None)

        async def _cancelar(interacao_cancelamento):
            await interacao_cancelamento.response.edit_message(content="Cancelado.", view=None)

        view = _ViewEscolherAlvo(
            "Upgrade de rolls", nivel_atual, nivel_atual + _TETO_OPCOES_DROPDOWN_LOJA,
            lambda alvo: db.custo_total_upgrade_rolls_ate(nivel_atual, alvo),
            "WiShards", _confirmar, _cancelar, saldo_atual=saldo,
        )
        await interaction.response.send_message("Escolha até qual nível de Upgrade de rolls ir:", view=view, ephemeral=True)

    async def _upgrade_claims(self, interaction: discord.Interaction):
        """Espelha `_upgrade` (rolls), mesmo pedido do usuário de remover o
        teto de nível (2026-09-03)."""
        if not await self._somente_autor(interaction):
            return
        nivel_atual = db.nivel_upgrade_claims(self.guild_id, interaction.user.id)
        saldo = db.saldo_wishards(self.guild_id, interaction.user.id)

        async def _confirmar(interacao_confirmacao, alvo):
            ok, mensagem = db.comprar_upgrade_claims_ate(self.guild_id, interacao_confirmacao.user.id, alvo)
            await interacao_confirmacao.response.edit_message(content=mensagem, view=None)

        async def _cancelar(interacao_cancelamento):
            await interacao_cancelamento.response.edit_message(content="Cancelado.", view=None)

        view = _ViewEscolherAlvo(
            "Upgrade de claims", nivel_atual, nivel_atual + _TETO_OPCOES_DROPDOWN_LOJA,
            lambda alvo: db.custo_total_upgrade_claims_ate(nivel_atual, alvo),
            "WiShards", _confirmar, _cancelar, saldo_atual=saldo,
        )
        await interaction.response.send_message("Escolha até qual nível de Upgrade de claims ir:", view=view, ephemeral=True)

    async def _treinamento_global(self, interaction: discord.Interaction):
        """Progressão Global (2026-08-30) - +CP FIXO por personagem, SEM
        nível máximo (`db.comprar_treinamento_global_ate`). Dropdown pra
        pular vários níveis de uma vez (mesmo dia, pedido do usuário: "tbm
        tem de permitr comprar varios leveis por vez, tbm informando
        custo e qnt possuo") - sem teto natural de nível, então as opções
        vão até `_TETO_OPCOES_DROPDOWN_LOJA` (25, o máximo que um select
        do Discord aceita)."""
        if not await self._somente_autor(interaction):
            return
        estado = db.progressao_conta(self.guild_id, interaction.user.id)
        nivel_atual = estado["nivel_treinamento_global"]
        # 🔥 Desconto por Nível de Progressão (2026-09-06) - calculado 1x
        # aqui fora do dropdown (nunca dentro do lambda por opção), pra
        # preview bater exatamente com o que `comprar_treinamento_global_
        # ate` vai cobrar de verdade.
        desconto = db.desconto_por_nivel_progressao(estado["nivel"])
        saldo = db.saldo_wishards(self.guild_id, interaction.user.id)

        async def _confirmar(interacao_confirmacao, alvo):
            ok, mensagem = db.comprar_treinamento_global_ate(self.guild_id, interacao_confirmacao.user.id, alvo)
            await interacao_confirmacao.response.edit_message(content=mensagem, view=None)

        async def _cancelar(interacao_cancelamento):
            await interacao_cancelamento.response.edit_message(content="Cancelado.", view=None)

        view = _ViewEscolherAlvo(
            "Treinamento da Coleção", nivel_atual, nivel_atual + _TETO_OPCOES_DROPDOWN_LOJA,
            lambda alvo: db.custo_total_treinamento_ate(nivel_atual, alvo, desconto),
            "WiShards", _confirmar, _cancelar, saldo_atual=saldo,
        )
        await interaction.response.send_message("Escolha até qual Nível de Treinamento da Coleção ir:", view=view, ephemeral=True)

    async def _potencial_colecao(self, interaction: discord.Interaction):
        """Progressão Global (2026-08-30) - +CP PERCENTUAL global, SEM
        nível máximo (`db.comprar_potencial_colecao_ate`) - mesmo dropdown
        de "Treinamento Global"."""
        if not await self._somente_autor(interaction):
            return
        estado = db.progressao_conta(self.guild_id, interaction.user.id)
        nivel_atual = estado["nivel_potencial_colecao"]
        desconto = db.desconto_por_nivel_progressao(estado["nivel"])
        saldo = db.saldo_wishards(self.guild_id, interaction.user.id)

        async def _confirmar(interacao_confirmacao, alvo):
            ok, mensagem = db.comprar_potencial_colecao_ate(self.guild_id, interacao_confirmacao.user.id, alvo)
            await interacao_confirmacao.response.edit_message(content=mensagem, view=None)

        async def _cancelar(interacao_cancelamento):
            await interacao_cancelamento.response.edit_message(content="Cancelado.", view=None)

        view = _ViewEscolherAlvo(
            "Maestria da Coleção", nivel_atual, nivel_atual + _TETO_OPCOES_DROPDOWN_LOJA,
            lambda alvo: db.custo_total_potencial_ate(nivel_atual, alvo, desconto),
            "WiShards", _confirmar, _cancelar, saldo_atual=saldo,
        )
        await interaction.response.send_message("Escolha até qual Nível de Maestria da Coleção ir:", view=view, ephemeral=True)


class _ViewEscolherRaridadeLoja(ViewPandora):
    """Select de raridade compartilhado por "Comprar" (1-5⭐) e "Garantir"
    (3-5⭐, mesmo teto de `db.PRECOS_GARANTIA`)."""

    def __init__(self, view_loja, acao):
        super().__init__(timeout=900)
        self._view_loja = view_loja
        self._acao = acao
        opcoes_raridade = range(1, 6) if acao == "comprar" else range(3, 6)
        select = discord.ui.Select(
            placeholder="Raridade...",
            options=[discord.SelectOption(label=gacha.estrelas_por_raridade(r), value=str(r)) for r in opcoes_raridade],
        )
        select.callback = self._selecionou
        self.add_item(select)

    async def _selecionou(self, interaction: discord.Interaction):
        raridade = int(interaction.data["values"][0])
        if self._acao == "garantir":
            await self._confirmar_garantir(interaction, raridade)
        else:
            # 🔥 Modal de busca por nome ANTES da lista (2026-09-03, pedido
            # do usuário: "Coloca para o comprar deixar escrever parte do
            # nome tbm, assim como foi na serie") - substitui o antigo
            # `_mostrar_personagens` direto (amostra ALEATÓRIA sempre, sem
            # jeito de procurar uma personagem específica).
            await interaction.response.send_modal(_ModalBuscarNomeLoja(self._view_loja, raridade))

    async def _confirmar_garantir(self, interaction: discord.Interaction, raridade):
        preco = db.PRECOS_GARANTIA[raridade]

        async def _confirmar(interacao_confirmacao: discord.Interaction):
            if db.debitar_wishards(self._view_loja.guild_id, interacao_confirmacao.user.id, preco, "loja_garantia", f"garantia {raridade}estrelas") is None:
                await interacao_confirmacao.response.edit_message(content=f"Custa {_fmt_numero(preco)} WiShards e você não tem o suficiente.", view=None)
                return
            db.definir_garantia(self._view_loja.guild_id, interacao_confirmacao.user.id, raridade)
            await interacao_confirmacao.response.edit_message(
                content=f"Garantido: seu próximo roll vai ser {raridade}⭐ ou mais (custou {_fmt_numero(preco)} WiShards).", view=None,
            )

        view = _ViewConfirmar(_confirmar)
        await interaction.response.edit_message(content=f"Garantir {raridade}⭐ custa {_fmt_numero(preco)} WiShards - confirma?", view=view)


class _ModalBuscarNomeLoja(ModalPandora, title="Comprar personagem"):
    """Busca por nome ANTES da lista da Loja (2026-09-03, pedido do
    usuário: "Coloca para o comprar deixar escrever parte do nome tbm,
    assim como foi na serie") - a Loja só mostrava uma AMOSTRA ALEATÓRIA
    de até 25 personagens livres da raridade escolhida (`db.personagens_
    livres_por_raridade`, `ORDER BY RANDOM()`) - impossível achar uma
    personagem ESPECÍFICA numa raridade com milhares de livres. Campo
    vazio mantém o comportamento de sempre (amostra aleatória)."""

    nome = discord.ui.TextInput(label="Nome (vazio = amostra aleatória)", required=False, max_length=100)

    def __init__(self, view_loja, raridade):
        super().__init__()
        self._view_loja = view_loja
        self._raridade = raridade

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        texto = str(self.nome).strip()
        permitir_nsfw = db.obter_configuracao_colecao(self._view_loja.guild_id)["nsfw_permitido"]
        if texto:
            personagens = await asyncio.to_thread(
                db.personagens_livres_por_raridade_e_nome, self._view_loja.guild_id, self._raridade, permitir_nsfw, texto, 25,
            )
        else:
            personagens = await asyncio.to_thread(
                db.personagens_livres_por_raridade, self._view_loja.guild_id, self._raridade, permitir_nsfw, 25,
            )
        if not personagens:
            mensagem = (
                f'Nenhuma personagem {gacha.estrelas_por_raridade(self._raridade)} livre parecida com "{texto}" nesse servidor.'
                if texto else economia.formatar_loja(self._raridade, personagens)
            )
            await interaction.edit_original_response(content=mensagem, view=None)
            return
        view = _ViewComprarPersonagem(self._view_loja, self._raridade, personagens)
        await interaction.edit_original_response(content=economia.formatar_loja(self._raridade, personagens), view=view)


class _ViewComprarPersonagem(ViewPandora):
    """Select final de "Comprar" - até 25 personagens livres dessa
    raridade (mesmo teto do Discord), `db.comprar_personagem` decide tudo
    (preço, corrida por quem paga primeiro, reembolso se perder).

    🔥 `gacha.comprar_com_revelacao` em vez de `db.comprar_personagem`
    direto (2026-09-03, pedido do usuário: "esses botoes tem q fazer
    exatamente o claim, definir clsse e tudo") - sem isso, uma personagem
    nunca reivindicada em nenhum servidor saía da Loja pra sempre sem
    classe (mesmo gap do Merge, nunca corrigido aqui)."""

    def __init__(self, view_loja, raridade, personagens):
        super().__init__(timeout=900)
        self._view_loja = view_loja
        self._personagens = personagens

        def _opcao(indice, p):
            texto, emoji = _descricao_personagem_livre_dropdown(p)
            return discord.SelectOption(label=p["nome"][:100], description=texto, value=str(indice), emoji=emoji)

        select = discord.ui.Select(
            placeholder=f"Comprar por {_fmt_numero(db.PRECOS_LOJA[raridade])} WiShards...",
            options=[_opcao(indice, p) for indice, p in enumerate(personagens)],
        )
        select.callback = self._comprar
        self.add_item(select)

    async def _comprar(self, interaction: discord.Interaction):
        personagem = self._personagens[int(interaction.data["values"][0])]
        # 🔥 `defer()` ANTES do `to_thread`/revelação de classe (2026-09-03)
        # - `gacha.comprar_com_revelacao` pode chamar a GAIA (webhook,
        # timeout de até 30s) quando a personagem nunca foi reivindicada
        # em nenhum servidor - mesma classe de bug de timeout já corrigida
        # várias vezes nesta sessão (defer sempre a 1ª linha).
        await interaction.response.defer()
        ok, mensagem, tem_classe = await gacha.comprar_com_revelacao(self._view_loja.guild_id, personagem["id"], interaction.user)
        if ok:
            mensagem += _sufixo_aviso_sem_classe(tem_classe)
        await interaction.edit_original_response(content=mensagem, view=None)


# 🔥 Sufixos aceitos de VOLTA na digitação (2026-09-04, pedido do usuário:
# "tem como colocar mascara de pontuação dentro das janelas q pedem
# numeros?") - Discord não dá nenhum jeito de mascarar a digitação num
# `discord.ui.TextInput` (é texto puro, sem controle nenhum do bot sobre
# como o cliente formata em tempo real) - a saída foi `_int_seguro`
# aceitar de volta os MESMOS formatos que `db.fmt_numero` já mostra na
# tela, em vez de exigir dígito puro.
_SUFIXOS_ENTRADA_NUMERO = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000, "Q": 1_000_000_000_000_000}


def _int_seguro(texto):
    """Aceita dígito puro de sempre ("1000000"), separador de milhar -
    ponto OU vírgula, tanto faz ("1.000.000"/"1,000,000") - e sufixo
    abreviado igual `db.fmt_numero` mostra ("75,1M"/"75.1M", igual o
    "você tem 75,1M WiShards" que já aparece no label do campo). Sufixos
    de 2 letras (AA/AB/...) não são aceitos aqui - pra esses casos raros,
    digitar o número completo continua funcionando. Texto vazio/inválido
    sempre cai em 0, nunca lança erro."""
    texto = (texto or "").strip().upper()
    if not texto:
        return 0
    sufixo = texto[-1] if texto[-1] in _SUFIXOS_ENTRADA_NUMERO else None
    corpo = texto[:-1] if sufixo else texto
    if sufixo:
        try:
            return int(round(float(corpo.replace(",", ".")) * _SUFIXOS_ENTRADA_NUMERO[sufixo]))
        except ValueError:
            return 0
    # 🔥 Sem sufixo, "." e "," só valem como separador de MILHAR (grupos
    # de exatamente 3 dígitos depois do primeiro) - nunca como ponto
    # decimal ("1.5" tem que falhar, não virar "15" silenciosamente).
    negativo = corpo.startswith("-")
    grupos = re.split(r"[.,]", corpo[1:] if negativo else corpo)
    if len(grupos) > 1 and any(not g.isdigit() or len(g) != 3 for g in grupos[1:]):
        return 0
    corpo = "".join(grupos)
    if not corpo.isdigit():
        return 0
    return -int(corpo) if negativo else int(corpo)


class _ViewEscolherAlvoTroca(ViewPandora):
    """Passo 1 de "🔄 Trocas" - escolher o outro jogador via
    `discord.ui.UserSelect` (nativo do Discord, sem listar membros na
    mão); passo 2/3 são selects de personagem (oferece/pede)."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        self._select = discord.ui.UserSelect(placeholder="Com quem você quer propor a troca?")
        self._select.callback = self._selecionou
        self.add_item(self._select)

    async def _selecionou(self, interaction: discord.Interaction):
        alvo = self._select.values[0]
        if alvo.id == interaction.user.id:
            await interaction.response.send_message("Não dá pra propor uma troca com você mesmo.", ephemeral=True)
            return
        # 🔥 `asyncio.to_thread` (2026-08-30, "GAIA não respondeu a tempo"
        # repetido - mesma causa de Auto-Party/Cidade/Personagem: buscar +
        # ordenar a coleção inteira via SQLite síncrono bloqueia o event
        # loop do bot inteiro, não só esta interação).
        def _buscar_ordenada():
            return torre.ordenar_por_power(
                db.colecao_do_usuario(self.guild_id, interaction.user.id), self.guild_id, interaction.user.id,
            )
        colecao_proponente = (await asyncio.to_thread(_buscar_ordenada))[:25]
        # 🔥 mesmo formato de dropdown do Party/Merge (2026-09-06, pedido do
        # usuário: "A lista dos personagens de troca... esta errado" - o
        # select de Trocas mostrava só nome+estrelas, nunca classe/CP/nível/
        # afinidade, diferente de todo outro select de personagem do pacote).
        contexto_lote = await asyncio.to_thread(torre._contexto_lote, self.guild_id, interaction.user.id)
        view = _ViewEscolherPersonagensTroca(
            self.guild_id, interaction.user.id, alvo, colecao_proponente, etapa="oferece", contexto_lote=contexto_lote,
        )
        await interaction.response.edit_message(content=f"Trocando com {alvo.mention} - escolha o que você OFERECE:", view=view)


class _ViewEscolherPersonagensTroca(ViewPandora):
    """Passo 2 (oferece) e 3 (pede) de "🔄 Trocas" (2026-08-29, pedido do
    usuário depois de eu ter feito isso com IDs digitados num Modal:
    "prefiro q seja um dropdown q permita escrever nome para pesquisar doq
    passar id, n decoro ids" + "coloca apenas personagens possuidos no
    dropdwon") - select nativo do Discord (já deixa digitar pra filtrar
    sozinho, sem precisar de busca customizada), populado só com o que a
    pessoa certa REALMENTE possui: coleção de quem propõe na etapa
    "oferece", coleção do ALVO na etapa "pede". `min_values=0` - trocar só
    WiShards sem nenhuma personagem é uma oferta válida (mesmo espírito de
    `/trocar propor` sem os parâmetros de personagem)."""

    def __init__(self, guild_id, proponente_id, alvo, colecao, etapa, oferece_ids=None, contexto_lote=None):
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.proponente_id = str(proponente_id)
        self.alvo = alvo
        self.etapa = etapa  # "oferece" ou "pede"
        self._colecao = colecao
        self._oferece_ids = oferece_ids or []
        rotulo = "OFERECE" if etapa == "oferece" else "PEDE"
        # 🔥 mesmo formato de dropdown do Party/Merge/"🔍 Personagem"
        # (2026-09-06, pedido do usuário: "A lista dos personagens de
        # troca... esta errado") - `dono_id` é quem POSSUI a coleção sendo
        # mostrada (proponente na etapa "oferece", alvo na "pede"), não
        # sempre o proponente.
        dono_id = self.proponente_id if etapa == "oferece" else str(alvo.id)

        def _opcao(indice, p):
            texto, emoji = _descricao_personagem_dropdown(p, guild_id, dono_id, contexto_lote)
            return discord.SelectOption(label=p["nome"][:100], description=texto[:100], value=str(indice), emoji=emoji)

        select = discord.ui.Select(
            placeholder=f"Personagens que você {rotulo} (opcional)...",
            min_values=0,
            max_values=min(25, len(colecao)) if colecao else 1,
            disabled=not colecao,
            options=[_opcao(indice, p) for indice, p in enumerate(colecao)]
            or [discord.SelectOption(label="(nenhuma personagem disponível)", value="-1")],
        )
        select.callback = self._selecionou
        self.add_item(select)
        pular = discord.ui.Button(label="Não escolher nenhuma", style=discord.ButtonStyle.secondary, row=1)
        pular.callback = self._pular
        self.add_item(pular)

    async def _avancar(self, interaction: discord.Interaction, ids_escolhidos):
        if self.etapa == "oferece":
            # 🔥 `asyncio.to_thread` (2026-08-30, "GAIA não respondeu a
            # tempo" repetido - mesma causa de Auto-Party/Cidade/Personagem).
            def _buscar_ordenada():
                return torre.ordenar_por_power(db.colecao_do_usuario(self.guild_id, self.alvo.id), self.guild_id, self.alvo.id)
            colecao_alvo = (await asyncio.to_thread(_buscar_ordenada))[:25]
            contexto_lote_alvo = await asyncio.to_thread(torre._contexto_lote, self.guild_id, self.alvo.id)
            proxima = _ViewEscolherPersonagensTroca(
                self.guild_id, self.proponente_id, self.alvo, colecao_alvo, etapa="pede", oferece_ids=ids_escolhidos,
                contexto_lote=contexto_lote_alvo,
            )
            await interaction.response.edit_message(content=f"Trocando com {self.alvo.mention} - agora escolha o que você PEDE:", view=proxima)
            return
        # etapa == "pede" -> falta só os 2 números de WiShards (nome/ID de
        # personagem NUNCA se digita nesse fluxo), mas antes do Modal
        # mostra o valor de loja de cada lado + o mínimo que uma conta de
        # BOT aceitaria (2026-09-02, pedido do usuário: "coloca o valor q
        # vale os personagens se fossem comprados na loja, e o valor
        # minimo q bot aceita") - Modal não tem como mostrar isso
        # calculado (é só campo de texto puro), por isso o passo extra.
        texto_valores = _texto_valores_troca(self.guild_id, self.proponente_id, self.alvo, self._oferece_ids, ids_escolhidos)
        await interaction.response.edit_message(
            content=f"Trocando com {self.alvo.mention}:\n{texto_valores}\n\nAgora clique pra definir os WiShards.",
            view=_ViewConfirmarValoresTroca(self.guild_id, self.proponente_id, self.alvo, self._oferece_ids, ids_escolhidos),
        )

    async def _selecionou(self, interaction: discord.Interaction):
        valores = [v for v in interaction.data["values"] if v != "-1"]
        ids = [self._colecao[int(indice)]["id"] for indice in valores]
        await self._avancar(interaction, ids)

    async def _pular(self, interaction: discord.Interaction):
        await self._avancar(interaction, [])


def _texto_valores_troca(guild_id, proponente_id, alvo, oferece_ids, pede_ids):
    """Valor de loja (`economia.valor_loja_personagens`) de cada lado da
    troca + seu saldo atual + (só quando o alvo é uma conta de BOT, única
    com regra de aceite automático) o mínimo em WiShards que faltaria pra
    ela aceitar, considerando já os personagens escolhidos - referência
    mostrada ANTES do Modal de WiShards (2026-09-02, pedido do usuário,
    incluindo o saldo depois: "tbm informa qnt vc tem disponivel")."""
    valor_oferece = economia.valor_loja_personagens(oferece_ids)
    valor_pede = economia.valor_loja_personagens(pede_ids)
    saldo = db.saldo_wishards(guild_id, proponente_id)
    linhas = [
        f"💰 Seu saldo atual: {_fmt_numero(saldo)} WiShards",
        f"🏪 Valor de loja do que você OFERECE: {_fmt_numero(valor_oferece)} WiShards",
        f"🏪 Valor de loja do que você PEDE: {_fmt_numero(valor_pede)} WiShards",
    ]
    if alvo.bot:
        limiar = valor_pede * economia.LIMIAR_TROCA_NPC
        faltam = max(0, limiar - valor_oferece)
        linhas.append(
            f"🤖 {alvo.mention} é uma conta de bot - só aceita se o total oferecido (WiShards + valor de "
            f"loja dos personagens) for pelo menos **{_fmt_numero(limiar)}** WiShards (10x o valor de loja do que você "
            f"pede). Contando só os personagens já escolhidos, faltam pelo menos **{_fmt_numero(faltam)}** WiShards."
        )
    return "\n".join(linhas)


class _ViewConfirmarValoresTroca(ViewPandora):
    """Passo extra entre escolher "pede" e o Modal de WiShards - só existe
    pra dar tempo de mostrar `_texto_valores_troca` antes de abrir o Modal
    (Modal em si não tem como calcular/mostrar nada, é só texto puro)."""

    def __init__(self, guild_id, proponente_id, alvo, oferece_ids, pede_ids):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.proponente_id = proponente_id
        self.alvo = alvo
        self._oferece_ids = oferece_ids
        self._pede_ids = pede_ids
        botao = discord.ui.Button(label="💰 Definir WiShards", style=discord.ButtonStyle.primary)
        botao.callback = self._abrir_modal
        self.add_item(botao)

    async def _abrir_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            _ModalWishardsTroca(self.guild_id, self.proponente_id, self.alvo, self._oferece_ids, self._pede_ids),
        )


class _ModalWishardsTroca(ModalPandora, title="Propor troca - WiShards"):
    """Último passo - só os 2 valores em WiShards continuam sendo texto
    (número é rápido de digitar; personagem nunca é, por isso os 2 passos
    de select acima)."""

    oferecer_wishards = discord.ui.TextInput(label="Você oferece (WiShards)", required=False, placeholder="0", default="0")
    pedir_wishards = discord.ui.TextInput(label="Você pede (WiShards)", required=False, placeholder="0", default="0")

    def __init__(self, guild_id, proponente_id, alvo, oferece_ids, pede_ids):
        super().__init__()
        self._guild_id = guild_id
        self._proponente_id = proponente_id
        self._alvo = alvo
        self._oferece_ids = oferece_ids
        self._pede_ids = pede_ids

    async def on_submit(self, interaction: discord.Interaction):
        status, mensagem, view = economia.criar_e_avaliar_troca(
            self._guild_id, self._proponente_id, self._alvo,
            self._oferece_ids, _int_seguro(str(self.oferecer_wishards)),
            self._pede_ids, _int_seguro(str(self.pedir_wishards)),
        )
        ephemeral = status in ("erro", "npc_recusada")
        # 🔥 `view=None` explícito quebra `send_message` (chama `.is_finished()`
        # sem checar None) - só passa `view=` quando existe de verdade.
        if view is not None:
            await interaction.response.send_message(mensagem, view=view, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(mensagem, ephemeral=ephemeral)


# ==========================================================================
# Batalha 5x5 com Aposta de Personagem (2026-09-01) - regra de negócio em
# `pandora.batalha` (motor puro); aqui só orquestra embed+View, mesmo
# contrato do resto deste módulo. Estado 100% no banco
# (`colecao_batalha_desafios`) - `ViewBatalhaHub` sempre reconstrói tudo
# fresco (mesmo padrão de `_ViewNivel`/`_ViewTorre`), então um restart do
# bot no meio de um desafio não trava ninguém nem perde WiShards.
# ==========================================================================

def _embed_batalha(desafio, autor_id):
    embed = discord.Embed(title="⚔️ Batalha 5x5", color=_COR_HUB)
    if desafio is None:
        embed.description = (
            "Nenhuma batalha ativa - desafie outro jogador (ou uma conta de bot da coleção) por uma "
            "personagem da coleção dele.\nVocê escolhe a formação na hora, só pela CATEGORIA de cada "
            "posição (DPS/Tank/Support) - o resultado é Jokenpô de categoria, nunca depende de CP nem "
            "de quantas personagens de cada tipo você possui."
        )
        return embed
    personagem = db.personagem_por_id(desafio["personagem_id"])
    papel = batalha.papel_do_jogador(desafio, autor_id)
    if desafio["status"] == "aguardando_defensor":
        if papel == "desafiante":
            embed.description = (
                f"⏳ Aguardando resposta pela sua reivindicação de **{personagem['nome']}** "
                f"({_fmt_numero(desafio['aposta_wishards'])} WiShards em risco)."
            )
        else:
            comp = batalha.composicao_ordem(json.loads(desafio["ordem_desafiante"]))
            embed.description = (
                f"⚔️ Sua **{personagem['nome']}** está sendo desafiada - "
                f"{_fmt_numero(desafio['aposta_wishards'])} WiShards em risco pro desafiante se você vencer.\n"
                f"Composição adversária: ⚔️ DPS {comp['DPS']} · 🛡️ Tank {comp['Tank']} · ✨ Support {comp['Support']} "
                f"(ordem oculta)."
            )
    return embed


def _membro_ou_none(guild, user_id):
    membro = guild.get_member(int(user_id))
    return membro.display_name if membro else f"Jogador {user_id}"


def _embed_resultado_final(desafio, personagem, nome_desafiante, nome_defensor, placar_a, placar_b, vencedor):
    if vencedor == "desafiante":
        descricao = (
            f"🏆 **{nome_desafiante} venceu!** **{personagem['nome']}** foi transferida - "
            f"{nome_defensor} NÃO recebeu os {_fmt_numero(desafio['aposta_wishards'])} WiShards apostados (a aposta some da economia)."
        )
    else:
        descricao = (
            f"🏆 **{nome_defensor} defendeu {personagem['nome']}!** "
            f"+{_fmt_numero(desafio['aposta_wishards'])} WiShards do desafiante."
        )
    embed = discord.Embed(title=f"⚔️ Resultado - {personagem['nome']}", description=descricao, color=_COR_HUB)
    embed.add_field(name="Placar final", value=f"{nome_desafiante} {placar_a} x {placar_b} {nome_defensor}", inline=False)
    return embed
