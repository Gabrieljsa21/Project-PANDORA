# -*- coding: utf-8 -*-
"""Itens consumíveis (2026-09-01, spec "World Boss: Recompensas e
Conquistas") - catálogo FECHADO de 7 itens (Seção 6), ganhos por drop raro
do World Boss (Seção 5) ou comprados na Loja normal (Seção 14). Cada item
é "usado" através do sistema que ele afeta de verdade (Proteção/Revanche
em `pandora.batalha`, Chave da Torre em `pandora.torre`, Upgrade de
Construção em `pandora.cidade`, Chamado em `pandora.worldboss`) - aqui só
vive o catálogo, o inventário genérico e a rolagem de drop raro."""
import random

from pandora import db

CATALOGO_ITENS = {
    "protecao": {"nome": "🛡️ Proteção", "descricao": "Protege 1 personagem contra perda na Batalha 5x5 enquanto ativa."},
    "revanche": {"nome": "⚔️ Revanche", "descricao": "Desafia de novo por uma personagem que você perdeu no PvP, ignorando cooldown/limite diário."},
    "chave_da_torre": {"nome": "🗝️ Chave da Torre", "descricao": "Ignora a restrição de categoria da PRÓXIMA tentativa de andar da Torre."},
    "upgrade_construcao": {"nome": "🏗️ Upgrade de Construção", "descricao": "Sobe permanentemente o nível de uma construção da Cidade."},
    "chamado": {"nome": "📯 Chamado", "descricao": "Escolhe qual World Boss aparece no próximo horário fixo desse servidor."},
    "roll_permanente": {"nome": "🎲 Roll Permanente", "descricao": "+1 roll por ciclo, pra sempre (limite separado do upgrade da Loja)."},
    "claim_permanente": {"nome": "💎 Claim Permanente", "descricao": "+1 claim por ciclo, pra sempre (limite separado do upgrade da Loja)."},
}

# 🔥 Pesos do sorteio de drop raro (Seção 5/6) - "nem todos precisam
# possuir a mesma chance... Roll/Claim Permanente devem estar entre os
# drops mais raros do sistema" - primeiro palpite, balanceável depois
# (mesmo padrão de toda constante nova do PANDORA).
PESOS_DROP_RARO = {
    "protecao": 30, "revanche": 25, "chave_da_torre": 20,
    "upgrade_construcao": 15, "chamado": 8, "roll_permanente": 1, "claim_permanente": 1,
}
# 🔥 Chance de QUALQUER drop raro por vitória (Seção 5: "devem ser
# significativamente mais raros que as recompensas básicas") - a maioria
# das vitórias não dá nada raro pra maioria dos jogadores.
CHANCE_DROP_RARO = 0.15

# 🔥 Preços da Loja normal (Seção 14) - primeiro palpite, Roll/Claim
# Permanente MUITO mais caros de propósito ("devem continuar extremamente
# restritos mesmo quando aparecerem na loja").
PRECOS_LOJA_ITENS = {
    "protecao": 3_000, "revanche": 4_000, "chave_da_torre": 5_000,
    "upgrade_construcao": 6_000, "chamado": 8_000, "roll_permanente": 50_000, "claim_permanente": 60_000,
}

LIMITE_ROLL_PERMANENTE = 5  # Seção 12 - "pode existir um limite máximo" (drop OU compra, contam juntos)
LIMITE_CLAIM_PERMANENTE = 5  # Seção 13 - idem

AREAS_CONSTRUCAO = {
    "Militar": "Quartel", "Saúde": "Hospital", "Cultura": "Academia",
    "Administração": "Prefeitura", "Comércio": "Mercado", "Arcano": "Torre Arcana",
}
NIVEL_MAXIMO_CONSTRUCAO = 10  # primeiro palpite
BONUS_POR_NIVEL_CONSTRUCAO = 0.10  # +10% de Poder na área, por nível (Seção 10: "melhora permanentemente o efeito")


def sortear_drop_raro():
    """Item sorteado, ou `None` (a maioria das vezes) - rolagem
    INDEPENDENTE por jogador (Seção 5: "o fato de um jogador receber um
    drop não interfere na chance dos demais")."""
    if random.random() >= CHANCE_DROP_RARO:
        return None
    return _sortear_item_ponderado()


def sortear_item_diario():
    """Item GARANTIDO pra Recompensa Diária (2026-09-02, pedido do usuário:
    "e da 1 item raro") - mesmos pesos do drop raro do World Boss
    (`PESOS_DROP_RARO`), mas SEM o portão de `CHANCE_DROP_RARO` - todo
    resgate da Diária dá exatamente 1 item, nunca `None`."""
    return _sortear_item_ponderado()


def _sortear_item_ponderado():
    itens = list(PESOS_DROP_RARO.keys())
    pesos = list(PESOS_DROP_RARO.values())
    return random.choices(itens, weights=pesos, k=1)[0]


def _campo_permanente(item):
    return {"roll_permanente": "rolls", "claim_permanente": "claims"}.get(item)


def _limite_permanente(campo):
    return LIMITE_ROLL_PERMANENTE if campo == "rolls" else LIMITE_CLAIM_PERMANENTE


