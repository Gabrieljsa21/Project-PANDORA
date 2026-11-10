# -*- coding: utf-8 -*-
"""Card "🔍 Personagem": navegação por posição/bloco/busca, Upar Nível, Aumentar Afinidade e detalhes de CP.

Parte de `pandora.paineis` (dividido por tela em 2026-11-10); de fora do
pacote, continuar usando `from pandora import paineis` e `paineis.<nome>`."""
import asyncio
import discord
from pandora import db
from pandora import cidade, consulta, personagens_favoritas, series_favoritas, torre
from pandora.ui_base import ViewPandora
from pandora.paineis.comum import (
    _COR_HUB,
    _ModalBuscarPosicaoOuNome,
    _ViewConfirmar,
    _ViewEscolherAlvo,
    _descricao_personagem_dropdown,
    _fmt_numero,
)


def _embed_detalhes_cp_personagem(personagem, guild_id, user_id):
    """Abre a conta completa do CP individual, com os mesmos insumos de
    ``torre.power_personagem``. É uma tela explicativa: não soma bônus de
    Party nem os bônus da Cidade, que pertencem ao cálculo da Torre."""
    niveis, bonus_global, cache_classe, bonus_series, favoritas_ocupantes = torre._contexto_lote(guild_id, user_id)
    personagem_id = personagem["id"]
    nivel = niveis.get(personagem_id, 1)
    afinidade = db.afinidade(guild_id, user_id, personagem_id)
    soulmate = db.is_soulmate(guild_id, user_id, personagem_id)
    personagem_vinculada = {**personagem, "afinidade": afinidade, "is_soulmate": soulmate}

    base_natural = torre.power_base(personagem["popularidade"])
    base_efetiva = base_natural
    fortalecimento = ascensao = 0.0
    ocupante = favoritas_ocupantes.get(personagem_id)
    if ocupante:
        base_fortalecida, _proximo = personagens_favoritas._estado_fortalecimento(
            personagem["popularidade"], ocupante["fortalecimento_bitmask"],
        )
        elegivel = personagens_favoritas.elegivel_ascensao(personagem_vinculada, nivel, base_fortalecida)
        base_efetiva = personagens_favoritas.power_efetivo(
            personagem["popularidade"], ocupante["fortalecimento_bitmask"], ocupante["nivel_ascensao"], elegivel,
        )
        fortalecimento = base_fortalecida - base_natural
        ascensao = base_efetiva - base_fortalecida

    bonus_nivel = (nivel - 1) * torre.BONUS_POWER_POR_NIVEL
    subtotal = base_efetiva + bonus_nivel
    multiplicador_vinculo = 2.0 if soulmate else 1.0 + (afinidade - 1) * 0.10
    apos_vinculo = subtotal * multiplicador_vinculo
    estado = db.progressao_conta(guild_id, user_id)
    bonus_progressao = estado["nivel"] // db.NIVEIS_PROGRESSAO_POR_PONTO_PERCENTUAL / 100
    bonus_maestria = estado["nivel_potencial_colecao"] * db.BONUS_PERCENTUAL_POR_NIVEL_POTENCIAL / 100
    bonus_fixo, bonus_percentual = bonus_global
    apos_conta = apos_vinculo * (1 + bonus_percentual)
    bonus_serie = bonus_series.get(personagem.get("serie"), 0.0)
    apos_serie = apos_conta * (1 + bonus_serie)
    power_final, _nivel, categoria = torre.power_personagem(
        personagem_vinculada, guild_id, user_id, nivel=nivel, bonus_global=bonus_global,
        cache_bonus_classe=cache_classe, bonus_series=bonus_series, favoritas_ocupantes=favoritas_ocupantes,
    )
    bonus_classe = cache_classe.get(personagem.get("classe"), (0.0, None, None))[0]
    bonus_fixo_progressao = estado["nivel"] * db.BONUS_FIXO_POR_NIVEL_PROGRESSAO
    bonus_fixo_treinamento = estado["nivel_treinamento_global"] * db.BONUS_FIXO_POR_NIVEL_TREINAMENTO

    embed = discord.Embed(
        title=f"📊 Detalhes do CP · {personagem['nome']}",
        description=f"{torre.icone_categoria(categoria)} **CP individual final: {_fmt_numero(power_final)}**",
        color=_COR_HUB,
    )
    linhas_base = [f"Base natural: **{_fmt_numero(base_natural)}**"]
    if ocupante:
        linhas_base.extend([
            f"Fortalecimento: +{_fmt_numero(fortalecimento)}",
            f"Ascensão: +{_fmt_numero(ascensao)}",
            f"Base efetiva: **{_fmt_numero(base_efetiva)}**",
        ])
    linhas_base.extend([f"Nível {nivel}: +{_fmt_numero(bonus_nivel)}", f"Subtotal: **{_fmt_numero(subtotal)}**"])
    embed.add_field(name="Base e Nível", value="\n".join(linhas_base), inline=True)

    vinculo = f"Soulmate: **×2,0** (substitui Afinidade {afinidade})" if soulmate else f"Afinidade {afinidade}: **×{_fmt_numero(multiplicador_vinculo, 1)}**"
    embed.add_field(
        name="Afinidade e Soulmate",
        value=f"{vinculo}\nApós vínculo: **{_fmt_numero(apos_vinculo)}**",
        inline=True,
    )
    linhas_multiplicadores = [
        f"Progressão Lv.{estado['nivel']}: +{_fmt_numero(bonus_progressao * 100)}%",
        f"Maestria Lv.{estado['nivel_potencial_colecao']}: +{_fmt_numero(bonus_maestria * 100)}%",
        f"Conta: **×{_fmt_numero(1 + bonus_percentual, 2)}**",
    ]
    if bonus_serie:
        linhas_multiplicadores.append(f"Série favorita: +{_fmt_numero(bonus_serie * 100)}%")
    linhas_multiplicadores.append(f"Após multiplicadores: **{_fmt_numero(apos_serie)}**")
    embed.add_field(name="Multiplicadores", value="\n".join(linhas_multiplicadores), inline=False)
    embed.add_field(
        name="Bônus fixos",
        value=(f"Progressão: +{_fmt_numero(bonus_fixo_progressao)}\n"
               f"Treinamento da Coleção: +{_fmt_numero(bonus_fixo_treinamento)}\n"
               f"Classe {personagem.get('classe') or 'sem classe'}: +{_fmt_numero(bonus_classe)}"),
        inline=True,
    )
    formula = (
        f"({_fmt_numero(base_efetiva)} + {_fmt_numero(bonus_nivel)}) × {_fmt_numero(multiplicador_vinculo, 1)} "
        f"× {_fmt_numero(1 + bonus_percentual, 2)} × {_fmt_numero(1 + bonus_serie, 2)} "
        f"+ {_fmt_numero(bonus_fixo)} + {_fmt_numero(bonus_classe)} = **{_fmt_numero(power_final)}**"
    )
    embed.add_field(name="Fórmula aplicada", value=formula, inline=False)
    embed.set_footer(text="Arcano, Militar e composição são bônus da Party/Torre; não entram no CP individual.")
    return embed


