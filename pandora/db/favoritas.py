# -*- coding: utf-8 -*-
"""Séries Favoritas, Personagens Favoritas (Waifus), Wishlist e tags pessoais.

Parte de `pandora.db` (dividido por domínio em 2026-11-10); de fora do
pacote, continuar usando `from pandora import db` e `db.<nome>`."""
from datetime import datetime, timezone
from pandora.db.nucleo import (
    conexao,
    fmt_numero,
    serializar_por_jogador,
)
from pandora.db.colecao import (
    debitar_wishards,
)
from pandora.db.economia import (
    _estado_jogador,
)
from pandora.db.combate import (
    andar_atual_torre,
)


# --------------------------------------------------------------------------
# Séries Favoritas (2026-09-02, `pandora.series_favoritas`) - até 5 slots
# base + upgrades pagos. CRUD puro aqui - cálculo do bônus mora em
# `pandora.series_favoritas` (usa `estatisticas_series` acima).
#
# 🔥 Cooldown de troca REMOVIDO (2026-09-03, pedido do usuário: "remove
# esse bloqueio Esse slot só pode trocar de novo em 7 dia(s)") - existia
# um cooldown de `COOLDOWN_DIAS_TROCA_SERIE_FAVORITA` dias entre trocas do
# MESMO slot (pedido do próprio usuário em 2026-09-02: "trocar uma Série
# Favorita não pode ser instantaneamente explorável... vou usar Megumin
# -> favorito KonoSuba -> ganho +20% -> luto -> tiro KonoSuba" - decidiu
# tirar depois). `bloqueado_ate` continua existindo na tabela (sem
# migração destrutiva) mas nunca mais é escrito com um valor de verdade -
# `definir_serie_favorita` sempre grava `None` e nunca mais recusa troca.
# --------------------------------------------------------------------------


