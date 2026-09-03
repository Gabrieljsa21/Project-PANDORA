# -*- coding: utf-8 -*-
"""Conquistas - 2 famílias distintas, com regras de recompensa DIFERENTES:

1. **World Boss** (`wb_*`, spec "World Boss: Recompensas e Conquistas",
   Seção 15/16) - registro PURO ("isso aconteceu nessa conta"), NUNCA
   concede WiShards/XP/Soulstones/itens/personagens/bônus.
2. **Colecionador** (`col_*`, 2026-09-01, `ERIS_sistema_colecao_
   wishards.md` Seções 22/24) - pedido do usuário: "Pode considerar essas
   conquistas q ele citou, apenas a parte de musica q acho q n é direto
   com pandora" - a Seção 23 ("Conquistas musicais") ficou de FORA de
   propósito (pertence ao sistema de música do ERIS, não ao PANDORA); a
   Seção 22 (framework geral) e 24 (conquistas do colecionador) foram
   implementadas. Progressiva de 5 marcos, PAGA WiShards por marco (Seção
   22: I=25, II=50, III=100, IV=250, V=500) - ao contrário das de World
   Boss, essas SÃO recompensadas.

Catálogo aberto pra crescer (o usuário já indicou: "podem existir também
para Torre, PvP, Cidade, coleção, Afinidade, Soulmate e demais
sistemas")."""
from pandora import db

CATALOGO = {
    "wb_primeiro_sangue": {"nome": "🏆 Primeiro Sangue", "descricao": "Participe da derrota do seu primeiro World Boss."},
    "wb_cacador": {"nome": "🏆 Caçador", "descricao": "Derrote 10 World Bosses."},
    "wb_veterano": {"nome": "🏆 Veterano", "descricao": "Derrote 100 World Bosses."},
    "wb_lenda_da_cacada": {"nome": "🏆 Lenda da Caçada", "descricao": "Derrote 1.000 World Bosses."},
    "wb_cacador_de_dragoes": {"nome": "🐉 Caçador de Dragões", "descricao": "Derrote o Dragão Ancião."},
    "wb_cacador_da_noite": {"nome": "🩸 Caçador da Noite", "descricao": "Derrote o Rei Vampiro."},
    "wb_reflexo_partido": {"nome": "🪞 Reflexo Partido", "descricao": "Derrote o Doppelgänger."},
    "wb_alem_da_morte": {"nome": "☠️ Além da Morte", "descricao": "Derrote o Senhor da Morte."},
    "wb_cinzas_as_cinzas": {"nome": "🔥 Cinzas às Cinzas", "descricao": "Derrote a Fênix Eterna."},
    "wb_queda_do_colosso": {"nome": "🗿 Queda do Colosso", "descricao": "Derrote o Colosso de Pedra."},
    "wb_contra_o_abismo": {"nome": "🌑 Contra o Abismo", "descricao": "Derrote o Devorador do Abismo."},
    "wb_regicidio": {"nome": "👑 Regicídio", "descricao": "Derrote o Rei Demônio."},
    "wb_sem_cabecas": {"nome": "🐍 Sem Cabeças", "descricao": "Derrote a Hidra."},
    "wb_contra_o_caos": {"nome": "🌌 Contra o Caos", "descricao": "Derrote o Deus do Caos."},
    "wb_por_um_fio": {"nome": "🏆 Por um Fio", "descricao": "Vença um World Boss com menos de 5% do HP restante."},
    "wb_intocaveis": {"nome": "🏆 Intocáveis", "descricao": "Vença terminando com 100% do HP."},
    "wb_ultimo_segundo": {"nome": "🏆 Último Segundo", "descricao": "Derrote o Boss no último turno possível."},
    "wb_ataque_total": {"nome": "🏆 Ataque Total", "descricao": "Vença com DPS representando mais de 70% do CP enviado."},
    "wb_fortaleza": {"nome": "🏆 Fortaleza", "descricao": "Vença com Tank sendo a categoria com maior CP agregado."},
    "wb_sustentacao": {"nome": "🏆 Sustentação", "descricao": "Vença com Support sendo a categoria com maior CP agregado."},
}

# 🔥 1 conquista por tipo de Boss (Seção 16, "Tipos de Boss") - chave
# igual a `pandora.worldboss.CATALOGO_BOSSES`.
BOSS_TIPO_PARA_CONQUISTA = {
    "dragao_anciao": "wb_cacador_de_dragoes",
    "rei_vampiro": "wb_cacador_da_noite",
    "doppelganger": "wb_reflexo_partido",
    "senhor_da_morte": "wb_alem_da_morte",
    "fenix_eterna": "wb_cinzas_as_cinzas",
    "colosso_de_pedra": "wb_queda_do_colosso",
    "devorador_do_abismo": "wb_contra_o_abismo",
    "rei_demonio": "wb_regicidio",
    "hidra": "wb_sem_cabecas",
    "deus_do_caos": "wb_contra_o_caos",
}

