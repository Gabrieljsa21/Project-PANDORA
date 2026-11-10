# -*- coding: utf-8 -*-
"""Conquistas (registro e métricas), inventário de itens e Construções da Cidade.

Parte de `pandora.db` (dividido por domínio em 2026-11-10); de fora do
pacote, continuar usando `from pandora import db` e `db.<nome>`."""
from datetime import datetime, timezone
from pandora.db.nucleo import (
    conexao,
)
from pandora.db.combate import (
    andar_atual_torre,
)


# --------------------------------------------------------------------------
# Conquistas (2026-09-01) - registro puro, nunca concede recompensa.
# --------------------------------------------------------------------------

def conceder_conquista(guild_id, user_id, conquista_id):
    """Devolve True se era NOVA (nunca desbloqueada antes nesse servidor) -
    `False` se já tinha, pra quem chama saber se deve anunciar "NOVA
    CONQUISTA" ou ficar quieto (idempotente - seguro chamar toda vez que a
    condição bater de novo, ex.: "Caçador" checado em toda vitória)."""
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO colecao_conquistas (guild_id, user_id, conquista_id, desbloqueada_em) VALUES (?, ?, ?, ?)",
            (str(guild_id), str(user_id), conquista_id, agora),
        )
        return cursor.rowcount > 0


def conquistas_do_jogador(guild_id, user_id):
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT conquista_id, desbloqueada_em FROM colecao_conquistas WHERE guild_id = ? AND user_id = ? ORDER BY desbloqueada_em",
            (str(guild_id), str(user_id)),
        ).fetchall()
    return [dict(r) for r in linhas]


def contar_vitorias_worldboss(guild_id, user_id):
    """Quantas vitórias de World Boss esse jogador já PARTICIPOU nesse
    servidor - inclui a que acabou de terminar, se `db.worldboss_
    finalizar` já rodou antes desta chamada (ordem que `pandora.worldboss.
    processar_vitoria` respeita)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT COUNT(*) AS n FROM colecao_worldboss_participantes p "
            "JOIN colecao_worldboss_eventos e ON e.id = p.evento_id "
            "WHERE e.guild_id = ? AND p.user_id = ? AND e.status = 'vitoria'",
            (str(guild_id), str(user_id)),
        ).fetchone()
    return linha["n"]


# --------------------------------------------------------------------------
# Inventário de itens (2026-09-01)
# --------------------------------------------------------------------------

def adicionar_item(guild_id, user_id, item, quantidade=1):
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_inventario (guild_id, user_id, item, quantidade) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, item) DO UPDATE SET quantidade = quantidade + excluded.quantidade",
            (str(guild_id), str(user_id), item, quantidade),
        )


def quantidade_item(guild_id, user_id, item):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT quantidade FROM colecao_inventario WHERE guild_id = ? AND user_id = ? AND item = ?",
            (str(guild_id), str(user_id), item),
        ).fetchone()
    return linha["quantidade"] if linha else 0


def consumir_item(guild_id, user_id, item, quantidade=1):
    """Devolve True/False - só desconta se tiver o suficiente (nunca vai
    negativo)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT quantidade FROM colecao_inventario WHERE guild_id = ? AND user_id = ? AND item = ?",
            (str(guild_id), str(user_id), item),
        ).fetchone()
        if linha is None or linha["quantidade"] < quantidade:
            return False
        conn.execute(
            "UPDATE colecao_inventario SET quantidade = quantidade - ? WHERE guild_id = ? AND user_id = ? AND item = ?",
            (quantidade, str(guild_id), str(user_id), item),
        )
        return True