def series_favoritas_do_jogador(guild_id, user_id):
    """Só os slots JÁ USADOS pelo menos 1x (linha existe) - slot nunca
    tocado não aparece aqui (é "vazio" por ausência, ver comentário da
    tabela). Devolve `[{"slot", "serie", "trocado_em", "bloqueado_ate"}]`
    ordenado por slot."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT slot, serie, trocado_em, bloqueado_ate FROM colecao_series_favoritas "
            "WHERE guild_id = ? AND user_id = ? ORDER BY slot",
            (str(guild_id), str(user_id)),
        ).fetchall()
    return [dict(r) for r in linhas]


def definir_serie_favorita(guild_id, user_id, slot, serie):
    """Define (ou limpa, se `serie=None`) a série de um slot - sempre
    instantâneo (2026-09-03, "remove esse bloqueio" - cooldown de troca
    removido, `bloqueado_ate` sempre gravado como `None` daqui pra
    frente, coluna mantida sem migração destrutiva)."""
    agora = datetime.now(timezone.utc)
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_series_favoritas (guild_id, user_id, slot, serie, trocado_em, bloqueado_ate) "
            "VALUES (?, ?, ?, ?, ?, NULL) "
            "ON CONFLICT(guild_id, user_id, slot) DO UPDATE SET "
            "serie = excluded.serie, trocado_em = excluded.trocado_em, bloqueado_ate = excluded.bloqueado_ate",
            (str(guild_id), str(user_id), slot, serie, agora.isoformat()),
        )


def nivel_upgrade_slots_serie_favorita(guild_id, user_id):
    with conexao() as conn:
        linha = _estado_jogador(conn, guild_id, user_id)
    return linha["nivel_upgrade_slots_serie_favorita"] if linha else 0


def auto_defesa_batalha_ativa(guild_id, user_id):
    """Auto-Defesa de Batalha (2026-09-02, pedido do usuário) - jogador
    liga isso pra ser defendido AUTOMATICAMENTE (`batalha.
    defesa_automatica`, mesma lógica usada pra bots) assim que desafiado,
    sem precisar esperar nem responder na mão. Desligado por padrão."""
    with conexao() as conn:
        linha = _estado_jogador(conn, guild_id, user_id)
    return bool(linha["auto_defesa_batalha_ativa"]) if linha else False


def definir_auto_defesa_batalha(guild_id, user_id, ativa):
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_estado_jogador ("
            "guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em, "
            "auto_defesa_batalha_ativa"
            ") VALUES (?, ?, 0, ?, 1, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET auto_defesa_batalha_ativa = excluded.auto_defesa_batalha_ativa",
            (str(guild_id), str(user_id), agora, agora, 1 if ativa else 0),
        )


# 🔥 Teto de slots subiu de 10 pra 25 (2026-09-03, pedido do usuário:
# "aumente o limite de series para 25 se conseguir") - 25 não foi escolha
# arbitrária: é o TETO de opções de um único `discord.ui.Select`, então
# 5 base + 20 níveis de upgrade cabem tudo num select só de escolher slot
# (ver `paineis._ViewSeriesFavoritas`, que trocou de 1 botão por slot -
# nunca caberia 25 botões nas 5 linhas do Discord - pra 1 select só).
# Slots 1-5 são gratuitos; cada upgrade libera o próximo slot (6-25) por
# uma tabela linear de 5M a 100M WiShards.
PRECOS_UPGRADE_SLOT_SERIE_FAVORITA = {
    nivel: nivel * 5_000_000
    for nivel in range(1, 21)
}
SLOTS_BASE_SERIE_FAVORITA = 5
NIVEL_MAXIMO_UPGRADE_SLOT_SERIE_FAVORITA = 20


def comprar_slot_serie_favorita(guild_id, user_id):
    """Desativado: slots de Série Favorita vêm da Torre."""
    return False, "Slots de Série Favorita são desbloqueados pela Torre, igual à Wishlist."


@serializar_por_jogador
def _comprar_slot_serie_favorita_legado(guild_id, user_id):
    """Mesmo padrão de `comprar_upgrade_rolls`/`comprar_upgrade_claims` -
    preço escalonado (`PRECOS_UPGRADE_SLOT_SERIE_FAVORITA`, "primeiro
    palpite", igual toda constante nova - barato -> extremamente caro,
    pedido do usuário), 1 slot a mais por nível, `SLOTS_BASE_SERIE_
    FAVORITA` (5) + até `NIVEL_MAXIMO_UPGRADE_SLOT_SERIE_FAVORITA` (20) =
    25 slots no total (2026-09-03, "aumente o limite de series para 25
    se conseguir" - 25 é também o teto de opções de 1 único Select do
    Discord, por isso esse número específico)."""
    nivel_atual = nivel_upgrade_slots_serie_favorita(guild_id, user_id)
    if nivel_atual >= NIVEL_MAXIMO_UPGRADE_SLOT_SERIE_FAVORITA:
        return False, "Você já tem o número máximo de slots de Série Favorita."
    proximo_nivel = nivel_atual + 1
    preco = PRECOS_UPGRADE_SLOT_SERIE_FAVORITA[proximo_nivel]
    if debitar_wishards(guild_id, user_id, preco, "upgrade_slot_serie_favorita", f"nivel {proximo_nivel}") is None:
        return False, f"Custa {fmt_numero(preco)} WiShards e você não tem o suficiente."
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_estado_jogador ("
            "guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em, "
            "nivel_upgrade_slots_serie_favorita"
            ") VALUES (?, ?, 0, ?, 1, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel_upgrade_slots_serie_favorita = excluded.nivel_upgrade_slots_serie_favorita",
            (str(guild_id), str(user_id), agora, agora, proximo_nivel),
        )
    total_slots = SLOTS_BASE_SERIE_FAVORITA + proximo_nivel
    return True, f"Slot de Série Favorita desbloqueado! {total_slots} slots no total (custou {fmt_numero(preco)} WiShards)."


def salvar_bonus_series_favoritas(guild_id, user_id, bonus_por_serie):
    """Substitui o snapshot inteiro (`colecao_series_favoritas_bonus`) de
    uma vez - `bonus_por_serie`: `{serie: {"bonus_percentual",
    "colecao_completa", "maestria_completa", "soulbond_completo"}}`.
    DELETE + INSERT (não é hot path, no máximo 10 linhas) - garante que
    séries que saíram das favoritas não deixam bônus fantasma pra trás."""
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute("DELETE FROM colecao_series_favoritas_bonus WHERE guild_id = ? AND user_id = ?", (str(guild_id), str(user_id)))
        for serie, dados in bonus_por_serie.items():
            conn.execute(
                "INSERT INTO colecao_series_favoritas_bonus "
                "(guild_id, user_id, serie, bonus_percentual, colecao_completa, maestria_completa, soulbond_completo, atualizado_em) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(guild_id), str(user_id), serie, dados["bonus_percentual"],
                    int(dados["colecao_completa"]), int(dados["maestria_completa"]), int(dados["soulbond_completo"]), agora,
                ),
            )


def bonus_series_favoritas(guild_id, user_id):
    """Leitura BARATA do snapshot (nunca recalcula) - usado por
    `torre._contexto_lote` no caminho quente. Devolve `{serie:
    bonus_percentual}` só com `bonus_percentual > 0` (a maioria das séries
    favoritadas ainda não tem nenhum marco completo)."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT serie, bonus_percentual FROM colecao_series_favoritas_bonus "
            "WHERE guild_id = ? AND user_id = ? AND bonus_percentual > 0",
            (str(guild_id), str(user_id)),
        ).fetchall()
    return {r["serie"]: r["bonus_percentual"] for r in linhas}


