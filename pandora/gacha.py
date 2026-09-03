# -*- coding: utf-8 -*-
"""Motor de roll/claim do colecionador estilo Mudae (ver
PLANO_COLECAO_WAIFUS.md/ERIS_sistema_colecao_wishards.md) - separação
inspirada no `gacha.ts` do Fable (github.com/ker0olos/fable, MIT): aqui só
decide QUAL personagem sai e QUEM ganha o quê; consulta/coleção/wishlist
ficam em `eris/colecao/consulta.py`.

Diferença de propósito em relação ao Fable: lá a raridade é sorteada NA HORA
do roll e o mesmo personagem pode ter vários donos (duplicatas configuráveis
por guilda); aqui a raridade é uma característica FIXA do personagem (ver
`db.recalcular_raridade`) e o dono é único por (guild, personagem) - decisão
explícita do usuário, mais perto da Mudae original que do Fable.

🔥 Nenhum número de dificuldade é constante fixa aqui (2026-08-29, pedido do
usuário: "o certo seria tudo q definimos ali ser configurável") - rolls/
ciclo, claims/ciclo, duração do card e chance de wish-roll vêm de
`db.obter_configuracao_colecao(guild_id)`, ajustável por servidor via
`/colecao_admin` (ver `eris/bot.py`), com fallback pros defaults em
`db._CONFIG_COLECAO_PADRAO` quando o servidor nunca configurou nada.

🔥 Personagem já reivindicada volta a poder aparecer no roll (2026-08-29,
ERIS_sistema_colecao_wishards.md Seção 4: "continua podendo aparecer, pois
isso alimenta Afinidade e WiShards") - `_resolver_resultado` decide, logo
depois do sorteio, se é uma personagem LIVRE (fluxo de claim de sempre),
um REENCONTRO (quem rolou já é dono - Afinidade sobe, paga na hora) ou um
roll de personagem de TERCEIRO (o dono de verdade recebe metade do valor,
sem mudar Afinidade nem dar nada a quem rolou)."""
import asyncio
import json
import random
from datetime import datetime, timedelta, timezone

import discord

from pandora import cidade, db, gaia_webhook

# 🔥 Cards individuais com reação pra reivindicar, estilo Mudae (2026-08-29,
# pedido do usuário: "quero que cada personagem seja enviada em uma
# mensagem separada, e nela venha a opcao de reagir p pegar") - persistido
# em `db.colecao_cards_pendentes` (2026-08-29, pedido do usuário: "cria
# uma tabela com a msm logica dos colecoes disponiveis" - achado real: um
# restart do processo no meio da janela de 1h fazia perder o acesso a uma
# personagem já rolada, card ainda visível no canal mas sem dono de
# verdade nenhum jeito de reivindicar). Funções em `db.py`: `registrar_
# card_pendente`/`card_pendente_por_mensagem`/`remover_card_pendente`/
# `cards_pendentes` (essa última já filtra quem JÁ tem dono e limpa
# expirados sozinha, reset preguiçoso).

# 🔥 Único número que continua fixo - é limite TÉCNICO do Discord (máximo de
# embeds numa única mensagem), não uma escolha de dificuldade. Usado só pra
# limitar o parâmetro `quantidade` de `/wa`/`/ha`/`/ma` no `eris/bot.py`; o
# `max_rolls_por_comando` configurável por servidor nunca pode passar disso.
LIMITE_TECNICO_EMBEDS_POR_MENSAGEM = 10

# 🔥 Mesma distribuição 50/30/15/4/1% do `gacha.ts` do Fable - lá é a chance
# de cada RATING no momento do roll; aqui é a chance de sortear cada TIER
# fixo (ver `db._CORTES_RARIDADE`, que distribui o catálogo nessas mesmas
# proporções na importação). Isso é o formato do catálogo, não dificuldade
# ajustável por servidor - fica fixo.
_PESOS_RARIDADE = {1: 50, 2: 30, 3: 15, 4: 4, 5: 1}
_ESTRELAS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}


def estrelas_por_raridade(raridade):
    return _ESTRELAS.get(raridade, "?")

_GENEROS_POR_COMANDO = {
    "wa": ["feminino"],
    "ha": ["masculino"],
    "ma": None,  # None = qualquer gênero
}

_CORES_RARIDADE = {1: 0x95A5A6, 2: 0x2ECC71, 3: 0x3498DB, 4: 0x9B59B6, 5: 0xF1C40F}

# 🔥 Cor de embed EXCLUSIVA de Soulmate (2026-08-29, Prova de Soulmate) -
# some por cima da cor por raridade em qualquer card/embed dela (cosmético 1
# dos 4 fechados na revisão, "equivalente prático de moldura" já que o ERIS
# usa embed puro, sem asset de imagem renderizada).
_COR_SOULMATE = 0xFF69B4

# 🔥 Chance/pity da Prova de Soulmate POR RARIDADE (2026-08-29,
# ERIS_power_afinidade_soulmate_niveis.md, números validados numa revisão do
# usuário sobre uma proposta do GPT) - "chance" é a chance INICIAL (1ª
# tentativa), "incremento" soma a cada FALHA (chance = inicial +
# incremento × tentativas_ja_feitas), "pity" é a tentativa em que o sucesso
# vira GARANTIDO por um branch explícito (`tentar_prova_soulmate`) - o pity
# NÃO emerge sozinho da matemática (ex.: 5⭐ na tentativa 20 dá só 79%, não
# 100%), é uma rede de segurança contra azar extremo, não o caminho normal
# (a média esperada de tentativas fica entre ~2 pra 1⭐ e ~6,2 pra 5⭐).
_PROVA_SOULMATE_POR_RARIDADE = {
    1: {"chance": 0.35, "incremento": 0.15, "pity": 5},
    2: {"chance": 0.25, "incremento": 0.10, "pity": 7},
    3: {"chance": 0.15, "incremento": 0.07, "pity": 10},
    4: {"chance": 0.08, "incremento": 0.05, "pity": 14},
    5: {"chance": 0.03, "incremento": 0.04, "pity": 20},
}

# 🔥 Cooldown fixo da Prova (Seção 8 do documento original, mantido) - 1
# tentativa por HORA, por personagem (não é configurável por servidor, é
# uma regra de balanceamento da mecânica em si, diferente da dificuldade de
# roll/claim que É configurável).
_PROVA_SOULMATE_COOLDOWN_MINUTOS = 60

# 🔥 Bônus de chance por escolher a resposta "certa" na situação da Prova
# (2026-08-29, redesenho pedido pelo usuário via GPT depois de testar ao
# vivo: "acertar não garante Soulmate, mas melhora a chance daquela
# tentativa") - FIXO (não escala por raridade, de propósito - simplicidade
# antes de generalizar sem necessidade concreta), aplicado SÓ na tentativa
# atual (nunca persistido/somado à progressão base de `_PROVA_SOULMATE_
# POR_RARIDADE`) - escolher errado não penaliza, só não dá o bônus.
_BONUS_ESCOLHA_CORRETA_PROVA_SOULMATE = 0.10

# 🔥 Cor do botão de claim condizendo com a raridade (2026-08-29, pedido do
# usuário) - o Discord só tem 4 estilos fixos de botão (blurple/cinza/verde/
# vermelho, sem roxo nem dourado), então quem carrega a cor EXATA de
# `_CORES_RARIDADE` é o emoji colorido; o estilo do botão só aproxima o mais
# perto disponível (5 estrelas reaproveita o vermelho de 4, mas continua
# visualmente distinto pelo emoji dourado + contagem de estrelas no rótulo).
_EMOJI_RARIDADE = {1: "⚪", 2: "🟢", 3: "🔵", 4: "🟣", 5: "🟡"}
# 🔥 1 reação A MAIS por card "livre" (2026-09-01, pedido do usuário:
# "emoji para favoritar personagem qnd aparece no roll") - ⭐ SEMPRE
# reivindica a personagem igual a reação colorida de sempre, só que
# também favorita na hora. Fixo (não varia por raridade, ao contrário de
# `_EMOJI_RARIDADE`) - nunca colide com ela porque nenhuma raridade usa ⭐
# como emoji de claim.
#
# 🔥 Existia uma 2ª reação (🔄, claim + tag "trade") - REMOVIDA em
# 2026-09-01 (achado do usuário: "essa reação de atualizar q vc pos nos
# rolls é inutil" - 🔄 lia como "atualizar"/"recarregar", não como
# "trocar", e cada reação a mais é mais 1 chamada de rede por personagem
# no roll, ligado direto à queixa de velocidade de aparição). `TAG_TROCA`
# continua existindo só porque o filtro "🏷️ Marcadas pra troca" em
# Coleção (`paineis.py`) ainda mostra quem já foi marcado antes.
EMOJI_FAVORITAR = "⭐"
TAG_TROCA = "trade"
_ESTILO_BOTAO_RARIDADE = {
    1: discord.ButtonStyle.secondary,
    2: discord.ButtonStyle.success,
    3: discord.ButtonStyle.primary,
    4: discord.ButtonStyle.danger,
    5: discord.ButtonStyle.danger,
}


