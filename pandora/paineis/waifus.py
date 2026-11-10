# -*- coding: utf-8 -*-
"""Personagens Favoritas (Waifus): slots, Fortalecimento e Ascensão.

Parte de `pandora.paineis` (dividido por tela em 2026-11-10); de fora do
pacote, continuar usando `from pandora import paineis` e `paineis.<nome>`."""
import asyncio
import discord
from pandora import db
from pandora import consulta, personagens_favoritas, torre
from pandora.ui_base import ViewPandora
from pandora.paineis.comum import (
    _ModalBuscarCatalogoWishlist,
    _ViewEscolherAlvo,
    _descricao_personagem_dropdown,
    _fmt_numero,
)


# ==========================================================================
# Personagens Favoritas (2026-09-03) - mesma lógica estrutural de Séries
# Favoritas acima, mas a progressão (Fortalecimento/Ascensão) pertence ao
# SLOT, não à personagem - ver `pandora.personagens_favoritas` pro núcleo.
# ==========================================================================

class _ViewPersonagensFavoritas(ViewPandora):
    """Gerenciar Personagens Favoritas - navegador com setas ◀️/▶️ entre os
    slots (2026-09-06, pedido do usuário: "quero q na propria tela de
    waifus... seja como a tela de personagens, q tem as setas p ver as
    imagens e dados detalhados de cada uma"), mesmo espírito de `_ViewNivel`
    ("🔍 Personagem") - substitui o antigo par "lista em texto + Select de
    slot" (`_ViewPersonagensFavoritas`) + "mensagem separada de detalhe"
    (`_ViewDetalheFavorita`, hoje fundida aqui) por UMA tela só, sempre
    mostrando o card completo (imagem/classe/vínculo) do slot atual. Nunca
    precisa paginar em blocos de 25 como "🔍 Personagem" faz - o total de
    slots é sempre pequeno (`SLOTS_MAXIMO`, no máximo 25), cabe inteiro em
    memória de uma vez."""

    @classmethod
    async def criar(cls, guild_id, user_id, indice=0):
        # 🔥 `criar()` async, busca fora de `__init__` (2026-09-03, mesmo
        # motivo já documentado em `_ViewSeriesFavoritas`: construir a View
        # inteira dentro de um `to_thread` deixa `BaseView.__init__` sem
        # event loop, e todo clique subsequente é descartado em silêncio).
        # 🔥 `contexto_lote` também pré-carregado aqui (2026-09-06, pedido
        # do usuário: "Nesse dropdown de slot era p ser igual dos outros
        # personagens, mostrando todas aquelas infos") - o dropdown "Ir
        # direto pro slot" passou a usar `_descricao_personagem_dropdown`
        # (classe/CP/CP base/Nível/Afinidade, mesmo formato de Party/Merge/
        # "🔍 Personagem"), que precisa desse contexto em lote pra não abrir
        # 1 consulta por slot ocupado.
        slots = await asyncio.to_thread(personagens_favoritas.listar, guild_id, user_id)
        contexto_lote = await asyncio.to_thread(torre._contexto_lote, guild_id, user_id)
        return cls(guild_id, user_id, slots, indice=indice, contexto_lote=contexto_lote)

    def __init__(self, guild_id, user_id, slots, indice=0, contexto_lote=None):
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.user_id = str(user_id)
        self._slots = slots
        self._indice = min(indice, len(slots) - 1)
        self._contexto_lote = contexto_lote
        self._montar_botoes()

    @property
    def _item(self):
        return self._slots[self._indice]

    async def _atualizar(self):
        self._slots = await asyncio.to_thread(personagens_favoritas.listar, self.guild_id, self.user_id)
        self._contexto_lote = await asyncio.to_thread(torre._contexto_lote, self.guild_id, self.user_id)
        self._indice = min(self._indice, len(self._slots) - 1)
        self._montar_botoes()

    def _montar_botoes(self):
        self.clear_items()
        self._montar_select_slots()
        anterior = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary, row=1, disabled=self._indice <= 0)
        anterior.callback = self._navegar_anterior
        self.add_item(anterior)
        proximo = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary, row=1, disabled=self._indice >= len(self._slots) - 1)
        proximo.callback = self._navegar_proximo
        self.add_item(proximo)

        item = self._item
        if item["personagem"]:
            if item["adquirida"] and item["proximo_fortalecimento"]:
                # 🔥 Dropdown "até qual patamar ir" (2026-09-06, pedido do
                # usuário: "o botao de fortalecer... tem de permitir
                # fortalecer varios niveis por vez, por um dropdown igual
                # nos outros locais, mostrando custo e qnt tenho") -
                # substitui o antigo par "Fortalecer" (1 patamar) +
                # "Fortalecer ao Máximo" (gasta tudo): a 1ª opção do
                # dropdown É o antigo comportamento de 1 clique, a última é
                # "gastar tudo que dá pra esse slot" - um botão só cobre os
                # dois casos e tudo no meio.
                fortalecer_botao = discord.ui.Button(label="Fortalecer", emoji="💪", style=discord.ButtonStyle.success, row=2)
                fortalecer_botao.callback = self._fortalecer
                self.add_item(fortalecer_botao)
            elif item["adquirida"] and item["elegivel_ascensao"]:
                ascender_botao = discord.ui.Button(label="Ascender", emoji="✨", style=discord.ButtonStyle.success, row=2)
                ascender_botao.callback = self._ascender
                self.add_item(ascender_botao)
            trocar_botao = discord.ui.Button(label="Trocar personagem", emoji="🔄", style=discord.ButtonStyle.secondary, row=3)
            trocar_botao.callback = self._trocar
            self.add_item(trocar_botao)
            esvaziar_botao = discord.ui.Button(label="Esvaziar slot", emoji="🗑️", style=discord.ButtonStyle.danger, row=3)
            esvaziar_botao.callback = self._esvaziar
            self.add_item(esvaziar_botao)
        else:
            escolher_botao = discord.ui.Button(label="Escolher personagem", emoji="➕", style=discord.ButtonStyle.primary, row=2)
            escolher_botao.callback = self._trocar
            self.add_item(escolher_botao)


    def _montar_select_slots(self):
        """Dropdown "ir direto pro slot" (2026-09-06, pedido do usuário:
        "Ficou faltando o dropdown p ir rapido para os personagens na tela
        de waifu") - a troca pelo navegador com setas (leva anterior, mesmo
        dia) perdeu esse atalho que a tela antiga já tinha (`slot_select`
        de `_ViewPersonagensFavoritas`, versão pré-navegador); mesmo
        espírito do "🔍 Personagem", que tem os dois ao mesmo tempo (setas
        E um menu suspenso pra pular direto), não um só. Sempre cabe TUDO
        numa página só (no máximo `SLOTS_MAXIMO`, bem abaixo do teto de 25
        de um `discord.ui.Select`), então não precisa de bloco/paginação
        como o "🔍 Personagem" precisa pra milhares de personagens.

        🔥 Descrição PADRÃO (2026-09-06, pedido do usuário: "Nesse dropdown
        de slot era p ser igual dos outros personagens, mostrando todas
        aquelas infos") - reaproveita `_descricao_personagem_dropdown`
        (classe, CP final, CP base, Nível, Afinidade, ícone de categoria),
        o MESMO formato de Party/Merge/Trocas/"🔍 Personagem", em vez de um
        texto próprio (só nome + "Power atual" do slot). O CP final aqui já
        reflete o Power do PRÓPRIO slot (Fortalecimento/Ascensão) - `torre.
        power_personagem` detecta sozinho que a personagem ocupa um slot
        de Waifu via `favoritas_ocupantes` (parte do `contexto_lote`) e usa
        o Power Base efetivo do slot em vez do natural; "CP base" continua
        mostrando o natural (antes de qualquer investimento no slot), pra
        comparar os dois."""
        options = []
        for indice, item in enumerate(self._slots):
            if item["personagem"]:
                texto, emoji = _descricao_personagem_dropdown(item["personagem"], self.guild_id, self.user_id, self._contexto_lote) if item["adquirida"] else ("🎯 Alvo dos rolls da Wishlist", "🎯")
                # 🔥 Power Atual (do SLOT, não o CP da descrição abaixo) DEPOIS
                # do nome, entre parênteses (2026-09-06, correção do usuário:
                # "valor era p ser igual antes Slot N: <Nome> (Power <Power
                # Atual>)" - a tentativa anterior tinha posto o número ANTES
                # do nome, formato errado) - mesmo formato de sempre, com o
                # 💞 de Soulmate na frente do nome (não do número).
                prefixo_soulmate = "💞 " if item["personagem"].get("is_soulmate") else ""
                estado = "🎴 " if item["adquirida"] else "🎯 "
                poder = f" (Power {_fmt_numero(item['power_atual'])})" if item["adquirida"] else ""
                rotulo = f"{estado}Slot {item['slot']}: {prefixo_soulmate}{item['personagem']['nome']}{poder}"
            else:
                texto, emoji = None, None
                rotulo = f"Slot {item['slot']} (vazio)"
            options.append(discord.SelectOption(
                label=rotulo[:100], value=str(indice), description=texto[:100] if texto else None, emoji=emoji,
                default=(indice == self._indice),
            ))
        select = discord.ui.Select(placeholder="💖 Ir direto pro slot...", options=options, row=0)
        select.callback = self._selecionou_slot
        self.add_item(select)

    async def _selecionou_slot(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        self._indice = int(interaction.data["values"][0])
        self._montar_botoes()
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    def montar_embed(self):
        item = self._item
        if not item["personagem"]:
            embed = discord.Embed(title=f"💖 Wishlist #{item['slot']}", color=0xE91E63)
            embed.description = "Slot vazio - escolha uma personagem para virar alvo dos seus rolls."
        else:
            p = item["personagem"]
            # 🔥 Card completo reaproveitado (2026-09-06, pedido do usuário:
            # "Na tela das waifus, quero ver as imagens das personagens
            # tbm, com as classes e tudo") - `consulta.embed_carta_
            # personagem` já monta imagem/classe/série/vínculo (mesmo card
            # do "🔍 Personagem"); antes este embed era construído do zero,
            # sem nenhum dos dois. Só o título/cor viram os do slot de
            # Waifu por cima.
            embed = consulta.embed_carta_personagem(p)
            estado = "🎴 Adquirida — Fortalecimento e Ascensão disponíveis." if item["adquirida"] else "🎯 Ainda não adquirida — alvo dos seus rolls de Wishlist."
            embed.title = f"💖 Wishlist #{item['slot']} - {p['nome']}"
            embed.color = 0xE91E63
            embed.description = estado
            if item["adquirida"]:
                embed.add_field(name="Power natural", value=_fmt_numero(item["power_natural"]), inline=True)
                embed.add_field(name="Power atual", value=_fmt_numero(item["power_atual"]), inline=True)
            if item["adquirida"] and item["proximo_fortalecimento"]:
                lo, hi = item["proximo_fortalecimento"]["patamar"]
                custo = item["proximo_fortalecimento"]["custo"]
                embed.add_field(
                    name="Próximo Fortalecimento", value=f"{lo} → {hi}\nCusto: {_fmt_numero(custo)} Soulstones", inline=False,
                )
            elif item["adquirida"]:
                req = item["requisitos_ascensao"]
                checklist = (
                    f"Nível máximo: {'✅' if req['nivel_max'] else '❌'}\n"
                    f"Afinidade máxima: {'✅' if req['afinidade_max'] else '❌'}\n"
                    f"Soulmate: {'✅' if req['soulmate'] else '❌'}"
                )
                embed.add_field(name="Requisitos de Ascensão", value=checklist, inline=False)
                if item["elegivel_ascensao"]:
                    proxima = item["proxima_ascensao"]
                    base = int(item["power_atual"])
                    embed.add_field(
                        name="Próxima Ascensão",
                        value=f"{base} → {base + personagens_favoritas.BONUS_POWER_POR_ASCENSAO}\nCusto: {_fmt_numero(proxima['custo'])} Soulstones",
                        inline=False,
                    )
        # 🔥 Indicador de posição "X/Y" (2026-09-06, mesmo espírito do
        # "43/1200" de "🔍 Personagem") - aqui Y é sempre pequeno (no
        # máximo `SLOTS_MAXIMO`), nunca precisa de paginação em bloco.
        embed.set_footer(text=f"{self._indice + 1}/{len(self._slots)}")
        return embed

    async def _somente_autor(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("Esse painel não é seu.", ephemeral=True)
            return False
        return True

    async def _navegar_anterior(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        self._indice = max(0, self._indice - 1)
        self._montar_botoes()
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    async def _navegar_proximo(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        self._indice = min(len(self._slots) - 1, self._indice + 1)
        self._montar_botoes()
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    async def _fortalecer(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        item = self._item
        slot = item["slot"]
        indice_proximo = item["proximo_fortalecimento"]["indice"]
        ultimo_indice = len(personagens_favoritas.PATAMARES_FORTALECIMENTO) - 1
        saldo = await asyncio.to_thread(db.saldo_soulstone, self.guild_id, interaction.user.id)

        def _rotulo_opcao(indice_alvo):
            _lo, hi = personagens_favoritas.PATAMARES_FORTALECIMENTO[indice_alvo]
            return f"Fortalecer até {hi}"

        async def _confirmar(interacao_confirmacao, indice_alvo):
            ok, mensagem = await asyncio.to_thread(
                personagens_favoritas.fortalecer_ate, self.guild_id, interacao_confirmacao.user.id, slot, indice_alvo,
            )
            if ok:
                await self._atualizar()
            # 🔥 Sempre volta pro card principal (mesmo em falha) - mesmo
            # padrão de `_ascender`/`_esvaziar` - nunca deixa o dropdown de
            # confirmação como beco sem saída.
            await interacao_confirmacao.response.edit_message(embed=self.montar_embed(), view=self)
            await interacao_confirmacao.followup.send(mensagem, ephemeral=True)

        async def _cancelar(interacao_cancelamento):
            await interacao_cancelamento.response.edit_message(embed=self.montar_embed(), view=self)

        view_escolher = _ViewEscolherAlvo(
            "Fortalecimento", indice_proximo - 1, ultimo_indice,
            lambda indice_alvo: personagens_favoritas.custo_fortalecer_ate(indice_proximo, indice_alvo),
            "Soulstone", _confirmar, _cancelar, saldo_atual=saldo,
            rotulo_opcao_fn=_rotulo_opcao, unidade_degrau="patamar",
        )
        await interaction.response.edit_message(embed=self.montar_embed(), view=view_escolher)

    async def _ascender(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        item = self._item
        slot = item["slot"]
        nivel_atual = item["proxima_ascensao"]["nivel"] - 1
        saldo = await asyncio.to_thread(db.saldo_soulstone, self.guild_id, interaction.user.id)

        def _rotulo_opcao(nivel_alvo):
            return f"Ascender até {nivel_alvo}"

        async def _confirmar(interacao_confirmacao, nivel_alvo):
            ok, mensagem = await asyncio.to_thread(
                personagens_favoritas.ascender_ate,
                self.guild_id, interacao_confirmacao.user.id, slot, nivel_alvo,
            )
            if ok:
                await self._atualizar()
            await interacao_confirmacao.response.edit_message(embed=self.montar_embed(), view=self)
            await interacao_confirmacao.followup.send(mensagem, ephemeral=True)

        async def _cancelar(interacao_cancelamento):
            await interacao_cancelamento.response.edit_message(embed=self.montar_embed(), view=self)

        view_escolher = _ViewEscolherAlvo(
            "Ascensão", nivel_atual, nivel_atual + 25,
            lambda nivel_alvo: personagens_favoritas.custo_ascender_ate(nivel_atual, nivel_alvo),
            "Soulstone", _confirmar, _cancelar, saldo_atual=saldo,
            rotulo_opcao_fn=_rotulo_opcao, unidade_degrau="ascensão",
        )
        await interaction.response.edit_message(embed=self.montar_embed(), view=view_escolher)

    async def _trocar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        # 🔥 mesmo formato de dropdown do Party/Merge/"🔍 Personagem"
        # (2026-09-06, pedido do usuário: "os de personagem tem q ser igual
        # do party") - antes caía no fallback simples (`#id · estrelas`) por
        # não passar `descricao=` nenhum pro Modal de busca.
        slot = self._item["slot"]

        # 🔥 3 parâmetros, não 2 (achado do usuário: "gaia nao responde" ao
        # selecionar) - `_ModalBuscarPersonagem.on_submit` sempre chama
        # `ao_selecionar` com `(interacao, personagens, candidatos)` - o
        # pool INTEIRO da busca vai como 3º argumento (2026-08-30, "quero q
        # o dropdown de selecionar personagem nao suma ao escolher um"),
        # nunca só 2. Sem o 3º parâmetro aqui, toda seleção estourava
        # `TypeError` dentro do callback do discord.py - engolido em
        # silêncio pela lib, nunca gerando resposta nenhuma (mesmo padrão
        # de `_usar_protecao` acima, que já recebe e ignora esse 3º
        # argumento com `_candidatos`).
        async def _ao_selecionar(interacao_sel, personagens, _candidatos):
            ok, mensagem = await asyncio.to_thread(
                personagens_favoritas.definir_personagem, self.guild_id, interacao_sel.user.id, slot, personagens[0]["id"],
            )
            if ok:
                await self._atualizar()
                await interacao_sel.response.edit_message(embed=self.montar_embed(), view=self)
                await interacao_sel.followup.send(mensagem, ephemeral=True)
            else:
                await interacao_sel.response.edit_message(content=mensagem, embed=None, view=None)

        modal = _ModalBuscarCatalogoWishlist(f"Wishlist - Slot {slot}", _ao_selecionar)
        await interaction.response.send_modal(modal)

    async def _esvaziar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        await interaction.response.defer()
        _ok, mensagem = await asyncio.to_thread(
            personagens_favoritas.definir_personagem, self.guild_id, interaction.user.id, self._item["slot"], None,
        )
        await self._atualizar()
        await interaction.edit_original_response(embed=self.montar_embed(), view=self)
        await interaction.followup.send(mensagem, ephemeral=True)

    async def _comprar_slot(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        await interaction.response.defer()
        ok, mensagem = await asyncio.to_thread(db.comprar_slot_personagem_favorita, self.guild_id, interaction.user.id)
        if not ok:
            await interaction.followup.send(mensagem, ephemeral=True)
            return
        await self._atualizar()
        await interaction.edit_original_response(embed=self.montar_embed(), view=self)
        await interaction.followup.send(mensagem, ephemeral=True)