# --------------------------------------------------------------------------
# Personagens Favoritas (2026-09-03, `pandora.personagens_favoritas`) - CRUD
# puro aqui (mesma divisão de Série Favorita) - Fortalecimento/Ascensão são
# regra de negócio, moram em `pandora.personagens_favoritas`.
# --------------------------------------------------------------------------

def personagens_favoritas_do_jogador(guild_id, user_id):
    """Só os slots JÁ USADOS pelo menos 1x (linha existe) - mesmo espírito
    de `series_favoritas_do_jogador`. Devolve `[{"slot", "personagem_id",
    "fortalecimento_bitmask", "nivel_ascensao"}]` ordenado por slot."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT slot, personagem_id, fortalecimento_bitmask, nivel_ascensao FROM colecao_personagens_favoritas "
            "WHERE guild_id = ? AND user_id = ? ORDER BY slot",
            (str(guild_id), str(user_id)),
        ).fetchall()
    return [dict(r) for r in linhas]


def definir_personagem_favorita(guild_id, user_id, slot, personagem_id):
    """Define (ou limpa, se `personagem_id=None`) o OCUPANTE de um slot -
    NUNCA toca `fortalecimento_bitmask`/`nivel_ascensao` (progressão
    pertence ao slot, sobrevive à troca de ocupante, pedido explícito do
    usuário) - por isso o `ON CONFLICT` só atualiza `personagem_id`/
    `trocado_em`, nunca as outras 2 colunas."""
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_personagens_favoritas "
            "(guild_id, user_id, slot, personagem_id, fortalecimento_bitmask, nivel_ascensao, trocado_em) "
            "VALUES (?, ?, ?, ?, 0, 0, ?) "
            "ON CONFLICT(guild_id, user_id, slot) DO UPDATE SET "
            "personagem_id = excluded.personagem_id, trocado_em = excluded.trocado_em",
            (str(guild_id), str(user_id), slot, personagem_id, agora),
        )


def personagens_favoritas_ocupantes(guild_id, user_id):
    """{personagem_id: {"slot", "fortalecimento_bitmask", "nivel_ascensao"}}
    - 1 query batched pra todos os slots OCUPADOS (personagem_id IS NOT
    NULL), usada por `torre._contexto_lote` (nunca recalculado/consultado
    por personagem individual no caminho quente, mesmo padrão de
    `bonus_series_favoritas`)."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT slot, personagem_id, fortalecimento_bitmask, nivel_ascensao FROM colecao_personagens_favoritas "
            "WHERE guild_id = ? AND user_id = ? AND personagem_id IS NOT NULL",
            (str(guild_id), str(user_id)),
        ).fetchall()
    return {
        r["personagem_id"]: {
            "slot": r["slot"], "fortalecimento_bitmask": r["fortalecimento_bitmask"], "nivel_ascensao": r["nivel_ascensao"],
        }
        for r in linhas
    }


def marcar_patamar_fortalecimento(guild_id, user_id, slot, indice):
    """Liga o bit `indice` do bitmask desse slot (`OR` bit a bit - nunca
    desliga um já ligado, nunca mexe nos outros bits)."""
    with conexao() as conn:
        conn.execute(
            "UPDATE colecao_personagens_favoritas SET fortalecimento_bitmask = fortalecimento_bitmask | ? "
            "WHERE guild_id = ? AND user_id = ? AND slot = ?",
            (1 << indice, str(guild_id), str(user_id), slot),
        )


