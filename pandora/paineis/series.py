# -*- coding: utf-8 -*-
"""Perfil, Séries Favoritas e navegador de Série.

Parte de `pandora.paineis` (dividido por tela em 2026-11-10); de fora do
pacote, continuar usando `from pandora import paineis` e `paineis.<nome>`."""
import asyncio
import traceback
import discord
from pandora import db
from pandora import conquistas, consulta, gacha, series_favoritas, torre
from pandora.registro import log
from pandora.ui_base import ModalPandora, ViewPandora
from pandora.paineis.comum import (
    _ViewConfirmarComprarTudo,
    _ViewEscolherRanking,
    _descricao_personagem_dropdown,
    _fmt_numero,
)
from pandora.paineis.personagem import (
    _sufixo_aviso_sem_classe,
)
from pandora.paineis.colecao import (
    ViewColecaoHub,
    ViewWishlistHub,
)
from pandora.paineis.inventario import (
    ViewBonusClasseHub,
    ViewConquistasHub,
    _ModalInvestirEmMassa,
)


def _fmt_pct(numerador, denominador):
    if denominador <= 0:
        return f"{numerador}/0"
    return f"{numerador}/{denominador} ({numerador / denominador:.0%})"


def _montar_embed_perfil(guild_id, user_id):
    resumo = db.resumo_perfil_geral(guild_id, user_id)
    por_raridade = db.resumo_perfil_raridade(guild_id, user_id)

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

    # 🔥 Séries Favoritas SAIU do embed do Perfil (2026-09-03, achado do
    # usuário: "Perfil tem limite de caracteres e esta perdendo coleções
    # das series" - até 25 séries favoritadas, ~5 linhas cada, num ÚNICO
    # campo de embed juntado e cortado em `[:1024]` (o teto de UM campo,
    # bem menor que o total real - dado sendo perdido em silêncio). Virou
    # botão próprio ("📚 Séries", `_ViewPerfil._series`) que abre `_montar_
    # embed_series_favoritas` - 1 campo de embed POR série (até 25 campos,
    # teto real do Discord), nunca um campo só com tudo junto. Também evita
    # chamar `series_favoritas.listar` (documentado como CARO) toda vez que
    # o Perfil abre, só quando o botão é clicado.
    embed.add_field(name="❤️ Séries Favoritas", value="Veja/edite com o botão 📚 Séries abaixo.", inline=False)

    embed.add_field(name="🏆 Conquistas", value=_fmt_numero(len(db.conquistas_do_jogador(guild_id, user_id))), inline=True)
    embed.add_field(name="🗼 Torre", value=f"Andar {_fmt_numero(db.andar_atual_torre(guild_id, user_id))}", inline=True)
    embed.add_field(name="💠 Soulstones", value=_fmt_numero(db.saldo_soulstone(guild_id, user_id)), inline=True)
    return embed


# 🔥 Alinhamento da grade 3-colunas (2026-09-03, achado do usuário vendo o
# resultado ao vivo: "consegue deixar tudo bem alinhado?", "independente
# do tamanho do titulo") - título de campo LONGO quebra em 2 linhas,
# título CURTO fica em 1 só; como as 3 colunas de uma mesma linha do
# Discord compartilham a altura da linha mas cada campo começa seu corpo
# logo ABAIXO do próprio título, um título de 1 linha faz o corpo daquele
# campo começar mais alto que o vizinho de título 2 linhas - a "grade"
# desalinha. Corrigido truncando o nome bem curto (`_LARGURA_TITULO_
# SERIE`, orçamento conservador pra nunca quebrar sozinho em 2 linhas,
# nem no client mobile) - todo título fica em 1 linha só, sempre.
# 🔥 (2026-09-03, achado do usuário: "remove esse espaço apos o titulo")
# - a 1ª versão também forçava uma 2ª linha vazia (`\n` + zero-width
# space) em TODO campo pra garantir altura 2 - resolvia o alinhamento mas
# deixava um vão feio entre título e conteúdo em campo nenhum precisava
# disso. Removido - a truncagem sozinha já garante 1 linha sempre, o que
# já é suficiente pro alinhamento (altura constante = 1 linha em vez de
# 2, mas ainda constante).
_LARGURA_TITULO_SERIE = 24


