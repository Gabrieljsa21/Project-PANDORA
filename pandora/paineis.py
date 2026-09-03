# -*- coding: utf-8 -*-
"""Painel-raiz `/pandora` (renomeado de `/waifu` em 2026-09-02, pedido do
usuário) do Colecionador (2026-08-29, pedido do usuário: "os
bots estão ficando muito poluídos" - inspirado no LegendsAwaken,
`C:\\Workspace\\LegendsAwaken`, projeto próprio dele). Reduz o Colecionador
de ~18 comandos raiz pra 1 hub com botões (embed + View editada/reenviada
na mesma conversa), no mesmo espírito do LA: 1 comando por sistema,
navegação depois via componente, sem subcomando.

Módulo NOVO dedicado a painel (mirror do `Panels/` do LA) - `gacha.py`/
`consulta.py`/`economia.py` continuam sendo a camada de dado/regra, SEM
mudança de lógica interna; aqui só orquestra embed+View a partir do que
elas já expõem. Cada botão do hub manda uma resposta NOVA (nunca edita a
mensagem do hub) - o hub continua clicável pra abrir outro sub-painel, sem
precisar de botão de "◀️ Voltar" nesta 1ª leva.

🔥 Fase 1 (aprovada, EM ANDAMENTO) - passo 1 (Rolar/Coleção) e passo 2
(Perfil/Wishlist) prontos; Party/Loja/Trocar/Ranking entram em passos
seguintes, ver o plano da sessão que criou isto. Os comandos antigos
equivalentes (`/colecao`, `/populares`, `/colecao_disponiveis`,
`/carteira`, `/ranking`, `/favoritar`, `/divorciar`, `/merge`,
`/wishlist`) continuam existindo até cada botão ser validado ao vivo -
`/pandora` é aditivo, não remove nada ainda."""
import asyncio
import json
import traceback
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import tasks

from pandora import db
from pandora import batalha, cidade, conquistas, consulta, economia, gacha, itens, series_favoritas, torre, worldboss

_COR_HUB = discord.Color(0xF1C40F)

_MODOS_COLECAO = [
    ("minha", "📚 Minha coleção"),
    ("populares", "🔥 Populares do catálogo"),
    ("disponiveis", "🎯 Disponíveis pra pegar"),
    # 🔥 2026-09-01, pedido do usuário: "outro emoji que coleta mas coloca
    # tag trade, permitir filtrar por tag depois" - lista quem foi
    # reivindicada pela reação 🔄 (`gacha.processar_reacao_claim`).
    ("tags_trade", "🏷️ Marcadas pra troca"),
]


def montar_embed_hub(guild, membro):
    """Absorve o que era o embed do painel "👤 Perfil" (2026-08-30, pedido
    do usuário: "botão de perfil é meio inutil, da p por todos os botoes e
    info dele ja no waifu") - WiShards/Coleção já mostrava, Favoritas/
    Ranking vieram de `montar_embed_perfil` (removido). "⭐ Favoritas"
    virou "💎 Soulstone" (mesmo dia, pedido do usuário: "No painel de
    waifu quero q informe qnts soulstones tenho tbm, substitua pelo campo
    Favoritas")."""
    saldo = db.saldo_wishards(guild.id, membro.id)
    colecao = db.colecao_do_usuario(guild.id, membro.id)
    soulstone = db.saldo_soulstone(guild.id, membro.id)
    # 🔥 `limite` bem acima de qualquer servidor real (escala pessoal) - só
    # assim dá pra achar a posição de QUALQUER um, não só do top 10 que
    # `db.ranking_guild` usa como default pro `/ranking` de sempre.
    ranking = db.ranking_guild(guild.id, limite=1_000_000)
    posicao = next(
        (indice + 1 for indice, linha in enumerate(ranking) if str(linha["dono_id"]) == str(membro.id)), None,
    )
    embed = discord.Embed(title=f"🎴 Pandora - {membro.display_name}", color=_COR_HUB)
    embed.add_field(name="💰 WiShards", value=str(saldo), inline=True)
    embed.add_field(name="📚 Coleção", value=f"{len(colecao)} personagem(ns)", inline=True)
    embed.add_field(name="💎 Soulstone", value=str(soulstone), inline=True)
    embed.add_field(name="🏆 Ranking do servidor", value=(f"#{posicao}" if posicao else "sem personagens ainda"), inline=True)
    # 🔥 Progressão Global da conta (2026-08-30, análise do usuário: "a
    # personagem possui um limite de desenvolvimento. A conta não") -
    # Nível SEM TETO, sempre visível aqui (mesmo espírito de mostrar
    # WiShards/Coleção direto no hub, sem precisar abrir outra tela).
    progressao = db.progressao_conta(guild.id, membro.id)
    xp_necessario = db.xp_necessario_nivel(progressao["nivel"])
    embed.add_field(
        name="📈 Progressão", value=f"Nível {progressao['nivel']} · {progressao['xp']}/{xp_necessario} XP", inline=True,
    )
    return embed


