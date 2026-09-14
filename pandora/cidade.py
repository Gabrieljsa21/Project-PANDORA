# -*- coding: utf-8 -*-
"""Cidade (2026-08-30, v2 - efeitos diferenciados por área) - análise
trazida pelo usuário (Seção 13) + pedido explícito: "n iremos setar
personagens em funcoes manualmente, sera automatico com base na classe/
profissão". Personagens possuídas que NÃO estão na Party "trabalham"
sozinhas, sem nenhum toggle/configuração - `funcao_cidade` (2º campo
derivado da classe, mesmo espírito de `categoria_combate`, ver
`pandora.db.definir_classe_personagem`) decide onde cada uma entra.

v1 (todas as 7 funções produzindo na MESMA taxa) virou v2 - cada área
tem um efeito PRÓPRIO, 2 famílias mecânicas diferentes (a MESMA fórmula
de marco por baixo das duas, só o que ela produz muda):
- Saúde/Cultura/Comércio geram RECURSO ACUMULADO NO TEMPO (Soulstone/XP/
  WiShards por hora, pull-based, sem scheduler - `coletar_producao_
  pendente` calcula tudo a partir do timestamp salvo, na hora que o
  jogador abre o painel "🏙️ Cidade").
- Militar/Arcano/Administração são BÔNUS DE CP AO VIVO pra Party (não dá
  pra "acumular" um bônus percentual no tempo - é um modificador de
  estado, não um recurso). Pra não escanear a coleção INTEIRA a cada
  cálculo de Torre (que roda muito mais vezes que a visita à Cidade),
  esses 3 (+ o "Bônus da Coleção", 4º ingrediente à parte) são
  calculados e GRAVADOS como SNAPSHOT junto com o timestamp
  (`db.definir_cidade_ultima_producao`) - `torre.calcular_power_party`
  só LÊ esse snapshot (`db.cidade_bonus_party`), nunca recalcula a
  partir da coleção inteira.

Módulo PRÓPRIO (não `db.py`) porque precisa de `torre.power_personagem`
pro CP de cada trabalhador - `db.py` não pode importar `torre` (`torre.py`
já importa `db.py`, viraria ciclo)."""
from datetime import datetime, timezone

from pandora import db, torre

# 🔥 Taxonomia FECHADA v2 (2026-08-30) - "Produção"/"Serviço" SAÍRAM,
# "Arcano" ENTROU (absorveu o que era místico/oculto de Cultura/Serviço -
# ver script de remigração `remigrar_funcao_cidade_2026-08-30.py`). Toda
# classe (combatente ou civil) mapeia OBRIGATORIAMENTE pra uma destas,
# nunca uma função nova (mesmo princípio de `categoria_combate`: a IA
# decide o aberto/temático - a classe -, o código valida o fechado/
# mecânico - a função). Alias pra `db.AREAS_CONSTRUCAO` (2026-09-03,
# unificado com o que era `itens.AREAS_CONSTRUCAO`, mesma lista - ver
# comentário lá) - era um tuple próprio idêntico, fonte única agora.
FUNCOES_CIDADE = db.AREAS_CONSTRUCAO

_ICONE_FUNCAO = {
    "Militar": "⚔️", "Saúde": "⚕️", "Cultura": "🎭",
    "Administração": "📜", "Comércio": "🏪", "Arcano": "🔮",
}