# 🔥 Recompensa FIXA por marco (Seção 22 - "toda conquista progressiva
# terá 5 marcos"), igual pra QUALQUER família do colecionador.
RECOMPENSA_POR_MARCO = (25, 50, 100, 250, 500)
_NUMERAL = ("I", "II", "III", "IV", "V")

# 🔥 Famílias das Conquistas do Colecionador (Seção 24 - "criar cinco
# marcos para: personagens totais; personagens por raridade; claims;
# rolls; personagens da Wishlist obtidas; Afinidade acumulada;
# Soulmates; trocas; merges; séries completas; valor da coleção;
# WiShards ganhos/gastos; andares da Torre"). `campo_metrica` liga cada
# família ao valor correspondente devolvido por `db.metricas_
# colecionador`. Limiares são primeiro palpite ("números exatos ficam
# para balanceamento", Seção 24) - "balanceável depois" de sempre.
FAMILIAS_COLECIONADOR = {
    "col_personagens_totais": {"nome": "📚 Colecionador", "campo_metrica": "personagens_totais", "unidade": "personagens", "marcos": (10, 50, 150, 500, 1500)},
    "col_raridade_1": {"nome": "⚪ Colecionador Comum", "campo_metrica": "raridade_1", "unidade": "personagens 1⭐", "marcos": (20, 100, 300, 800, 2000)},
    "col_raridade_2": {"nome": "🟢 Colecionador Incomum", "campo_metrica": "raridade_2", "unidade": "personagens 2⭐", "marcos": (15, 75, 200, 500, 1200)},
    "col_raridade_3": {"nome": "🔵 Colecionador Raro", "campo_metrica": "raridade_3", "unidade": "personagens 3⭐", "marcos": (10, 50, 150, 400, 1000)},
    "col_raridade_4": {"nome": "🟣 Colecionador Épico", "campo_metrica": "raridade_4", "unidade": "personagens 4⭐", "marcos": (5, 25, 75, 200, 500)},
    "col_raridade_5": {"nome": "🟡 Colecionador Lendário", "campo_metrica": "raridade_5", "unidade": "personagens 5⭐", "marcos": (3, 10, 30, 75, 200)},
    "col_claims": {"nome": "💘 Caçador de Waifus", "campo_metrica": "claims", "unidade": "claims", "marcos": (10, 50, 150, 500, 1500)},
    "col_rolls": {"nome": "🎲 Rolador Compulsivo", "campo_metrica": "rolls", "unidade": "rolls", "marcos": (50, 250, 750, 2000, 5000)},
    "col_wishlist_obtidas": {"nome": "⭐ Desejo Realizado", "campo_metrica": "wishlist_obtidas", "unidade": "itens da wishlist obtidos", "marcos": (3, 10, 25, 50, 100)},
    "col_afinidade_acumulada": {"nome": "❤️ Vínculo Profundo", "campo_metrica": "afinidade_acumulada", "unidade": "pontos de Afinidade acumulados", "marcos": (50, 250, 750, 2000, 5000)},
    "col_soulmates": {"nome": "💞 Alma Gêmea", "campo_metrica": "soulmates", "unidade": "Soulmates", "marcos": (1, 5, 15, 30, 50)},
    "col_trocas": {"nome": "🔄 Negociante", "campo_metrica": "trocas", "unidade": "trocas aceitas", "marcos": (5, 15, 50, 150, 400)},
    "col_merges": {"nome": "🔀 Fusão Arcana", "campo_metrica": "merges", "unidade": "merges", "marcos": (5, 15, 50, 150, 400)},
    "col_series_completas": {"nome": "📖 Completista", "campo_metrica": "series_completas", "unidade": "séries completas", "marcos": (1, 3, 10, 25, 50)},
    "col_valor_colecao": {"nome": "💰 Coleção Valiosa", "campo_metrica": "valor_colecao", "unidade": "WiShards em valor de coleção", "marcos": (5_000, 25_000, 100_000, 500_000, 2_000_000)},
    "col_wishards_movimentados": {"nome": "🏦 Economia Ativa", "campo_metrica": "wishards_movimentados", "unidade": "WiShards movimentados (ganhos+gastos)", "marcos": (5_000, 25_000, 100_000, 500_000, 2_000_000)},
    "col_andares_torre": {"nome": "🗼 Escalador", "campo_metrica": "andares_torre", "unidade": "andares da Torre", "marcos": (10, 25, 50, 100, 200)},
}