def incrementar_ascensao_personagem_favorita(guild_id, user_id, slot, quantidade=1):
    """Acrescenta uma ou mais Ascensões já validadas pelo domínio."""
    with conexao() as conn:
        conn.execute(
            "UPDATE colecao_personagens_favoritas SET nivel_ascensao = nivel_ascensao + ? "
            "WHERE guild_id = ? AND user_id = ? AND slot = ?",
            (quantidade, str(guild_id), str(user_id), slot),
        )


# Mesma tabela de Série Favorita: WiShards, 5 base + 20 pagos = 25 slots.
PRECOS_UPGRADE_SLOT_PERSONAGEM_FAVORITA = PRECOS_UPGRADE_SLOT_SERIE_FAVORITA
SLOTS_BASE_PERSONAGEM_FAVORITA = 5
NIVEL_MAXIMO_UPGRADE_SLOT_PERSONAGEM_FAVORITA = 20


def nivel_upgrade_slots_personagem_favorita(guild_id, user_id):
    with conexao() as conn:
        linha = _estado_jogador(conn, guild_id, user_id)
    return linha["nivel_upgrade_slots_personagem_favorita"] if linha else 0


@serializar_por_jogador
def comprar_slot_personagem_favorita(guild_id, user_id):
    """Mesmo padrão de `comprar_slot_serie_favorita` - preço escalonado,
    1 slot a mais por nível, `SLOTS_BASE_PERSONAGEM_FAVORITA` (5) + até
    `NIVEL_MAXIMO_UPGRADE_SLOT_PERSONAGEM_FAVORITA` (20) = 25 no total."""
    nivel_atual = nivel_upgrade_slots_personagem_favorita(guild_id, user_id)
    if nivel_atual >= NIVEL_MAXIMO_UPGRADE_SLOT_PERSONAGEM_FAVORITA:
        return False, "Você já tem o número máximo de slots de Waifu."
    proximo_nivel = nivel_atual + 1
    preco = PRECOS_UPGRADE_SLOT_PERSONAGEM_FAVORITA[proximo_nivel]
    if debitar_wishards(guild_id, user_id, preco, "upgrade_slot_personagem_favorita", f"nivel {proximo_nivel}") is None:
        return False, f"Custa {fmt_numero(preco)} WiShards e você não tem o suficiente."
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_estado_jogador ("
            "guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em, "
            "nivel_upgrade_slots_personagem_favorita"
            ") VALUES (?, ?, 0, ?, 1, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel_upgrade_slots_personagem_favorita = excluded.nivel_upgrade_slots_personagem_favorita",
            (str(guild_id), str(user_id), agora, agora, proximo_nivel),
        )
    total_slots = SLOTS_BASE_PERSONAGEM_FAVORITA + proximo_nivel
    return True, f"Slot de Waifu desbloqueado! {total_slots} slots no total (custou {fmt_numero(preco)} WiShards)."


# --------------------------------------------------------------------------
# Wishlist (Seção 15 - "Favoritas/Protegidas" original) - 2026-09-03, fusão
# Favoritos+Wishlist ("tem Favoritos e Wishlist, Vamos unir tudo em
# Wishlist... melhor manter o favoritos e apenas renomea-lo para wishlist,
# vc ta mantendo o nome das funcoes relacionadas a essa uniao como
# wishlist?") - MECANISMO de baixo nível é o antigo Favoritos (tabela
# `colecao_favoritas`, sempre mais simples/direto - "é pego com emote e
# botão fácil"), mas as FUNÇÕES agora chamam "wishlist" (reaproveitando os
# nomes exatos que `colecao_wishlist`/o comando `/wishlist` antigo já
# usavam) - é o nome que sobrevive de verdade daqui pra frente. O card
# "🔍 Personagem" (`_ViewNivel.favoritar`) e o navegador de Série
# (`_ViewNavegarSerie._favoritar`) continuam com esse VERBO/rótulo visível
# ("Favoritar"/"Desfavoritar") - é o atalho rápido que o usuário pediu pra
# manter tal como está -, só chamando essas funções por baixo agora.
# --------------------------------------------------------------------------