# 🔥 Marcos da Cidade por Construção (2026-09-07) - substitui de vez o
# "Poder da Área" (CP + quantidade ponderados, que ainda restava em
# Saúde/Cultura/Comércio) E o marco com retorno decrescente que Militar/
# Arcano/Administração tinham desde ontem. Pedido do usuário, com
# fórmula e exemplos numéricos próprios que bateram exato: "M =
# floor(P/5); B_marco = B_base × Lv; B_total = M × B_marco" - cada 5
# personagens trabalhando na área vira 1 marco, sem bônus parcial entre
# marcos e SEM retorno decrescente (a única diminuição de retorno de
# todo o jogo continua sendo o Bônus por Classe, `db.pontos_por_marco`/
# `FAIXAS_BONUS_CLASSE`, intocado - não faz parte deste pedido, nem o
# Bônus da Coleção, que segue com a MESMA lógica de antes, sem
# Construção própria).
#
# O Nível da Construção MULTIPLICA DIRETO o bônus-base de cada marco
# (Lv10 = 10×, substituindo de vez o antigo `1 + 0.10×nível`). Uma área
# sem NENHUM Upgrade de Construção comprado já rende o bônus do Lv1, não
# zero (2026-09-07, "tem q começar ja no lv1" - correção no mesmo dia da
# 1ª versão, que zerava tudo em Lv0) - `nivel_efetivo_construcao` aplica
# esse piso só pro BÔNUS/exibição da Cidade; `db.nivel_construcao` (0 se
# nunca comprado) continua cru pra quem precisa saber quantos Upgrades já
# foram gastos de verdade (teto dinâmico, dropdown de comprar/usar).
#
# Valores-base (por marco, no Lv1) calibrados pra ficar perto da última
# recalibração numa conta real: Militar Lv10/2901 trabalhadores -> +58K
# CP; Administração Lv20/841 -> +16,8%; Arcano Lv10/683 -> +13,6%; Saúde
# Lv20/194 -> +380 Soulstone/h; Cultura Lv10/470 -> +23,5K XP/h; Comércio
# Lv19/1331 -> +1,26M WiShards/h - todos os 6 conferidos 1 a 1 contra os
# exemplos do próprio usuário antes de aplicar.
MARCO_QUANTIDADE_CIDADE = 5
BONUS_BASE_POR_AREA = {
    "Militar": 10,             # CP fixo p/ Party, por marco, no Lv1
    "Saúde": 0.5,              # Soulstone/h, por marco, no Lv1
    "Cultura": 25,             # XP de Progressão/h, por marco, no Lv1
    "Administração": 0.00005,  # fração (0,005%) de eficiência das outras áreas, por marco, no Lv1
    # 🔥 Reduzido de 250 pra 50 (2026-09-07, pedido do usuário: "a partir
    # da decisão de reduzir o Comércio para base 50" - Comércio estava
    # rendendo WiShards desproporcionalmente rápido perto do custo NOVO
    # de Upar Construção, ver `itens.FAIXAS_CUSTO_CONSTRUCAO` - conferido
    # contra a tabela do próprio usuário: 269 marcos atuais, Lv100 (Militar
    # e Administração também no Lv100 nesse cenário) -> 2,55M WiShards/h).
    "Comércio": 50,            # WiShards/h, por marco, no Lv1
    "Arcano": 0.0001,          # fração (0,01%) de CP p/ Party, por marco, no Lv1
}
# 👑 Bônus da Coleção (2026-09-08): CP total da coleção vira bônus linear
# de loot. 308M CP = 3,08 = +308%, portanto recompensas ×4,08.
CP_COLECAO_POR_PERCENTUAL_LOOT = 1_000_000
TETO_HORAS_ACUMULO = 168  # 7 dias - evita acúmulo sem limite se ninguém abrir o painel por meses


def icone_funcao(funcao):
    return _ICONE_FUNCAO.get(funcao, "❓")


def marcos_ativos(personagens):
    return personagens // MARCO_QUANTIDADE_CIDADE


def progresso_marco(personagens):
    """(marco_atual, proximo_marco), EM PERSONAGENS - `marco_atual` é o
    último múltiplo de `MARCO_QUANTIDADE_CIDADE` (5) já coberto,
    `proximo_marco` sempre `marco_atual + 5` (nunca bônus parcial entre
    os dois)."""
    marco_atual = marcos_ativos(personagens) * MARCO_QUANTIDADE_CIDADE
    return marco_atual, marco_atual + MARCO_QUANTIDADE_CIDADE


def multiplicador_nivel(funcao, nivel_construcao):
    """Multiplicador do nível de Construção para uma área.

    Militar e Arcano usam a curva própria `Lv × 0,05`; as demais áreas
    preservam o multiplicador integral do nível. O nível recebido já é o
    efetivo.
    """
    if funcao in ("Militar", "Arcano"):
        return nivel_construcao * 0.05
    return nivel_construcao


def bonus_area(funcao, personagens, nivel_construcao):
    """Bônus-base da área antes do cruzamento da Administração.

    Militar/Arcano: `floor(P/5) × B_base × (Lv × 0,05)`.
    Demais áreas: `floor(P/5) × B_base × Lv`.
    `nivel_construcao` aqui já deve vir EFETIVO (`nivel_efetivo_
    construcao`, nunca 0 - "tem q começar ja no lv1", pedido do usuário
    2026-09-07: o bônus da área já existe no Lv1 mesmo sem NUNCA ter
    comprado um Upgrade de Construção pra ela; Lv0 zerando tudo, do
    palpite inicial, foi corrigido no mesmo dia)."""
    return marcos_ativos(personagens) * BONUS_BASE_POR_AREA[funcao] * multiplicador_nivel(funcao, nivel_construcao)


