# -*- coding: utf-8 -*-
"""Batalha 5x5 (desafio, defesa, revelação, `SchedulerBatalha`) e World Boss.

Parte de `pandora.paineis` (dividido por tela em 2026-11-10); de fora do
pacote, continuar usando `from pandora import paineis` e `paineis.<nome>`."""
import asyncio
import json
import traceback
from datetime import datetime, timedelta, timezone
import discord
from discord.ext import tasks
from pandora import db
from pandora import batalha, gacha, torre, worldboss
from pandora.registro import log
from pandora.ui_base import ViewPandora
from pandora.paineis.comum import (
    _COR_HUB,
    _ModalBuscarPersonagem,
    _ViewConfirmar,
    _descricao_personagem_dropdown,
    _fmt_numero,
)
from pandora.paineis.loja import (
    _embed_batalha,
    _embed_resultado_final,
    _membro_ou_none,
)


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
    log.debug(f" [BATALHA] _resolver_e_revelar iniciado - desafio_id={desafio['id']}")
    try:
        ordem_a = json.loads(desafio["ordem_desafiante"])
        ordem_b = json.loads(desafio["ordem_defensor"])
        rodadas, _placar_final_a, _placar_final_b, vencedor = await asyncio.to_thread(
            batalha.resolver_rodadas, ordem_a, ordem_b,
        )
    except Exception:
        log.warning(" [BATALHA] !!! EXCEÇÃO dentro de _resolver_e_revelar (resolvendo rodadas) !!!")
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
            log.warning(f" [BATALHA] edit_original_response falhou (ignorado, comportamento já era esse): {erro_http}")
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
        f"Aposta em risco pro desafiante: **{_fmt_numero(desafio['aposta_wishards'])} WiShards**.\n"
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
    Roda só na instância "principal" (mesmo critério de `SchedulerWorldBoss`
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
                log.warning(f" [BATALHA] SchedulerBatalha falhou ao checar desafios expirados em {guild.id}: {e}")
                continue
            for desafio_id in ids:
                try:
                    await self._auto_resolver(desafio_id)
                except Exception as e:
                    log.warning(f" [BATALHA] SchedulerBatalha falhou ao auto-resolver desafio #{desafio_id}: {e}")

    async def _auto_resolver(self, desafio_id):
        desafio = await asyncio.to_thread(db.batalha_por_id, desafio_id)
        if desafio is None or desafio["status"] != "aguardando_defensor":
            return  # 🔥 alguém respondeu bem no meio do tick - nada a fazer
        formacao = await asyncio.to_thread(batalha.defesa_automatica_para_desafio, desafio_id)
        ok, erro, desafio_atualizado = await asyncio.to_thread(
            batalha.montar_defesa, desafio["guild_id"], desafio_id, desafio["defensor_id"], formacao,
        )
        if not ok:
            log.warning(f" [BATALHA] SchedulerBatalha - montar_defesa recusou o desafio #{desafio_id}: {erro}")
            return
        canal = self.client.get_channel(int(desafio["canal_id"])) if desafio["canal_id"] else None
        if canal is None:
            log.warning(f" [BATALHA] SchedulerBatalha resolveu o desafio #{desafio_id} por timeout, mas sem canal salvo pra anunciar.")
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
            log.warning(f" [BATALHA] SchedulerBatalha falhou ao anunciar o desafio #{desafio['id']}: {erro_http}")


class ViewBatalhaHub(ViewPandora):
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
        super().__init__(timeout=900)
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

class _ViewEscolherFormacaoBatalha(ViewPandora):
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
        super().__init__(timeout=900)
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


class _ViewEscolherAlvoBatalha(ViewPandora):
    """Passo 1 de "⚔️ Desafiar" - escolher o jogador-alvo via `discord.ui.
    UserSelect` (mesmo padrão de `_ViewEscolherAlvoTroca`); passo 2 é a
    busca por nome na coleção DELE (`_ModalBuscarPersonagem`, reaproveitado
    sem nenhuma mudança - já aceita qualquer coleção como parâmetro)."""

    def __init__(self, guild_id, autor_id):
        super().__init__(timeout=900)
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
        # 🔥 mesmo formato de dropdown do Party/Merge (2026-09-06, pedido do
        # usuário: "os de personagem tem q ser igual do party") - CP/Nível/
        # Afinidade são do ALVO (`alvo.id`), não de quem está desafiando.
        contexto_lote_alvo = await asyncio.to_thread(torre._contexto_lote, self.guild_id, alvo.id)
        modal = _ModalBuscarPersonagem(
            f"Desafiar {alvo.display_name} por quem?", colecao_alvo,
            "Escolha a personagem que você quer conquistar...", self._personagem_escolhida,
            descricao=lambda p: _descricao_personagem_dropdown(p, self.guild_id, alvo.id, contexto_lote_alvo),
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
                log.debug(f" [BATALHA] _confirmar (desafiar) iniciado - desafiante={interacao_confirmacao.user.id} alvo={alvo.id} (bot={alvo.bot}) personagem={personagem['id']}")
                try:
                    await interacao_confirmacao.response.defer()
                    log.debug(" [BATALHA] defer() OK")
                    canal_id = interacao_confirmacao.channel.id if interacao_confirmacao.channel else None
                    ok, erro, desafio_id = await asyncio.to_thread(
                        batalha.iniciar_desafio, guild_id, interacao_confirmacao.user.id, alvo.id, personagem["id"],
                        categorias_ordem, canal_id=canal_id,
                    )
                    log.warning(f" [BATALHA] iniciar_desafio -> ok={ok} erro={erro} desafio_id={desafio_id}")
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
                        log.debug(f" [BATALHA] auto-defesa (bot={alvo.bot}) - formação: {formacao_auto}")
                        ok_defesa, erro_defesa, desafio_atualizado = await asyncio.to_thread(
                            batalha.montar_defesa, guild_id, desafio_id, alvo.id, formacao_auto,
                        )
                        log.warning(f" [BATALHA] montar_defesa -> ok={ok_defesa} erro={erro_defesa}")
                        if not ok_defesa:
                            await interacao_confirmacao.edit_original_response(content=f"❌ {erro_defesa}", view=None)
                            return
                        log.debug(" [BATALHA] entrando em _resolver_e_revelar...")
                        await _resolver_e_revelar(interacao_confirmacao, desafio_atualizado)
                        log.debug(" [BATALHA] _resolver_e_revelar concluído.")
                        return
                    await interacao_confirmacao.edit_original_response(
                        content=(
                            f"⚔️ Desafio enviado! {_fmt_numero(aposta)} WiShards em risco - aguardando {alvo.mention} responder "
                            f"(acompanhe em `/pandora` -> ⚔️ PvP)."
                        ),
                        view=None,
                    )
                    await _anunciar_desafio(interacao_confirmacao.channel, guild_id, desafio_id, alvo.mention)
                    log.debug(" [BATALHA] desafio contra humano enviado com sucesso.")
                except Exception:
                    log.warning(" [BATALHA] !!! EXCEÇÃO dentro de _confirmar (desafiar) !!!")
                    traceback.print_exc()
                    try:
                        await interacao_confirmacao.edit_original_response(content="❌ Erro interno - já registrado no log.", view=None)
                    except Exception:
                        log.warning(" [BATALHA] (falhou até tentar avisar o usuário do erro - ver traceback acima)")

            async def _cancelar(interacao_cancelamento: discord.Interaction):
                await interacao_cancelamento.response.edit_message(content="Desafio cancelado.", view=None)

            view_confirmar = _ViewConfirmar(_confirmar, ao_cancelar=_cancelar)
            await interacao_formacao.response.edit_message(
                content=(
                    f"Desafiar {alvo.mention} por **{personagem['nome']}** ({gacha.estrelas_por_raridade(personagem['raridade'])}) - "
                    f"você arrisca **{_fmt_numero(aposta)} WiShards**, mas só paga de verdade se PERDER (vencer não custa nada, esses "
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

class _ViewWorldBossAuto(ViewPandora):
    """Preferência de Entrada Automática (Seção 8/9) - ephemeral, só quem
    abriu vê (não precisa de checagem de autor extra - já é pessoal por
    ser ephemeral)."""

    def __init__(self, guild_id, user_id, ativo, categorias):
        super().__init__(timeout=900)
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


class ViewWorldBossHub(ViewPandora):
    """Painel "🐉 World Boss" - sempre reconstrói o estado fresco do banco
    (mesmo padrão de `ViewBatalhaHub`) - restart-safe, nenhum turno/
    inscrição depende desta View específica sobreviver (o scheduler roda
    sozinho, isto aqui é só consulta+entrada). Botões de categoria são
    TOGGLE (Seção 5/6) - clicar de novo na mesma categoria remove ela do
    conjunto permitido."""

    def __init__(self, guild_id):
        super().__init__(timeout=900)
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
