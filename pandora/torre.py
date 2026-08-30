# -*- coding: utf-8 -*-
"""Torre (2026-08-30) - mecânica PvE de combate do Colecionador,
`ERIS_power_afinidade_soulmate_niveis.md` (Fórmula de Power/Afinidade/
Soulmate já fechada; o mecanismo de combate em si, Seção 11, nunca tinha
sido decidido). Decisão do usuário: resolução DETERMINÍSTICA por threshold
(soma de Power da Party vs. alvo do andar, sem RNG) + fórmula INFINITA de
andares (sem lista fixa) - geração de andares via IA fica pra uma leva
futura (já validada em princípio, mas "depende da Torre existir
primeiro").

Módulo PURO (sem discord.py) - `pandora.paineis` decide como mostrar."""
import math

from pandora import db

# 🔥 Power Base (Seção 1 do documento) - compressão logarítmica da
# popularidade, 300 a 1.000. `likes_max` vem de `db.popularidade_maxima_
# catalogo()` (cacheada, catálogo só muda via sincronização).
_POWER_BASE_MINIMO = 300
_POWER_BASE_AMPLITUDE = 700


def power_base(popularidade):
    likes_max = db.popularidade_maxima_catalogo()
    if likes_max <= 0:
        return _POWER_BASE_MINIMO
    return _POWER_BASE_MINIMO + _POWER_BASE_AMPLITUDE * math.log(1 + popularidade) / math.log(1 + likes_max)


# 🔥 Bônus de nível (Seção 5) - FIXO, não percentual (decisão explícita do
# documento original: percentual faria personagens já populares ganharem
# muito mais em valor absoluto, o oposto do objetivo de deixar
# personagens obscuras competitivas com investimento).
BONUS_POWER_POR_NIVEL = 50


def power_final(popularidade, nivel, afinidade, is_soulmate):
    """Fórmula fechada (Seção 6): `(Power Base + Bônus de Nível) ×
    Multiplicador` - multiplicador é 2,0 se Soulmate, senão `1,0 +
    (afinidade-1)×0,10` (Afinidade 1 = 1,0×, Afinidade 10 = 1,9×)."""
    base = power_base(popularidade) + (nivel - 1) * BONUS_POWER_POR_NIVEL
    multiplicador = 2.0 if is_soulmate else 1.0 + (afinidade - 1) * 0.10
    return base * multiplicador


# 🔥 Fórmula do Power-alvo por andar (2026-08-30, número que o documento
# original não definia - "impacto exato das classes/andares" ficou em
# aberto) - geométrica, ~6%/andar: andar 1 pede ~1.000 (alcançável até
# solo por 1-2 personagens recém-obtidas), andar 50 pede ~16.000 (perto do
# teto de uma Party de 5 totalmente desenvolvida - Base 1.000+Nv.10+
# Soulmate ×5 ×1,10 de composição ≈ 15.950) - continua crescendo depois
# disso pra quem quiser seguir subindo.
_POWER_ALVO_BASE = 1000
_POWER_ALVO_TAXA_CRESCIMENTO = 1.06


def power_alvo_andar(andar):
    bruto = _POWER_ALVO_BASE * (_POWER_ALVO_TAXA_CRESCIMENTO ** (andar - 1))
    return round(bruto / 10) * 10


# 🔥 Restrição de categoria por andar (2026-08-30) - rotação FIXA e
# determinística (índice `(andar-1) % 6`), usa Categoria de combate como
# "vocabulário de restrição" (decisão já fechada antes desta leva) sem
# precisar de geração por IA ainda. Andar 1 (índice 0) sempre sem
# restrição, pra não travar quem tá começando.
RESTRICOES_ANDAR = (
    None,               # 0 - nenhuma restrição
    "min_tank",         # 1 - pelo menos 1 Tank
    "min_support",      # 2 - pelo menos 1 Support
    "max_1_tank",       # 3 - no máximo 1 Tank
    "todas_categorias", # 4 - DPS + Tank + Support, todas presentes
    "so_dps",           # 5 - só DPS, nenhum Tank/Support
)

_DESCRICAO_RESTRICAO = {
    None: "Nenhuma",
    "min_tank": "Precisa de pelo menos 1 🛡️ Tank na Party",
    "min_support": "Precisa de pelo menos 1 ✨ Support na Party",
    "max_1_tank": "No máximo 1 🛡️ Tank na Party",
    "todas_categorias": "Precisa das 3 categorias (DPS + Tank + Support)",
    "so_dps": "Só ⚔️ DPS permitido (nenhum Tank/Support)",
}

