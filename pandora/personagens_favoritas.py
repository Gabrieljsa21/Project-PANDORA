# -*- coding: utf-8 -*-
"""Personagens Favoritas (2026-09-03, pedido do usuário: "Implementar um
novo sistema chamado 💖 Personagens Favoritas, seguindo a mesma lógica
estrutural já usada em ❤️ Séries Favoritas") - até `SLOTS_MAXIMO` slots
(5 base, mais compráveis na Loja via `db.comprar_slot_personagem_favorita`,
mesma curva de preço em WiShards de Série Favorita), cada um podendo conter
1 personagem OCUPANTE.

Diferente de Série Favorita (bônus percentual por completude), aqui a
progressão em si é o produto: **Fortalecimento** sobe o Power Base da
personagem que ocupa o slot, em 14 patamares fixos de 50 em 50 (300→1000),
pago em Soulstone; depois de 1000, **Ascensão** ultrapassa o teto em +50
por vez (sem limite), mas exige a personagem estar no teto de Nível/
Afinidade/Soulmate.

🔥 A regra central: a progressão pertence ao SLOT, nunca à personagem que o
ocupa. Trocar de ocupante NUNCA reseta `fortalecimento_bitmask`/
`nivel_ascensao` (ver `db.definir_personagem_favorita`) - a personagem nova
só herda o que já foi comprado ali depois de preencher, ela mesma, toda
lacuna entre seu próprio Power Base natural e o que já foi desbloqueado
(`_estado_fortalecimento` abaixo resolve isso sozinho, mesmo algoritmo pros
2 casos: natural alto pulando patamares baixos nunca comprados, e natural
baixo parando na primeira lacuna mesmo com patamares mais altos já
comprados). Adicionar uma personagem como Favorita, por si só, NÃO concede
nenhum Power - só dá acesso ao que aquele slot já tinha."""
from pandora import db, torre

SLOTS_MAXIMO = db.SLOTS_BASE_PERSONAGEM_FAVORITA + db.NIVEL_MAXIMO_UPGRADE_SLOT_PERSONAGEM_FAVORITA

# 🔥 14 patamares fixos de 50 em 50 (300→1000) - bit `i` do bitmask = patamar
# `i` comprado NAQUELE slot (nunca uma lista de strings, pedido explícito do
# usuário: "Implementar da maneira mais limpa possível"). Custos crescentes,
# valores literais do pedido original.
PATAMARES_FORTALECIMENTO = (
    (300, 350), (350, 400), (400, 450), (450, 500), (500, 550), (550, 600),
    (600, 650), (650, 700), (700, 750), (750, 800), (800, 850), (850, 900),
    (900, 950), (950, 1000),
)
CUSTOS_FORTALECIMENTO = (
    50, 100, 250, 500, 1_000, 2_500, 5_000, 10_000, 20_000, 40_000,
    75_000, 150_000, 300_000, 500_000,
)

# 🔥 Ascensão (Seção 8/9 do pedido) - só depois de Fortalecimento completo
# (1000) E a personagem no teto de Nível/Afinidade/Soulmate. Cada Ascensão
# soma +50 de Power Base, sem teto de nível (ao contrário de Fortalecimento,
# nunca tem "lacuna" - é sempre comprada em ordem, mesmo padrão de todo
# "nível de upgrade" já existente no projeto, por isso um contador simples
# em vez de bitmask).
CUSTO_ASCENSAO_BASE = 600_000
CUSTO_ASCENSAO_INCREMENTO = 100_000
BONUS_POWER_POR_ASCENSAO = 50


def custo_ascensao(nivel):
    """`nivel` é o Nº da Ascensão sendo comprada (1 = primeira, 1000→1050).
    Continua a escala depois do último Fortalecimento (500.000) com um
    salto pra 600.000, depois +100.000 por Ascensão, linear e sem teto."""
    return CUSTO_ASCENSAO_BASE + (nivel - 1) * CUSTO_ASCENSAO_INCREMENTO


