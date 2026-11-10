# -*- coding: utf-8 -*-
"""Cidade (hub, áreas, Progressão, Upar Construção) e Torre.

Parte de `pandora.paineis` (dividido por tela em 2026-11-10); de fora do
pacote, continuar usando `from pandora import paineis` e `paineis.<nome>`."""
import asyncio
import discord
from pandora import db
from pandora import cidade, series_favoritas, torre
from pandora.ui_base import ViewPandora
from pandora.paineis.comum import (
    _COR_HUB,
    _fmt_numero,
)
from pandora.paineis.personagem import (
    _TEXTO_BONUS_POR_FUNCAO,
    _fluxo_progressao_cidade,
    _pips_construcao,
    _texto_detalhe_calculo,
    _texto_valor_curto,
)
from pandora.paineis.equipe import (
    _fluxo_upar_construcao_direto,
    _fluxo_usar_upgrade_construcao,
)


def _fluxo_detalhe_area_cidade(guild_id, autor_id, funcao):
    """Callback do botão de detalhe de UMA área da Cidade (2026-09-06,
    mockup do usuário) - resposta EPHEMERAL (só quem clicou vê), o card
    principal continua aberto e intocado por trás."""
    async def callback(interaction: discord.Interaction):
        if str(interaction.user.id) != autor_id:
            await interaction.response.send_message("Esse painel não é seu.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        embed = await asyncio.to_thread(_embed_cidade_area_detalhe, funcao, guild_id, interaction.user.id)
        await interaction.followup.send(embed=embed, ephemeral=True)
    return callback


class ViewCidadeHub(ViewPandora):
    """Painel "🏙️ Cidade" (2026-09-06, pedido do usuário: "Coloca a opção
    comprar e usar Upgrade de Construção no painel da cidade") - o Nível de
    Construção de cada área já aparece neste card (`Lv{nivel}` no título de
    cada campo, ver `_embed_cidade`), então comprar/usar o upgrade que sobe
    esse número direto daqui evita o ricochete Loja (comprar) -> 🎒
    Inventário (usar) só pra mexer num dado que este painel já mostra.

    🔥 "Comprar" virou "Upar Construção" (2026-09-07, pedido do usuário:
    "Vamos tirar esse item da loja e permitir o jogador upar diretamente a
    construção") - o item "🏗️ Upgrade de Construção" SAIU da Loja (não é
    mais comprável com WiShards), então `_fluxo_comprar_item_view` não
    serve mais aqui; `_fluxo_upar_construcao_direto` (novo) paga WiShards
    direto, sem item no meio. "Usar Upgrade de Construção" continua igual
    - o item ainda existe como drop do World Boss/prêmio da Diária,
    consumido de graça por quem o tiver.

    🔥 Botão "Usar Upgrade de Construção" só aparece com item guardado
    (2026-09-07, pedido do usuário: "Podia informar quantos upgrades de
    construção tenho. E se nao tiver nenhum ja avisar de inicio, ou
    sequer aparecer o botão de usar eles" - mesmo padrão já usado em
    `ViewInventarioHub`, reaproveitado aqui) - a quantidade guardada
    aparece no próprio rótulo do botão (`(x3)`), sem precisar clicar em
    nada pra saber quanto tem."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        upar = discord.ui.Button(label="Upar Construção", emoji="💰", style=discord.ButtonStyle.success, row=0)
        upar.callback = _fluxo_upar_construcao_direto(guild_id, self.autor_id)
        self.add_item(upar)
        disponivel = db.quantidade_item(guild_id, self.autor_id, "upgrade_construcao")
        if disponivel > 0:
            usar = discord.ui.Button(label=f"Usar Upgrade de Construção (x{disponivel})", emoji="🏗️", style=discord.ButtonStyle.primary, row=0)
            usar.callback = _fluxo_usar_upgrade_construcao(guild_id, self.autor_id)
            self.add_item(usar)
        # 🔥 "📈 Progressão" (2026-09-07, pedido do usuário: "traz um botao
        # de progressao, mostrando as fontes de xp acumaladas ate entao"),
        # ANTES de "Atualizar" na 1ª fileira (2026-09-07, pedido do
        # usuário: "Coloca o progressao antes do botao atualizar, na
        # primeira fileira") - ordem de inserção decide a posição visual
        # dentro da fileira, então precisa vir ANTES do `add_item` do
        # Atualizar, não depois.
        progressao = discord.ui.Button(label="Progressão", emoji="📈", style=discord.ButtonStyle.secondary, row=0)
        progressao.callback = _fluxo_progressao_cidade(guild_id, self.autor_id)
        self.add_item(progressao)
        # 🔥 "Atualizar" ADICIONADO MANUALMENTE, não mais via decorator
        # `@discord.ui.button` (2026-09-07, pedido do usuário: "mova o
        # Atualizar para o fim da primeira fileira") - botões via decorator
        # são inseridos ANTES dos que `__init__` adiciona na mão (mesmo
        # `row`), então como decorator "Atualizar" sempre vinha PRIMEIRO na
        # fileira 0, nunca por último; adicionando aqui, por último, ele
        # fica na ordem visual certa (fim da fileira).
        atualizar = discord.ui.Button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.secondary, row=0)
        atualizar.callback = self._callback_atualizar
        self.add_item(atualizar)
        # 🔥 1 botão por área (2026-09-06, mockup do usuário: "criar botoes
        # p cada area") - abre a tela de detalhe (`_embed_cidade_area_
        # detalhe`) só pra quem clicou (ephemeral), sem sair/poluir o card
        # principal. 3 por linha (rows 2/3) - Discord permite até 5 por
        # linha, mas 3 combina melhor com o texto do rótulo (nome da área).
        for indice, funcao in enumerate(cidade.FUNCOES_CIDADE):
            botao_area = discord.ui.Button(
                label=funcao, emoji=cidade.icone_funcao(funcao),
                style=discord.ButtonStyle.secondary, row=2 + indice // 3,
            )
            botao_area.callback = _fluxo_detalhe_area_cidade(guild_id, self.autor_id, funcao)
            self.add_item(botao_area)

    async def _callback_atualizar(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.autor_id:
            await interaction.response.send_message("Esse painel não é seu.", ephemeral=True)
            return
        await interaction.response.defer()
        resultado = await asyncio.to_thread(cidade.coletar_producao_pendente, self.guild_id, interaction.user.id)
        embed = await asyncio.to_thread(_embed_cidade, resultado, self.guild_id, interaction.user.id)
        # 🔥 View NOVA, não `self` (2026-09-07) - o botão "Usar Upgrade de
        # Construção" (aparece/some + a quantidade no rótulo) é decidido só
        # na hora de CONSTRUIR o View; reaproveitar `self` deixaria o botão
        # desatualizado se a quantidade de itens mudou (drop novo, usado
        # pelo 🎒 Inventário) enquanto o painel estava aberto.
        nova_view = ViewCidadeHub(self.guild_id, interaction.user.id)
        await interaction.edit_original_response(embed=embed, view=nova_view)


def _embed_cidade(resultado, guild_id, user_id):
    """Status da Cidade v2 (2026-08-30, efeitos diferenciados por área) -
    `resultado` vem de `cidade.coletar_producao_pendente`. Mostra a
    CAPACIDADE ATUAL de cada área (`taxas_por_funcao` - independente de
    quanto tempo passou desde a última visita, pedido do usuário: "o
    painel deve mostrar sempre o bônus atual por hora, independentemente
    de quanto tempo passou desde a última coleta") - só o resumo do topo
    mostra o ACUMULADO desde a última visita.

    🔥 `guild_id`/`user_id` (2026-09-03, pedido do usuário: "informa na
    cidade o lv dessas construcoes") - o Nível de Construção de cada
    área (item "Upgrade de Construção", `db.nivel_construcao`/`teto_
    atual_construcao`) só aparecia no painel "🎒 Inventário" antes; agora
    também no card de cada área aqui, junto do resto do bônus dela."""
    embed = discord.Embed(title="🏙️ Cidade", color=_COR_HUB)
    if resultado["primeira_visita"]:
        embed.description = (
            "Primeira vez aqui - o relógio de produção começou a contar agora. "
            "Volte depois pra coletar o que suas personagens fora da Party produziram."
        )
        return embed
    # 🔥 Soulstone antes de XP (2026-09-06, pedido do usuário - troca pura
    # de ordem de exibição, os 3 valores continuam sendo os mesmos).
    embed.description = (
        f"Desde sua última visita ({resultado['horas']}h atrás):\n"
        f"+{_fmt_numero(resultado['wishards'])} WiShards\n"
        f"+{_fmt_numero(resultado['soulstone'])} Soulstone\n"
        f"+{_fmt_numero(resultado['xp'])} XP de Progressão"
    )
    embed.add_field(
        name="👑 Bônus da Coleção",
        value=(
            f"Personagens na coleção: {_fmt_numero(resultado['total_personagens'])}\n"
            f"CP da coleção: {_fmt_numero(resultado['cp_total'])}\n"
            f"Bônus: +{_fmt_numero(resultado['bonus_colecao_loot_percentual'] * 100)}% de loot\n"
            "Afeta recompensas da Torre, World Boss e claims"
        ),
        inline=False,
    )
    # 🔥 SEMPRE lista as 6 áreas, mesmo sem NENHUM trabalhador ainda
    # (2026-09-01, pedido do usuário: "um local que detalhe todos os
    # bônus ativos e alvos") - antes pulava área vazia (`if not dados:
    # continue`), então o jogador só via o que JÁ tinha, sem saber o que
    # cada área faz antes de mandar a 1ª personagem pra lá.
    for funcao in cidade.FUNCOES_CIDADE:
        dados = resultado["por_funcao"].get(funcao) or {"qtd": 0, "cp": 0.0}
        taxa_atual = resultado["taxas_por_funcao"].get(funcao, 0.0)
        texto_bonus = _TEXTO_BONUS_POR_FUNCAO[funcao](taxa_atual)
        # 🔥 "Lv{nivel}" no TÍTULO do campo, sem campo/linha própria pra
        # Construção (2026-09-03, pedido do usuário: "n precisar colocar
        # o campo construcao, é so por lv X na frente, Ex: ⚔️ Militar -
        # Lv10").
        nivel_construcao = cidade.nivel_efetivo_construcao(guild_id, user_id, funcao)
        embed.add_field(
            name=f"{cidade.icone_funcao(funcao)} {funcao} - Lv{nivel_construcao}",
            value=(
                f"{_pips_construcao(nivel_construcao)}\n"
                f"Personagens: {dados['qtd']}\nBônus: {texto_bonus}"
            ),
            inline=True,
        )
    embed.set_footer(text="Veja os botões abaixo para o detalhe de cada área")
    return embed


def _embed_cidade_area_detalhe(funcao, guild_id, user_id):
    """Tela de detalhe de UMA área da Cidade - layout batendo com a seção
    "Exibição sugerida no Discord" de `PANDORA_marcos_cidade.md`
    (especificação do usuário, 2026-09-07): "Trabalhando aqui" / "Bônus
    atual" / "Marcos" (concluídos + valor de CADA marco) / "Próximo
    marco" (X/Y + faltam quantos) / "📊 Detalhes" (a conta por extenso:
    "580 marcos × 10 CP base × Lv10 = +58K CP"). O documento pede
    EXPLICITAMENTE pra NÃO listar marcos individualmente ("Regras
    finais") - a versão anterior desta tela (tabela ✅/🔒 de 50 a 10.000
    personagens) foi substituída por isso, mais compacto. Não recalibra
    NENHUM valor - só expõe, em outro formato, a mesma fórmula já
    calibrada que `_embed_cidade`/`cidade.coletar_producao_pendente`
    usam."""
    nivel_construcao = cidade.nivel_efetivo_construcao(guild_id, user_id, funcao)
    embed = discord.Embed(
        title=f"{cidade.icone_funcao(funcao)} {funcao} · Lv{nivel_construcao}",
        description=_pips_construcao(nivel_construcao),
        color=_COR_HUB,
    )
    _cp_total_colecao, por_funcao, total_personagens = cidade._workforce_por_funcao(guild_id, user_id)
    dados = por_funcao.get(funcao) or {"qtd": 0, "cp": 0.0}
    quantidade = dados["qtd"]
    embed.add_field(
        name="Trabalhando aqui",
        value=f"{_fmt_numero(quantidade)} personagens",
        inline=False,
    )

    # 🔥 "Bônus atual" usa o valor REAL vigente pra Party/produção (o
    # mesmo que `_embed_cidade` mostra) - já inclui o `(1 + bônus de
    # Administração)` cruzado, quando aplicável (Administração nunca
    # cruza sobre si mesma).
    bonus_por_area = cidade._bonus_todas_areas(guild_id, user_id, por_funcao)
    bonus_atual = bonus_por_area[funcao]
    marcos = cidade.marcos_ativos(quantidade)
    _marco_atual, marco_proximo = cidade.progresso_marco(quantidade)
    faltam = marco_proximo - quantidade
    valor_marco = cidade.bonus_por_marco(funcao, nivel_construcao)
    texto_bonus = _TEXTO_BONUS_POR_FUNCAO[funcao](bonus_atual)

    embed.add_field(name="Bônus atual", value=texto_bonus, inline=False)
    embed.add_field(
        name="Marcos",
        value=f"{marcos} concluído(s)\nCada 5 personagens: +{_texto_valor_curto(funcao, valor_marco)}",
        inline=True,
    )
    embed.add_field(
        name="Próximo marco",
        value=f"{_fmt_numero(quantidade)} / {_fmt_numero(marco_proximo)}\nFaltam {faltam} personagens",
        inline=True,
    )
    bonus_admin = bonus_por_area["Administração"]
    embed.add_field(
        name="📊 Detalhes do cálculo",
        value=_texto_detalhe_calculo(funcao, marcos, nivel_construcao, cidade.BONUS_BASE_POR_AREA[funcao], bonus_admin, bonus_atual),
        inline=False,
    )
    return embed


def _embed_torre(contexto, resultado_final=False):
    """`resultado_final=True` só depois de clicar "Subir" (já com recompensa/
    novo andar, se venceu) - antes disso é só PREVIEW (`torre.preview_andar`,
    sem efeito colateral)."""
    andar = contexto["andar"]
    cor = 0x2ECC71 if contexto["venceu"] else 0xE74C3C
    titulo = f"🗼 Torre - Andar {andar}"
    embed = discord.Embed(title=titulo, color=cor)
    embed.add_field(name="Power da Party", value=_fmt_numero(contexto["power_total"]), inline=True)
    embed.add_field(name="Power necessário", value=_fmt_numero(contexto["alvo"]), inline=True)
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
        linhas_membros.append(f"{icone} - {m['nome']} - Nv.{m['nivel']} · {vinculo} · CP {_fmt_numero(m['power'])}")
    embed.add_field(name="Sua Party", value="\n".join(linhas_membros), inline=False)
    if resultado_final:
        if contexto["venceu"]:
            bonus_loot = contexto.get("bonus_loot_colecao", 0.0)
            embed.description = (
                f"✅ **Vitória!** +{_fmt_numero(contexto['recompensa'])} WiShards (saldo: {_fmt_numero(contexto['novo_saldo'])}), "
                f"+{_fmt_numero(contexto['xp_ganho'])} XP de Progressão · Bônus da Coleção: +{_fmt_numero(bonus_loot * 100)}% loot "
                f"- avançou pro andar {contexto['novo_andar']}."
            )
        else:
            embed.description = "❌ **Derrota.** Suba de nível/Afinidade ou ajuste a Party e tente de novo - sem RNG, sem cooldown."
    return embed


def _embed_detalhes_party(contexto, guild_id, user_id):
    """Explica o mesmo Power da Party que a Torre usa para o andar atual."""
    detalhes = torre.detalhes_power_party(contexto["membros"], guild_id, user_id)
    categorias = detalhes["categorias"]
    contagem_categorias = ", ".join(
        f"{torre.icone_categoria(categoria)} {categoria}: {categorias.count(categoria)}"
        for categoria in ("DPS", "Tank", "Support")
    )
    composicao = detalhes["bonus_composicao"]
    texto_composicao = (
        f"DPS + Tank + Support: **+{_fmt_numero(composicao * 100)}%**"
        if composicao else "Sem bônus: é preciso ter DPS, Tank e Support."
    )
    embed = discord.Embed(
        title="📊 Detalhes do Power da Party",
        description=f"**Power final: {_fmt_numero(detalhes['total'])}**",
        color=_COR_HUB,
    )
    embed.add_field(
        name="CP dos membros",
        value="\n".join(f"{torre.icone_categoria(m['categoria_combate'])} {m['nome']}: {_fmt_numero(m['power'])}" for m in contexto["membros"]),
        inline=False,
    )
    embed.add_field(
        name="Composição",
        value=f"{contagem_categorias}\n{texto_composicao}\nApós composição: **{_fmt_numero(detalhes['apos_composicao'])}**",
        inline=False,
    )
    embed.add_field(
        name="Bônus da Cidade",
        value=(f"Arcano: +{_fmt_numero(detalhes['bonus_arcano_percentual'] * 100)}%\n"
               f"Após Arcano: **{_fmt_numero(detalhes['apos_arcano'])}**\n"
               f"Militar: +{_fmt_numero(detalhes['bonus_militar_fixo'])} CP"),
        inline=True,
    )
    formula = (
        f"({_fmt_numero(detalhes['soma_individual'])} × {_fmt_numero(1 + composicao, 2)}) "
        f"× {_fmt_numero(1 + detalhes['bonus_arcano_percentual'], 2)} "
        f"+ {_fmt_numero(detalhes['bonus_militar_fixo'])} = **{_fmt_numero(detalhes['total'])}**"
    )
    embed.add_field(name="Fórmula aplicada", value=formula, inline=False)
    embed.set_footer(text="Administração já está incorporada nos bônus de Arcano e Militar.")
    return embed


def _resumo_subir_max(resumo):
    """Texto de resumo do "Subir Max" (2026-09-04) - `resumo` é o dict
    devolvido por `torre.subir_max`. Usado como `embed.description` sobre
    o preview do andar em que parou (mesma composição de texto que
    `_embed_torre(resultado_final=True)` usa pra 1 andar só, só que
    cobrindo VÁRIOS andares de uma vez)."""
    if resumo["andares_subidos"] > 0:
        texto = (
            f"⏫ Subiu **{resumo['andares_subidos']} andar(es)** (do {resumo['andar_inicial']} pro {resumo['andar_final']})! "
            f"+{_fmt_numero(resumo['recompensa_total'])} WiShards, +{_fmt_numero(resumo['xp_total'])} XP de Progressão."
        )
    else:
        texto = f"⏫ Não conseguiu vencer nem o Andar {resumo['andar_inicial']} com a melhor Party possível."
    if resumo["motivo_parada"] == "restricao_impossivel":
        texto += f"\n❌ Travou no Andar {resumo['andar_final']}: {resumo['restricao_travada']} - falta personagem(ns) dessa categoria na sua coleção."
    elif resumo["motivo_parada"] == "power_insuficiente":
        texto += f"\n❌ Travou no Andar {resumo['andar_final']} por Power insuficiente - suba Nível/Afinidade ou invista na Progressão Global."
    elif resumo["motivo_parada"] == "limite_seguranca":
        texto += "\n⚠️ Parou no limite de segurança de andares por chamada - clique em Subir Max de novo pra continuar."
    return texto


class _ViewTorre(ViewPandora):
    """Tela da Torre (2026-08-30) - botão "Subir" sem confirmação extra (a
    resolução é determinística e SEM CUSTO de tentar - perder não consome
    nada, então não existe risco real a confirmar, diferente da Prova de
    Soulmate que tem RNG/cooldown). "Auto-Party" (mesmo dia, pedido do
    usuário: "coloca um auto-party... pega as restrições do andar p montar
    a pt com maior CP") também sem confirmação - substitui a Party inteira
    na hora, mas é sempre reversível (rodar de novo/editar na mão)."""

    def __init__(self, guild_id):
        super().__init__(timeout=900)
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

    @discord.ui.button(label="Subir Max", emoji="⏫", style=discord.ButtonStyle.success)
    async def subir_max(self, interaction: discord.Interaction, botao: discord.ui.Button):
        """"Subir Max" (2026-09-04, pedido do usuário: "usado Subir torre
        ate o máximo possível mas seguindo as regras por andar e trocando
        de time p considerar ela") - `torre.subir_max` sobe em loop até
        perder, trocando a Party automaticamente a cada mudança de
        restrição (nunca precisa clicar "Auto-Party" na mão pra cada
        padrão diferente). Mesmo `defer()` + `to_thread` do "Auto-Party" -
        o loop varre a coleção inteira 1x e pode escrever no banco várias
        vezes, bloquearia o event loop do processo INTEIRO sem isso (mesma
        causa raiz já corrigida lá)."""
        await interaction.response.defer()
        resumo = await asyncio.to_thread(torre.subir_max, self.guild_id, interaction.user.id)
        if resumo["andares_subidos"] > 0:
            await asyncio.to_thread(cidade.atualizar_snapshot_bonus, self.guild_id, interaction.user.id)
            await asyncio.to_thread(series_favoritas.recalcular_bonus, self.guild_id, interaction.user.id)
        _ok, _erro, contexto = torre.preview_andar(self.guild_id, interaction.user.id)
        if contexto is None:
            await interaction.followup.send("Você ainda não tem nenhuma personagem pra montar uma Party.", ephemeral=True)
            return
        embed = _embed_torre(contexto)
        embed.description = _resumo_subir_max(resumo)
        await interaction.edit_original_response(embed=embed, view=self)

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

    @discord.ui.button(label="Detalhes da Party", emoji="📊", style=discord.ButtonStyle.secondary)
    async def detalhes_party(self, interaction: discord.Interaction, botao: discord.ui.Button):
        ok, erro, contexto = await asyncio.to_thread(torre.preview_andar, self.guild_id, interaction.user.id)
        if not ok:
            await interaction.response.send_message(erro, ephemeral=True)
            return
        embed = _embed_detalhes_party(contexto, self.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