def _sortear_raridade_com_candidatos(guild_id, generos, permitir_nsfw, raridade_minima=None):
    """Sorteia o TIER primeiro (pesos fixos), depois um personagem dentro
    dele - se o tier sorteado não tiver candidato elegível (catálogo pequeno
    demais), cai pro próximo tier mais comum disponível (mesmo espírito do
    `fallbackPool()` do Fable). `raridade_minima` (Guaranteed Roll comprado
    na loja, ver `db.consumir_garantia`) restringe o sorteio do TIER aos
    tiers >= esse valor - se nenhum deles tiver candidato (catálogo raro
    demais pro filtro atual), cai pro sorteio normal sem garantia em vez de
    devolver vazio (proteção contra um Guaranteed Roll comprado virar
    "nada aconteceu")."""
    tiers_por_frequencia = sorted(_PESOS_RARIDADE, key=lambda t: _PESOS_RARIDADE[t], reverse=True)

    if raridade_minima:
        tiers_garantidos = [t for t in tiers_por_frequencia if t >= raridade_minima]
        for tier in sorted(tiers_garantidos):
            candidatos = db.candidatos_por_raridade(guild_id, tier, generos, permitir_nsfw)
            if candidatos:
                return random.choice(candidatos)
        # nenhum tier >= raridade_minima tinha candidato - cai pro sorteio normal

    tier_sorteado = random.choices(list(_PESOS_RARIDADE.keys()), weights=list(_PESOS_RARIDADE.values()), k=1)[0]
    ordem_fallback = [tier_sorteado] + [t for t in tiers_por_frequencia if t != tier_sorteado]
    for tier in ordem_fallback:
        candidatos = db.candidatos_por_raridade(guild_id, tier, generos, permitir_nsfw)
        if candidatos:
            return random.choice(candidatos)
    return None


def _sortear_um(guild_id, user_id, generos, permitir_nsfw, chance_wish_roll, raridade_minima=None):
    """Sorteia UM personagem (wish-roll ou raridade normal/garantida) - já
    pressupõe que o cooldown de roll já foi consumido por quem chamou (ver
    `rolar_varios`, que consome o LOTE inteiro de uma vez, não um por um).
    `raridade_minima` (Guaranteed Roll) PULA o wish-roll - uma garantia paga
    de verdade não deveria virar uma personagem da wishlist de raridade
    baixa só por sorte."""
    if raridade_minima is None and random.random() < chance_wish_roll:
        disponiveis = db.wishlist_disponiveis_no_guild(guild_id, user_id, permitir_nsfw)
        if disponiveis:
            return db.personagem_por_id(random.choice(disponiveis))

    personagem_id = _sortear_raridade_com_candidatos(guild_id, generos, permitir_nsfw, raridade_minima)
    return db.personagem_por_id(personagem_id) if personagem_id is not None else None


def _resolver_resultado(guild_id, user_id, personagem):
    """Depois de sortear uma personagem, decide o que ela REPRESENTA pra
    quem rolou (ver docstring do módulo) - "livre" segue pro fluxo normal de
    claim (`ViewClaimMultiplo`, com botão); "reencontro"/"terceiro" já saem
    daqui com a Afinidade/WiShards resolvidos, sem precisar de nenhum
    clique (`eris/bot.py`/`ViewClaimMultiplo` só não desenham botão pra
    esses)."""
    resultado = dict(personagem)
    valor_base = db.valor_base_wishards(personagem["raridade"])
    resultado["valor_base"] = valor_base

    dono_id = db.dono_do_personagem(guild_id, personagem["id"])
    if dono_id is None:
        resultado["resultado_tipo"] = "livre"
        return resultado

    resultado["dono_id"] = dono_id
    if str(dono_id) == str(user_id):
        # 🔥 3 ramos do reencontro (2026-08-30, Soulstone/Afinidade -
        # decisão do usuário: "Reencontro continua aumentando afinidade e
        # WiShards, é apenas outra forma de aumentar afinidade... o
        # soulmate final so vai ser possivel rodando a pesonagem. Se rodar
        # uma personagem ja no max, da 10 soulstones extra... seriam
        # copias apos o soulmate") - reencontro comum (Afinidade < 10)
        # continua IDÊNTICO a antes; os 2 ramos novos só existem quando a
        # Afinidade já está no teto.
        afinidade_anterior = db.afinidade(guild_id, user_id, personagem["id"])
        ja_soulmate = db.is_soulmate(guild_id, user_id, personagem["id"])
        if ja_soulmate:
            # "Cópia" pós-Soulmate - Afinidade não mexe mais (já no teto),
            # reencontro vira Soulstone extra em vez de tentar subir de novo.
            recompensa = valor_base * afinidade_anterior
            novo_saldo = db.creditar_wishards(guild_id, user_id, recompensa, "reencontro", personagem["nome"], str(personagem["id"]))
            soulstone_ganho = 10
            novo_saldo_soulstone = db.creditar_soulstone(
                guild_id, user_id, soulstone_ganho, "reencontro_copia", personagem["nome"], str(personagem["id"]),
            )
            resultado.update(
                resultado_tipo="reencontro_copia", afinidade_anterior=afinidade_anterior,
                afinidade=afinidade_anterior, recompensa=recompensa, saldo=novo_saldo,
                soulstone_ganho=soulstone_ganho, saldo_soulstone=novo_saldo_soulstone, is_soulmate=True,
            )
        elif afinidade_anterior >= 10:
            # 1ª vez encontrando ela já no teto - vira Soulmate AGORA
            # (substitui a "Prova de Soulmate" antiga como o jeito de
            # virar Soulmate - Soulstone NUNCA compra isso).
            db.tornar_soulmate(guild_id, user_id, personagem["id"])
            recompensa = valor_base * afinidade_anterior
            novo_saldo = db.creditar_wishards(guild_id, user_id, recompensa, "reencontro", personagem["nome"], str(personagem["id"]))
            resultado.update(
                resultado_tipo="reencontro_soulmate", afinidade_anterior=afinidade_anterior,
                afinidade=afinidade_anterior, recompensa=recompensa, saldo=novo_saldo, is_soulmate=True,
            )
        else:
            nova_afinidade = db.incrementar_afinidade(guild_id, user_id, personagem["id"])
            recompensa = valor_base * nova_afinidade
            novo_saldo = db.creditar_wishards(guild_id, user_id, recompensa, "reencontro", personagem["nome"], str(personagem["id"]))
            resultado.update(
                resultado_tipo="reencontro", afinidade_anterior=afinidade_anterior,
                afinidade=nova_afinidade, recompensa=recompensa, saldo=novo_saldo, is_soulmate=False,
            )
    else:
        afinidade_dono = db.afinidade(guild_id, dono_id, personagem["id"])
        recompensa_dono = (valor_base * afinidade_dono) // 2
        db.creditar_wishards(guild_id, dono_id, recompensa_dono, "roll_terceiro", personagem["nome"], str(personagem["id"]))
        resultado.update(resultado_tipo="terceiro", recompensa_dono=recompensa_dono)
    return resultado


def _limite_rolls_atual(guild_id, user_id, config=None):
    """Quantos rolls o servidor + upgrade permanente da pessoa somam nesse
    ciclo - extraído (2026-08-29) pra ser reaproveitado por `rolar_varios`
    E por `enviar_resultados` (mostra "Puxada N/limite" no rodapé do card,
    pedido do usuário: "é p ser o numero q aquele roll representa dentre o
    limite atual do usuario ex 13/50"), sem duplicar a conta em 2
    lugares."""
    config = config or db.obter_configuracao_colecao(guild_id)
    # 🔥 Roll Permanente (2026-09-01, drop raro do World Boss OU compra na
    # Loja - contados SEPARADOS entre si, `db.bonus_permanente_total` soma
    # os 2) - bônus SEPARADO do upgrade pago acima, mas soma junto.
    bonus_rolls, _bonus_claims = db.bonus_permanente_total(guild_id, user_id)
    return config["rolls_por_ciclo"] + db.nivel_upgrade_rolls(guild_id, user_id) * db.BONUS_ROLLS_POR_NIVEL + bonus_rolls