class _ViewNivel(ViewPandora):
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
        super().__init__(timeout=900)
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
        contexto_lote = torre._contexto_lote(self.guild_id, self.autor_id)
        niveis, bonus_global, cache_classe, bonus_series, favoritas_ocupantes = contexto_lote
        personagem_vinculada = {
            **self.personagem,
            "afinidade": db.afinidade(self.guild_id, self.autor_id, self.personagem["id"]),
            "is_soulmate": db.is_soulmate(self.guild_id, self.autor_id, self.personagem["id"]),
        }
        power, _nivel_ignorado, categoria = torre.power_personagem(
            personagem_vinculada, self.guild_id, self.autor_id,
            nivel=niveis.get(self.personagem["id"], 1), bonus_global=bonus_global, cache_bonus_classe=cache_classe,
            bonus_series=bonus_series, favoritas_ocupantes=favoritas_ocupantes,
        )
        embed.add_field(name="CP", value=f"{torre.icone_categoria(categoria)} {_fmt_numero(power)}", inline=True)
        if custo is None:
            embed.add_field(name="Nível", value=f"{nivel_atual} (máximo)", inline=True)
            self.upar.disabled = True
        else:
            embed.add_field(name="Nível", value=f"{nivel_atual} (próximo: {_fmt_numero(custo)} WiShards)", inline=True)
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
            embed.add_field(name="Afinidade", value=f"{afinidade_atual} (próximo: {_fmt_numero(custo_afinidade)} Soulstone)", inline=True)
            self.upar_afinidade.disabled = False
        favorita = db.esta_na_wishlist(self.guild_id, self.autor_id, self.personagem["id"])
        self.favoritar.label = "Desfavoritar" if favorita else "Favoritar"
        self.favoritar.style = discord.ButtonStyle.success if favorita else discord.ButtonStyle.secondary
        # 🔥 Estatística de Torre (2026-09-01, pedido do usuário: "saber
        # quais personagens mais subiram torre") - só aparece se já
        # contribuiu pra pelo menos 1 vitória, sem poluir o card de quem
        # nunca usou a Torre.
        andares_vencidos = db.andares_vencidos_personagem(self.guild_id, self.autor_id, self.personagem["id"])
        if andares_vencidos:
            embed.add_field(name="🗼 Andares vencidos", value=_fmt_numero(andares_vencidos), inline=True)
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
        if db.esta_na_wishlist(self.guild_id, self.autor_id, self.personagem["id"]):
            db.wishlist_remover(self.guild_id, self.autor_id, self.personagem["id"])
            self._status = f"Desmarcada como favorita: **{self.personagem['nome']}**."
        else:
            ok, mensagem = db.wishlist_adicionar(self.guild_id, self.autor_id, self.personagem["id"])
            self._status = f"{'⭐' if ok else '⚠️'} {mensagem}"
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    @discord.ui.button(label="Detalhes CP", emoji="📊", style=discord.ButtonStyle.secondary)
    async def detalhes_cp(self, interaction: discord.Interaction, botao: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        embed = await asyncio.to_thread(_embed_detalhes_cp_personagem, self.personagem, self.guild_id, self.autor_id)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Divorciar", emoji="💔", style=discord.ButtonStyle.danger)
    async def divorciar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        if db.esta_na_wishlist(self.guild_id, self.autor_id, self.personagem["id"]):
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
            mensagem = f"💔 Personagem liberada da sua coleção - +{_fmt_numero(recompensa)} WiShards, +{_fmt_numero(xp)} XP de Progressão (Afinidade preservada, um resgate futuro continua com o vínculo)."
        else:
            mensagem = "Você não tem essa personagem nesse servidor."
        await interaction.response.edit_message(content=mensagem, embed=None, view=None)


def _sufixo_aviso_sem_classe(tem_classe):
    """Sufixo pra mensagem de compra quando a personagem saiu SEM classe
    (`gacha.comprar_com_revelacao` devolveu `tem_classe=False`) - 2026-09-05,
    achado do usuário: "as personagens compradas estão vindo sem classe"
    (mais provável numa compra em lote tipo "Comprar Tudo", já que a cota
    diária de tokens da Groq só aguenta ~23 classificações reais por dia,
    ver CHANGELOG). Aponta pro `/pandora_admin validar_classes` (já existia,
    cobre exatamente esse caso) como retentativa, em vez de ficar
    silencioso."""
    if tem_classe:
        return ""
    return " ⚠️ Sem classe por enquanto (GAIA sem cota/fora do ar) - `/pandora_admin validar_classes` tenta de novo depois."


# 🔥 Militar/Arcano/Administração são bônus AO VIVO (nunca "/h" - não
# acumulam no tempo, são um modificador de estado sempre ativo); Saúde/
# Cultura/Comércio são taxa POR HORA de verdade (acumulam) - hoisted pra
# módulo (2026-09-07) pra `_embed_cidade`/`_embed_cidade_area_detalhe`
# reaproveitarem a mesma formatação, sem duplicar.
_TEXTO_BONUS_POR_FUNCAO = {
    "Militar": lambda t: f"+{_fmt_numero(t)} CP fixo para a Party",
    "Saúde": lambda t: f"+{_fmt_numero(t)} Soulstone/h",
    "Cultura": lambda t: f"+{_fmt_numero(t)} XP de Progressão/h",
    "Administração": lambda t: f"+{_fmt_numero(t * 100)}% de eficiência das outras áreas",
    "Comércio": lambda t: f"+{_fmt_numero(t)} WiShards/h",
    "Arcano": lambda t: f"+{_fmt_numero(t * 100)}% CP para a Party",
}

# 🔥 Versão CURTA da unidade, SEM o "+" (2026-09-07) - só pro termo
# "base" da linha "📊 Detalhes do cálculo" da tela de detalhe
# (`_embed_cidade_area_detalhe`), onde o texto completo de `_TEXTO_
# BONUS_POR_FUNCAO` (com "+" e o resto da frase) não cabe no meio da
# fórmula ("580 marcos × 10 CP base × Lv10").
_UNIDADE_CURTA_POR_FUNCAO = {
    "Militar": ("CP", False), "Saúde": ("Soulstone/h", False), "Cultura": ("XP/h", False),
    "Administração": ("%", True), "Comércio": ("WiShards/h", False), "Arcano": ("% CP", True),
}


def _numero_valor_curto(funcao, valor):
    """Só o NÚMERO (sem unidade) - `%` já multiplicado por 100 quando
    aplicável, pronto pra entrar numa multiplicação/exibição em cadeia
    (`_texto_detalhe_calculo`). Mais casas decimais pra número MENOR que 1
    (2026-09-07, achado testando Administração/Arcano) - o bônus-base
    percentual delas é bem pequeno (0,005%/0,01%) e o padrão de 1 casa
    decimal do `_fmt_numero` arredondava pra "0" (`round(0.005, 1) ==
    0.0`), sumindo com o número."""
    _unidade, is_percentual = _UNIDADE_CURTA_POR_FUNCAO[funcao]
    numero = valor * 100 if is_percentual else valor
    casas = 3 if 0 < abs(numero) < 1 else 1
    return _fmt_numero(numero, casas)


def _texto_valor_curto(funcao, valor):
    unidade, _is_percentual = _UNIDADE_CURTA_POR_FUNCAO[funcao]
    numero_str = _numero_valor_curto(funcao, valor)
    # 🔥 "%"/"% CP" colam direto no número (17,9%, não "17,9 %") - só
    # unidades por extenso (CP, Soulstone/h...) levam espaço antes.
    return f"{numero_str}{unidade}" if unidade.startswith("%") else f"{numero_str} {unidade}"


def _texto_detalhe_calculo(funcao, marcos, nivel_construcao, valor_base, bonus_admin, bonus_final):
    """"📊 Detalhes do cálculo" por extenso (2026-09-07, pedido do
    usuário: "Quero q as areas tenham as infos do calculo mais
    detalhadas", com a fórmula/variáveis/cálculo exatas que ele deu -
    conferida contra o código: `B_final = M × B_base × Lv × (1 + A)` pras
    áreas que recebem o cross-bonus da Administração (`cidade.
    _bonus_todas_areas`). Militar e Arcano usam a curva própria `Lv ×
    0,05`; a
    própria Administração não tem o termo `(1 +
    A)` (nunca cruza sobre si mesma), então sai da fórmula/Cálculo dela,
    não só do valor."""
    m_str = _fmt_numero(marcos, 0)
    base_str = _numero_valor_curto(funcao, valor_base)
    variaveis = [
        f"M = Marcos concluídos = {m_str}",
        f"B_base = Bônus-base por marco = {_texto_valor_curto(funcao, valor_base)}",
        f"Lv = Nível da construção = {nivel_construcao}",
    ]
    if funcao == "Administração":
        formula = "B_final = M × B_base × Lv"
        calculo = f"{m_str} × {base_str} × {nivel_construcao} = {_texto_valor_curto(funcao, bonus_final)}"
    elif funcao in ("Militar", "Arcano"):
        multiplicador_nivel = cidade.multiplicador_nivel(funcao, nivel_construcao)
        variaveis.append(f"Lv × 0,05 = Multiplicador de nível {funcao} = {_fmt_numero(multiplicador_nivel, 3)}")
        variaveis.append(f"A = Bônus da Administração = {_texto_valor_curto('Administração', bonus_admin)}")
        formula = "B_final = M × B_base × (Lv × 0,05) × (1 + A)"
        calculo = (
            f"{m_str} × {base_str} × ({nivel_construcao} × 0,05) × (1 + {_fmt_numero(bonus_admin, 3)}) "
            f"= {_texto_valor_curto(funcao, bonus_final)}"
        )
    else:
        variaveis.append(f"A = Bônus da Administração = {_texto_valor_curto('Administração', bonus_admin)}")
        formula = "B_final = M × B_base × Lv × (1 + A)"
        calculo = (
            f"{m_str} × {base_str} × {nivel_construcao} × (1 + {_fmt_numero(bonus_admin, 3)}) "
            f"= {_texto_valor_curto(funcao, bonus_final)}"
        )
    variaveis.append("B_final = Bônus final da área")
    return (
        f"**Fórmula**\n{formula}\n\n"
        f"**Variáveis**\n" + "\n".join(variaveis) + "\n\n"
        f"**Cálculo**\n{calculo}"
    )


def _pips_construcao(nivel_construcao):
    """Indicador visual de nível (◆ preenchido / ◇ vazio) pro card da
    Cidade (2026-09-06, mockup do usuário - pips em vez de só o número) -
    10 pips por "década" de nível (o teto sobe de 10 em 10, `db.teto_
    atual_construcao`), preenche do zero a cada nova década (Lv13 mostra
    3/10 preenchidos, não 13/10)."""
    preenchidos = nivel_construcao % 10
    if nivel_construcao and preenchidos == 0:
        preenchidos = 10
    return "◆" * preenchidos + "◇" * (10 - preenchidos)


# 🔥 Rótulo de exibição por origem do ledger de XP (2026-09-07, pedido do
# usuário: "botao de progressao, mostrando as fontes de xp acumaladas ate
# entao") - `origem` bruta (`db.xp_por_origem`) é a mesma chave usada nos
# ledgers de WiShards/Soulstone (snake_case, sem acento); origem sem
# entrada aqui (ex.: alguma futura) cai no fallback (capitaliza a chave
# crua, nunca quebra por origem desconhecida).
_ROTULO_ORIGEM_XP = {
    "cidade_producao": "🏙️ Cidade (produção)",
    "torre_andar": "🗼 Torre (andares vencidos)",
    "claim": "🎯 Claims",
    "divorcio": "💔 Divórcio",
    "upar_nivel_personagem": "⬆️ Upar Nível",
    "merge": "🧬 Fusão",
    "marco_colecao": "🏆 Marcos de coleção",
    "admin_atribuicao": "🛠️ Atribuição administrativa",
    "auto_colecionador": "🤖 Auto-colecionador",
    "worldboss_vitoria": "🐉 World Boss (vitória)",
}


def _embed_progressao_cidade(guild_id, user_id):
    """"📈 Progressão" (2026-09-07, pedido do usuário: "botao de
    progressao, mostrando as fontes de xp acumaladas ate entao") - Nível/
    XP atual + quanto falta pro próximo, e a soma de XP por origem
    (`db.xp_por_origem`, ledger próprio - só existe a partir de 2026-09-07,
    então XP creditado ANTES disso não aparece discriminado por fonte,
    só no Nível/XP totais em si)."""
    estado = db.progressao_conta(guild_id, user_id)
    nivel, xp = estado["nivel"], estado["xp"]
    necessario = db.xp_necessario_nivel(nivel, guild_id, user_id)
    embed = discord.Embed(
        title="📈 Progressão",
        description=f"Nível {nivel} - {_fmt_numero(xp)} / {_fmt_numero(necessario)} XP pro próximo nível",
        color=_COR_HUB,
    )
    por_origem = db.xp_por_origem(guild_id, user_id)
    if not por_origem:
        embed.add_field(
            name="Fontes de XP acumuladas",
            value="Nenhum XP registrado ainda por este contador (criado 2026-09-07 - XP de antes não fica discriminado por fonte, só no Nível/XP acima).",
            inline=False,
        )
        return embed
    total = sum(por_origem.values())
    linhas = [
        f"{_ROTULO_ORIGEM_XP.get(origem, origem.replace('_', ' ').capitalize())}: {_fmt_numero(soma)} XP"
        for origem, soma in por_origem.items()
    ]
    embed.add_field(
        name=f"Fontes de XP acumuladas (desde 2026-09-07) - total {_fmt_numero(total)} XP",
        value="\n".join(linhas),
        inline=False,
    )
    return embed


def _fluxo_progressao_cidade(guild_id, autor_id):
    """Callback do botão "📈 Progressão" da Cidade - mesmo padrão EPHEMERAL
    de `_fluxo_detalhe_area_cidade`."""
    async def callback(interaction: discord.Interaction):
        if str(interaction.user.id) != autor_id:
            await interaction.response.send_message("Esse painel não é seu.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        embed = await asyncio.to_thread(_embed_progressao_cidade, guild_id, interaction.user.id)
        await interaction.followup.send(embed=embed, ephemeral=True)
    return callback
