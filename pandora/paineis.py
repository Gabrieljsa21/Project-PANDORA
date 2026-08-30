# -*- coding: utf-8 -*-
"""Painel-raiz `/waifu` do Colecionador (2026-08-29, pedido do usuário: "os
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
`/waifu` é aditivo, não remove nada ainda."""
import asyncio

import discord

from pandora import db
from pandora import cidade, consulta, economia, gacha, torre

_COR_HUB = discord.Color(0xF1C40F)

_MODOS_COLECAO = [
    ("minha", "📚 Minha coleção"),
    ("populares", "🔥 Populares do catálogo"),
    ("disponiveis", "🎯 Disponíveis pra pegar"),
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
    embed = discord.Embed(title=f"🎴 Waifu - {membro.display_name}", color=_COR_HUB)
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
    embed.set_footer(text="Escolha uma opção abaixo")
    return embed


class ViewHubWaifu(discord.ui.View):
    """Painel-raiz de `/waifu` - restrito a quem abriu (`autor_id`), mesmo
    espírito de um menu pessoal (o LA também trata painéis de coleção como
    algo individual). `timeout=300` - tempo de sobra pra navegar sem
    precisar reabrir `/waifu` de novo."""

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
        wishlist = discord.ui.Button(label="Wishlist", emoji="⭐", style=discord.ButtonStyle.secondary, row=0)
        wishlist.callback = self._wishlist
        self.add_item(wishlist)
        party = discord.ui.Button(label="Party", emoji="👥", style=discord.ButtonStyle.secondary, row=0)
        party.callback = self._party
        self.add_item(party)
        loja = discord.ui.Button(label="Loja", emoji="🛒", style=discord.ButtonStyle.secondary, row=1)
        loja.callback = self._loja
        self.add_item(loja)
        trocar = discord.ui.Button(label="Trocar", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
        trocar.callback = self._trocar
        self.add_item(trocar)
        ranking = discord.ui.Button(label="Ranking", emoji="🏆", style=discord.ButtonStyle.secondary, row=1)
        ranking.callback = self._ranking
        self.add_item(ranking)
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
        ativo = db.auto_colecionar_ativo(self.guild_id, self.autor_id)
        auto_coleta = discord.ui.Button(
            label=f"Auto-coleta: {'LIGADA' if ativo else 'DESLIGADA'}", emoji="🤖",
            style=discord.ButtonStyle.success if ativo else discord.ButtonStyle.secondary, row=2,
        )
        auto_coleta.callback = self._toggle_auto_coleta
        self.add_item(auto_coleta)
        cidade_botao = discord.ui.Button(label="Cidade", emoji="🏙️", style=discord.ButtonStyle.secondary, row=2)
        cidade_botao.callback = self._cidade
        self.add_item(cidade_botao)

    async def _somente_autor(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.autor_id:
            await interaction.response.send_message("Esse painel não é seu - use `/waifu` pra abrir o seu.", ephemeral=True)
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

    async def _wishlist(self, interaction: discord.Interaction):
        """Mesma visibilidade ephemeral que `/wishlist listar` já tem hoje -
        é lista pessoal, nunca foi pública."""
        if not await self._somente_autor(interaction):
            return
        view = ViewWishlistHub(self.guild_id, interaction.user.id)
        await interaction.response.send_message(view.formatar(), view=view, ephemeral=True)

    async def _party(self, interaction: discord.Interaction):
        """`/party` deixa de existir como comando (nem `/waifu party`) -
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

    async def _ranking(self, interaction: discord.Interaction):
        """25 em vez dos 10 de sempre (2026-08-29) - sem paginação de
        verdade ainda (o formato de `consulta.formatar_ranking` é
        membro+contagem, não personagem - não dá pra reaproveitar
        `ViewColecao` direto); 25 já cobre qualquer servidor pessoal real
        até aqui, sem precisar construir um pager novo só pra isso."""
        if not await self._somente_autor(interaction):
            return
        ranking = db.ranking_guild(self.guild_id, limite=25)
        await interaction.response.send_message(consulta.formatar_ranking(interaction.guild, ranking))

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
        de Coleção/Perfil/Party). Coleção ordenada por CP ANTES de abrir a
        busca - o fallback de campo vazio (`consulta.buscar_por_nome`)
        mostra as de maior CP primeiro."""
        if not await self._somente_autor(interaction):
            return
        colecao = db.colecao_do_usuario(self.guild_id, interaction.user.id)
        if not colecao:
            await interaction.response.send_message("Você ainda não tem nenhuma personagem.", ephemeral=True)
            return
        # 🔥 `asyncio.to_thread` (2026-08-30, achado do usuário: "Auto-party
        # esta demorando e as vezes cai em GAIA não respondeu a tempo. O
        # Cidade e Personagem cai com frequencia nesse erro tbm") - `db.
        # conexao()` é SQLite síncrono, então varrer a coleção INTEIRA
        # (`ordenar_por_power`) bloqueia o event loop inteiro do processo -
        # não só ESTA interação, QUALQUER OUTRA (de qualquer usuário) que
        # chegue durante os ~1s do scan também perde o prazo de 3s do
        # Discord, mesmo sendo leve. Rodar num thread separado libera o
        # loop pro resto do bot continuar respondendo enquanto isso roda.
        colecao = await asyncio.to_thread(torre.ordenar_por_power, colecao, self.guild_id, interaction.user.id)
        contexto_lote = await asyncio.to_thread(torre._contexto_lote, self.guild_id, interaction.user.id)
        modal = _ModalBuscarPersonagem(
            "Buscar personagem", colecao, "Escolha quem ver...", self._ver_selecionado, editar_mensagem_original=False,
            descricao=lambda p: _descricao_personagem_dropdown(p, self.guild_id, interaction.user.id, contexto_lote),
        )
        await interaction.response.send_modal(modal)

    async def _ver_selecionado(self, interaction: discord.Interaction, personagens, candidatos):
        """`candidatos` (2026-08-30, pedido do usuário: "quero q o dropdown
        de selecionar personagem nao suma ao escolher um") - repassado pro
        card (`_ViewNivel`), que passa a ter seu PRÓPRIO select "Trocar de
        personagem" - o dropdown de busca não precisa mais ser reaberto
        pra ver outra personagem da mesma busca."""
        view = _ViewNivel(self.guild_id, self.autor_id, personagens[0], candidatos=candidatos)
        await interaction.response.edit_message(content=None, embed=view.montar_embed(), view=view)

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
        ids = [p["id"] for p in personagens]
        ok, mensagem, precisa_confirmar = economia.executar_merge(self.guild_id, interaction.user.id, ids, confirmar)
        if precisa_confirmar:
            async def _confirmar(interacao_confirmacao):
                await self._merge_selecionado(interacao_confirmacao, personagens, confirmar=True)
            view = _ViewConfirmar(_confirmar)
            await interaction.response.edit_message(content=f"{mensagem} Confirma o Merge mesmo assim?", view=view)
            return
        await interaction.response.edit_message(content=mensagem, view=None)

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

    async def _toggle_auto_coleta(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        novo_estado = not db.auto_colecionar_ativo(self.guild_id, self.autor_id)
        db.definir_auto_colecionar(self.guild_id, self.autor_id, novo_estado)
        embed = montar_embed_hub(interaction.guild, interaction.user)
        view = ViewHubWaifu(self.guild_id, self.autor_id)
        await interaction.response.edit_message(embed=embed, view=view)

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
    niveis, bonus_global, cache_classe = contexto_lote or (None, None, None)
    nivel = niveis.get(personagem["id"], 1) if niveis is not None else None
    power, nivel_resolvido, categoria = torre.power_personagem(
        personagem, guild_id, user_id, nivel=nivel, bonus_global=bonus_global, cache_bonus_classe=cache_classe,
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
    primeiros 25 da ordem de quem chama)."""

    nome = discord.ui.TextInput(label="Nome (pode ser parcial/aproximado)", required=False, max_length=100)

    def __init__(self, titulo, colecao, placeholder_select, ao_selecionar, descricao=None, editar_mensagem_original=True):
        """`editar_mensagem_original` (default True) - EDITA a mensagem do
        botão que abriu o modal (fluxos de painel de 1 mensagem só); `False`
        manda uma mensagem NOVA em vez disso (fluxos como "🔍 Personagem" do
        hub, que sempre abrem conversa nova, nunca editam o hub - mesmo
        padrão de Coleção/Party)."""
        super().__init__(title=titulo[:45])
        self._colecao = colecao
        self._placeholder_select = placeholder_select
        self._ao_selecionar = ao_selecionar
        self._descricao = descricao
        self._editar_mensagem_original = editar_mensagem_original

    async def on_submit(self, interaction: discord.Interaction):
        candidatos = consulta.buscar_por_nome(self._colecao, str(self.nome))
        if not candidatos:
            await interaction.response.send_message(
                f"Nenhuma personagem parecida com \"{self.nome}\" na sua coleção.", ephemeral=True,
            )
            return

        # 🔥 repassa `candidatos` (o pool INTEIRO da busca, não só quem foi
        # escolhido) pro `ao_selecionar` de quem chamou (2026-08-30, pedido
        # do usuário: "quero q o dropdown de selecionar personagem nao suma
        # ao escolher um" - "🔍 Personagem", único uso deste Modal hoje)
        # - `_ViewSelecionarPersonagem` continua com seu contrato de 2
        # argumentos de sempre (Merge/Party/Prova não mudam nada).
        async def _selecionar_com_pool(interacao_selecao, personagens):
            await self._ao_selecionar(interacao_selecao, personagens, candidatos)

        view = _ViewSelecionarPersonagem(candidatos, self._placeholder_select, _selecionar_com_pool, descricao=self._descricao)
        if self._editar_mensagem_original:
            # 🔥 `edit_message` funciona aqui porque o modal foi aberto a
            # partir de um CLIQUE DE BOTÃO (`interaction.response.send_
            # modal`) - o submit do modal carrega a mensagem original
            # desse botão, então dá pra editar ela em vez de abrir uma
            # conversa nova (mesmo padrão de mensagem única de sempre).
            await interaction.response.edit_message(content="Selecione:", view=view)
        else:
            await interaction.response.send_message(content="Selecione:", view=view)


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

    🔥 `candidatos` opcional (2026-08-30, pedido do usuário: "quero q o
    dropdown de selecionar personagem nao suma ao escolher um") - o pool
    INTEIRO da busca que trouxe até aqui (`_ver_selecionado`). Se tiver
    mais de 1, ganha um select "🔄 Trocar de personagem" (linha própria,
    descrição PADRÃO de `_descricao_personagem_dropdown` - ícone/CP/Nível/
    Afinidade, mesmo pedido do usuário: "no dropdwon de ver personagem tem
    q informar o icone da classe, CP, lv e afinidade") que troca
    `self.personagem` SEM reabrir o Modal de busca - o card e os botões
    continuam os mesmos, só o conteúdo muda. Ganha também "◀️"/"▶️"
    (2026-08-30, pedido do usuário: "quando estou na tela de personagem,
    quero q tenha as setas p direita e esquerda p trocar entre eles
    rapido, sem precisar passar pelo dropdwon") - navegam pelo MESMO
    `_candidatos`, desabilitando na ponta (sem voltar ao início, mesmo
    padrão de `consulta.ViewColecao`)."""

    def __init__(self, guild_id, autor_id, personagem, candidatos=None):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.autor_id = autor_id
        self.personagem = personagem
        self._status = None
        self._candidatos = candidatos or []
        self._indice_atual = next(
            (i for i, p in enumerate(self._candidatos) if p["id"] == personagem["id"]), 0,
        )
        self._botao_anterior = None
        self._botao_proximo = None
        if len(self._candidatos) > 1:
            contexto_lote = torre._contexto_lote(self.guild_id, self.autor_id)
            options = []
            for indice, p in enumerate(self._candidatos):
                texto, emoji = _descricao_personagem_dropdown(p, self.guild_id, self.autor_id, contexto_lote)
                options.append(discord.SelectOption(label=p["nome"][:100], description=texto[:100], value=str(indice), emoji=emoji))
            select = discord.ui.Select(placeholder="🔄 Trocar de personagem...", options=options, row=1)
            select.callback = self._trocar_personagem
            self.add_item(select)
            self._botao_anterior = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary, row=2)
            self._botao_anterior.callback = self._navegar_anterior
            self.add_item(self._botao_anterior)
            self._botao_proximo = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary, row=2)
            self._botao_proximo.callback = self._navegar_proximo
            self.add_item(self._botao_proximo)

    async def _trocar_personagem(self, interaction: discord.Interaction):
        self._indice_atual = int(interaction.data["values"][0])
        self.personagem = self._candidatos[self._indice_atual]
        self._status = None
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    async def _navegar_anterior(self, interaction: discord.Interaction):
        await self._navegar(interaction, -1)

    async def _navegar_proximo(self, interaction: discord.Interaction):
        await self._navegar(interaction, 1)

    async def _navegar(self, interaction: discord.Interaction, delta):
        self._indice_atual = max(0, min(len(self._candidatos) - 1, self._indice_atual + delta))
        self.personagem = self._candidatos[self._indice_atual]
        self._status = None
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    def montar_embed(self):
        if self._botao_anterior is not None:
            self._botao_anterior.disabled = self._indice_atual <= 0
            self._botao_proximo.disabled = self._indice_atual >= len(self._candidatos) - 1
        nivel_atual = db.nivel_personagem(self.guild_id, self.autor_id, self.personagem["id"])
        custo = db.custo_proximo_nivel(self.personagem["raridade"], nivel_atual)
        embed = consulta.embed_carta_personagem(self.personagem)
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

    async def _divorciar_de_verdade(self, interaction: discord.Interaction):
        ok, recompensa, xp = db.divorciar(self.guild_id, self.personagem["id"], interaction.user.id)
        if ok:
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
    if not resultado["por_funcao"]:
        embed.add_field(
            name="Trabalhadores", value="Nenhuma personagem fora da Party com classe revelada ainda.", inline=False,
        )
        return embed
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
    for funcao in cidade.FUNCOES_CIDADE:
        dados = resultado["por_funcao"].get(funcao)
        if not dados:
            continue
        taxa_atual = resultado["taxas_por_funcao"][funcao]
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
    if not contexto["restricao_ok"]:
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
        _ok, _erro, contexto = torre.preview_andar(self.guild_id, interaction.user.id)
        embed = _embed_torre(contexto)
        await interaction.edit_original_response(embed=embed, view=self)


class ViewColecaoHub(consulta.ViewColecao):
    """Estende `ViewColecao` (paginação ◀️/▶️ já pronta) com um SELECT de
    modo (painel `/waifu`) - troca a fonte de dado sem sair da mesma
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
            remover = discord.ui.Select(
                placeholder="Remover da wishlist...",
                options=[discord.SelectOption(label=p["nome"][:100], value=str(p["id"])) for p in pagina_atual],
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
        id_personagem = int(interaction.data["values"][0])
        db.wishlist_remover(self.guild_id, self.autor_id, id_personagem)
        self._recarregar()
        self._montar()
        await interaction.response.edit_message(content=self.formatar(), view=self)


class _ModalAdicionarWishlist(discord.ui.Modal, title="Adicionar à wishlist"):
    nome = discord.ui.TextInput(label="Nome do personagem", placeholder="Ex.: Megumin", max_length=100)

    def __init__(self, view_wishlist):
        super().__init__()
        self._view_wishlist = view_wishlist

    async def on_submit(self, interaction: discord.Interaction):
        resultados = db.buscar_personagens(str(self.nome))
        if not resultados:
            await interaction.response.send_message(f'Nenhum personagem encontrado pra "{self.nome}".', ephemeral=True)
            return
        if len(resultados) > 1:
            linhas = "\n".join(f"`#{p['id']}` {p['nome']}" for p in resultados[:10])
            await interaction.response.send_message(
                f'Mais de um resultado pra "{self.nome}" - use `/wishlist adicionar` com o #id certo:\n{linhas}', ephemeral=True,
            )
            return
        personagem = resultados[0]
        db.wishlist_adicionar(self._view_wishlist.guild_id, interaction.user.id, personagem["id"])
        self._view_wishlist._recarregar()
        self._view_wishlist._montar()
        await interaction.response.edit_message(content=self._view_wishlist.formatar(), view=self._view_wishlist)


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
    """Painel de Party (2026-08-29) - SEM `/party` nem `/waifu party`, só
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
            filtrados = candidatos if categoria is None else [
                p for p in candidatos if torre.categoria_personagem(p) == categoria
            ]
            # 🔥 ordena por CP ANTES de cortar em 25 (2026-08-30, pedido do
            # usuário: "Todo dropdwon q listar waifu, sempre ordene pelas
            # com maior CP/popularidade") - via thread (2026-08-30,
            # achado do usuário: "GAIA não respondeu a tempo" repetido,
            # mesma causa das outras varreduras de coleção inteira).
            filtrados = (await asyncio.to_thread(torre.ordenar_por_power, filtrados, self.guild_id, self.autor_id))[:25]
            if not filtrados:
                await interaction_filtro.response.send_message(
                    f"Você não tem nenhuma personagem fora da Party na role {categoria}.", ephemeral=True,
                )
                return
            contexto_lote = await asyncio.to_thread(torre._contexto_lote, self.guild_id, self.autor_id)
            view = _ViewSelecionarPersonagem(
                filtrados, f"Escolha até {min(vagas, len(filtrados))} personagem(ns)...", self._adicionar_selecionados,
                min_values=1, max_values=min(vagas, len(filtrados)),
                descricao=lambda p: _descricao_personagem_dropdown(p, self.guild_id, self.autor_id, contexto_lote),
            )
            await interaction_filtro.response.edit_message(content="Selecione:", view=view)

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
        equipe = db.obter_equipe(self.guild_id, interaction.user.id, "party")
        vagas_livres = (posicao for posicao in range(1, db.MAX_POSICOES_EQUIPE + 1) if posicao not in equipe)
        for personagem in personagens:
            posicao = next(vagas_livres, None)
            if posicao is None:
                break
            db.definir_posicao_equipe(self.guild_id, interaction.user.id, "party", posicao, personagem["id"])
        self._montar()
        await interaction.response.edit_message(content=self.formatar(), view=self)

    async def _abrir_remover(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        equipe = db.obter_equipe(self.guild_id, self.autor_id, "party")
        if not equipe:
            await interaction.response.send_message("Sua Party está vazia.", ephemeral=True)
            return
        membros = torre.ordenar_por_power(list(equipe.values()), self.guild_id, self.autor_id)
        contexto_lote = torre._contexto_lote(self.guild_id, self.autor_id)
        view = _ViewSelecionarPersonagem(
            membros, "Escolha quem remover da Party...", self._remover_selecionados, min_values=1, max_values=len(membros),
            descricao=lambda p: _descricao_personagem_dropdown(p, self.guild_id, self.autor_id, contexto_lote),
        )
        await interaction.response.edit_message(content="Selecione:", view=view)

    async def _remover_selecionados(self, interaction: discord.Interaction, personagens):
        equipe = db.obter_equipe(self.guild_id, interaction.user.id, "party")
        posicao_por_personagem_id = {p["id"]: posicao for posicao, p in equipe.items()}
        for personagem in personagens:
            posicao = posicao_por_personagem_id.get(personagem["id"])
            if posicao is not None:
                db.remover_posicao_equipe(self.guild_id, interaction.user.id, "party", posicao)
        self._montar()
        await interaction.response.edit_message(content=self.formatar(), view=self)

    async def _limpar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        db.limpar_equipe(self.guild_id, self.autor_id, "party")
        self._montar()
        await interaction.response.edit_message(content=self.formatar(), view=self)

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
            await self._mostrar_personagens(interaction, raridade)

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

    async def _mostrar_personagens(self, interaction: discord.Interaction, raridade):
        permitir_nsfw = db.obter_configuracao_colecao(self._view_loja.guild_id)["nsfw_permitido"]
        personagens = db.personagens_livres_por_raridade(self._view_loja.guild_id, raridade, permitir_nsfw, limite=25)
        if not personagens:
            await interaction.response.edit_message(content=economia.formatar_loja(raridade, personagens), view=None)
            return
        view = _ViewComprarPersonagem(self._view_loja, raridade, personagens)
        await interaction.response.edit_message(content=economia.formatar_loja(raridade, personagens), view=view)


class _ViewComprarPersonagem(discord.ui.View):
    """Select final de "Comprar" - até 25 personagens livres dessa
    raridade (mesmo teto do Discord), `db.comprar_personagem` decide tudo
    (preço, corrida por quem paga primeiro, reembolso se perder)."""

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
        ok, mensagem = db.comprar_personagem(self._view_loja.guild_id, interaction.user.id, personagem["id"])
        await interaction.response.edit_message(content=mensagem, view=None)


def _int_seguro(texto):
    texto = (texto or "").strip()
    return int(texto) if texto.lstrip("-").isdigit() else 0


class _ViewEscolherAlvoTroca(discord.ui.View):
    """Passo 1 de "🔄 Trocar" - escolher o outro jogador via
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
    """Passo 2 (oferece) e 3 (pede) de "🔄 Trocar" (2026-08-29, pedido do
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
        # etapa == "pede" -> só falta os 2 números de WiShards, via Modal (nome/ID de personagem NUNCA se digita nesse fluxo)
        await interaction.response.send_modal(
            _ModalWishardsTroca(self.guild_id, self.proponente_id, self.alvo, self._oferece_ids, ids_escolhidos),
        )

    async def _selecionou(self, interaction: discord.Interaction):
        valores = [v for v in interaction.data["values"] if v != "-1"]
        ids = [self._colecao[int(indice)]["id"] for indice in valores]
        await self._avancar(interaction, ids)

    async def _pular(self, interaction: discord.Interaction):
        await self._avancar(interaction, [])


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
