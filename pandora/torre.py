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


def power_final(popularidade, nivel, afinidade, is_soulmate, power_base_override=None):
    """Fórmula fechada (Seção 6): `(Power Base + Bônus de Nível) ×
    Multiplicador` - multiplicador é 2,0 se Soulmate, senão `1,0 +
    (afinidade-1)×0,10` (Afinidade 1 = 1,0×, Afinidade 10 = 1,9×).

    🔥 `power_base_override` (2026-09-03, `pandora.personagens_favoritas`) -
    Personagem Favorita substitui só o Power Base NATURAL (`power_base(
    popularidade)`) pelo Power Base efetivo do slot (300-1000 por
    Fortalecimento, além disso por Ascensão) - o resto da fórmula (bônus de
    nível fixo, multiplicador de Afinidade/Soulmate) continua IDÊNTICO,
    pedido explícito do usuário: "não alterar a fórmula original... Nível/
    Afinidade/Soulmate continuam participando normalmente"."""
    base_natural = power_base_override if power_base_override is not None else power_base(popularidade)
    base = base_natural + (nivel - 1) * BONUS_POWER_POR_NIVEL
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


def power_personagem(personagem, guild_id, user_id, nivel=None, bonus_global=None, cache_bonus_classe=None, bonus_series=None, favoritas_ocupantes=None):
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
    funcionando igual, sem passar nada disso - cai no fallback de sempre.

    🔥 `favoritas_ocupantes` (2026-09-03, `pandora.personagens_favoritas`,
    opcional) - `{personagem_id: {"fortalecimento_bitmask", "nivel_ascensao"}}`
    pré-carregado (ver `_contexto_lote`), mesmo padrão de `bonus_series` -
    se essa personagem ocupa um slot de Personagem Favorita, o Power Base
    NATURAL é substituído pelo efetivo do slot (`power_base_override` em
    `power_final`) - import LOCAL (não no topo do arquivo) porque
    `personagens_favoritas.py` importa `torre` (`power_base`), import no
    topo dos dois viraria ciclo."""
    if nivel is None:
        nivel = db.nivel_personagem(guild_id, user_id, personagem["id"])
    power_base_override = None
    if favoritas_ocupantes and personagem["id"] in favoritas_ocupantes:
        from pandora import personagens_favoritas
        ocupante = favoritas_ocupantes[personagem["id"]]
        elegivel = personagens_favoritas.elegivel_ascensao(
            personagem, nivel,
            personagens_favoritas._estado_fortalecimento(personagem["popularidade"], ocupante["fortalecimento_bitmask"])[0],
        )
        power_base_override = personagens_favoritas.power_efetivo(
            personagem["popularidade"], ocupante["fortalecimento_bitmask"], ocupante["nivel_ascensao"], elegivel,
        )
    power = power_final(
        personagem["popularidade"], nivel, personagem.get("afinidade", 1), bool(personagem.get("is_soulmate")),
        power_base_override=power_base_override,
    )
    if bonus_global is None:
        bonus_global = db.bonus_cp_global(guild_id, user_id)
    bonus_fixo, bonus_percentual = bonus_global
    classe = personagem.get("classe")
    # 🔥 `categoria_combate_da_classe` também entra no cache (2026-09-01,
    # achado do usuário: "Quando fui upar level apenas de 1 personagem
    # para o maximo, gaia nao respondeu a tempo") - só `bonus_cp_classe`
    # era cacheado antes; `categoria_personagem` (que faz sua PRÓPRIA
    # consulta) continuava rodando pra TODA personagem da coleção, mesmo
    # repetindo a MESMA classe centenas de vezes (ex.: 44 "Guerreiro" =
    # 44 conexões SQLite idênticas) - `db.conexao()` não faz pool, então
    # isso sozinho dominava o tempo de `cidade._workforce_por_funcao`
    # (2,7s pra ~1.100 personagens, quase tudo nessa 2ª consulta por
    # classe). Cache guarda os 2 valores juntos por classe agora.
    if cache_bonus_classe is not None:
        # 🔥 3º elemento (`funcao_cidade`) é ignorado aqui de propósito -
        # não é usado por `power_personagem`, só existe nesta tupla pra
        # `cidade._workforce_por_funcao` reaproveitar o MESMO cache (ver
        # `db.info_classes_em_lote`) sem precisar de outra consulta.
        if classe not in cache_bonus_classe:
            cache_bonus_classe[classe] = (
                db.bonus_cp_classe(guild_id, user_id, classe),
                categoria_personagem(personagem),
                db.funcao_cidade_da_classe(classe),
            )
        bonus_classe, categoria, _funcao_cidade = cache_bonus_classe[classe]
    else:
        bonus_classe = db.bonus_cp_classe(guild_id, user_id, classe)
        categoria = categoria_personagem(personagem)
    # 🔥 Bônus de Série Favorita (2026-09-02, pedido do usuário) - só afeta
    # personagens DAQUELA série (nunca CP global, "isso inevitavelmente vira
    # outra fonte enorme de power creep") - lido do snapshot pré-calculado
    # (`db.bonus_series_favoritas`, via `_contexto_lote`), nunca recalculado
    # aqui (calcular completude de série é caro, ver `pandora.series_
    # favoritas`). Chamada avulsa (sem `bonus_series`) simplesmente não
    # aplica bônus nenhum, mesmo padrão de `bonus_global`/`cache_bonus_
    # classe` opcionais.
    bonus_serie = bonus_series.get(personagem.get("serie"), 0.0) if bonus_series else 0.0
    power = (power + bonus_fixo + bonus_classe) * (1 + bonus_percentual) * (1 + bonus_serie)
    return power, nivel, categoria


def _contexto_lote(guild_id, user_id):
    """Nível/bônus global pré-carregados 1x + cache de bônus/categoria por
    classe JÁ PREENCHIDO (2026-09-01, achado do usuário: "upar level de 1
    personagem pro maximo... gaia nao respondeu a tempo") - `db.info_
    classes_em_lote` resolve TODA classe da coleção numa query só, em vez
    de deixar `power_personagem` abrir 1 conexão nova por classe DISTINTA
    encontrada durante o loop (ainda seria N+1, só que por classe em vez
    de por personagem - pra muitas classes diferentes, isso sozinho já
    dominava o tempo de `cidade._workforce_por_funcao`). 🔥 4º item,
    `bonus_series` (2026-09-02) - snapshot de bônus por Série Favorita
    (`db.bonus_series_favoritas`), mesma lógica: 1 leitura barata aqui em
    vez de `power_personagem` consultar por personagem. 🔥 5º item,
    `favoritas_ocupantes` (2026-09-03) - mesma lógica, pra Personagem
    Favorita (`db.personagens_favoritas_ocupantes`)."""
    return (
        db.nivel_em_lote(guild_id, user_id), db.bonus_cp_global(guild_id, user_id),
        dict(db.info_classes_em_lote(guild_id, user_id)), db.bonus_series_favoritas(guild_id, user_id),
        db.personagens_favoritas_ocupantes(guild_id, user_id),
    )


def ordenar_por_power(personagens, guild_id, user_id, contexto_lote=None):
    """Ordena do MAIOR pro menor CP (2026-08-30, pedido do usuário: "Todo
    dropdwon q listar waifu, sempre ordene pelas com maior CP/
    popularidade") - só faz sentido pra personagens JÁ POSSUÍDAS (usa
    `power_personagem`, que depende de Nível/Afinidade do vínculo); pra
    lista de personagens NÃO possuídas (loja/wishlist), usar `consulta.
    ordenar_por_popularidade` em vez desta.

    🔥 `contexto_lote` opcional (2026-09-06, achado do usuário: "na hora de
    adicionar membros a party, apos colocar a role, demora um pouco p
    aparecer as personagens daquela role") - quem já filtrou/vai descrever
    a MESMA lista por perto (ex.: `paineis._abrir_adicionar`, que também
    filtra por categoria e monta a descrição do dropdown) pode pré-carregar
    1x e passar aqui, em vez desta função abrir sua PRÓPRIA consulta
    `_contexto_lote` de novo - reduz de 3 idas ao banco (filtro + esta
    função + descrição) pra 1 só. `None` (padrão) mantém o comportamento de
    sempre, busca sozinha."""
    if contexto_lote is None:
        contexto_lote = _contexto_lote(guild_id, user_id)
    niveis, bonus_global, cache_classe, bonus_series, favoritas_ocupantes = contexto_lote

    def _power(p):
        nivel = niveis.get(p["id"], 1)
        return power_personagem(
            p, guild_id, user_id, nivel=nivel, bonus_global=bonus_global, cache_bonus_classe=cache_classe,
            bonus_series=bonus_series, favoritas_ocupantes=favoritas_ocupantes,
        )[0]

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


def _calcular_contexto(guild_id, user_id, ignorar_restricao=False):
    """Cálculo PURO (sem efeito colateral) - reaproveitado por `preview_
    andar` (mostra antes de arriscar, resolução é determinística, então
    "planejar antes de clicar" faz sentido de verdade aqui) e `tentar_
    andar` (mesmo cálculo + credita recompensa/avança andar só se
    venceu). Devolve `None` se a Party estiver vazia.

    `ignorar_restricao` (2026-09-01, item 🗝️ Chave da Torre) - "a Chave
    não reduz o Power necessário e não garante vitória, só remove a
    restrição daquele andar"."""
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
            "id": p["id"],
            "nome": p["nome"],
            "nivel": nivel,
            "afinidade": p.get("afinidade", 1),
            "is_soulmate": bool(p.get("is_soulmate")),
            "categoria_combate": categoria,
            "power": power,
        })
    power_total, categorias = calcular_power_party(membros, guild_id, user_id)
    restricao_ok = True if ignorar_restricao else checar_restricao(restricao, categorias)
    venceu = restricao_ok and power_total >= alvo

    return {
        "andar": andar, "alvo": alvo, "restricao": restricao, "restricao_ok": restricao_ok,
        "power_total": power_total, "membros": membros, "venceu": venceu,
        "restricao_ignorada": ignorar_restricao,
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

    niveis, bonus_global, cache_classe, bonus_series, favoritas_ocupantes = _contexto_lote(guild_id, user_id)
    pool = []
    for p in colecao:
        power, _nivel, categoria = power_personagem(
            p, guild_id, user_id, nivel=niveis.get(p["id"], 1), bonus_global=bonus_global, cache_bonus_classe=cache_classe,
            bonus_series=bonus_series, favoritas_ocupantes=favoritas_ocupantes,
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
    chave_ativa = db.chave_torre_ativa(guild_id, user_id)
    contexto = _calcular_contexto(guild_id, user_id, ignorar_restricao=chave_ativa)
    if contexto is None:
        return False, "Sua Party está vazia - monte uma equipe antes de tentar a Torre.", None
    return True, None, contexto


def tentar_andar(guild_id, user_id):
    """Núcleo da Torre - MESMO cálculo de `preview_andar`, mas credita a
    recompensa e avança o andar se `venceu`. SEM RNG - perder só significa
    "a Party ainda não é forte o suficiente", tentar de novo é sempre
    permitido, sem cooldown. Devolve (ok, erro_ou_None, contexto_ou_None).

    🔥 Chave da Torre (2026-09-01) - consumida NA TENTATIVA (vença ou
    perca), nunca só na vitória - a Chave paga pelo direito de tentar sem
    a restrição, não pelo resultado."""
    chave_ativa = db.chave_torre_ativa(guild_id, user_id)
    contexto = _calcular_contexto(guild_id, user_id, ignorar_restricao=chave_ativa)
    if contexto is None:
        return False, "Sua Party está vazia - monte uma equipe antes de tentar a Torre.", None
    if chave_ativa:
        db.definir_chave_torre_ativa(guild_id, user_id, False)
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
        # 🔥 Estatística por personagem (2026-09-01, pedido do usuário:
        # "estatísticas de participação com sucesso na torre por
        # personagens") - só em vitória, nunca em tentativa perdida.
        db.registrar_vitoria_torre_personagens(guild_id, user_id, [m["id"] for m in contexto["membros"]])
        contexto["recompensa"] = recompensa
        contexto["novo_saldo"] = novo_saldo
        contexto["novo_andar"] = novo_andar
        contexto["xp_ganho"] = xp
    return True, None, contexto


_LIMITE_ANDARES_SUBIR_MAX = 2000  # segurança contra loop infinito - inatingível numa conta real (custo cresce 6%/andar)


def subir_max(guild_id, user_id):
    """"Subir Max" (2026-09-04, pedido do usuário: "usado Subir torre ate
    o máximo possível mas seguindo as regras por andar e trocando de time
    p considerar ela") - sobe andar por andar em loop até perder, escolhendo
    pra CADA andar a mesma composição de maior CP que `montar_auto_party`
    já escolheria pro andar atual (respeitando a restrição de categoria
    dele, `RESTRICOES_ANDAR`).

    Como nenhuma personagem sobe de Nível/Afinidade durante o loop, a
    MELHOR composição pra cada um dos 6 padrões de restrição é a MESMA
    em todo andar que usa aquele padrão - pré-calculada 1x fora do loop
    (`composicoes`), nunca recalculada andar a andar. A Party só é
    REGRAVADA no banco quando a composição realmente muda de um andar pro
    próximo (a restrição cicla de 6 em 6, então a maioria dos andares
    reaproveita a mesma Party sem escrita nenhuma) - "trocando de time p
    considerar ela" é EXATAMENTE essa troca, automática, sem precisar
    clicar "Auto-Party" a cada mudança de restrição na mão.

    🗝️ Chave da Torre - mesma regra de `tentar_andar` (consumida na
    tentativa, vença ou perca), só que aqui só pode valer pro 1º andar do
    loop (não dá pra "ignorar restrição" o tempo todo) - usa a composição
    SEM restrição nenhuma (maior CP possível, `composicoes[None]`) só
    nessa 1ª tentativa, mesmo que o andar real peça outra coisa.

    Devolve um dict-resumo (nunca `None`) com `andares_subidos`,
    `andar_inicial`, `andar_final`, `recompensa_total`, `xp_total`,
    `motivo_parada` (`"sem_colecao"`, `"restricao_impossivel"`,
    `"power_insuficiente"` ou `"limite_seguranca"`) e `restricao_travada`
    (descrição da restrição que travou o avanço, `None` se foi por power).
    Nunca lança erro - Party vazia/coleção vazia só zera `andares_subidos`."""
    colecao = db.colecao_do_usuario(guild_id, user_id)
    andar_inicial = db.andar_atual_torre(guild_id, user_id)
    if not colecao:
        return {
            "andares_subidos": 0, "andar_inicial": andar_inicial, "andar_final": andar_inicial,
            "recompensa_total": 0, "xp_total": 0, "motivo_parada": "sem_colecao", "restricao_travada": None,
        }

    tamanho = db.MAX_POSICOES_EQUIPE
    niveis, bonus_global, cache_classe, bonus_series, favoritas_ocupantes = _contexto_lote(guild_id, user_id)
    pool = []
    for p in colecao:
        power, _nivel, categoria = power_personagem(
            p, guild_id, user_id, nivel=niveis.get(p["id"], 1), bonus_global=bonus_global,
            cache_bonus_classe=cache_classe, bonus_series=bonus_series, favoritas_ocupantes=favoritas_ocupantes,
        )
        pool.append({"id": p["id"], "power": power, "categoria_combate": categoria})

    # 🔥 1 composição por padrão de RESTRIÇÃO (nunca por andar) - `None`
    # (já incluso em `RESTRICOES_ANDAR`) é a composição "sem restrição",
    # usada pela Chave.
    composicoes = {}
    for restricao in set(RESTRICOES_ANDAR):
        selecionados = _selecionar_auto_party(pool, restricao, tamanho)
        power_total, categorias = calcular_power_party(selecionados, guild_id, user_id)
        composicoes[restricao] = {
            "ids": [c["id"] for c in selecionados],
            "power_total": power_total,
            "restricao_ok": checar_restricao(restricao, categorias),
        }

    chave_ativa = db.chave_torre_ativa(guild_id, user_id)
    equipe_atual_ids = {p["id"] for p in db.obter_equipe(guild_id, user_id, "party").values()}
    andar = andar_inicial
    recompensa_total = 0
    xp_total = 0
    motivo_parada = "power_insuficiente"
    restricao_travada = None

    for indice in range(_LIMITE_ANDARES_SUBIR_MAX):
        restricao = restricao_andar(andar)
        alvo = power_alvo_andar(andar)
        usar_chave_aqui = chave_ativa and indice == 0
        comp = composicoes[None] if usar_chave_aqui else composicoes[restricao]
        if not usar_chave_aqui and not comp["restricao_ok"]:
            motivo_parada = "restricao_impossivel"
            restricao_travada = descricao_restricao(restricao)
            break
        if comp["power_total"] < alvo:
            motivo_parada = "power_insuficiente"
            break
        if set(comp["ids"]) != equipe_atual_ids:
            db.limpar_equipe(guild_id, user_id, "party")
            for posicao, personagem_id in enumerate(comp["ids"], start=1):
                db.definir_posicao_equipe(guild_id, user_id, "party", posicao, personagem_id)
            equipe_atual_ids = set(comp["ids"])
        if usar_chave_aqui:
            db.definir_chave_torre_ativa(guild_id, user_id, False)
        recompensa = recompensa_andar(andar)
        db.creditar_wishards(guild_id, user_id, recompensa, "torre_andar", f"Andar {andar}", str(andar))
        xp = 10 * andar * (5 if andar % 50 == 0 else 1)
        db.creditar_xp_progressao(guild_id, user_id, xp)
        db.registrar_vitoria_torre_personagens(guild_id, user_id, comp["ids"])
        andar = db.avancar_andar_torre(guild_id, user_id)
        recompensa_total += recompensa
        xp_total += xp
    else:
        motivo_parada = "limite_seguranca"

    if chave_ativa and andar == andar_inicial:
        # 🔥 Chave consumida mesmo perdendo o 1º andar (mesma regra de
        # `tentar_andar` - "paga pelo direito de tentar, não pelo
        # resultado") - se o loop já venceu pelo menos 1 andar, a Chave já
        # foi consumida dentro do loop acima; só falta cobrir quem perdeu
        # de cara e nunca entrou no bloco `usar_chave_aqui`.
        db.definir_chave_torre_ativa(guild_id, user_id, False)

    return {
        "andares_subidos": andar - andar_inicial, "andar_inicial": andar_inicial, "andar_final": andar,
        "recompensa_total": recompensa_total, "xp_total": xp_total,
        "motivo_parada": motivo_parada, "restricao_travada": restricao_travada,
    }


def _investir_em_massa(guild_id, user_id, orcamento, nivel_maximo, obter_atual, custo_ate, subir_ate, colecao=None):
    """Motor genérico (2026-09-01, pedido do usuário: "permitir aumentar
    afinidade e nível em massa das personagens ordenadas pelo de maior
    CP, apenas informando qnt pretende investir") - percorre a coleção
    ORDENADA POR CP (maior primeiro, mesmo critério de sempre), gastando
    o orçamento na personagem atual até ela bater no máximo ou o
    orçamento acabar, só então passando pra próxima. `obter_atual(p)`/
    `custo_ate(p, atual, alvo)`/`subir_ate(p, alvo)` isolam a única
    diferença entre Nível (WiShards) e Afinidade (Soulstone) - reaproveita
    a MESMA varredura/ordenação pras duas, nunca 2 cópias do loop.
    `colecao` (opcional, 2026-09-03, pedido do usuário: "botao la tbm p
    maximizar nivel e afinidade da serie, assim como é o em massa") -
    escopo alternativo à coleção INTEIRA (default `None` = `db.
    colecao_do_usuario`), usado pelo navegador de Série Favorita pra
    investir só nas personagens QUE O JOGADOR JÁ POSSUI daquela série.
    Devolve (gasto_total, detalhes) - `detalhes` só de quem realmente
    mudou, na ordem investida."""
    if colecao is None:
        colecao = db.colecao_do_usuario(guild_id, user_id)
    colecao = ordenar_por_power(colecao, guild_id, user_id)
    saldo_restante = orcamento
    detalhes = []
    for personagem in colecao:
        if saldo_restante <= 0:
            break
        atual = obter_atual(personagem)
        if atual >= nivel_maximo:
            continue
        melhor_alvo = atual
        for alvo in range(atual + 1, nivel_maximo + 1):
            if custo_ate(personagem, atual, alvo) <= saldo_restante:
                melhor_alvo = alvo
            else:
                break
        if melhor_alvo > atual:
            custo_final = custo_ate(personagem, atual, melhor_alvo)
            ok, _mensagem = subir_ate(personagem, melhor_alvo)
            if ok:
                saldo_restante -= custo_final
                detalhes.append((personagem, atual, melhor_alvo))
    return orcamento - saldo_restante, detalhes


def investir_nivel_em_massa(guild_id, user_id, orcamento_wishards, colecao=None):
    """Sobe Nível (WiShards) da MAIOR CP pra menor - Seção acima."""
    return _investir_em_massa(
        guild_id, user_id, orcamento_wishards, db.NIVEL_MAXIMO_PERSONAGEM,
        obter_atual=lambda p: db.nivel_personagem(guild_id, user_id, p["id"]),
        custo_ate=lambda p, atual, alvo: db.custo_total_ate_nivel(p["raridade"], atual, alvo),
        subir_ate=lambda p, alvo: db.subir_nivel_ate(guild_id, user_id, p["id"], alvo),
        colecao=colecao,
    )


def investir_afinidade_em_massa(guild_id, user_id, orcamento_soulstone, colecao=None):
    """Sobe Afinidade (Soulstone) da MAIOR CP pra menor - Seção acima."""
    return _investir_em_massa(
        guild_id, user_id, orcamento_soulstone, db.NIVEL_MAXIMO_AFINIDADE,
        obter_atual=lambda p: db.afinidade(guild_id, user_id, p["id"]),
        custo_ate=lambda p, atual, alvo: db.custo_total_ate_afinidade(atual, alvo),
        subir_ate=lambda p, alvo: db.subir_afinidade_ate(guild_id, user_id, p["id"], alvo),
        colecao=colecao,
    )
