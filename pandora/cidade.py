# -*- coding: utf-8 -*-
"""Cidade (2026-08-30, v2 - efeitos diferenciados por área) - análise
trazida pelo usuário (Seção 13) + pedido explícito: "n iremos setar
personagens em funcoes manualmente, sera automatico com base na classe/
profissão". Personagens possuídas que NÃO estão na Party "trabalham"
sozinhas, sem nenhum toggle/configuração - `funcao_cidade` (2º campo
derivado da classe, mesmo espírito de `categoria_combate`, ver
`pandora.db.definir_classe_personagem`) decide onde cada uma entra.

v1 (todas as 7 funções produzindo na MESMA taxa) virou v2 - cada área
tem um efeito PRÓPRIO, 2 famílias mecânicas diferentes:
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
# mecânico - a função).
FUNCOES_CIDADE = ("Militar", "Saúde", "Cultura", "Administração", "Comércio", "Arcano")

_ICONE_FUNCAO = {
    "Militar": "⚔️", "Saúde": "⚕️", "Cultura": "🎭",
    "Administração": "📜", "Comércio": "🏪", "Arcano": "🔮",
}

# 🔥 "Poder da Área" (2026-08-30, pedido do usuário: "os bônus das áreas
# não devem depender apenas do CP total... quantidade e CP devem sempre
# participar do cálculo") - `Poder = CP_total × PESO_CP + quantidade ×
# PESO_PERSONAGEM`, cada área converte esse Poder (não o CP cru) pra sua
# unidade própria. Evita 2 armadilhas opostas: 1 personagem de CP altíssimo
# "valendo" sozinha por uma legião de personagens médias (só CP contaria
# isso), e simplesmente acumular centenas de personagens Nv.1 sem
# desenvolver ninguém (só quantidade contaria isso). `PESO_PERSONAGEM`
# deliberadamente MODESTO (não o mesmo palpite que rejeitei pra Nível 1 -
# um Nv.1 já teria ~300-1000 CP próprio; se a quantidade valesse o mesmo,
# hoardear fracas ficaria tão bom quanto desenvolver - "balanceável
# depois" como toda constante nova desta sessão).
PESO_CP_POR_PODER = 1.0
PESO_PERSONAGEM_POR_PODER = 50

# 🔥 Taxas por área (2026-08-30, efeitos diferenciados - primeiro palpite,
# sem dado real pra calibrar, "balanceável depois" mesmo padrão de toda
# fórmula nova desta sessão - EXCETO `TAXA_BONUS_COLECAO`, que já veio
# com valor literal do usuário: "CP total da coleção: 50.000 -> +500 CP
# na Party" = 1%). `TAXA_BONUS_COLECAO` não usa "Poder da Área" - o
# Bônus da Coleção não é uma área, é a coleção INTEIRA, sempre só CP×1%
# (exemplo literal do usuário não tem termo de quantidade).
#
# 🔥 RECALIBRADO depois de testar contra uma conta REAL (2026-08-30) - o
# palpite inicial de Militar/Arcano/Administração usava uma escala de CP
# ~10x menor que a real (contas desenvolvidas somam CENTENAS de milhares
# de CP total, não dezenas de milhares) - a 1ª versão dava +100% de CP só
# de Arcano/Administração combinados, quase quadruplicando a Party. Essas
# 3 taxas (não a `TAXA_BONUS_COLECAO`, que é literal do usuário) foram
# cortadas ~20-50x pra virar um SUPLEMENTO modesto, não o fator dominante.
TAXA_BONUS_COLECAO = 0.01
TAXA_SOULSTONE_POR_CP_HORA = 0.001
TAXA_XP_POR_CP_HORA = 0.005
TAXA_WISHARDS_POR_CP_HORA = 0.01
# 🔥 TAXA_MILITAR_PARA_CP_FIXO subida de 0,0005 pra 0,01 (2026-08-30,
# pedido direto do usuário: "troca o 0,0005 do militar por 0.01") - ajuste
# manual em cima da recalibração acima, só pra esta taxa.
TAXA_MILITAR_PARA_CP_FIXO = 0.01
TAXA_ARCANO_PARA_PERCENTUAL = 0.0000005
TAXA_ADMINISTRACAO_PARA_PERCENTUAL = 0.0000002
TETO_HORAS_ACUMULO = 168  # 7 dias - evita acúmulo sem limite se ninguém abrir o painel por meses


def icone_funcao(funcao):
    return _ICONE_FUNCAO.get(funcao, "❓")


def _workforce_por_funcao(guild_id, user_id):
    """Escaneia a coleção INTEIRA 1x só - devolve (cp_total_colecao,
    por_funcao). `cp_total_colecao` inclui TODO MUNDO (dentro ou fora da
    Party - usado só pelo "Bônus da Coleção", que não é ligado a nenhuma
    função específica). `por_funcao` ({funcao: {"qtd", "cp"}}) só conta
    quem NÃO está na Party (mesmo critério de sempre - "personagens fora
    da Party trabalham") e já tem `classe` revelada."""
    equipe_party = db.obter_equipe(guild_id, user_id, "party")
    ids_na_party = {p["id"] for p in equipe_party.values()}
    colecao = db.colecao_do_usuario(guild_id, user_id)

    cp_total_colecao = 0.0
    por_funcao = {}
    for personagem in colecao:
        power, _nivel, _categoria = torre.power_personagem(personagem, guild_id, user_id)
        cp_total_colecao += power
        if personagem["id"] in ids_na_party:
            continue
        funcao = db.funcao_cidade_da_classe(personagem.get("classe"))
        if funcao is None:
            continue
        entrada = por_funcao.setdefault(funcao, {"qtd": 0, "cp": 0.0})
        entrada["qtd"] += 1
        entrada["cp"] += power
    return cp_total_colecao, por_funcao


def _poder_area(dados):
    """`Poder da Área` (Seção "Regra de cálculo", pedido do usuário) -
    combina quantidade E CP, nunca só um dos dois."""
    return dados["cp"] * PESO_CP_POR_PODER + dados["qtd"] * PESO_PERSONAGEM_POR_PODER


def coletar_producao_pendente(guild_id, user_id):
    """Credita Soulstone/XP/WiShards acumulados desde a última visita ao
    painel "🏙️ Cidade" (ou não credita nada e só liga o relógio, na 1ª
    vez) E atualiza o snapshot de bônus de CP pra Party (Militar/Arcano/
    Administração/Bônus da Coleção). Devolve um dict com o resumo
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
        return {
            "wishards": 0, "xp": 0, "soulstone": 0, "horas": 0.0, "cp_total": 0.0, "por_funcao": {},
            "primeira_visita": True, "bonus_militar_fixo": 0.0, "bonus_arcano_percentual": 0.0,
            "bonus_colecao_fixo": 0.0, "bonus_administracao_percentual": 0.0, "taxas_por_funcao": {},
        }

    horas = min((agora - ultima).total_seconds() / 3600, TETO_HORAS_ACUMULO)
    cp_total_colecao, por_funcao = _workforce_por_funcao(guild_id, user_id)

    def _poder(funcao):
        dados = por_funcao.get(funcao)
        return _poder_area(dados) if dados else 0.0

    # 🔥 Administração multiplica as OUTRAS 5 áreas (nunca o Bônus da
    # Coleção, que é um mecanismo à parte, sempre 1% fixo).
    bonus_admin = _poder("Administração") * TAXA_ADMINISTRACAO_PARA_PERCENTUAL

    # 🔥 TAXA (por hora, SEM multiplicar pelas horas passadas) - é isso
    # que o painel mostra como "capacidade atual" de cada área, sempre
    # igual não importa há quanto tempo o jogador não visita.
    taxa_soulstone_hora = _poder("Saúde") * TAXA_SOULSTONE_POR_CP_HORA * (1 + bonus_admin)
    taxa_xp_hora = _poder("Cultura") * TAXA_XP_POR_CP_HORA * (1 + bonus_admin)
    taxa_wishards_hora = _poder("Comércio") * TAXA_WISHARDS_POR_CP_HORA * (1 + bonus_admin)
    bonus_militar_fixo = _poder("Militar") * TAXA_MILITAR_PARA_CP_FIXO * (1 + bonus_admin)
    bonus_arcano_percentual = _poder("Arcano") * TAXA_ARCANO_PARA_PERCENTUAL * (1 + bonus_admin)
    bonus_colecao_fixo = cp_total_colecao * TAXA_BONUS_COLECAO

    # 🔥 ACUMULADO desde a última visita (taxa × horas) - só isso credita
    # de verdade e some no resumo do topo do painel.
    soulstone = round(taxa_soulstone_hora * horas)
    xp = round(taxa_xp_hora * horas)
    wishards = round(taxa_wishards_hora * horas)

    if wishards:
        db.creditar_wishards(guild_id, user_id, wishards, "cidade_producao")
    if xp:
        db.creditar_xp_progressao(guild_id, user_id, xp)
    if soulstone:
        db.creditar_soulstone(guild_id, user_id, soulstone, "cidade_producao")
    db.definir_cidade_ultima_producao(guild_id, user_id, agora, bonus_militar_fixo, bonus_arcano_percentual, bonus_colecao_fixo)

    return {
        "wishards": wishards, "xp": xp, "soulstone": soulstone, "horas": round(horas, 1),
        "cp_total": cp_total_colecao, "por_funcao": por_funcao, "primeira_visita": False,
        "bonus_militar_fixo": bonus_militar_fixo, "bonus_arcano_percentual": bonus_arcano_percentual,
        "bonus_colecao_fixo": bonus_colecao_fixo, "bonus_administracao_percentual": bonus_admin,
        # 🔥 Capacidade ATUAL por área, independente de `horas` - o painel
        # usa isso pra "Bônus:" de cada área, nunca o valor acumulado.
        "taxas_por_funcao": {
            "Militar": bonus_militar_fixo, "Saúde": taxa_soulstone_hora, "Cultura": taxa_xp_hora,
            "Administração": bonus_admin, "Comércio": taxa_wishards_hora, "Arcano": bonus_arcano_percentual,
        },
    }