# 🔥 Ícone por categoria de combate (2026-08-30, pedido do usuário: "coloca
# a role antes do nome com base no icone") - vocabulário fechado, mesmo
# das restrições acima; personagem sem classe revelada cai no fallback.
ICONE_CATEGORIA = {"DPS": "⚔️", "Tank": "🛡️", "Support": "✨"}


def icone_categoria(categoria):
    return ICONE_CATEGORIA.get(categoria, "❓")


def restricao_andar(andar):
    return RESTRICOES_ANDAR[(andar - 1) % len(RESTRICOES_ANDAR)]


def descricao_restricao(restricao):
    return _DESCRICAO_RESTRICAO[restricao]


def checar_restricao(restricao, categorias):
    """`categorias` é a lista de `categoria_combate` de cada membro da
    Party (pode ter `None` se a personagem nunca foi classificada -
    tratada como "não conta pra nenhuma categoria")."""
    if restricao is None:
        return True
    n_tank = categorias.count("Tank")
    n_support = categorias.count("Support")
    if restricao == "min_tank":
        return n_tank >= 1
    if restricao == "min_support":
        return n_support >= 1
    if restricao == "max_1_tank":
        return n_tank <= 1
    if restricao == "todas_categorias":
        return {"DPS", "Tank", "Support"}.issubset(set(categorias))
    if restricao == "so_dps":
        return n_tank == 0 and n_support == 0
    return True


# 🔥 Bônus de composição (2026-08-29, já fechado antes desta leva) - ÚNICO
# bônus de categoria, nunca um multiplicador individual por categoria
# isolada.
BONUS_COMPOSICAO_3_CATEGORIAS = 0.10


def categoria_personagem(personagem):
    return db.categoria_combate_da_classe(personagem["classe"]) if personagem.get("classe") else None


def power_personagem(personagem, guild_id, user_id, nivel=None, bonus_global=None, cache_bonus_classe=None):
    """CP de UMA personagem, no vínculo (guild+user) - núcleo reaproveitado
    pela Party inteira (`_calcular_contexto`) e por qualquer UI que precise
    mostrar o CP avulso de uma personagem (Party/dropdowns, 2026-08-30,
    pedido do usuário: "é importante informar o CP tbm"). Devolve
    (power, nivel, categoria_combate).

    🔥 Progressão Global da conta (2026-08-30, análise do usuário: "a
    personagem possui um limite de desenvolvimento. A conta não") - ÚNICO
    ponto do pacote que aplica `db.bonus_cp_global` (`(CP + fixo) × (1 +
    percentual)`, Seção 8) - toda Party/Torre/dropdown que já passa por
    esta função herda o bônus automaticamente, sem precisar mudar mais
    nada. Uma personagem no Nv.10/Afinidade 10/Soulmate (teto individual)
    continua ficando mais forte no futuro conforme a CONTA evolui.

    🔥 Bônus por CLASSE (2026-08-30, pedido do usuário: "a cd 5 [personagens
    da mesma classe] aumenta 50 [CP fixo p todas daquela classe]") - MESMO
    ponto único, `db.bonus_cp_classe` soma junto do fixo global antes do
    multiplicador percentual - incentiva colecionar várias da MESMA
    classe (taxonomia aberta), não só desenvolver uma só.

    🔥 `nivel`/`bonus_global`/`cache_bonus_classe` opcionais (2026-08-30,
    corrige N+1 achado no Auto-Party: "atualiza a pt logicamente mas n
    troca visualmente, da erro de GAIA não respondeu a tempo") - quem
    varre a coleção INTEIRA (`ordenar_por_power`/`torre.montar_auto_party`)
    pré-carrega isso 1x fora do loop e passa aqui, em vez de cada chamada
    abrir conexões SQLite novas pra cada personagem (`db.conexao()` não
    faz pool - uma coleção de centenas virava mil+ conexões, estourando o
    teto de 3s do Discord). Chamada avulsa (card de 1 personagem) continua
    funcionando igual, sem passar nada disso - cai no fallback de sempre."""
    if nivel is None:
        nivel = db.nivel_personagem(guild_id, user_id, personagem["id"])
    categoria = categoria_personagem(personagem)
    power = power_final(
        personagem["popularidade"], nivel, personagem.get("afinidade", 1), bool(personagem.get("is_soulmate")),
    )
    if bonus_global is None:
        bonus_global = db.bonus_cp_global(guild_id, user_id)
    bonus_fixo, bonus_percentual = bonus_global
    classe = personagem.get("classe")
    if cache_bonus_classe is not None:
        if classe not in cache_bonus_classe:
            cache_bonus_classe[classe] = db.bonus_cp_classe(guild_id, user_id, classe)
        bonus_classe = cache_bonus_classe[classe]
    else:
        bonus_classe = db.bonus_cp_classe(guild_id, user_id, classe)
    power = (power + bonus_fixo + bonus_classe) * (1 + bonus_percentual)
    return power, nivel, categoria