def rolar_varios(guild_id, user_id, comando, quantidade=1):
    """`comando` em {"wa", "ha", "ma"}; `quantidade` é limitada pelo
    `max_rolls_por_comando` CONFIGURADO nesse servidor (nunca pelo limite
    técnico do Discord sozinho - ver `LIMITE_TECNICO_EMBEDS_POR_MENSAGEM`,
    que hoje só limita quantos embeds cabem numa mensagem COMBINADA, não
    mais o total de um comando - ver `enviar_resultados`) pra permitir uma
    "puxada" de várias personagens num comando só (pedido do usuário,
    2026-08-29 - "permitir dar 10 pulls de 1x"). Devolve (ok, lista_de_
    resultados_ou_erro) - quando `ok` é False, o 2º item já é um texto
    pronto pra mandar ao usuário. Nunca falha por pedir mais rolls do que
    sobra no ciclo - entrega quantos der (ver `db.consumir_rolls`), só
    falha de vez se não sobrar NENHUM.

    🔥 `quantidade <= 0` é sentinela pra "máximo disponível" (2026-08-29,
    pedido do usuário: "quero a opção de com 1 unico clique, rodar os
    maximo de rolls disponiveis"). Ignora `max_rolls_por_comando` DE
    PROPÓSITO nesse caso - esse teto é uma dificuldade POR COMANDO (evita
    puxadas grandes acidentais); pedir o máximo é uma ação EXPLÍCITA do
    jogador, não devia ficar preso num teto pensado pra outra coisa."""
    config = db.obter_configuracao_colecao(guild_id)
    limite_rolls = _limite_rolls_atual(guild_id, user_id, config)
    if quantidade <= 0:
        quantidade = limite_rolls
    else:
        quantidade = max(1, min(quantidade, config["max_rolls_por_comando"]))
    consumidos = db.consumir_rolls(guild_id, user_id, quantidade, limite_rolls, config["ciclo_rolls_minutos"])
    if consumidos == 0:
        segundos = db.tempo_restante(guild_id, user_id, "rolls_restantes", "rolls_resetam_em", limite_rolls, config["ciclo_rolls_minutos"])
        minutos = max(1, segundos // 60)
        return False, f"Você já usou seus {limite_rolls} rolls desse ciclo - tenta de novo em ~{minutos} min."
    # 🔥 Contador vitalício (2026-09-01, Conquistas do Colecionador,
    # "col_rolls") - só rolls de JOGADOR de verdade (`rolar_sem_cooldown`,
    # usado pelas contas de bot/NPC, nunca passa por aqui).
    db.incrementar_rolls_realizados(guild_id, user_id, consumidos)

    generos = _GENEROS_POR_COMANDO[comando]
    # 🔥 Guaranteed Roll (loja, Seção 12) - consumo ÚNICO, vale só pra 1ª
    # personagem sorteada nesse comando (mesmo numa puxada de várias); o
    # resto do lote segue o sorteio ponderado normal.
    raridade_minima = db.consumir_garantia(guild_id, user_id)
    resultados = []
    for indice in range(consumidos):
        personagem = _sortear_um(
            guild_id, user_id, generos, config["nsfw_permitido"], config["chance_wish_roll"],
            raridade_minima=raridade_minima if indice == 0 else None,
        )
        if personagem is not None:
            resultados.append(_resolver_resultado(guild_id, user_id, personagem))
    if not resultados:
        return False, "Não sobrou nenhum personagem elegível pra rolar nesse servidor agora."

    return True, resultados


def rolar_sem_cooldown(guild_id, user_id, quantidade, permitir_nsfw, chance_wish_roll):
    """Variante de `rolar_varios` pro auto-colecionador (`eris/colecao/
    auto_colecionador.py`, 2026-08-29) - NÃO consulta/consome cooldown nem
    respeita `max_rolls_por_comando`, porque não é um comando de jogador:
    é a conta do próprio bot rodando um número FIXO de tiros (não
    configurável por servidor, pedido explícito do usuário). Sempre
    qualquer gênero (não faz sentido preferência de gênero pra uma conta
    NPC). Devolve a lista de resultados já resolvidos (ver
    `_resolver_resultado`), sem filtrar por tipo - quem chama decide o que
    fazer com "livre"/"reencontro"/"terceiro"."""
    resultados = []
    for _ in range(quantidade):
        personagem = _sortear_um(guild_id, user_id, None, permitir_nsfw, chance_wish_roll)
        if personagem is not None:
            resultados.append(_resolver_resultado(guild_id, user_id, personagem))
    return resultados


def rolar(guild_id, user_id, comando):
    """Atalho pra um roll só - mantido pra quem só quer 1 personagem."""
    ok, resultado = rolar_varios(guild_id, user_id, comando, quantidade=1)
    if not ok:
        return False, resultado
    return True, resultado[0]


def _embed_base(personagem):
    embed = discord.Embed(
        title=personagem["nome"],
        description=(personagem.get("descricao") or "")[:500],
        color=_CORES_RARIDADE.get(personagem["raridade"], 0x2ECC71),
    )
    if personagem.get("serie"):
        embed.add_field(name="Série", value=personagem["serie"], inline=True)
    embed.add_field(name="Raridade", value=_ESTRELAS.get(personagem["raridade"], "?"), inline=True)
    if personagem.get("nsfw"):
        embed.add_field(name="Conteúdo", value="🔞 NSFW", inline=True)
    if personagem.get("imagem_url"):
        embed.set_image(url=personagem["imagem_url"])
    rodape = f"#{personagem['id']}"
    if personagem.get("nome_romanizado"):
        rodape += f" · {personagem['nome_romanizado']}"
    embed.set_footer(text=rodape)
    return embed


def montar_embed(resultado):
    """`resultado` vem de `rolar_varios` - já inclui `resultado_tipo`
    ("livre"/"reencontro"/"terceiro", ver `_resolver_resultado`). Só o
    "livre" ganha botão de reivindicar (`ViewClaimMultiplo`); os outros dois
    já chegam aqui com a recompensa resolvida, só falta mostrar."""
    tipo = resultado.get("resultado_tipo", "livre")
    if tipo in ("reencontro", "reencontro_soulmate", "reencontro_copia"):
        # 🔥 Formato igual ao da confirmação de reivindicação (2026-09-01,
        # pedido do usuário: "os rolls de personagens já coletados pode ser
        # no formato das mensagens de reinvidicação, so marque o dono") -
        # antes usava `_embed_base` (descrição/série/imagem GRANDE, igual um
        # roll novo); agora é compacto (thumbnail + campos), igual
        # `_embed_confirmacao_claim`, e marca o dono (`resultado["dono_id"]`
        # já é o próprio jogador que rolou, ver `_resolver_resultado`) -
        # antes o card não mencionava ninguém.
        cor = _COR_SOULMATE if tipo != "reencontro" else _CORES_RARIDADE.get(resultado["raridade"], 0x2ECC71)
        embed = discord.Embed(
            description=f"🔁 <@{resultado['dono_id']}> reencontrou **{resultado['nome']}**!",
            color=cor,
        )
        embed.add_field(name="Raridade", value=_ESTRELAS.get(resultado["raridade"], "?"), inline=True)
        classe = resultado.get("classe_exibicao") or resultado.get("classe")
        if classe:
            categoria_combate = db.categoria_combate_da_classe(resultado.get("classe"))
            sufixo = f" ({categoria_combate})" if categoria_combate else ""
            embed.add_field(name="Classe", value=f"{classe}{sufixo}", inline=True)
        if resultado.get("imagem_url"):
            embed.set_thumbnail(url=resultado["imagem_url"])
        # 🔥 3 ramos do reencontro (2026-08-30, Soulstone/Afinidade -
        # substitui a "Prova de Soulmate" antiga como o jeito de virar
        # Soulmate) - cor exclusiva de Soulmate (cosmético, já existia)
        # aparece nos 2 ramos onde `is_soulmate` é True.
        if tipo == "reencontro_copia":
            nome_campo = "✨ Cópia da sua Soulmate!"
            valor_campo = f"Afinidade {resultado['afinidade']} (máxima) · +{resultado['recompensa']} WiShards · +{resultado['soulstone_ganho']} Soulstone"
        elif tipo == "reencontro_soulmate":
            nome_campo = "💞 Virou sua Soulmate!"
            valor_campo = f"Afinidade {resultado['afinidade']} (máxima) · +{resultado['recompensa']} WiShards"
        else:
            nome_campo = "🔁 Reencontro!"
            valor_campo = f"Afinidade {resultado['afinidade_anterior']} → {resultado['afinidade']} · +{resultado['recompensa']} WiShards"
        embed.add_field(name=nome_campo, value=valor_campo, inline=False)
        return embed
    if tipo == "terceiro":
        # 🔥 Compacto, igual reencontro (2026-09-02, achado do usuário:
        # "ele rolou um personagem q outra pessoa tem, e n mostrou o card
        # resumido como o dos reinvidicado, como definimos antes") - o
        # pedido original ("rolls de personagens JÁ COLETADOS") também
        # cobria esse caso (já tem dono, só que de OUTRA pessoa), não só
        # reencontro (já tem dono, da MESMA pessoa que rolou) - ficou pra
        # trás na leva anterior, só reencontro foi reformatado. Mesmo
        # `_embed_base` grande (descrição/série/imagem GRANDE) que um roll
        # novo usava - agora thumbnail + campos, igual `_embed_confirmacao_
        # claim`/reencontro.
        embed = discord.Embed(
            description=f"👀 <@{resultado['dono_id']}> já tem **{resultado['nome']}**!",
            color=_CORES_RARIDADE.get(resultado["raridade"], 0x2ECC71),
        )
        embed.add_field(name="Raridade", value=_ESTRELAS.get(resultado["raridade"], "?"), inline=True)
        classe = resultado.get("classe_exibicao") or resultado.get("classe")
        if classe:
            categoria_combate = db.categoria_combate_da_classe(resultado.get("classe"))
            sufixo = f" ({categoria_combate})" if categoria_combate else ""
            embed.add_field(name="Classe", value=f"{classe}{sufixo}", inline=True)
        if resultado.get("imagem_url"):
            embed.set_thumbnail(url=resultado["imagem_url"])
        embed.add_field(
            name="🎁 Já tem dono",
            value=f"Pertence a <@{resultado['dono_id']}>, que ganhou {resultado['recompensa_dono']} WiShards.",
            inline=False,
        )
        return embed
    return _embed_base(resultado)


async def revelar_classe(personagem):
    """Classe/categoria de combate são "secretas" até a personagem ser
    reivindicada (2026-08-29, pedido do usuário) - nunca calculadas em
    lote, nunca mostradas no card do roll (`montar_embed`). Na 1ª
    reivindicação em QUALQUER servidor (por um humano OU pelo auto-
    colecionador, ver `eris/colecao/auto_colecionador.py`), pede pra GAIA
    classificar as duas JUNTAS (classe: taxonomia aberta, reaproveitando
    classes já usadas no catálogo quando fizer sentido; categoria de
    combate: sempre DPS/Tank/Support, Seção 16); reivindicações seguintes
    da MESMA personagem (outro servidor, ou depois de um divórcio) só
    reexibem o que já foi decidido, nunca pedem de novo. Devolve (classe_
    exibida, categoria_combate), ambos None se nunca foi decidido. Módulo-
    level (não método) desde 2026-08-29 - reaproveitado tanto por
    `ViewClaimMultiplo` (claim de humano) quanto pelo auto-colecionador.

    🔥 Canônica x exibição (2026-08-29, mesmo dia) - `classe` (gravada no
    banco, usada em `classes_existentes()`/estatísticas) é sempre a forma
    masculina/singular ("Ladino"), pra nunca fragmentar a taxonomia por
    gênero; `classe_exibicao` concorda com o gênero da personagem
    ("Ladina") e é o que ESTA FUNÇÃO devolve/usa em qualquer texto pro
    jogador - cai pra `classe` se a GAIA não devolver uma."""
    if personagem.get("classe"):
        # 🔥 `categoria_combate` NÃO mora mais em `colecao_personagens`
        # (2026-08-30, pedido do usuário: "ta salvando id delas e pondo
        # nos personagens?" - a coluna antiga era uma CÓPIA duplicada,
        # sincronizada só na escrita; sem a coluna, não tem como duas
        # personagens da MESMA classe divergirem de novo). Busca sempre
        # em `colecao_classes`, fonte ÚNICA de verdade.
        categoria_combate = await asyncio.to_thread(db.categoria_combate_da_classe, personagem["classe"])
        return personagem.get("classe_exibicao") or personagem["classe"], categoria_combate
    classes = await asyncio.to_thread(db.classes_existentes)
    resultado = await asyncio.to_thread(
        gaia_webhook.pedir_classe_personagem,
        personagem["nome"], personagem.get("descricao"), personagem.get("serie"),
        personagem["genero"], classes,
    )
    classe = resultado.get("classe")
    if not classe:
        return None, None
    classe_exibicao = resultado.get("classe_exibicao") or classe
    # 🔥 `definir_classe_personagem` devolve a categoria REALMENTE gravada
    # (a canônica de `colecao_classes`, se a classe já existia - nunca a
    # sugestão crua da GAIA pra este personagem específico).
    categoria_combate = await asyncio.to_thread(
        db.definir_classe_personagem, personagem["id"], classe, resultado.get("categoria_combate"), classe_exibicao,
        resultado.get("funcao_cidade"),
    )
    personagem["classe"] = classe
    personagem["classe_exibicao"] = classe_exibicao
    return classe_exibicao, categoria_combate


def _embed_confirmacao_claim(user, personagem, recompensa, novo_saldo, classe, categoria_combate):
    """1 única mensagem consolidando o que antes eram 2 followups separados
    (WiShards + classe) - pedido do usuário (2026-08-29): "é bom deixar
    claro que pegou, e a raridade da personagem. Tbm pode marcar a pessoa
    q pegou e unificar tudo relevante p ela em 1 unica mensagem"."""
    embed = discord.Embed(
        description=f"🎉 {user.mention} reivindicou **{personagem['nome']}**!",
        color=_CORES_RARIDADE.get(personagem["raridade"], 0x2ECC71),
    )
    embed.add_field(name="Raridade", value=_ESTRELAS.get(personagem["raridade"], "?"), inline=True)
    embed.add_field(name="WiShards", value=f"+{recompensa} (saldo: {novo_saldo})", inline=True)
    if classe:
        sufixo = f" ({categoria_combate})" if categoria_combate else ""
        embed.add_field(name="Classe", value=f"{classe}{sufixo}", inline=True)
    if personagem.get("imagem_url"):
        embed.set_thumbnail(url=personagem["imagem_url"])
    return embed


def _processar_claim_economia(guild_id, personagem, user):
    """Núcleo ECONÔMICO do claim (checagem de cooldown + claim atômico +
    WiShards/Afinidade/XP/marcos) - extraído de `_processar_claim`
    (2026-09-02, achado do usuário: "pq a logica do reinvindicar tudo
    demora? N da p otimizar?") - `gacha.reivindicar_em_massa` chama SÓ
    isso pra cada personagem, sequencialmente (tem que ser em ordem, o
    contador de claims é COMPARTILHADO entre elas), sem esperar
    `revelar_classe` (que pode ser uma chamada de REDE pra GAIA classificar
    - só acontece na 1ª reivindicação de uma personagem em QUALQUER
    servidor) de cada uma antes de passar pra próxima. Devolve (ok,
    erro_ou_None, recompensa_ou_None, novo_saldo_ou_None) - SÍNCRONA de
    propósito (nenhuma chamada de rede aqui dentro), quem chama de dentro
    de uma interação do Discord deve rodar em `asyncio.to_thread`."""
    config = db.obter_configuracao_colecao(guild_id)
    # 🔥 Upgrade permanente de claims (Seção 11, pago na loja, 2026-08-29 -
    # mesmo bônus PESSOAL somado em cima da config do SERVIDOR que já
    # existia pra rolls) - nunca substitui a config do servidor, só soma.
    # 🔥 Claim Permanente (2026-09-01, drop raro do World Boss OU compra na
    # Loja - contados separados entre si, `db.bonus_permanente_total` soma
    # os 2) - bônus SEPARADO do upgrade pago acima, soma junto.
    _bonus_rolls, bonus_claims = db.bonus_permanente_total(guild_id, user.id)
    limite_claims = (
        config["claims_por_ciclo"] + db.nivel_upgrade_claims(guild_id, user.id) * db.BONUS_CLAIMS_POR_NIVEL + bonus_claims
    )
    if db.claims_disponiveis(guild_id, user.id, limite_claims, config["ciclo_claims_minutos"]) <= 0:
        segundos = db.tempo_restante(
            guild_id, user.id, "claims_restantes", "claims_resetam_em",
            limite_claims, config["ciclo_claims_minutos"],
        )
        minutos = max(1, segundos // 60)
        return False, f"Você já usou seu claim desse ciclo - tenta de novo em ~{minutos} min.", None, None

    venceu = db.reivindicar(guild_id, personagem["id"], user.id)
    if not venceu:
        return False, "Alguém foi mais rápido - essa personagem já tem dono.", None, None

    db.consumir_claim(guild_id, user.id, limite_claims, config["ciclo_claims_minutos"])
    # 🔥 WiShards do claim inicial + Afinidade nasce em 1 (ERIS_sistema_
    # colecao_wishards.md Seções 4/7) - sempre feito ANTES do ack visual,
    # pra nunca existir um instante em que o claim "ganhou" mas ainda não
    # pagou nada.
    recompensa = db.valor_base_wishards(personagem["raridade"])
    novo_saldo = db.creditar_wishards(guild_id, user.id, recompensa, "claim", personagem["nome"], str(personagem["id"]))
    db.definir_afinidade_inicial(guild_id, user.id, personagem["id"])
    # 🔥 XP de Progressão (2026-08-30, análise do usuário Seção 4: "obter
    # personagens novas" é uma das fontes) + marcos de coleção única
    # (Seção 11) - checados JUNTO do claim, nunca em lote separado.
    db.creditar_xp_progressao(guild_id, user.id, personagem["raridade"] * 15)
    db.checar_marcos_colecao(guild_id, user.id)
    # 🔥 REMOVIDO (2026-09-01, achado do usuário: "os botões de claim,
    # tanto por botão qnt emoji, estão parando de responder ou demorando")
    # - `cidade.atualizar_snapshot_bonus` foi adicionado aqui na leva
    # anterior pra manter o bônus da Cidade sempre em dia, mas ele escaneia
    # a COLEÇÃO INTEIRA (`_workforce_por_funcao`) - rodar isso em TODO
    # claim (o caminho mais quente do jogo, muito mais frequente que Party/
    # Nível/Afinidade) trava a resposta do próprio claim pra quem tem
    # coleção grande (usuário citou "mesmo q tenha mais de 10k"). O bônus
    # da Cidade continua atualizando via Party/Upar Nível/Aumentar
    # Afinidade/Divorciar/Merge (`cidade.atualizar_snapshot_bonus` ainda
    # chamado nesses pontos, bem mais raros que um claim) - uma personagem
    # recém-reivindicada só entra no cálculo na PRÓXIMA dessas ações ou na
    # próxima visita à Cidade, atraso aceitável trocado por claim
    # instantâneo de novo.
    return True, None, recompensa, novo_saldo


async def _processar_claim(guild_id, personagem, user, ao_confirmar_economia=None):
    """Núcleo do claim (economia + classe) - compartilhado entre o botão
    (`ViewClaimMultiplo`) e a reação estilo Mudae (`processar_reacao_
    claim`), pra nunca duplicar essa lógica entre os dois caminhos.
    `ao_confirmar_economia` (opcional, async) roda logo depois do claim
    econômico confirmar (WiShards/Afinidade já creditados), ANTES de
    esperar a classificação de classe - dá pro chamador fazer o ack visual
    instantâneo (desabilitar botão, editar mensagem) sem esperar a GAIA
    responder (~1-2s). Devolve (ok, erro_ou_None, embed_ou_None)."""
    ok, erro, recompensa, novo_saldo = _processar_claim_economia(guild_id, personagem, user)
    if not ok:
        return False, erro, None

    if ao_confirmar_economia is not None:
        await ao_confirmar_economia()

    classe, categoria_combate = await revelar_classe(personagem)
    embed = _embed_confirmacao_claim(user, personagem, recompensa, novo_saldo, classe, categoria_combate)
    return True, None, embed


async def _claim_sem_cooldown(guild_id, personagem_id, user, origem_wishards):
    """Núcleo COMPARTILHADO de "dar uma personagem LIVRE pra alguém sem
    checar/consumir o cooldown normal de claims" (2026-08-30, extraído
    depois do usuário apontar retrabalho: "isso tao sendo geradas do
    mesmo codigo ne? ja falamos sobre retrabalho antes" - `atribuir_
    personagem_admin` (presente de admin) e o claim automático do
    auto-colecionador de CONTAS DE BOT, `AutoColecionador._reivindicar_
    melhor`, reimplementavam a MESMA sequência claim+WiShards+Afinidade+
    classe+embed cada um do seu jeito). MESMO fluxo econômico + revelação
    de classe de um claim normal (`_processar_claim`), só sem a checagem/
    consumo de cooldown de CLAIMS - nem admin nem conta de bot deviam
    gastar a cota normal de ninguém. `origem_wishards` é só o rótulo do
    ledger (diferencia "admin_atribuicao" de "auto_colecionador" nas
    estatísticas, nunca muda o comportamento). Devolve (ok, erro_ou_None,
    embed_ou_None) - mesmo formato de `_processar_claim`."""
    personagem = db.personagem_por_id(personagem_id)
    if personagem is None:
        return False, "Não achei nenhum personagem com esse #id.", None
    if not db.reivindicar(guild_id, personagem_id, user.id):
        return False, "Alguém pegou essa personagem nesse exato instante - tenta de novo.", None

    recompensa = db.valor_base_wishards(personagem["raridade"])
    novo_saldo = db.creditar_wishards(guild_id, user.id, recompensa, origem_wishards, personagem["nome"], str(personagem_id))
    db.definir_afinidade_inicial(guild_id, user.id, personagem_id)
    db.creditar_xp_progressao(guild_id, user.id, personagem["raridade"] * 15)
    db.checar_marcos_colecao(guild_id, user.id)

    classe, categoria_combate = await revelar_classe(personagem)
    embed = _embed_confirmacao_claim(user, personagem, recompensa, novo_saldo, classe, categoria_combate)
    return True, None, embed


async def atribuir_personagem_admin(guild_id, personagem_id, user):
    """Dá uma personagem LIVRE pra alguém direto (`/colecao_admin dar_
    personagem`, 2026-08-29) - reaproveita `_claim_sem_cooldown` (usuário:
    "soq sem descontar claim" - é presente do admin, não devia gastar a
    cota normal de ninguém). Único acréscimo aqui: recusa se a personagem
    já tiver dono (o auto-colecionador de contas de bot já filtra isso
    ANTES de chamar `_claim_sem_cooldown`, então essa checagem fica só
    onde é útil - `/colecao_admin` pode receber qualquer #id, inclusive de
    uma já reivindicada)."""
    if db.dono_do_personagem(guild_id, personagem_id) is not None:
        return False, "Essa personagem já tem dono nesse servidor.", None
    return await _claim_sem_cooldown(guild_id, personagem_id, user, "admin_atribuicao")


async def comprar_com_revelacao(guild_id, personagem_id, user):
    """Envelope de `db.comprar_personagem` que TAMBÉM revela classe
    (2026-09-03, pedido do usuário: "lembrando q esses botoes tem q fazer
    exatamente o claim, definir clsse e tudo") - sozinho, `db.
    comprar_personagem` nunca chamava `revelar_classe` (mesmo gap já
    achado no Merge antes, nunca corrigido pra Loja/navegador de série)
    - uma personagem NUNCA reivindicada em NENHUM servidor podia sair
    comprada sem classe pra sempre. Devolve `(ok, mensagem)` - MESMO
    formato de `db.comprar_personagem`, quem chama não precisa saber que
    teve um passo a mais."""
    ok, mensagem = await asyncio.to_thread(db.comprar_personagem, guild_id, user.id, personagem_id)
    if ok:
        personagem = await asyncio.to_thread(db.personagem_por_id, personagem_id)
        await revelar_classe(personagem)
    return ok, mensagem


def regra_prova_soulmate(raridade):
    """Regra (chance inicial/incremento/pity) da Prova de Soulmate pra uma
    raridade - exposta pra UI (`paineis.py`) montar o embed de contexto sem
    acessar `_PROVA_SOULMATE_POR_RARIDADE` diretamente."""
    return _PROVA_SOULMATE_POR_RARIDADE[raridade]


_CAMPOS_TEXTO_PROVA_SOULMATE = (
    "prova_soulmate_nome", "prova_soulmate_descricao", "prova_soulmate_situacao",
    "prova_soulmate_reacao_acerto", "prova_soulmate_reacao_erro",
    "prova_soulmate_derrota", "prova_soulmate_vitoria",
)

# 🔥 Opções genéricas de fallback (2026-08-29) - usadas só se a GAIA nunca
# respondeu (fora do ar) E a personagem ainda não tem nada cacheado. Opção
# índice 1 (a empática/calma) é a "certa" por padrão - mesmo espírito de
# `_normalizar_opcoes_prova_soulmate` do lado da GAIA, um fallback SEMPRE
# precisa de exatamente 1 opção certa, nunca ambíguo.
_OPCOES_GENERICAS_PROVA_SOULMATE = [
    {"texto": "Diga que ela devia ser mais forte sozinha.", "correta": False},
    {"texto": "Pergunte com calma se ela está bem.", "correta": True},
    {"texto": "Ignore e continue com o que estava fazendo.", "correta": False},
]


async def obter_textos_prova_soulmate(personagem):
    """Conteúdo da Prova de Soulmate (nome/descrição/situação/opções de
    resposta/reações/derrota/vitória), gerado 1x pela GAIA (LLM) na 1ª vez
    que a personagem chega em Afinidade 10 em QUALQUER servidor, e cacheado
    pra sempre (mesmo padrão de `revelar_classe` acima). Se a LLM nunca
    respondeu (GAIA fora do ar), cai pra um texto GENÉRICO baseado no nome -
    a mecânica (chance/pity/bônus de escolha) NUNCA depende da LLM
    responder, só a ambientação fica mais simples nesse caso.

    🔥 Cache-check por `prova_soulmate_opcoes` (2026-08-29, não mais por
    `prova_soulmate_nome`) - o redesenho da Prova (situação+3 opções em vez
    de intro solto) adicionou esse campo; checar `opcoes` faz uma
    personagem testada ANTES do redesenho (nome preenchido, opcoes NULA)
    se auto-curar sozinha, regenerando com o formato novo na próxima vez
    que alguém abrir a Prova dela - sem precisar de UPDATE manual no banco."""
    if personagem.get("prova_soulmate_opcoes"):
        opcoes = personagem["prova_soulmate_opcoes"]
        if isinstance(opcoes, str):
            opcoes = json.loads(opcoes)
        return {
            **{campo: personagem.get(campo) for campo in _CAMPOS_TEXTO_PROVA_SOULMATE},
            "prova_soulmate_opcoes": opcoes,
        }
    resultado = await asyncio.to_thread(
        gaia_webhook.pedir_prova_soulmate,
        personagem["nome"], personagem.get("descricao"), personagem.get("serie"), personagem["genero"],
    )
    if resultado.get("prova_soulmate_nome") and resultado.get("prova_soulmate_opcoes"):
        opcoes_json = json.dumps(resultado["prova_soulmate_opcoes"], ensure_ascii=False)
        await asyncio.to_thread(
            db.definir_textos_prova_soulmate, personagem["id"],
            resultado["prova_soulmate_nome"], resultado.get("prova_soulmate_descricao"),
            resultado.get("prova_soulmate_situacao"), opcoes_json,
            resultado.get("prova_soulmate_reacao_acerto"), resultado.get("prova_soulmate_reacao_erro"),
            resultado.get("prova_soulmate_derrota"), resultado.get("prova_soulmate_vitoria"),
        )
        personagem.update(resultado)
        personagem["prova_soulmate_opcoes"] = opcoes_json
        return resultado
    return {
        "prova_soulmate_nome": f"Prova de {personagem['nome']}",
        "prova_soulmate_descricao": f"Prove que é digno de se tornar Soulmate de {personagem['nome']}.",
        "prova_soulmate_situacao": f"{personagem['nome']} observa você em silêncio, avaliando se você está à altura.",
        "prova_soulmate_opcoes": list(_OPCOES_GENERICAS_PROVA_SOULMATE),
        "prova_soulmate_reacao_acerto": f"{personagem['nome']} parece um pouco mais confortável com sua presença.",
        "prova_soulmate_reacao_erro": f"{personagem['nome']} hesita diante da sua resposta.",
        "prova_soulmate_derrota": "Talvez... possamos tentar de novo mais tarde.",
        "prova_soulmate_vitoria": "Você me provou seu valor. A partir de agora, somos Soulmates.",
    }


async def tentar_prova_soulmate(guild_id, user_id, personagem_id, user, bonus_escolha=0.0):
    """Núcleo da Prova de Soulmate (2026-08-29, ERIS_power_afinidade_
    soulmate_niveis.md) - valida dono + Afinidade 10 + ainda não é Soulmate
    + cooldown de 1h/personagem; sorteia com chance crescente por falha
    (`_PROVA_SOULMATE_POR_RARIDADE`) + `bonus_escolha` (0.0 ou
    `_BONUS_ESCOLHA_CORRETA_PROVA_SOULMATE`, decidido por `paineis.py` a
    partir da resposta escolhida na situação - aplicado SÓ nesta tentativa,
    nunca persistido), com um branch de PITY EXPLÍCITO (garante sucesso na
    tentativa N, ignora `bonus_escolha` - nunca confia só na % chegar em
    100 sozinha, ver comentário da tabela acima). Devolve (ok, erro_ou_None,
    contexto_ou_None) - `contexto` é o que `paineis.py` precisa pra montar o
    embed de resultado (personagem, venceu, tentativa_atual, chance_usada,
    textos)."""
    if str(db.dono_do_personagem(guild_id, personagem_id)) != str(user_id):
        return False, "Essa personagem não é sua.", None
    personagem = db.personagem_por_id(personagem_id)
    if personagem is None:
        return False, "Não achei essa personagem.", None
    if db.afinidade(guild_id, user_id, personagem_id) < 10:
        return False, f"{personagem['nome']} ainda não chegou em Afinidade 10.", None
    if db.is_soulmate(guild_id, user_id, personagem_id):
        return False, f"{personagem['nome']} já é sua Soulmate.", None

    prontas = {p["id"]: p for p in await asyncio.to_thread(db.personagens_prontas_para_prova, guild_id, user_id)}
    estado = prontas.get(personagem_id)
    tentativas_feitas = estado["soulmate_tentativas"] if estado else 0
    ultima_tentativa = estado["soulmate_ultima_tentativa_em"] if estado else None
    if ultima_tentativa:
        proxima = datetime.fromisoformat(ultima_tentativa) + timedelta(minutes=_PROVA_SOULMATE_COOLDOWN_MINUTOS)
        agora = datetime.now(timezone.utc)
        if agora < proxima:
            minutos = max(1, int((proxima - agora).total_seconds() // 60))
            return False, f"Você já tentou a Prova de {personagem['nome']} recentemente - tenta de novo em ~{minutos} min.", None

    regra = _PROVA_SOULMATE_POR_RARIDADE[personagem["raridade"]]
    tentativa_atual = tentativas_feitas + 1
    chance_base = min(1.0, regra["chance"] + regra["incremento"] * tentativas_feitas)
    chance_usada = min(1.0, chance_base + bonus_escolha)
    pity_forcado = tentativa_atual >= regra["pity"]
    venceu = pity_forcado or random.random() < chance_usada

    agora_iso = datetime.now(timezone.utc).isoformat()
    await asyncio.to_thread(db.registrar_tentativa_soulmate, guild_id, user_id, personagem_id, venceu, agora_iso)
    textos = await obter_textos_prova_soulmate(personagem)

    contexto = {
        "personagem": personagem, "venceu": venceu, "pity_forcado": pity_forcado,
        "tentativa_atual": tentativa_atual, "pity_maximo": regra["pity"], "chance_usada": chance_usada,
        "textos": textos,
    }
    return True, None, contexto


async def enviar_cards_individuais(canal, guild_id, resultados, indice_inicial=0, total_ciclo=None):
    """Manda cada personagem numa mensagem PRÓPRIA (2026-08-29, pedido do
    usuário: "quero que cada personagem seja enviada em uma mensagem
    separada, e nela venha a opcao de reagir p pegar, igual no mudae") -
    reação (emoji colorido por raridade, mesmo de `_EMOJI_RARIDADE`) em vez
    de botão. Só "livre" ganha reação de claim; "reencontro"/"terceiro"
    (ver `_resolver_resultado`) só mostram o card, já foram resolvidos na
    hora do roll. A mensagem com os botões (`ViewClaimMultiplo`) continua
    existindo IGUAL, mandada em SEGUIDA pelo chamador - pedido do usuário:
    "a mensagem com os 10 botoes pode ficar numa mensagem separada no
    final normalmente".

    🔥 "Puxada N/M" corrigido (2026-08-29, pedido do usuário: "é p ser o
    numero q aquele roll representa dentre o limite atual do usuario ex
    13/50") - antes `N/M` eram só a posição/tamanho do LOTE atual (sempre
    reiniciava em 1 a cada 10, nunca passava de "X/10"); agora `indice_
    inicial` (posição GLOBAL do primeiro item desse lote dentro do roll
    inteiro) e `total_ciclo` (limite de rolls da pessoa nesse ciclo,
    `gacha._limite_rolls_atual` - inclui upgrade permanente) vêm de quem
    chama (`enviar_resultados`); sem eles (chamada do auto-colecionador,
    que não tem "limite de ciclo" - usa `rolar_sem_cooldown`), cai pro
    comportamento antigo (numera só dentro do que foi passado aqui)."""
    config = db.obter_configuracao_colecao(guild_id)
    expira_em = datetime.now(timezone.utc) + timedelta(seconds=config["duracao_card_segundos"])
    total_ciclo = total_ciclo if total_ciclo is not None else len(resultados)
    for indice, resultado in enumerate(resultados):
        embed = montar_embed(resultado)
        if total_ciclo > 1:
            rodape_atual = embed.footer.text or ""
            posicao_global = indice_inicial + indice + 1
            embed.set_footer(text=f"{rodape_atual} · Roll {posicao_global}/{total_ciclo}".strip(" ·"))
        try:
            mensagem = await canal.send(embed=embed)
        except discord.HTTPException:
            continue
        if resultado.get("resultado_tipo", "livre") != "livre":
            continue
        emoji_claim = _EMOJI_RARIDADE.get(resultado.get("raridade", 1), "💘")
        # 🔥 2 reações por card (2026-09-01) - a colorida de sempre (claim
        # normal) e ⭐ (claim + favoritar na hora). A 3ª (🔄, claim + tag
        # "trade") foi REMOVIDA no mesmo dia (achado do usuário: "essa
        # reação de atualizar q vc pos nos rolls é inutil" - o emoji 🔄
        # lia como "atualizar", não como "trocar", e cada reação a mais é
        # mais 1 chamada de rede por personagem, direto ligado à queixa
        # "tem como melhorar a velocidade de aparição das personagens?").
        # As 2 que sobraram são adicionadas em PARALELO (`asyncio.gather`,
        # não uma sequência de `await`) - metade do tempo de rede por
        # card; o registro dos 2 cards pendentes vira 1 chamada só
        # (`registrar_cards_pendentes`, 1 conexão/transação em vez de 2).
        resultados_reacao = await asyncio.gather(
            mensagem.add_reaction(emoji_claim), mensagem.add_reaction(EMOJI_FAVORITAR), return_exceptions=True,
        )
        itens_pendentes = [
            (emoji, acao) for emoji, acao, resultado_reacao in (
                (emoji_claim, "claim", resultados_reacao[0]), (EMOJI_FAVORITAR, "favoritar", resultados_reacao[1]),
            )
            if not isinstance(resultado_reacao, Exception)
        ]
        if itens_pendentes:
            await asyncio.to_thread(
                db.registrar_cards_pendentes, guild_id, mensagem.id, resultado["id"], itens_pendentes, expira_em.isoformat(),
            )


async def enviar_resultados_em_lotes(canal, guild_id, resultados, total_ciclo, enviar_primeira_mensagem=None):
    """Divide `resultados` em lotes de até `LIMITE_TECNICO_EMBEDS_POR_
    MENSAGEM` (10, teto de botões numa `ViewClaimMultiplo` sem apertar) e
    manda cada lote (cards individuais com reação, `enviar_cards_
    individuais`, + 1 mensagem só de botões, `ViewClaimMultiplo`) -
    ÚNICA implementação desse padrão (2026-08-29, extraída de dentro de
    `enviar_resultados` - achado real: o auto-colecionador tinha uma CÓPIA
    manual desse mesmo loop de "dividir em lotes de 10", que nunca recebeu
    o fix de "Puxada N/M" feito aqui, e voltou a mostrar "Puxada X/10"
    reiniciando a cada lote - "vc ta ignorando alguns principios... é a
    msm coisa, n deveria ter de corrigir em locais diferentes". Agora só
    existe 1 lugar que sabe dividir em lotes/numerar globalmente - roll de
    jogador (`enviar_resultados`) E auto-colecionador (`eris/colecao/
    auto_colecionador.py`) chamam ESTA função.

    `enviar_primeira_mensagem(conteudo, view) -> mensagem` (opcional,
    async) - se passado, só o 1º lote de botões usa ele (ex.: `interaction.
    followup.send`, fecha a interação); lotes seguintes (e todo o resto
    quando None, caso do auto-colecionador que não tem `Interaction`
    nenhuma) usam `canal.send` direto. Devolve [(view, lote), ...] só dos
    lotes que enviaram com sucesso - quem chama decide o que fazer com
    isso (`_processar_reacao_claim`/`_decidir_claims` do auto-colecionador
    precisam de `view`+`lote` pra montar a lista de pendentes)."""
    lotes_enviados = []
    primeiro_lote = True
    for inicio in range(0, len(resultados), LIMITE_TECNICO_EMBEDS_POR_MENSAGEM):
        lote = resultados[inicio:inicio + LIMITE_TECNICO_EMBEDS_POR_MENSAGEM]
        await enviar_cards_individuais(canal, guild_id, lote, indice_inicial=inicio, total_ciclo=total_ciclo)
        view = ViewClaimMultiplo(guild_id, lote)
        conteudo = "👇 Ou reivindique por aqui:"
        try:
            if primeiro_lote and enviar_primeira_mensagem is not None:
                mensagem = await enviar_primeira_mensagem(conteudo, view)
                primeiro_lote = False
            else:
                mensagem = await canal.send(conteudo, view=view)
        except discord.HTTPException:
            continue
        view.mensagem = mensagem
        lotes_enviados.append((view, lote))
    return lotes_enviados


async def enviar_resultados(interaction, resultados):
    """Manda os resultados de um roll (`/wa`/`/ha`/`/ma`, QUALQUER
    quantidade) - pedido do usuário (2026-08-29): "quero a opção de com 1
    unico clique, rodar os maximo de rolls disponiveis... n apenas os 10".
    Resolve o "total_ciclo" (limite de rolls da pessoa, pro rodapé "Roll
    N/M") e como mandar o 1º lote de botões - o loop de lotes em si é
    `enviar_resultados_em_lotes` (extraído pra ser compartilhado com o
    auto-colecionador, ver docstring dela).

    🔥 Canal de anúncio configurado SEMPRE vence (2026-08-30, pedido do
    usuário: "quero q tudo relacionado a musica so seja respondido no
    canal de musica definido, independente se mandar o comando em outro
    canal... o msm p os colecionar") - se `/colecao_admin canal` tiver
    configurado um canal pra esse servidor, os cards/botões saem SEMPRE
    lá, nunca no canal de onde `/wa`/`/ha`/`/ma`/`/pandora` foi digitado; a
    interação em si só recebe um ack ephemeral (apagado em seguida) nesse
    caso - mesma limitação de sempre, não dá pra fazer uma resposta de
    interação aparecer num canal diferente de onde ela nasceu."""
    guild_id = interaction.guild.id
    config = await asyncio.to_thread(db.obter_configuracao_colecao, guild_id)
    canal = interaction.channel
    if config.get("canal_anuncio_id"):
        canal_configurado = interaction.guild.get_channel(int(config["canal_anuncio_id"]))
        if canal_configurado is not None:
            canal = canal_configurado
    redireciona = canal.id != interaction.channel.id
    total_ciclo = await asyncio.to_thread(_limite_rolls_atual, guild_id, interaction.user.id, config)

    async def _enviar_primeira_mensagem(conteudo, view):
        if redireciona:
            return await canal.send(conteudo, view=view)
        return await interaction.followup.send(conteudo, view=view)

    await enviar_resultados_em_lotes(canal, guild_id, resultados, total_ciclo, enviar_primeira_mensagem=_enviar_primeira_mensagem)
    if redireciona:
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass


async def processar_reacao_claim(client, payload):
    """Chamado de `on_raw_reaction_add` (`eris/bot.py`) pra toda reação em
    QUALQUER mensagem - filtra pra card pendente na hora. Ignora
    silenciosamente qualquer coisa que não seja exatamente o emoji de claim
    desse card específico (evita reação aleatória virar claim sem querer).

    🔥 SÓ registrado no papel "completo" (2026-08-30, achado do usuário:
    "ambas os bots respondem, tinha q ser so 1") - a suposição antiga era
    de que cada instância só recebia evento das PRÓPRIAS mensagens, mas o
    Discord entrega `on_raw_reaction_add` pra QUALQUER bot conectado ao
    canal, não só pra quem postou a mensagem - as duas instâncias (que
    ficam no MESMO servidor, compartilhando o mesmo banco) processavam o
    MESMO claim, só uma vencia a corrida mas a outra (música, que nem
    deveria participar) ainda respondia com erro/duplicado.

    🔥 Pendentes persistidos (2026-08-29) - `db.card_pendente_por_mensagem`
    já limpa expirados sozinha (reset preguiçoso), sem precisar checar
    `expira_em` aqui manualmente como antes."""
    if payload.user_id == client.user.id:
        return
    # 🔥 Busca já FILTRADA pelo emoji exato (2026-09-01) - antes buscava só
    # por `message_id` e comparava o emoji manualmente aqui; agora cada
    # emoji da mesma mensagem é uma linha própria (claim/favoritar/trocar,
    # ver `db.registrar_card_pendente`), então `None` já cobre "reação
    # aleatória que não é nenhum dos 3 válidos" igual antes.
    pendente = await asyncio.to_thread(db.card_pendente_por_mensagem, payload.message_id, str(payload.emoji))
    if pendente is None:
        return
    personagem = await asyncio.to_thread(db.personagem_por_id, pendente["personagem_id"])
    if personagem is None:
        return

    guild = client.get_guild(payload.guild_id) if payload.guild_id else None
    if guild is None:
        return
    membro = payload.member or guild.get_member(payload.user_id)
    if membro is None:
        try:
            membro = await guild.fetch_member(payload.user_id)
        except discord.HTTPException:
            return
    if membro.bot:
        return

    canal = client.get_channel(payload.channel_id)
    ok, erro, embed = await _processar_claim(pendente["guild_id"], personagem, membro)
    if not ok:
        if canal is not None:
            try:
                await canal.send(f"{membro.mention} {erro}", delete_after=10)
            except discord.HTTPException:
                pass
        return

    await asyncio.to_thread(db.remover_card_pendente, payload.message_id)
    # 🔥 Ação extra da reação (2026-09-01) - "favoritar" (ver `EMOJI_
    # FAVORITAR`) só se aplica DEPOIS do claim confirmar de verdade (nunca
    # antes - só faz sentido favoritar uma personagem que já é sua);
    # "claim" (a reação colorida de sempre) não faz nada extra aqui. A
    # ação "trocar" (🔄, tag "trade") foi REMOVIDA no mesmo dia (achado do
    # usuário: "essa reação de atualizar q vc pos nos rolls é inutil") -
    # `db.definir_tag`/`TAG_TROCA`/o filtro "🏷️ Marcadas pra troca" em
    # Coleção continuam existindo (ainda mostram o que já foi marcado
    # antes), só não tem mais um jeito NOVO de marcar via reação de roll.
    if pendente["acao"] == "favoritar":
        await asyncio.to_thread(db.favoritar, pendente["guild_id"], membro.id, personagem["id"])
        embed.add_field(name="⭐ Favoritada!", value="Já marcada como favorita.", inline=False)
    if canal is not None:
        try:
            await canal.send(embed=embed)
        except discord.HTTPException:
            pass


class ViewClaimMultiplo(discord.ui.View):
    """Um botão "💘" por personagem LIVRE rolada na MESMA mensagem - suporta
    tanto um roll único quanto uma "puxada" de várias (pedido do usuário,
    2026-08-29). Personagens já resolvidas como "reencontro"/"terceiro" (ver
    `_resolver_resultado`) NÃO ganham botão - já foram pagas na hora do
    roll, só o card explica o que aconteceu.

    Cada botão fica ativo pela duração CONFIGURADA nesse servidor
    (`duracao_card_segundos`); depois disso `on_timeout` desabilita todos e
    edita a mensagem original. Cooldown de claim também é lido do servidor a
    cada clique (`db.obter_configuracao_colecao`), então uma mudança de
    config feita pelo admin já vale pra cards abertos ANTES dela. Estado
    fica em MEMÓRIA, igual às sessões de música (`eris/core/musica.py`) -
    não sobrevive a um restart do processo, aceito como limitação conhecida
    na mesma linha do resto do ERIS."""

    def __init__(self, guild_id, personagens):
        duracao = db.obter_configuracao_colecao(guild_id)["duracao_card_segundos"]
        super().__init__(timeout=duracao)
        self.guild_id = guild_id
        self.personagens = personagens
        self.mensagem = None
        # 🔥 Índice do personagem -> botão (não `self.children[indice]`) -
        # personagens "reencontro"/"terceiro" não geram botão nenhum, então
        # o índice na lista de personagens e o índice em `self.children`
        # divergem assim que uma delas aparece no meio de uma puxada.
        self._botoes_por_indice = {}
        contagem_botoes = 0
        for indice, personagem in enumerate(personagens):
            if personagem.get("resultado_tipo", "livre") != "livre":
                continue
            rotulo = personagem["nome"] if len(personagens) == 1 else f"{indice + 1}. {personagem['nome']}"
            raridade = personagem.get("raridade", 1)
            botao = discord.ui.Button(
                label=rotulo[:80],
                style=_ESTILO_BOTAO_RARIDADE.get(raridade, discord.ButtonStyle.success),
                emoji=_EMOJI_RARIDADE.get(raridade, "💘"),
                row=contagem_botoes // 5,
            )
            botao.callback = self._callback_para(indice)
            self.add_item(botao)
            self._botoes_por_indice[indice] = botao
            contagem_botoes += 1

    def _callback_para(self, indice):
        async def callback(interaction: discord.Interaction):
            await self._reivindicar(interaction, indice)
        return callback

    async def _reivindicar(self, interaction: discord.Interaction, indice):
        botao = self._botoes_por_indice[indice]
        if botao.disabled:
            await interaction.response.send_message("Essa carta já foi resolvida.", ephemeral=True)
            return

        personagem = self.personagens[indice]

        async def _ack_visual():
            # 🔥 Desabilita o botão/edita a mensagem JÁ, ANTES de esperar a
            # LLM classificar (~1-2s) - mesma regra de "zero espera
            # perceptível" de sempre no ERIS. A confirmação consolidada
            # (WiShards + classe numa única mensagem, pedido do usuário)
            # chega logo depois, como followup.
            botao.disabled = True
            botao.label = f"Reivindicada por {interaction.user.display_name}"[:80]
            await interaction.response.edit_message(view=self)

        ok, erro, embed = await _processar_claim(self.guild_id, personagem, interaction.user, ao_confirmar_economia=_ack_visual)
        if not ok:
            await interaction.response.send_message(erro, ephemeral=True)
            return

        try:
            await interaction.followup.send(embed=embed)
        except discord.HTTPException:
            pass

    async def marcar_reivindicada_externamente(self, indice, rotulo):
        """Usado pelo auto-colecionador (`eris/colecao/auto_colecionador.py`,
        2026-08-29) quando ELE - não um clique de humano - venceu a corrida
        pela personagem desse índice, depois dos 5min de janela pra qualquer
        humano reivindicar primeiro. Só cuida da parte VISUAL (desabilita o
        botão, edita a mensagem) - a economia (claim atômico, WiShards,
        Afinidade) já foi feita por quem chamou, igual `_reivindicar` faz pra
        um clique de verdade, só que sem passar por uma `Interaction`."""
        botao = self._botoes_por_indice.get(indice)
        if botao is None or botao.disabled:
            return
        botao.disabled = True
        botao.label = rotulo[:80]
        if self.mensagem is not None:
            try:
                await self.mensagem.edit(view=self)
            except discord.HTTPException:
                pass

    async def on_timeout(self):
        if self.mensagem is None:
            return
        for item in self.children:
            item.disabled = True
        try:
            await self.mensagem.edit(view=self)
        except discord.HTTPException:
            pass


def personagens_pendentes(guild_id, raridade=None, limite=None):
    """Cards de reação ainda DISPONÍVEIS nesse servidor (não expirados,
    ainda sem dono) - lista os personagens rolados na última hora (mesma
    janela de `duracao_card_segundos`) que ninguém pegou ainda. Devolve
    [(message_id, personagem), ...], ordenado por POPULARIDADE DESC
    (`db.cards_pendentes` já cuida disso, junto com o reset preguiçoso de
    expirados e o filtro de quem já tem dono).

    🔥 Corrigido (2026-08-29, usuário: "esse comando é p listar apenas os
    personagens n coletados e rolados na ultima hora, e trazer ordenado
    por popularidade... e eu pedi p retornar apenas os 10 melhores") -
    antes ordenava por RARIDADE e listava tudo (até ~150 com 3 pessoas
    rolando 50/hora cada), sem bater com o pedido original. `limite`
    (opcional) corta o resultado aos N primeiros DEPOIS de ordenar -
    `/colecao_disponiveis` usa `limite=10` ("os 10 melhores"); o painel
    `/pandora` -> Coleção -> Disponíveis continua sem limite, pra poder
    paginar por cima de tudo que sobrar. `raridade` (opcional) filtra pra
    só esse tier ANTES de aplicar `limite`.

    🔥 Persistido em `eris.db` desde 2026-08-29 (pedido do usuário: "cria
    uma tabela com a msm logica dos colecoes disponiveis" - achado real:
    um restart do processo no meio da janela de 1h fazia perder acesso a
    uma personagem já rolada, sem jeito de reivindicar depois). Função
    SÍNCRONA (é uma query de banco só, pequena e indexada por guild) -
    quem chama de dentro de uma interação do Discord deve rodar em
    `asyncio.to_thread` e `defer()` ANTES, mesmo cuidado do bug de timeout
    já corrigido em `rolar_varios`."""
    pendentes = db.cards_pendentes(guild_id, raridade)
    if limite is not None:
        pendentes = pendentes[:limite]
    return pendentes


async def reivindicar_em_massa(guild_id, user):
    """🔥 Novo (2026-09-01, pedido do usuário: "quero um botão que gasta
    todos os meus claims p pegar as personagens disponiveis por ordem de
    popularidade") - reivindica, uma atrás da outra, as personagens ainda
    pendentes nesse servidor (`personagens_pendentes`, já vem ordenado por
    POPULARIDADE DESC) até os claims desse ciclo acabarem de vez ou a
    lista de pendentes se esgotar. Perder a corrida pra outro clique não
    consome claim nenhum (mesma regra de sempre), só pula pra próxima
    pendente da lista; a única forma de PARAR de verdade é os claims
    acabarem. Devolve [(personagem, recompensa_wishards), ...] das
    reivindicadas com sucesso, na ordem em que foram conquistadas.

    🔥 Otimizado (2026-09-02, achado do usuário: "pq a logica do
    reinvindicar tudo demora? N da p otimizar?") - usa `_processar_claim_
    economia` (só a parte rápida, sem rede) em vez de `_processar_claim`
    completo PRA CADA personagem - a parte cara (`revelar_classe`, que faz
    uma chamada de REDE pra GAIA classificar quando é a 1ª vez que ESSA
    personagem é reivindicada em QUALQUER servidor) deixou de rodar uma
    atrás da outra dentro do loop (N personagens nunca-antes-classificadas
    = N chamadas de rede EM SÉRIE, cada uma ~1-2s) - agora só dispara
    DEPOIS que todos os claims econômicos já terminaram, todas de uma vez
    em PARALELO (`asyncio.gather`). O contador de claims em si continua
    sendo consumido em ordem estrita (é compartilhado entre as
    personagens, não dá pra paralelizar essa parte sem risco de
    corrida/gastar claim a mais)."""
    pendentes = await asyncio.to_thread(personagens_pendentes, guild_id)
    conquistadas = []
    para_revelar_classe = []
    for message_id, personagem in pendentes:
        ok, erro, recompensa, _novo_saldo = await asyncio.to_thread(_processar_claim_economia, guild_id, personagem, user)
        if not ok:
            if "já usou seu claim" in erro:
                break
            continue
        await asyncio.to_thread(db.remover_card_pendente, message_id)
        conquistadas.append((personagem, recompensa))
        para_revelar_classe.append(personagem)
    if para_revelar_classe:
        await asyncio.gather(*(revelar_classe(personagem) for personagem in para_revelar_classe))
    return conquistadas


class ViewClaimPendentes(discord.ui.View):
    """Botões de claim pros N personagens ainda pendentes (`/colecao_
    disponiveis`, 2026-08-29) - reaproveita `_processar_claim` (mesmo
    núcleo econômico do botão de `/wa`/da reação), sem rolar nada novo:
    cada botão aqui reivindica uma personagem que já estava esperando de
    um roll anterior (qualquer lote, humano ou auto-colecionador)."""

    def __init__(self, guild_id, itens):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self._itens = itens
        for indice, (message_id, personagem) in enumerate(itens):
            raridade = personagem.get("raridade", 1)
            botao = discord.ui.Button(
                label=personagem["nome"][:80],
                style=_ESTILO_BOTAO_RARIDADE.get(raridade, discord.ButtonStyle.success),
                emoji=_EMOJI_RARIDADE.get(raridade, "💘"),
                row=indice // 5,
            )
            botao.callback = self._callback_para(indice)
            self.add_item(botao)

    def _callback_para(self, indice):
        async def callback(interaction: discord.Interaction):
            await self._reivindicar(interaction, indice)
        return callback

    async def _reivindicar(self, interaction: discord.Interaction, indice):
        botao = self.children[indice]
        if botao.disabled:
            await interaction.response.send_message("Essa carta já foi resolvida.", ephemeral=True)
            return
        message_id, personagem = self._itens[indice]

        async def _ack_visual():
            botao.disabled = True
            botao.label = f"Reivindicada por {interaction.user.display_name}"[:80]
            await interaction.response.edit_message(view=self)

        ok, erro, embed = await _processar_claim(self.guild_id, personagem, interaction.user, ao_confirmar_economia=_ack_visual)
        if not ok:
            await interaction.response.send_message(erro, ephemeral=True)
            return
        await asyncio.to_thread(db.remover_card_pendente, message_id)
        try:
            await interaction.followup.send(embed=embed)
        except discord.HTTPException:
            pass
