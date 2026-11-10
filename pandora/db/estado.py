# -*- coding: utf-8 -*-
"""Estado efêmero ou de configuração: séries bloqueadas, cards de reação pendentes, formações (Party/Fusão) e Modo Auto-coleta.

Parte de `pandora.db` (dividido por domínio em 2026-11-10); de fora do
pacote, continuar usando `from pandora import db` e `db.<nome>`."""
from datetime import datetime, timezone
from pandora.db.nucleo import (
    conexao,
)


# --------------------------------------------------------------------------
# Séries bloqueadas por servidor (Seção 21)
# --------------------------------------------------------------------------

def bloquear_serie(guild_id, serie):
    with conexao() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO colecao_series_bloqueadas (guild_id, serie) VALUES (?, ?)",
            (str(guild_id), serie),
        )


def desbloquear_serie(guild_id, serie):
    """Case-insensitive (`LOWER`) - o admin pode digitar com capitalização
    ligeiramente diferente da usada em `bloquear_serie` e ainda desbloquear
    certo (mesmo motivo do filtro em `candidatos_por_raridade`)."""
    with conexao() as conn:
        conn.execute(
            "DELETE FROM colecao_series_bloqueadas WHERE guild_id = ? AND LOWER(serie) = LOWER(?)",
            (str(guild_id), serie),
        )


def series_bloqueadas(guild_id):
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT serie FROM colecao_series_bloqueadas WHERE guild_id = ? ORDER BY serie", (str(guild_id),),
        ).fetchall()
        return [r["serie"] for r in linhas]


# --------------------------------------------------------------------------
# Cards de reação pendentes (2026-08-29) - persistido, sobrevive a um
# restart do processo (antes vivia só em `gacha._CARDS_REACAO_PENDENTES`,
# em memória). `_limpar_cards_expirados` é chamada de dentro das outras
# funções aqui - reset PREGUIÇOSO, mesmo padrão de sempre no ERIS (nenhum
# job/cron varrendo a tabela sozinho).
# --------------------------------------------------------------------------

def registrar_card_pendente(guild_id, message_id, personagem_id, emoji, expira_em_iso, acao="claim"):
    """`acao` ("claim"/"favoritar", 2026-09-01) - até 2 linhas por
    `message_id`, uma por emoji válido nesse card. `processar_reacao_
    claim` decide o que fazer depois do claim com base nisso. Pra
    registrar MAIS de um emoji do mesmo card de uma vez (o caso comum),
    usar `registrar_cards_pendentes` (1 conexão só, em vez de 1 por
    emoji)."""
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_cards_pendentes (message_id, emoji, guild_id, personagem_id, acao, expira_em) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(message_id, emoji) DO UPDATE SET expira_em = excluded.expira_em",
            (str(message_id), emoji, str(guild_id), personagem_id, acao, expira_em_iso),
        )


def registrar_cards_pendentes(guild_id, message_id, personagem_id, itens_emoji_acao, expira_em_iso):
    """Versão em LOTE de `registrar_card_pendente` (2026-09-01, achado do
    usuário: "tem como melhorar a velocidade de aparição das
    personagens?") - `itens_emoji_acao` é `[(emoji, acao), ...]` - grava
    TODAS as linhas numa ÚNICA conexão/transação, em vez de abrir uma
    conexão SQLite nova por emoji (2 aberturas viravam 2 antes; pra um
    roll de 50 isso é 100 conexões a mais só nessa parte)."""
    with conexao() as conn:
        for emoji, acao in itens_emoji_acao:
            conn.execute(
                "INSERT INTO colecao_cards_pendentes (message_id, emoji, guild_id, personagem_id, acao, expira_em) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(message_id, emoji) DO UPDATE SET expira_em = excluded.expira_em",
                (str(message_id), emoji, str(guild_id), personagem_id, acao, expira_em_iso),
            )


def _limpar_cards_expirados(conn, agora_iso):
    conn.execute("DELETE FROM colecao_cards_pendentes WHERE expira_em <= ?", (agora_iso,))


def card_pendente_por_mensagem(message_id, emoji):
    """Usado por `gacha.processar_reacao_claim` - devolve {"guild_id",
    "personagem_id", "emoji", "acao", "expira_em"} ou None (nunca existiu
    ESSE emoji nessa mensagem - reação aleatória de alguém, ou já foi
    reivindicado, ou expirou - todos tratados como "ignora essa reação",
    igual antes). Filtrar pelo `emoji` exato (2026-09-01) substitui a
    checagem manual que `processar_reacao_claim` fazia depois de buscar só
    por `message_id` - agora cada emoji da mesma mensagem é uma linha
    própria (claim/favoritar/trocar)."""
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        _limpar_cards_expirados(conn, agora)
        linha = conn.execute(
            "SELECT guild_id, personagem_id, emoji, acao, expira_em FROM colecao_cards_pendentes "
            "WHERE message_id = ? AND emoji = ?",
            (str(message_id), emoji),
        ).fetchone()
    return dict(linha) if linha else None


def remover_card_pendente(message_id):
    """Remove TODAS as variantes de emoji dessa mensagem (claim/favoritar/
    trocar) - depois de resolvida (por qualquer uma delas), as outras 2
    reações no mesmo card deixam de valer."""
    with conexao() as conn:
        conn.execute("DELETE FROM colecao_cards_pendentes WHERE message_id = ?", (str(message_id),))