def _contexto_lote(guild_id, user_id):
    """Nível/bônus global pré-carregados 1x + cache vazio de bônus por
    classe - pra passar em `power_personagem` ao varrer uma coleção
    inteira sem N+1 (ver docstring de `power_personagem`)."""
    return db.nivel_em_lote(guild_id, user_id), db.bonus_cp_global(guild_id, user_id), {}


def ordenar_por_power(personagens, guild_id, user_id):
    """Ordena do MAIOR pro menor CP (2026-08-30, pedido do usuário: "Todo
    dropdwon q listar waifu, sempre ordene pelas com maior CP/
    popularidade") - só faz sentido pra personagens JÁ POSSUÍDAS (usa
    `power_personagem`, que depende de Nível/Afinidade do vínculo); pra
    lista de personagens NÃO possuídas (loja/wishlist), usar `consulta.
    ordenar_por_popularidade` em vez desta."""
    niveis, bonus_global, cache_classe = _contexto_lote(guild_id, user_id)

    def _power(p):
        nivel = niveis.get(p["id"], 1)
        return power_personagem(p, guild_id, user_id, nivel=nivel, bonus_global=bonus_global, cache_bonus_classe=cache_classe)[0]

    return sorted(personagens, key=_power, reverse=True)


def calcular_power_party(membros, guild_id, user_id):
    """`membros`: lista de dicts já com `power` e `categoria_combate`
    resolvidos por quem chama (`power_personagem`, um por personagem).
    Devolve (power_total, categorias) - `categorias` é reaproveitada por
    `checar_restricao` sem recalcular.

    🔥 Cidade v2 (2026-08-30, efeitos diferenciados por área) - depois do
    bônus de composição de sempre, aplica o SNAPSHOT de bônus de CP pra
    Party (`db.cidade_bonus_party` - Militar/Arcano já com Administração
    multiplicada dentro, "Bônus da Coleção" = 1% de TODA a coleção, ver
    `pandora.cidade`). Lê um snapshot pré-calculado (nunca escaneia a
    coleção inteira aqui - hot path, roda a cada cálculo de Torre)."""
    if not membros:
        return 0.0, []
    total = sum(m["power"] for m in membros)
    categorias = [m.get("categoria_combate") for m in membros]
    if {"DPS", "Tank", "Support"}.issubset(set(categorias)):
        total *= 1 + BONUS_COMPOSICAO_3_CATEGORIAS
    bonus_militar_fixo, bonus_arcano_percentual, bonus_colecao_fixo = db.cidade_bonus_party(guild_id, user_id)
    total = (total + bonus_colecao_fixo + bonus_militar_fixo) * (1 + bonus_arcano_percentual)
    return total, categorias


# 🔥 Recompensa por andar vencido (2026-08-30) - cresce com o andar,
# incentivo pra continuar subindo em vez de estacionar.
def recompensa_andar(andar):
    return 50 * andar


def _calcular_contexto(guild_id, user_id):
    """Cálculo PURO (sem efeito colateral) - reaproveitado por `preview_
    andar` (mostra antes de arriscar, resolução é determinística, então
    "planejar antes de clicar" faz sentido de verdade aqui) e `tentar_
    andar` (mesmo cálculo + credita recompensa/avança andar só se
    venceu). Devolve `None` se a Party estiver vazia."""
    equipe = db.obter_equipe(guild_id, user_id, "party")
    if not equipe:
        return None

    andar = db.andar_atual_torre(guild_id, user_id)
    alvo = power_alvo_andar(andar)
    restricao = restricao_andar(andar)

    membros = []
    for p in equipe.values():
        power, nivel, categoria = power_personagem(p, guild_id, user_id)
        membros.append({
            "nome": p["nome"],
            "nivel": nivel,
            "afinidade": p.get("afinidade", 1),
            "is_soulmate": bool(p.get("is_soulmate")),
            "categoria_combate": categoria,
            "power": power,
        })
    power_total, categorias = calcular_power_party(membros, guild_id, user_id)
    restricao_ok = checar_restricao(restricao, categorias)
    venceu = restricao_ok and power_total >= alvo

    return {
        "andar": andar, "alvo": alvo, "restricao": restricao, "restricao_ok": restricao_ok,
        "power_total": power_total, "membros": membros, "venceu": venceu,
    }