SLOTS_BASE_WISHLIST = 5
SLOTS_MAXIMO_WISHLIST = 25
ANDAR_MAXIMO_BONUS_WISHLIST = 500


def beneficios_wishlist_torre(guild_id, user_id):
    """Recompensas permanentes da Torre para a Wishlist.

    ``andar_atual`` é o próximo andar a tentar; portanto, as recompensas
    usam somente os andares já vencidos. A cada 25 vitórias há um slot,
    até 25 no total. A cada cinco vitórias que não fecha um bloco de 25 há
    +0,25 ponto percentual de chance, até +20 pontos no andar 500.
    """
    andares_vencidos = max(0, andar_atual_torre(guild_id, user_id) - 1)
    andares_considerados = min(andares_vencidos, ANDAR_MAXIMO_BONUS_WISHLIST)
    slots = min(SLOTS_MAXIMO_WISHLIST, SLOTS_BASE_WISHLIST + andares_considerados // 25)
    marcos_de_cinco = andares_considerados // 5
    marcos_de_vinte_e_cinco = andares_considerados // 25
    bonus_chance = (marcos_de_cinco - marcos_de_vinte_e_cinco) * 0.0025
    return {"andares_vencidos": andares_vencidos, "slots": slots, "bonus_chance": bonus_chance}


def wishlist_adicionar(guild_id, user_id, personagem_id):
    """Adiciona aos Favoritos pessoais, sem limite e sem efeito em rolls."""
    with conexao() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO colecao_favoritas (guild_id, user_id, personagem_id) VALUES (?, ?, ?)",
            (str(guild_id), str(user_id), personagem_id),
        )
    return True, "Personagem adicionada aos Favoritos."