def _estado_fortalecimento(popularidade, bitmask):
    """Núcleo do sistema - devolve `(power_atual, indice_proximo_patamar)`,
    o 2º `None` se os 14 patamares já foram todos cobertos (natural OU
    comprado). Sobe a partir do Power Base NATURAL (`torre.power_base`,
    fórmula original intocada), patamar por patamar em ORDEM:
    - se o Power natural já ultrapassa esse patamar, pula ele sem checar o
      bit (nunca precisa comprar o que já superou naturalmente - Seção 4);
    - senão, só sobe se o bit estiver ligado NESSE slot; no primeiro bit
      desligado, PARA ali (lacuna) - mesmo com patamares mais altos já
      comprados no slot (Seção 5, "troca de personagem")."""
    atual = torre.power_base(popularidade)
    for indice, (_lo, hi) in enumerate(PATAMARES_FORTALECIMENTO):
        if atual >= hi:
            continue
        if bitmask & (1 << indice):
            atual = hi
        else:
            return atual, indice
    return atual, None


def power_efetivo(popularidade, bitmask, nivel_ascensao, elegivel):
    """Power Base FINAL de uma personagem nesse slot - some Ascensão só se
    o Fortalecimento estiver completo (1000) E `elegivel` (Nível/Afinidade/
    Soulmate no teto) - sem isso, mesmo com Ascensões já compradas no slot,
    "fica limitada a 1000" (Seção 10 do pedido)."""
    atual, proximo = _estado_fortalecimento(popularidade, bitmask)
    if proximo is None and elegivel:
        atual += nivel_ascensao * BONUS_POWER_POR_ASCENSAO
    return atual


def elegivel_ascensao(personagem, nivel_personagem, power_atual):
    """Seção 8 - Power Base efetivo = 1000 (Fortalecimento completo) +
    Nível máximo + Afinidade máxima + Soulmate, TODOS ao mesmo tempo."""
    return (
        power_atual >= 1000
        and nivel_personagem == db.NIVEL_MAXIMO_PERSONAGEM
        and personagem.get("afinidade") == db.NIVEL_MAXIMO_AFINIDADE
        and bool(personagem.get("is_soulmate"))
    )


def slots_disponiveis(guild_id, user_id):
    return db.SLOTS_BASE_PERSONAGEM_FAVORITA + db.nivel_upgrade_slots_personagem_favorita(guild_id, user_id)


def _requisitos(personagem, nivel_personagem):
    return {
        "nivel_max": nivel_personagem == db.NIVEL_MAXIMO_PERSONAGEM,
        "afinidade_max": personagem.get("afinidade") == db.NIVEL_MAXIMO_AFINIDADE,
        "soulmate": bool(personagem.get("is_soulmate")),
    }


def _com_vinculo(guild_id, user_id, personagem):
    """Personagem + afinidade/soulmate do vínculo (guild+user) embutidos -
    mesmos campos que `torre.power_personagem`/`elegivel_ascensao` esperam
    encontrar no dict (`personagem.get("afinidade")`/`.get("is_soulmate")`)."""
    return {
        **personagem,
        "afinidade": db.afinidade(guild_id, user_id, personagem["id"]),
        "is_soulmate": db.is_soulmate(guild_id, user_id, personagem["id"]),
    }


