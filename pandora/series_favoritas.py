# -*- coding: utf-8 -*-
"""Séries Favoritas (2026-09-02, pedido do usuário depois do redesenho do
`/perfil`) - até `SLOTS_MAXIMO` séries/franquias escolhidas pelo jogador (5
slots base, mais compráveis na Loja via `db.comprar_slot_serie_favorita`),
cada uma com 4 marcos (Coleção Completa/Maestria Completa/Afinidade
Completa/Soulbond Completo), cada marco dando um bônus de CP que só afeta
personagens DAQUELA série (nunca CP global - "isso inevitavelmente vira
outra fonte enorme de power creep", pedido do usuário). Transforma série de
um dado inútil espalhado entre milhares de franquias (o `/perfil` antigo
listava TODAS) numa escolha deliberada do jogador, com identidade própria
por conta.

🔥 Marcos deixaram de ser INDEPENDENTES (2026-09-03, pedido do usuário:
"tem q comprar a serie inteira p ganhar bonus... sao 5% de possuir tudo, 5%
de tudo nivel max, 5% afinidade max, 5% soulbound") - Maestria/Afinidade/
Soulbond agora EXIGEM Coleção Completa também (possuir 100% do catálogo da
série), não só que o que já possui esteja tudo maximizado. Os 4 bônus
viraram iguais (5% cada, teto continua +20% no total - antes era 5/5/10 com
Maestria/Coleção independentes de Soulbond).

Cálculo do bônus é CARO (varre a coleção do jogador filtrada por série) -
nunca roda no caminho quente (`torre.power_personagem`/`_contexto_lote` só
LEEM o snapshot via `db.bonus_series_favoritas`) - `recalcular_bonus` só é
chamado depois de ações que mudam completude (claim/nível/afinidade/
divórcio/merge) OU depois de trocar uma série favorita, mesmo padrão de
`cidade.atualizar_snapshot_bonus`."""
from pandora import db

SLOTS_MAXIMO = db.SLOTS_BASE_SERIE_FAVORITA + db.NIVEL_MAXIMO_UPGRADE_SLOT_SERIE_FAVORITA

# 🔥 Bônus por marco (2026-09-03, "sao 5% de possuir tudo, 5% de tudo
# nivel max, 5% afinidade max, 5% soulbound") - cumulativos, só sobre
# personagens DA série, teto +20% no total (4 × 5%).
BONUS_COLECAO_COMPLETA = 0.05
BONUS_MAESTRIA_COMPLETA = 0.05
BONUS_AFINIDADE_COMPLETA = 0.05
BONUS_SOULBOND_COMPLETO = 0.05


def slots_disponiveis(guild_id, user_id):
    return db.SLOTS_BASE_SERIE_FAVORITA + db.nivel_upgrade_slots_serie_favorita(guild_id, user_id)


def listar(guild_id, user_id):
    """Todos os slots DISPONÍVEIS pro jogador (base + comprados), cada um
    com o que está dentro (ou `None`, vazio) e as estatísticas de
    completude quando ocupado - devolve `[{"slot", "serie", "bloqueado_ate",
    "possuidas", "total_catalogo", "colecao_completa", "nivel_maximo",
    "maestria_completa", "afinidade_maxima", "afinidade_completa",
    "soulmates", "soulbond_completo", "bonus_percentual"}, ...]` ordenado
    por slot, um item por slot mesmo os nunca usados (`serie=None`, resto
    zerado)."""
    disponiveis = slots_disponiveis(guild_id, user_id)
    usados = {linha["slot"]: linha for linha in db.series_favoritas_do_jogador(guild_id, user_id)}
    series_ocupadas = [linha["serie"] for linha in usados.values() if linha["serie"]]
    stats = db.estatisticas_series(guild_id, user_id, series_ocupadas)

    resultado = []
    for slot in range(1, disponiveis + 1):
        linha = usados.get(slot)
        serie = linha["serie"] if linha else None
        item = {
            "slot": slot, "serie": serie, "bloqueado_ate": linha["bloqueado_ate"] if linha else None,
            "possuidas": 0, "total_catalogo": 0, "nivel_maximo": 0, "afinidade_maxima": 0, "soulmates": 0,
            "colecao_completa": False, "maestria_completa": False, "afinidade_completa": False,
            "soulbond_completo": False, "bonus_percentual": 0.0,
        }
        if serie:
            dados = stats.get(
                serie, {"total_catalogo": 0, "possuidas": 0, "nivel_maximo": 0, "afinidade_maxima": 0, "soulmates": 0},
            )
            marcos = _marcos(dados)
            item.update(dados)
            item.update(marcos)
            item["bonus_percentual"] = _bonus_de_marcos(marcos)
        resultado.append(item)
    return resultado