def wishlist_remover(guild_id, user_id, personagem_id):
    with conexao() as conn:
        conn.execute(
            "DELETE FROM colecao_favoritas WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        )


def esta_na_wishlist(guild_id, user_id, personagem_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT 1 FROM colecao_favoritas WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        ).fetchone()
    return linha is not None


def wishlist_listar(guild_id, user_id):
    """Personagens na Wishlist desse jogador (2026-09-02, pedido do
    usuário: "quero q tenha uma lista com meus personagens favoritos,
    assim como tem so de personagens"; renomeada em 2026-09-03 na fusão
    com a Wishlist antiga) - mesmo formato de `colecao_do_usuario`
    (afinidade/soulmate inclusos, pra `consulta.linha_personagem` mostrar
    igual à Coleção), só filtrado pelas marcadas em `colecao_favoritas`
    (nome da TABELA não mudou, só as funções que a usam). Ordenado por
    popularidade DESC.

    🔥 `JOIN` -> `LEFT JOIN` com `colecao_propriedade` (2026-09-03) - a
    Wishlist passou a aceitar personagem NÃO possuída também (era exigido
    antes, ver `paineis.py`/`eris/bot.py` - as checagens de posse saíram
    de lá). `reivindicado_em` volta `None` pra quem ainda não tem dono
    nesse servidor - é o jeito de quem chama distinguir "já é sua" de
    "ainda só na lista de desejos", sem precisar de uma coluna nova.

    🔥 `dono_id` de verdade (2026-09-03, "A wishlist tem q ser igual a
    tela de personagem, mostrando imagem e com os msm botoes") - `own`
    é um 2º `LEFT JOIN` em `colecao_propriedade` SEM restringir por dono
    (dá o dono REAL, seja o próprio autor, outro jogador, ou `None` se
    livre) - o `reivindicado_em` acima só sabia dizer "é do autor ou não",
    o navegador de card (`ViewWishlistHub`) precisa dos 3 estados (Livre/
    É sua/De outro jogador) pra decidir quais botões habilitar, mesmo
    padrão de `personagens_da_serie_paginada`."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT p.*, own.dono_id, c.reivindicado_em, COALESCE(a.afinidade, 1) AS afinidade, "
            "COALESCE(a.is_soulmate, 0) AS is_soulmate "
            "FROM colecao_favoritas f "
            "JOIN colecao_personagens p ON p.id = f.personagem_id "
            "LEFT JOIN colecao_propriedade own ON own.guild_id = f.guild_id AND own.personagem_id = f.personagem_id "
            "LEFT JOIN colecao_propriedade c ON c.guild_id = f.guild_id AND c.dono_id = f.user_id AND c.personagem_id = f.personagem_id "
            "LEFT JOIN colecao_afinidade a "
            "  ON a.guild_id = f.guild_id AND a.user_id = f.user_id AND a.personagem_id = f.personagem_id "
            "WHERE f.guild_id = ? AND f.user_id = ? "
            "ORDER BY p.popularidade DESC",
            (str(guild_id), str(user_id)),
        ).fetchall()
        return [dict(r) for r in linhas]


def wishlist_disponiveis_no_guild(guild_id, user_id, permitir_nsfw, raridade=None):
    """Itens da Wishlist que ainda não têm dono NESSE servidor - candidatos
    reais pro "wish roll" (`gacha._sortear_um`) - a lista aumenta
    moderadamente a chance, nunca garante o aparecimento (PLANO_COLECAO_
    WAIFUS.md, Seção 12). Mesmo nome/contrato da função antiga (que lia
    `colecao_wishlist`) - só a fonte virou `colecao_favoritas` na fusão de
    2026-09-03."""
    filtros = ["f.guild_id = ?", "f.user_id = ?", "p.ativo = 1"]
    params = [str(guild_id), str(user_id)]
    if not permitir_nsfw:
        filtros.append("p.nsfw = 0")
    if raridade is not None:
        filtros.append("p.raridade = ?")
        params.append(raridade)
    filtros.append("p.id NOT IN (SELECT personagem_id FROM colecao_propriedade WHERE guild_id = ?)")
    params.append(str(guild_id))
    sql = (
        "SELECT p.id FROM colecao_favoritas f JOIN colecao_personagens p ON p.id = f.personagem_id "
        f"WHERE {' AND '.join(filtros)}"
    )
    with conexao() as conn:
        return [r["id"] for r in conn.execute(sql, params).fetchall()]


def wishlist_slots_disponiveis_no_guild(guild_id, user_id, permitir_nsfw, raridade=None):
    """Alvos da Wishlist por slots, inclusive personagens já adquiridas."""
    filtros = ["w.guild_id = ?", "w.user_id = ?", "w.personagem_id IS NOT NULL", "p.ativo = 1"]
    params = [str(guild_id), str(user_id)]
    if not permitir_nsfw:
        filtros.append("p.nsfw = 0")
    if raridade is not None:
        filtros.append("p.raridade = ?")
        params.append(raridade)
    sql = (
        "SELECT DISTINCT p.id FROM colecao_personagens_favoritas w "
        "JOIN colecao_personagens p ON p.id = w.personagem_id "
        f"WHERE {' AND '.join(filtros)}"
    )
    with conexao() as conn:
        return [r["id"] for r in conn.execute(sql, params).fetchall()]


# --------------------------------------------------------------------------
# Tags pessoais por personagem (2026-09-01) - "trade" é a 1ª usada
# --------------------------------------------------------------------------

def definir_tag(guild_id, user_id, personagem_id, tag):
    with conexao() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO colecao_tags (guild_id, user_id, personagem_id, tag) VALUES (?, ?, ?, ?)",
            (str(guild_id), str(user_id), personagem_id, tag),
        )


def remover_tag(guild_id, user_id, personagem_id, tag):
    with conexao() as conn:
        conn.execute(
            "DELETE FROM colecao_tags WHERE guild_id = ? AND user_id = ? AND personagem_id = ? AND tag = ?",
            (str(guild_id), str(user_id), personagem_id, tag),
        )


def tags_do_personagem(guild_id, user_id, personagem_id):
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT tag FROM colecao_tags WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        ).fetchall()
    return [r["tag"] for r in linhas]


def colecao_por_tag(guild_id, user_id, tag):
    """Personagens da coleção do jogador marcadas com essa tag (ex.:
    "trade", ver `gacha.processar_reacao_claim`) - usado pro filtro
    "🏷️ Tags" do hub, ordenado por popularidade (mesmo critério simples de
    `wishlist_listar`, sem contexto de vínculo)."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT p.* FROM colecao_tags t JOIN colecao_personagens p ON p.id = t.personagem_id "
            "WHERE t.guild_id = ? AND t.user_id = ? AND t.tag = ? ORDER BY p.popularidade DESC",
            (str(guild_id), str(user_id), tag),
        ).fetchall()
    return [dict(r) for r in linhas]