def _nome_campo_serie(slot, serie):
    prefixo = f"Slot {slot}: "
    orcamento = max(_LARGURA_TITULO_SERIE - len(prefixo), 1)
    curto = serie if len(serie) <= orcamento else serie[: orcamento - 1].rstrip() + "…"
    return f"{prefixo}{curto}"


def _montar_embed_series_favoritas(guild_id, user_id):
    """Estatísticas detalhadas das Séries Favoritas (2026-09-03, extraído
    do antigo campo único do Perfil - ver comentário em `_montar_embed_
    perfil`) - 1 CAMPO DE EMBED POR SÉRIE (nunca um campo só com tudo
    junto e cortado em [:1024]) - até 25 séries favoritadas cabem
    confortavelmente nos até 25 campos que um embed aceita, cada um bem
    abaixo do teto de 1024 chars por campo. Título truncado + altura fixa
    via `_nome_campo_serie` - ver comentário acima pro porquê."""
    favoritas = [item for item in series_favoritas.listar(guild_id, user_id) if item["serie"]]
    embed = discord.Embed(title="❤️ Séries Favoritas", color=0x8E44AD)
    if not favoritas:
        embed.description = "Nenhuma ainda - escolha um slot abaixo pra favoritar uma série."
        return embed
    for item in favoritas:
        marco = lambda ok: " ✅" if ok else ""
        bonus_pct = f"+{item['bonus_percentual']:.0%}" if item["bonus_percentual"] else "nenhum"
        valor = (
            f"📚 {_fmt_pct(item['possuidas'], item['total_catalogo'])}{marco(item['colecao_completa'])}\n"
            f"⭐ {_fmt_pct(item['nivel_maximo'], item['possuidas'])}{marco(item['maestria_completa'])}\n"
            f"❤️ {_fmt_pct(item['afinidade_maxima'], item['possuidas'])}{marco(item['afinidade_completa'])}\n"
            f"💕 {_fmt_pct(item['soulmates'], item['possuidas'])}{marco(item['soulbond_completo'])}\n"
            f"Bônus: {bonus_pct} CP"
        )
        embed.add_field(name=_nome_campo_serie(item["slot"], item["serie"]), value=valor, inline=True)
    return embed


async def _enviar_series_favoritas(interaction: discord.Interaction, guild_id, autor_id):
    """Núcleo compartilhado de "abrir a tela de Séries Favoritas" - usado
    tanto pelo botão ❤️ Séries do hub raiz quanto pelo botão 📚 Séries do
    Perfil (2026-09-03, pedido do usuário: "pode por as series separadas
    dentro de um botão la naquela tela [Perfil]"), pra nunca duplicar essa
    lógica entre os dois pontos de entrada. Manda o editor de slots
    (`_ViewSeriesFavoritas`, texto puro) + o embed de estatísticas
    detalhadas (`_montar_embed_series_favoritas`) juntos, na mesma
    mensagem."""
    await interaction.response.defer(ephemeral=True)
    view = await _ViewSeriesFavoritas.criar(guild_id, autor_id)
    embed = await asyncio.to_thread(_montar_embed_series_favoritas, guild_id, autor_id)
    await interaction.followup.send(view.formatar(), embed=embed, view=view, ephemeral=True)


