# -*- coding: utf-8 -*-
"""Hub `/pandora` (`ViewHubWaifu`, `montar_embed_hub`) e a entrada pública da Fusão.

Parte de `pandora.paineis` (dividido por tela em 2026-11-10); de fora do
pacote, continuar usando `from pandora import paineis` e `paineis.<nome>`."""
import asyncio
import discord
from pandora import db
from pandora import cidade, economia, gacha, itens, torre
from pandora.ui_base import ViewPandora
from pandora.paineis.comum import (
    _COR_HUB,
    _ViewConfirmar,
    _ViewEscolherMergeAlvo,
    _fmt_numero,
)
from pandora.paineis.personagem import (
    _ViewNivel,
)
from pandora.paineis.equipe import (
    ViewEquipe,
)
from pandora.paineis.cidade import (
    ViewCidadeHub,
    _ViewTorre,
    _embed_cidade,
    _embed_torre,
)
from pandora.paineis.loja import (
    ViewLoja,
    _ViewEscolherAlvoTroca,
)
from pandora.paineis.batalha import (
    ViewBatalhaHub,
    ViewWorldBossHub,
)
from pandora.paineis.inventario import (
    ViewInventarioHub,
    _ViewInvestirEmMassa,
)
from pandora.paineis.series import (
    _ViewPerfil,
    _enviar_series_favoritas,
    _montar_embed_perfil,
)
from pandora.paineis.waifus import (
    _ViewPersonagensFavoritas,
)


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
    embed.add_field(name="💰 WiShards", value=_fmt_numero(saldo), inline=True)
    embed.add_field(name="📚 Coleção", value=f"{_fmt_numero(len(colecao))} personagem(ns)", inline=True)
    embed.add_field(name="💎 Soulstone", value=_fmt_numero(soulstone), inline=True)
    embed.add_field(name="🏆 Ranking do servidor", value=(f"#{posicao}" if posicao else "sem personagens ainda"), inline=True)
    # 🔥 Progressão Global da conta (2026-08-30, análise do usuário: "a
    # personagem possui um limite de desenvolvimento. A conta não") -
    # Nível SEM TETO, sempre visível aqui (mesmo espírito de mostrar
    # WiShards/Coleção direto no hub, sem precisar abrir outra tela).
    progressao = db.progressao_conta(guild.id, membro.id)
    xp_necessario = db.xp_necessario_nivel(progressao["nivel"], guild.id, membro.id)
    embed.add_field(
        name="📈 Progressão", value=f"Nível {progressao['nivel']} · {_fmt_numero(progressao['xp'])}/{_fmt_numero(xp_necessario)} XP", inline=True,
    )
    return embed