def bonus_por_marco(funcao, nivel_construcao):
    """Valor de CADA marco individual (não o total), ver `bonus_area`.
    Exposto separado (2026-09-07, especificação do usuário
    em `PANDORA_marcos_cidade.md`: "Cada 5 personagens: +100 CP") pra
    exibição - a tela de detalhe mostra isso junto do total, não só o
    total."""
    return BONUS_BASE_POR_AREA[funcao] * multiplicador_nivel(funcao, nivel_construcao)


def nivel_efetivo_construcao(guild_id, user_id, funcao):
    """Nível de Construção pra fins de BÔNUS/exibição na Cidade - nunca
    menor que 1 (2026-09-07, "tem q começar ja no lv1": uma área sem
    NENHUM Upgrade de Construção comprado ainda já rende o bônus do Lv1,
    não zero). `db.nivel_construcao` (0 se nunca comprado) continua CRU
    em todo lugar que precisa saber quantos Upgrades já foram
    efetivamente gastos (ex.: `teto_atual_construcao`, o dropdown de
    comprar/usar Upgrade) - só a Cidade (bônus e o que ela exibe) usa o
    piso de 1."""
    return max(db.nivel_construcao(guild_id, user_id, funcao), 1)


def _workforce_por_funcao(guild_id, user_id):
    """Escaneia a coleção INTEIRA 1x só - devolve (cp_total_colecao,
    por_funcao, total_personagens). `cp_total_colecao`/`total_personagens`
    incluem TODO MUNDO (dentro ou fora da Party) - `total_personagens`
    (2026-09-06, Bônus da Coleção virou marco) é só `len(colecao)`, sem
    custo extra (a coleção inteira já precisava ser carregada aqui pra
    somar `cp_total_colecao`). `por_funcao` ({funcao: {"qtd", "cp"}}) só
    conta quem NÃO está na Party (mesmo critério de sempre - "personagens
    fora da Party trabalham") e já tem `classe` revelada. `cp` aqui é só
    INFORMATIVO pro painel (2026-09-07, a fórmula de bônus não depende
    mais de CP nenhum, só de quantidade - ver `bonus_area`).

    🔥 `torre._contexto_lote` (2026-09-01, achado do usuário: "Quando fui
    upar level apenas de 1 personagem para o maximo, gaia nao respondeu a
    tempo") - antes chamava `torre.power_personagem` SEM `nivel`/
    `bonus_global`/`cache_bonus_classe`, então CADA personagem da coleção
    abria suas PRÓPRIAS conexões SQLite novas (nível + bônus global +
    bônus de classe) - pra uma coleção de milhares, isso é o MESMO N+1 já
    corrigido no Auto-Party há tempo, só que nunca tinha sido aplicado
    aqui. `atualizar_snapshot_bonus` (chamado depois de Upar Nível/
    Afinidade/Divorciar/Merge/Party) passa por esta função - o N+1 tornava
    QUALQUER uma dessas ações lenta pra coleção grande."""
    equipe_party = db.obter_equipe(guild_id, user_id, "party")
    ids_na_party = {p["id"] for p in equipe_party.values()}
    colecao = db.colecao_do_usuario(guild_id, user_id)
    niveis, bonus_global, cache_classe, bonus_series, favoritas_ocupantes = torre._contexto_lote(guild_id, user_id)

    cp_total_colecao = 0.0
    por_funcao = {}
    for personagem in colecao:
        nivel = niveis.get(personagem["id"], 1)
        power, _nivel, _categoria = torre.power_personagem(
            personagem, guild_id, user_id, nivel=nivel, bonus_global=bonus_global, cache_bonus_classe=cache_classe,
            bonus_series=bonus_series, favoritas_ocupantes=favoritas_ocupantes,
        )
        cp_total_colecao += power
        if personagem["id"] in ids_na_party:
            continue
        # 🔥 Lê do MESMO cache de `torre._contexto_lote` (2026-09-01,
        # achado do usuário: "upar level de 1 personagem pro maximo...
        # gaia nao respondeu a tempo") - antes chamava `db.funcao_cidade_
        # da_classe` por PERSONAGEM (não só por classe distinta), abrindo
        # 1 conexão SQLite nova por item da coleção inteira; `cache_
        # classe[classe]` já foi populado com `(bonus_cp, categoria,
        # funcao_cidade)` numa única query (`db.info_classes_em_lote`).
        classe = personagem.get("classe")
        _bonus_cp, _categoria, funcao = cache_classe.get(classe, (0, None, None))
        if funcao is None:
            continue
        entrada = por_funcao.setdefault(funcao, {"qtd": 0, "cp": 0.0})
        entrada["qtd"] += 1
        entrada["cp"] += power
    return cp_total_colecao, por_funcao, len(colecao)


