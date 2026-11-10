# -*- coding: utf-8 -*-
"""Peças compartilhadas pelos painéis: cores, formatação de número, confirmações, dropdowns genéricos de personagem/alvo e modais de busca.

Parte de `pandora.paineis` (dividido por tela em 2026-11-10); de fora do
pacote, continuar usando `from pandora import paineis` e `paineis.<nome>`."""
import asyncio
import discord
from pandora import db
from pandora import cidade, consulta, economia, gacha, series_favoritas, torre
from pandora.ui_base import ModalPandora, ViewPandora

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


class _ViewConfirmarComprarTudo(ViewPandora):
    """Confirmação de "🛍️ Comprar Tudo" (2026-09-03, pedido do usuário:
    "qnd clico ele abre uma nova mensagem com o preço de tudo e o botão
    de confirmar") - mensagem NOVA e separada do card de navegação, com o
    total já calculado. Compra 1 por 1 sequencialmente via `gacha.
    comprar_com_revelacao` (MESMO claim+classe de sempre, "lembrando q
    esses botoes tem q fazer exatamente o claim, definir clsse e tudo") -
    sequencial (não paralelo) porque `db.reivindicar` já é atômico por
    personagem, sem necessidade de paralelizar, e sequencial deixa o
    resumo final simples de montar (sucesso/falha por item, sem condição
    de corrida entre elas mesmas).

    🔥 `view_serie` (2026-09-06, pedido do usuário: "tem como editar a
    própria mensagem já com as infos atualizadas apos essas ações?") - a
    confirmação continua numa mensagem separada (pedido original de
    2026-09-03, mantido - o preço total precisa aparecer ANTES de gastar
    nada), mas agora reedita o card do `_ViewNavegarSerie` original
    (`_reeditar_apos_acao_em_massa`) depois da compra, pra dono/CP não
    ficarem desatualizados até o jogador reabrir o navegador."""

    def __init__(self, guild_id, autor_id, serie, personagens_livres, view_serie=None):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.autor_id = str(autor_id)
        self.serie = serie
        self._personagens_livres = personagens_livres
        self._view_serie = view_serie

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
        compradas, falhas, sem_classe, gasto_total = [], [], [], 0
        for personagem in self._personagens_livres:
            ok, mensagem, tem_classe = await gacha.comprar_com_revelacao(self.guild_id, personagem["id"], interaction.user)
            if ok:
                compradas.append(personagem["nome"])
                gasto_total += db.PRECOS_LOJA[personagem["raridade"]]
                if not tem_classe:
                    sem_classe.append(personagem["nome"])
            else:
                falhas.append(f"{personagem['nome']}: {mensagem}")
        resumo = f"✅ Compradas {len(compradas)}/{len(self._personagens_livres)} personagem(ns) de **{self.serie}** por {_fmt_numero(gasto_total)} WiShards."
        # 🔥 Aviso de "sem classe" (2026-09-05, achado do usuário: "as
        # personagens compradas estão vindo sem classe") - "Comprar Tudo"
        # dispara 1 classificação por personagem SEQUENCIALMENTE, fácil
        # estourar a cota diária da Groq (~23 classificações reais/dia,
        # ver CHANGELOG) numa série grande - antes, a compra em si sempre
        # tinha sucesso e ninguém percebia a falta de classe até auditar
        # depois. `/pandora_admin validar_classes` (já existia) retenta.
        if sem_classe:
            resumo += f"\n⚠️ {len(sem_classe)}/{len(compradas)} sem classe ainda (GAIA sem cota/fora do ar) - `/pandora_admin validar_classes` tenta de novo depois."
        if falhas:
            resumo += "\n❌ " + "\n❌ ".join(falhas[:10])
            if len(falhas) > 10:
                resumo += f"\n... e mais {len(falhas) - 10} falha(s)."
        await interaction.edit_original_response(content=resumo, view=None)
        if self._view_serie is not None:
            await self._view_serie._reeditar_apos_acao_em_massa()

    @discord.ui.button(label="Cancelar", emoji="❌", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        if not await self._somente_autor(interaction):
            return
        await interaction.response.edit_message(content="Cancelado.", view=None)


class _ViewEscolherMergeAlvo(ViewPandora):
    """2º passo do Merge (2026-09-02, pedido do usuário: "5 da msm raridade
    por 1 da msm raridade disponivel, a escolha") - até 25 personagens
    LIVRES (`db.personagens_livres_por_raridade`, mesma fonte que a Loja
    usa pra "Comprar") da mesma raridade das 5 sacrificadas; `economia.
    executar_merge` só roda quando o jogador escolhe uma."""

    def __init__(self, guild_id, ids_sacrificio, estrelas, personagens, tipo_sacrificios=None):
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self._ids_sacrificio = ids_sacrificio
        self._personagens = personagens
        self._tipo_sacrificios = tipo_sacrificios

        def _opcao(indice, p):
            texto, emoji = _descricao_personagem_livre_dropdown(p)
            return discord.SelectOption(label=p["nome"][:100], description=texto, value=str(indice), emoji=emoji)

        select = discord.ui.Select(
            placeholder=f"Receber qual {estrelas}...",
            options=[_opcao(indice, p) for indice, p in enumerate(personagens)],
        )
        select.callback = self._escolher
        self.add_item(select)

    async def _escolher(self, interaction: discord.Interaction):
        escolhida = self._personagens[int(interaction.data["values"][0])]
        ok, mensagem = await asyncio.to_thread(
            economia.executar_merge, self.guild_id, interaction.user.id, self._ids_sacrificio, escolhida["id"],
        )
        if ok:
            if self._tipo_sacrificios:
                db.limpar_equipe(self.guild_id, interaction.user.id, self._tipo_sacrificios)
            # 🔥 `revelar_classe` (2026-09-03, achado do usuário: "Validar
            # Classes... se ao comprar pela colecao ta setando classe" -
            # `economia.executar_merge` reivindica direto via `db.
            # reivindicar`, sem passar pelo claim normal - mesmo gap já
            # corrigido na Loja/navegador de série (`gacha.
            # comprar_com_revelacao`), nunca corrigido aqui. Se a personagem
            # recebida no Merge nunca foi reivindicada em NENHUM servidor
            # antes, ela saía sem classe pra sempre.
            await gacha.revelar_classe(escolhida)
            # 🔥 `to_thread` (2026-09-01) - `atualizar_snapshot_bonus` escaneia
            # a coleção INTEIRA, mesma classe de bug "GAIA não respondeu a
            # tempo" já corrigida em Auto-Party/Cidade/Personagem (SQLite
            # síncrono bloquearia o event loop do bot inteiro sem isso).
            await asyncio.to_thread(cidade.atualizar_snapshot_bonus, self.guild_id, interaction.user.id)
            await asyncio.to_thread(series_favoritas.recalcular_bonus, self.guild_id, interaction.user.id)
        await interaction.response.edit_message(content=mensagem, view=None)


class _ViewEscolherRanking(ViewPandora):
    """Seletor de métrica pro `/ranking` (2026-09-02, "rankings expandidos"
    - Seção 25 do plano original) - Coleção/Soulmates/Torre, cada uma 1
    query barata de 1 tabela só (`db.ranking_guild`)."""

    def __init__(self, guild_id):
        super().__init__(timeout=900)
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
    categoria + classe + CP (final e base) + Nível + Afinidade (2026-08-30,
    pedido do usuário: "no dropdwon de ver personagem tem q informar o
    icone da classe, CP, lv e afinidade. Tem varios locais q repetem esse
    padrao, pq vc n esta usando 1 p tudo?") - ÚNICO ponto que monta esse
    texto no pacote inteiro, reaproveitado por TODO select que lista
    personagens possuídas ("🔍 Personagem"/"🔄 Trocar de personagem", Merge,
    Party Adicionar/Remover, Batalha, Proteção, Waifus) - trocar o formato
    aqui atualiza todos de uma vez, nunca precisa caçar duplicata de novo.

    🔥 Classe + "CP base" (2026-09-06, pedido do usuário: "os de personagem
    tem q ser igual do party, porem ainda falta acrescentar o CP base
    daquele personagem, q esta relacionado a mecanica de waifu" + "no
    dropdown tbm tem q mostrar a classe") - `torre.power_base(popularidade)`
    é o Power Base NATURAL antes de Nível/Afinidade/Soulmate/bônus (300 a
    1000, só a popularidade importa) - é o número que decide quanto do
    Fortalecimento de um slot de Waifu a personagem já cobre sozinha (ver
    `personagens_favoritas._estado_fortalecimento`), então é o dado que
    interessa na hora de escolher QUEM colocar num slot, separado do CP
    final (que já inclui todos os bônus de conta/classe/série).

    `contexto_lote` (opcional, de `torre._contexto_lote`) - evita N+1 de
    query ao montar uma LISTA inteira (até 25 opções): quem monta o select
    pré-carrega 1x e passa aqui, em vez de cada personagem abrir suas
    próprias conexões SQLite (mesmo problema já corrigido no Auto-Party)."""
    niveis, bonus_global, cache_classe, bonus_series, favoritas_ocupantes = contexto_lote or (None, None, None, None, None)
    nivel = niveis.get(personagem["id"], 1) if niveis is not None else None
    power, nivel_resolvido, categoria = torre.power_personagem(
        personagem, guild_id, user_id, nivel=nivel, bonus_global=bonus_global, cache_bonus_classe=cache_classe,
        bonus_series=bonus_series, favoritas_ocupantes=favoritas_ocupantes,
    )
    afinidade_atual = personagem.get("afinidade", 1)
    cp_base = torre.power_base(personagem["popularidade"])
    classe = personagem.get("classe_exibicao") or personagem.get("classe")
    classe_texto = f"{classe} · " if classe else ""
    texto = (
        f"#{personagem['id']} · {classe_texto}{gacha.estrelas_por_raridade(personagem['raridade'])} · "
        f"Nv.{nivel_resolvido} · CP {_fmt_numero(power)} (base {_fmt_numero(cp_base)}) · 💞{afinidade_atual}"
    )
    return texto, torre.icone_categoria(categoria)


def _descricao_personagem_livre_dropdown(personagem):
    """`(texto, emoji)` pra listas de personagens SEM dono ou de dono
    ALHEIO variável (Merge - escolher quem receber; Loja - "Comprar";
    Revanche - personagens perdidas, cada uma com um dono atual
    diferente) - versão mais simples de `_descricao_personagem_dropdown`
    acima, sem Nível/Afinidade (não fazem sentido sem UM dono fixo pra
    consultar), mas com a MESMA classe + CP base que o pedido do usuário
    (2026-09-06: "os de personagem tem q ser igual do party"... "no
    dropdown tbm tem q mostrar a classe") pede em qualquer select de
    personagem. `CP base` (`torre.power_base`) não depende de
    conta/vínculo nenhum, por isso funciona igual aqui."""
    cp_base = torre.power_base(personagem["popularidade"])
    classe = personagem.get("classe_exibicao") or personagem.get("classe")
    classe_texto = f"{classe} · " if classe else ""
    texto = f"#{personagem['id']} · {classe_texto}{gacha.estrelas_por_raridade(personagem['raridade'])} · CP base {_fmt_numero(cp_base)}"
    # 🔥 `categoria_personagem` é puro (só olha `personagem["classe"]`, sem
    # precisar de dono/vínculo nenhum) - dá pro ícone de categoria (⚔️/🛡️/✨)
    # aparecer igual ao Party mesmo em listas sem dono fixo.
    return texto[:100], torre.icone_categoria(torre.categoria_personagem(personagem))


class _ViewSelecionarPersonagem(ViewPandora):
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
        super().__init__(timeout=900)
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


class _ViewConfirmar(ViewPandora):
    """Sim/Não genérico - `ao_confirmar(interaction)` só roda no "Sim".
    `ao_cancelar` (opcional) roda no "Não" em vez do padrão (apagar a
    mensagem) - usado quando cancelar deve VOLTAR pra uma tela anterior
    (2026-08-30, ex.: Divorciar dentro do card "🔍 Personagem" - cancelar
    não pode apagar o card, tem que voltar pra ele)."""

    def __init__(self, ao_confirmar, ao_cancelar=None):
        super().__init__(timeout=300)
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


class _ViewEscolherAlvo(ViewPandora):
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
    passou a atualizar UM dos dois, o que a mensagem original tiver.

    🔥 "~X/nível" quando o alvo pula MAIS de 1 degrau (2026-09-04, pedido
    do usuário: "Pode deixar mais claro na tela" - achado investigando um
    relato de "preço errado": o Nv.340 custando 820k e o Nv.341 seguinte
    custando só 34k não é bug nenhum, `custo_total_fn` sempre soma TODOS
    os degraus de onde você está até o alvo - 820k era o preço de 25
    níveis de uma vez (316->340), 34k era 1 nível só (340->341), nunca deu
    pra comparar os dois. O rótulo "Custo total" sozinho não deixava isso
    óbvio - toda opção que pula mais de 1 nível agora também mostra
    quantos níveis estão inclusos e o custo médio de cada um.

    🔥 `rotulo_opcao_fn`/`unidade_degrau` (2026-09-06, Fortalecimento de
    Waifu - "por um dropdown igual nos outros locais") - generalizações
    MÍNIMAS pra caber um domínio de "degraus" que não são incrementos de 1
    unidade (Fortalecimento pula de 50 em 50, só 14 patamares no total, com
    label específico tipo "Fortalecer até 500") sem duplicar toda a lógica
    de custo acumulado/confirmação/preservação do embed que já existe
    aqui: `rotulo_opcao_fn(alvo)` troca o rótulo padrão `f"{rotulo} {alvo}"`
    por um customizado; `unidade_degrau` troca a palavra "nível" (ex.: pra
    "patamar"). Ambos opcionais - `None`/padrão mantém o comportamento de
    sempre pra Upar Nível/Afinidade/Loja/Construção, nenhum desses precisou
    mudar uma linha."""

    def __init__(
        self, rotulo, valor_atual, valor_maximo, custo_total_fn, unidade, ao_confirmar, ao_cancelar,
        saldo_atual=None, rotulo_opcao_fn=None, unidade_degrau="nível",
    ):
        super().__init__(timeout=900)
        # 🔥 Clamp de 25 opções (2026-09-07, achado ao implementar o degrau
        # de teto de Construção de 50 - `discord.ui.Select` aceita no
        # máximo 25 `SelectOption`, e até aqui todo caller ficava com uma
        # janela pequena (Nível/Afinidade de personagem = 10, Fortalecimento
        # = 14 patamares) - o teto de Construção agora pode abrir uma
        # janela de até 49 (área recém-destravada, ainda no nível 1, teto
        # 50), o 1º caso real que estourava o limite do Discord sem isso).
        # Corrigido AQUI (não em cada caller) - protege qualquer uso futuro
        # deste componente compartilhado, não só Construção.
        valor_maximo = min(valor_maximo, valor_atual + 25)
        self._custo_total_fn = custo_total_fn
        self._unidade = unidade
        self._unidade_degrau = unidade_degrau
        self._ao_confirmar = ao_confirmar
        self._ao_cancelar = ao_cancelar
        self._valor_atual = valor_atual
        rotulo_opcao_fn = rotulo_opcao_fn or (lambda alvo: f"{rotulo} {alvo}")
        options = [
            discord.SelectOption(
                label=rotulo_opcao_fn(alvo)[:100], value=str(alvo),
                description=self._descricao_opcao(valor_atual, alvo, unidade)[:100],
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

    def _descricao_opcao(self, valor_atual, alvo, unidade):
        custo = self._custo_total_fn(alvo)
        degraus = alvo - valor_atual
        if degraus <= 1:
            return f"Custo total: {_fmt_numero(custo)} {unidade}"
        return f"Custo total: {_fmt_numero(custo)} {unidade} ({degraus} {self._unidade_degrau}(s), ~{_fmt_numero(custo / degraus)}/{self._unidade_degrau})"

    async def _selecionou(self, interaction: discord.Interaction):
        alvo = int(interaction.data["values"][0])
        custo = self._custo_total_fn(alvo)
        degraus = alvo - self._valor_atual

        async def _confirmar(interacao_confirmacao):
            await self._ao_confirmar(interacao_confirmacao, alvo)

        view_confirmar = _ViewConfirmar(_confirmar, ao_cancelar=self._ao_cancelar)
        if degraus <= 1:
            texto = f"Ir até aqui custa **{_fmt_numero(custo)} {self._unidade}** - confirma?"
        else:
            texto = (
                f"Ir até aqui custa **{_fmt_numero(custo)} {self._unidade}** "
                f"({degraus} {self._unidade_degrau}(s), ~{_fmt_numero(custo / degraus)}/{self._unidade_degrau}) - confirma?"
            )
        embed_atual = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed_atual:
            embed_atual = embed_atual.copy()
            embed_atual.description = texto
            await interaction.response.edit_message(embed=embed_atual, view=view_confirmar)
        else:
            await interaction.response.edit_message(content=texto, view=view_confirmar)

    async def _cancelar_direto(self, interaction: discord.Interaction):
        await self._ao_cancelar(interaction)


class _ModalBuscarPersonagem(ModalPandora):
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


class _ModalBuscarCatalogoWishlist(ModalPandora):
    """Busca no catálogo para preencher um slot de Wishlist, possuída ou não."""

    nome = discord.ui.TextInput(label="Nome da personagem", placeholder="Ex.: Megumin", max_length=100)

    def __init__(self, titulo, ao_selecionar):
        super().__init__(title=titulo[:45])
        self._ao_selecionar = ao_selecionar

    async def on_submit(self, interaction: discord.Interaction):
        candidatos = await asyncio.to_thread(db.buscar_personagens, str(self.nome).strip(), 25)
        if not candidatos:
            await interaction.response.send_message(f'Nenhuma personagem parecida com "{self.nome}".', ephemeral=True)
            return

        async def _selecionar_com_pool(interacao_selecao, personagens):
            await self._ao_selecionar(interacao_selecao, personagens, candidatos)

        view = _ViewSelecionarPersonagem(candidatos, "Escolha a personagem...", _selecionar_com_pool)
        await interaction.response.edit_message(content="Selecione:", view=view)


class _ModalBuscarPosicaoOuNome(ModalPandora, title="Buscar personagem"):
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


# 🔥 Movido pra `db.fmt_numero` (2026-09-03, pedido do usuário: "separa
# por . as casas de todos os numeros") - camada mais baixa, importável
# por `itens.py`/`economia.py`/`gacha.py` também, sem import circular.
# Alias mantido aqui pra não precisar tocar as dezenas de chamadas já
# existentes neste arquivo.
_fmt_numero = db.fmt_numero


class _ViewFiltrarCategoria(ViewPandora):
    """Filtro de categoria de combate (2026-08-30, pedido do usuário: "na
    hora de adicionar, deixa selecionar a role p filtrar e ficar facil de
    preencher oq precisa") - passo extra só no fluxo de ADICIONAR da Party
    (Remover não precisa, a lista já é só quem tá lá dentro). `ao_filtrar
    (interaction, categoria_ou_None)` recebe `None` pra "Todas"."""

    def __init__(self, ao_filtrar):
        super().__init__(timeout=900)
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