def conceder_item_drop(guild_id, user_id, item):
    """Aplica o drop raro (Seção 5/6) - devolve um texto pronto pra
    mostrar. Roll/Claim Permanente respeitam o limite MESMO vindos de
    drop (Seção 12/13) - no teto, vira WiShards de consolação em vez de
    descartar o prêmio."""
    nome = CATALOGO_ITENS[item]["nome"]
    campo = _campo_permanente(item)
    if campo is not None:
        limite = _limite_permanente(campo)
        atual_rolls, atual_claims = db.bonus_permanente_drop(guild_id, user_id)
        atual = atual_rolls if campo == "rolls" else atual_claims
        if atual >= limite:
            consolacao = 1000
            db.creditar_wishards(guild_id, user_id, consolacao, "worldboss_drop_convertido", item)
            return f"{nome} (já no limite máximo de {limite} - convertido em +{consolacao} WiShards)"
        db.adicionar_bonus_permanente_drop(guild_id, user_id, campo, 1)
        return f"{nome}!"
    db.adicionar_item(guild_id, user_id, item, 1)
    return f"{nome}!"


def comprar_item(guild_id, user_id, item, quantidade=1):
    """Seção 14 - mesmos itens da Loja normal, WiShards como moeda.
    🔥 2026-09-01, pedido do usuário: "os rolls/claims permanentes
    vendidos na loja sao contados diferentes se ganhos dos boss" - usa o
    contador de LOJA (`bonus_permanente_loja`), nunca o de drop - cada um
    com seu próprio teto independente."""
    if item not in CATALOGO_ITENS:
        return False, "Item desconhecido."
    campo = _campo_permanente(item)
    if campo is not None:
        limite = _limite_permanente(campo)
        atual_rolls, atual_claims = db.bonus_permanente_loja(guild_id, user_id)
        atual = atual_rolls if campo == "rolls" else atual_claims
        if atual + quantidade > limite:
            return False, f"Você já comprou {atual}/{limite} na Loja - comprar {quantidade} passaria do limite máximo (drops do World Boss têm um teto separado)."
    custo_total = PRECOS_LOJA_ITENS[item] * quantidade
    if db.saldo_wishards(guild_id, user_id) < custo_total:
        return False, f"Custa {custo_total} WiShards e você não tem o suficiente."
    db.creditar_wishards(guild_id, user_id, -custo_total, "loja_item", item)
    if campo is not None:
        db.adicionar_bonus_permanente_loja(guild_id, user_id, campo, quantidade)
    else:
        db.adicionar_item(guild_id, user_id, item, quantidade)
    return True, f"Comprado: {CATALOGO_ITENS[item]['nome']} x{quantidade} por {custo_total} WiShards."


def usar_protecao(guild_id, user_id, personagem_id):
    """Seção 7 - consumível, permanece ativa até removida (sem prazo
    definido na spec - "balanceável depois")."""
    if db.esta_protegida_pvp(guild_id, user_id, personagem_id):
        return False, "Essa personagem já está protegida."
    if not db.consumir_item(guild_id, user_id, "protecao", 1):
        return False, "Você não tem nenhuma Proteção."
    db.aplicar_protecao_pvp(guild_id, user_id, personagem_id)
    return True, "🛡️ Proteção aplicada - essa personagem não pode ser reivindicada via Batalha 5x5 enquanto ativa."


def remover_protecao(guild_id, user_id, personagem_id):
    """Libera o slot (não devolve o item - já foi consumido ao aplicar)."""
    db.remover_protecao_pvp(guild_id, user_id, personagem_id)
    return True, "Proteção removida."


def usar_chave_da_torre(guild_id, user_id):
    """Seção 9 - ativa pra PRÓXIMA tentativa de andar (`pandora.torre.
    tentar_andar` confere e consome, vença ou perca)."""
    if db.chave_torre_ativa(guild_id, user_id):
        return False, "Você já tem uma Chave da Torre ativa - tente o andar antes de usar outra."
    if not db.consumir_item(guild_id, user_id, "chave_da_torre", 1):
        return False, "Você não tem nenhuma Chave da Torre."
    db.definir_chave_torre_ativa(guild_id, user_id, True)
    return True, "🗝️ Chave da Torre ativada - sua PRÓXIMA tentativa de andar ignora a restrição de categoria."


def usar_upgrade_construcao(guild_id, user_id, area):
    """Seção 10 - jogador escolhe ONDE aplicar."""
    if area not in AREAS_CONSTRUCAO:
        return False, "Área inválida."
    if db.nivel_construcao(guild_id, user_id, area) >= NIVEL_MAXIMO_CONSTRUCAO:
        return False, f"{AREAS_CONSTRUCAO[area]} já está no nível máximo ({NIVEL_MAXIMO_CONSTRUCAO})."
    if not db.consumir_item(guild_id, user_id, "upgrade_construcao", 1):
        return False, "Você não tem nenhum Upgrade de Construção."
    novo_nivel = db.subir_construcao(guild_id, user_id, area)
    return True, f"🏗️ {AREAS_CONSTRUCAO[area]} ({area}) subiu pro Nível {novo_nivel}!"


def usar_chamado(guild_id, user_id, boss_tipo):
    """Seção 11 - escolhe o Boss do PRÓXIMO horário fixo (não cria evento
    extra). Import local de `worldboss` só pra validar o tipo - evita
    ciclo de import no nível de módulo (`worldboss` importa `itens`)."""
    from pandora import worldboss
    if boss_tipo not in worldboss.CATALOGO_BOSSES:
        return False, "Boss inválido."
    if not db.consumir_item(guild_id, user_id, "chamado", 1):
        return False, "Você não tem nenhum Chamado."
    db.definir_worldboss_forcado(guild_id, boss_tipo)
    return True, f"📯 Chamado usado - o próximo World Boss desse servidor será {worldboss.CATALOGO_BOSSES[boss_tipo]['nome']}."