def _marcos(dados):
    """🔥 Coleção Completa virou PRÉ-REQUISITO dos outros 3 (2026-09-03,
    "tem q comprar a serie inteira p ganhar bonus") - antes bastava o que
    já possuía estar tudo maximizado/soulmate, mesmo sem ter a série
    inteira; agora só conta se `possuidas == total_catalogo` também."""
    possuidas = dados["possuidas"]
    total = dados["total_catalogo"]
    colecao_completa = total > 0 and possuidas == total
    return {
        "colecao_completa": colecao_completa,
        "maestria_completa": colecao_completa and dados["nivel_maximo"] == possuidas,
        "afinidade_completa": colecao_completa and dados["afinidade_maxima"] == possuidas,
        "soulbond_completo": colecao_completa and dados["soulmates"] == possuidas,
    }


def _bonus_de_marcos(marcos):
    bonus = 0.0
    if marcos["colecao_completa"]:
        bonus += BONUS_COLECAO_COMPLETA
    if marcos["maestria_completa"]:
        bonus += BONUS_MAESTRIA_COMPLETA
    if marcos["afinidade_completa"]:
        bonus += BONUS_AFINIDADE_COMPLETA
    if marcos["soulbond_completo"]:
        bonus += BONUS_SOULBOND_COMPLETO
    return bonus


def definir(guild_id, user_id, slot, serie):
    """Escolhe (`serie` truthy) ou limpa (`serie=None`) um slot - valida
    faixa do slot contra os disponíveis, valida que a série existe de
    verdade no catálogo (evita favoritar um nome digitado errado que nunca
    vai completar nada), e recalcula o snapshot de bônus na hora (troca de
    série muda completude imediatamente - "calculado ali na hora", mesmo
    espírito do CP recomendado do World Boss). Devolve `(ok: bool,
    mensagem: str)` - sempre instantâneo (2026-09-03, "remove esse
    bloqueio" - cooldown de troca entre slots removido, era pedido do
    próprio usuário antes)."""
    disponiveis = slots_disponiveis(guild_id, user_id)
    if not (1 <= slot <= disponiveis):
        return False, f"Você só tem {disponiveis} slot(s) de Série Favorita disponível(is)."
    if serie:
        # 🔥 Busca case-insensitive (2026-09-02) - jogador digita de cabeça,
        # não copia/cola do catálogo - resolve pra grafia CANÔNICA antes de
        # gravar (senão "konosuba" e "KonoSuba" virariam séries diferentes
        # pro sistema de bônus).
        canonico = db.encontrar_serie_por_nome(serie)
        if canonico is None:
            parecidas = db.series_do_catalogo(prefixo=serie, limite=5)
            sugestao = f' Você quis dizer: {", ".join(parecidas)}?' if parecidas else ""
            return False, f'Nenhuma personagem do catálogo pertence à série "{serie}".{sugestao}'
        serie = canonico
    db.definir_serie_favorita(guild_id, user_id, slot, serie)
    recalcular_bonus(guild_id, user_id)
    if serie:
        return True, f'"{serie}" definida como Série Favorita no slot {slot}.'
    return True, f"Slot {slot} esvaziado."


def recalcular_bonus(guild_id, user_id):
    """Recalcula e grava o snapshot inteiro de bônus (2026-09-02) - chamar
    depois de qualquer ação que muda completude de uma série favoritada
    (claim/nível/afinidade/divórcio/merge) ou depois de `definir` acima.
    Só olha as séries ATUALMENTE favoritadas (nunca escaneia o catálogo
    inteiro)."""
    favoritas = [linha["serie"] for linha in db.series_favoritas_do_jogador(guild_id, user_id) if linha["serie"]]
    if not favoritas:
        db.salvar_bonus_series_favoritas(guild_id, user_id, {})
        return
    stats = db.estatisticas_series(guild_id, user_id, favoritas)
    bonus_por_serie = {}
    for serie in favoritas:
        dados = stats.get(serie, {"total_catalogo": 0, "possuidas": 0, "nivel_maximo": 0, "soulmates": 0})
        marcos = _marcos(dados)
        bonus_por_serie[serie] = {
            "bonus_percentual": _bonus_de_marcos(marcos),
            "colecao_completa": marcos["colecao_completa"],
            "maestria_completa": marcos["maestria_completa"],
            "soulbond_completo": marcos["soulbond_completo"],
        }
    db.salvar_bonus_series_favoritas(guild_id, user_id, bonus_por_serie)