def _melhor_fora(pool, selecionados, bloquear_categorias=()):
    """Melhor candidato do `pool` que ainda NÃO está em `selecionados`,
    excluindo quem for de alguma categoria bloqueada - `None` se não
    sobrar ninguém (ex.: coleção inteira é só Tank)."""
    ids_selecionados = {c["id"] for c in selecionados}
    candidatos = [
        c for c in pool
        if c["id"] not in ids_selecionados and c["categoria_combate"] not in bloquear_categorias
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda c: c["power"])


def _garantir_categoria(selecionados, pool, categoria):
    """Garante pelo menos 1 membro da `categoria` - se já tem, não mexe;
    senão troca o membro de MENOR power pelo melhor candidato daquela
    categoria fora da seleção. Sem candidato disponível = segue sem (a
    restrição fica só parcialmente cumprida, não trava o Auto-Party -
    quem chama decide o que fazer com isso, ver `_calcular_contexto`)."""
    if any(c["categoria_combate"] == categoria for c in selecionados):
        return selecionados
    ids_selecionados = {c["id"] for c in selecionados}
    candidatos_categoria = [c for c in pool if c["id"] not in ids_selecionados and c["categoria_combate"] == categoria]
    if not candidatos_categoria:
        return selecionados
    melhor_da_categoria = max(candidatos_categoria, key=lambda c: c["power"])
    pior = min(selecionados, key=lambda c: c["power"])
    return [melhor_da_categoria if c["id"] == pior["id"] else c for c in selecionados]


def _aplicar_todas_categorias(selecionados, pool):
    """Igual `_garantir_categoria`, mas pras 3 categorias de uma vez -
    processa em sequência e BLOQUEIA quem já garante uma categoria de ser
    removido pela troca seguinte (senão a 2ª/3ª troca podia desfazer a
    1ª)."""
    ids_bloqueados = set()
    for categoria in ("DPS", "Tank", "Support"):
        ja_presente = [c for c in selecionados if c["categoria_combate"] == categoria]
        if ja_presente:
            ids_bloqueados.add(max(ja_presente, key=lambda c: c["power"])["id"])
            continue
        ids_selecionados = {c["id"] for c in selecionados}
        candidatos_categoria = [c for c in pool if c["id"] not in ids_selecionados and c["categoria_combate"] == categoria]
        if not candidatos_categoria:
            continue
        melhor_da_categoria = max(candidatos_categoria, key=lambda c: c["power"])
        substituiveis = [c for c in selecionados if c["id"] not in ids_bloqueados]
        if not substituiveis:
            break
        pior = min(substituiveis, key=lambda c: c["power"])
        selecionados = [melhor_da_categoria if c["id"] == pior["id"] else c for c in selecionados]
        ids_bloqueados.add(melhor_da_categoria["id"])
    return selecionados


def _aplicar_max_1_tank(selecionados, pool):
    """Se tiver mais de 1 Tank, troca os excedentes (do mais fraco pro
    mais forte) pelo melhor não-Tank fora da seleção, mantendo só o Tank
    de maior power."""
    tanks = [c for c in selecionados if c["categoria_combate"] == "Tank"]
    while len(tanks) > 1:
        pior_tank = min(tanks, key=lambda c: c["power"])
        substituto = _melhor_fora(pool, selecionados, bloquear_categorias={"Tank"})
        if substituto is None:
            break
        selecionados = [substituto if c["id"] == pior_tank["id"] else c for c in selecionados]
        tanks = [c for c in selecionados if c["categoria_combate"] == "Tank"]
    return selecionados