def listar(guild_id, user_id):
    """Todos os slots DISPONÍVEIS pro jogador (base + comprados), 1 item
    por slot mesmo os nunca usados - devolve `[{"slot", "personagem"
    (dict ou None), "power_natural", "power_atual", "proximo_fortalecimento"
    ({"indice", "patamar", "custo"} ou None), "requisitos_ascensao"
    ({"nivel_max", "afinidade_max", "soulmate"}), "elegivel_ascensao",
    "proxima_ascensao" ({"nivel", "custo"})}, ...]` ordenado por slot."""
    disponiveis = slots_disponiveis(guild_id, user_id)
    usados = {linha["slot"]: linha for linha in db.personagens_favoritas_do_jogador(guild_id, user_id)}

    resultado = []
    for slot in range(1, disponiveis + 1):
        linha = usados.get(slot)
        personagem_id = linha["personagem_id"] if linha else None
        bitmask = linha["fortalecimento_bitmask"] if linha else 0
        nivel_ascensao = linha["nivel_ascensao"] if linha else 0
        item = {
            "slot": slot, "personagem": None, "power_natural": None, "power_atual": None,
            "proximo_fortalecimento": None, "requisitos_ascensao": None,
            "elegivel_ascensao": False, "proxima_ascensao": None,
        }
        if personagem_id is not None:
            personagem = db.personagem_por_id(personagem_id)
            dono = db.dono_do_personagem(guild_id, personagem_id)
            if personagem is not None and dono == str(user_id):
                personagem = _com_vinculo(guild_id, user_id, personagem)
                nivel_personagem = db.nivel_personagem(guild_id, user_id, personagem_id)
                power_natural = torre.power_base(personagem["popularidade"])
                power_atual, indice_proximo = _estado_fortalecimento(personagem["popularidade"], bitmask)
                requisitos = _requisitos(personagem, nivel_personagem)
                elegivel = elegivel_ascensao(personagem, nivel_personagem, power_atual)
                if elegivel:
                    power_atual += nivel_ascensao * BONUS_POWER_POR_ASCENSAO
                item.update({
                    "personagem": personagem,
                    "power_natural": power_natural,
                    "power_atual": power_atual,
                    "proximo_fortalecimento": (
                        {"indice": indice_proximo, "patamar": PATAMARES_FORTALECIMENTO[indice_proximo], "custo": CUSTOS_FORTALECIMENTO[indice_proximo]}
                        if indice_proximo is not None else None
                    ),
                    "requisitos_ascensao": requisitos,
                    "elegivel_ascensao": elegivel,
                    "proxima_ascensao": {"nivel": nivel_ascensao + 1, "custo": custo_ascensao(nivel_ascensao + 1)} if indice_proximo is None else None,
                })
        resultado.append(item)
    return resultado


def definir_personagem(guild_id, user_id, slot, personagem_id):
    """Escolhe (`personagem_id` truthy) ou esvazia (`personagem_id=None`)
    um slot - valida faixa do slot contra os disponíveis e posse da
    personagem (nunca deixa favoritar algo que não é seu). NUNCA toca
    Fortalecimento/Ascensão do slot (`db.definir_personagem_favorita` já
    garante isso). Devolve `(ok: bool, mensagem: str)`."""
    disponiveis = slots_disponiveis(guild_id, user_id)
    if not (1 <= slot <= disponiveis):
        return False, f"Você só tem {disponiveis} slot(s) de Waifu disponível(is)."
    if personagem_id is not None:
        personagem = db.personagem_por_id(personagem_id)
        if personagem is None:
            return False, "Não achei nenhuma personagem com esse #id."
        if db.dono_do_personagem(guild_id, personagem_id) != str(user_id):
            return False, "Essa personagem não é sua nesse servidor."
    db.definir_personagem_favorita(guild_id, user_id, slot, personagem_id)
    if personagem_id is not None:
        return True, f"**{personagem['nome']}** definida como Waifu no slot {slot}."
    return True, f"Slot {slot} esvaziado."


def custo_fortalecer_ate(indice_proximo, indice_alvo):
    """Custo TOTAL (Soulstone) pra fortalecer do próximo patamar disponível
    (`indice_proximo`, ver `_estado_fortalecimento`) até `indice_alvo`
    (inclusive) - soma pura de `CUSTOS_FORTALECIMENTO`, sem tocar no banco.
    Usada pelo dropdown "até qual patamar ir" (`paineis._fortalecer`) pra
    mostrar o custo de cada opção sem precisar reconsultar popularidade/
    bitmask a cada uma."""
    return sum(CUSTOS_FORTALECIMENTO[indice_proximo:indice_alvo + 1])


