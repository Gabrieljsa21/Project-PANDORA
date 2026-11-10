# -*- coding: utf-8 -*-
"""Inventário, Conquistas, Bônus por Classe e Investir em Massa.

Parte de `pandora.paineis` (dividido por tela em 2026-11-10); de fora do
pacote, continuar usando `from pandora import paineis` e `paineis.<nome>`."""
import asyncio
import discord
from pandora import db
from pandora import batalha, conquistas, itens, torre, worldboss
from pandora.ui_base import ModalPandora, ViewPandora
from pandora.paineis.comum import (
    _COR_HUB,
    _ModalBuscarPersonagem,
    _ViewSelecionarPersonagem,
    _descricao_personagem_dropdown,
    _descricao_personagem_livre_dropdown,
    _fmt_numero,
)
from pandora.paineis.equipe import (
    _fluxo_usar_upgrade_construcao,
)
from pandora.paineis.loja import (
    _int_seguro,
)
from pandora.paineis.batalha import (
    _ViewEscolherFormacaoBatalha,
    _resolver_e_revelar,
)


# ==========================================================================
# Itens/Conquistas (2026-09-01, "World Boss: Recompensas e Conquistas") -
# regra de negócio em `pandora.itens`/`pandora.conquistas`, aqui só a UI.
# ==========================================================================


class ViewInventarioHub(ViewPandora):
    """Painel "🎒 Inventário" - painel PESSOAL (restrito ao autor, ao
    contrário do World Boss). Só mostra botão de usar pra item que o
    jogador REALMENTE tem (Roll/Claim Permanente não têm botão - já se
    aplicam sozinhos na hora do ganho/compra, só mostrados como status)."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=900)
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
            botao = discord.ui.Button(
                label=f"Usar Upgrade de Construção (x{posse['upgrade_construcao']})",
                emoji="🏗️", style=discord.ButtonStyle.primary, row=1,
            )
            botao.callback = _fluxo_usar_upgrade_construcao(self.guild_id, self.autor_id)
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
            # 🔥 "/teto" (2026-09-03) - área/construção deixaram de ser 2
            # coisas (`itens.AREAS_CONSTRUCAO` era um dict área->nome de
            # construção, "Militar"->"Quartel"; pedido do usuário: "vc tem
            # distinguindo construção de area, mas é a msm coisa, so use
            # area") - só a área agora, com o teto DINÂMICO vigente ao lado
            # (`db.teto_atual_construcao`, ver comentário lá).
            teto = db.teto_atual_construcao(self.guild_id, self.autor_id)
            linhas_construcao = [f"{area}: Nível {nivel}/{teto}" for area, nivel in niveis.items()]
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
        # 🔥 mesmo formato de dropdown do Party/Merge (2026-09-06, pedido do
        # usuário: "os de personagem tem q ser igual do party").
        contexto_lote = await asyncio.to_thread(torre._contexto_lote, self.guild_id, interaction.user.id)

        async def _ao_selecionar(interacao_sel, personagens, _candidatos):
            ok, mensagem = itens.usar_protecao(self.guild_id, interacao_sel.user.id, personagens[0]["id"])
            await interacao_sel.response.edit_message(content=mensagem, view=None)

        modal = _ModalBuscarPersonagem(
            "Proteger qual personagem?", colecao, "Escolha a personagem...", _ao_selecionar,
            descricao=lambda p: _descricao_personagem_dropdown(p, self.guild_id, interaction.user.id, contexto_lote),
        )
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

        # 🔥 Descrição "livre" (2026-09-06, pedido do usuário: "os de
        # personagem tem q ser igual do party") - cada perdida tem um DONO
        # ATUAL diferente (quem venceu a Batalha), não dá pra usar 1 só
        # `contexto_lote` (é por conta); mostra classe/CP base, que não
        # dependem de dono nenhum.
        view = _ViewSelecionarPersonagem(
            perdidas, "Escolha quem recuperar...", _ao_selecionar,
            descricao=lambda p: _descricao_personagem_livre_dropdown(p),
        )
        await interaction.response.send_message("Selecione:", view=view, ephemeral=True)

    async def _usar_chave(self, interaction: discord.Interaction):
        ok, mensagem = itens.usar_chave_da_torre(self.guild_id, interaction.user.id)
        self._montar()
        await interaction.response.edit_message(content=mensagem, embed=self.formatar(), view=self)

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
        view_select = ViewPandora(timeout=900)
        view_select.add_item(select)
        await interaction.response.send_message("Escolha o próximo World Boss desse servidor:", view=view_select, ephemeral=True)


class ViewConquistasHub(ViewPandora):
    """Painel "🏆 Conquistas" - 2 famílias distintas (2026-09-01): 🐉 World
    Boss (registro puro, Seção 15 - lista só o que já foi desbloqueado) e
    📚 Colecionador (`ERIS_sistema_colecao_wishards.md` Seções 22/24, paga
    WiShards por marco - mostra PROGRESSO de todas as famílias, mesmo as
    ainda sem nenhum marco batido, não só as já desbloqueadas)."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=900)
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