def _selecionar_auto_party(pool, restricao, tamanho):
    """Núcleo do Auto-Party (2026-08-30, pedido do usuário: "coloca um
    auto-party. Que pega as restrições do andar p montar a pt com maior
    CP") - maximiza CP total dentro do que a `restricao` do andar permite.
    Estratégia gulosa: parte do TOP N por power puro (o melhor caso já é
    válido pra maioria dos andares, `restricao=None`) e só troca o mínimo
    necessário pra cumprir a restrição quando ela não é satisfeita de
    graça."""
    if restricao == "so_dps":
        validos = [c for c in pool if c["categoria_combate"] not in ("Tank", "Support")]
        return sorted(validos, key=lambda c: c["power"], reverse=True)[:tamanho]

    selecionados = sorted(pool, key=lambda c: c["power"], reverse=True)[:tamanho]
    if restricao is None:
        return selecionados
    if restricao == "min_tank":
        return _garantir_categoria(selecionados, pool, "Tank")
    if restricao == "min_support":
        return _garantir_categoria(selecionados, pool, "Support")
    if restricao == "max_1_tank":
        return _aplicar_max_1_tank(selecionados, pool)
    if restricao == "todas_categorias":
        return _aplicar_todas_categorias(selecionados, pool)
    return selecionados


def montar_auto_party(guild_id, user_id):
    """Substitui a Party INTEIRA (não só preenche vagas) pela combinação de
    maior CP que cumpre a restrição do andar ATUAL, usando TODA a coleção
    do jogador (não só quem já tava na Party). Devolve (ok, erro_ou_None,
    quantidade_definida) - `quantidade_definida` pode ser menor que
    `db.MAX_POSICOES_EQUIPE` se a coleção for menor que isso."""
    colecao = db.colecao_do_usuario(guild_id, user_id)
    if not colecao:
        return False, "Você ainda não tem nenhuma personagem pra montar uma Party.", 0

    andar = db.andar_atual_torre(guild_id, user_id)
    restricao = restricao_andar(andar)
    tamanho = db.MAX_POSICOES_EQUIPE

    niveis, bonus_global, cache_classe = _contexto_lote(guild_id, user_id)
    pool = []
    for p in colecao:
        power, _nivel, categoria = power_personagem(
            p, guild_id, user_id, nivel=niveis.get(p["id"], 1), bonus_global=bonus_global, cache_bonus_classe=cache_classe,
        )
        pool.append({"id": p["id"], "power": power, "categoria_combate": categoria})

    selecionados = _selecionar_auto_party(pool, restricao, tamanho)

    db.limpar_equipe(guild_id, user_id, "party")
    for posicao, personagem in enumerate(selecionados, start=1):
        db.definir_posicao_equipe(guild_id, user_id, "party", posicao, personagem["id"])

    return True, None, len(selecionados)


def preview_andar(guild_id, user_id):
    """Mostra o resultado ANTES de arriscar - como a resolução é
    determinística (sem RNG), o jogador pode saber com certeza se vai
    vencer ou não antes de clicar "Subir"; a Torre é sobre planejamento
    (nível/Party/Afinidade), não sorte. Devolve (ok, erro_ou_None,
    contexto_ou_None) - `contexto` NUNCA tem efeito colateral (nada é
    creditado/avançado aqui)."""
    contexto = _calcular_contexto(guild_id, user_id)
    if contexto is None:
        return False, "Sua Party está vazia - monte uma equipe antes de tentar a Torre.", None
    return True, None, contexto


def tentar_andar(guild_id, user_id):
    """Núcleo da Torre - MESMO cálculo de `preview_andar`, mas credita a
    recompensa e avança o andar se `venceu`. SEM RNG - perder só significa
    "a Party ainda não é forte o suficiente", tentar de novo é sempre
    permitido, sem cooldown. Devolve (ok, erro_ou_None, contexto_ou_None)."""
    contexto = _calcular_contexto(guild_id, user_id)
    if contexto is None:
        return False, "Sua Party está vazia - monte uma equipe antes de tentar a Torre.", None
    if contexto["venceu"]:
        andar = contexto["andar"]
        recompensa = recompensa_andar(andar)
        novo_saldo = db.creditar_wishards(guild_id, user_id, recompensa, "torre_andar", f"Andar {andar}", str(andar))
        novo_andar = db.avancar_andar_torre(guild_id, user_id)
        # 🔥 XP de Progressão (2026-08-30, análise do usuário Seção 12:
        # "vencer andares pode conceder XP de Progressão... em checkpoints
        # as recompensas podem ser maiores") - ×5 a cada 50 andares.
        xp = 10 * andar * (5 if andar % 50 == 0 else 1)
        db.creditar_xp_progressao(guild_id, user_id, xp)
        contexto["recompensa"] = recompensa
        contexto["novo_saldo"] = novo_saldo
        contexto["novo_andar"] = novo_andar
        contexto["xp_ganho"] = xp
    return True, None, contexto