def cards_pendentes(guild_id, raridade=None):
    """Personagens ainda LIVRES com card de reação ativo nesse servidor -
    devolve [(message_id, personagem_dict), ...] ordenado por POPULARIDADE
    DESC. Reset preguiçoso (remove expirados na leitura) + filtra quem JÁ
    tem dono (pode ter sido reivindicado pelo OUTRO caminho - o botão da
    mensagem combinada, `ViewClaimMultiplo`/`ViewClaimPendentes`, nunca
    remove a linha daqui - mais simples e mais correto filtrar por dono de
    verdade do que confiar em toda ação de claim lembrar de limpar aqui
    também)."""
    agora = datetime.now(timezone.utc).isoformat()
    filtros = [
        "c.guild_id = ?",
        # 🔥 `acao = 'claim'` (2026-09-01) - com favoritar/trocar também
        # gravando linha própria pra mesma mensagem/personagem, sem esse
        # filtro cada card apareceria até 3x aqui (1 por emoji); "claim"
        # sempre existe pra todo card "livre" (ver `gacha.
        # enviar_cards_individuais`), então filtrar por ele já deduplica.
        "c.acao = 'claim'",
        "NOT EXISTS (SELECT 1 FROM colecao_propriedade o WHERE o.guild_id = c.guild_id AND o.personagem_id = c.personagem_id)",
    ]
    params = [str(guild_id)]
    if raridade is not None:
        filtros.append("p.raridade = ?")
        params.append(raridade)
    sql = (
        "SELECT c.message_id AS _message_id, p.* FROM colecao_cards_pendentes c "
        "JOIN colecao_personagens p ON p.id = c.personagem_id "
        f"WHERE {' AND '.join(filtros)} ORDER BY p.popularidade DESC"
    )
    with conexao() as conn:
        _limpar_cards_expirados(conn, agora)
        linhas = conn.execute(sql, params).fetchall()
    return [(r["_message_id"], {chave: r[chave] for chave in r.keys() if chave != "_message_id"}) for r in linhas]


# --------------------------------------------------------------------------
# Formações de até 5 posições (Party/Fusão; `tipo` distingue) na mesma tabela.
# Party ainda não tem Torre pra jogar, mas já protege contra
# Merge (bloqueio duro em `eris/bot.py::_merge`, checado via `esta_na_party`)
# - "personagens da Party ficam protegidas contra ações destrutivas
# automáticas" vale desde já, não precisa esperar a Torre existir.
# --------------------------------------------------------------------------

MAX_POSICOES_EQUIPE = 5


def definir_posicao_equipe(guild_id, user_id, tipo, posicao, personagem_id):
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_equipe (guild_id, user_id, tipo, posicao, personagem_id) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, tipo, posicao) DO UPDATE SET personagem_id = excluded.personagem_id",
            (str(guild_id), str(user_id), tipo, posicao, personagem_id),
        )


def remover_posicao_equipe(guild_id, user_id, tipo, posicao):
    with conexao() as conn:
        cursor = conn.execute(
            "DELETE FROM colecao_equipe WHERE guild_id = ? AND user_id = ? AND tipo = ? AND posicao = ?",
            (str(guild_id), str(user_id), tipo, posicao),
        )
        return cursor.rowcount > 0


def limpar_equipe(guild_id, user_id, tipo):
    with conexao() as conn:
        conn.execute(
            "DELETE FROM colecao_equipe WHERE guild_id = ? AND user_id = ? AND tipo = ?",
            (str(guild_id), str(user_id), tipo),
        )


def obter_equipe(guild_id, user_id, tipo):
    """Devolve {posicao: personagem_dict}, só com as posições PREENCHIDAS -
    quem chama decide como mostrar os slots vazios. Junta Afinidade/
    `is_soulmate` (2026-08-29, Prova de Soulmate) - antes a Party/Vitrine não
    traziam essa informação, então o marcador de Soulmate nunca aparecia
    nelas em `consulta.linha_personagem`."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT e.posicao, p.*, COALESCE(a.afinidade, 1) AS afinidade, COALESCE(a.is_soulmate, 0) AS is_soulmate "
            "FROM colecao_equipe e "
            "JOIN colecao_personagens p ON p.id = e.personagem_id "
            "LEFT JOIN colecao_afinidade a "
            "  ON a.guild_id = e.guild_id AND a.user_id = e.user_id AND a.personagem_id = e.personagem_id "
            "WHERE e.guild_id = ? AND e.user_id = ? AND e.tipo = ? ORDER BY e.posicao",
            (str(guild_id), str(user_id), tipo),
        ).fetchall()
        return {r["posicao"]: dict(r) for r in linhas}


def esta_na_party(guild_id, user_id, personagem_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT 1 FROM colecao_equipe WHERE guild_id = ? AND user_id = ? AND tipo = 'party' AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        ).fetchone()
    return linha is not None


# --------------------------------------------------------------------------
# Modo Auto-coleta por usuário (2026-08-30) - rola/coleta sozinho pra quem
# ativou, nos horários fixos :50/:55 (ver `pandora.auto_colecionador_
# usuarios`), gastando a cota REAL de rolls/claims da pessoa.
# --------------------------------------------------------------------------

def auto_colecionar_ativo(guild_id, user_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT ativo FROM colecao_auto_colecionar_usuarios WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    return bool(linha["ativo"]) if linha else False


def definir_auto_colecionar(guild_id, user_id, ativo):
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_auto_colecionar_usuarios (guild_id, user_id, ativo) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET ativo = excluded.ativo",
            (str(guild_id), str(user_id), 1 if ativo else 0),
        )


def usuarios_auto_colecionar_ativos(guild_id):
    """IDs de quem ativou o Modo Auto-coleta NESSE servidor - consultado
    pelo loop fixo de :50/:55 (`auto_colecionador.AutoColecionadorUsuarios`)."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT user_id FROM colecao_auto_colecionar_usuarios WHERE guild_id = ? AND ativo = 1",
            (str(guild_id),),
        ).fetchall()
        return [r["user_id"] for r in linhas]