class ViewHubWaifu(discord.ui.View):
    """Painel-raiz de `/pandora` - restrito a quem abriu (`autor_id`), mesmo
    espírito de um menu pessoal (o LA também trata painéis de coleção como
    algo individual). `timeout=300` - tempo de sobra pra navegar sem
    precisar reabrir `/pandora` de novo."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        self._montar()

    def _montar(self):
        self.clear_items()
        rolar = discord.ui.Button(label="Rolar", emoji="🎲", style=discord.ButtonStyle.success, row=0)
        rolar.callback = self._rolar
        self.add_item(rolar)
        colecao = discord.ui.Button(label="Coleção", emoji="📚", style=discord.ButtonStyle.primary, row=0)
        colecao.callback = self._colecao
        self.add_item(colecao)
        # 🔥 Wishlist saiu daqui, virou botão dentro do "📖 Perfil"
        # (2026-09-02, pedido do usuário: "poe ela e a wishlist dentro do
        # perfil" - mesmo pedido do Ranking/Conquistas/Auto-claim antes).
        party = discord.ui.Button(label="Party", emoji="👥", style=discord.ButtonStyle.secondary, row=0)
        party.callback = self._party
        self.add_item(party)
        loja = discord.ui.Button(label="Loja", emoji="🛒", style=discord.ButtonStyle.secondary, row=1)
        loja.callback = self._loja
        self.add_item(loja)
        trocar = discord.ui.Button(label="Trocas", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
        trocar.callback = self._trocar
        self.add_item(trocar)
        # 🔥 Ranking saiu do hub, virou botão dentro do "📖 Perfil"
        # (2026-09-02, pedido do usuário: "Mover Auto-claim, Ranking,
        # Conquistas para dentro do perfil").
        torre = discord.ui.Button(label="Torre", emoji="🗼", style=discord.ButtonStyle.secondary, row=1)
        torre.callback = self._torre
        self.add_item(torre)
        ver = discord.ui.Button(label="Personagem", emoji="🔍", style=discord.ButtonStyle.secondary, row=1)
        ver.callback = self._ver
        self.add_item(ver)
        # 🔥 Botões do antigo painel "👤 Perfil" absorvidos direto no hub
        # (2026-08-30, pedido do usuário: "botão de perfil é meio inutil,
        # da p por todos os botoes e info dele ja no waifu") - Divorciar e
        # Favoritar NÃO vieram junto, mudaram pro card "🔍 Personagem"
        # (pedidos do mesmo usuário: "pode mover o divorciar para o lado
        # do upar nivel" e, depois, "move a funcao de favoritar para
        # entro da personagem").
        merge = discord.ui.Button(label="Merge", emoji="🔀", style=discord.ButtonStyle.primary, row=2)
        merge.callback = self._abrir_merge
        self.add_item(merge)
        # 🔥 "Prova de Soulmate" REMOVIDA (2026-08-30, Soulstone/Afinidade)
        # - Soulmate agora acontece via reencontro numa personagem já no
        # teto de Afinidade (`gacha._resolver_resultado`), não precisa
        # mais de tela própria. Só o botão saiu - `_abrir_prova_soulmate`/
        # `_prova_selecionada`/`_ViewEscolherRespostaProva`/
        # `_ViewEnfrentarProva`/`_embed_resultado_prova` ficam intactos e
        # dormentes (decisão do usuário: reaproveitar/decidir depois).
        # 🔥 Auto-claim (era "Auto-coleta") saiu do hub, virou botão dentro
        # do "📖 Perfil" (2026-09-02, mesmo pedido do Ranking acima).
        cidade_botao = discord.ui.Button(label="Cidade", emoji="🏙️", style=discord.ButtonStyle.secondary, row=2)
        cidade_botao.callback = self._cidade
        self.add_item(cidade_botao)
        batalha_botao = discord.ui.Button(label="PvP", emoji="⚔️", style=discord.ButtonStyle.danger, row=2)
        batalha_botao.callback = self._batalha
        self.add_item(batalha_botao)
        worldboss_botao = discord.ui.Button(label="World Boss", emoji="🐉", style=discord.ButtonStyle.danger, row=2)
        worldboss_botao.callback = self._worldboss
        self.add_item(worldboss_botao)
        inventario_botao = discord.ui.Button(label="Inventário", emoji="🎒", style=discord.ButtonStyle.secondary, row=3)
        inventario_botao.callback = self._inventario
        self.add_item(inventario_botao)
        # 🔥 Conquistas saiu do hub, virou botão dentro do "📖 Perfil"
        # (2026-09-02, mesmo pedido do Ranking acima).
        investir_botao = discord.ui.Button(label="Investir em Massa", emoji="📈", style=discord.ButtonStyle.secondary, row=3)
        investir_botao.callback = self._investir_em_massa
        self.add_item(investir_botao)
        reivindicar_tudo_botao = discord.ui.Button(label="Claim All", emoji="🎯", style=discord.ButtonStyle.success, row=3)
        reivindicar_tudo_botao.callback = self._reivindicar_tudo
        self.add_item(reivindicar_tudo_botao)
        bonus_classe_botao = discord.ui.Button(label="Classes", emoji="⚔️", style=discord.ButtonStyle.secondary, row=3)
        bonus_classe_botao.callback = self._bonus_classe
        self.add_item(bonus_classe_botao)
        diaria_ok = db.diaria_disponivel(self.guild_id, self.autor_id)
        diaria_botao = discord.ui.Button(
            label="Diária" if diaria_ok else "Diária ✓", emoji="🎁",
            style=discord.ButtonStyle.success if diaria_ok else discord.ButtonStyle.secondary, row=4,
        )
        diaria_botao.callback = self._diaria
        self.add_item(diaria_botao)
        perfil_botao = discord.ui.Button(label="Perfil", emoji="📖", style=discord.ButtonStyle.secondary, row=4)
        perfil_botao.callback = self._perfil
        self.add_item(perfil_botao)
        series_favoritas_botao = discord.ui.Button(label="Séries", emoji="❤️", style=discord.ButtonStyle.secondary, row=4)
        series_favoritas_botao.callback = self._series_favoritas
        self.add_item(series_favoritas_botao)

    async def _somente_autor(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.autor_id:
            await interaction.response.send_message("Esse painel não é seu - use `/pandora` pra abrir o seu.", ephemeral=True)
            return False
        return True

    async def _rolar(self, interaction: discord.Interaction):
        """🔥 Revertido de volta pra `quantidade=0` (2026-08-30, pedido
        direto do usuário: "qnd clico no rodar dentro do waifu, tem q
        rodar as 50, n apenas 1") - o `quantidade=1` (2026-08-29, achado
        de que 1 clique consumia o ciclo INTEIRO sem aviso) resolvia um
        problema real, mas o usuário decidiu que prefere o comportamento
        original mesmo assim: 1 clique rola tudo que sobrar no ciclo
        (`quantidade<=0` = "máximo disponível", `gacha.rolar_varios`)."""
        if not await self._somente_autor(interaction):
            return
        # 🔥 defer ANTES de chamar `rolar_varios`, não depois (2026-08-29,
        # mesmo bug corrigido em `_rolar_e_responder` de `eris/bot.py` -
        # o defer antigo vinha DEPOIS da chamada síncrona, então não
        # protegia contra o timeout de 3s do Discord de jeito nenhum).
        await interaction.response.defer()
        ok, resultado = await asyncio.to_thread(gacha.rolar_varios, self.guild_id, interaction.user.id, "ma", 0)
        if not ok:
            await interaction.followup.send(resultado, ephemeral=True)
            return
        await gacha.enviar_resultados(interaction, resultado)

    async def _colecao(self, interaction: discord.Interaction):
        """Manda uma mensagem NOVA (não edita o hub) - mesma visibilidade
        (pública) que `/colecao` já tem hoje, só que com o select de modo
        novo (Minha coleção/Populares/Disponíveis) por cima.

        🔥 `asyncio.to_thread` (2026-08-30, achado do usuário: "O Cidade e
        Personagem cai com frequencia nesse erro tbm [GAIA não respondeu a
        tempo]") - o modo padrão ("minha") ordena a coleção INTEIRA por CP
        (`torre.ordenar_por_power`), SQLite síncrono que bloquearia o
        event loop do bot inteiro se rodasse dentro de `ViewColecaoHub.
        __init__` (que é síncrono, `View.__init__` não pode ser `async`) -
        calculado AQUI antes de construir a View, pra rodar numa thread
        separada."""
        if not await self._somente_autor(interaction):
            return
        colecao_minha = await asyncio.to_thread(
            ViewColecaoHub.colecao_minha_ordenada, interaction.guild.id, interaction.user.id,
        )
        view = ViewColecaoHub(interaction.guild, interaction.user, colecao_minha_precomputada=colecao_minha)
        await interaction.response.send_message(view.formatar(), view=view)

    async def _party(self, interaction: discord.Interaction):
        """`/party` deixa de existir como comando (nem `/pandora party`) -
        alcançável SÓ por este botão, mesmo modelo do `Grupos` do LA (zero
        pegada no seletor `/`). Mesma visibilidade PÚBLICA que `/party ver`
        já tinha hoje - só as ações de editar (`_abrir_slot`/`_limpar`)
        continuam ephemeral, igual `/party definir`/`remover`/`limpar`."""
        if not await self._somente_autor(interaction):
            return
        view = ViewEquipe(self.guild_id, interaction.user.id)
        await interaction.response.send_message(view.formatar(), view=view)

    async def _loja(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        view = ViewLoja(self.guild_id, interaction.user.id)
        await interaction.response.send_message("🛒 **Loja** - escolha uma opção:", view=view, ephemeral=True)

    async def _trocar(self, interaction: discord.Interaction):
        """Peça mais arriscada da leva (ver plano) - "propor" vira 2
        passos: `discord.ui.UserSelect` (escolher o alvo, nativo do
        Discord) + `discord.ui.Modal` (termos da troca), em vez dos
        parâmetros de texto de `/trocar propor`. Aceitar/Recusar (`ViewTroca`)
        não muda nada - já era botão."""
        if not await self._somente_autor(interaction):
            return
        view = _ViewEscolherAlvoTroca(self.guild_id, interaction.user.id)
        await interaction.response.send_message("Escolha com quem propor a troca:", view=view, ephemeral=True)

    async def _diaria(self, interaction: discord.Interaction):
        """Recompensa Diária (2026-09-02, pedido do usuário - Seção 6/29
        do plano original: "eventual recompensa diária") - reset por dia
        de calendário UTC, não 24h rolantes. 🔥 2026-09-02 (pedido do
        usuário: "multiplicada os wishards pelo nivel da progressao. e da
        1 item raro") - WiShards escalam com `db.progressao_conta`
        (SEM TETO, cresce junto com a conta) + 1 item GARANTIDO
        (`itens.sortear_item_diario`, mesmos pesos do drop raro do World
        Boss, sem o portão de 15% - todo resgate dá exatamente 1)."""
        if not await self._somente_autor(interaction):
            return
        ok, novo_saldo, wishards = await asyncio.to_thread(db.reivindicar_diaria_com_recompensa, self.guild_id, interaction.user.id)
        if not ok:
            await interaction.response.send_message("🎁 Você já resgatou a Recompensa Diária hoje - volta amanhã!", ephemeral=True)
            return
        item_raro = await asyncio.to_thread(itens.sortear_item_diario)
        texto_item = await asyncio.to_thread(itens.conceder_item_drop, self.guild_id, interaction.user.id, item_raro)
        self._montar()
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"🎁 Recompensa Diária resgatada! +{wishards} WiShards (saldo: {novo_saldo}) · 🎁 {texto_item}",
            ephemeral=True,
        )

    async def _perfil(self, interaction: discord.Interaction):
        """Perfil redesenhado (2026-09-02, pedido do usuário em cima de uma
        sugestão externa endossada: "eu faria o /perfil como um resumo
        compacto no topo e, logo abaixo, uma tabela de progressão por
        raridade... eu não colocaria ⭐ 5★: 126 no cabeçalho, porque agora
        todas as raridades estarão detalhadas logo abaixo"). Substituiu de
        vez a lista de TODAS as séries tocadas (antigo `db.progresso_por_
        serie` no painel, função ainda existe mas não é mais usada aqui) -
        só as Séries Favoritas (`pandora.series_favoritas`, no máximo 25)
        aparecem agora, o resto vira "evitaria listar personagens... pra
        isso você pode ter comandos separados", cada raridade já resume o
        tamanho real da coleção.

        🔥 Ganhou botões (2026-09-02, pedido do usuário: "Mover Auto-claim,
        Ranking, Conquistas para dentro do perfil") - `_ViewPerfil`, saíram
        do hub raiz."""
        if not await self._somente_autor(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        embed = await asyncio.to_thread(_montar_embed_perfil, self.guild_id, interaction.user.id)
        view = _ViewPerfil(self.guild_id, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def _series_favoritas(self, interaction: discord.Interaction):
        """Gerenciar Séries Favoritas (2026-09-02) - até 25 slots (5 base +
        20 níveis de upgrade pagos, 2026-09-03), cada um com a série
        escolhida e o bônus de CP ativo pros personagens dela."""
        if not await self._somente_autor(interaction):
            return
        # 🔥 `defer()` ANTES do fetch caro (2026-09-02) - `_ViewSeriesFavoritas.
        # criar` já busca os slots (`series_favoritas.listar`, CARO - varre
        # a coleção inteira filtrada por série) via `to_thread` internamente,
        # SEM `to_thread` por fora (`criar` precisa terminar de CONSTRUIR a
        # View de volta na thread principal - ver docstring da classe pro
        # bug real que isso corrigiu: View construída inteira dentro de um
        # `to_thread` nunca recebe clique nenhum, silenciosamente).
        print(f" [SERIES] abrindo painel - guild={self.guild_id} user={interaction.user.id}")
        try:
            await interaction.response.defer(ephemeral=True)
            print(" [SERIES] defer() OK (abertura)")
            view = await _ViewSeriesFavoritas.criar(self.guild_id, interaction.user.id)
            await interaction.followup.send(view.formatar(), view=view, ephemeral=True)
            print(" [SERIES] painel enviado.")
        except Exception:
            print(" [SERIES] !!! EXCEÇÃO abrindo o painel !!!")
            traceback.print_exc()

    async def _torre(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        ok, erro, contexto = torre.preview_andar(self.guild_id, interaction.user.id)
        if not ok:
            await interaction.response.send_message(erro, ephemeral=True)
            return
        embed = _embed_torre(contexto)
        view = _ViewTorre(self.guild_id)
        await interaction.response.send_message(embed=embed, view=view)

    async def _ver(self, interaction: discord.Interaction):
        """Card completo (raridade/classe/série/foto/Nível) + upar Nível
        de UMA personagem específica (2026-08-30, pedido do usuário: "qnd
        eu coleto a personagem, mostra a raridade, classe e foto dela. Tem
        outra forma de ver isso?", depois "pode remover o botão de nivel,
        renomeie o ver para personagem e deixe apenas ele" - vira o ÚNICO
        jeito de ver/upar uma personagem, substitui o antigo "⬆️ Nível" do
        Perfil). Manda mensagem NOVA em vez de editar o hub (mesmo padrão
        de Coleção/Perfil/Party). Abre direto na posição 1 - navegar/pular
        pra qualquer posição vira trabalho do `_ViewNivel` (2026-09-02, ver
        docstring da classe)."""
        if not await self._somente_autor(interaction):
            return
        await interaction.response.defer()
        view = await _ViewNivel.criar(self.guild_id, interaction.user.id)
        if view is None:
            await interaction.followup.send("Você ainda não tem nenhuma personagem.", ephemeral=True)
            return
        await interaction.followup.send(embed=view.montar_embed(), view=view)

    async def _colecao_ate_25(self):
        # 🔥 ordena por CP ANTES de cortar em 25 (2026-08-30, pedido do
        # usuário: "Todo dropdwon q listar waifu, sempre ordene pelas com
        # maior CP/popularidade") - cortar primeiro e ordenar depois dava
        # só um recorte arbitrário (raridade/nome), nunca as 25 de maior CP.
        # `asyncio.to_thread` (2026-08-30, "Auto-party esta demorando... O
        # Cidade e Personagem cai com frequencia nesse erro tbm") - varrer
        # a coleção inteira é SQLite síncrono, bloquearia o event loop
        # inteiro do bot (não só este comando) enquanto roda.
        colecao = await asyncio.to_thread(db.colecao_do_usuario, self.guild_id, self.autor_id)
        colecao = await asyncio.to_thread(torre.ordenar_por_power, colecao, self.guild_id, self.autor_id)
        return colecao[:25]

    async def _abrir_merge(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        colecao = await self._colecao_ate_25()
        if len(colecao) < 5:
            await interaction.response.send_message("Você precisa de pelo menos 5 personagens pra fazer um Merge.", ephemeral=True)
            return
        contexto_lote = await asyncio.to_thread(torre._contexto_lote, self.guild_id, self.autor_id)
        view = _ViewSelecionarPersonagem(
            colecao, "Escolha EXATAMENTE 5 personagens da MESMA raridade...", self._merge_selecionado, min_values=5, max_values=5,
            descricao=lambda p: _descricao_personagem_dropdown(p, self.guild_id, self.autor_id, contexto_lote),
        )
        await interaction.response.send_message("Selecione:", view=view, ephemeral=True)

    async def _merge_selecionado(self, interaction: discord.Interaction, personagens, confirmar=False):
        """2026-09-02 (pedido do usuário: "ele vai deixar trocar 5 da msm
        raridade por 1 da msm raridade disponivel, a escolha") - só valida
        aqui (`economia.validar_merge`); a escolha de qual personagem
        disponível receber vira um 2º passo (`_ViewEscolherMergeAlvo`),
        `economia.executar_merge` só roda depois que o jogador escolhe."""
        ids = [p["id"] for p in personagens]
        ok, mensagem, raridade, precisa_confirmar = await asyncio.to_thread(
            economia.validar_merge, self.guild_id, interaction.user.id, ids, confirmar,
        )
        if precisa_confirmar:
            async def _confirmar(interacao_confirmacao):
                await self._merge_selecionado(interacao_confirmacao, personagens, confirmar=True)
            view = _ViewConfirmar(_confirmar)
            await interaction.response.edit_message(content=f"{mensagem} Confirma o Merge mesmo assim?", view=view)
            return
        if not ok:
            await interaction.response.edit_message(content=mensagem, view=None)
            return
        permitir_nsfw = await asyncio.to_thread(db.obter_configuracao_colecao, self.guild_id)
        disponiveis = await asyncio.to_thread(
            db.personagens_livres_por_raridade, self.guild_id, raridade, permitir_nsfw["nsfw_permitido"], 25,
        )
        estrelas = "⭐" * raridade
        if not disponiveis:
            await interaction.response.edit_message(
                content=f"Não sobrou nenhuma personagem livre {estrelas} nesse servidor agora - tenta de novo daqui a pouco.",
                view=None,
            )
            return
        view = _ViewEscolherMergeAlvo(self.guild_id, ids, estrelas, disponiveis)
        await interaction.response.edit_message(content=f"Escolha qual personagem {estrelas} você quer receber:", view=view)

    async def _abrir_prova_soulmate(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        prontas = torre.ordenar_por_power(db.personagens_prontas_para_prova(self.guild_id, self.autor_id), self.guild_id, self.autor_id)[:25]
        if not prontas:
            await interaction.response.send_message("Nenhuma personagem sua está em Afinidade 10 ainda.", ephemeral=True)
            return
        view = _ViewSelecionarPersonagem(prontas, "Escolha quem vai enfrentar a Prova...", self._prova_selecionada)
        await interaction.response.send_message("Selecione:", view=view, ephemeral=True)

    async def _prova_selecionada(self, interaction: discord.Interaction, personagens):
        personagem = personagens[0]
        # 🔥 defer ANTES de `obter_textos_prova_soulmate` (pode chamar a GAIA
        # via webhook, timeout até 30s) - mesmo cuidado do bug de timeout já
        # corrigido em `_rolar`/`_rolar_e_responder` (2026-08-29).
        await interaction.response.defer()
        textos = await gacha.obter_textos_prova_soulmate(personagem)
        embed = discord.Embed(
            title=f"💞 {textos['prova_soulmate_nome']}",
            description=f"{textos['prova_soulmate_descricao']}\n\n*{textos['prova_soulmate_situacao']}*",
            color=gacha._CORES_RARIDADE.get(personagem["raridade"], 0x2ECC71),
        )
        embed.add_field(name="Personagem", value=f"{personagem['nome']} · {gacha.estrelas_por_raridade(personagem['raridade'])}", inline=True)
        embed.add_field(name="Afinidade", value="10/10", inline=True)
        view = _ViewEscolherRespostaProva(self.guild_id, personagem, textos)
        await interaction.edit_original_response(embed=embed, view=view)

    async def _cidade(self, interaction: discord.Interaction):
        """Painel de status da Cidade (2026-08-30, análise do usuário Seção
        13 + "n iremos setar personagens em funcoes manualmente, sera
        automatico com base na classe/profissão") - SEM view/ação nenhuma,
        é só um status (a atribuição é automática, não tem nada pra
        configurar) - mensagem NOVA (mesmo padrão de Coleção/Party, nunca
        edita o hub). Coleta a produção acumulada desde a última visita na
        hora de abrir."""
        if not await self._somente_autor(interaction):
            return
        # 🔥 `defer()` + `asyncio.to_thread` (2026-08-30, achado do usuário:
        # "O Cidade... cai com frequencia nesse erro [GAIA não respondeu a
        # tempo]") - `coletar_producao_pendente` varia a coleção INTEIRA
        # (`_workforce_por_funcao`) via SQLite síncrono, bloqueando o event
        # loop do bot inteiro enquanto roda (não só esta interação) - além
        # de rodar num thread separado, `defer()` primeiro garante que a
        # PRÓPRIA interação nunca perde o prazo de 3s mesmo se a varredura
        # demorar mais que isso.
        await interaction.response.defer()
        resultado = await asyncio.to_thread(cidade.coletar_producao_pendente, self.guild_id, interaction.user.id)
        embed = _embed_cidade(resultado)
        await interaction.followup.send(embed=embed)

    async def _batalha(self, interaction: discord.Interaction):
        """Painel "⚔️ Batalha 5x5 com Aposta de Personagem" (2026-09-01,
        spec completa do usuário) - mensagem NOVA (mesmo padrão de Party/
        Torre/Cidade, nunca edita o hub)."""
        if not await self._somente_autor(interaction):
            return
        view = ViewBatalhaHub(self.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=view.formatar(), view=view)

    async def _worldboss(self, interaction: discord.Interaction):
        """Painel "🐉 World Boss" (2026-09-01, spec completa do usuário) -
        DIFERENTE do resto do hub: cooperativo, então NÃO é restrito a
        quem abriu (`ViewWorldBossHub` não tem `_somente_autor` de
        propósito - qualquer jogador do servidor pode clicar as categorias,
        é a mesma mecânica pra todo mundo)."""
        if not await self._somente_autor(interaction):
            return
        view = ViewWorldBossHub(self.guild_id)
        await interaction.response.send_message(embed=view.formatar(), view=view)

    async def _inventario(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        view = ViewInventarioHub(self.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=view.formatar(), view=view, ephemeral=True)

    async def _investir_em_massa(self, interaction: discord.Interaction):
        """2026-09-01, pedido do usuário: "permitir aumentar afinidade e
        nível em massa das personagens ordenadas pelo de maior CP, apenas
        informando qnt pretende investir"."""
        if not await self._somente_autor(interaction):
            return
        view = _ViewInvestirEmMassa(self.guild_id)
        await interaction.response.send_message("📈 Investir em massa - escolha o quê:", view=view, ephemeral=True)

    async def _reivindicar_tudo(self, interaction: discord.Interaction):
        """2026-09-01, pedido do usuário: "quero um botão que gasta todos
        os meus clains p pegar as personagens disponiveis por ordem de
        popularidade" - 1 clique só, sem escolher nada: reivindica as
        pendentes desse servidor em ordem de popularidade até os claims
        acabarem ou a lista esgotar (`gacha.reivindicar_em_massa`)."""
        if not await self._somente_autor(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        conquistadas = await gacha.reivindicar_em_massa(self.guild_id, interaction.user)
        if not conquistadas:
            await interaction.followup.send(
                "Nenhuma personagem disponível pra reivindicar agora (ou seus claims já acabaram nesse ciclo).",
                ephemeral=True,
            )
            return
        total_wishards = sum(recompensa for _personagem, recompensa in conquistadas)
        linhas = [
            f"{gacha._EMOJI_RARIDADE.get(personagem['raridade'], '💘')} {personagem['nome']}: +{recompensa} WiShards"
            for personagem, recompensa in conquistadas[:25]
        ]
        texto = "\n".join(linhas)
        if len(conquistadas) > 25:
            texto += f"\n... e mais {len(conquistadas) - 25} personagem(ns)."
        await interaction.followup.send(
            f"🎯 Reivindicadas {len(conquistadas)} personagem(ns), +{total_wishards} WiShards no total:\n{texto}",
            ephemeral=True,
        )

    async def _bonus_classe(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        view = ViewBonusClasseHub(self.guild_id, interaction.user.id)
        embed = await asyncio.to_thread(view.formatar)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ==========================================================================
# Perfil + Séries Favoritas (2026-09-02, redesenho do `/perfil` + sistema
# NOVO de Séries Favoritas - pedido do usuário em cima de uma sugestão
# externa endossada: "acho bem melhor... transforma série de um dado
# inútil entre milhares em uma escolha do jogador"). Regra de negócio em
# `pandora.series_favoritas`, aqui só embed+View.
# ==========================================================================

def _fmt_pct(numerador, denominador):
    if denominador <= 0:
        return f"{numerador}/0"
    return f"{numerador}/{denominador} ({numerador / denominador:.0%})"


def _montar_embed_perfil(guild_id, user_id):
    resumo = db.resumo_perfil_geral(guild_id, user_id)
    por_raridade = db.resumo_perfil_raridade(guild_id, user_id)
    favoritas = [item for item in series_favoritas.listar(guild_id, user_id) if item["serie"]]

    embed = discord.Embed(title="👤 Perfil", color=0x8E44AD)
    embed.add_field(
        name="📊 Resumo",
        value=(
            f"Personagens: {resumo['total']}\n"
            f"⭐ Nível máximo: {resumo['nivel_maximo']}\n"
            f"💕 Afinidade máxima: {resumo['afinidade_maxima']}\n"
            f"💞 Soulmates: {resumo['soulmates']}"
        ),
        inline=False,
    )

    if por_raridade:
        linhas = []
        for linha in por_raridade:
            estrelas = gacha.estrelas_por_raridade(linha["raridade"])
            total = linha["total"]
            linhas.append(
                f"{estrelas}\n"
                f"Personagens: {total}\n"
                f"Nível máximo: {_fmt_pct(linha['nivel_maximo'], total)}\n"
                f"Afinidade máxima: {_fmt_pct(linha['afinidade_maxima'], total)}\n"
                f"Soulmates: {_fmt_pct(linha['soulmates'], total)}"
            )
        embed.add_field(name="📚 Coleção por Raridade", value="\n\n".join(linhas)[:1024], inline=False)

    if favoritas:
        linhas = []
        for item in favoritas:
            marco = lambda ok: " ✅" if ok else ""
            bonus_pct = f"+{item['bonus_percentual']:.0%}" if item["bonus_percentual"] else "nenhum"
            linhas.append(
                f"**{item['serie']}**\n"
                f"📚 {_fmt_pct(item['possuidas'], item['total_catalogo'])}{marco(item['colecao_completa'])}\n"
                f"⭐ {_fmt_pct(item['nivel_maximo'], item['possuidas'])}{marco(item['maestria_completa'])}\n"
                f"❤️ {_fmt_pct(item['afinidade_maxima'], item['possuidas'])}{marco(item['afinidade_completa'])}\n"
                f"💕 {_fmt_pct(item['soulmates'], item['possuidas'])}{marco(item['soulbond_completo'])}\n"
                f"Bônus: {bonus_pct} CP"
            )
        embed.add_field(name="❤️ Séries Favoritas", value="\n\n".join(linhas)[:1024], inline=False)
    else:
        embed.add_field(name="❤️ Séries Favoritas", value="Nenhuma ainda - use ❤️ Séries no hub.", inline=False)

    embed.add_field(name="🏆 Conquistas", value=str(len(db.conquistas_do_jogador(guild_id, user_id))), inline=True)
    embed.add_field(name="🗼 Torre", value=f"Andar {db.andar_atual_torre(guild_id, user_id)}", inline=True)
    embed.add_field(name="💠 Soulstones", value=str(db.saldo_soulstone(guild_id, user_id)), inline=True)
    return embed


class _ViewPerfil(discord.ui.View):
    """Botões do "📖 Perfil" (2026-09-02, pedido do usuário: "Mover
    Auto-claim, Ranking, Conquistas para dentro do perfil", depois "quero
    q tenha uma lista com meus personagens favoritos... e poe ela e a
    wishlist dentro do perfil") - saíram do hub raiz `/pandora` pra cá,
    mesma lógica de sempre (só "Auto-claim" mudou de verdade: reconstrói
    e edita O PRÓPRIO Perfil depois do toggle, em vez do hub)."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        self._montar()

    def _montar(self):
        self.clear_items()
        ativo = db.auto_colecionar_ativo(self.guild_id, self.autor_id)
        auto_claim_botao = discord.ui.Button(
            label=f"Auto-claim: {'ON' if ativo else 'OFF'}", emoji="🤖",
            style=discord.ButtonStyle.success if ativo else discord.ButtonStyle.secondary, row=0,
        )
        auto_claim_botao.callback = self._toggle_auto_claim
        self.add_item(auto_claim_botao)
        ranking_botao = discord.ui.Button(label="Ranking", emoji="🏆", style=discord.ButtonStyle.secondary, row=0)
        ranking_botao.callback = self._ranking
        self.add_item(ranking_botao)
        conquistas_botao = discord.ui.Button(label="Conquistas", emoji="🏆", style=discord.ButtonStyle.secondary, row=0)
        conquistas_botao.callback = self._conquistas
        self.add_item(conquistas_botao)
        favoritos_botao = discord.ui.Button(label="Favoritos", emoji="⭐", style=discord.ButtonStyle.secondary, row=1)
        favoritos_botao.callback = self._favoritos
        self.add_item(favoritos_botao)
        wishlist_botao = discord.ui.Button(label="Wishlist", emoji="⭐", style=discord.ButtonStyle.secondary, row=1)
        wishlist_botao.callback = self._wishlist
        self.add_item(wishlist_botao)

    async def _somente_autor(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.autor_id:
            await interaction.response.send_message("Esse painel não é seu - use `/pandora` -> 📖 Perfil pra abrir o seu.", ephemeral=True)
            return False
        return True

    async def _toggle_auto_claim(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        # 🔥 `defer()` ANTES do `to_thread` (mesma classe de bug já
        # corrigida várias vezes nesta sessão) - `_montar_embed_perfil`
        # chama `series_favoritas.listar`, documentado como CARO.
        await interaction.response.defer()
        novo_estado = not db.auto_colecionar_ativo(self.guild_id, self.autor_id)
        await asyncio.to_thread(db.definir_auto_colecionar, self.guild_id, self.autor_id, novo_estado)
        self._montar()
        embed = await asyncio.to_thread(_montar_embed_perfil, self.guild_id, interaction.user.id)
        await interaction.edit_original_response(embed=embed, view=self)

    async def _ranking(self, interaction: discord.Interaction):
        """25 em vez dos 10 de sempre (2026-08-29) - sem paginação de
        verdade ainda (o formato de `consulta.formatar_ranking` é
        membro+contagem, não personagem - não dá pra reaproveitar
        `ViewColecao` direto); 25 já cobre qualquer servidor pessoal real
        até aqui, sem precisar construir um pager novo só pra isso.

        🔥 Rankings expandidos (2026-09-02) - antes só existia "Coleção"
        (tamanho); agora abre um seletor (`_ViewEscolherRanking`) com
        Coleção/Soulmates/Torre."""
        if not await self._somente_autor(interaction):
            return
        view = _ViewEscolherRanking(self.guild_id)
        await interaction.response.send_message("Ranking de qual métrica?", view=view, ephemeral=True)

    async def _conquistas(self, interaction: discord.Interaction):
        """🔥 2026-09-01 - `conquistas.verificar_colecionador` roda AQUI
        (sob demanda, ao abrir o painel), nunca num caminho quente como
        claim/roll/merge - só os 2 contadores vitalícios (rolls/merges)
        são atualizados na hora do evento em si, o resto é agregado SQL
        barato calculado só quando o jogador realmente olha."""
        if not await self._somente_autor(interaction):
            return
        await interaction.response.defer()
        novos = await asyncio.to_thread(conquistas.verificar_colecionador, self.guild_id, interaction.user.id)
        view = ViewConquistasHub(self.guild_id, interaction.user.id)
        embed = await asyncio.to_thread(view.formatar)
        if novos:
            nomes_novos = [conquistas.CATALOGO[c]["nome"] for c in novos]
            embed.add_field(name="🎉 Novas conquistas!", value="\n".join(nomes_novos), inline=False)
        await interaction.followup.send(embed=embed, view=view)

    async def _favoritos(self, interaction: discord.Interaction):
        """Lista paginada dos favoritos (2026-09-02, pedido do usuário:
        "quero q tenha uma lista com meus personagens favoritos, assim
        como tem so de personagens") - mesma visibilidade ephemeral da
        Wishlist, é lista pessoal."""
        if not await self._somente_autor(interaction):
            return
        view = ViewFavoritosHub(self.guild_id, interaction.user.id)
        await interaction.response.send_message(view.formatar(), view=view, ephemeral=True)

    async def _wishlist(self, interaction: discord.Interaction):
        """Mesma visibilidade ephemeral que `/wishlist listar` já tem hoje -
        é lista pessoal, nunca foi pública. Movida do hub raiz pra cá
        (2026-09-02, "poe ela e a wishlist dentro do perfil")."""
        if not await self._somente_autor(interaction):
            return
        view = ViewWishlistHub(self.guild_id, interaction.user.id)
        await interaction.response.send_message(view.formatar(), view=view, ephemeral=True)


async def _definir_serie_e_atualizar(view_series, slot, serie, interacao_editar_painel, interacao_responder):
    """Núcleo compartilhado - grava a Série Favorita, atualiza o painel
    "❤️ Séries Favoritas" (mensagem original, editada via `interacao_
    editar_painel` - o Modal ou, na desambiguação, a interação do Modal
    guardada por fora) e responde (ephemeral) na interação de quem
    confirmou de fato (`interacao_responder` - pode ser uma interação
    DIFERENTE da que edita o painel, ver `_ViewEscolherSerieFavorita`)."""
    ok, mensagem = await asyncio.to_thread(series_favoritas.definir, view_series.guild_id, view_series.user_id, slot, serie)
    print(f" [SERIES] series_favoritas.definir -> ok={ok} mensagem={mensagem}")
    if ok:
        await view_series._atualizar()
        await interacao_editar_painel.edit_original_response(content=view_series.formatar(), view=view_series)
    await interacao_responder.followup.send(mensagem, ephemeral=True)


class _ViewEscolherSerieFavorita(discord.ui.View):
    """Passo de desambiguação (2026-09-02, achado do usuário: "essa
    resposta q recebi nem faz sentido... n tem algo p confirmar, é so uma
    mensagem, se eu escrever sim vai reconhecer?", refinado depois: "a
    ideia era vc eu escrever parte do nome no campo q abre, e vc abrir um
    dropdown com filtro q tenha aquele campo, igual era p adicionar na
    pt") - quando a busca por texto (`db.series_do_catalogo`, substring)
    não bate uma EXATA, lista as até 25 candidatas pra ESCOLHER a certa
    (select de verdade, clicável) - SEMPRE mostra o dropdown, mesmo com 1
    candidata só (nunca aplica uma correspondência aproximada sozinho
    sem o jogador confirmar de propósito). Mais perto do "dropdown
    enquanto digita" que dá pra fazer aqui - Discord só permite
    autocomplete de verdade (sugestão ao vivo enquanto digita) em
    parâmetro de SLASH COMMAND, nunca dentro de um Modal (campo de Modal
    é sempre texto puro, sem callback de digitação) - esse 2º passo
    (buscar -> escolher da lista) é o equivalente mais próximo possível
    vindo de um Modal, mesmo padrão de busca-depois-dropdown já usado em
    `_ModalBuscarPersonagem`/Party."""

    def __init__(self, view_series, slot, candidatas, interacao_modal):
        super().__init__(timeout=120)
        self._view_series = view_series
        self._slot = slot
        self._candidatas = candidatas
        self._interacao_modal = interacao_modal
        # 🔥 `value=str(indice)` em vez do nome cru (2026-09-02, achado em
        # produção: "kono" -> 9 candidatas, uma delas com nome > 100
        # caracteres - `SelectOption.value` tem o MESMO teto de 100 do
        # Discord que `label`, mas só `label` estava sendo cortado
        # (`nome[:100]`); `value=nome` sem cortar quebrava o ENVIO da
        # mensagem inteira com "Invalid Form Body" - índice nunca estoura
        # e resolve de volta pro nome EXATO/INTEIRO via `self._candidatas`,
        # mesmo padrão já usado no resto do arquivo (`_ViewSelecionarPersonagem`).
        select = discord.ui.Select(
            placeholder="Qual série?",
            options=[discord.SelectOption(label=nome[:100], value=str(indice)) for indice, nome in enumerate(candidatas)],
        )
        select.callback = self._selecionou
        self.add_item(select)

    async def _selecionou(self, interaction: discord.Interaction):
        serie = self._candidatas[int(interaction.data["values"][0])]
        await interaction.response.defer(ephemeral=True)
        await _definir_serie_e_atualizar(self._view_series, self._slot, serie, self._interacao_modal, interaction)


class _ModalDefinirSerieFavorita(discord.ui.Modal):
    def __init__(self, view, slot, serie_atual):
        super().__init__(title=f"Série Favorita - Slot {slot}"[:45])
        self._view = view
        self._slot = slot
        self.serie = discord.ui.TextInput(
            label="Série (vazio limpa o slot)"[:45], required=False, max_length=100,
            default=serie_atual or None,
        )
        self.add_item(self.serie)

    async def on_submit(self, interaction: discord.Interaction):
        # 🔥 `defer()` ANTES do `to_thread` (2026-09-02, achado do usuário:
        # "qnd clico nos slots da tela de series favoritas, da gaia nao
        # respondeu a tempo") - `series_favoritas.definir` chama
        # `recalcular_bonus`, que o próprio módulo documenta como CARO
        # (varre a coleção inteira filtrada por série) - rodava ANTES de
        # qualquer resposta à interação, mesma classe de bug já corrigida
        # na Batalha (defer sempre a 1ª linha, nunca depois do to_thread).
        # Interação de Modal aberto por um botão vira `deferred_message_
        # update` (edita a MESMA mensagem do painel) - `edit_original_
        # response` no lugar de `response.edit_message` depois do defer.
        print(f" [SERIES] Modal on_submit iniciado - slot={self._slot} user={interaction.user.id}")
        try:
            await interaction.response.defer()
            print(" [SERIES] defer() OK")
            texto = str(self.serie).strip() or None
            if texto is not None:
                # 🔥 Resolução ANTES de gravar (2026-09-02, pedido do
                # usuário: "a ideia era vc eu escrever parte do nome no
                # campo q abre, e vc abrir um dropdown com filtro q tenha
                # aquele campo, igual era p adicionar na pt") - exata
                # primeiro (case-insensitive, cobre digitar certo com
                # maiúscula/minúscula errada, aplica direto sem dropdown -
                # não tem ambiguidade nenhuma pra escolher); se não achar,
                # busca por SUBSTRING (`db.series_do_catalogo`) e SEMPRE
                # mostra o dropdown pra escolher (mesmo com 1 candidata só
                # - nunca aplica sozinho uma correspondência aproximada
                # sem o jogador confirmar de propósito, diferente da 1ª
                # versão desta correção).
                canonico = await asyncio.to_thread(db.encontrar_serie_por_nome, texto)
                if canonico is None:
                    candidatas = await asyncio.to_thread(db.series_do_catalogo, texto, 25)
                    print(f" [SERIES] busca por substring '{texto}' -> {len(candidatas)} candidata(s)")
                    if not candidatas:
                        await interaction.followup.send(f'Nenhuma série parecida com "{texto}" no catálogo.', ephemeral=True)
                        return
                    view_escolher = _ViewEscolherSerieFavorita(self._view, self._slot, candidatas, interaction)
                    await interaction.followup.send(
                        f'{len(candidatas)} série(s) parecida(s) com "{texto}" - escolha a certa:',
                        view=view_escolher, ephemeral=True,
                    )
                    return
                texto = canonico
            await _definir_serie_e_atualizar(self._view, self._slot, texto, interaction, interaction)
            print(" [SERIES] Modal on_submit concluído.")
        except Exception:
            print(" [SERIES] !!! EXCEÇÃO dentro de on_submit !!!")
            traceback.print_exc()


class _ViewSeriesFavoritas(discord.ui.View):
    """Gerenciar Séries Favoritas (2026-09-02) - 1 botão por slot
    (verde = ocupado, cinza = vazio), abre `_ModalDefinirSerieFavorita`
    pra escolher/trocar/limpar; + 1 botão "Comprar Slot" quando ainda não
    chegou no teto (`series_favoritas.SLOTS_MAXIMO`).

    🔥 Causa raiz de verdade do "GAIA não respondeu a tempo" persistente
    (2026-09-02, achado depois do fix de `str`/`int` não resolver) -
    `criar()` (chamado como `await asyncio.to_thread(_ViewSeriesFavoritas.
    criar, ...)`) construía a View INTEIRA (`__init__` -> `super().
    __init__()` -> `discord.ui.view.BaseView.__init__`) dentro da thread
    worker do `to_thread`, SEM event loop rodando ali - `BaseView.__init__`
    tenta `asyncio.get_running_loop()` pra criar o Future interno
    `__stopped`, e sem loop cai no `except RuntimeError` e deixa
    `__stopped = None` PRA SEMPRE (nunca mais corrigido depois). O método
    interno que o discord.py usa pra rotear QUALQUER clique de botão pro
    callback certo (`View._dispatch_item`) começa com `if self.__stopped
    is None or self.__stopped.done(): return None` - com `__stopped=None`,
    TODO clique nessa View é descartado em silêncio, sem exceção, sem
    log, sem resposta nenhuma - exatamente o sintoma relatado (nenhum log
    `[SERIES]` aparecia pro clique, só pra abertura do painel). Corrigido
    separando busca de dado (`series_favoritas.listar`, CARO - continua
    rodando em `to_thread`) da CONSTRUÇÃO da View em si (`__init__`/
    `_montar_botoes`, que precisa rodar na thread principal pra
    `BaseView.__init__` pegar o loop de verdade) - `criar()` virou
    `async`, busca os slots via `to_thread` e SÓ DEPOIS constrói `cls(...)`
    já de volta na thread principal (o `await` devolve o controle lá)."""

    @classmethod
    async def criar(cls, guild_id, user_id):
        slots = await asyncio.to_thread(series_favoritas.listar, guild_id, user_id)
        return cls(guild_id, user_id, slots)

    def __init__(self, guild_id, user_id, slots):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        # 🔥 `str(...)` (2026-09-02, achado do usuário: "Na tela de Series,
        # tanto ao clicar nos slots qnt em comprar slot retorna GAIA nao
        # respondeu a tempo") - `user_id` chegava aqui como INT
        # (`interaction.user.id`, direto), mas `_callback_slot`/`_comprar_
        # slot` comparavam com `str(interaction.user.id)` - `str != int`
        # nunca é igual em Python, então o check de dono barrava SEMPRE,
        # até pro dono de verdade, com "Esse painel não é seu." (mesmo
        # padrão `str(autor_id)` já usado em `ViewHubWaifu`/resto do hub).
        self.user_id = str(user_id)
        self._slots = slots
        self._montar_botoes()

    async def _atualizar(self):
        """Rebusca os slots (`to_thread`, CARO) + reconstrói os botões
        (`_montar_botoes`, síncrono/rápido - chamado direto, na thread
        principal de quem já está dentro de um callback de interação, sem
        `to_thread` nenhum) - usado depois de qualquer mudança (escolher
        série, comprar slot)."""
        self._slots = await asyncio.to_thread(series_favoritas.listar, self.guild_id, self.user_id)
        self._montar_botoes()

    def _montar_botoes(self):
        self.clear_items()
        # 🔥 1 SELECT pra escolher/trocar/limpar slot, em vez de 1 botão
        # POR slot (2026-09-03, pedido do usuário: "aumente o limite de
        # series para 25 se conseguir") - 25 botões estourariam sozinhos
        # as 5 linhas x 5 itens do Discord (nem sobraria espaço pro
        # "Comprar slot" nem pro "Navegar"); 1 select cabe até 25 opções
        # numa linha só - é O MOTIVO do teto ter virado exatamente 25 (ver
        # `db.NIVEL_MAXIMO_UPGRADE_SLOT_SERIE_FAVORITA`). `value=str(slot)`
        # (nunca o nome da série - mesmo motivo já corrigido no dropdown
        # de desambiguação: `SelectOption.value` tem teto de 100 chars).
        options_slot = []
        for item in self._slots:
            rotulo = f"Slot {item['slot']}: {item['serie']}" if item["serie"] else f"Slot {item['slot']} (vazio)"
            options_slot.append(discord.SelectOption(label=rotulo[:100], value=str(item["slot"]), emoji="✅" if item["serie"] else None))
        slot_select = discord.ui.Select(placeholder="✏️ Escolher/trocar/limpar um slot...", options=options_slot, row=0)
        slot_select.callback = self._callback_slot_select
        self.add_item(slot_select)
        disponiveis = len(self._slots)
        if disponiveis < series_favoritas.SLOTS_MAXIMO:
            proximo_nivel = db.nivel_upgrade_slots_serie_favorita(self.guild_id, self.user_id) + 1
            preco = db.PRECOS_UPGRADE_SLOT_SERIE_FAVORITA[proximo_nivel]
            comprar_botao = discord.ui.Button(
                label=f"Comprar slot ({preco} WiShards)", emoji="🛒", style=discord.ButtonStyle.primary, row=1,
            )
            comprar_botao.callback = self._comprar_slot
            self.add_item(comprar_botao)
        # 🔥 Dropdown de navegação rápida (2026-09-03, pedido do usuário:
        # "quero colocar um dropdown na tela de series, com a lista de
        # series q favoritei. E qnd seleciono uma serie, ele abre os
        # personagens... soq com um botao de comprar tbm") - `value=str(
        # indice)` (nunca o nome cru) pelo MESMO motivo do select acima.
        series_favoritadas = [item["serie"] for item in self._slots if item["serie"]]
        if series_favoritadas:
            navegar_select = discord.ui.Select(
                placeholder="🎬 Navegar por uma Série Favorita...", row=2,
                options=[discord.SelectOption(label=serie[:100], value=str(indice)) for indice, serie in enumerate(series_favoritadas)],
            )
            navegar_select.callback = self._callback_navegar_serie(series_favoritadas)
            self.add_item(navegar_select)

    def _callback_navegar_serie(self, series_favoritadas):
        async def _callback(interaction: discord.Interaction):
            serie = series_favoritadas[int(interaction.data["values"][0])]
            await interaction.response.defer(ephemeral=True)
            view = await _ViewNavegarSerie.criar(self.guild_id, self.user_id, serie)
            if view is None:
                await interaction.followup.send(f'Nenhuma personagem ativa encontrada pra "{serie}".', ephemeral=True)
                return
            await interaction.followup.send(embed=view.montar_embed(), view=view, ephemeral=True)
        return _callback

    async def _callback_slot_select(self, interaction: discord.Interaction):
        slot = int(interaction.data["values"][0])
        item = next(i for i in self._slots if i["slot"] == slot)
        print(f" [SERIES] selecionou o slot {slot} - user={interaction.user.id} self.user_id={self.user_id}")
        try:
            if str(interaction.user.id) != self.user_id:
                print(" [SERIES] bloqueado - painel não é do autor.")
                await interaction.response.send_message("Esse painel não é seu.", ephemeral=True)
                return
            await interaction.response.send_modal(_ModalDefinirSerieFavorita(self, item["slot"], item["serie"]))
            print(" [SERIES] send_modal OK")
        except Exception:
            print(" [SERIES] !!! EXCEÇÃO dentro do clique de slot !!!")
            traceback.print_exc()

    async def _comprar_slot(self, interaction: discord.Interaction):
        print(f" [SERIES] Comprar Slot clicado - user={interaction.user.id} self.user_id={self.user_id}")
        try:
            if str(interaction.user.id) != self.user_id:
                print(" [SERIES] bloqueado - painel não é do autor.")
                await interaction.response.send_message("Esse painel não é seu.", ephemeral=True)
                return
            # 🔥 `defer()` ANTES do `to_thread` (2026-09-02) - `_atualizar`
            # chama `series_favoritas.listar`, documentado como CARO (varre
            # a coleção inteira filtrada por série).
            await interaction.response.defer()
            print(" [SERIES] defer() OK")
            ok, mensagem = await asyncio.to_thread(db.comprar_slot_serie_favorita, self.guild_id, interaction.user.id)
            print(f" [SERIES] comprar_slot_serie_favorita -> ok={ok} mensagem={mensagem}")
            if not ok:
                await interaction.followup.send(mensagem, ephemeral=True)
                return
            await self._atualizar()
            print(" [SERIES] _atualizar concluído, editando resposta original...")
            await interaction.edit_original_response(content=self.formatar(), view=self)
            await interaction.followup.send(mensagem, ephemeral=True)
            print(" [SERIES] Comprar Slot concluído.")
        except Exception:
            print(" [SERIES] !!! EXCEÇÃO dentro de Comprar Slot !!!")
            traceback.print_exc()

    def formatar(self):
        linhas = ["❤️ **Séries Favoritas** - clique num slot pra escolher/trocar/limpar."]
        for item in self._slots:
            if item["serie"]:
                bonus = f" (+{item['bonus_percentual']:.0%} CP)" if item["bonus_percentual"] else ""
                linhas.append(f"Slot {item['slot']}: **{item['serie']}**{bonus}")
            else:
                linhas.append(f"Slot {item['slot']}: vazio")
        return "\n".join(linhas)


class _ModalBuscarPosicaoOuNomeSerie(discord.ui.Modal, title="Buscar personagem"):
    """"🔎 Buscar" do navegador de Série (2026-09-03, pedido do usuário:
    "Faz o msm esquemas das personagens" - mesmo Modal de posição/nome de
    `_ModalBuscarPosicaoOuNome`, só que resolvendo posição DENTRO da
    série em vez da coleção do jogador)."""

    consulta_texto = discord.ui.TextInput(label="Nome ou posição (nº)", placeholder="Ex.: Sasuke ou 120", max_length=100)

    def __init__(self, view):
        super().__init__()
        self._view = view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        texto = str(self.consulta_texto).strip()
        if not texto:
            await interaction.followup.send("Digite um nome ou uma posição.", ephemeral=True)
            return
        if texto.isdigit():
            posicao = int(texto)
            if posicao < 1:
                await interaction.followup.send("Posição inválida - use um número a partir de 1.", ephemeral=True)
                return
            indice_alvo = posicao - 1
        else:
            personagens_ordenados = await asyncio.to_thread(
                db.personagens_da_serie, self._view.guild_id, self._view.serie, self._view._permitir_nsfw,
            )
            melhores = consulta.buscar_por_nome(personagens_ordenados, texto, limite=1)
            if not melhores:
                await interaction.followup.send(f'Nenhuma personagem parecida com "{texto}" em "{self._view.serie}".', ephemeral=True)
                return
            alvo_id = melhores[0]["id"]
            indice_alvo = next(i for i, p in enumerate(personagens_ordenados) if p["id"] == alvo_id)
        ok = await self._view._ir_para(indice_alvo)
        if not ok:
            await interaction.followup.send("Nenhuma personagem encontrada nessa série.", ephemeral=True)
            return
        if self._view._indice_global != indice_alvo:
            self._view._status = f"⚠️ Só existem {self._view._total} personagem(ns) - mostrando a posição {self._view._indice_global + 1}."
        await interaction.edit_original_response(embed=self._view.montar_embed(), view=self._view)


class _ViewNavegarSerie(discord.ui.View):
    """Navegador de uma Série Favorita (2026-09-03, pedido do usuário:
    "quero colocar um dropdown na tela de series, com a lista de series q
    favoritei. E qnd seleciono uma serie, ele abre os personagens, igual
    na tela de personagens, soq com um botao de comprar tbm", depois
    "Faz o msm esquemas das personagens, o skip com 25, o dropdown com
    base na posição. E corrige o limite q hj é so 25") - MESMA navegação
    por posição/bloco/busca do "🔍 Personagem" (`_ViewNivel`), só que
    sobre o CATÁLOGO da série (não a coleção do jogador): `_indice_global`
    contra o TOTAL de verdade (`db.contar_personagens_da_serie`) e um
    BLOCO de até 25 (`db.personagens_da_serie_paginada`) que contém a
    posição atual - qualquer posição é 1 SELECT por `OFFSET`/`LIMIT`,
    nunca precisa carregar a série inteira nem travar em 25 pra sempre
    (bug igual ao já corrigido no "🔍 Personagem"). Card usa o MESMO
    `consulta.embed_carta_personagem` de sempre; "🛒 Comprar"/"🛍️ Comprar
    Tudo" reaproveitam `gacha.comprar_com_revelacao`/`db.comprar_
    personagem` (MESMA regra/preço/corrida da Loja de verdade)."""

    @classmethod
    async def criar(cls, guild_id, autor_id, serie, indice_global=0):
        """Fábrica assíncrona (mesmo motivo de `_ViewSeriesFavoritas.
        criar`/`_ViewNivel.criar` - View NUNCA pode ser construída dentro
        de um `to_thread`). `None` se a série não tiver nenhum personagem
        ATIVO."""
        permitir_nsfw = await asyncio.to_thread(db.obter_configuracao_colecao, guild_id)
        permitir_nsfw = permitir_nsfw["nsfw_permitido"]
        total = await asyncio.to_thread(db.contar_personagens_da_serie, serie, permitir_nsfw)
        if total <= 0:
            return None
        indice_global = max(0, min(total - 1, indice_global))
        bloco_offset = (indice_global // 25) * 25
        bloco = await asyncio.to_thread(
            db.personagens_da_serie_paginada, guild_id, serie, permitir_nsfw, bloco_offset, 25,
        )
        if not bloco:
            return None
        idx_local = min(indice_global - bloco_offset, len(bloco) - 1)
        return cls(guild_id, autor_id, serie, permitir_nsfw, bloco, bloco_offset, idx_local, total)

    def __init__(self, guild_id, autor_id, serie, permitir_nsfw, bloco, bloco_offset, idx_local, total):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        self.serie = serie
        self._permitir_nsfw = permitir_nsfw
        self._bloco = bloco
        self._bloco_offset = bloco_offset
        self._idx_local = idx_local
        self._total = total
        self._status = None

        self._select = discord.ui.Select(placeholder="🔄 Trocar de personagem...", options=[discord.SelectOption(label="-", value="0")], row=0)
        self._select.callback = self._trocar
        self.add_item(self._select)
        self._botao_bloco_anterior = discord.ui.Button(emoji="⏮️", style=discord.ButtonStyle.secondary, row=1)
        self._botao_bloco_anterior.callback = self._ir_bloco_anterior
        self.add_item(self._botao_bloco_anterior)
        self._botao_anterior = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
        self._botao_anterior.callback = self._navegar_anterior
        self.add_item(self._botao_anterior)
        self._botao_proximo = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary, row=1)
        self._botao_proximo.callback = self._navegar_proximo
        self.add_item(self._botao_proximo)
        self._botao_bloco_seguinte = discord.ui.Button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=1)
        self._botao_bloco_seguinte.callback = self._ir_bloco_seguinte
        self.add_item(self._botao_bloco_seguinte)
        self._botao_buscar = discord.ui.Button(label="Buscar", emoji="🔎", style=discord.ButtonStyle.primary, row=1)
        self._botao_buscar.callback = self._abrir_busca
        self.add_item(self._botao_buscar)

        self._botao_comprar = discord.ui.Button(label="Comprar", emoji="🛒", style=discord.ButtonStyle.success, row=2)
        self._botao_comprar.callback = self._comprar
        self.add_item(self._botao_comprar)
        self._botao_comprar_tudo = discord.ui.Button(label="Comprar Tudo", emoji="🛍️", style=discord.ButtonStyle.danger, row=2)
        self._botao_comprar_tudo.callback = self._comprar_tudo
        self.add_item(self._botao_comprar_tudo)
        # 🔥 Favoritar (2026-09-03, pedido do usuário: "Nos personagens das
        # series favoritas, permita favoritar tbm") - só funciona pra
        # personagem que o autor JÁ POSSUI (favoritar é sobre a COLEÇÃO
        # dele, `db.favoritos_listar` exige posse), mesmo toggle de
        # `_ViewNivel.favoritar`.
        self._botao_favoritar = discord.ui.Button(label="Favoritar", emoji="⭐", style=discord.ButtonStyle.secondary, row=2)
        self._botao_favoritar.callback = self._favoritar
        self.add_item(self._botao_favoritar)
        # 🔥 Investir em massa ESCOPADO à série (2026-09-03, pedido do
        # usuário: "Coloca botao la tbm p maximizar nivel e afinidade da
        # serie, assim como é o em massa") - MESMO Modal/motor do
        # "📈 Investir em Massa" do hub (`torre._investir_em_massa`), só
        # que a coleção passada é filtrada pra "possui + é dessa série".
        self._botao_nivel_serie = discord.ui.Button(label="Maximizar Nível", emoji="⬆️", style=discord.ButtonStyle.primary, row=3)
        self._botao_nivel_serie.callback = self._abrir_nivel_serie
        self.add_item(self._botao_nivel_serie)
        self._botao_afinidade_serie = discord.ui.Button(label="Maximizar Afinidade", emoji="💕", style=discord.ButtonStyle.primary, row=3)
        self._botao_afinidade_serie.callback = self._abrir_afinidade_serie
        self.add_item(self._botao_afinidade_serie)
        self._atualizar_select_options()

    @property
    def _indice_global(self):
        return self._bloco_offset + self._idx_local

    @property
    def personagem(self):
        return self._bloco[self._idx_local]

    def _atualizar_select_options(self):
        contexto_lote = torre._contexto_lote(self.guild_id, self.autor_id)
        options = []
        for indice, p in enumerate(self._bloco):
            texto, emoji = _descricao_personagem_dropdown(p, self.guild_id, self.autor_id, contexto_lote)
            posicao_absoluta = self._bloco_offset + indice + 1
            options.append(discord.SelectOption(
                label=f"{posicao_absoluta}. {p['nome']}"[:100], description=texto[:100], value=str(indice),
                emoji=emoji, default=(indice == self._idx_local),
            ))
        self._select.options = options
        self._select.placeholder = f"🔄 Trocar de personagem (bloco {self._bloco_offset + 1}-{self._bloco_offset + len(self._bloco)})..."

    async def _ir_para(self, indice_global):
        """Núcleo de TODA navegação (setas/bloco/busca/select) - MESMO
        padrão de `_ViewNivel._ir_para`, só trocando a fonte de dado pra
        `db.personagens_da_serie_paginada`/`contar_personagens_da_serie`."""
        total = await asyncio.to_thread(db.contar_personagens_da_serie, self.serie, self._permitir_nsfw)
        if total <= 0:
            self._total = 0
            return False
        indice_global = max(0, min(total - 1, indice_global))
        novo_bloco_offset = (indice_global // 25) * 25
        if novo_bloco_offset != self._bloco_offset:
            novo_bloco = await asyncio.to_thread(
                db.personagens_da_serie_paginada, self.guild_id, self.serie, self._permitir_nsfw, novo_bloco_offset, 25,
            )
            if not novo_bloco:
                self._total = total
                return False
            self._bloco = novo_bloco
            self._bloco_offset = novo_bloco_offset
        self._total = total
        self._idx_local = min(indice_global - novo_bloco_offset, len(self._bloco) - 1)
        self._status = None
        self._atualizar_select_options()
        return True

    async def _renderizar(self, interaction: discord.Interaction):
        if self._total <= 0:
            await interaction.response.edit_message(content="Nenhuma personagem encontrada nessa série.", embed=None, view=None)
            return
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    async def _somente_autor(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.autor_id:
            await interaction.response.send_message("Esse painel não é seu.", ephemeral=True)
            return False
        return True

    async def _trocar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        await self._ir_para(self._bloco_offset + int(interaction.data["values"][0]))
        await self._renderizar(interaction)

    async def _navegar_anterior(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        await self._ir_para(self._indice_global - 1)
        await self._renderizar(interaction)

    async def _navegar_proximo(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        await self._ir_para(self._indice_global + 1)
        await self._renderizar(interaction)

    async def _ir_bloco_anterior(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        await self._ir_para(max(0, self._bloco_offset - 25))
        await self._renderizar(interaction)

    async def _ir_bloco_seguinte(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        await self._ir_para(self._bloco_offset + 25)
        await self._renderizar(interaction)

    async def _abrir_busca(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        await interaction.response.send_modal(_ModalBuscarPosicaoOuNomeSerie(self))

    def _colecao_possuida_da_serie(self, user_id):
        """Personagens da série que ESSE jogador já possui nesse servidor
        - busca a série INTEIRA (não só o bloco carregado pra navegação),
        mesmo motivo do "Comprar Tudo" - uma série pode ter mais que 25."""
        todos = db.personagens_da_serie(self.guild_id, self.serie, self._permitir_nsfw)
        return [p for p in todos if p.get("dono_id") == str(user_id)]

    async def _abrir_nivel_serie(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        colecao_serie = await asyncio.to_thread(self._colecao_possuida_da_serie, interaction.user.id)
        if not colecao_serie:
            await interaction.response.send_message(f'Você não possui nenhuma personagem de "{self.serie}" ainda.', ephemeral=True)
            return
        saldo = await asyncio.to_thread(db.saldo_wishards, self.guild_id, interaction.user.id)
        await interaction.response.send_modal(_ModalInvestirEmMassa(self.guild_id, "nivel", saldo, colecao_serie))

    async def _abrir_afinidade_serie(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        colecao_serie = await asyncio.to_thread(self._colecao_possuida_da_serie, interaction.user.id)
        if not colecao_serie:
            await interaction.response.send_message(f'Você não possui nenhuma personagem de "{self.serie}" ainda.', ephemeral=True)
            return
        saldo = await asyncio.to_thread(db.saldo_soulstone, self.guild_id, interaction.user.id)
        await interaction.response.send_modal(_ModalInvestirEmMassa(self.guild_id, "afinidade", saldo, colecao_serie))

    async def _comprar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        personagem = self.personagem
        await interaction.response.defer()
        # 🔥 `gacha.comprar_com_revelacao` em vez de `db.comprar_personagem`
        # direto (2026-09-03, pedido do usuário: "esses botoes tem q
        # fazer exatamente o claim, definir clsse e tudo").
        ok, mensagem = await gacha.comprar_com_revelacao(self.guild_id, personagem["id"], interaction.user)
        if ok:
            # 🔥 Atualiza o `dono_id` LOCAL (2026-09-03) - sem isso o card
            # continuaria mostrando "🛒 Disponível" até reabrir o
            # navegador, já que o bloco carregado não é rebuscado depois
            # de comprar (só o `db` de verdade muda).
            personagem["dono_id"] = str(interaction.user.id)
        self._status = f"{'✅' if ok else '❌'} {mensagem}"
        await interaction.edit_original_response(embed=self.montar_embed(), view=self)

    async def _comprar_tudo(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        # 🔥 Rebusca a série INTEIRA (não só o bloco carregado aqui pra
        # navegação) - "Comprar Tudo" tem que valer pra série INTEIRA de
        # verdade, senão uma série com mais de 25 nunca completaria via
        # esse atalho.
        await interaction.response.defer(ephemeral=True)
        todos = await asyncio.to_thread(db.personagens_da_serie, self.guild_id, self.serie, self._permitir_nsfw)
        livres = [p for p in todos if p.get("dono_id") is None]
        if not livres:
            await interaction.followup.send(
                f'Nenhuma personagem livre pra comprar em "{self.serie}" - já foram todas reivindicadas.', ephemeral=True,
            )
            return
        preco_total = sum(db.PRECOS_LOJA[p["raridade"]] for p in livres)
        saldo = await asyncio.to_thread(db.saldo_wishards, self.guild_id, interaction.user.id)
        aviso_saldo = " - **saldo insuficiente pra tudo, vai comprar o que der**" if saldo < preco_total else ""
        texto = (
            f"🛍️ **Comprar tudo de {self.serie}**\n"
            f"{len(livres)} personagem(ns) livre(s) - total: **{preco_total} WiShards**\n"
            f"Seu saldo: {saldo} WiShards{aviso_saldo}"
        )
        view_confirmar = _ViewConfirmarComprarTudo(self.guild_id, self.autor_id, self.serie, livres)
        await interaction.followup.send(texto, view=view_confirmar, ephemeral=True)

    async def _favoritar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        personagem = self.personagem
        if personagem.get("dono_id") != self.autor_id:
            await interaction.response.send_message("Só dá pra favoritar uma personagem que você já possui.", ephemeral=True)
            return
        if db.eh_favorita(self.guild_id, self.autor_id, personagem["id"]):
            db.desfavoritar(self.guild_id, self.autor_id, personagem["id"])
            self._status = f"Desmarcada como favorita: **{personagem['nome']}**."
        else:
            db.favoritar(self.guild_id, self.autor_id, personagem["id"])
            self._status = f"⭐ Marcada como favorita: **{personagem['nome']}**."
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    def montar_embed(self):
        self._botao_anterior.disabled = self._indice_global <= 0
        self._botao_proximo.disabled = self._indice_global >= self._total - 1
        self._botao_bloco_anterior.disabled = self._bloco_offset <= 0
        self._botao_bloco_seguinte.disabled = self._bloco_offset + 25 >= self._total
        personagem = self.personagem
        embed = consulta.embed_carta_personagem(personagem)
        embed.set_footer(text=f"{self._indice_global + 1}/{self._total} · {self.serie}")
        dono_id = personagem.get("dono_id")
        if dono_id is None:
            preco = db.PRECOS_LOJA[personagem["raridade"]]
            embed.add_field(name="Status", value=f"🛒 Disponível - {preco} WiShards", inline=True)
            self._botao_comprar.disabled = False
            self._botao_comprar.label = f"Comprar ({preco})"
            self._botao_favoritar.disabled = True
            self._botao_favoritar.label = "Favoritar"
            self._botao_favoritar.style = discord.ButtonStyle.secondary
        elif dono_id == self.autor_id:
            power, _nivel, categoria = torre.power_personagem(personagem, self.guild_id, self.autor_id)
            embed.add_field(name="Status", value="✅ Já é sua", inline=True)
            embed.add_field(name="CP", value=f"{torre.icone_categoria(categoria)} {power:.0f}", inline=True)
            self._botao_comprar.disabled = True
            self._botao_comprar.label = "Já é sua"
            favorita = db.eh_favorita(self.guild_id, self.autor_id, personagem["id"])
            self._botao_favoritar.disabled = False
            self._botao_favoritar.label = "Desfavoritar" if favorita else "Favoritar"
            self._botao_favoritar.style = discord.ButtonStyle.success if favorita else discord.ButtonStyle.secondary
        else:
            embed.add_field(name="Status", value=f"🔒 Possuída por <@{dono_id}>", inline=True)
            self._botao_comprar.disabled = True
            self._botao_comprar.label = "Indisponível"
            self._botao_favoritar.disabled = True
            self._botao_favoritar.label = "Favoritar"
            self._botao_favoritar.style = discord.ButtonStyle.secondary
        if self._status:
            embed.description = self._status
        return embed


class _ViewConfirmarComprarTudo(discord.ui.View):
    """Confirmação de "🛍️ Comprar Tudo" (2026-09-03, pedido do usuário:
    "qnd clico ele abre uma nova mensagem com o preço de tudo e o botão
    de confirmar") - mensagem NOVA e separada do card de navegação (não
    edita o `_ViewNavegarSerie` original), com o total já calculado.
    Compra 1 por 1 sequencialmente via `gacha.comprar_com_revelacao`
    (MESMO claim+classe de sempre, "lembrando q esses botoes tem q fazer
    exatamente o claim, definir clsse e tudo") - sequencial (não paralelo)
    porque `db.reivindicar` já é atômico por personagem, sem necessidade
    de paralelizar, e sequencial deixa o resumo final simples de montar
    (sucesso/falha por item, sem condição de corrida entre elas mesmas)."""

    def __init__(self, guild_id, autor_id, serie, personagens_livres):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        self.serie = serie
        self._personagens_livres = personagens_livres

    async def _somente_autor(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.autor_id:
            await interaction.response.send_message("Essa confirmação não é sua.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirmar", emoji="✅", style=discord.ButtonStyle.success)
    async def confirmar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        if not await self._somente_autor(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        compradas, falhas, gasto_total = [], [], 0
        for personagem in self._personagens_livres:
            ok, mensagem = await gacha.comprar_com_revelacao(self.guild_id, personagem["id"], interaction.user)
            if ok:
                compradas.append(personagem["nome"])
                gasto_total += db.PRECOS_LOJA[personagem["raridade"]]
            else:
                falhas.append(f"{personagem['nome']}: {mensagem}")
        resumo = f"✅ Compradas {len(compradas)}/{len(self._personagens_livres)} personagem(ns) de **{self.serie}** por {gasto_total} WiShards."
        if falhas:
            resumo += "\n❌ " + "\n❌ ".join(falhas[:10])
            if len(falhas) > 10:
                resumo += f"\n... e mais {len(falhas) - 10} falha(s)."
        await interaction.edit_original_response(content=resumo, view=None)

    @discord.ui.button(label="Cancelar", emoji="❌", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        if not await self._somente_autor(interaction):
            return
        await interaction.response.edit_message(content="Cancelado.", view=None)


class _ViewEscolherMergeAlvo(discord.ui.View):
    """2º passo do Merge (2026-09-02, pedido do usuário: "5 da msm raridade
    por 1 da msm raridade disponivel, a escolha") - até 25 personagens
    LIVRES (`db.personagens_livres_por_raridade`, mesma fonte que a Loja
    usa pra "Comprar") da mesma raridade das 5 sacrificadas; `economia.
    executar_merge` só roda quando o jogador escolhe uma."""

    def __init__(self, guild_id, ids_sacrificio, estrelas, personagens):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self._ids_sacrificio = ids_sacrificio
        self._personagens = personagens
        select = discord.ui.Select(
            placeholder=f"Receber qual {estrelas}...",
            options=[
                discord.SelectOption(label=p["nome"][:100], description=f"#{p['id']}", value=str(indice))
                for indice, p in enumerate(personagens)
            ],
        )
        select.callback = self._escolher
        self.add_item(select)

    async def _escolher(self, interaction: discord.Interaction):
        escolhida = self._personagens[int(interaction.data["values"][0])]
        ok, mensagem = await asyncio.to_thread(
            economia.executar_merge, self.guild_id, interaction.user.id, self._ids_sacrificio, escolhida["id"],
        )
        if ok:
            # 🔥 `to_thread` (2026-09-01) - `atualizar_snapshot_bonus` escaneia
            # a coleção INTEIRA, mesma classe de bug "GAIA não respondeu a
            # tempo" já corrigida em Auto-Party/Cidade/Personagem (SQLite
            # síncrono bloquearia o event loop do bot inteiro sem isso).
            await asyncio.to_thread(cidade.atualizar_snapshot_bonus, self.guild_id, interaction.user.id)
            await asyncio.to_thread(series_favoritas.recalcular_bonus, self.guild_id, interaction.user.id)
        await interaction.response.edit_message(content=mensagem, view=None)


class _ViewEscolherRanking(discord.ui.View):
    """Seletor de métrica pro `/ranking` (2026-09-02, "rankings expandidos"
    - Seção 25 do plano original) - Coleção/Soulmates/Torre, cada uma 1
    query barata de 1 tabela só (`db.ranking_guild`)."""

    def __init__(self, guild_id):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        select = discord.ui.Select(
            placeholder="Ranking de qual métrica?",
            options=[
                discord.SelectOption(label=nome, value=metrica)
                for metrica, nome in db.RANKINGS_DISPONIVEIS.items()
            ],
        )
        select.callback = self._escolheu
        self.add_item(select)
        self._select = select

    async def _escolheu(self, interaction: discord.Interaction):
        metrica = self._select.values[0]
        ranking = await asyncio.to_thread(db.ranking_guild, self.guild_id, metrica, 25)
        await interaction.response.edit_message(
            content=consulta.formatar_ranking(interaction.guild, ranking, metrica), view=None,
        )


def _descricao_personagem_dropdown(personagem, guild_id, user_id, contexto_lote=None):
    """`(texto, emoji)` PADRÃO de uma personagem num select - ícone de
    categoria + CP + Nível + Afinidade (2026-08-30, pedido do usuário: "no
    dropdwon de ver personagem tem q informar o icone da classe, CP, lv e
    afinidade. Tem varios locais q repetem esse padrao, pq vc n esta
    usando 1 p tudo?") - ÚNICO ponto que monta esse texto no pacote
    inteiro, reaproveitado por TODO select que lista personagens
    possuídas ("🔍 Personagem"/"🔄 Trocar de personagem", Merge, Party
    Adicionar/Remover) - trocar o formato aqui atualiza todos de uma vez,
    nunca precisa caçar duplicata de novo.

    `contexto_lote` (opcional, de `torre._contexto_lote`) - evita N+1 de
    query ao montar uma LISTA inteira (até 25 opções): quem monta o select
    pré-carrega 1x e passa aqui, em vez de cada personagem abrir suas
    próprias conexões SQLite (mesmo problema já corrigido no Auto-Party)."""
    niveis, bonus_global, cache_classe, bonus_series = contexto_lote or (None, None, None, None)
    nivel = niveis.get(personagem["id"], 1) if niveis is not None else None
    power, nivel_resolvido, categoria = torre.power_personagem(
        personagem, guild_id, user_id, nivel=nivel, bonus_global=bonus_global, cache_bonus_classe=cache_classe,
        bonus_series=bonus_series,
    )
    afinidade_atual = personagem.get("afinidade", 1)
    texto = (
        f"#{personagem['id']} · {gacha.estrelas_por_raridade(personagem['raridade'])} · "
        f"Nv.{nivel_resolvido} · CP {power:.0f} · 💞{afinidade_atual}"
    )
    return texto, torre.icone_categoria(categoria)


class _ViewSelecionarPersonagem(discord.ui.View):
    """Select genérico de até 25 personagens (teto do Discord) - usado
    pelo botão "Merge" do hub e pela Party. `ao_selecionar
    (interaction, lista_de_personagens)` recebe SEMPRE uma lista (1 item
    se `max_values=1`, N se for multi-select tipo Merge) - quem chama
    decide o que fazer com ela."""

    def __init__(self, personagens, placeholder, ao_selecionar, min_values=1, max_values=1, descricao=None):
        """`descricao` (opcional, recebe a personagem, devolve `(texto,
        emoji_ou_None)`) - default é o texto simples sem ícone (fallback
        genérico pra quando quem chama não tem `guild_id`/`user_id` à
        mão); todo caller de verdade passa `_descricao_personagem_dropdown`
        (acima) via closure."""
        super().__init__(timeout=120)
        self._personagens = personagens
        self._ao_selecionar = ao_selecionar
        descricao = descricao or (lambda p: (f"#{p['id']} · {gacha.estrelas_por_raridade(p['raridade'])}", None))
        options = []
        for indice, p in enumerate(personagens):
            texto, emoji = descricao(p)
            options.append(discord.SelectOption(
                label=p["nome"][:100], description=texto[:100], value=str(indice), emoji=emoji,
            ))
        select = discord.ui.Select(placeholder=placeholder, min_values=min_values, max_values=max_values, options=options)
        select.callback = self._selecionou
        self.add_item(select)

    async def _selecionou(self, interaction: discord.Interaction):
        indices = [int(v) for v in interaction.data["values"]]
        await self._ao_selecionar(interaction, [self._personagens[i] for i in indices])


class _ViewConfirmar(discord.ui.View):
    """Sim/Não genérico - `ao_confirmar(interaction)` só roda no "Sim".
    `ao_cancelar` (opcional) roda no "Não" em vez do padrão (apagar a
    mensagem) - usado quando cancelar deve VOLTAR pra uma tela anterior
    (2026-08-30, ex.: Divorciar dentro do card "🔍 Personagem" - cancelar
    não pode apagar o card, tem que voltar pra ele)."""

    def __init__(self, ao_confirmar, ao_cancelar=None):
        super().__init__(timeout=60)
        self._ao_confirmar = ao_confirmar
        self._ao_cancelar = ao_cancelar

    @discord.ui.button(label="Sim, confirmar", style=discord.ButtonStyle.danger)
    async def sim(self, interaction: discord.Interaction, botao: discord.ui.Button):
        await self._ao_confirmar(interaction)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def nao(self, interaction: discord.Interaction, botao: discord.ui.Button):
        if self._ao_cancelar:
            await self._ao_cancelar(interaction)
        else:
            await interaction.response.edit_message(content="Cancelado.", view=None)


# 🔥 Teto de opções pros dropdowns SEM nível máximo natural (Treinamento
# Global/Potencial da Coleção, 2026-08-30) - 25 é o limite de verdade de
# um `discord.ui.Select` (API do Discord), não um palpite de balanceamento.
_TETO_OPCOES_DROPDOWN_LOJA = 25


class _ViewEscolherAlvo(discord.ui.View):
    """Select de "até qual nível/Afinidade ir", pulando degraus (2026-08-30,
    pedido do usuário: "o botao de upar nivel e afinidade tem de ser um
    dropdown, p permitir pular ate o maximo. A pessoa escolhe o nivel
    alvo, vc retorna o custo com um botao de confirmar") - reaproveitado
    por "Upar Nível" (WiShards) e "Aumentar Afinidade" (Soulstone) do
    card "🔍 Personagem", só muda o range/custo/unidade/rótulo.
    `custo_total_fn(alvo)` já soma TODOS os degraus de onde a personagem
    está até `alvo` - quem chama decide a fórmula exata.

    🔥 `saldo_atual` opcional (2026-08-30, pedido do usuário: "tem q
    informar no dropdwon qnd q possuo") - aparece no placeholder do select
    (visível ANTES de abrir o dropdown), ex.: "Você tem 1.234 WiShards -
    escolha o Nível alvo...". Reaproveitado também pela Loja (Treinamento
    Global/Potencial da Coleção, mesmo dia, "tbm tem de permitr comprar
    varios leveis por vez... informando custo e qnt possuo") - essas telas
    usam `content` (texto puro) em vez de `embed`, então `_selecionou`
    passou a atualizar UM dos dois, o que a mensagem original tiver."""

    def __init__(self, rotulo, valor_atual, valor_maximo, custo_total_fn, unidade, ao_confirmar, ao_cancelar, saldo_atual=None):
        super().__init__(timeout=120)
        self._custo_total_fn = custo_total_fn
        self._unidade = unidade
        self._ao_confirmar = ao_confirmar
        self._ao_cancelar = ao_cancelar
        options = [
            discord.SelectOption(
                label=f"{rotulo} {alvo}", value=str(alvo),
                description=f"Custo total: {_fmt_numero(custo_total_fn(alvo))} {unidade}"[:100],
            )
            for alvo in range(valor_atual + 1, valor_maximo + 1)
        ]
        if saldo_atual is not None:
            placeholder = f"Você tem {_fmt_numero(saldo_atual)} {unidade} - escolha o {rotulo} alvo..."
        else:
            placeholder = f"Escolha o {rotulo} alvo..."
        select = discord.ui.Select(placeholder=placeholder[:150], options=options, row=0)
        select.callback = self._selecionou
        self.add_item(select)
        cancelar = discord.ui.Button(label="Cancelar", style=discord.ButtonStyle.secondary, row=1)
        cancelar.callback = self._cancelar_direto
        self.add_item(cancelar)

    async def _selecionou(self, interaction: discord.Interaction):
        alvo = int(interaction.data["values"][0])
        custo = self._custo_total_fn(alvo)

        async def _confirmar(interacao_confirmacao):
            await self._ao_confirmar(interacao_confirmacao, alvo)

        view_confirmar = _ViewConfirmar(_confirmar, ao_cancelar=self._ao_cancelar)
        texto = f"Ir até aqui custa **{_fmt_numero(custo)} {self._unidade}** - confirma?"
        embed_atual = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed_atual:
            embed_atual = embed_atual.copy()
            embed_atual.description = texto
            await interaction.response.edit_message(embed=embed_atual, view=view_confirmar)
        else:
            await interaction.response.edit_message(content=texto, view=view_confirmar)

    async def _cancelar_direto(self, interaction: discord.Interaction):
        await self._ao_cancelar(interaction)


class _ModalBuscarPersonagem(discord.ui.Modal):
    """Busca por nome ANTES do select (2026-08-30, pedido do usuário: "ja
    tenho mais de 50 personagens, e discord so lista 25... msm eu n
    acertando nome, traz os mais proximos") - filtra a coleção INTEIRA
    (não só as primeiras 25) por proximidade de texto (`consulta.
    buscar_por_nome`) antes de montar o select, que continua limitado a 25
    pelo próprio Discord. Campo vazio cai no comportamento de sempre (os
    primeiros 25 da ordem de quem chama). Usado por Batalha (escolher
    personagem alheia pra desafiar) e Proteção - "🔍 Personagem" ganhou seu
    PRÓPRIO fluxo (`_ModalBuscarPosicaoOuNome`, 2026-09-02: navegação por
    posição/bloco não se encaixa mais nesse contrato de lista fechada de
    candidatos, não usa mais este Modal)."""

    nome = discord.ui.TextInput(label="Nome (pode ser parcial/aproximado)", required=False, max_length=100)

    def __init__(self, titulo, colecao, placeholder_select, ao_selecionar, descricao=None):
        super().__init__(title=titulo[:45])
        self._colecao = colecao
        self._placeholder_select = placeholder_select
        self._ao_selecionar = ao_selecionar
        self._descricao = descricao

    async def on_submit(self, interaction: discord.Interaction):
        nome = str(self.nome).strip()
        candidatos = consulta.buscar_por_nome(self._colecao, nome)
        if not candidatos:
            await interaction.response.send_message(
                f"Nenhuma personagem parecida com \"{self.nome}\" na sua coleção.", ephemeral=True,
            )
            return

        # 🔥 repassa `candidatos` (o pool INTEIRO da busca, não só quem foi
        # escolhido) pro `ao_selecionar` de quem chamou (2026-08-30, pedido
        # do usuário: "quero q o dropdown de selecionar personagem nao suma
        # ao escolher um") - `_ViewSelecionarPersonagem` continua com seu
        # contrato de 2 argumentos de sempre (Merge/Party/Prova não mudam).
        async def _selecionar_com_pool(interacao_selecao, personagens):
            await self._ao_selecionar(interacao_selecao, personagens, candidatos)

        view = _ViewSelecionarPersonagem(candidatos, self._placeholder_select, _selecionar_com_pool, descricao=self._descricao)
        # 🔥 `edit_message` funciona aqui porque o modal foi aberto a partir
        # de um CLIQUE DE BOTÃO (`interaction.response.send_modal`) - o
        # submit do modal carrega a mensagem original desse botão.
        await interaction.response.edit_message(content="Selecione:", view=view)


class _ModalBuscarPosicaoOuNome(discord.ui.Modal, title="Buscar personagem"):
    """"🔎 Buscar" do card "🔍 Personagem" (2026-09-02, pedido do usuário:
    "adicione um botão 🔎 Buscar que abra um modal do Discord permitindo
    informar o nome da personagem ou uma posição específica: digitando
    Megumin, abre diretamente a Megumin; digitando 2750, abre diretamente
    a personagem da posição 2750") - 1 campo só, resolvido em 2 modos:
    texto TODO dígito vira posição (1-indexed, igual ao rodapé "X/Y");
    qualquer outra coisa vira busca por nome (`consulta.buscar_por_nome`,
    MESMO algoritmo de sempre - substring primeiro, similaridade de texto
    depois) contra a coleção INTEIRA (`_posicao_por_nome`, mesma ordem de
    `db.colecao_do_usuario_paginada` - crítico: é a MESMA ordem usada pra
    numerar posição/montar bloco, senão o número mostrado não bateria com
    onde a navegação por seta/bloco realmente chega), ficando só com o
    MELHOR resultado (`limite=1`) - abre direto nela, sem lista
    intermediária pra escolher (diferente do "🔄 Trocar de personagem",
    que continua mostrando as opções do bloco atual)."""

    consulta_texto = discord.ui.TextInput(label="Nome ou posição (nº)", placeholder="Ex.: Megumin ou 2750", max_length=100)

    def __init__(self, view):
        super().__init__()
        self._view = view

    async def on_submit(self, interaction: discord.Interaction):
        # 🔥 `defer()` ANTES do `to_thread` (mesma classe de bug já
        # corrigida várias vezes nesta sessão - Batalha/Séries Favoritas) -
        # busca por nome carrega a coleção INTEIRA (`_posicao_por_nome`).
        await interaction.response.defer()
        texto = str(self.consulta_texto).strip()
        if not texto:
            await interaction.followup.send("Digite um nome ou uma posição.", ephemeral=True)
            return
        if texto.isdigit():
            posicao = int(texto)
            if posicao < 1:
                await interaction.followup.send("Posição inválida - use um número a partir de 1.", ephemeral=True)
                return
            indice_alvo = posicao - 1
        else:
            indice_alvo = await asyncio.to_thread(_posicao_por_nome, self._view.guild_id, self._view.autor_id, texto)
            if indice_alvo is None:
                await interaction.followup.send(f"Nenhuma personagem parecida com \"{texto}\" na sua coleção.", ephemeral=True)
                return
        ok = await self._view._ir_para(indice_alvo)
        if not ok:
            await interaction.followup.send("Você não tem mais nenhuma personagem.", ephemeral=True)
            return
        if self._view._indice_global != indice_alvo:
            self._view._status = f"⚠️ Só existem {self._view._total} personagem(ns) - mostrando a posição {self._view._indice_global + 1}."
        await interaction.edit_original_response(embed=self._view.montar_embed(), view=self._view)


def _posicao_por_nome(guild_id, user_id, nome):
    """Posição (0-indexed) do MELHOR resultado de `consulta.buscar_por_nome`
    dentro da MESMA ordem usada por `db.colecao_do_usuario_paginada`
    (crítico pra bater com a numeração "X/Y" e a navegação por bloco) -
    carrega a coleção INTEIRA (`limite` bem alto - mesmo espírito de custo
    de "carregar tudo pra buscar por nome" já aceito antes desta sessão
    pelo antigo fluxo de busca) só pra essa 1 busca pontual, `None` se
    nada bateu (corte de similaridade de `consulta.buscar_por_nome`)."""
    colecao_ordenada = db.colecao_do_usuario_paginada(guild_id, user_id, 0, 1_000_000)
    melhores = consulta.buscar_por_nome(colecao_ordenada, nome, limite=1)
    if not melhores:
        return None
    alvo_id = melhores[0]["id"]
    return next((i for i, p in enumerate(colecao_ordenada) if p["id"] == alvo_id), None)


class _ViewNivel(discord.ui.View):
    """Card completo (`consulta.embed_carta_personagem`) + upar Nível +
    upar Afinidade + Divorciar + Favoritar (2026-08-30) - usado pelo
    "🔍 Personagem" do hub, ÚNICO jeito de ver/gerenciar uma personagem
    específica (antigo botão "⬆️ Nível" removido do Perfil, que também
    deixou de existir - "botão de perfil é meio inutil, da p por todos os
    botoes e info dele ja no waifu"; Divorciar veio pro lado do Upar
    Nível a pedido do usuário: "pode mover o divorciar para o lado do
    upar nivel"; Favoritar veio do hub pro mesmo lugar depois: "move a
    funcao de favoritar para entro da personagem"; Upar Afinidade veio
    depois, gastando Soulstone em vez de WiShards - NUNCA compra Soulmate,
    que continua exclusivo de reencontro). Todos os botões reaproveitáveis
    pra usar várias vezes seguidas sem reabrir a busca, mesmo padrão de
    `_ViewTorre` - sempre leem estado FRESCO do banco a cada clique.

    🔥 Navegação por POSIÇÃO GLOBAL (2026-09-02, reescrita completa -
    pedido do usuário comparando com o Mudae: "consegue passar bem mais de
    25 profiles... quero passar de 25 e ter registro de posição") - em vez
    de acumular uma lista de candidatos cada vez maior (jeito antigo), a
    view guarda só a POSIÇÃO atual (`_indice_global`, 0-indexed) contra o
    TOTAL de verdade (`_total`, `db.contar_colecao_do_usuario`) e o BLOCO
    de até 25 personagens (`_bloco`, `db.colecao_do_usuario_paginada` com
    `offset`/`limite=25`) que contém essa posição - qualquer posição (2750,
    50000...) é 1 SELECT por `OFFSET`/`LIMIT` direto, nunca precisa
    carregar tudo. O select "🔄 Trocar de personagem" sempre reflete o
    BLOCO de 25 correspondente (posições 1-25 mostram 1-25, 26-50 mostram
    26-50, 93 mostra 76-100, 101 mostra 101-125...) e se reconstrói sozinho
    (`_atualizar_select_options`) toda vez que a posição muda de bloco.
    Navegação: "◀️"/"▶️" andam 1 posição (pedido original, 2026-08-30);
    "⏮️"/"⏭️" pulam um bloco INTEIRO de 25 (pedido novo); "🔎 Buscar" abre
    `_ModalBuscarPosicaoOuNome` pra pular direto por nome OU posição
    digitada. Os 3 (setas/blocos/busca) convergem no mesmo `_ir_para`."""

    def __init__(self, guild_id, autor_id, bloco, bloco_offset, idx_local, total):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.autor_id = autor_id
        self._bloco = bloco
        self._bloco_offset = bloco_offset
        self._idx_local = idx_local
        self._total = total
        self.personagem = bloco[idx_local]
        self._status = None

        self._select = discord.ui.Select(placeholder="🔄 Trocar de personagem...", options=[discord.SelectOption(label="-", value="0")], row=1)
        self._select.callback = self._trocar_personagem
        self.add_item(self._select)

        self._botao_bloco_anterior = discord.ui.Button(emoji="⏮️", style=discord.ButtonStyle.secondary, row=2)
        self._botao_bloco_anterior.callback = self._ir_bloco_anterior
        self.add_item(self._botao_bloco_anterior)
        self._botao_anterior = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary, row=2)
        self._botao_anterior.callback = self._navegar_anterior
        self.add_item(self._botao_anterior)
        self._botao_proximo = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary, row=2)
        self._botao_proximo.callback = self._navegar_proximo
        self.add_item(self._botao_proximo)
        self._botao_bloco_seguinte = discord.ui.Button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=2)
        self._botao_bloco_seguinte.callback = self._ir_bloco_seguinte
        self.add_item(self._botao_bloco_seguinte)
        self._botao_buscar = discord.ui.Button(label="Buscar", emoji="🔎", style=discord.ButtonStyle.primary, row=2)
        self._botao_buscar.callback = self._abrir_busca
        self.add_item(self._botao_buscar)

        self._atualizar_select_options()

    @classmethod
    async def criar(cls, guild_id, autor_id, indice_global=0):
        """Fábrica assíncrona (`__init__` não pode ser `async` mas precisa
        do bloco/total já buscados) - `None` se a coleção estiver vazia."""
        total = await asyncio.to_thread(db.contar_colecao_do_usuario, guild_id, autor_id)
        if total <= 0:
            return None
        indice_global = max(0, min(total - 1, indice_global))
        bloco_offset = (indice_global // 25) * 25
        bloco = await asyncio.to_thread(db.colecao_do_usuario_paginada, guild_id, autor_id, bloco_offset, 25)
        if not bloco:
            return None
        idx_local = min(indice_global - bloco_offset, len(bloco) - 1)
        return cls(guild_id, autor_id, bloco, bloco_offset, idx_local, total)

    @property
    def _indice_global(self):
        return self._bloco_offset + self._idx_local

    def _atualizar_select_options(self):
        contexto_lote = torre._contexto_lote(self.guild_id, self.autor_id)
        options = []
        for indice, p in enumerate(self._bloco):
            texto, emoji = _descricao_personagem_dropdown(p, self.guild_id, self.autor_id, contexto_lote)
            posicao_absoluta = self._bloco_offset + indice + 1
            options.append(discord.SelectOption(
                label=f"{posicao_absoluta}. {p['nome']}"[:100], description=texto[:100], value=str(indice),
                emoji=emoji, default=(indice == self._idx_local),
            ))
        self._select.options = options
        self._select.placeholder = f"🔄 Trocar de personagem (bloco {self._bloco_offset + 1}-{self._bloco_offset + len(self._bloco)})..."

    async def _ir_para(self, indice_global):
        """Núcleo de TODA navegação (setas/bloco/busca) - recarrega o
        BLOCO sob demanda só quando a posição alvo cai fora do bloco já
        carregado (`db.colecao_do_usuario_paginada`, 1 SELECT com OFFSET/
        LIMIT direto, nunca precisa passar pelas posições intermediárias).
        Recalcula `_total` do zero a cada chamada (COUNT(*) barato) -
        cobre a coleção ter mudado de tamanho (troca/claim/divórcio) desde
        a última vez que essa view foi montada. `False` só se a coleção
        ficou vazia (sem personagem nenhuma pra mostrar)."""
        total = await asyncio.to_thread(db.contar_colecao_do_usuario, self.guild_id, self.autor_id)
        if total <= 0:
            self._total = 0
            return False
        indice_global = max(0, min(total - 1, indice_global))
        novo_bloco_offset = (indice_global // 25) * 25
        if novo_bloco_offset != self._bloco_offset:
            novo_bloco = await asyncio.to_thread(
                db.colecao_do_usuario_paginada, self.guild_id, self.autor_id, novo_bloco_offset, 25,
            )
            if not novo_bloco:
                self._total = total
                return False
            self._bloco = novo_bloco
            self._bloco_offset = novo_bloco_offset
        self._total = total
        self._idx_local = min(indice_global - novo_bloco_offset, len(self._bloco) - 1)
        self.personagem = self._bloco[self._idx_local]
        self._status = None
        self._atualizar_select_options()
        return True

    async def _renderizar(self, interaction: discord.Interaction):
        if self._total <= 0:
            await interaction.response.edit_message(content="Você não tem mais nenhuma personagem.", embed=None, view=None)
            return
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    async def _trocar_personagem(self, interaction: discord.Interaction):
        escolhido_local = int(interaction.data["values"][0])
        await self._ir_para(self._bloco_offset + escolhido_local)
        await self._renderizar(interaction)

    async def _navegar_anterior(self, interaction: discord.Interaction):
        await self._ir_para(self._indice_global - 1)
        await self._renderizar(interaction)

    async def _navegar_proximo(self, interaction: discord.Interaction):
        await self._ir_para(self._indice_global + 1)
        await self._renderizar(interaction)

    async def _ir_bloco_anterior(self, interaction: discord.Interaction):
        """Pula pro INÍCIO do bloco anterior de 25 (mesmo padrão de
        `consulta.ViewColecao` - página vira sempre no primeiro item dela,
        não desloca por 25 a partir da posição atual)."""
        await self._ir_para(max(0, self._bloco_offset - 25))
        await self._renderizar(interaction)

    async def _ir_bloco_seguinte(self, interaction: discord.Interaction):
        await self._ir_para(self._bloco_offset + 25)
        await self._renderizar(interaction)

    async def _abrir_busca(self, interaction: discord.Interaction):
        await interaction.response.send_modal(_ModalBuscarPosicaoOuNome(self))

    def montar_embed(self):
        self._botao_anterior.disabled = self._indice_global <= 0
        self._botao_proximo.disabled = self._indice_global >= self._total - 1
        self._botao_bloco_anterior.disabled = self._bloco_offset <= 0
        self._botao_bloco_seguinte.disabled = self._bloco_offset + 25 >= self._total
        nivel_atual = db.nivel_personagem(self.guild_id, self.autor_id, self.personagem["id"])
        custo = db.custo_proximo_nivel(self.personagem["raridade"], nivel_atual)
        embed = consulta.embed_carta_personagem(self.personagem)
        # 🔥 Indicador de posição "X/Y" (2026-09-02, pedido do usuário,
        # comparando com o "43/48" do Mudae).
        embed.set_footer(text=f"{self._indice_global + 1}/{self._total}")
        # 🔥 CP (2026-08-30, achado do usuário: "Qnd seleciona um
        # personagem pelo botao personagem, mostra a classe, CP e lv" -
        # classe/nível já apareciam, CP estava faltando).
        power, _nivel_ignorado, categoria = torre.power_personagem(self.personagem, self.guild_id, self.autor_id)
        embed.add_field(name="CP", value=f"{torre.icone_categoria(categoria)} {power:.0f}", inline=True)
        if custo is None:
            embed.add_field(name="Nível", value=f"{nivel_atual} (máximo)", inline=True)
            self.upar.disabled = True
        else:
            embed.add_field(name="Nível", value=f"{nivel_atual} (próximo: {custo} WiShards)", inline=True)
            self.upar.disabled = False
        # 🔥 Upar Afinidade com Soulstone (2026-08-30) - custo = nível-alvo
        # (pedido literal do usuário). NUNCA compra Soulmate - isso
        # continua exclusivo de reencontro (`gacha._resolver_resultado`).
        afinidade_atual = db.afinidade(self.guild_id, self.autor_id, self.personagem["id"])
        custo_afinidade = db.custo_proximo_afinidade(afinidade_atual)
        if custo_afinidade is None:
            embed.add_field(name="Afinidade", value=f"{afinidade_atual} (máxima)", inline=True)
            self.upar_afinidade.disabled = True
        else:
            embed.add_field(name="Afinidade", value=f"{afinidade_atual} (próximo: {custo_afinidade} Soulstone)", inline=True)
            self.upar_afinidade.disabled = False
        favorita = db.eh_favorita(self.guild_id, self.autor_id, self.personagem["id"])
        self.favoritar.label = "Desfavoritar" if favorita else "Favoritar"
        self.favoritar.style = discord.ButtonStyle.success if favorita else discord.ButtonStyle.secondary
        # 🔥 Estatística de Torre (2026-09-01, pedido do usuário: "saber
        # quais personagens mais subiram torre") - só aparece se já
        # contribuiu pra pelo menos 1 vitória, sem poluir o card de quem
        # nunca usou a Torre.
        andares_vencidos = db.andares_vencidos_personagem(self.guild_id, self.autor_id, self.personagem["id"])
        if andares_vencidos:
            embed.add_field(name="🗼 Andares vencidos", value=str(andares_vencidos), inline=True)
        if self._status:
            embed.description = self._status
        return embed

    @discord.ui.button(label="Upar Nível", emoji="⬆️", style=discord.ButtonStyle.success)
    async def upar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        """🔥 Dropdown pra escolher o nível-alvo (2026-08-30, pedido do
        usuário: "o botao de upar nivel e afinidade tem de ser um
        dropdown, p permitir pular ate o maximo") - substitui o antigo
        "+1 por clique"; `db.subir_nivel_ate` já soma o custo de TODOS os
        degraus até o alvo."""
        nivel_atual = db.nivel_personagem(self.guild_id, self.autor_id, self.personagem["id"])
        raridade = self.personagem["raridade"]

        async def _confirmar(interacao_confirmacao, alvo):
            ok, mensagem = db.subir_nivel_ate(self.guild_id, interacao_confirmacao.user.id, self.personagem["id"], alvo)
            if ok:
                await asyncio.to_thread(cidade.atualizar_snapshot_bonus, self.guild_id, interacao_confirmacao.user.id)
                await asyncio.to_thread(series_favoritas.recalcular_bonus, self.guild_id, interacao_confirmacao.user.id)
            self._status = f"{'✅' if ok else '❌'} {mensagem}"
            await interacao_confirmacao.response.edit_message(embed=self.montar_embed(), view=self)

        async def _cancelar(interacao_cancelamento):
            await interacao_cancelamento.response.edit_message(embed=self.montar_embed(), view=self)

        view_escolher = _ViewEscolherAlvo(
            "Nível", nivel_atual, db.NIVEL_MAXIMO_PERSONAGEM,
            lambda alvo: db.custo_total_ate_nivel(raridade, nivel_atual, alvo),
            "WiShards", _confirmar, _cancelar,
            saldo_atual=db.saldo_wishards(self.guild_id, self.autor_id),
        )
        await interaction.response.edit_message(embed=self.montar_embed(), view=view_escolher)

    @discord.ui.button(label="Aumentar Afinidade", emoji="💕", style=discord.ButtonStyle.success)
    async def upar_afinidade(self, interaction: discord.Interaction, botao: discord.ui.Button):
        """Mesmo dropdown de "Upar Nível", pra Afinidade/Soulstone."""
        afinidade_atual = db.afinidade(self.guild_id, self.autor_id, self.personagem["id"])

        async def _confirmar(interacao_confirmacao, alvo):
            ok, mensagem = db.subir_afinidade_ate(self.guild_id, interacao_confirmacao.user.id, self.personagem["id"], alvo)
            if ok:
                await asyncio.to_thread(cidade.atualizar_snapshot_bonus, self.guild_id, interacao_confirmacao.user.id)
                await asyncio.to_thread(series_favoritas.recalcular_bonus, self.guild_id, interacao_confirmacao.user.id)
            self._status = f"{'✅' if ok else '❌'} {mensagem}"
            await interacao_confirmacao.response.edit_message(embed=self.montar_embed(), view=self)

        async def _cancelar(interacao_cancelamento):
            await interacao_cancelamento.response.edit_message(embed=self.montar_embed(), view=self)

        view_escolher = _ViewEscolherAlvo(
            "Afinidade", afinidade_atual, db.NIVEL_MAXIMO_AFINIDADE,
            lambda alvo: db.custo_total_ate_afinidade(afinidade_atual, alvo),
            "Soulstone", _confirmar, _cancelar,
            saldo_atual=db.saldo_soulstone(self.guild_id, self.autor_id),
        )
        await interaction.response.edit_message(embed=self.montar_embed(), view=view_escolher)

    @discord.ui.button(label="Favoritar", emoji="⭐", style=discord.ButtonStyle.secondary)
    async def favoritar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        if db.eh_favorita(self.guild_id, self.autor_id, self.personagem["id"]):
            db.desfavoritar(self.guild_id, self.autor_id, self.personagem["id"])
            self._status = f"Desmarcada como favorita: **{self.personagem['nome']}**."
        else:
            db.favoritar(self.guild_id, self.autor_id, self.personagem["id"])
            self._status = f"⭐ Marcada como favorita: **{self.personagem['nome']}**."
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    @discord.ui.button(label="Divorciar", emoji="💔", style=discord.ButtonStyle.danger)
    async def divorciar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        if db.eh_favorita(self.guild_id, self.autor_id, self.personagem["id"]):
            async def _confirmar(interacao_confirmacao):
                await self._divorciar_de_verdade(interacao_confirmacao)

            async def _cancelar(interacao_cancelamento):
                await interacao_cancelamento.response.edit_message(embed=self.montar_embed(), view=self)

            embed_aviso = self.montar_embed()
            embed_aviso.description = "⚠️ Essa personagem está favoritada - tem certeza que quer divorciar mesmo assim?"
            view_confirmar = _ViewConfirmar(_confirmar, ao_cancelar=_cancelar)
            await interaction.response.edit_message(embed=embed_aviso, view=view_confirmar)
            return
        await self._divorciar_de_verdade(interaction)

    @discord.ui.button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def atualizar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        """2026-09-01, pedido do usuário: "botão de atualizar nos
        Personagens, Torre" - reconstrói o card com dado FRESCO do banco
        (CP/Nível/Afinidade podem ter mudado por outra ação enquanto o
        card estava aberto) sem precisar fechar e reabrir."""
        self._status = None
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    async def _divorciar_de_verdade(self, interaction: discord.Interaction):
        ok, recompensa, xp = db.divorciar(self.guild_id, self.personagem["id"], interaction.user.id)
        if ok:
            await asyncio.to_thread(cidade.atualizar_snapshot_bonus, self.guild_id, interaction.user.id)
            await asyncio.to_thread(series_favoritas.recalcular_bonus, self.guild_id, interaction.user.id)
            mensagem = f"💔 Personagem liberada da sua coleção - +{recompensa} WiShards, +{xp} XP de Progressão (Afinidade preservada, um resgate futuro continua com o vínculo)."
        else:
            mensagem = "Você não tem essa personagem nesse servidor."
        await interaction.response.edit_message(content=mensagem, embed=None, view=None)


def _fmt_numero(valor, casas_decimais=0):
    """Formato numérico BR (ponto de milhar, vírgula decimal) - pedido do
    usuário no exemplo do painel da Cidade ("CP: 191.181", "+0,XX
    Soulstone/h")."""
    parte_inteira, _, parte_decimal = f"{valor:,.{casas_decimais}f}".partition(".")
    parte_inteira = parte_inteira.replace(",", ".")
    return f"{parte_inteira},{parte_decimal}" if casas_decimais else parte_inteira


def _embed_cidade(resultado):
    """Status da Cidade v2 (2026-08-30, efeitos diferenciados por área) -
    `resultado` vem de `cidade.coletar_producao_pendente`. Mostra a
    CAPACIDADE ATUAL de cada área (`taxas_por_funcao` - independente de
    quanto tempo passou desde a última visita, pedido do usuário: "o
    painel deve mostrar sempre o bônus atual por hora, independentemente
    de quanto tempo passou desde a última coleta") - só o resumo do topo
    mostra o ACUMULADO desde a última visita."""
    embed = discord.Embed(title="🏙️ Cidade", color=_COR_HUB)
    if resultado["primeira_visita"]:
        embed.description = (
            "Primeira vez aqui - o relógio de produção começou a contar agora. "
            "Volte depois pra coletar o que suas personagens fora da Party produziram."
        )
        return embed
    embed.description = (
        f"Desde sua última visita ({resultado['horas']}h atrás):\n"
        f"+{resultado['wishards']} WiShards\n"
        f"+{resultado['xp']} XP de Progressão\n"
        f"+{resultado['soulstone']} Soulstone"
    )
    embed.add_field(
        name="👑 Bônus da Coleção",
        value=(
            f"CP da coleção: {_fmt_numero(resultado['cp_total'])}\n"
            f"Conversão: {cidade.TAXA_BONUS_COLECAO * 100:.0f}%\n"
            f"Bônus: +{_fmt_numero(resultado['bonus_colecao_fixo'])} CP fixo para a Party"
        ),
        inline=False,
    )
    # 🔥 Militar/Arcano/Administração são bônus AO VIVO (nunca "/h" - não
    # acumulam no tempo, são um modificador de estado sempre ativo);
    # Saúde/Cultura/Comércio são taxa POR HORA de verdade (acumulam).
    _TEXTO_BONUS_POR_FUNCAO = {
        "Militar": lambda t: f"+{_fmt_numero(t)} CP fixo para a Party",
        "Saúde": lambda t: f"+{_fmt_numero(t, 2)} Soulstone/h",
        "Cultura": lambda t: f"+{_fmt_numero(t, 1)} XP de Progressão/h",
        "Administração": lambda t: f"+{_fmt_numero(t * 100, 2)}% de eficiência das outras áreas",
        "Comércio": lambda t: f"+{_fmt_numero(t, 1)} WiShards/h",
        "Arcano": lambda t: f"+{_fmt_numero(t * 100, 2)}% CP para a Party",
    }
    # 🔥 SEMPRE lista as 6 áreas, mesmo sem NENHUM trabalhador ainda
    # (2026-09-01, pedido do usuário: "um local que detalhe todos os
    # bônus ativos e alvos") - antes pulava área vazia (`if not dados:
    # continue`), então o jogador só via o que JÁ tinha, sem saber o que
    # cada área faz antes de mandar a 1ª personagem pra lá.
    for funcao in cidade.FUNCOES_CIDADE:
        dados = resultado["por_funcao"].get(funcao) or {"qtd": 0, "cp": 0.0}
        taxa_atual = resultado["taxas_por_funcao"].get(funcao, 0.0)
        texto_bonus = _TEXTO_BONUS_POR_FUNCAO[funcao](taxa_atual)
        embed.add_field(
            name=f"{cidade.icone_funcao(funcao)} {funcao}",
            value=f"Personagens: {dados['qtd']}\nCP: {_fmt_numero(dados['cp'])}\nBônus: {texto_bonus}",
            inline=True,
        )
    embed.set_footer(text=f"CP total trabalhando: {_fmt_numero(resultado['cp_total'])}")
    return embed


def _embed_torre(contexto, resultado_final=False):
    """`resultado_final=True` só depois de clicar "Subir" (já com recompensa/
    novo andar, se venceu) - antes disso é só PREVIEW (`torre.preview_andar`,
    sem efeito colateral)."""
    andar = contexto["andar"]
    cor = 0x2ECC71 if contexto["venceu"] else 0xE74C3C
    titulo = f"🗼 Torre - Andar {andar}"
    embed = discord.Embed(title=titulo, color=cor)
    embed.add_field(name="Power da Party", value=f"{contexto['power_total']:.0f}", inline=True)
    embed.add_field(name="Power necessário", value=f"{contexto['alvo']}", inline=True)
    restricao_txt = torre.descricao_restricao(contexto["restricao"])
    if contexto.get("restricao_ignorada"):
        restricao_txt += " · 🗝️ ignorada (Chave da Torre)"
    elif not contexto["restricao_ok"]:
        restricao_txt += " ❌ (não cumprida)"
    embed.add_field(name="Restrição do andar", value=restricao_txt, inline=False)
    linhas_membros = []
    for m in contexto["membros"]:
        vinculo = "💞 Soulmate" if m["is_soulmate"] else f"❤️{m['afinidade']}"
        icone = torre.icone_categoria(m["categoria_combate"])
        linhas_membros.append(f"{icone} - {m['nome']} - Nv.{m['nivel']} · {vinculo} · CP {m['power']:.0f}")
    embed.add_field(name="Sua Party", value="\n".join(linhas_membros), inline=False)
    if resultado_final:
        if contexto["venceu"]:
            embed.description = f"✅ **Vitória!** +{contexto['recompensa']} WiShards (saldo: {contexto['novo_saldo']}), +{contexto['xp_ganho']} XP de Progressão - avançou pro andar {contexto['novo_andar']}."
        else:
            embed.description = "❌ **Derrota.** Suba de nível/Afinidade ou ajuste a Party e tente de novo - sem RNG, sem cooldown."
    return embed


class _ViewTorre(discord.ui.View):
    """Tela da Torre (2026-08-30) - botão "Subir" sem confirmação extra (a
    resolução é determinística e SEM CUSTO de tentar - perder não consome
    nada, então não existe risco real a confirmar, diferente da Prova de
    Soulmate que tem RNG/cooldown). "Auto-Party" (mesmo dia, pedido do
    usuário: "coloca um auto-party... pega as restrições do andar p montar
    a pt com maior CP") também sem confirmação - substitui a Party inteira
    na hora, mas é sempre reversível (rodar de novo/editar na mão)."""

    def __init__(self, guild_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id

    @discord.ui.button(label="Subir", emoji="🗼", style=discord.ButtonStyle.primary)
    async def subir(self, interaction: discord.Interaction, botao: discord.ui.Button):
        ok, erro, contexto = torre.tentar_andar(self.guild_id, interaction.user.id)
        if not ok:
            await interaction.response.send_message(erro, ephemeral=True)
            return
        embed = _embed_torre(contexto, resultado_final=True)
        # 🔥 A MESMA view serve pra tentativa seguinte, vença ou perca -
        # `tentar_andar` sempre lê o andar atual fresco do banco
        # (`db.andar_atual_torre`), então clicar "Subir" de novo já ataca
        # o próximo andar automaticamente se o anterior foi vencido.
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Auto-Party", emoji="🤖", style=discord.ButtonStyle.secondary)
    async def auto_party(self, interaction: discord.Interaction, botao: discord.ui.Button):
        # 🔥 `defer()` + `asyncio.to_thread` (2026-08-30, achado do usuário:
        # primeiro "atualiza a pt logicamente mas n troca visualmente, da
        # erro de GAIA não respondeu a tempo", depois - MESMO com o N+1 de
        # query já cortado (ver `torre.power_personagem`) e o `defer()` já
        # em produção - "Auto-party esta demorando e as vezes cai em GAIA
        # não respondeu a tempo" de novo. Causa raiz real: `db.conexao()` é
        # SQLite SÍNCRONO, então `montar_auto_party` varrendo a coleção
        # inteira BLOQUEIA o event loop do processo INTEIRO enquanto roda -
        # não só esta interação. Se OUTRA interação (de QUALQUER usuário,
        # em QUALQUER comando) for despachada durante esse bloqueio,
        # inclusive o PRÓPRIO `defer()` dela nunca chega a ser enviado a
        # tempo, porque a corrotina nem começa a rodar até o bloqueio
        # liberar o loop - por isso `defer()` sozinho não resolvia de
        # verdade. `asyncio.to_thread` roda a varredura numa thread
        # separada, deixando o loop livre pro resto do bot continuar
        # respondendo (inclusive a comandos de OUTROS usuários) enquanto
        # isso acontece.
        await interaction.response.defer()
        ok, erro, _qtd = await asyncio.to_thread(torre.montar_auto_party, self.guild_id, interaction.user.id)
        if not ok:
            await interaction.followup.send(erro, ephemeral=True)
            return
        await asyncio.to_thread(cidade.atualizar_snapshot_bonus, self.guild_id, interaction.user.id)
        await asyncio.to_thread(series_favoritas.recalcular_bonus, self.guild_id, interaction.user.id)
        _ok, _erro, contexto = torre.preview_andar(self.guild_id, interaction.user.id)
        embed = _embed_torre(contexto)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def atualizar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        """2026-09-01, pedido do usuário: "botão de atualizar nos
        Personagens, Torre" - recalcula o preview com Power/Nível/Party
        FRESCOS do banco (podem ter mudado desde que o painel foi aberto,
        ex.: upou nível em outra tela) sem precisar tentar o andar."""
        ok, erro, contexto = torre.preview_andar(self.guild_id, interaction.user.id)
        if not ok:
            await interaction.response.send_message(erro, ephemeral=True)
            return
        await interaction.response.edit_message(embed=_embed_torre(contexto), view=self)

    @discord.ui.button(label="Estatísticas", emoji="📊", style=discord.ButtonStyle.secondary)
    async def estatisticas(self, interaction: discord.Interaction, botao: discord.ui.Button):
        """2026-09-01, pedido do usuário: "estatísticas de participação
        com sucesso na torre por personagens, p saber quais personagens
        mais subiram torre" - top 10 por andares vencidos."""
        top = await asyncio.to_thread(db.estatisticas_torre_top, self.guild_id, interaction.user.id, 10)
        if not top:
            await interaction.response.send_message("Nenhuma personagem venceu um andar da Torre ainda.", ephemeral=True)
            return
        embed = discord.Embed(title="📊 Torre - Personagens que mais venceram andares", color=_COR_HUB)
        embed.description = "\n".join(f"{indice + 1}. **{linha['nome']}** - {linha['andares_vencidos']} andar(es)" for indice, linha in enumerate(top))
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ViewColecaoHub(consulta.ViewColecao):
    """Estende `ViewColecao` (paginação ◀️/▶️ já pronta) com um SELECT de
    modo (painel `/pandora`) - troca a fonte de dado sem sair da mesma
    mensagem. `/colecao`/`/populares`/`/colecao_disponiveis` continuam
    usando `ViewColecao`/`ViewClaimPendentes` puros, sem esse select - só
    o painel novo precisa alternar modo depois de aberto."""

    def __init__(self, guild, membro, colecao_minha_precomputada=None):
        self._guild = guild
        self._membro = membro
        self._modo = "minha"
        super().__init__(*self._dados_do_modo(colecao_minha_precomputada))

    @staticmethod
    def colecao_minha_ordenada(guild_id, membro_id):
        """A parte PESADA de `_dados_do_modo` (modo "minha") - separada
        pra poder rodar via `asyncio.to_thread` de fora (2026-08-30,
        achado do usuário: "GAIA não respondeu a tempo" no Cidade/
        Personagem, mesma causa aqui) - `__init__` de uma `discord.ui.View`
        é síncrono, não dá pra `await` lá dentro, então quem CONSTRÓI a
        View (`_colecao`/`_trocar_modo`, ambos `async`) pré-calcula isso
        ANTES e passa pronto."""
        return torre.ordenar_por_power(db.colecao_do_usuario(guild_id, membro_id), guild_id, membro_id)

    def _dados_do_modo(self, colecao_minha_precomputada=None):
        permitir_nsfw = db.obter_configuracao_colecao(self._guild.id)["nsfw_permitido"]
        if self._modo == "populares":
            personagens = db.personagens_por_popularidade(50, permitir_nsfw)
            return "🔥 Personagens mais populares do catálogo", personagens, 0, consulta.linha_populares
        if self._modo == "disponiveis":
            pendentes = gacha.personagens_pendentes(self._guild.id)
            titulo = "🎯 Disponíveis pra pegar (botão nas 10 mais raras)"
            return titulo, [personagem for _, personagem in pendentes], 0, None
        if self._modo == "tags_trade":
            personagens = db.colecao_por_tag(self._guild.id, self._membro.id, gacha.TAG_TROCA)
            return "🏷️ Marcadas pra troca", personagens, 0, None
        # 🔥 CP + ordenação (2026-08-30, achado do usuário: "Minha coleção
        # n mostra o CP") - ordenada por CP (maior primeiro), mesmo padrão
        # já aplicado em todo dropdown de personagem possuída.
        personagens = (
            colecao_minha_precomputada if colecao_minha_precomputada is not None
            else self.colecao_minha_ordenada(self._guild.id, self._membro.id)
        )
        return f"📚 Coleção de {self._membro.display_name}", personagens, 0, self._linha_com_cp

    def _linha_com_cp(self, _indice, personagem):
        power, _nivel, categoria = torre.power_personagem(personagem, self._guild.id, self._membro.id)
        icone = torre.icone_categoria(categoria)
        return f"{icone} - {consulta.linha_personagem(personagem)} · CP {power:.0f}"

    def _montar(self):
        super()._montar()
        select = discord.ui.Select(
            placeholder="Trocar modo...",
            options=[
                discord.SelectOption(label=rotulo, value=chave, default=chave == self._modo)
                for chave, rotulo in _MODOS_COLECAO
            ],
            row=1,
        )
        select.callback = self._trocar_modo
        self.add_item(select)
        if self._modo == "disponiveis" and self._personagens:
            botao_claim = discord.ui.Button(
                label="Reivindicar uma das 10 primeiras", emoji="💘", style=discord.ButtonStyle.success, row=2,
            )
            botao_claim.callback = self._abrir_claim
            self.add_item(botao_claim)

    async def _trocar_modo(self, interaction: discord.Interaction):
        self._modo = interaction.data["values"][0]
        # 🔥 `asyncio.to_thread` só quando vai pro modo "minha" (o único que
        # varre a coleção INTEIRA) - mesmo motivo de `_colecao`/`__init__`
        # acima (2026-08-30, "GAIA não respondeu a tempo" no Cidade/
        # Personagem).
        colecao_minha = None
        if self._modo == "minha":
            colecao_minha = await asyncio.to_thread(
                ViewColecaoHub.colecao_minha_ordenada, self._guild.id, self._membro.id,
            )
        titulo, personagens, pagina, formatador = self._dados_do_modo(colecao_minha)
        self._titulo = titulo
        self._personagens = personagens
        self._pagina = pagina
        self._formatador_linha = formatador or (lambda indice, p: consulta.linha_personagem(p))
        self._montar()
        await interaction.response.edit_message(content=self.formatar(), view=self)

    async def _abrir_claim(self, interaction: discord.Interaction):
        # 🔥 Re-busca em vez de reaproveitar `self._personagens` (que já
        # perdeu o `message_id` no achatamento de `_dados_do_modo`) - mesmo
        # espírito "re-derivar do banco a cada clique" do LA, evita
        # oferecer claim numa carta que expirou entre abrir o painel e
        # clicar aqui.
        pendentes = gacha.personagens_pendentes(self._guild.id)
        if not pendentes:
            await interaction.response.send_message("Nada disponível pra reivindicar agora.", ephemeral=True)
            return
        view = gacha.ViewClaimPendentes(self._guild.id, pendentes[:10])
        await interaction.response.send_message("Escolha quem reivindicar:", view=view)


class _ViewEscolherRespostaProva(discord.ui.View):
    """3 botões de resposta pra situação da Prova (2026-08-29) - escolher a
    que combina com a personalidade da personagem (`opcao["correta"]`,
    decidido pela GAIA e validado/normalizado no lado dela - taxonomia
    FECHADA, sempre exatamente 1 certa entre 3) dá um bônus FIXO de chance
    (`gacha._BONUS_ESCOLHA_CORRETA_PROVA_SOULMATE`) só NESSA tentativa -
    nunca garante sucesso sozinho, o RNG/pity de `gacha.tentar_prova_
    soulmate` continuam decidindo. Separa "conhecer a personagem" de
    "vencer o gacha" - a mesma ideia validada pra Classe/Categoria de
    combate (IA decide o aberto/temático, código decide o fechado/
    numérico)."""

    def __init__(self, guild_id, personagem, textos):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.personagem = personagem
        self.textos = textos
        for indice, opcao in enumerate(textos["prova_soulmate_opcoes"][:3]):
            botao = discord.ui.Button(label=opcao["texto"][:80], style=discord.ButtonStyle.secondary, row=0)
            botao.callback = self._montar_callback(indice)
            self.add_item(botao)

    def _montar_callback(self, indice):
        async def _callback(interaction: discord.Interaction):
            opcao = self.textos["prova_soulmate_opcoes"][indice]
            acertou = bool(opcao.get("correta"))
            regra = gacha.regra_prova_soulmate(self.personagem["raridade"])
            tentativas_feitas = self.personagem.get("soulmate_tentativas") or 0
            tentativa_atual = tentativas_feitas + 1
            chance_base = min(1.0, regra["chance"] + regra["incremento"] * tentativas_feitas)
            bonus = gacha._BONUS_ESCOLHA_CORRETA_PROVA_SOULMATE if acertou else 0.0
            chance_final = min(1.0, chance_base + bonus)
            reacao = self.textos["prova_soulmate_reacao_acerto"] if acertou else self.textos["prova_soulmate_reacao_erro"]
            embed = discord.Embed(
                title=f"💞 {self.textos['prova_soulmate_nome']}",
                description=reacao,
                color=gacha._CORES_RARIDADE.get(self.personagem["raridade"], 0x2ECC71),
            )
            if tentativa_atual >= regra["pity"]:
                embed.add_field(name="Resultado", value="🌟 Garantido (limite de tentativas atingido)", inline=False)
            else:
                embed.add_field(name="Chance base", value=f"{chance_base:.0%}", inline=True)
                if bonus:
                    embed.add_field(name="Bônus da resposta", value=f"+{bonus:.0%}", inline=True)
                embed.add_field(name="Chance final", value=f"{chance_final:.0%}", inline=True)
            embed.add_field(name="Tentativa", value=f"{tentativa_atual} de {regra['pity']}", inline=True)
            embed.add_field(name="Garantia", value=f"{regra['pity']}ª tentativa", inline=True)
            view = _ViewEnfrentarProva(self.guild_id, self.personagem, bonus)
            await interaction.response.edit_message(embed=embed, view=view)
        return _callback


class _ViewEnfrentarProva(discord.ui.View):
    """Tela final da Prova de Soulmate (2026-08-29) - botão único, sem
    voltar/cancelar (a resposta já foi escolhida na tela anterior; desistir
    é só não clicar)."""

    def __init__(self, guild_id, personagem, bonus_escolha):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.personagem = personagem
        self.bonus_escolha = bonus_escolha

    @discord.ui.button(label="Enfrentar Prova", emoji="💞", style=discord.ButtonStyle.danger)
    async def enfrentar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        await interaction.response.defer()
        ok, erro, contexto = await gacha.tentar_prova_soulmate(
            self.guild_id, interaction.user.id, self.personagem["id"], interaction.user,
            bonus_escolha=self.bonus_escolha,
        )
        if not ok:
            await interaction.followup.send(erro, ephemeral=True)
            return
        # 🔥 Uma edição só, sem mensagem nova (2026-08-29, feedback do
        # usuário: "eu tentaria manter a Prova inteira em uma única
        # interação/edit de embed sempre que possível") - antes fechava o
        # botão E mandava um followup separado com o resultado.
        await interaction.edit_original_response(embed=_embed_resultado_prova(contexto), view=None)


def _embed_resultado_prova(contexto):
    personagem = contexto["personagem"]
    textos = contexto["textos"]
    if contexto["venceu"]:
        embed = discord.Embed(
            title="💞 Soulmate!",
            description=textos["prova_soulmate_vitoria"],
            color=gacha._COR_SOULMATE,
        )
        embed.add_field(name="Multiplicador de Afinidade", value="1,9× → 2,0×", inline=True)
        if contexto["pity_forcado"]:
            embed.add_field(name="Pity", value="Ativado (sucesso garantido)", inline=True)
        return embed
    regra = gacha.regra_prova_soulmate(personagem["raridade"])
    chance_anterior = contexto["chance_usada"]
    chance_nova = min(1.0, regra["chance"] + regra["incremento"] * contexto["tentativa_atual"])
    embed = discord.Embed(
        title="Prova fracassada",
        description=textos["prova_soulmate_derrota"],
        color=gacha._CORES_RARIDADE.get(personagem["raridade"], 0x2ECC71),
    )
    embed.add_field(name="Chance", value=f"{chance_anterior:.0%} → {chance_nova:.0%} na próxima", inline=True)
    embed.add_field(name="Próxima tentativa", value="em ~1h", inline=True)
    return embed


class ViewFavoritosHub(consulta.ViewColecao):
    """Lista paginada dos favoritos (2026-09-02, pedido do usuário: "quero
    q tenha uma lista com meus personagens favoritos, assim como tem so
    de personagens, e poe ela e a wishlist dentro do perfil") - herda
    `ViewColecao` (mesma paginação ◀️/▶️ de "📚 Minha coleção"), sem botão
    nenhum a mais - favoritar/desfavoritar continua exclusivo do card
    "🔍 Personagem" (`_ViewNivel.favoritar`), nunca por aqui."""

    def __init__(self, guild_id, autor_id):
        super().__init__("⭐ Seus favoritos", db.favoritos_listar(guild_id, autor_id))


class ViewWishlistHub(consulta.ViewColecao):
    """Wishlist paginada (herda `ViewColecao`, mesma paginação ◀️/▶️) +
    botão "➕ Adicionar" (`discord.ui.Modal` com o nome) e select "🗑
    Remover" (até 25 da PÁGINA atual, mesmo teto de sempre).

    🔥 "✨" à direita de quem já tem dono (2026-08-29, pedido do usuário:
    "coloca aquele emoji de brilho na direita dos q ja foram pegos") -
    `db.wishlist_disponiveis_no_guild` já exclui quem tem dono da chance de
    vir num wish-roll, mas o item continua na wishlist até ser removido à
    mão; o "✨" deixa claro por que ele parou de aparecer nos rolls."""

    def __init__(self, guild_id, autor_id):
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        formatador = lambda indice, p: consulta.linha_personagem(p) + (" ✨" if db.dono_do_personagem(guild_id, p["id"]) is not None else "")
        super().__init__("⭐ Sua wishlist", db.wishlist_listar(guild_id, autor_id), formatador_linha=formatador)

    def _recarregar(self):
        self._personagens = db.wishlist_listar(self.guild_id, self.autor_id)
        if self._pagina >= self._total_paginas:
            self._pagina = max(0, self._total_paginas - 1)

    def _montar(self):
        super()._montar()
        adicionar = discord.ui.Button(label="Adicionar", emoji="➕", style=discord.ButtonStyle.success, row=1)
        adicionar.callback = self._abrir_modal_adicionar
        self.add_item(adicionar)
        pagina_atual = self._pagina_atual()
        if pagina_atual:
            # 🔥 `max_values` (2026-09-02, pedido do usuário: "Remover da
            # wishlist tem de permitir selecionar varios por vez") - era
            # `min_values`/`max_values` padrão (1/1, só 1 por vez); agora
            # seleciona de 1 até TODOS da página atual numa tacada só.
            remover = discord.ui.Select(
                placeholder="Remover da wishlist...",
                options=[discord.SelectOption(label=p["nome"][:100], value=str(p["id"])) for p in pagina_atual],
                min_values=1, max_values=len(pagina_atual),
                row=2,
            )
            remover.callback = self._remover_selecionado
            self.add_item(remover)

    async def _abrir_modal_adicionar(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.autor_id:
            await interaction.response.send_message("Essa wishlist não é sua.", ephemeral=True)
            return
        await interaction.response.send_modal(_ModalAdicionarWishlist(self))

    async def _remover_selecionado(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.autor_id:
            await interaction.response.send_message("Essa wishlist não é sua.", ephemeral=True)
            return
        for id_personagem in interaction.data["values"]:
            db.wishlist_remover(self.guild_id, self.autor_id, int(id_personagem))
        self._recarregar()
        self._montar()
        await interaction.response.edit_message(content=self.formatar(), view=self)


class _ModalAdicionarWishlist(discord.ui.Modal, title="Adicionar à wishlist"):
    """Campo único MULTI-LINHA (2026-09-01, pedido do usuário: "alterar
    forma de adicionar wishlist por uma mais fácil e rápido p incluir
    mais de 1") - 1 nome por linha, processa todos numa submissão só (
    antes precisava reabrir o Modal pra cada personagem)."""

    nomes = discord.ui.TextInput(
        label="Nomes (1 por linha)", style=discord.TextStyle.paragraph,
        placeholder="Megumin\nZero Two\nAsuna Yuuki", max_length=2000,
    )

    def __init__(self, view_wishlist):
        super().__init__()
        self._view_wishlist = view_wishlist

    async def on_submit(self, interaction: discord.Interaction):
        linhas_nomes = [linha.strip() for linha in str(self.nomes).split("\n") if linha.strip()]
        if not linhas_nomes:
            await interaction.response.send_message("Nenhum nome digitado.", ephemeral=True)
            return

        adicionados, ambiguos, nao_encontrados = [], [], []
        for nome in linhas_nomes:
            resultados = await asyncio.to_thread(db.buscar_personagens, nome)
            if not resultados:
                nao_encontrados.append(nome)
            elif len(resultados) > 1:
                ambiguos.append(nome)
            else:
                await asyncio.to_thread(db.wishlist_adicionar, self._view_wishlist.guild_id, interaction.user.id, resultados[0]["id"])
                adicionados.append(resultados[0]["nome"])

        partes = []
        if adicionados:
            partes.append(f"✅ Adicionados: {', '.join(adicionados)}")
        if ambiguos:
            partes.append(f"⚠️ Mais de 1 resultado (use `/wishlist adicionar` com #id): {', '.join(ambiguos)}")
        if nao_encontrados:
            partes.append(f"❌ Não encontrados: {', '.join(nao_encontrados)}")

        self._view_wishlist._recarregar()
        self._view_wishlist._montar()
        await interaction.response.edit_message(
            content=f"{chr(10).join(partes)}\n\n{self._view_wishlist.formatar()}", view=self._view_wishlist,
        )


class _ViewFiltrarCategoria(discord.ui.View):
    """Filtro de categoria de combate (2026-08-30, pedido do usuário: "na
    hora de adicionar, deixa selecionar a role p filtrar e ficar facil de
    preencher oq precisa") - passo extra só no fluxo de ADICIONAR da Party
    (Remover não precisa, a lista já é só quem tá lá dentro). `ao_filtrar
    (interaction, categoria_ou_None)` recebe `None` pra "Todas"."""

    def __init__(self, ao_filtrar):
        super().__init__(timeout=120)
        self._ao_filtrar = ao_filtrar
        select = discord.ui.Select(
            placeholder="Filtrar por role (opcional)...",
            options=[
                discord.SelectOption(label="Todas", value="todas", emoji="🔀"),
                discord.SelectOption(label="DPS", value="DPS", emoji=torre.icone_categoria("DPS")),
                discord.SelectOption(label="Tank", value="Tank", emoji=torre.icone_categoria("Tank")),
                discord.SelectOption(label="Support", value="Support", emoji=torre.icone_categoria("Support")),
            ],
        )
        select.callback = self._selecionou
        self.add_item(select)

    async def _selecionou(self, interaction: discord.Interaction):
        valor = interaction.data["values"][0]
        await self._ao_filtrar(interaction, None if valor == "todas" else valor)


class ViewEquipe(discord.ui.View):
    """Painel de Party (2026-08-29) - SEM `/party` nem `/pandora party`, só
    alcançável pelo botão 👥 Party do hub (mesmo modelo do `Grupos` do LA -
    zero comando raiz). `tipo` fixo em "party" nesta leva - Vitrine
    reaproveita a MESMA tabela via `db.obter_equipe(..., "vitrine")`, mas
    ainda não tem botão no hub (fica pra depois, `/vitrine` continua sendo
    o único jeito de ver/editar por enquanto).

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

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        self._montar()

    def _montar(self):
        self.clear_items()
        equipe = db.obter_equipe(self.guild_id, self.autor_id, "party")
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

    def formatar(self):
        equipe = db.obter_equipe(self.guild_id, self.autor_id, "party")

        def linha(personagem):
            power, nivel, categoria = torre.power_personagem(personagem, self.guild_id, self.autor_id)
            icone = torre.icone_categoria(categoria)
            return f"{icone} - {consulta.linha_personagem(personagem)} · Nv.{nivel} · CP {power:.0f}"

        return consulta.formatar_equipe("Sua Party", equipe, db.MAX_POSICOES_EQUIPE, formatador_linha=linha)

    async def _somente_autor(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.autor_id:
            await interaction.response.send_message("Essa party não é sua.", ephemeral=True)
            return False
        return True

    async def _abrir_adicionar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        equipe = db.obter_equipe(self.guild_id, self.autor_id, "party")
        vagas = db.MAX_POSICOES_EQUIPE - len(equipe)
        if vagas <= 0:
            await interaction.response.send_message("Sua Party já está cheia.", ephemeral=True)
            return
        ja_na_party = {p["id"] for p in equipe.values()}
        candidatos = [p for p in db.colecao_do_usuario(self.guild_id, self.autor_id) if p["id"] not in ja_na_party]
        if not candidatos:
            await interaction.response.send_message("Você não tem mais nenhuma personagem fora da Party.", ephemeral=True)
            return

        async def prosseguir(interaction_filtro: discord.Interaction, categoria):
            # 🔥 `defer()` ANTES de qualquer trabalho síncrono (2026-09-03,
            # achado do usuário: "Ao selecionar role da personagem p por
            # na pt, GAIA n responde a tempo") - filtrar por categoria
            # chama `torre.categoria_personagem` (1 query síncrona por
            # personagem candidata, sem `to_thread`) ANTES de qualquer
            # resposta à interação - mesma classe de bug (trabalho
            # bloqueante antes do 1º ack) já corrigida várias vezes nesta
            # sessão. Interação de Select vira `deferred_message_update`
            # (edita a MESMA mensagem do filtro) - `edit_original_response`
            # no lugar de `response.edit_message`/`send_message` depois.
            await interaction_filtro.response.defer()
            if categoria is None:
                filtrados = candidatos
            else:
                filtrados = await asyncio.to_thread(
                    lambda: [p for p in candidatos if torre.categoria_personagem(p) == categoria],
                )
            # 🔥 ordena por CP ANTES de cortar em 25 (2026-08-30, pedido do
            # usuário: "Todo dropdwon q listar waifu, sempre ordene pelas
            # com maior CP/popularidade") - via thread (2026-08-30,
            # achado do usuário: "GAIA não respondeu a tempo" repetido,
            # mesma causa das outras varreduras de coleção inteira).
            filtrados = (await asyncio.to_thread(torre.ordenar_por_power, filtrados, self.guild_id, self.autor_id))[:25]
            if not filtrados:
                await interaction_filtro.followup.send(
                    f"Você não tem nenhuma personagem fora da Party na role {categoria}.", ephemeral=True,
                )
                return
            contexto_lote = await asyncio.to_thread(torre._contexto_lote, self.guild_id, self.autor_id)
            view = _ViewSelecionarPersonagem(
                filtrados, f"Escolha até {min(vagas, len(filtrados))} personagem(ns)...", self._adicionar_selecionados,
                min_values=1, max_values=min(vagas, len(filtrados)),
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
        equipe = db.obter_equipe(self.guild_id, interaction.user.id, "party")
        vagas_livres = (posicao for posicao in range(1, db.MAX_POSICOES_EQUIPE + 1) if posicao not in equipe)
        for personagem in personagens:
            posicao = next(vagas_livres, None)
            if posicao is None:
                break
            db.definir_posicao_equipe(self.guild_id, interaction.user.id, "party", posicao, personagem["id"])
        await asyncio.to_thread(cidade.atualizar_snapshot_bonus, self.guild_id, interaction.user.id)
        await asyncio.to_thread(series_favoritas.recalcular_bonus, self.guild_id, interaction.user.id)
        self._montar()
        await interaction.edit_original_response(content=self.formatar(), view=self)

    async def _abrir_remover(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        equipe = db.obter_equipe(self.guild_id, self.autor_id, "party")
        if not equipe:
            await interaction.response.send_message("Sua Party está vazia.", ephemeral=True)
            return
        # 🔥 `defer()` ANTES do `to_thread` (2026-09-03) - `ordenar_por_
        # power`/`_contexto_lote` rodavam síncronos ANTES de responder.
        await interaction.response.defer()
        membros = await asyncio.to_thread(torre.ordenar_por_power, list(equipe.values()), self.guild_id, self.autor_id)
        contexto_lote = await asyncio.to_thread(torre._contexto_lote, self.guild_id, self.autor_id)
        view = _ViewSelecionarPersonagem(
            membros, "Escolha quem remover da Party...", self._remover_selecionados, min_values=1, max_values=len(membros),
            descricao=lambda p: _descricao_personagem_dropdown(p, self.guild_id, self.autor_id, contexto_lote),
        )
        await interaction.edit_original_response(content="Selecione:", view=view)

    async def _remover_selecionados(self, interaction: discord.Interaction, personagens):
        await interaction.response.defer()
        equipe = db.obter_equipe(self.guild_id, interaction.user.id, "party")
        posicao_por_personagem_id = {p["id"]: posicao for posicao, p in equipe.items()}
        for personagem in personagens:
            posicao = posicao_por_personagem_id.get(personagem["id"])
            if posicao is not None:
                db.remover_posicao_equipe(self.guild_id, interaction.user.id, "party", posicao)
        await asyncio.to_thread(cidade.atualizar_snapshot_bonus, self.guild_id, interaction.user.id)
        await asyncio.to_thread(series_favoritas.recalcular_bonus, self.guild_id, interaction.user.id)
        self._montar()
        await interaction.edit_original_response(content=self.formatar(), view=self)

    async def _limpar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        await interaction.response.defer()
        db.limpar_equipe(self.guild_id, self.autor_id, "party")
        await asyncio.to_thread(cidade.atualizar_snapshot_bonus, self.guild_id, self.autor_id)
        await asyncio.to_thread(series_favoritas.recalcular_bonus, self.guild_id, self.autor_id)
        self._montar()
        await interaction.edit_original_response(content=self.formatar(), view=self)

class ViewLoja(discord.ui.View):
    """Painel da Loja (2026-08-29) - `/loja` deixa de existir como comando
    NESTA leva; alcançável só pelo botão 🛒 do hub. 3 ações de sempre
    (`/loja ver+comprar`, `/loja garantir`, `/loja upgrade`), cada uma
    reaproveitando as MESMAS funções de `db`/`economia` que os comandos
    antigos já chamavam."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        comprar = discord.ui.Button(label="Comprar", emoji="🛍️", style=discord.ButtonStyle.primary, row=0)
        comprar.callback = self._abrir_comprar
        self.add_item(comprar)
        garantir = discord.ui.Button(label="Garantir raridade", emoji="🎯", style=discord.ButtonStyle.primary, row=0)
        garantir.callback = self._abrir_garantir
        self.add_item(garantir)
        upgrade = discord.ui.Button(label="Upgrade de rolls", emoji="⬆️", style=discord.ButtonStyle.success, row=0)
        upgrade.callback = self._upgrade
        self.add_item(upgrade)
        upgrade_claims = discord.ui.Button(label="Upgrade de claims", emoji="🔺", style=discord.ButtonStyle.success, row=0)
        upgrade_claims.callback = self._upgrade_claims
        self.add_item(upgrade_claims)
        # 🔥 Progressão Global da conta (2026-08-30, análise do usuário
        # Seção 7: "a loja também será uma das principais formas de
        # transformar WiShards em crescimento permanente") - SEM nível
        # máximo, diferente dos 2 upgrades acima.
        treinamento = discord.ui.Button(label="Treinamento Global", emoji="🏋️", style=discord.ButtonStyle.success, row=1)
        treinamento.callback = self._treinamento_global
        self.add_item(treinamento)
        potencial = discord.ui.Button(label="Potencial da Coleção", emoji="📊", style=discord.ButtonStyle.success, row=1)
        potencial.callback = self._potencial_colecao
        self.add_item(potencial)
        itens_botao = discord.ui.Button(label="Itens", emoji="🎁", style=discord.ButtonStyle.primary, row=2)
        itens_botao.callback = self._abrir_itens
        self.add_item(itens_botao)
        slot_serie_botao = discord.ui.Button(label="Slot de Série Favorita", emoji="❤️", style=discord.ButtonStyle.success, row=2)
        slot_serie_botao.callback = self._upgrade_slot_serie_favorita
        self.add_item(slot_serie_botao)

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

    async def _abrir_itens(self, interaction: discord.Interaction):
        """Seção 14 (2026-09-01) - mesmos itens raros do World Boss,
        comprados com WiShards."""
        if not await self._somente_autor(interaction):
            return
        view = _ViewLojaItens(self.guild_id)
        await interaction.response.send_message("🎁 Escolha o item:", view=view, ephemeral=True)

    async def _upgrade(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        nivel_atual = db.nivel_upgrade_rolls(self.guild_id, interaction.user.id)
        if nivel_atual >= db.NIVEL_MAXIMO_UPGRADE_ROLLS:
            await interaction.response.send_message("Você já está no nível máximo desse upgrade.", ephemeral=True)
            return
        preco = db.PRECOS_UPGRADE_ROLLS[nivel_atual + 1]

        async def _confirmar(interacao_confirmacao: discord.Interaction):
            ok, mensagem = db.comprar_upgrade_rolls(self.guild_id, interacao_confirmacao.user.id)
            await interacao_confirmacao.response.edit_message(content=mensagem, view=None)

        view = _ViewConfirmar(_confirmar)
        bonus = (nivel_atual + 1) * db.BONUS_ROLLS_POR_NIVEL
        await interaction.response.send_message(
            f"Nível {nivel_atual + 1}: +{db.BONUS_ROLLS_POR_NIVEL} rolls por ciclo, PRA SEMPRE "
            f"(acumulado: +{bonus} no total) - custa {preco} WiShards. Confirma?",
            view=view, ephemeral=True,
        )

    async def _upgrade_claims(self, interaction: discord.Interaction):
        """Espelha `_upgrade` (rolls), 2026-08-29 - pedido do usuário
        "claim tem q ter upgrade permanente tbm"."""
        if not await self._somente_autor(interaction):
            return
        nivel_atual = db.nivel_upgrade_claims(self.guild_id, interaction.user.id)
        if nivel_atual >= db.NIVEL_MAXIMO_UPGRADE_CLAIMS:
            await interaction.response.send_message("Você já está no nível máximo desse upgrade.", ephemeral=True)
            return
        preco = db.PRECOS_UPGRADE_CLAIMS[nivel_atual + 1]

        async def _confirmar(interacao_confirmacao: discord.Interaction):
            ok, mensagem = db.comprar_upgrade_claims(self.guild_id, interacao_confirmacao.user.id)
            await interacao_confirmacao.response.edit_message(content=mensagem, view=None)

        view = _ViewConfirmar(_confirmar)
        bonus = (nivel_atual + 1) * db.BONUS_CLAIMS_POR_NIVEL
        await interaction.response.send_message(
            f"Nível {nivel_atual + 1}: +{db.BONUS_CLAIMS_POR_NIVEL} claim(s) por ciclo, PRA SEMPRE "
            f"(acumulado: +{bonus} no total) - custa {preco} WiShards. Confirma?",
            view=view, ephemeral=True,
        )

    async def _upgrade_slot_serie_favorita(self, interaction: discord.Interaction):
        """Espelha `_upgrade`/`_upgrade_claims` - slot extra de Série
        Favorita (2026-09-02, `pandora.series_favoritas`), 5 base + até 5
        pagos aqui."""
        if not await self._somente_autor(interaction):
            return
        nivel_atual = db.nivel_upgrade_slots_serie_favorita(self.guild_id, interaction.user.id)
        if nivel_atual >= db.NIVEL_MAXIMO_UPGRADE_SLOT_SERIE_FAVORITA:
            await interaction.response.send_message("Você já tem o número máximo de slots de Série Favorita.", ephemeral=True)
            return
        preco = db.PRECOS_UPGRADE_SLOT_SERIE_FAVORITA[nivel_atual + 1]

        async def _confirmar(interacao_confirmacao: discord.Interaction):
            ok, mensagem = db.comprar_slot_serie_favorita(self.guild_id, interacao_confirmacao.user.id)
            await interacao_confirmacao.response.edit_message(content=mensagem, view=None)

        view = _ViewConfirmar(_confirmar)
        total_slots = db.SLOTS_BASE_SERIE_FAVORITA + nivel_atual + 1
        await interaction.response.send_message(
            f"Slot {total_slots}: +1 Série Favorita, PRA SEMPRE - custa {preco} WiShards. Confirma?",
            view=view, ephemeral=True,
        )

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
        nivel_atual = db.progressao_conta(self.guild_id, interaction.user.id)["nivel_treinamento_global"]
        saldo = db.saldo_wishards(self.guild_id, interaction.user.id)

        async def _confirmar(interacao_confirmacao, alvo):
            ok, mensagem = db.comprar_treinamento_global_ate(self.guild_id, interacao_confirmacao.user.id, alvo)
            await interacao_confirmacao.response.edit_message(content=mensagem, view=None)

        async def _cancelar(interacao_cancelamento):
            await interacao_cancelamento.response.edit_message(content="Cancelado.", view=None)

        view = _ViewEscolherAlvo(
            "Treinamento Global", nivel_atual, nivel_atual + _TETO_OPCOES_DROPDOWN_LOJA,
            lambda alvo: db.custo_total_treinamento_ate(nivel_atual, alvo),
            "WiShards", _confirmar, _cancelar, saldo_atual=saldo,
        )
        await interaction.response.send_message("Escolha até qual Nível de Treinamento Global ir:", view=view, ephemeral=True)

    async def _potencial_colecao(self, interaction: discord.Interaction):
        """Progressão Global (2026-08-30) - +CP PERCENTUAL global, SEM
        nível máximo (`db.comprar_potencial_colecao_ate`) - mesmo dropdown
        de "Treinamento Global"."""
        if not await self._somente_autor(interaction):
            return
        nivel_atual = db.progressao_conta(self.guild_id, interaction.user.id)["nivel_potencial_colecao"]
        saldo = db.saldo_wishards(self.guild_id, interaction.user.id)

        async def _confirmar(interacao_confirmacao, alvo):
            ok, mensagem = db.comprar_potencial_colecao_ate(self.guild_id, interacao_confirmacao.user.id, alvo)
            await interacao_confirmacao.response.edit_message(content=mensagem, view=None)

        async def _cancelar(interacao_cancelamento):
            await interacao_cancelamento.response.edit_message(content="Cancelado.", view=None)

        view = _ViewEscolherAlvo(
            "Potencial da Coleção", nivel_atual, nivel_atual + _TETO_OPCOES_DROPDOWN_LOJA,
            lambda alvo: db.custo_total_potencial_ate(nivel_atual, alvo),
            "WiShards", _confirmar, _cancelar, saldo_atual=saldo,
        )
        await interaction.response.send_message("Escolha até qual Nível de Potencial da Coleção ir:", view=view, ephemeral=True)


class _ViewEscolherRaridadeLoja(discord.ui.View):
    """Select de raridade compartilhado por "Comprar" (1-5⭐) e "Garantir"
    (3-5⭐, mesmo teto de `db.PRECOS_GARANTIA`)."""

    def __init__(self, view_loja, acao):
        super().__init__(timeout=120)
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
            if db.saldo_wishards(self._view_loja.guild_id, interacao_confirmacao.user.id) < preco:
                await interacao_confirmacao.response.edit_message(content=f"Custa {preco} WiShards e você não tem o suficiente.", view=None)
                return
            db.creditar_wishards(self._view_loja.guild_id, interacao_confirmacao.user.id, -preco, "loja_garantia", f"garantia {raridade}estrelas")
            db.definir_garantia(self._view_loja.guild_id, interacao_confirmacao.user.id, raridade)
            await interacao_confirmacao.response.edit_message(
                content=f"Garantido: seu próximo roll vai ser {raridade}⭐ ou mais (custou {preco} WiShards).", view=None,
            )

        view = _ViewConfirmar(_confirmar)
        await interaction.response.edit_message(content=f"Garantir {raridade}⭐ custa {preco} WiShards - confirma?", view=view)


class _ModalBuscarNomeLoja(discord.ui.Modal, title="Comprar personagem"):
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


class _ViewComprarPersonagem(discord.ui.View):
    """Select final de "Comprar" - até 25 personagens livres dessa
    raridade (mesmo teto do Discord), `db.comprar_personagem` decide tudo
    (preço, corrida por quem paga primeiro, reembolso se perder).

    🔥 `gacha.comprar_com_revelacao` em vez de `db.comprar_personagem`
    direto (2026-09-03, pedido do usuário: "esses botoes tem q fazer
    exatamente o claim, definir clsse e tudo") - sem isso, uma personagem
    nunca reivindicada em nenhum servidor saía da Loja pra sempre sem
    classe (mesmo gap do Merge, nunca corrigido aqui)."""

    def __init__(self, view_loja, raridade, personagens):
        super().__init__(timeout=120)
        self._view_loja = view_loja
        self._personagens = personagens
        select = discord.ui.Select(
            placeholder=f"Comprar por {db.PRECOS_LOJA[raridade]} WiShards...",
            options=[
                discord.SelectOption(label=p["nome"][:100], description=f"#{p['id']}", value=str(indice))
                for indice, p in enumerate(personagens)
            ],
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
        ok, mensagem = await gacha.comprar_com_revelacao(self._view_loja.guild_id, personagem["id"], interaction.user)
        await interaction.edit_original_response(content=mensagem, view=None)


def _int_seguro(texto):
    texto = (texto or "").strip()
    return int(texto) if texto.lstrip("-").isdigit() else 0


class _ViewEscolherAlvoTroca(discord.ui.View):
    """Passo 1 de "🔄 Trocas" - escolher o outro jogador via
    `discord.ui.UserSelect` (nativo do Discord, sem listar membros na
    mão); passo 2/3 são selects de personagem (oferece/pede)."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=120)
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
        view = _ViewEscolherPersonagensTroca(self.guild_id, interaction.user.id, alvo, colecao_proponente, etapa="oferece")
        await interaction.response.edit_message(content=f"Trocando com {alvo.mention} - escolha o que você OFERECE:", view=view)


class _ViewEscolherPersonagensTroca(discord.ui.View):
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

    def __init__(self, guild_id, proponente_id, alvo, colecao, etapa, oferece_ids=None):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.proponente_id = str(proponente_id)
        self.alvo = alvo
        self.etapa = etapa  # "oferece" ou "pede"
        self._colecao = colecao
        self._oferece_ids = oferece_ids or []
        rotulo = "OFERECE" if etapa == "oferece" else "PEDE"
        select = discord.ui.Select(
            placeholder=f"Personagens que você {rotulo} (opcional)...",
            min_values=0,
            max_values=min(25, len(colecao)) if colecao else 1,
            disabled=not colecao,
            options=[
                discord.SelectOption(label=p["nome"][:100], description=gacha.estrelas_por_raridade(p["raridade"]), value=str(indice))
                for indice, p in enumerate(colecao)
            ] or [discord.SelectOption(label="(nenhuma personagem disponível)", value="-1")],
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
            proxima = _ViewEscolherPersonagensTroca(
                self.guild_id, self.proponente_id, self.alvo, colecao_alvo, etapa="pede", oferece_ids=ids_escolhidos,
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
        f"💰 Seu saldo atual: {saldo} WiShards",
        f"🏪 Valor de loja do que você OFERECE: {valor_oferece} WiShards",
        f"🏪 Valor de loja do que você PEDE: {valor_pede} WiShards",
    ]
    if alvo.bot:
        limiar = valor_pede * economia.LIMIAR_TROCA_NPC
        faltam = max(0, limiar - valor_oferece)
        linhas.append(
            f"🤖 {alvo.mention} é uma conta de bot - só aceita se o total oferecido (WiShards + valor de "
            f"loja dos personagens) for pelo menos **{limiar}** WiShards (10x o valor de loja do que você "
            f"pede). Contando só os personagens já escolhidos, faltam pelo menos **{faltam}** WiShards."
        )
    return "\n".join(linhas)


class _ViewConfirmarValoresTroca(discord.ui.View):
    """Passo extra entre escolher "pede" e o Modal de WiShards - só existe
    pra dar tempo de mostrar `_texto_valores_troca` antes de abrir o Modal
    (Modal em si não tem como calcular/mostrar nada, é só texto puro)."""

    def __init__(self, guild_id, proponente_id, alvo, oferece_ids, pede_ids):
        super().__init__(timeout=180)
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


class _ModalWishardsTroca(discord.ui.Modal, title="Propor troca - WiShards"):
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
                f"({desafio['aposta_wishards']} WiShards em risco)."
            )
        else:
            comp = batalha.composicao_ordem(json.loads(desafio["ordem_desafiante"]))
            embed.description = (
                f"⚔️ Sua **{personagem['nome']}** está sendo desafiada - "
                f"{desafio['aposta_wishards']} WiShards em risco pro desafiante se você vencer.\n"
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
            f"{nome_defensor} NÃO recebeu os {desafio['aposta_wishards']} WiShards apostados (a aposta some da economia)."
        )
    else:
        descricao = (
            f"🏆 **{nome_defensor} defendeu {personagem['nome']}!** "
            f"+{desafio['aposta_wishards']} WiShards do desafiante."
        )
    embed = discord.Embed(title=f"⚔️ Resultado - {personagem['nome']}", description=descricao, color=_COR_HUB)
    embed.add_field(name="Placar final", value=f"{nome_desafiante} {placar_a} x {placar_b} {nome_defensor}", inline=False)
    return embed


async def _resolver_e_revelar(interaction: discord.Interaction, desafio):
    """Resolve as posições congeladas e revela 1 confronto por vez editando
    a MESMA resposta (Seção 10: "a revelação gradual cria suspense") -
    `interaction` já precisa estar deferida/respondida (`edit_original_
    response`). Sempre termina num resultado final (Morte Súbita
    REMOVIDA, 2026-09-02 - `batalha.resolver_rodadas` nunca mais devolve
    `vencedor=None`).

    🔥 Log de entrada (2026-09-02, pedido do usuário: "Coloca log se ta
    tendo dificuldade de encontrar os problemas") - função COMPARTILHADA
    por Desafiar/Montar Defesa/Revanche, nenhuma logava nada antes - só
    re-levanta depois de logar (não muda o comportamento de quem chama,
    só garante que a exceção fica visível no log de qualquer jeito)."""
    print(f" [BATALHA] _resolver_e_revelar iniciado - desafio_id={desafio['id']}")
    try:
        ordem_a = json.loads(desafio["ordem_desafiante"])
        ordem_b = json.loads(desafio["ordem_defensor"])
        rodadas, _placar_final_a, _placar_final_b, vencedor = await asyncio.to_thread(
            batalha.resolver_rodadas, ordem_a, ordem_b,
        )
    except Exception:
        print(" [BATALHA] !!! EXCEÇÃO dentro de _resolver_e_revelar (resolvendo rodadas) !!!")
        traceback.print_exc()
        raise
    personagem = db.personagem_por_id(desafio["personagem_id"])
    nome_desafiante = _membro_ou_none(interaction.guild, desafio["desafiante_id"])
    nome_defensor = _membro_ou_none(interaction.guild, desafio["defensor_id"])

    linhas = []
    placar_a = placar_b = 0
    for rodada in rodadas:
        icone_a = torre.icone_categoria(rodada["categoria_a"])
        icone_b = torre.icone_categoria(rodada["categoria_b"])
        if rodada["resultado"] == 1:
            placar_a += 1
            resumo = f"{icone_a} vence {icone_b}"
        elif rodada["resultado"] == -1:
            placar_b += 1
            resumo = f"{icone_b} vence {icone_a}"
        else:
            resumo = f"{icone_a} empata com {icone_b}"
        linhas.append(f"Rodada {rodada['posicao']}: {resumo}")
        embed = discord.Embed(title=f"⚔️ Batalha por {personagem['nome']}", description="\n".join(linhas), color=_COR_HUB)
        embed.add_field(name="Placar", value=f"{nome_desafiante} {placar_a} x {placar_b} {nome_defensor}", inline=False)
        try:
            await interaction.edit_original_response(embed=embed)
        except discord.HTTPException as erro_http:
            # 🔥 Log em vez de engolir em silêncio (2026-09-02, pedido do
            # usuário: "Coloca log se ta tendo dificuldade de encontrar os
            # problemas") - antes um HTTPException aqui (token expirado,
            # permissão, rate limit) desaparecia sem deixar rastro nenhum.
            print(f" [BATALHA] edit_original_response falhou (ignorado, comportamento já era esse): {erro_http}")
        await asyncio.sleep(1.5)

    # 🔥 Morte Súbita REMOVIDA (2026-09-02, pedido do usuário) -
    # `batalha.resolver_rodadas` nunca mais devolve `vencedor=None`, então
    # não existe mais ramo de empate aqui - direto pro resultado final.
    batalha.concluir_batalha(desafio, placar_a, placar_b, vencedor)
    embed = _embed_resultado_final(desafio, personagem, nome_desafiante, nome_defensor, placar_a, placar_b, vencedor)
    try:
        await interaction.edit_original_response(embed=embed)
    except discord.HTTPException:
        pass


async def _anunciar_desafio(canal, guild_id, desafio_id, alvo_mention):
    """Aviso PÚBLICO no canal onde o desafio nasceu (2026-09-01) - só
    informativo (nunca interativo, ao contrário do resto do fluxo) pra
    nunca depender de um botão numa mensagem específica sobreviver a um
    restart do bot; a ação de verdade sempre passa pelo hub "⚔️ PvP"
    (`ViewBatalhaHub`, sempre reconstruído fresco do banco)."""
    desafio = db.batalha_por_id(desafio_id)
    personagem = db.personagem_por_id(desafio["personagem_id"])
    comp = batalha.composicao_ordem(json.loads(desafio["ordem_desafiante"]))
    texto = (
        f"⚔️ **Desafio recebido, {alvo_mention}!**\n"
        f"Sua **{personagem['nome']}** ({gacha.estrelas_por_raridade(personagem['raridade'])}) está sendo reivindicada.\n"
        f"Aposta em risco pro desafiante: **{desafio['aposta_wishards']} WiShards**.\n"
        f"Composição do desafiante: ⚔️ DPS {comp['DPS']} · 🛡️ Tank {comp['Tank']} · ✨ Support {comp['Support']} (ordem oculta).\n"
        f"Abra `/pandora` -> ⚔️ PvP pra montar sua defesa ou recusar."
    )
    try:
        await canal.send(texto)
    except discord.HTTPException:
        pass


class SchedulerBatalha:
    """Auto-Defesa por TIMEOUT (2026-09-02, pedido do usuário: "Se o
    desafiado n responder em 10min, considera essa defesa automatica") -
    tick de baixa frequência (30s, mesmo padrão de `worldboss.
    SchedulerWorldBoss`) que resolve sozinho, em background, qualquer
    desafio 'aguardando_defensor' criado há mais de
    `LIMITE_MINUTOS_AUTO_DEFESA` - substitui o cancelamento por
    inatividade de 24h antigo (`batalha.cancelar_expirados`, removido - o
    auto-resolve de 10min sempre vence a corrida antes dele acontecer).
    Roda só na instância "completo" (mesmo critério de `SchedulerWorldBoss`
    - é onde vive o hub "⚔️ PvP"), instanciado em `eris/bot.py`."""

    LIMITE_MINUTOS_AUTO_DEFESA = 10

    def __init__(self, client):
        self.client = client
        self._loop.start()

    def parar(self):
        self._loop.cancel()

    @tasks.loop(seconds=30)
    async def _loop(self):
        await self.client.wait_until_ready()
        limite = (datetime.now(timezone.utc) - timedelta(minutes=self.LIMITE_MINUTOS_AUTO_DEFESA)).isoformat()
        for guild in list(self.client.guilds):
            try:
                ids = await asyncio.to_thread(db.desafios_batalha_expirados, guild.id, limite)
            except Exception as e:
                print(f" [BATALHA] SchedulerBatalha falhou ao checar desafios expirados em {guild.id}: {e}")
                continue
            for desafio_id in ids:
                try:
                    await self._auto_resolver(desafio_id)
                except Exception as e:
                    print(f" [BATALHA] SchedulerBatalha falhou ao auto-resolver desafio #{desafio_id}: {e}")

    async def _auto_resolver(self, desafio_id):
        desafio = await asyncio.to_thread(db.batalha_por_id, desafio_id)
        if desafio is None or desafio["status"] != "aguardando_defensor":
            return  # 🔥 alguém respondeu bem no meio do tick - nada a fazer
        formacao = await asyncio.to_thread(batalha.defesa_automatica_para_desafio, desafio_id)
        ok, erro, desafio_atualizado = await asyncio.to_thread(
            batalha.montar_defesa, desafio["guild_id"], desafio_id, desafio["defensor_id"], formacao,
        )
        if not ok:
            print(f" [BATALHA] SchedulerBatalha - montar_defesa recusou o desafio #{desafio_id}: {erro}")
            return
        canal = self.client.get_channel(int(desafio["canal_id"])) if desafio["canal_id"] else None
        if canal is None:
            print(f" [BATALHA] SchedulerBatalha resolveu o desafio #{desafio_id} por timeout, mas sem canal salvo pra anunciar.")
            return
        await self._resolver_e_anunciar(canal, desafio_atualizado)

    async def _resolver_e_anunciar(self, canal, desafio):
        """Mesma resolução de `_resolver_e_revelar`, mas sem revelação
        gradual (não tem interação de Discord viva aqui, ninguém
        necessariamente está olhando ao vivo) - resolve tudo de uma vez e
        posta o resultado final como mensagem NOVA no canal."""
        ordem_a = json.loads(desafio["ordem_desafiante"])
        ordem_b = json.loads(desafio["ordem_defensor"])
        rodadas, placar_a, placar_b, vencedor = await asyncio.to_thread(batalha.resolver_rodadas, ordem_a, ordem_b)
        personagem = await asyncio.to_thread(db.personagem_por_id, desafio["personagem_id"])
        nome_desafiante = _membro_ou_none(canal.guild, desafio["desafiante_id"])
        nome_defensor = _membro_ou_none(canal.guild, desafio["defensor_id"])
        await asyncio.to_thread(batalha.concluir_batalha, desafio, placar_a, placar_b, vencedor)
        embed = _embed_resultado_final(desafio, personagem, nome_desafiante, nome_defensor, placar_a, placar_b, vencedor)
        embed.description = "🤖 **Auto-Defesa por timeout** (10min sem resposta) - " + embed.description
        try:
            await canal.send(embed=embed)
        except discord.HTTPException as erro_http:
            print(f" [BATALHA] SchedulerBatalha falhou ao anunciar o desafio #{desafio['id']}: {erro_http}")


class ViewBatalhaHub(discord.ui.View):
    """Painel "⚔️ PvP" (era "⚔️ Batalha" - 2026-09-02, botão renomeado) -
    único jeito de desafiar/defender/ligar a Auto-Defesa. Restrito a quem
    abriu (`autor_id`) - cada jogador envolvido num desafio abre o PRÓPRIO
    hub (`/pandora` -> ⚔️ PvP) pra agir no seu lado; nunca um botão só que
    os 2 dividem.

    🔥 `batalha.cancelar_expirados` (cancelamento de 24h sob demanda)
    REMOVIDA daqui (2026-09-02) - `SchedulerBatalha` já resolve sozinho em
    background depois de só 10min, não precisa mais de um reset preguiçoso
    no momento de abrir o hub."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        self._montar()

    def _desafio(self):
        return db.batalha_ativa_do_jogador(self.guild_id, self.autor_id)

    def _montar(self):
        self.clear_items()
        desafio = self._desafio()
        if desafio is None:
            desafiar = discord.ui.Button(label="Desafiar", emoji="⚔️", style=discord.ButtonStyle.danger, row=0)
            desafiar.callback = self._abrir_desafiar
            self.add_item(desafiar)
        else:
            papel = batalha.papel_do_jogador(desafio, self.autor_id)
            if desafio["status"] == "aguardando_defensor" and papel == "defensor":
                montar = discord.ui.Button(label="Montar Defesa", emoji="🛡️", style=discord.ButtonStyle.success, row=0)
                montar.callback = self._montar_defesa
                self.add_item(montar)
                recusar = discord.ui.Button(label="Recusar", emoji="🏳️", style=discord.ButtonStyle.danger, row=0)
                recusar.callback = self._recusar
                self.add_item(recusar)
        atualizar = discord.ui.Button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
        atualizar.callback = self._atualizar
        self.add_item(atualizar)
        # 🔥 Auto-Defesa (2026-09-02, pedido do usuário: "É possivel deixar
        # configurado p players tbm") - toggle sempre visível (não depende
        # de ter desafio ativo) - liga/desliga ser defendido na hora, igual
        # um bot, sem precisar esperar os 10min do `SchedulerBatalha`.
        auto_defesa_ativa = db.auto_defesa_batalha_ativa(self.guild_id, self.autor_id)
        auto_defesa_botao = discord.ui.Button(
            label=f"Auto-Defesa: {'Ligada' if auto_defesa_ativa else 'Desligada'}", emoji="🤖",
            style=discord.ButtonStyle.success if auto_defesa_ativa else discord.ButtonStyle.secondary, row=1,
        )
        auto_defesa_botao.callback = self._alternar_auto_defesa
        self.add_item(auto_defesa_botao)

    def formatar(self):
        return _embed_batalha(self._desafio(), self.autor_id)

    async def _somente_autor(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.autor_id:
            await interaction.response.send_message("Esse painel não é seu - abra o seu em `/pandora` -> ⚔️ PvP.", ephemeral=True)
            return False
        return True

    async def _atualizar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        self._montar()
        await interaction.response.edit_message(embed=self.formatar(), view=self)

    async def _alternar_auto_defesa(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        novo_estado = not db.auto_defesa_batalha_ativa(self.guild_id, self.autor_id)
        await asyncio.to_thread(db.definir_auto_defesa_batalha, self.guild_id, self.autor_id, novo_estado)
        self._montar()
        await interaction.response.edit_message(embed=self.formatar(), view=self)

    async def _abrir_desafiar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        view = _ViewEscolherAlvoBatalha(self.guild_id, interaction.user.id)
        await interaction.response.send_message("Quem você quer desafiar?", view=view, ephemeral=True)

    async def _montar_defesa(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        desafio = self._desafio()
        if desafio is None:
            await interaction.response.send_message("Esse desafio não existe mais.", ephemeral=True)
            return
        guild_id = self.guild_id
        desafio_id = desafio["id"]

        async def _apos_formacao(interacao_formacao: discord.Interaction, categorias_ordem):
            # 🔥 `defer()` PRIMEIRO (2026-09-02, mesmo achado do usuário e
            # mesmo fix do desafio contra bot, acima - "GAIA nao respondeu a
            # tempo") - `montar_defesa` via `to_thread` não pode rodar antes
            # do primeiro ack, senão o token da interação pode expirar.
            await interacao_formacao.response.defer()
            ok, erro, desafio_atualizado = await asyncio.to_thread(
                batalha.montar_defesa, guild_id, desafio_id, interacao_formacao.user.id, categorias_ordem,
            )
            if not ok:
                await interacao_formacao.edit_original_response(content=f"❌ {erro}", view=None)
                return
            await _resolver_e_revelar(interacao_formacao, desafio_atualizado)

        view_formacao = _ViewEscolherFormacaoBatalha(_apos_formacao)
        await interaction.response.send_message(
            "Escolha a categoria de cada uma das 5 posições da sua formação (só a categoria importa - CP e posse de personagem não afetam o resultado):",
            view=view_formacao, ephemeral=True,
        )

    async def _recusar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        desafio = self._desafio()
        if desafio is None:
            await interaction.response.send_message("Esse desafio não existe mais.", ephemeral=True)
            return
        ok, erro = await asyncio.to_thread(batalha.recusar_desafio, desafio["id"], interaction.user.id)
        if not ok:
            await interaction.response.send_message(erro, ephemeral=True)
            return
        await interaction.response.send_message("🏳️ Desafio recusado - o desafiante foi reembolsado.", ephemeral=True)

class _ViewEscolherFormacaoBatalha(discord.ui.View):
    """5 seletores (1 por posição) - DPS/Tank/Support (2026-09-02, pedido
    do usuário: "em vez de eu ter q escolher os personagens q vao
    participar, deixar escolher apenas as categorias e suas posições") -
    a formação vira só a lista de categorias escolhidas, sem depender de
    posse de personagem nenhuma (`batalha.montar_formacao_por_categoria`,
    2026-09-02 - correção do usuário: "o CP n importa de qq forma"),
    substitui a Party como formação de Batalha (a Party continua
    existindo, só que agora só pra Torre). Avança sozinho assim que as 5
    posições forem escolhidas -
    sem botão de confirmar à parte (as 5 linhas do Discord já são
    ocupadas pelos 5 seletores). `ao_completo(interaction, categorias_
    ordem)` roda só quando a 5ª posição é escolhida."""

    def __init__(self, ao_completo):
        super().__init__(timeout=120)
        self._ao_completo = ao_completo
        self._categorias = [None] * db.MAX_POSICOES_EQUIPE
        for posicao in range(db.MAX_POSICOES_EQUIPE):
            select = discord.ui.Select(
                placeholder=f"Posição {posicao + 1}...",
                options=[
                    discord.SelectOption(label=categoria, emoji=torre.icone_categoria(categoria), value=categoria)
                    for categoria in batalha.CATEGORIAS_VALIDAS
                ],
                row=posicao,
            )
            select.callback = self._escolheu(posicao)
            self.add_item(select)

    def _escolheu(self, posicao):
        async def callback(interaction: discord.Interaction):
            self._categorias[posicao] = self.children[posicao].values[0]
            if None in self._categorias:
                await interaction.response.defer()
                return
            await self._ao_completo(interaction, list(self._categorias))
        return callback


class _ViewEscolherAlvoBatalha(discord.ui.View):
    """Passo 1 de "⚔️ Desafiar" - escolher o jogador-alvo via `discord.ui.
    UserSelect` (mesmo padrão de `_ViewEscolherAlvoTroca`); passo 2 é a
    busca por nome na coleção DELE (`_ModalBuscarPersonagem`, reaproveitado
    sem nenhuma mudança - já aceita qualquer coleção como parâmetro)."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        self._alvo = None
        select = discord.ui.UserSelect(placeholder="Quem você quer desafiar?")
        select.callback = self._selecionou
        self.add_item(select)
        self._select = select

    async def _selecionou(self, interaction: discord.Interaction):
        alvo = self._select.values[0]
        if str(alvo.id) == self.autor_id:
            await interaction.response.send_message("Você não pode desafiar a si mesmo.", ephemeral=True)
            return
        colecao_alvo = await asyncio.to_thread(db.colecao_do_usuario, self.guild_id, alvo.id)
        if not colecao_alvo:
            await interaction.response.send_message(f"{alvo.display_name} ainda não tem nenhuma personagem.", ephemeral=True)
            return
        self._alvo = alvo
        modal = _ModalBuscarPersonagem(
            f"Desafiar {alvo.display_name} por quem?", colecao_alvo,
            "Escolha a personagem que você quer conquistar...", self._personagem_escolhida,
        )
        await interaction.response.send_modal(modal)

    async def _personagem_escolhida(self, interaction: discord.Interaction, personagens, _candidatos):
        personagem = personagens[0]
        aposta = batalha.calcular_aposta(personagem)
        alvo = self._alvo
        guild_id = self.guild_id

        async def _apos_formacao(interacao_formacao: discord.Interaction, categorias_ordem):
            async def _confirmar(interacao_confirmacao: discord.Interaction):
                # 🔥 `defer()` PRIMEIRO, antes de qualquer `to_thread` (2026-09-02,
                # achado do usuário: "GAIA nao respondeu a tempo" ao confirmar
                # contra um bot - mesma classe de bug já corrigida em `_rolar`,
                # "defer ANTES de chamar rolar_varios, não depois") - a versão
                # antiga só reconhecia a interação DEPOIS de `iniciar_desafio` E
                # (pro caso de bot) `montar_defesa`, os 2 via `to_thread` - juntos
                # podiam facilmente estourar os 3s do Discord antes do primeiro
                # ack, matando o token da interação. `_resolver_e_revelar` já
                # exigia isso no próprio docstring ("interaction já precisa estar
                # deferida") - só esta função não cumpria.
                #
                # 🔥 Log passo a passo + captura explícita de exceção (2026-09-02,
                # pedido do usuário depois de "nada aconteceu" 2x sem NENHUM
                # rastro no log - "Coloca log se ta tendo dificuldade de
                # encontrar os problemas") - o resto do fluxo de Batalha nunca
                # logou nada em caminho de sucesso, então não dava pra saber se
                # a interação nem chegava aqui, travava num dos `to_thread`, ou
                # uma exceção estava sendo engolida silenciosamente por algum
                # handler do discord.py sem cair no log redirecionado.
                print(f" [BATALHA] _confirmar (desafiar) iniciado - desafiante={interacao_confirmacao.user.id} alvo={alvo.id} (bot={alvo.bot}) personagem={personagem['id']}")
                try:
                    await interacao_confirmacao.response.defer()
                    print(" [BATALHA] defer() OK")
                    canal_id = interacao_confirmacao.channel.id if interacao_confirmacao.channel else None
                    ok, erro, desafio_id = await asyncio.to_thread(
                        batalha.iniciar_desafio, guild_id, interacao_confirmacao.user.id, alvo.id, personagem["id"],
                        categorias_ordem, canal_id=canal_id,
                    )
                    print(f" [BATALHA] iniciar_desafio -> ok={ok} erro={erro} desafio_id={desafio_id}")
                    if not ok:
                        await interacao_confirmacao.edit_original_response(content=f"❌ {erro}", view=None)
                        return
                    # 🔥 Auto-Defesa (2026-09-02, pedido do usuário: "coloca um
                    # modo defesa automatica... Bots respondem na hr com essa
                    # logica. É possivel deixar configurado p players tbm") -
                    # bot SEMPRE (não abre hub pra responder) ou jogador que
                    # ligou a Auto-Defesa (`db.auto_defesa_batalha_ativa`) -
                    # resolve JÁ, mesma lógica dos 2 casos (`defesa_automatica`
                    # conta o que vence cada categoria do desafiante e
                    # embaralha a ordem). Quem NÃO ligou continua esperando
                    # resposta manual, com `SchedulerBatalha` resolvendo sozinho
                    # depois de 10min se ninguém responder.
                    auto_defesa = alvo.bot or await asyncio.to_thread(db.auto_defesa_batalha_ativa, guild_id, alvo.id)
                    if auto_defesa:
                        formacao_auto = await asyncio.to_thread(batalha.defesa_automatica_para_desafio, desafio_id)
                        print(f" [BATALHA] auto-defesa (bot={alvo.bot}) - formação: {formacao_auto}")
                        ok_defesa, erro_defesa, desafio_atualizado = await asyncio.to_thread(
                            batalha.montar_defesa, guild_id, desafio_id, alvo.id, formacao_auto,
                        )
                        print(f" [BATALHA] montar_defesa -> ok={ok_defesa} erro={erro_defesa}")
                        if not ok_defesa:
                            await interacao_confirmacao.edit_original_response(content=f"❌ {erro_defesa}", view=None)
                            return
                        print(" [BATALHA] entrando em _resolver_e_revelar...")
                        await _resolver_e_revelar(interacao_confirmacao, desafio_atualizado)
                        print(" [BATALHA] _resolver_e_revelar concluído.")
                        return
                    await interacao_confirmacao.edit_original_response(
                        content=(
                            f"⚔️ Desafio enviado! {aposta} WiShards em risco - aguardando {alvo.mention} responder "
                            f"(acompanhe em `/pandora` -> ⚔️ PvP)."
                        ),
                        view=None,
                    )
                    await _anunciar_desafio(interacao_confirmacao.channel, guild_id, desafio_id, alvo.mention)
                    print(" [BATALHA] desafio contra humano enviado com sucesso.")
                except Exception:
                    print(" [BATALHA] !!! EXCEÇÃO dentro de _confirmar (desafiar) !!!")
                    traceback.print_exc()
                    try:
                        await interacao_confirmacao.edit_original_response(content="❌ Erro interno - já registrado no log.", view=None)
                    except Exception:
                        print(" [BATALHA] (falhou até tentar avisar o usuário do erro - ver traceback acima)")

            async def _cancelar(interacao_cancelamento: discord.Interaction):
                await interacao_cancelamento.response.edit_message(content="Desafio cancelado.", view=None)

            view_confirmar = _ViewConfirmar(_confirmar, ao_cancelar=_cancelar)
            await interacao_formacao.response.edit_message(
                content=(
                    f"Desafiar {alvo.mention} por **{personagem['nome']}** ({gacha.estrelas_por_raridade(personagem['raridade'])}) - "
                    f"você arrisca **{aposta} WiShards**, mas só paga de verdade se PERDER (vencer não custa nada, esses "
                    f"WiShards não são debitados agora). Confirma?"
                ),
                view=view_confirmar,
            )

        view_formacao = _ViewEscolherFormacaoBatalha(_apos_formacao)
        await interaction.response.edit_message(
            content="Escolha a categoria de cada uma das 5 posições da sua formação (só a categoria importa - CP e posse de personagem não afetam o resultado):",
            view=view_formacao,
        )


# ==========================================================================
# World Boss (2026-09-01) - regra de negócio/scheduler em `pandora.
# worldboss`; aqui só o painel `/pandora` -> 🐉 World Boss. COOPERATIVO -
# `ViewWorldBossHub` de propósito NÃO restringe por autor (qualquer membro
# do servidor participa clicando as mesmas categorias), diferente de todo
# o resto deste módulo (que é sempre um painel PESSOAL).
# ==========================================================================

class _ViewWorldBossAuto(discord.ui.View):
    """Preferência de Entrada Automática (Seção 8/9) - ephemeral, só quem
    abriu vê (não precisa de checagem de autor extra - já é pessoal por
    ser ephemeral)."""

    def __init__(self, guild_id, user_id, ativo, categorias):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.user_id = str(user_id)
        self._ativo = ativo
        self._categorias = list(categorias)
        self._montar()

    def _montar(self):
        self.clear_items()
        toggle = discord.ui.Button(
            label="Desativar" if self._ativo else "Ativar", emoji="⚙️",
            style=discord.ButtonStyle.danger if self._ativo else discord.ButtonStyle.success, row=0,
        )
        toggle.callback = self._toggle
        self.add_item(toggle)
        select = discord.ui.Select(
            placeholder="Categorias permitidas...", min_values=1, max_values=len(worldboss.CATEGORIAS),
            options=[
                discord.SelectOption(label=c, emoji=torre.icone_categoria(c), value=c, default=c in self._categorias)
                for c in worldboss.CATEGORIAS
            ],
            row=1,
        )
        select.callback = self._definir_categorias
        self.add_item(select)

    def formatar(self):
        status = "✅ Ativa" if self._ativo else "❌ Desativada"
        return (
            f"⚙️ **Entrada Automática no World Boss** (Seção 8/9 - só participa se você NÃO tiver entrado manualmente)\n"
            f"Status: {status}\nCategorias permitidas: {', '.join(self._categorias)}"
        )

    async def _toggle(self, interaction: discord.Interaction):
        self._ativo = not self._ativo
        db.worldboss_definir_auto(self.guild_id, self.user_id, self._ativo, self._categorias)
        self._montar()
        await interaction.response.edit_message(content=self.formatar(), view=self)

    async def _definir_categorias(self, interaction: discord.Interaction):
        self._categorias = list(interaction.data["values"])
        db.worldboss_definir_auto(self.guild_id, self.user_id, self._ativo, self._categorias)
        self._montar()
        await interaction.response.edit_message(content=self.formatar(), view=self)


class ViewWorldBossHub(discord.ui.View):
    """Painel "🐉 World Boss" - sempre reconstrói o estado fresco do banco
    (mesmo padrão de `ViewBatalhaHub`) - restart-safe, nenhum turno/
    inscrição depende desta View específica sobreviver (o scheduler roda
    sozinho, isto aqui é só consulta+entrada). Botões de categoria são
    TOGGLE (Seção 5/6) - clicar de novo na mesma categoria remove ela do
    conjunto permitido."""

    def __init__(self, guild_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self._montar()

    def _evento(self):
        return db.worldboss_evento_ativo(self.guild_id)

    def _montar(self):
        self.clear_items()
        evento = self._evento()
        if evento is not None and evento["status"] == "inscricoes":
            for categoria in worldboss.CATEGORIAS:
                botao = discord.ui.Button(
                    label=categoria, emoji=torre.icone_categoria(categoria), style=discord.ButtonStyle.primary, row=0,
                )
                botao.callback = self._alternar(categoria)
                self.add_item(botao)
        auto = discord.ui.Button(label="Entrada Automática", emoji="⚙️", style=discord.ButtonStyle.secondary, row=1)
        auto.callback = self._abrir_auto
        self.add_item(auto)
        atualizar = discord.ui.Button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
        atualizar.callback = self._atualizar
        self.add_item(atualizar)

    def formatar(self):
        evento = self._evento()
        if evento is None:
            return discord.Embed(
                title="🐉 World Boss",
                description="Nenhum World Boss ativo agora - aparece às 10h/14h/18h/22h (horário de Brasília).",
                color=0xC0392B,
            )
        return worldboss.embed_status(evento)

    async def _atualizar(self, interaction: discord.Interaction):
        self._montar()
        await interaction.response.edit_message(embed=self.formatar(), view=self)

    def _alternar(self, categoria):
        async def callback(interaction: discord.Interaction):
            evento = self._evento()
            if evento is None or evento["status"] != "inscricoes":
                self._montar()
                await interaction.response.edit_message(embed=self.formatar(), view=self)
                return
            ok, mensagem, _personagem, _cp = await asyncio.to_thread(
                worldboss.alternar_categoria, evento["id"], self.guild_id, interaction.user.id, categoria,
            )
            self._montar()
            await interaction.response.edit_message(embed=self.formatar(), view=self)
            await interaction.followup.send(mensagem, ephemeral=True)
        return callback

    async def _abrir_auto(self, interaction: discord.Interaction):
        ativo, categorias = await asyncio.to_thread(db.worldboss_auto_ativo, self.guild_id, interaction.user.id)
        view = _ViewWorldBossAuto(self.guild_id, interaction.user.id, ativo, categorias)
        await interaction.response.send_message(view.formatar(), view=view, ephemeral=True)


# ==========================================================================
# Itens/Conquistas (2026-09-01, "World Boss: Recompensas e Conquistas") -
# regra de negócio em `pandora.itens`/`pandora.conquistas`, aqui só a UI.
# ==========================================================================

class _ViewLojaItens(discord.ui.View):
    """Loja de itens raros (Seção 14) - mesmo catálogo do drop do World
    Boss, comprado com WiShards."""

    def __init__(self, guild_id):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        select = discord.ui.Select(
            placeholder="Escolha o item...",
            options=[
                discord.SelectOption(
                    label=f"{dados['nome']} - {itens.PRECOS_LOJA_ITENS[chave]} WiShards", value=chave,
                    description=dados["descricao"][:100],
                )
                for chave, dados in itens.CATALOGO_ITENS.items()
            ],
        )
        select.callback = self._selecionou
        self.add_item(select)

    async def _selecionou(self, interaction: discord.Interaction):
        item = interaction.data["values"][0]
        dados = itens.CATALOGO_ITENS[item]
        preco = itens.PRECOS_LOJA_ITENS[item]

        async def _confirmar(interacao_confirmacao: discord.Interaction):
            ok, mensagem = itens.comprar_item(self.guild_id, interacao_confirmacao.user.id, item, 1)
            await interacao_confirmacao.response.edit_message(content=mensagem, view=None)

        view = _ViewConfirmar(_confirmar)
        await interaction.response.edit_message(
            content=f"{dados['nome']} - {dados['descricao']}\nCusta **{preco} WiShards**. Confirma?", view=view,
        )


class ViewInventarioHub(discord.ui.View):
    """Painel "🎒 Inventário" - painel PESSOAL (restrito ao autor, ao
    contrário do World Boss). Só mostra botão de usar pra item que o
    jogador REALMENTE tem (Roll/Claim Permanente não têm botão - já se
    aplicam sozinhos na hora do ganho/compra, só mostrados como status)."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        self._montar()

    def _montar(self):
        self.clear_items()
        posse = db.itens_do_jogador(self.guild_id, self.autor_id)
        if posse.get("protecao", 0) > 0:
            botao = discord.ui.Button(label="Usar Proteção", emoji="🛡️", style=discord.ButtonStyle.primary, row=0)
            botao.callback = self._usar_protecao
            self.add_item(botao)
        if posse.get("revanche", 0) > 0:
            botao = discord.ui.Button(label="Usar Revanche", emoji="⚔️", style=discord.ButtonStyle.primary, row=0)
            botao.callback = self._usar_revanche
            self.add_item(botao)
        if posse.get("chave_da_torre", 0) > 0 and not db.chave_torre_ativa(self.guild_id, self.autor_id):
            botao = discord.ui.Button(label="Ativar Chave da Torre", emoji="🗝️", style=discord.ButtonStyle.primary, row=0)
            botao.callback = self._usar_chave
            self.add_item(botao)
        if posse.get("upgrade_construcao", 0) > 0:
            botao = discord.ui.Button(label="Usar Upgrade de Construção", emoji="🏗️", style=discord.ButtonStyle.primary, row=1)
            botao.callback = self._usar_construcao
            self.add_item(botao)
        if posse.get("chamado", 0) > 0:
            botao = discord.ui.Button(label="Usar Chamado", emoji="📯", style=discord.ButtonStyle.primary, row=1)
            botao.callback = self._usar_chamado
            self.add_item(botao)
        atualizar = discord.ui.Button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.secondary, row=2)
        atualizar.callback = self._atualizar
        self.add_item(atualizar)

    def formatar(self):
        posse = db.itens_do_jogador(self.guild_id, self.autor_id)
        bonus_rolls_drop, bonus_claims_drop = db.bonus_permanente_drop(self.guild_id, self.autor_id)
        bonus_rolls_loja, bonus_claims_loja = db.bonus_permanente_loja(self.guild_id, self.autor_id)
        embed = discord.Embed(title="🎒 Inventário", color=_COR_HUB)
        linhas = [f"{itens.CATALOGO_ITENS[chave]['nome']}: {qtd}" for chave, qtd in posse.items()]
        # 🔥 Contadores SEPARADOS (2026-09-01) - drop do World Boss e compra
        # na Loja têm teto PRÓPRIO cada um, nunca somados na mesma barra.
        if bonus_rolls_drop:
            linhas.append(f"🎲 Roll Permanente (World Boss): +{bonus_rolls_drop} (limite {itens.LIMITE_ROLL_PERMANENTE})")
        if bonus_rolls_loja:
            linhas.append(f"🎲 Roll Permanente (Loja): +{bonus_rolls_loja} (limite {itens.LIMITE_ROLL_PERMANENTE})")
        if bonus_claims_drop:
            linhas.append(f"💎 Claim Permanente (World Boss): +{bonus_claims_drop} (limite {itens.LIMITE_CLAIM_PERMANENTE})")
        if bonus_claims_loja:
            linhas.append(f"💎 Claim Permanente (Loja): +{bonus_claims_loja} (limite {itens.LIMITE_CLAIM_PERMANENTE})")
        embed.description = "\n".join(linhas) if linhas else "Vazio - itens vêm de drop raro do World Boss ou da Loja."
        if db.chave_torre_ativa(self.guild_id, self.autor_id):
            embed.add_field(name="🗝️ Chave da Torre", value="Ativa - sua próxima tentativa de andar ignora a restrição.", inline=False)
        protegidas = db.personagens_protegidas_pvp(self.guild_id, self.autor_id)
        if protegidas:
            nomes = [p["nome"] for p in (db.personagem_por_id(pid) for pid in protegidas) if p]
            embed.add_field(name="🛡️ Personagens protegidas", value=", ".join(nomes), inline=False)
        niveis = db.niveis_construcoes(self.guild_id, self.autor_id)
        if niveis:
            linhas_construcao = [f"{itens.AREAS_CONSTRUCAO[area]} ({area}): Nível {nivel}" for area, nivel in niveis.items()]
            embed.add_field(name="🏗️ Construções", value="\n".join(linhas_construcao), inline=False)
        return embed

    async def _atualizar(self, interaction: discord.Interaction):
        self._montar()
        await interaction.response.edit_message(embed=self.formatar(), view=self)

    async def _usar_protecao(self, interaction: discord.Interaction):
        colecao = await asyncio.to_thread(db.colecao_do_usuario, self.guild_id, interaction.user.id)
        if not colecao:
            await interaction.response.send_message("Você não tem nenhuma personagem.", ephemeral=True)
            return

        async def _ao_selecionar(interacao_sel, personagens, _candidatos):
            ok, mensagem = itens.usar_protecao(self.guild_id, interacao_sel.user.id, personagens[0]["id"])
            await interacao_sel.response.edit_message(content=mensagem, view=None)

        modal = _ModalBuscarPersonagem("Proteger qual personagem?", colecao, "Escolha a personagem...", _ao_selecionar)
        await interaction.response.send_modal(modal)

    async def _usar_revanche(self, interaction: discord.Interaction):
        perdidas = await asyncio.to_thread(db.personagens_perdidas_recuperaveis, self.guild_id, interaction.user.id)
        if not perdidas:
            await interaction.response.send_message("Você não tem nenhuma personagem perdida pra recuperar.", ephemeral=True)
            return

        async def _ao_selecionar(interacao_sel, personagens):
            personagem = personagens[0]
            dono_atual = await asyncio.to_thread(db.dono_do_personagem, self.guild_id, personagem["id"])
            if dono_atual is None:
                await interacao_sel.response.send_message("Essa personagem não tem dono agora - Revanche não se aplica.", ephemeral=True)
                return

            async def _apos_formacao(interacao_formacao: discord.Interaction, categorias_ordem):
                # 🔥 `defer()` PRIMEIRO (2026-09-02, mesmo achado do usuário -
                # "GAIA nao respondeu a tempo" - aplicado em todo `to_thread`
                # de Batalha que rodava antes do 1º ack da interação).
                await interacao_formacao.response.defer()
                canal_id = interacao_formacao.channel.id if interacao_formacao.channel else None
                ok, erro, desafio_id = await asyncio.to_thread(
                    batalha.iniciar_desafio_com_revanche, self.guild_id, interacao_formacao.user.id, dono_atual,
                    personagem["id"], categorias_ordem, canal_id=canal_id,
                )
                if not ok:
                    await interacao_formacao.edit_original_response(content=f"❌ {erro}", view=None)
                    return
                # 🔥 Auto-Defesa (2026-09-02) - mesma lógica do fluxo normal de
                # Desafiar (ver `_personagem_escolhida`) - bot ou jogador com
                # Auto-Defesa ligada resolve JÁ, sem esperar.
                alvo_membro = interacao_formacao.guild.get_member(int(dono_atual)) if interacao_formacao.guild else None
                auto_defesa = (alvo_membro is not None and alvo_membro.bot) or await asyncio.to_thread(
                    db.auto_defesa_batalha_ativa, self.guild_id, dono_atual,
                )
                if auto_defesa:
                    formacao_auto = await asyncio.to_thread(batalha.defesa_automatica_para_desafio, desafio_id)
                    ok_defesa, erro_defesa, desafio_atualizado = await asyncio.to_thread(
                        batalha.montar_defesa, self.guild_id, desafio_id, dono_atual, formacao_auto,
                    )
                    if not ok_defesa:
                        await interacao_formacao.edit_original_response(content=f"❌ {erro_defesa}", view=None)
                        return
                    await _resolver_e_revelar(interacao_formacao, desafio_atualizado)
                    return
                await interacao_formacao.edit_original_response(
                    content="⚔️ Revanche usada - desafio criado! Acompanhe em `/pandora` -> ⚔️ PvP.", view=None,
                )

            view_formacao = _ViewEscolherFormacaoBatalha(_apos_formacao)
            await interacao_sel.response.edit_message(
                content="Escolha a categoria de cada uma das 5 posições da sua formação:", view=view_formacao,
            )

        view = _ViewSelecionarPersonagem(perdidas, "Escolha quem recuperar...", _ao_selecionar)
        await interaction.response.send_message("Selecione:", view=view, ephemeral=True)

    async def _usar_chave(self, interaction: discord.Interaction):
        ok, mensagem = itens.usar_chave_da_torre(self.guild_id, interaction.user.id)
        self._montar()
        await interaction.response.edit_message(content=mensagem, embed=self.formatar(), view=self)

    async def _usar_construcao(self, interaction: discord.Interaction):
        select = discord.ui.Select(
            placeholder="Escolha a área...",
            options=[discord.SelectOption(label=f"{nome} ({area})", value=area) for area, nome in itens.AREAS_CONSTRUCAO.items()],
        )

        async def _callback(interacao_sel: discord.Interaction):
            ok, mensagem = itens.usar_upgrade_construcao(self.guild_id, interacao_sel.user.id, interacao_sel.data["values"][0])
            await interacao_sel.response.edit_message(content=mensagem, view=None)

        select.callback = _callback
        view_select = discord.ui.View(timeout=60)
        view_select.add_item(select)
        await interaction.response.send_message("Escolha onde aplicar o Upgrade de Construção:", view=view_select, ephemeral=True)

    async def _usar_chamado(self, interaction: discord.Interaction):
        select = discord.ui.Select(
            placeholder="Escolha o Boss...",
            options=[
                discord.SelectOption(label=dados["nome"], value=tipo) for tipo, dados in worldboss.CATALOGO_BOSSES.items()
            ],
        )

        async def _callback(interacao_sel: discord.Interaction):
            ok, mensagem = itens.usar_chamado(self.guild_id, interacao_sel.user.id, interacao_sel.data["values"][0])
            await interacao_sel.response.edit_message(content=mensagem, view=None)

        select.callback = _callback
        view_select = discord.ui.View(timeout=60)
        view_select.add_item(select)
        await interaction.response.send_message("Escolha o próximo World Boss desse servidor:", view=view_select, ephemeral=True)


class ViewConquistasHub(discord.ui.View):
    """Painel "🏆 Conquistas" - 2 famílias distintas (2026-09-01): 🐉 World
    Boss (registro puro, Seção 15 - lista só o que já foi desbloqueado) e
    📚 Colecionador (`ERIS_sistema_colecao_wishards.md` Seções 22/24, paga
    WiShards por marco - mostra PROGRESSO de todas as famílias, mesmo as
    ainda sem nenhum marco batido, não só as já desbloqueadas)."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)

    def formatar(self):
        desbloqueadas = conquistas.do_jogador(self.guild_id, self.autor_id)
        nomes_wb = [nome for conquista_id, nome, _descricao, _data in desbloqueadas if conquista_id.startswith("wb_")]
        embed = discord.Embed(title="🏆 Conquistas", color=_COR_HUB)
        embed.add_field(
            name=f"🐉 World Boss ({len(nomes_wb)})",
            value="\n".join(nomes_wb) if nomes_wb else "Nenhuma ainda.",
            inline=False,
        )
        progresso = conquistas.progresso_colecionador(self.guild_id, self.autor_id)
        linhas_progresso = []
        for nome, valor_atual, tier, proximo in progresso:
            marcadores = "⭐" * tier + "▫️" * (5 - tier)
            valor_fmt = _fmt_numero(valor_atual)
            if proximo is not None:
                linhas_progresso.append(f"{nome}: {marcadores} ({valor_fmt}/{_fmt_numero(proximo)})")
            else:
                linhas_progresso.append(f"{nome}: {marcadores} (completo!)")
        embed.add_field(name="📚 Colecionador - progresso", value="\n".join(linhas_progresso), inline=False)
        return embed

    @discord.ui.button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def atualizar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        novos = await asyncio.to_thread(conquistas.verificar_colecionador, self.guild_id, self.autor_id)
        embed = await asyncio.to_thread(self.formatar)
        if novos:
            nomes_novos = [conquistas.CATALOGO[c]["nome"] for c in novos]
            embed.add_field(name="🎉 Novas conquistas!", value="\n".join(nomes_novos), inline=False)
        await interaction.response.edit_message(embed=embed, view=self)


_ORDEM_CATEGORIAS_BONUS = ("DPS", "Tank", "Support", "Sem categoria")


class ViewBonusClasseHub(discord.ui.View):
    """Painel "⚔️ Bônus por Classe" (2026-09-02, pedido do usuário: "uma
    nova tela q mostrasse q DPS ta ganhando +X Tank +Y... e n sei se
    separou por classe tbm") - 1 campo por categoria de combate (DPS/Tank/
    Support), com o total somado das classes que o jogador possui daquela
    categoria, e logo abaixo a lista de CADA classe com seu próprio
    bônus/progresso (`db.bonus_classes_por_categoria`)."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)

    def formatar(self):
        categorias = db.bonus_classes_por_categoria(self.guild_id, self.autor_id)
        embed = discord.Embed(title="⚔️ Bônus por Classe", color=_COR_HUB)
        if not categorias:
            embed.description = "Você ainda não tem nenhuma personagem com classe revelada."
            return embed
        ordem = [c for c in _ORDEM_CATEGORIAS_BONUS if c in categorias]
        ordem += [c for c in categorias if c not in ordem]
        for categoria in ordem:
            dados = categorias[categoria]
            icone = torre.icone_categoria(categoria) if categoria != "Sem categoria" else "❓"
            linhas = [
                f"{c['classe']}: +{c['bonus']} CP ({c['quantidade']}/{c['proximo_marco']} p/ próximo marco)"
                for c in dados["classes"]
            ]
            embed.add_field(
                name=f"{icone} {categoria} - +{dados['total_bonus']} CP no total ({dados['total_personagens']} personagens)",
                value="\n".join(linhas)[:1024],
                inline=False,
            )
        return embed

    @discord.ui.button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def atualizar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        embed = await asyncio.to_thread(self.formatar)
        await interaction.response.edit_message(embed=embed, view=self)


# ==========================================================================
# Investir em Massa (2026-09-01, pedido do usuário: "permitir aumentar
# afinidade e nível em massa das personagens ordenadas pelo de maior CP,
# apenas informando qnt pretende investir") - regra de negócio em
# `pandora.torre._investir_em_massa`/`investir_nivel_em_massa`/
# `investir_afinidade_em_massa`, aqui só a UI.
# ==========================================================================

class _ModalInvestirEmMassa(discord.ui.Modal):
    """🔥 `saldo_atual` (2026-09-01, pedido do usuário: "o investir em
    massa tem que informar quanto tenho para investir") - o campo do
    Modal não pode mostrar um valor pronto de antemão sem ser um `Text
    Input` de VERDADE construído por instância (por isso não é mais um
    atributo de classe fixo) - o saldo (WiShards ou Soulstone, conforme
    `tipo`) já vem no LABEL, visível antes mesmo de digitar."""

    def __init__(self, guild_id, tipo, saldo_atual, colecao=None):
        """`colecao` (opcional, 2026-09-03, pedido do usuário: "botao la
        tbm p maximizar nivel e afinidade da serie, assim como é o em
        massa") - escopo alternativo à coleção INTEIRA (default `None`),
        usado pelo navegador de Série Favorita pra restringir o
        investimento só às personagens daquela série."""
        super().__init__(title=f"Investir em massa - {'Nível' if tipo == 'nivel' else 'Afinidade'}")
        self.guild_id = guild_id
        self.tipo = tipo
        self._colecao = colecao
        moeda = "WiShards" if tipo == "nivel" else "Soulstone"
        self.valor = discord.ui.TextInput(
            label=f"Quanto? (você tem {_fmt_numero(saldo_atual)} {moeda})"[:45],
            placeholder="Ex.: 50000",
        )
        self.add_item(self.valor)

    async def on_submit(self, interaction: discord.Interaction):
        orcamento = _int_seguro(str(self.valor))
        if orcamento <= 0:
            await interaction.response.send_message("Valor inválido.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if self.tipo == "nivel":
            gasto, detalhes = await asyncio.to_thread(
                torre.investir_nivel_em_massa, self.guild_id, interaction.user.id, orcamento, self._colecao,
            )
            moeda = "WiShards"
        else:
            gasto, detalhes = await asyncio.to_thread(
                torre.investir_afinidade_em_massa, self.guild_id, interaction.user.id, orcamento, self._colecao,
            )
            moeda = "Soulstone"
        if not detalhes:
            await interaction.followup.send(f"Nenhuma personagem pôde subir com {orcamento} {moeda} disponível.", ephemeral=True)
            return
        linhas = [f"{personagem['nome']}: {antes} → {depois}" for personagem, antes, depois in detalhes[:25]]
        texto = "\n".join(linhas)
        if len(detalhes) > 25:
            texto += f"\n... e mais {len(detalhes) - 25} personagem(ns)."
        await interaction.followup.send(f"✅ Investidos {gasto}/{orcamento} {moeda} em {len(detalhes)} personagem(ns):\n{texto}", ephemeral=True)


class _ViewInvestirEmMassa(discord.ui.View):
    """Escolhe Nível (WiShards) ou Afinidade (Soulstone) - cada um abre o
    Modal que pede só o orçamento, sem precisar escolher personagem
    nenhuma (a ordem por CP decide sozinha onde investir)."""

    def __init__(self, guild_id):
        super().__init__(timeout=60)
        self.guild_id = guild_id

    @discord.ui.button(label="Nível (WiShards)", emoji="⬆️", style=discord.ButtonStyle.success)
    async def nivel(self, interaction: discord.Interaction, botao: discord.ui.Button):
        saldo = await asyncio.to_thread(db.saldo_wishards, self.guild_id, interaction.user.id)
        await interaction.response.send_modal(_ModalInvestirEmMassa(self.guild_id, "nivel", saldo))

    @discord.ui.button(label="Afinidade (Soulstone)", emoji="💕", style=discord.ButtonStyle.success)
    async def afinidade(self, interaction: discord.Interaction, botao: discord.ui.Button):
        saldo = await asyncio.to_thread(db.saldo_soulstone, self.guild_id, interaction.user.id)
        await interaction.response.send_modal(_ModalInvestirEmMassa(self.guild_id, "afinidade", saldo))