def bonus_loot_colecao(cp_total_colecao):
    """Fração adicional de loot da coleção: 1M CP = +1%, sem teto."""
    return cp_total_colecao / (CP_COLECAO_POR_PERCENTUAL_LOOT * 100)


def _bonus_todas_areas(guild_id, user_id, por_funcao):
    """`bonus_por_area` cobre as 6 áreas via `bonus_area` (marco direto por
    por_area` cobre as 6 áreas via `bonus_area` (marco direto por
    Construção, 2026-09-07). Administração nunca recebe seu próprio
    cross-bonus, as outras 5 recebem `(1 + bonus_admin)` por cima do
    próprio bônus (regra já existente, mantida - "a Administração
    continua aumentando a eficiência das outras áreas conforme a regra
    já existente no sistema", palavras do usuário). Bônus da Coleção
    não participa aqui: ele é um multiplicador de loot baseado no CP total
    da coleção, calculado por `bonus_loot_colecao`."""
    def _qtd(funcao):
        dados = por_funcao.get(funcao)
        return dados["qtd"] if dados else 0

    nivel_admin = nivel_efetivo_construcao(guild_id, user_id, "Administração")
    bonus_admin = bonus_area("Administração", _qtd("Administração"), nivel_admin)

    bonus_por_area = {"Administração": bonus_admin}
    for funcao in ("Militar", "Saúde", "Cultura", "Comércio", "Arcano"):
        nivel = nivel_efetivo_construcao(guild_id, user_id, funcao)
        bonus_por_area[funcao] = bonus_area(funcao, _qtd(funcao), nivel) * (1 + bonus_admin)

    return bonus_por_area


def taxa_xp_progressao_por_hora(guild_id, user_id):
    """Produção atual de Cultura, usada como referência do próximo nível."""
    _cp, por_funcao, _total = _workforce_por_funcao(guild_id, user_id)
    return _bonus_todas_areas(guild_id, user_id, por_funcao)["Cultura"]


