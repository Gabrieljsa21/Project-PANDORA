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

# 🔥 Preços BASE da Loja normal (Seção 14) - primeiro palpite. Roll/Claim
# Permanente SAÍRAM da compra por WiShards fixos (2026-09-03, pedido do
# usuário: "os rolls e calims de dentro doq hj esta em itens, pode
# remover" - redundante com o Upgrade de Rolls/Claims, que perdeu o teto
# de nível no mesmo pedido e virou o caminho único pra isso na Loja) -
# continuam no `CATALOGO_ITENS`/`PESOS_DROP_RARO` acima (nome/descrição +
# drop raro do World Boss), só saíram de `ITENS_LOJA`/`PRECOS_LOJA_ITENS`.
# 🔥 Reduzido ~30% (2026-09-03, pedido do usuário: "O preço desses itens
# esta muito caro. Diminui um pouco") - preço "primeiro palpite" de cima
# estava alto demais na prática; continua "balanceável depois" como todo
# valor novo desta sessão, fácil de reajustar aqui de novo se precisar.
PRECOS_LOJA_ITENS = {
    "protecao": 2_100, "revanche": 2_800, "chave_da_torre": 3_500,
    "upgrade_construcao": 4_200, "chamado": 5_600,
}

# 🔥 Itens de fato COMPRÁVEIS na Loja (2026-09-03) - subconjunto de
# `CATALOGO_ITENS`, exclui Roll/Claim Permanente (ver comentário acima).
ITENS_LOJA = {chave: dados for chave, dados in CATALOGO_ITENS.items() if chave in PRECOS_LOJA_ITENS}

# 🔥 Preço escalável (2026-09-03, pedido do usuário: "Todos os itens da
# loja tem q aumentar o preço a medida q são comprados, igual os upgrades
# de rolls") - crescimento "leve" (escolhido pelo usuário): +15% por
# unidade já comprada, composto (dobra a cada ~5 compras) - fica pra
# balanceamento como o resto, fácil de reajustar aqui.
FATOR_CRESCIMENTO_PRECO_LOJA = 1.15

LIMITE_ROLL_PERMANENTE = 5  # Seção 12 - "pode existir um limite máximo" (só drop agora, ver comentário acima)
LIMITE_CLAIM_PERMANENTE = 5  # Seção 13 - idem

# 🔥 Alias pra `db.AREAS_CONSTRUCAO` (2026-09-03, ver comentário lá) - era
# um dict área->nome de construção próprio ("Quartel"/"Hospital"/etc,
# pedido do usuário pra remover: "vc tem distinguindo construção de area,
# mas é a msm coisa, so use area") - virou o mesmo tuple de 6 áreas que
# `cidade.FUNCOES_CIDADE` já usava, fonte única em `db.py`.
AREAS_CONSTRUCAO = db.AREAS_CONSTRUCAO
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
            return f"{nome} (já no limite máximo de {limite} - convertido em +{db.fmt_numero(consolacao)} WiShards)"
        db.adicionar_bonus_permanente_drop(guild_id, user_id, campo, 1)
        return f"{nome}!"
    db.adicionar_item(guild_id, user_id, item, 1)
    return f"{nome}!"


def preco_unidade_loja(item, unidades_ja_compradas):
    """Preço da PRÓXIMA unidade desse item, dado quantas o jogador já
    comprou na Loja antes (vitalício, `db.total_comprado_item` - nunca cai
    de volta quando o item é usado/consumido). Cresce geométrico
    (`FATOR_CRESCIMENTO_PRECO_LOJA`) a partir do preço base."""
    base = PRECOS_LOJA_ITENS[item]
    return round(base * (FATOR_CRESCIMENTO_PRECO_LOJA ** unidades_ja_compradas))


def custo_total_item(guild_id, user_id, item, quantidade):
    """Soma o preço de CADA unidade de 1..`quantidade`, a partir de quantas
    já foram compradas antes - mesmo padrão de "custo total até" usado nos
    upgrades sem teto (`db.custo_total_treinamento_ate` etc.), só que
    somando UNIDADES em vez de NÍVEIS."""
    ja_comprado = db.total_comprado_item(guild_id, user_id, item)
    return sum(preco_unidade_loja(item, ja_comprado + i) for i in range(quantidade))


def comprar_item(guild_id, user_id, item, quantidade=1):
    """Seção 14 - itens de `ITENS_LOJA` (Roll/Claim Permanente SAÍRAM
    daqui, 2026-09-03 - ver comentário em `ITENS_LOJA`), WiShards como
    moeda, preço escalando por unidade já comprada (`custo_total_item`)."""
    if item not in ITENS_LOJA:
        return False, "Item não disponível pra compra na Loja."
    custo_total = custo_total_item(guild_id, user_id, item, quantidade)
    if db.saldo_wishards(guild_id, user_id) < custo_total:
        return False, f"Custa {db.fmt_numero(custo_total)} WiShards e você não tem o suficiente."
    db.creditar_wishards(guild_id, user_id, -custo_total, "loja_item", item)
    db.adicionar_item(guild_id, user_id, item, quantidade)
    db.registrar_compra_item(guild_id, user_id, item, quantidade)
    return True, f"Comprado: {CATALOGO_ITENS[item]['nome']} x{quantidade} por {db.fmt_numero(custo_total)} WiShards."


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


def usar_upgrade_construcao(guild_id, user_id, area, quantidade=1):
    """Seção 10 - jogador escolhe ONDE aplicar, agora em LOTE (2026-09-03,
    pedido do usuário: "alguns pode permitir usar varios por vez, como o
    upgrade de construção, q upo a msm construção varios lv por vez").

    Teto DINÂMICO (`db.teto_atual_construcao` - sobe +10 só quando TODAS
    as áreas já bateram o teto anterior, ver comentário lá) em vez do
    antigo teto FIXO por área: `quantidade` é clampada em silêncio pro
    que sobra até o teto vigente (nunca falha por causa disso sozinho -
    pedir mais do que cabe só aplica o que cabe, mesmo espírito de nunca
    perder uma compra por arredondamento). Falta de ITEM continua sendo
    um erro explícito (mesma régua de "não tem WiShards suficiente" do
    resto da Loja) - os dois motivos de falha são de natureza diferente
    (teto é um limite estrutural do jogo, item é um recurso que falta)."""
    if area not in AREAS_CONSTRUCAO:
        return False, "Área inválida."
    nivel_atual = db.nivel_construcao(guild_id, user_id, area)
    teto = db.teto_atual_construcao(guild_id, user_id)
    if nivel_atual >= teto:
        return False, f"{area} já está no teto atual (Nível {teto}) - suba as outras áreas até lá pro teto aumentar."
    quantidade = min(quantidade, teto - nivel_atual)
    disponivel = db.quantidade_item(guild_id, user_id, "upgrade_construcao")
    if disponivel < quantidade:
        return False, f"Você só tem {disponivel} Upgrade(s) de Construção - precisa de {quantidade} pra chegar no Nível {nivel_atual + quantidade}."
    db.consumir_item(guild_id, user_id, "upgrade_construcao", quantidade)
    novo_nivel = db.subir_construcao(guild_id, user_id, area, quantidade)
    return True, f"🏗️ {area} subiu pro Nível {novo_nivel} (+{quantidade})!"


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