def itens_do_jogador(guild_id, user_id):
    """{item: quantidade} só com quantidade > 0."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT item, quantidade FROM colecao_inventario WHERE guild_id = ? AND user_id = ? AND quantidade > 0",
            (str(guild_id), str(user_id)),
        ).fetchall()
    return {r["item"]: r["quantidade"] for r in linhas}


def total_comprado_item(guild_id, user_id, item):
    """Quantas unidades desse item o jogador JÁ comprou na Loja (vitalício,
    nunca decrementado por uso) - base do preço escalável (`pandora.itens.
    custo_total_item`)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT total FROM colecao_compras_item WHERE guild_id = ? AND user_id = ? AND item = ?",
            (str(guild_id), str(user_id), item),
        ).fetchone()
    return linha["total"] if linha else 0


def registrar_compra_item(guild_id, user_id, item, quantidade):
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_compras_item (guild_id, user_id, item, total) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, item) DO UPDATE SET total = total + excluded.total",
            (str(guild_id), str(user_id), item, quantidade),
        )


# --------------------------------------------------------------------------
# Construções da Cidade (2026-09-01, item "Upgrade de Construção", Seção 10)
# --------------------------------------------------------------------------

# 🔥 Fonte ÚNICA das 6 áreas (2026-09-03, pedido do usuário: "vc tem
# distinguindo construção de area, mas é a msm coisa, so use area") -
# antes existiam 2 listas quase-duplicadas (`itens.AREAS_CONSTRUCAO`, um
# dict área->nome de construção tipo "Quartel"/"Hospital" nunca usado de
# um jeito que precisasse ser diferente da área; `cidade.FUNCOES_CIDADE`,
# o mesmo tuple de 6 nomes) - unificadas aqui, a única que o teto
# DINÂMICO abaixo pode enxergar sem criar import cíclico (`itens.py` e
# `cidade.py` já importam `db.py`, nunca o contrário). `itens.
# AREAS_CONSTRUCAO`/`cidade.FUNCOES_CIDADE` viraram aliases pra esta.
# Ordem visual única da Cidade: os cards, botões de detalhe e seletores de
# construção reutilizam esta lista. Mantém Administração/Militar/Arcano na
# primeira linha e Comércio/Saúde/Cultura na segunda.
AREAS_CONSTRUCAO = ("Administração", "Militar", "Arcano", "Comércio", "Saúde", "Cultura")

# 🔥 50 em vez de 10 (2026-09-07, pedido do usuário: "Esse limite de so
# poder upar de 10 em 10... pode aumentar o limite p 50lvs" - depois
# simplificado pra permanente: "Na verdade pode manter sempre 50 como
# cap" + "P subir p 51, todas tem de ta 50. P subir p 101, todas tem de
# ta em 100" - mesma mecânica de sempre (área mais atrasada trava as
# outras), só o degrau que cresceu.
NIVEL_MAXIMO_CONSTRUCAO_BASE = 50  # primeiro degrau do teto dinâmico, ver `teto_atual_construcao`


def nivel_construcao(guild_id, user_id, area):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT nivel FROM colecao_construcoes WHERE guild_id = ? AND user_id = ? AND area = ?",
            (str(guild_id), str(user_id), area),
        ).fetchone()
    return linha["nivel"] if linha else 0