def coletar_producao_pendente(guild_id, user_id):
    """Credita Soulstone/XP/WiShards acumulados desde a última visita ao
    painel "🏙️ Cidade" (ou não credita nada e só liga o relógio, na 1ª
    vez) E atualiza snapshots de Militar/Arcano para Party e do bônus de
    loot da Coleção. Devolve um dict com o resumo
    completo - inclui tanto o ACUMULADO desde a última visita (`wishards`/
    `xp`/`soulstone`, usado no resumo do topo do painel) quanto as TAXAS
    atuais por hora/bônus ao vivo (`taxas_por_funcao`, usado pra mostrar
    "capacidade atual" de cada área - 2026-08-30, pedido do usuário: "o
    painel deve mostrar sempre o bônus atual por hora, independentemente
    de quanto tempo passou desde a última coleta")."""
    agora = datetime.now(timezone.utc)
    ultima = db.cidade_ultima_producao(guild_id, user_id)
    if ultima is None:
        db.definir_cidade_ultima_producao(guild_id, user_id, agora)
        atualizar_snapshot_bonus(guild_id, user_id)
        return {
            "wishards": 0, "xp": 0, "soulstone": 0, "horas": 0.0, "cp_total": 0.0, "total_personagens": 0,
            "por_funcao": {}, "primeira_visita": True, "bonus_militar_fixo": 0.0, "bonus_arcano_percentual": 0.0,
            "bonus_colecao_loot_percentual": 0.0, "bonus_administracao_percentual": 0.0, "taxas_por_funcao": {},
        }

    horas = min((agora - ultima).total_seconds() / 3600, TETO_HORAS_ACUMULO)
    cp_total_colecao, por_funcao, total_personagens = _workforce_por_funcao(guild_id, user_id)

    bonus_por_area = _bonus_todas_areas(guild_id, user_id, por_funcao)
    bonus_colecao_loot_percentual = bonus_loot_colecao(cp_total_colecao)
    bonus_admin = bonus_por_area["Administração"]
    bonus_militar_fixo = bonus_por_area["Militar"]
    bonus_arcano_percentual = bonus_por_area["Arcano"]
    # 🔥 TAXA (por hora, SEM multiplicar pelas horas passadas) - é isso
    # que o painel mostra como "capacidade atual" de cada área, sempre
    # igual não importa há quanto tempo o jogador não visita. Saúde/
    # Cultura/Comércio agora usam a MESMA fórmula de marco (2026-09-07),
    # só o que produzem continua sendo taxa/hora em vez de CP direto.
    taxa_soulstone_hora = bonus_por_area["Saúde"]
    taxa_xp_hora = bonus_por_area["Cultura"]
    taxa_wishards_hora = bonus_por_area["Comércio"]

    # 🔥 ACUMULADO desde a última visita (taxa × horas) - só isso credita
    # de verdade e some no resumo do topo do painel.
    soulstone = round(taxa_soulstone_hora * horas)
    xp = round(taxa_xp_hora * horas)
    wishards = round(taxa_wishards_hora * horas)

    if wishards:
        db.creditar_wishards(guild_id, user_id, wishards, "cidade_producao")
    if xp:
        db.creditar_xp_progressao(guild_id, user_id, xp, "cidade_producao")
    if soulstone:
        db.creditar_soulstone(guild_id, user_id, soulstone, "cidade_producao")
    db.definir_cidade_ultima_producao(
        guild_id, user_id, agora, bonus_militar_fixo, bonus_arcano_percentual, bonus_colecao_loot_percentual,
    )
    # 🔥 Log de produção (2026-09-06, pedido do usuário: "meu farm ta
    # sempre aumentando, seria ate bom manter uns logs disso") - throttlado
    # dentro de `db.registrar_producao_historico`, então chamar em toda
    # visita é seguro (não grava 1 linha por clique).
    nivel_progressao = db.progressao_conta(guild_id, user_id)["nivel"]
    db.registrar_producao_historico(
        guild_id, user_id, taxa_wishards_hora, taxa_soulstone_hora, taxa_xp_hora, cp_total_colecao, nivel_progressao,
    )

    return {
        "wishards": wishards, "xp": xp, "soulstone": soulstone, "horas": round(horas, 1),
        "cp_total": cp_total_colecao, "total_personagens": total_personagens,
        "por_funcao": por_funcao, "primeira_visita": False,
        "bonus_militar_fixo": bonus_militar_fixo, "bonus_arcano_percentual": bonus_arcano_percentual,
        "bonus_colecao_loot_percentual": bonus_colecao_loot_percentual, "bonus_administracao_percentual": bonus_admin,
        # 🔥 Capacidade ATUAL por área, independente de `horas` - o painel
        # usa isso pra "Bônus:" de cada área, nunca o valor acumulado.
        "taxas_por_funcao": {
            "Militar": bonus_militar_fixo, "Saúde": taxa_soulstone_hora, "Cultura": taxa_xp_hora,
            "Administração": bonus_admin, "Comércio": taxa_wishards_hora, "Arcano": bonus_arcano_percentual,
        },
    }


def atualizar_snapshot_bonus(guild_id, user_id):
    """Recalcula snapshots de Militar/Arcano e do loot da Coleção, sem tocar no relógio de produção
    acumulada (Saúde/Cultura/Comércio) nem no que já foi creditado -
    (2026-09-01, achado do usuário: "os bônus da cidade parece que só são
    recarregados depois que clica em cidade"). Chamado depois de qualquer
    ação que muda quem trabalha ou o CP de alguém (Party, Upar Nível,
    Aumentar Afinidade, Divorciar, Merge, Auto-Party) - assim o bônus de CP
    da Party reflete a mudança na hora, sem precisar visitar o painel
    "🏙️ Cidade" de novo. Não faz nada se a Cidade nunca foi visitada ainda
    (sem timestamp pra preservar) - a 1ª visita já calcula tudo do zero."""
    ultima = db.cidade_ultima_producao(guild_id, user_id)
    if ultima is None:
        return
    cp_total_colecao, por_funcao, _total_personagens = _workforce_por_funcao(guild_id, user_id)

    bonus_por_area = _bonus_todas_areas(guild_id, user_id, por_funcao)
    db.definir_cidade_ultima_producao(
        guild_id, user_id, ultima, bonus_por_area["Militar"], bonus_por_area["Arcano"], bonus_loot_colecao(cp_total_colecao),
    )