class _ViewPerfil(ViewPandora):
    """Botões do "📖 Perfil" (2026-09-02, pedido do usuário: "Mover
    Auto-claim, Ranking, Conquistas para dentro do perfil", depois "quero
    q tenha uma lista com meus personagens favoritos... e poe ela e a
    wishlist dentro do perfil") - saíram do hub raiz `/pandora` pra cá,
    mesma lógica de sempre (só "Auto-claim" mudou de verdade: reconstrói
    e edita O PRÓPRIO Perfil depois do toggle, em vez do hub)."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=900)
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
        wishlist_botao = discord.ui.Button(label="Favoritos", emoji="⭐", style=discord.ButtonStyle.secondary, row=1)
        wishlist_botao.callback = self._wishlist
        self.add_item(wishlist_botao)
        series_botao = discord.ui.Button(label="Séries", emoji="📚", style=discord.ButtonStyle.secondary, row=1)
        series_botao.callback = self._series
        self.add_item(series_botao)
        # 🔥 Coleção/Classes saíram do hub raiz, viraram botões aqui
        # (2026-09-04, pedido do usuário: "coloca a coleções e classes q
        # estao dentro do /pandora em perfil") - mesmo espírito do
        # Ranking/Conquistas/Auto-claim/Wishlist, movidos antes.
        colecao_botao = discord.ui.Button(label="Coleção", emoji="📚", style=discord.ButtonStyle.primary, row=1)
        colecao_botao.callback = self._colecao
        self.add_item(colecao_botao)
        bonus_classe_botao = discord.ui.Button(label="Classes", emoji="⚔️", style=discord.ButtonStyle.secondary, row=1)
        bonus_classe_botao.callback = self._bonus_classe
        self.add_item(bonus_classe_botao)

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

    async def _wishlist(self, interaction: discord.Interaction):
        """Abre Favoritos: lista pessoal ilimitada, sem efeito em rolls."""
        if not await self._somente_autor(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        view = await ViewWishlistHub.criar(self.guild_id, interaction.user.id)
        await interaction.followup.send(embed=view.montar_embed(), view=view, ephemeral=True)

    async def _series(self, interaction: discord.Interaction):
        """Séries Favoritas acessível direto do Perfil (2026-09-03, pedido
        do usuário: "pode por as series separadas dentro de um botão la
        naquela tela" - o campo inline do Perfil truncava/perdia dado com
        até 25 séries, ver `_montar_embed_perfil`). Mesmo painel do botão
        ❤️ Séries do hub raiz (`_enviar_series_favoritas`)."""
        if not await self._somente_autor(interaction):
            return
        await _enviar_series_favoritas(interaction, self.guild_id, interaction.user.id)

    async def _colecao(self, interaction: discord.Interaction):
        """Coleção acessível direto do Perfil (2026-09-04, pedido do
        usuário: "coloca a coleções e classes q estao dentro do /pandora
        em perfil") - mesmo painel de sempre, só mudou de onde é aberto.
        Manda uma mensagem NOVA (não edita o Perfil) - mesma visibilidade
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
        # 🔥 `defer()` ANTES do `to_thread` (2026-09-06, achado do usuário:
        # "O botão Coleção dentro de Perfil nao responde") - mesma classe de
        # bug já corrigida várias vezes neste arquivo: `colecao_minha_
        # ordenada` roda ANTES de qualquer resposta à interação e ordena a
        # coleção INTEIRA por CP (documentado acima como caro) - sem defer,
        # estourava o orçamento de 3s do Discord pro 1º ack sempre que a
        # coleção fosse grande, e o clique parecia simplesmente não fazer
        # nada.
        await interaction.response.defer()
        colecao_minha = await asyncio.to_thread(
            ViewColecaoHub.colecao_minha_ordenada, interaction.guild.id, interaction.user.id,
        )
        view = ViewColecaoHub(interaction.guild, interaction.user, colecao_minha_precomputada=colecao_minha)
        await interaction.followup.send(view.formatar(), view=view)

    async def _bonus_classe(self, interaction: discord.Interaction):
        """Classes acessível direto do Perfil (2026-09-04, mesmo pedido
        da Coleção acima) - mesmo painel de sempre, só mudou de onde é
        aberto."""
        if not await self._somente_autor(interaction):
            return
        view = ViewBonusClasseHub(self.guild_id, interaction.user.id)
        embed = await asyncio.to_thread(view.formatar)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def _definir_serie_e_atualizar(view_series, slot, serie, interacao_editar_painel, interacao_responder):
    """Núcleo compartilhado - grava a Série Favorita, atualiza o painel
    "❤️ Séries Favoritas" (mensagem original, editada via `interacao_
    editar_painel` - o Modal ou, na desambiguação, a interação do Modal
    guardada por fora) e responde (ephemeral) na interação de quem
    confirmou de fato (`interacao_responder` - pode ser uma interação
    DIFERENTE da que edita o painel, ver `_ViewEscolherSerieFavorita`)."""
    ok, mensagem = await asyncio.to_thread(series_favoritas.definir, view_series.guild_id, view_series.user_id, slot, serie)
    log.debug(f" [SERIES] series_favoritas.definir -> ok={ok} mensagem={mensagem}")
    if ok:
        await view_series._atualizar()
        await interacao_editar_painel.edit_original_response(content=view_series.formatar(), view=view_series)
    await interacao_responder.followup.send(mensagem, ephemeral=True)


class _ViewEscolherSerieFavorita(ViewPandora):
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
        super().__init__(timeout=900)
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


class _ModalDefinirSerieFavorita(ModalPandora):
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
        log.debug(f" [SERIES] Modal on_submit iniciado - slot={self._slot} user={interaction.user.id}")
        try:
            await interaction.response.defer()
            log.debug(" [SERIES] defer() OK")
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
                    log.debug(f" [SERIES] busca por substring '{texto}' -> {len(candidatas)} candidata(s)")
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
            log.debug(" [SERIES] Modal on_submit concluído.")
        except Exception:
            log.warning(" [SERIES] !!! EXCEÇÃO dentro de on_submit !!!")
            traceback.print_exc()


class _ViewSeriesFavoritas(ViewPandora):
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
        super().__init__(timeout=900)
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
            view.mensagem = await interaction.followup.send(embed=view.montar_embed(), view=view, ephemeral=True)
        return _callback

    async def _callback_slot_select(self, interaction: discord.Interaction):
        slot = int(interaction.data["values"][0])
        item = next(i for i in self._slots if i["slot"] == slot)
        log.debug(f" [SERIES] selecionou o slot {slot} - user={interaction.user.id} self.user_id={self.user_id}")
        try:
            if str(interaction.user.id) != self.user_id:
                log.debug(" [SERIES] bloqueado - painel não é do autor.")
                await interaction.response.send_message("Esse painel não é seu.", ephemeral=True)
                return
            await interaction.response.send_modal(_ModalDefinirSerieFavorita(self, item["slot"], item["serie"]))
            log.debug(" [SERIES] send_modal OK")
        except Exception:
            log.warning(" [SERIES] !!! EXCEÇÃO dentro do clique de slot !!!")
            traceback.print_exc()

    async def _comprar_slot(self, interaction: discord.Interaction):
        log.debug(f" [SERIES] Comprar Slot clicado - user={interaction.user.id} self.user_id={self.user_id}")
        try:
            if str(interaction.user.id) != self.user_id:
                log.debug(" [SERIES] bloqueado - painel não é do autor.")
                await interaction.response.send_message("Esse painel não é seu.", ephemeral=True)
                return
            # 🔥 `defer()` ANTES do `to_thread` (2026-09-02) - `_atualizar`
            # chama `series_favoritas.listar`, documentado como CARO (varre
            # a coleção inteira filtrada por série).
            await interaction.response.defer()
            log.debug(" [SERIES] defer() OK")
            ok, mensagem = await asyncio.to_thread(db.comprar_slot_serie_favorita, self.guild_id, interaction.user.id)
            log.debug(f" [SERIES] comprar_slot_serie_favorita -> ok={ok} mensagem={mensagem}")
            if not ok:
                await interaction.followup.send(mensagem, ephemeral=True)
                return
            await self._atualizar()
            log.debug(" [SERIES] _atualizar concluído, editando resposta original...")
            await interaction.edit_original_response(content=self.formatar(), view=self)
            await interaction.followup.send(mensagem, ephemeral=True)
            log.debug(" [SERIES] Comprar Slot concluído.")
        except Exception:
            log.warning(" [SERIES] !!! EXCEÇÃO dentro de Comprar Slot !!!")
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


class _ModalBuscarPosicaoOuNomeSerie(ModalPandora, title="Buscar personagem"):
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


class _ViewNavegarSerie(ViewPandora):
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
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        self.serie = serie
        self._permitir_nsfw = permitir_nsfw
        self._bloco = bloco
        self._bloco_offset = bloco_offset
        self._idx_local = idx_local
        self._total = total
        self._status = None
        # 🔥 Referência à própria mensagem (2026-09-06, pedido do usuário:
        # "Comprar Tudo/Maximizar Nível/Afinidade... tem como editar a
        # própria mensagem já com as infos atualizadas apos essas ações?")
        # - preenchida por quem envia a mensagem (`_callback_navegar_serie`)
        # logo depois do `followup.send`. "Comprar Tudo" (mensagem de
        # confirmação separada) e "Maximizar Nível/Afinidade" (Modal) usam
        # isso pra reeditar ESTE card depois da ação, sem precisar que o
        # jogador feche e reabra o navegador pra ver dono/CP atualizados.
        self.mensagem = None

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

    async def _atualizar_bloco(self):
        """Rebusca o BLOCO atual do zero (2026-09-06) - `_ir_para` só
        rebusca quando muda de bloco (otimização de navegação simples);
        "Comprar Tudo"/"Maximizar Nível"/"Maximizar Afinidade" mudam várias
        personagens da série de uma vez (não só a exibida no momento), sem
        trocar de bloco nem de posição - precisa forçar a releitura pra o
        card seguinte (`montar_embed`) refletir dono/CP/Nível atualizados."""
        self._bloco = await asyncio.to_thread(
            db.personagens_da_serie_paginada, self.guild_id, self.serie, self._permitir_nsfw, self._bloco_offset, 25,
        )
        self._atualizar_select_options()

    async def _reeditar_apos_acao_em_massa(self):
        """Reflete no card do navegador o resultado de uma ação que mexeu em
        VÁRIAS personagens da série de fora do fluxo normal de navegação
        ("Comprar Tudo"/"Maximizar Nível"/"Maximizar Afinidade") - chamado
        de dentro de OUTRA interação (a confirmação/Modal, não um clique
        neste próprio card), por isso edita `self.mensagem` diretamente em
        vez de `interaction.edit_original_response` (que editaria a mensagem
        ERRADA - a da própria confirmação/Modal)."""
        if self.mensagem is None:
            return
        await self._atualizar_bloco()
        try:
            await self.mensagem.edit(embed=self.montar_embed(), view=self)
        except discord.HTTPException:
            pass

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
        await interaction.response.send_modal(_ModalInvestirEmMassa(self.guild_id, "nivel", saldo, colecao_serie, self))

    async def _abrir_afinidade_serie(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        colecao_serie = await asyncio.to_thread(self._colecao_possuida_da_serie, interaction.user.id)
        if not colecao_serie:
            await interaction.response.send_message(f'Você não possui nenhuma personagem de "{self.serie}" ainda.', ephemeral=True)
            return
        saldo = await asyncio.to_thread(db.saldo_soulstone, self.guild_id, interaction.user.id)
        await interaction.response.send_modal(_ModalInvestirEmMassa(self.guild_id, "afinidade", saldo, colecao_serie, self))

    async def _comprar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        personagem = self.personagem
        await interaction.response.defer()
        # 🔥 `gacha.comprar_com_revelacao` em vez de `db.comprar_personagem`
        # direto (2026-09-03, pedido do usuário: "esses botoes tem q
        # fazer exatamente o claim, definir clsse e tudo").
        ok, mensagem, tem_classe = await gacha.comprar_com_revelacao(self.guild_id, personagem["id"], interaction.user)
        if ok:
            # 🔥 Atualiza o `dono_id` LOCAL (2026-09-03) - sem isso o card
            # continuaria mostrando "🛒 Disponível" até reabrir o
            # navegador, já que o bloco carregado não é rebuscado depois
            # de comprar (só o `db` de verdade muda).
            personagem["dono_id"] = str(interaction.user.id)
            mensagem += _sufixo_aviso_sem_classe(tem_classe)
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
            f"{len(livres)} personagem(ns) livre(s) - total: **{_fmt_numero(preco_total)} WiShards**\n"
            f"Seu saldo: {_fmt_numero(saldo)} WiShards{aviso_saldo}"
        )
        view_confirmar = _ViewConfirmarComprarTudo(self.guild_id, self.autor_id, self.serie, livres, self)
        await interaction.followup.send(texto, view=view_confirmar, ephemeral=True)

    async def _favoritar(self, interaction: discord.Interaction):
        """Favoritar/Wishlist (2026-09-03) - não exige mais posse (fusão
        com a Wishlist antiga, `db.wishlist_adicionar` nunca checou posse
        de verdade, só as views/comandos antigos checavam) - favoritar uma
        personagem alheia ou ainda livre vira "colocar na lista de
        desejos". Nome do método/rótulo mantido "favoritar" (não
        "wishlist") de propósito - é o atalho "com emote e botão fácil"
        que o usuário pediu pra preservar."""
        if not await self._somente_autor(interaction):
            return
        personagem = self.personagem
        if db.esta_na_wishlist(self.guild_id, self.autor_id, personagem["id"]):
            db.wishlist_remover(self.guild_id, self.autor_id, personagem["id"])
            self._status = f"Desmarcada como favorita: **{personagem['nome']}**."
        else:
            ok, mensagem = db.wishlist_adicionar(self.guild_id, self.autor_id, personagem["id"])
            self._status = f"{'⭐' if ok else '⚠️'} {mensagem}"
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
        # 🔥 Favoritar/Wishlist SEMPRE habilitado, não importa quem é dono
        # (2026-09-03, fusão Favoritos+Wishlist - "favoritar" virou também
        # "colocar na lista de desejos" pra personagem que você não possui
        # ainda, mesma regra que a Wishlist antiga já tinha: `db.favoritar`
        # não exige posse, só o wish-roll (`wishlist_disponiveis_no_guild`)
        # ignora quem já tem dono na hora de sortear).
        favorita = db.esta_na_wishlist(self.guild_id, self.autor_id, personagem["id"])
        self._botao_favoritar.disabled = False
        self._botao_favoritar.label = "Desfavoritar" if favorita else "Favoritar"
        self._botao_favoritar.style = discord.ButtonStyle.success if favorita else discord.ButtonStyle.secondary
        if dono_id is None:
            preco = db.PRECOS_LOJA[personagem["raridade"]]
            embed.add_field(name="Status", value=f"🛒 Disponível - {_fmt_numero(preco)} WiShards", inline=True)
            self._botao_comprar.disabled = False
            self._botao_comprar.label = f"Comprar ({_fmt_numero(preco)})"
        elif dono_id == self.autor_id:
            power, _nivel, categoria = torre.power_personagem(personagem, self.guild_id, self.autor_id)
            embed.add_field(name="Status", value="✅ Já é sua", inline=True)
            embed.add_field(name="CP", value=f"{torre.icone_categoria(categoria)} {_fmt_numero(power)}", inline=True)
            self._botao_comprar.disabled = True
            self._botao_comprar.label = "Já é sua"
        else:
            embed.add_field(name="Status", value=f"🔒 Possuída por <@{dono_id}>", inline=True)
            self._botao_comprar.disabled = True
            self._botao_comprar.label = "Indisponível"
        if self._status:
            embed.description = self._status
        return embed