def fortalecer_ate(guild_id, user_id, slot, indice_alvo):
    """Compra os patamares de Fortalecimento do ocupante atual desse slot,
    do PRÓXIMO disponível até `indice_alvo` (inclusive), em sequência -
    2026-09-06, pedido do usuário: "o botao de fortalecer... tem de
    permitir fortalecer varios niveis por vez, por um dropdown igual nos
    outros locais, mostrando custo e qnt tenho" (substitui o antigo botão
    de 1 patamar por vez + o de "gastar tudo que der", ambos virando só
    OPÇÕES do mesmo dropdown - a 1ª opção do dropdown é o antigo
    comportamento de 1 clique, a última é "gastar tudo que dá pra esse
    slot"). Preço fixo por patamar (`CUSTOS_FORTALECIMENTO`), nunca
    proporcional à distância real coberta (Seção 7 do pedido - um Power
    natural desalinhado tipo 873 paga o preço CHEIO do patamar 850→900 pra
    chegar em 900, igual quem começasse exatamente em 850). Devolve
    `(ok: bool, mensagem: str)` - `ok=False` se o saldo não cobrir o custo
    TOTAL até `indice_alvo` (tudo ou nada, o jogador já escolheu o alvo
    exato no dropdown antes de confirmar - diferente do antigo "gasta o
    quanto der", aqui não faz sentido parar no meio de uma compra que o
    próprio jogador pediu)."""
    slots = {linha["slot"]: linha for linha in db.personagens_favoritas_do_jogador(guild_id, user_id)}
    linha = slots.get(slot)
    if linha is None or linha["personagem_id"] is None:
        return False, "Esse slot não tem nenhuma Waifu."
    personagem = db.personagem_por_id(linha["personagem_id"])
    bitmask = linha["fortalecimento_bitmask"]
    _atual, indice_proximo = _estado_fortalecimento(personagem["popularidade"], bitmask)
    if indice_proximo is None:
        return False, "Esse slot já está no Fortalecimento máximo (1000) - use Ascensão."
    if indice_alvo < indice_proximo or indice_alvo >= len(PATAMARES_FORTALECIMENTO):
        return False, "Patamar-alvo inválido - tenta abrir o dropdown de novo."
    custo_total = custo_fortalecer_ate(indice_proximo, indice_alvo)
    if db.saldo_soulstone(guild_id, user_id) < custo_total:
        return False, f"Custa {db.fmt_numero(custo_total)} Soulstone no total e você não tem o suficiente."
    for indice in range(indice_proximo, indice_alvo + 1):
        db.creditar_soulstone(guild_id, user_id, -CUSTOS_FORTALECIMENTO[indice], "fortalecimento_personagem_favorita", f"slot {slot} patamar {indice}")
        db.marcar_patamar_fortalecimento(guild_id, user_id, slot, indice)
    patamares_comprados = indice_alvo - indice_proximo + 1
    _lo, hi = PATAMARES_FORTALECIMENTO[indice_alvo]
    return True, f"💪 Fortalecido {patamares_comprados} patamar(es)! Chegou em {hi} no slot {slot} (custou {db.fmt_numero(custo_total)} Soulstone)."


def ascender(guild_id, user_id, slot):
    """Compra a PRÓXIMA Ascensão do slot - exige o ocupante atual elegível
    (Fortalecimento completo + Nível/Afinidade/Soulmate no teto). Devolve
    `(ok: bool, mensagem: str)`."""
    slots = {linha["slot"]: linha for linha in db.personagens_favoritas_do_jogador(guild_id, user_id)}
    linha = slots.get(slot)
    if linha is None or linha["personagem_id"] is None:
        return False, "Esse slot não tem nenhuma Waifu."
    personagem_id = linha["personagem_id"]
    personagem = _com_vinculo(guild_id, user_id, db.personagem_por_id(personagem_id))
    nivel_personagem = db.nivel_personagem(guild_id, user_id, personagem_id)
    power_atual, indice_proximo = _estado_fortalecimento(personagem["popularidade"], linha["fortalecimento_bitmask"])
    if indice_proximo is not None:
        return False, "Essa personagem ainda não completou o Fortalecimento (1000) - termine antes de Ascender."
    if not elegivel_ascensao(personagem, nivel_personagem, power_atual):
        return False, "Precisa de Nível máximo, Afinidade máxima e Soulmate pra usar Ascensão nesse slot."
    proximo_nivel = linha["nivel_ascensao"] + 1
    custo = custo_ascensao(proximo_nivel)
    if db.saldo_soulstone(guild_id, user_id) < custo:
        return False, f"Custa {db.fmt_numero(custo)} Soulstone e você não tem o suficiente."
    db.creditar_soulstone(guild_id, user_id, -custo, "ascensao_personagem_favorita", f"slot {slot} nível {proximo_nivel}")
    db.incrementar_ascensao_personagem_favorita(guild_id, user_id, slot)
    novo_power = 1000 + proximo_nivel * BONUS_POWER_POR_ASCENSAO
    return True, f"✨ Ascendido! Power Base do slot {slot} agora é {db.fmt_numero(novo_power)} (custou {db.fmt_numero(custo)} Soulstone)."