def niveis_construcoes(guild_id, user_id):
    """{area: nivel} só com nível > 0."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT area, nivel FROM colecao_construcoes WHERE guild_id = ? AND user_id = ? AND nivel > 0",
            (str(guild_id), str(user_id)),
        ).fetchall()
    return {r["area"]: r["nivel"] for r in linhas}


def teto_atual_construcao(guild_id, user_id):
    """Teto de nível vigente pra upgrade de QUALQUER área (2026-09-03,
    pedido do usuário: "os upgrades maximos vao ser a cd 10 lv, e o
    limite so é quebrado qnd todas as reas tao no maximo. Ai o limite
    aumenta em +10, e vai indo" - degrau virou 50 em 2026-09-07, ver
    comentário de `NIVEL_MAXIMO_CONSTRUCAO_BASE`) - começa em
    `NIVEL_MAXIMO_CONSTRUCAO_BASE`; só sobe mais um degrau quando TODAS
    as 6 áreas já bateram o teto anterior - a área MAIS ATRASADA decide o
    teto vigente pra TODAS, não cada uma o seu próprio (área nunca
    comprada conta como nível 0, o pior caso possível). O teto é sempre
    RECALCULADO na hora (nunca gravado) - no instante em que a última
    área atrasada alcança o teto velho, a própria leitura seguinte já
    devolve o teto novo, sem precisar de um passo separado de
    "destravar"."""
    niveis = niveis_construcoes(guild_id, user_id)
    nivel_minimo = min((niveis.get(area, 0) for area in AREAS_CONSTRUCAO), default=0)
    return NIVEL_MAXIMO_CONSTRUCAO_BASE * (nivel_minimo // NIVEL_MAXIMO_CONSTRUCAO_BASE + 1)


def subir_construcao(guild_id, user_id, area, quantidade=1):
    """`quantidade` (2026-09-03, pedido do usuário: "alguns [itens] pode
    permitir usar varios por vez, como o upgrade de construção, q upo a
    msm construção varios lv por vez") - soma `quantidade` níveis de uma
    vez, 1 única escrita (era sempre +1, chamada em loop faria N
    round-trips no banco à toa pra uma compra em lote)."""
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_construcoes (guild_id, user_id, area, nivel) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, area) DO UPDATE SET nivel = nivel + excluded.nivel",
            (str(guild_id), str(user_id), area, quantidade),
        )
        linha = conn.execute(
            "SELECT nivel FROM colecao_construcoes WHERE guild_id = ? AND user_id = ? AND area = ?",
            (str(guild_id), str(user_id), area),
        ).fetchone()
    return linha["nivel"]


# --------------------------------------------------------------------------
# Métricas das Conquistas do Colecionador (2026-09-01,
# `ERIS_sistema_colecao_wishards.md` Seções 22/24) - todas de leitura
# barata (agregado SQL, nunca materializa a coleção inteira em Python) -
# ver `pandora.conquistas.verificar_colecionador`, que só roda sob
# demanda (painel "🏆 Conquistas"), nunca num caminho quente como claim.
# --------------------------------------------------------------------------

def incrementar_rolls_realizados(guild_id, user_id, quantidade):
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_estado_jogador (guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em, total_rolls_realizados) "
            "VALUES (?, ?, 0, ?, 1, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET total_rolls_realizados = total_rolls_realizados + excluded.total_rolls_realizados",
            (str(guild_id), str(user_id), agora, agora, quantidade),
        )


def incrementar_merges_realizados(guild_id, user_id):
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_estado_jogador (guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em, total_merges_realizados) "
            "VALUES (?, ?, 0, ?, 1, ?, 1) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET total_merges_realizados = total_merges_realizados + 1",
            (str(guild_id), str(user_id), agora, agora),
        )


def metricas_colecionador(guild_id, user_id):
    """Todas as métricas das Conquistas do Colecionador NUMA função só (1
    dict) - cada valor vem de um agregado SQL barato, nunca de
    materializar a coleção inteira em Python."""
    guild_id, user_id = str(guild_id), str(user_id)
    with conexao() as conn:
        total_personagens = conn.execute(
            "SELECT COUNT(*) AS n FROM colecao_propriedade WHERE guild_id = ? AND dono_id = ?",
            (guild_id, user_id),
        ).fetchone()["n"]

        por_raridade = {r["raridade"]: r["n"] for r in conn.execute(
            "SELECT p.raridade AS raridade, COUNT(*) AS n FROM colecao_propriedade c "
            "JOIN colecao_personagens p ON p.id = c.personagem_id "
            "WHERE c.guild_id = ? AND c.dono_id = ? GROUP BY p.raridade",
            (guild_id, user_id),
        )}

        claims = conn.execute(
            "SELECT COUNT(*) AS n FROM colecao_wishards_ledger WHERE guild_id = ? AND user_id = ? AND origem = 'claim'",
            (guild_id, user_id),
        ).fetchone()["n"]

        rolls = conn.execute(
            "SELECT total_rolls_realizados AS n FROM colecao_estado_jogador WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
        rolls = rolls["n"] if rolls else 0

        wishlist_obtidas = conn.execute(
            "SELECT COUNT(*) AS n FROM colecao_wishlist w JOIN colecao_propriedade c "
            "ON c.guild_id = w.guild_id AND c.dono_id = w.user_id AND c.personagem_id = w.personagem_id "
            "WHERE w.guild_id = ? AND w.user_id = ?",
            (guild_id, user_id),
        ).fetchone()["n"]

        afinidade_acumulada = conn.execute(
            "SELECT COALESCE(SUM(afinidade), 0) AS soma FROM colecao_afinidade WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()["soma"]

        soulmates = conn.execute(
            "SELECT COUNT(*) AS n FROM colecao_afinidade WHERE guild_id = ? AND user_id = ? AND is_soulmate = 1",
            (guild_id, user_id),
        ).fetchone()["n"]

        trocas = conn.execute(
            "SELECT COUNT(*) AS n FROM colecao_troca_proposta WHERE guild_id = ? AND status = 'aceita' "
            "AND (proponente_id = ? OR alvo_id = ?)",
            (guild_id, user_id, user_id),
        ).fetchone()["n"]

        merges = conn.execute(
            "SELECT total_merges_realizados AS n FROM colecao_estado_jogador WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
        merges = merges["n"] if merges else 0

        # 🔥 Séries completas - só entre séries onde o jogador já tem
        # PELO MENOS 1 personagem (bounded pelo tamanho da COLEÇÃO DELE,
        # nunca pelo catálogo inteiro) comparadas contra o total daquela
        # série no catálogo.
        series_possuidas = conn.execute(
            "SELECT p.serie AS serie, COUNT(*) AS n FROM colecao_propriedade c "
            "JOIN colecao_personagens p ON p.id = c.personagem_id "
            "WHERE c.guild_id = ? AND c.dono_id = ? AND p.serie IS NOT NULL AND p.serie != '' "
            "GROUP BY p.serie",
            (guild_id, user_id),
        ).fetchall()
        series_completas = 0
        for linha_serie in series_possuidas:
            total_da_serie = conn.execute(
                "SELECT COUNT(*) AS n FROM colecao_personagens WHERE serie = ? AND ativo = 1",
                (linha_serie["serie"],),
            ).fetchone()["n"]
            if total_da_serie > 0 and linha_serie["n"] >= total_da_serie:
                series_completas += 1

        valor_colecao = conn.execute(
            "SELECT COALESCE(SUM(p.raridade * 20), 0) AS soma FROM colecao_propriedade c "
            "JOIN colecao_personagens p ON p.id = c.personagem_id "
            "WHERE c.guild_id = ? AND c.dono_id = ?",
            (guild_id, user_id),
        ).fetchone()["soma"]

        wishards_movimentados = conn.execute(
            "SELECT COALESCE(SUM(ABS(quantidade)), 0) AS soma FROM colecao_wishards_ledger WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()["soma"]

    andar_torre = andar_atual_torre(guild_id, user_id)

    return {
        "personagens_totais": total_personagens,
        "raridade_1": por_raridade.get(1, 0), "raridade_2": por_raridade.get(2, 0),
        "raridade_3": por_raridade.get(3, 0), "raridade_4": por_raridade.get(4, 0), "raridade_5": por_raridade.get(5, 0),
        "claims": claims, "rolls": rolls, "wishlist_obtidas": wishlist_obtidas,
        "afinidade_acumulada": afinidade_acumulada, "soulmates": soulmates,
        "trocas": trocas, "merges": merges, "series_completas": series_completas,
        "valor_colecao": valor_colecao, "wishards_movimentados": wishards_movimentados,
        "andares_torre": andar_torre,
    }