class ViewHubWaifu(ViewPandora):
    """Painel-raiz de `/pandora` - restrito a quem abriu (`autor_id`), mesmo
    espírito de um menu pessoal (o LA também trata painéis de coleção como
    algo individual). `timeout=300` - tempo de sobra pra navegar sem
    precisar reabrir `/pandora` de novo."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        self._montar()

    def _montar(self):
        """Ordem/linhas do hub (2026-09-04, pedido explícito do usuário -
        layout ditado botão por botão):
        Linha 0: Rolar, Claim All, Diária
        Linha 1: Party, Trocas, PvP, Fusão
        Linha 2: Cidade, Torre, World Boss
        Linha 3: Loja, Inventário, Investir em Massa
        Linha 4: Perfil, Personagem, Séries, Wishlist

        Coleção/Classes NÃO estão aqui de propósito - moraram pro "📖
        Perfil" (2026-09-04, pedido anterior do mesmo dia). "Fusão" é o
        MESMO botão que já existia como "Merge" (🔀) - só o rótulo/emoji
        mudaram pra 🧬, callback (`_abrir_merge`) e nome interno intactos."""
        self.clear_items()

        rolar = discord.ui.Button(label="Rolar", emoji="🎲", style=discord.ButtonStyle.success, row=0)
        rolar.callback = self._rolar
        self.add_item(rolar)
        reivindicar_tudo_botao = discord.ui.Button(label="Claim All", emoji="🎯", style=discord.ButtonStyle.success, row=0)
        reivindicar_tudo_botao.callback = self._reivindicar_tudo
        self.add_item(reivindicar_tudo_botao)
        diaria_ok = db.diaria_disponivel(self.guild_id, self.autor_id)
        diaria_botao = discord.ui.Button(
            label="Diária" if diaria_ok else "Diária ✓", emoji="🎁",
            style=discord.ButtonStyle.success if diaria_ok else discord.ButtonStyle.secondary, row=0,
        )
        diaria_botao.callback = self._diaria
        self.add_item(diaria_botao)

        party = discord.ui.Button(label="Party", emoji="👥", style=discord.ButtonStyle.secondary, row=1)
        party.callback = self._party
        self.add_item(party)
        trocar = discord.ui.Button(label="Trocas", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
        trocar.callback = self._trocar
        self.add_item(trocar)
        batalha_botao = discord.ui.Button(label="PvP", emoji="⚔️", style=discord.ButtonStyle.danger, row=1)
        batalha_botao.callback = self._batalha
        self.add_item(batalha_botao)
        merge = discord.ui.Button(label="Fusão", emoji="🧬", style=discord.ButtonStyle.primary, row=1)
        merge.callback = self._abrir_merge
        self.add_item(merge)

        cidade_botao = discord.ui.Button(label="Cidade", emoji="🏙️", style=discord.ButtonStyle.secondary, row=2)
        cidade_botao.callback = self._cidade
        self.add_item(cidade_botao)
        torre = discord.ui.Button(label="Torre", emoji="🗼", style=discord.ButtonStyle.secondary, row=2)
        torre.callback = self._torre
        self.add_item(torre)
        worldboss_botao = discord.ui.Button(label="World Boss", emoji="🐉", style=discord.ButtonStyle.danger, row=2)
        worldboss_botao.callback = self._worldboss
        self.add_item(worldboss_botao)

        loja = discord.ui.Button(label="Loja", emoji="🛒", style=discord.ButtonStyle.secondary, row=3)
        loja.callback = self._loja
        self.add_item(loja)
        inventario_botao = discord.ui.Button(label="Inventário", emoji="🎒", style=discord.ButtonStyle.secondary, row=3)
        inventario_botao.callback = self._inventario
        self.add_item(inventario_botao)
        investir_botao = discord.ui.Button(label="Investir em Massa", emoji="📈", style=discord.ButtonStyle.secondary, row=3)
        investir_botao.callback = self._investir_em_massa
        self.add_item(investir_botao)

        perfil_botao = discord.ui.Button(label="Perfil", emoji="📖", style=discord.ButtonStyle.secondary, row=4)
        perfil_botao.callback = self._perfil
        self.add_item(perfil_botao)
        ver = discord.ui.Button(label="Personagem", emoji="🔍", style=discord.ButtonStyle.secondary, row=4)
        ver.callback = self._ver
        self.add_item(ver)
        series_favoritas_botao = discord.ui.Button(label="Séries", emoji="❤️", style=discord.ButtonStyle.secondary, row=4)
        series_favoritas_botao.callback = self._series_favoritas
        self.add_item(series_favoritas_botao)
        favoritas_botao = discord.ui.Button(label="Wishlist", emoji="💖", style=discord.ButtonStyle.secondary, row=4)
        favoritas_botao.callback = self._favoritas
        self.add_item(favoritas_botao)

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
        Discord) + `ModalPandora` (termos da troca), em vez dos
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
            f"🎁 Recompensa Diária resgatada! +{_fmt_numero(wishards)} WiShards (saldo: {_fmt_numero(novo_saldo)}) · 🎁 {texto_item}",
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
        escolhida e o bônus de CP ativo pros personagens dela. Núcleo
        compartilhado com o botão 📚 Séries do Perfil em `_enviar_series_
        favoritas` (2026-09-03) - ver docstring de lá pro porquê de
        `_ViewSeriesFavoritas.criar` não poder rodar dentro de um
        `to_thread`."""
        if not await self._somente_autor(interaction):
            return
        await _enviar_series_favoritas(interaction, self.guild_id, interaction.user.id)

    async def _favoritas(self, interaction: discord.Interaction):
        """Wishlist por slots da Torre, com Fortalecimento/Ascensão por slot."""
        if not await self._somente_autor(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        view = await _ViewPersonagensFavoritas.criar(self.guild_id, interaction.user.id)
        await interaction.followup.send(embed=view.montar_embed(), view=view, ephemeral=True)

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
        await interaction.response.defer(ephemeral=True)
        colecao = await asyncio.to_thread(db.colecao_do_usuario, self.guild_id, self.autor_id)
        if len(colecao) < 5:
            await interaction.followup.send("Você precisa de pelo menos 5 personagens pra fazer uma Fusão.", ephemeral=True)
            return
        view = ViewEquipe(
            self.guild_id, self.autor_id, tipo="fusao", titulo="Sua Fusão",
            ao_fundir=self._merge_selecionado,
        )
        await interaction.edit_original_response(content=view.formatar(), view=view)

    async def _merge_selecionado(self, interaction: discord.Interaction, personagens, confirmar=False):
        """2026-09-02 (pedido do usuário: "ele vai deixar trocar 5 da msm
        raridade por 1 da msm raridade disponivel, a escolha") - só valida
        aqui (`economia.validar_merge`); a escolha de qual personagem
        disponível receber vira um 2º passo (`_ViewEscolherMergeAlvo`),
        `economia.executar_merge` só roda depois que o jogador escolhe."""
        await interaction.response.defer()
        ids = [p["id"] for p in personagens]
        ok, mensagem, raridade, precisa_confirmar = await asyncio.to_thread(
            economia.validar_merge, self.guild_id, interaction.user.id, ids, confirmar,
        )
        if precisa_confirmar:
            async def _confirmar(interacao_confirmacao):
                await self._merge_selecionado(interacao_confirmacao, personagens, confirmar=True)
            view = _ViewConfirmar(_confirmar)
            await interaction.edit_original_response(content=f"{mensagem} Confirma a Fusão mesmo assim?", view=view)
            return
        if not ok:
            await interaction.edit_original_response(content=mensagem, view=None)
            return
        permitir_nsfw = await asyncio.to_thread(db.obter_configuracao_colecao, self.guild_id)
        disponiveis = await asyncio.to_thread(
            db.personagens_livres_por_raridade, self.guild_id, raridade, permitir_nsfw["nsfw_permitido"], 25,
        )
        estrelas = "⭐" * raridade
        if not disponiveis:
            await interaction.edit_original_response(
                content=f"Não sobrou nenhuma personagem livre {estrelas} nesse servidor agora - tenta de novo daqui a pouco.",
                view=None,
            )
            return
        view = _ViewEscolherMergeAlvo(self.guild_id, ids, estrelas, disponiveis, tipo_sacrificios="fusao")
        nomes = ", ".join(p["nome"] for p in personagens)
        await interaction.edit_original_response(
            content=f"Sacrifícios selecionados: **{nomes}**.\nEscolha qual personagem {estrelas} você quer receber:",
            view=view,
        )

    async def _cidade(self, interaction: discord.Interaction):
        """Painel de status da Cidade (2026-08-30, análise do usuário Seção
        13 + "n iremos setar personagens em funcoes manualmente, sera
        automatico com base na classe/profissão") - a ALOCAÇÃO de
        personagem por função continua automática, sem nada pra configurar
        aqui; mas ganhou uma View (2026-09-06, pedido do usuário: "Coloca a
        opção comprar e usar Upgrade de Construção no painel da cidade") já
        que o Nível de Construção de cada área É mostrado neste card
        (`Lv{nivel}` no título de cada campo) - antes só dava pra comprar/
        usar esse upgrade indo em Loja + 🎒 Inventário separados. Mensagem
        NOVA (mesmo padrão de Coleção/Party, nunca edita o hub). Coleta a
        produção acumulada desde a última visita na hora de abrir."""
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
        embed = await asyncio.to_thread(_embed_cidade, resultado, self.guild_id, interaction.user.id)
        view = ViewCidadeHub(self.guild_id, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)

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
            f"{gacha._EMOJI_RARIDADE.get(personagem['raridade'], '💘')} {personagem['nome']}: +{_fmt_numero(recompensa)} WiShards"
            for personagem, recompensa in conquistadas[:25]
        ]
        texto = "\n".join(linhas)
        if len(conquistadas) > 25:
            texto += f"\n... e mais {len(conquistadas) - 25} personagem(ns)."
        await interaction.followup.send(
            f"🎯 Reivindicadas {len(conquistadas)} personagem(ns), +{_fmt_numero(total_wishards)} WiShards no total:\n{texto}",
            ephemeral=True,
        )


# ==========================================================================
# Perfil + Séries Favoritas (2026-09-02, redesenho do `/perfil` + sistema
# NOVO de Séries Favoritas - pedido do usuário em cima de uma sugestão
# externa endossada: "acho bem melhor... transforma série de um dado
# inútil entre milhares em uma escolha do jogador"). Regra de negócio em
# `pandora.series_favoritas`, aqui só embed+View.
# ==========================================================================

async def abrir_fusao(interaction: discord.Interaction):
    """Entrada pública da Fusão pra quem está fora do hub (o comando
    `/merge` do bot): abre o MESMO painel do botão "🧬 Fusão", em vez de
    repetir o fluxo de 2 etapas por parâmetro de comando."""
    view = ViewHubWaifu(interaction.guild.id, interaction.user.id)
    await view._abrir_merge(interaction)