class ViewBonusClasseHub(ViewPandora):
    """Painel "⚔️ Bônus por Classe" (2026-09-02, pedido do usuário: "uma
    nova tela q mostrasse q DPS ta ganhando +X Tank +Y... e n sei se
    separou por classe tbm") - 1 campo por categoria de combate (DPS/Tank/
    Support), com o total somado das classes que o jogador possui daquela
    categoria, e logo abaixo a lista de CADA classe com seu próprio
    bônus/progresso (`db.bonus_classes_por_categoria`)."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=900)
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
                f"{c['classe']}: +{_fmt_numero(c['bonus'])} CP ({c['quantidade']} possuída(s) · próximo marco: +{_fmt_numero(c['ganho_proximo_marco'])} CP)"
                for c in dados["classes"]
            ]
            embed.add_field(
                name=f"{icone} {categoria} - +{_fmt_numero(dados['total_bonus'])} CP no total ({dados['total_personagens']} personagens)",
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

class _ModalInvestirEmMassa(ModalPandora):
    """🔥 `saldo_atual` (2026-09-01, pedido do usuário: "o investir em
    massa tem que informar quanto tenho para investir") - o campo do
    Modal não pode mostrar um valor pronto de antemão sem ser um `Text
    Input` de VERDADE construído por instância (por isso não é mais um
    atributo de classe fixo) - o saldo (WiShards ou Soulstone, conforme
    `tipo`) já vem no LABEL, visível antes mesmo de digitar."""

    def __init__(self, guild_id, tipo, saldo_atual, colecao=None, view_serie=None):
        """`colecao` (opcional, 2026-09-03, pedido do usuário: "botao la
        tbm p maximizar nivel e afinidade da serie, assim como é o em
        massa") - escopo alternativo à coleção INTEIRA (default `None`),
        usado pelo navegador de Série Favorita pra restringir o
        investimento só às personagens daquela série. `view_serie`
        (2026-09-06, pedido do usuário: "tem como editar a própria
        mensagem já com as infos atualizadas apos essas ações?") - só vem
        preenchido junto com `colecao` (o navegador que abriu este Modal),
        pra reeditar o CARD dele com o CP/Nível/Afinidade atualizados
        depois do investimento; `None` no "📈 Investir em Massa" genérico
        do hub, que não tem card nenhum pra reeditar."""
        super().__init__(title=f"Investir em massa - {'Nível' if tipo == 'nivel' else 'Afinidade'}")
        self.guild_id = guild_id
        self.tipo = tipo
        self._colecao = colecao
        self._view_serie = view_serie
        moeda = "WiShards" if tipo == "nivel" else "Soulstone"
        self.valor = discord.ui.TextInput(
            label=f"Quanto? (você tem {_fmt_numero(saldo_atual)} {moeda})"[:45],
            placeholder="Ex.: 50000, 50.000 ou 50K",
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
            await interaction.followup.send(f"Nenhuma personagem pôde subir com {_fmt_numero(orcamento)} {moeda} disponível.", ephemeral=True)
            return
        linhas = [f"{personagem['nome']}: {antes} → {depois}" for personagem, antes, depois in detalhes[:25]]
        texto = "\n".join(linhas)
        if len(detalhes) > 25:
            texto += f"\n... e mais {len(detalhes) - 25} personagem(ns)."
        await interaction.followup.send(f"✅ Investidos {_fmt_numero(gasto)}/{_fmt_numero(orcamento)} {moeda} em {len(detalhes)} personagem(ns):\n{texto}", ephemeral=True)
        if self._view_serie is not None:
            await self._view_serie._reeditar_apos_acao_em_massa()


class _ViewInvestirEmMassa(ViewPandora):
    """Escolhe Nível (WiShards) ou Afinidade (Soulstone) - cada um abre o
    Modal que pede só o orçamento, sem precisar escolher personagem
    nenhuma (a ordem por CP decide sozinha onde investir)."""

    def __init__(self, guild_id):
        super().__init__(timeout=900)
        self.guild_id = guild_id

    @discord.ui.button(label="Nível (WiShards)", emoji="⬆️", style=discord.ButtonStyle.success)
    async def nivel(self, interaction: discord.Interaction, botao: discord.ui.Button):
        saldo = await asyncio.to_thread(db.saldo_wishards, self.guild_id, interaction.user.id)
        await interaction.response.send_modal(_ModalInvestirEmMassa(self.guild_id, "nivel", saldo))

    @discord.ui.button(label="Afinidade (Soulstone)", emoji="💕", style=discord.ButtonStyle.success)
    async def afinidade(self, interaction: discord.Interaction, botao: discord.ui.Button):
        saldo = await asyncio.to_thread(db.saldo_soulstone, self.guild_id, interaction.user.id)
        await interaction.response.send_modal(_ModalInvestirEmMassa(self.guild_id, "afinidade", saldo))
