# -*- coding: utf-8 -*-
"""Coleção (`ViewColecaoHub`) e Wishlist (`ViewWishlistHub`).

Parte de `pandora.paineis` (dividido por tela em 2026-11-10); de fora do
pacote, continuar usando `from pandora import paineis` e `paineis.<nome>`."""
import asyncio
import discord
from pandora import db
from pandora import cidade, consulta, gacha, series_favoritas, torre
from pandora.ui_base import ModalPandora, ViewPandora
from pandora.paineis.comum import (
    _COR_HUB,
    _MODOS_COLECAO,
    _ViewConfirmar,
    _ViewEscolherAlvo,
    _descricao_personagem_dropdown,
    _fmt_numero,
)
from pandora.paineis.personagem import (
    _sufixo_aviso_sem_classe,
)


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
        Personagem, mesma causa aqui) - `__init__` de uma `ViewPandora`
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
        return f"{icone} - {consulta.linha_personagem(personagem)} · CP {_fmt_numero(power)}"

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


class ViewWishlistHub(ViewPandora):
    """Navegador de Wishlist (2026-09-03, pedido do usuário: "A wishlist
    tem q ser igual a tela de personagem, mostrando imagem e com os msm
    botoes") - MESMO card (`consulta.embed_carta_personagem`) + navegação
    por posição/bloco/busca do "🔍 Personagem" (`_ViewNivel`), agora sobre
    a lista da Wishlist (favoritos, tabela `colecao_favoritas`) em vez da
    coleção inteira. Como a Wishlist aceita personagem NÃO possuída desde
    a fusão Favoritos+Wishlist, cada card ganha os mesmos 3 ESTADOS de
    posse do navegador de Série (`_ViewNavegarSerie`): 🛒 Livre (botão
    "Comprar" habilitado, `gacha.comprar_com_revelacao`), ✅ Já é sua (Upar
    Nível/Afinidade/Divorciar habilitados, mesmo fluxo de `_ViewNivel`) ou
    🔒 De outro jogador (só "Desfavoritar"/"Atualizar" continuam ativos).
    "Desfavoritar" aqui NUNCA alterna pra "Favoritar" - tudo mostrado
    nesta tela já está na Wishlist por definição, só sai dela.

    A lista inteira já vem carregada de 1 vez (`db.wishlist_listar` não
    usa `OFFSET`/`LIMIT` - Wishlist é curada à mão pelo jogador, nunca do
    tamanho da coleção inteira) - só FATIADA em blocos de 25 pro select
    (mesmo teto de sempre); cada navegação (`_ir_para`) recarrega a lista
    inteira do banco de novo (barato) pra refletir qualquer adição/
    remoção feita fora dessa tela enquanto ela estava aberta.

    Lista vazia NUNCA fecha a tela (diferente de `_ViewNivel.criar`, que
    devolve `None` se a coleção estiver vazia) - "➕ Adicionar" continua
    disponível, é o único jeito de colocar a 1ª personagem."""

    @classmethod
    async def criar(cls, guild_id, autor_id, indice=0):
        """Fábrica assíncrona (View nunca pode ser construída dentro de um
        `to_thread`, mesmo motivo de `_ViewNivel.criar`)."""
        personagens = await asyncio.to_thread(db.wishlist_listar, guild_id, autor_id)
        return cls(guild_id, autor_id, personagens, indice)

    def __init__(self, guild_id, autor_id, personagens, indice=0):
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        self._personagens = personagens
        self._indice = max(0, min(len(personagens) - 1, indice)) if personagens else 0
        self._bloco_offset = (self._indice // 25) * 25
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

        self._botao_comprar = discord.ui.Button(label="Comprar", emoji="🛒", style=discord.ButtonStyle.success, row=3)
        self._botao_comprar.callback = self._comprar
        self.add_item(self._botao_comprar)
        self._botao_adicionar = discord.ui.Button(label="Adicionar", emoji="➕", style=discord.ButtonStyle.secondary, row=3)
        self._botao_adicionar.callback = self._abrir_modal_adicionar
        self.add_item(self._botao_adicionar)

        self._atualizar_select_options()

    @property
    def personagem(self):
        return self._personagens[self._indice] if self._personagens else None

    async def _somente_autor(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.autor_id:
            await interaction.response.send_message("Essa Wishlist não é sua.", ephemeral=True)
            return False
        return True

    def _atualizar_select_options(self):
        if not self._personagens:
            self._select.options = [discord.SelectOption(label="-", value="0")]
            self._select.placeholder = "Wishlist vazia..."
            return
        contexto_lote = torre._contexto_lote(self.guild_id, self.autor_id)
        bloco = self._personagens[self._bloco_offset:self._bloco_offset + 25]
        options = []
        for indice, p in enumerate(bloco):
            texto, emoji = _descricao_personagem_dropdown(p, self.guild_id, self.autor_id, contexto_lote)
            posicao_absoluta = self._bloco_offset + indice + 1
            options.append(discord.SelectOption(
                label=f"{posicao_absoluta}. {p['nome']}"[:100], description=texto[:100], value=str(indice),
                emoji=emoji, default=(self._bloco_offset + indice == self._indice),
            ))
        self._select.options = options
        self._select.placeholder = f"🔄 Trocar de personagem (bloco {self._bloco_offset + 1}-{self._bloco_offset + len(bloco)})..."

    async def _ir_para(self, indice_alvo):
        """Núcleo de TODA navegação - recarrega a Wishlist INTEIRA do
        banco a cada passo (barato, é curada à mão, nunca do tamanho da
        coleção completa), pra refletir qualquer adição/remoção feita
        fora dessa tela enquanto ela estava aberta. `False` só se a
        Wishlist ficou vazia."""
        personagens = await asyncio.to_thread(db.wishlist_listar, self.guild_id, self.autor_id)
        self._personagens = personagens
        if not personagens:
            self._indice = 0
            self._bloco_offset = 0
            self._atualizar_select_options()
            return False
        self._indice = max(0, min(len(personagens) - 1, indice_alvo))
        self._bloco_offset = (self._indice // 25) * 25
        self._status = None
        self._atualizar_select_options()
        return True

    async def _renderizar(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    async def _trocar_personagem(self, interaction: discord.Interaction):
        await self._ir_para(self._bloco_offset + int(interaction.data["values"][0]))
        await self._renderizar(interaction)

    async def _navegar_anterior(self, interaction: discord.Interaction):
        await self._ir_para(self._indice - 1)
        await self._renderizar(interaction)

    async def _navegar_proximo(self, interaction: discord.Interaction):
        await self._ir_para(self._indice + 1)
        await self._renderizar(interaction)

    async def _ir_bloco_anterior(self, interaction: discord.Interaction):
        await self._ir_para(max(0, self._bloco_offset - 25))
        await self._renderizar(interaction)

    async def _ir_bloco_seguinte(self, interaction: discord.Interaction):
        await self._ir_para(self._bloco_offset + 25)
        await self._renderizar(interaction)

    async def _abrir_busca(self, interaction: discord.Interaction):
        await interaction.response.send_modal(_ModalBuscarPosicaoOuNomeWishlist(self))

    async def _abrir_modal_adicionar(self, interaction: discord.Interaction):
        if not await self._somente_autor(interaction):
            return
        await interaction.response.send_modal(_ModalAdicionarWishlist(self))

    def montar_embed(self):
        self._botao_adicionar.disabled = False
        if not self._personagens:
            for botao in (
                self._botao_anterior, self._botao_proximo, self._botao_bloco_anterior, self._botao_bloco_seguinte,
                self._botao_buscar, self._botao_comprar, self.upar, self.upar_afinidade, self.favoritar, self.divorciar,
            ):
                botao.disabled = True
            self._select.disabled = True
            return discord.Embed(
                title="⭐ Seus Favoritos", color=_COR_HUB,
                description=(self._status + "\n\n" if self._status else "") + "Vazia - use ➕ Adicionar pra colocar a 1ª personagem.",
            )
        self._select.disabled = False
        self._botao_anterior.disabled = self._indice <= 0
        self._botao_proximo.disabled = self._indice >= len(self._personagens) - 1
        self._botao_bloco_anterior.disabled = self._bloco_offset <= 0
        self._botao_bloco_seguinte.disabled = self._bloco_offset + 25 >= len(self._personagens)
        personagem = self.personagem
        embed = consulta.embed_carta_personagem(personagem)
        embed.set_footer(text=f"{self._indice + 1}/{len(self._personagens)} · Favoritos")
        self.favoritar.label = "Desfavoritar"
        self.favoritar.style = discord.ButtonStyle.success
        dono_id = personagem.get("dono_id")
        if dono_id is None:
            preco = db.PRECOS_LOJA[personagem["raridade"]]
            embed.add_field(name="Status", value=f"🛒 Disponível - {_fmt_numero(preco)} WiShards", inline=True)
            self._botao_comprar.disabled = False
            self._botao_comprar.label = f"Comprar ({_fmt_numero(preco)})"
            self.upar.disabled = True
            self.upar_afinidade.disabled = True
            self.divorciar.disabled = True
        elif dono_id == self.autor_id:
            self._botao_comprar.disabled = True
            self._botao_comprar.label = "Já é sua"
            nivel_atual = db.nivel_personagem(self.guild_id, self.autor_id, personagem["id"])
            custo = db.custo_proximo_nivel(personagem["raridade"], nivel_atual)
            power, _nivel_ignorado, categoria = torre.power_personagem(personagem, self.guild_id, self.autor_id)
            embed.add_field(name="Status", value="✅ Já é sua", inline=True)
            embed.add_field(name="CP", value=f"{torre.icone_categoria(categoria)} {_fmt_numero(power)}", inline=True)
            if custo is None:
                embed.add_field(name="Nível", value=f"{nivel_atual} (máximo)", inline=True)
                self.upar.disabled = True
            else:
                embed.add_field(name="Nível", value=f"{nivel_atual} (próximo: {_fmt_numero(custo)} WiShards)", inline=True)
                self.upar.disabled = False
            afinidade_atual = db.afinidade(self.guild_id, self.autor_id, personagem["id"])
            custo_afinidade = db.custo_proximo_afinidade(afinidade_atual)
            if custo_afinidade is None:
                embed.add_field(name="Afinidade", value=f"{afinidade_atual} (máxima)", inline=True)
                self.upar_afinidade.disabled = True
            else:
                embed.add_field(name="Afinidade", value=f"{afinidade_atual} (próximo: {_fmt_numero(custo_afinidade)} Soulstone)", inline=True)
                self.upar_afinidade.disabled = False
            andares_vencidos = db.andares_vencidos_personagem(self.guild_id, self.autor_id, personagem["id"])
            if andares_vencidos:
                embed.add_field(name="🗼 Andares vencidos", value=_fmt_numero(andares_vencidos), inline=True)
            self.divorciar.disabled = False
        else:
            embed.add_field(name="Status", value=f"🔒 Possuída por <@{dono_id}>", inline=True)
            self._botao_comprar.disabled = True
            self._botao_comprar.label = "Indisponível"
            self.upar.disabled = True
            self.upar_afinidade.disabled = True
            self.divorciar.disabled = True
        if self._status:
            embed.description = self._status
        return embed

    @discord.ui.button(label="Upar Nível", emoji="⬆️", style=discord.ButtonStyle.success)
    async def upar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        """Mesmo dropdown de `_ViewNivel.upar` - `db.subir_nivel_ate` já
        soma o custo de TODOS os degraus até o alvo."""
        personagem = self.personagem
        nivel_atual = db.nivel_personagem(self.guild_id, self.autor_id, personagem["id"])
        raridade = personagem["raridade"]

        async def _confirmar(interacao_confirmacao, alvo):
            ok, mensagem = db.subir_nivel_ate(self.guild_id, interacao_confirmacao.user.id, personagem["id"], alvo)
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
        personagem = self.personagem
        afinidade_atual = db.afinidade(self.guild_id, self.autor_id, personagem["id"])

        async def _confirmar(interacao_confirmacao, alvo):
            ok, mensagem = db.subir_afinidade_ate(self.guild_id, interacao_confirmacao.user.id, personagem["id"], alvo)
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

    @discord.ui.button(label="Desfavoritar", emoji="⭐", style=discord.ButtonStyle.success)
    async def favoritar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        """SEMPRE remove - tudo mostrado nesta tela já está na Wishlist
        por definição, diferente do `favoritar` do "🔍 Personagem"/
        navegador de Série (esses alternam, porque podem mostrar
        personagem ainda não favoritada)."""
        personagem = self.personagem
        db.wishlist_remover(self.guild_id, self.autor_id, personagem["id"])
        nome = personagem["nome"]
        await self._ir_para(self._indice)
        self._status = f"Removida da Wishlist: **{nome}**."
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    @discord.ui.button(label="Divorciar", emoji="💔", style=discord.ButtonStyle.danger)
    async def divorciar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        """Sempre pede confirmação - tudo mostrado aqui já está
        favoritado/na Wishlist por definição (mesmo aviso que `_ViewNivel.
        divorciar` só mostra condicionalmente lá, aqui é sempre)."""
        async def _confirmar(interacao_confirmacao):
            await self._divorciar_de_verdade(interacao_confirmacao)

        async def _cancelar(interacao_cancelamento):
            await interacao_cancelamento.response.edit_message(embed=self.montar_embed(), view=self)

        embed_aviso = self.montar_embed()
        embed_aviso.description = "⚠️ Essa personagem está favoritada - tem certeza que quer divorciar mesmo assim?"
        view_confirmar = _ViewConfirmar(_confirmar, ao_cancelar=_cancelar)
        await interaction.response.edit_message(embed=embed_aviso, view=view_confirmar)

    @discord.ui.button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def atualizar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        await self._ir_para(self._indice)
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    async def _divorciar_de_verdade(self, interaction: discord.Interaction):
        personagem = self.personagem
        ok, recompensa, xp = db.divorciar(self.guild_id, personagem["id"], interaction.user.id)
        if ok:
            await asyncio.to_thread(cidade.atualizar_snapshot_bonus, self.guild_id, interaction.user.id)
            await asyncio.to_thread(series_favoritas.recalcular_bonus, self.guild_id, interaction.user.id)
            mensagem = f"💔 Personagem liberada da sua coleção - +{_fmt_numero(recompensa)} WiShards, +{_fmt_numero(xp)} XP de Progressão (Afinidade preservada, um resgate futuro continua com o vínculo)."
        else:
            mensagem = "Você não tem essa personagem nesse servidor."
        await interaction.response.edit_message(content=mensagem, embed=None, view=None)

    async def _comprar(self, interaction: discord.Interaction):
        """Mesmo `gacha.comprar_com_revelacao` do navegador de Série
        (`_ViewNavegarSerie._comprar`) - MESMA regra/preço/corrida da Loja
        de verdade, já revelando classe se for a 1ª vez que essa
        personagem é reivindicada em qualquer servidor."""
        personagem = self.personagem
        await interaction.response.defer()
        ok, mensagem, tem_classe = await gacha.comprar_com_revelacao(self.guild_id, personagem["id"], interaction.user)
        if ok:
            personagem["dono_id"] = str(interaction.user.id)
            mensagem += _sufixo_aviso_sem_classe(tem_classe)
        self._status = f"{'✅' if ok else '❌'} {mensagem}"
        await interaction.edit_original_response(embed=self.montar_embed(), view=self)


class _ModalBuscarPosicaoOuNomeWishlist(ModalPandora, title="Buscar personagem"):
    """"🔎 Buscar" da Wishlist (2026-09-03) - mesmo Modal de posição/nome
    de `_ModalBuscarPosicaoOuNomeSerie`, resolvendo posição dentro da
    Wishlist do jogador em vez do catálogo de uma série."""

    consulta_texto = discord.ui.TextInput(label="Nome ou posição (nº)", placeholder="Ex.: Megumin ou 5", max_length=100)

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
            personagens_atualizados = await asyncio.to_thread(db.wishlist_listar, self._view.guild_id, self._view.autor_id)
            melhores = consulta.buscar_por_nome(personagens_atualizados, texto, limite=1)
            if not melhores:
                await interaction.followup.send(f'Nenhuma personagem parecida com "{texto}" na sua Wishlist.', ephemeral=True)
                return
            alvo_id = melhores[0]["id"]
            indice_alvo = next(i for i, p in enumerate(personagens_atualizados) if p["id"] == alvo_id)
        ok = await self._view._ir_para(indice_alvo)
        if not ok:
            await interaction.followup.send("Sua Wishlist está vazia.", ephemeral=True)
            return
        if self._view._indice != indice_alvo:
            self._view._status = f"⚠️ Só existem {len(self._view._personagens)} personagem(ns) na sua Wishlist - mostrando a posição {self._view._indice + 1}."
        await interaction.edit_original_response(embed=self._view.montar_embed(), view=self._view)


class _ModalAdicionarWishlist(ModalPandora, title="Adicionar aos Favoritos/Wishlist"):
    """Campo único MULTI-LINHA (2026-09-01, pedido original da Wishlist:
    "alterar forma de adicionar wishlist por uma mais fácil e rápido p
    incluir mais de 1") - 1 nome por linha, processa todos numa submissão
    só. Único jeito de favoritar/wishlistar uma personagem que você AINDA
    NÃO possui (`db.wishlist_adicionar` não exige posse desde a fusão de
    2026-09-03) - pra quem já possui, o card "🔍 Personagem" continua mais
    rápido (é o "emote e botão fácil" que o usuário pediu pra manter)."""

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
        ultimo_id_adicionado = None
        for nome in linhas_nomes:
            resultados = await asyncio.to_thread(db.buscar_personagens, nome)
            if not resultados:
                nao_encontrados.append(nome)
            elif len(resultados) > 1:
                ambiguos.append(nome)
            else:
                ok, mensagem = await asyncio.to_thread(
                    db.wishlist_adicionar, self._view_wishlist.guild_id, interaction.user.id, resultados[0]["id"]
                )
                if ok:
                    adicionados.append(resultados[0]["nome"])
                    ultimo_id_adicionado = resultados[0]["id"]
                else:
                    nao_encontrados.append(f"{nome} ({mensagem})")

        partes = []
        if adicionados:
            partes.append(f"✅ Adicionados: {', '.join(adicionados)}")
        if ambiguos:
            partes.append(f"⚠️ Mais de 1 resultado (use `/favoritar` com #id): {', '.join(ambiguos)}")
        if nao_encontrados:
            partes.append(f"❌ Não encontrados: {', '.join(nao_encontrados)}")

        # 🔥 Reabre já em cima do último adicionado (2026-09-03, tela virou
        # card único - `wishlist_listar` ordena por popularidade, não por
        # ordem de inserção, então achar a posição de novo depois de
        # recarregar é o único jeito de saber onde ele caiu na lista).
        await self._view_wishlist._ir_para(0)
        if ultimo_id_adicionado is not None:
            for indice, p in enumerate(self._view_wishlist._personagens):
                if p["id"] == ultimo_id_adicionado:
                    await self._view_wishlist._ir_para(indice)
                    break
        self._view_wishlist._status = "\n".join(partes) if partes else None
        await interaction.response.edit_message(content=None, embed=self._view_wishlist.montar_embed(), view=self._view_wishlist)