def _gerar_catalogo_colecionador():
    catalogo = {}
    for chave_familia, dados in FAMILIAS_COLECIONADOR.items():
        for indice, limiar in enumerate(dados["marcos"]):
            catalogo[f"{chave_familia}_{indice + 1}"] = {
                "nome": f"{dados['nome']} {_NUMERAL[indice]}",
                "descricao": f"Alcance {limiar:,} {dados['unidade']}.".replace(",", "."),
                "recompensa_wishards": RECOMPENSA_POR_MARCO[indice],
            }
    return catalogo


CATALOGO_COLECIONADOR = _gerar_catalogo_colecionador()
CATALOGO.update(CATALOGO_COLECIONADOR)


def conceder(guild_id, user_id, conquista_id):
    """Devolve True só se era NOVA - idempotente, seguro chamar toda vez
    que a condição bater de novo. 🔥 2026-09-01 - conquistas "col_*"
    (Colecionador) TAMBÉM creditam WiShards (Seção 22); as de World Boss
    ("wb_*") continuam SEM recompensa (spec própria, Seção 15)."""
    nova = db.conceder_conquista(guild_id, user_id, conquista_id)
    if nova and conquista_id in CATALOGO_COLECIONADOR:
        recompensa = CATALOGO_COLECIONADOR[conquista_id]["recompensa_wishards"]
        db.creditar_wishards(guild_id, user_id, recompensa, "conquista", conquista_id)
    return nova


def verificar_colecionador(guild_id, user_id):
    """Confere TODAS as famílias "col_*" contra as métricas ATUAIS do
    jogador (Seção 24) - concede todo marco já alcançado e ainda não
    desbloqueado (podem sair vários de uma vez, ex.: Merge em massa
    cruzando 2 marcos ao mesmo tempo). Só deve ser chamado sob DEMANDA
    (painel "🏆 Conquistas") - `db.metricas_colecionador` é barato (só
    agregados SQL), mas ainda assim nunca deveria rodar num caminho
    quente feito claim (mesma lição da correção anterior: nada que
    escaneia/agrega a coleção deveria rodar em TODO clique). Devolve a
    lista de IDs novos concedidos."""
    metricas = db.metricas_colecionador(guild_id, user_id)
    novos = []
    for chave_familia, dados in FAMILIAS_COLECIONADOR.items():
        valor_atual = metricas.get(dados["campo_metrica"], 0)
        for indice, limiar in enumerate(dados["marcos"]):
            if valor_atual >= limiar:
                conquista_id = f"{chave_familia}_{indice + 1}"
                if conceder(guild_id, user_id, conquista_id):
                    novos.append(conquista_id)
    return novos


def do_jogador(guild_id, user_id):
    """[(conquista_id, nome, descricao, desbloqueada_em), ...] - já
    traduzido do catálogo, pronto pra exibir (`conquista_id` cru pra
    quem chama separar World Boss/"wb_" de Colecionador/"col_", ver
    `paineis.ViewConquistasHub`)."""
    linhas = db.conquistas_do_jogador(guild_id, user_id)
    resultado = []
    for linha in linhas:
        dados = CATALOGO.get(linha["conquista_id"])
        if dados is None:
            continue
        resultado.append((linha["conquista_id"], dados["nome"], dados["descricao"], linha["desbloqueada_em"]))
    return resultado


def progresso_colecionador(guild_id, user_id):
    """[(nome_familia, valor_atual, tier_atual_0_a_5, proximo_limiar_ou_
    None), ...] - progresso de TODAS as famílias "col_*", mesmo as ainda
    sem nenhum marco batido. `tier_atual` conta quantos marcos já foram
    CRUZADOS pelo valor atual (pode estar à frente do que já foi
    CONCEDIDO de fato - só `verificar_colecionador` concede/credita)."""
    metricas = db.metricas_colecionador(guild_id, user_id)
    progresso = []
    for dados in FAMILIAS_COLECIONADOR.values():
        valor_atual = metricas.get(dados["campo_metrica"], 0)
        tier = sum(1 for limiar in dados["marcos"] if valor_atual >= limiar)
        proximo = dados["marcos"][tier] if tier < len(dados["marcos"]) else None
        progresso.append((dados["nome"], valor_atual, tier, proximo))
    return progresso
