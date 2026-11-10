# -*- coding: utf-8 -*-
"""Batalha 5x5, Torre, World Boss, Proteção PvP, personagens perdidas, Chave da Torre, Chamado e estatísticas da Torre.

Parte de `pandora.db` (dividido por domínio em 2026-11-10); de fora do
pacote, continuar usando `from pandora import db` e `db.<nome>`."""
import json
from datetime import datetime, timedelta, timezone
from pandora.db.nucleo import (
    conexao,
)
from pandora.db.colecao import (
    obter_configuracao_colecao,
    xp_necessario_nivel,
)


# --------------------------------------------------------------------------
# Batalha 5x5 com Aposta de Personagem (2026-09-01) - CRUD puro, regra de
# negócio (validação/cálculo/resolução) mora em `pandora.batalha`.
# --------------------------------------------------------------------------

def batalha_ativa_do_jogador(guild_id, user_id):
    """Desafio NÃO terminal (nem 'concluida' nem 'cancelada') onde esse
    jogador é desafiante OU defensor - usado pra "1 batalha por vez" e pro
    hub "⚔️ Batalha" saber o que mostrar. `None` se não tiver nenhum."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT * FROM colecao_batalha_desafios WHERE guild_id = ? "
            "AND status NOT IN ('concluida', 'cancelada') "
            "AND (desafiante_id = ? OR defensor_id = ?) "
            "ORDER BY id DESC LIMIT 1",
            (str(guild_id), str(user_id), str(user_id)),
        ).fetchone()
    return dict(linha) if linha else None


def batalha_por_id(desafio_id):
    with conexao() as conn:
        linha = conn.execute("SELECT * FROM colecao_batalha_desafios WHERE id = ?", (desafio_id,)).fetchone()
    return dict(linha) if linha else None


def criar_desafio_batalha(guild_id, desafiante_id, defensor_id, personagem_id, aposta_wishards, ordem_desafiante, canal_id=None):
    """`canal_id` (2026-09-02, Auto-Defesa) - onde o desafio nasceu, pro
    `batalha.SchedulerBatalha` saber onde postar o resultado se o defensor
    nunca responder e o auto-resolve de 10min entrar em ação."""
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        cursor = conn.execute(
            "INSERT INTO colecao_batalha_desafios ("
            "guild_id, canal_id, desafiante_id, defensor_id, personagem_id, aposta_wishards, ordem_desafiante, criado_em"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(guild_id), str(canal_id) if canal_id else None, str(desafiante_id), str(defensor_id),
                personagem_id, aposta_wishards, json.dumps(ordem_desafiante), agora,
            ),
        )
        return cursor.lastrowid


def definir_ordem_defensor(desafio_id, ordem_defensor):
    with conexao() as conn:
        conn.execute(
            "UPDATE colecao_batalha_desafios SET ordem_defensor = ?, status = 'em_andamento' WHERE id = ?",
            (json.dumps(ordem_defensor), desafio_id),
        )


def finalizar_desafio_batalha(desafio_id, placar_desafiante, placar_defensor):
    with conexao() as conn:
        conn.execute(
            "UPDATE colecao_batalha_desafios SET placar_desafiante = ?, placar_defensor = ?, "
            "status = 'concluida', resolvido_em = ? WHERE id = ?",
            (placar_desafiante, placar_defensor, datetime.now(timezone.utc).isoformat(), desafio_id),
        )


def cancelar_desafio_batalha(desafio_id):
    with conexao() as conn:
        conn.execute(
            "UPDATE colecao_batalha_desafios SET status = 'cancelada', resolvido_em = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), desafio_id),
        )


def cooldown_batalha_ok(guild_id, desafiante_id, defensor_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT ultimo_desafio_em FROM colecao_batalha_cooldown WHERE guild_id = ? "
            "AND desafiante_id = ? AND defensor_id = ?",
            (str(guild_id), str(desafiante_id), str(defensor_id)),
        ).fetchone()
    if linha is None:
        return True
    ultimo = datetime.fromisoformat(linha["ultimo_desafio_em"])
    horas = obter_configuracao_colecao(guild_id)["cooldown_batalha_horas"]
    return horas <= 0 or (datetime.now(timezone.utc) - ultimo) >= timedelta(hours=horas)


def registrar_desafio_cooldown(guild_id, desafiante_id, defensor_id):
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_batalha_cooldown (guild_id, desafiante_id, defensor_id, ultimo_desafio_em) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, desafiante_id, defensor_id) "
            "DO UPDATE SET ultimo_desafio_em = excluded.ultimo_desafio_em",
            (str(guild_id), str(desafiante_id), str(defensor_id), agora),
        )


def defesas_hoje(guild_id, defensor_id):
    hoje = datetime.now(timezone.utc).date().isoformat()
    with conexao() as conn:
        linha = conn.execute(
            "SELECT quantidade FROM colecao_batalha_defesas_hoje WHERE guild_id = ? AND defensor_id = ? AND data = ?",
            (str(guild_id), str(defensor_id), hoje),
        ).fetchone()
    return linha["quantidade"] if linha else 0


def registrar_defesa_hoje(guild_id, defensor_id):
    hoje = datetime.now(timezone.utc).date().isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_batalha_defesas_hoje (guild_id, defensor_id, data, quantidade) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(guild_id, defensor_id, data) DO UPDATE SET quantidade = quantidade + 1",
            (str(guild_id), str(defensor_id), hoje),
        )


def desafios_batalha_expirados(guild_id, limite_iso):
    """IDs de desafios 'aguardando_defensor' criados ANTES de `limite_iso`
    (defensor nunca respondeu) - usado por `paineis.SchedulerBatalha`
    (2026-09-02, Auto-Defesa por timeout de 10min, substitui o
    cancelamento por inatividade de 24h que existia antes - agora
    RESOLVE o desafio sozinho em vez de só cancelar)."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT id FROM colecao_batalha_desafios WHERE guild_id = ? "
            "AND status = 'aguardando_defensor' AND criado_em <= ?",
            (str(guild_id), limite_iso),
        ).fetchall()
    return [r["id"] for r in linhas]


# --------------------------------------------------------------------------
# Torre (2026-08-30) - progresso por (guild, usuário) + popularidade máxima
# do catálogo (usada pelo Power Base, `pandora.torre.power_base`).
# --------------------------------------------------------------------------

def andar_atual_torre(guild_id, user_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT andar_atual FROM colecao_torre_progresso WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    return linha["andar_atual"] if linha else 1


def avancar_andar_torre(guild_id, user_id):
    """Incrementa o andar atual em 1 e devolve o novo valor - só chamado
    depois de uma vitória (`pandora.torre.tentar_andar`)."""
    novo = andar_atual_torre(guild_id, user_id) + 1
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_torre_progresso (guild_id, user_id, andar_atual) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET andar_atual = excluded.andar_atual",
            (str(guild_id), str(user_id), novo),
        )
    return novo


def registrar_vitorias_torre_em_lote(guild_id, user_id, vitorias, andar_final, party_final_ids):
    """Persiste uma sequência já validada de vitórias da Torre em UMA
    transação.

    ``subir_max`` decide as composições e valida os andares em memória; este
    método só grava o resultado. Mantém uma linha de ledger por andar para
    WiShards e XP, mas evita abrir/confirmar quatro conexões SQLite por
    vitória. A Party é gravada uma vez, com a última composição vencedora.
    """
    if not vitorias:
        return
    agora = datetime.now(timezone.utc).isoformat()
    guild_id, user_id = str(guild_id), str(user_id)
    with conexao() as conn:
        saldo_linha = conn.execute(
            "SELECT saldo FROM colecao_wishards_saldo WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
        saldo = saldo_linha["saldo"] if saldo_linha else 0
        linhas_wishards = []
        for vitoria in vitorias:
            saldo += vitoria["recompensa"]
            andar = vitoria["andar"]
            linhas_wishards.append((
                guild_id, user_id, vitoria["recompensa"], "torre_andar", f"Andar {andar}", str(andar), saldo, agora,
            ))
        conn.execute(
            "INSERT INTO colecao_wishards_saldo (guild_id, user_id, saldo) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET saldo = excluded.saldo",
            (guild_id, user_id, saldo),
        )
        conn.executemany(
            "INSERT INTO colecao_wishards_ledger "
            "(guild_id, user_id, quantidade, origem, motivo, referencia, saldo_resultante, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            linhas_wishards,
        )

        progresso = conn.execute(
            "SELECT nivel, xp FROM colecao_progressao WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
        nivel, xp = (progresso["nivel"], progresso["xp"]) if progresso else (1, 0)
        linhas_xp = []
        for vitoria in vitorias:
            xp += vitoria["xp"]
            while xp >= xp_necessario_nivel(nivel, guild_id, user_id):
                xp -= xp_necessario_nivel(nivel, guild_id, user_id)
                nivel += 1
            andar = vitoria["andar"]
            linhas_xp.append((
                guild_id, user_id, vitoria["xp"], "torre_andar", f"Andar {andar}", str(andar), nivel, agora,
            ))
        conn.execute(
            "INSERT INTO colecao_progressao (guild_id, user_id, nivel, xp) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel = excluded.nivel, xp = excluded.xp",
            (guild_id, user_id, nivel, xp),
        )
        conn.executemany(
            "INSERT INTO colecao_xp_progressao_ledger "
            "(guild_id, user_id, quantidade, origem, motivo, referencia, nivel_resultante, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            linhas_xp,
        )

        vitorias_por_personagem = {}
        for vitoria in vitorias:
            for personagem_id in vitoria["personagem_ids"]:
                vitorias_por_personagem[personagem_id] = vitorias_por_personagem.get(personagem_id, 0) + 1
        conn.executemany(
            "INSERT INTO colecao_torre_estatisticas (guild_id, user_id, personagem_id, andares_vencidos) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, personagem_id) DO UPDATE SET "
            "andares_vencidos = andares_vencidos + excluded.andares_vencidos",
            [(guild_id, user_id, personagem_id, quantidade) for personagem_id, quantidade in vitorias_por_personagem.items()],
        )

        conn.execute("DELETE FROM colecao_equipe WHERE guild_id = ? AND user_id = ? AND tipo = 'party'", (guild_id, user_id))
        conn.executemany(
            "INSERT INTO colecao_equipe (guild_id, user_id, tipo, posicao, personagem_id) VALUES (?, ?, 'party', ?, ?)",
            [(guild_id, user_id, posicao, personagem_id) for posicao, personagem_id in enumerate(party_final_ids, start=1)],
        )
        conn.execute(
            "INSERT INTO colecao_torre_progresso (guild_id, user_id, andar_atual) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET andar_atual = excluded.andar_atual",
            (guild_id, user_id, andar_final),
        )


_popularidade_maxima_cache = None


def popularidade_maxima_catalogo():
    """Maior `popularidade` do catálogo INTEIRO - usada como `likes_max` na
    fórmula de Power Base (`pandora.torre.power_base`). Cacheada em memória
    (o catálogo só muda via sincronização periódica, não vale a pena
    recalcular a cada Power) - `None` só na 1ª chamada do processo."""
    global _popularidade_maxima_cache
    if _popularidade_maxima_cache is None:
        with conexao() as conn:
            linha = conn.execute("SELECT MAX(popularidade) AS maximo FROM colecao_personagens").fetchone()
        _popularidade_maxima_cache = linha["maximo"] or 1
    return _popularidade_maxima_cache


# --------------------------------------------------------------------------
# World Boss (2026-09-01) - CRUD puro, regra de negócio (mecânicas/turnos/
# scheduler) mora em `pandora.worldboss`.
# --------------------------------------------------------------------------

def worldboss_criar_evento(
    guild_id, canal_id, boss_tipo, boss_hp_maximo, boss_atk_base, estado_mecanica, inscricoes_fecham_em,
    dificuldade=None, cp_recomendado=None,
):
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        cursor = conn.execute(
            "INSERT INTO colecao_worldboss_eventos ("
            "guild_id, canal_id, boss_tipo, boss_hp_maximo, boss_hp_atual, boss_atk_base, boss_atk_atual, "
            "estado_mecanica, dificuldade, cp_recomendado, criado_em, inscricoes_fecham_em"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(guild_id), str(canal_id) if canal_id else None, boss_tipo, boss_hp_maximo, boss_hp_maximo,
                boss_atk_base, boss_atk_base, json.dumps(estado_mecanica), dificuldade, cp_recomendado,
                agora, inscricoes_fecham_em,
            ),
        )
        return cursor.lastrowid


def worldboss_evento_por_id(evento_id):
    with conexao() as conn:
        linha = conn.execute("SELECT * FROM colecao_worldboss_eventos WHERE id = ?", (evento_id,)).fetchone()
    return dict(linha) if linha else None


def worldboss_evento_ativo(guild_id):
    """Evento NÃO terminal (inscrições ou em combate) desse servidor -
    "cada aparição inicia um evento independente", nunca 2 ao mesmo tempo
    no mesmo servidor."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT * FROM colecao_worldboss_eventos WHERE guild_id = ? "
            "AND status NOT IN ('vitoria', 'derrota', 'expirado_por_turnos', 'cancelado_sem_participantes') "
            "ORDER BY id DESC LIMIT 1",
            (str(guild_id),),
        ).fetchone()
    return dict(linha) if linha else None


def worldboss_eventos_com_inscricoes_vencidas(agora_iso):
    """TODOS os servidores - usado pelo tick do scheduler (30s), que
    resolve fechamento de inscrições sem precisar saber de guild nenhuma
    de antemão."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT id FROM colecao_worldboss_eventos WHERE status = 'inscricoes' AND inscricoes_fecham_em <= ?",
            (agora_iso,),
        ).fetchall()
    return [r["id"] for r in linhas]


def worldboss_eventos_com_turno_pendente(agora_iso):
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT id FROM colecao_worldboss_eventos WHERE status = 'em_combate' AND proximo_turno_em <= ?",
            (agora_iso,),
        ).fetchall()
    return [r["id"] for r in linhas]


def worldboss_iniciar_combate(evento_id, time_hp_maximo, time_dano_turno, time_cura_turno, estado_mecanica, proximo_turno_em):
    with conexao() as conn:
        conn.execute(
            "UPDATE colecao_worldboss_eventos SET status = 'em_combate', time_hp_maximo = ?, time_hp_atual = ?, "
            "time_dano_turno = ?, time_cura_turno = ?, estado_mecanica = ?, proximo_turno_em = ? WHERE id = ?",
            (
                time_hp_maximo, time_hp_maximo, time_dano_turno, time_cura_turno,
                json.dumps(estado_mecanica), proximo_turno_em, evento_id,
            ),
        )


def worldboss_atualizar_turno(evento_id, turno_atual, boss_hp_atual, boss_atk_atual, time_hp_atual, estado_mecanica, proximo_turno_em):
    with conexao() as conn:
        conn.execute(
            "UPDATE colecao_worldboss_eventos SET turno_atual = ?, boss_hp_atual = ?, boss_atk_atual = ?, "
            "time_hp_atual = ?, estado_mecanica = ?, proximo_turno_em = ? WHERE id = ?",
            (turno_atual, boss_hp_atual, boss_atk_atual, time_hp_atual, json.dumps(estado_mecanica), proximo_turno_em, evento_id),
        )


def worldboss_finalizar(evento_id, status):
    with conexao() as conn:
        conn.execute(
            "UPDATE colecao_worldboss_eventos SET status = ?, concluido_em = ? WHERE id = ?",
            (status, datetime.now(timezone.utc).isoformat(), evento_id),
        )


def worldboss_definir_participante(evento_id, user_id, personagem_id, categoria, categorias_selecionadas, cp, origem):
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_worldboss_participantes ("
            "evento_id, user_id, personagem_id, categoria, categorias_selecionadas, cp, origem, entrou_em"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(evento_id, user_id) DO UPDATE SET personagem_id = excluded.personagem_id, "
            "categoria = excluded.categoria, categorias_selecionadas = excluded.categorias_selecionadas, "
            "cp = excluded.cp, origem = excluded.origem",
            (evento_id, str(user_id), personagem_id, categoria, json.dumps(categorias_selecionadas), cp, origem, agora),
        )


def worldboss_remover_participante(evento_id, user_id):
    with conexao() as conn:
        conn.execute(
            "DELETE FROM colecao_worldboss_participantes WHERE evento_id = ? AND user_id = ?",
            (evento_id, str(user_id)),
        )


def worldboss_participante(evento_id, user_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT * FROM colecao_worldboss_participantes WHERE evento_id = ? AND user_id = ?",
            (evento_id, str(user_id)),
        ).fetchone()
    return dict(linha) if linha else None


def worldboss_participantes(evento_id):
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT * FROM colecao_worldboss_participantes WHERE evento_id = ?", (evento_id,),
        ).fetchall()
    return [dict(r) for r in linhas]


def worldboss_auto_ativo(guild_id, user_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT ativo, categorias FROM colecao_worldboss_auto WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    if linha is None:
        return False, ["DPS", "Tank", "Support"]
    return bool(linha["ativo"]), json.loads(linha["categorias"])


def worldboss_definir_auto(guild_id, user_id, ativo, categorias):
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_worldboss_auto (guild_id, user_id, ativo, categorias) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET ativo = excluded.ativo, categorias = excluded.categorias",
            (str(guild_id), str(user_id), 1 if ativo else 0, json.dumps(categorias)),
        )


def worldboss_usuarios_auto_ativos(guild_id):
    """(user_id, categorias) de quem tem Entrada Automática ligada nesse
    servidor - usado só DEPOIS que as inscrições manuais encerram (Seção
    8/10), pra quem ainda não tem participação registrada nesse evento."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT user_id, categorias FROM colecao_worldboss_auto WHERE guild_id = ? AND ativo = 1",
            (str(guild_id),),
        ).fetchall()
    return [(r["user_id"], json.loads(r["categorias"])) for r in linhas]


# --------------------------------------------------------------------------
# Proteção PvP (2026-09-01, item "Proteção", Seção 7)
# --------------------------------------------------------------------------

def aplicar_protecao_pvp(guild_id, user_id, personagem_id):
    with conexao() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO colecao_protecao_pvp (guild_id, user_id, personagem_id, aplicada_em) VALUES (?, ?, ?, ?)",
            (str(guild_id), str(user_id), personagem_id, datetime.now(timezone.utc).isoformat()),
        )


def remover_protecao_pvp(guild_id, user_id, personagem_id):
    with conexao() as conn:
        conn.execute(
            "DELETE FROM colecao_protecao_pvp WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        )


def esta_protegida_pvp(guild_id, user_id, personagem_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT 1 FROM colecao_protecao_pvp WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        ).fetchone()
    return linha is not None


def personagens_protegidas_pvp(guild_id, user_id):
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT personagem_id FROM colecao_protecao_pvp WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchall()
    return [r["personagem_id"] for r in linhas]


# --------------------------------------------------------------------------
# Personagens perdidas na Batalha 5x5 (2026-09-01, item "Revanche", Seção 8)
# --------------------------------------------------------------------------

def registrar_personagem_perdida(guild_id, personagem_id, jogador_perdedor_id):
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_batalha_personagens_perdidas (guild_id, personagem_id, jogador_perdedor_id, perdida_em, recuperada) "
            "VALUES (?, ?, ?, ?, 0) "
            "ON CONFLICT(guild_id, personagem_id, jogador_perdedor_id) DO UPDATE SET "
            "perdida_em = excluded.perdida_em, recuperada = 0",
            (str(guild_id), personagem_id, str(jogador_perdedor_id), datetime.now(timezone.utc).isoformat()),
        )


def personagem_perdida_por(guild_id, personagem_id, jogador_perdedor_id):
    """`True` se `jogador_perdedor_id` perdeu ESSA personagem numa Batalha
    5x5 e ainda não recuperou de volta - usado pra validar o item
    Revanche (só pode ser usado contra uma personagem que você realmente
    perdeu daquele jeito)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT 1 FROM colecao_batalha_personagens_perdidas WHERE guild_id = ? AND personagem_id = ? "
            "AND jogador_perdedor_id = ? AND recuperada = 0",
            (str(guild_id), personagem_id, str(jogador_perdedor_id)),
        ).fetchone()
    return linha is not None


def marcar_personagem_recuperada(guild_id, personagem_id, jogador_perdedor_id):
    with conexao() as conn:
        conn.execute(
            "UPDATE colecao_batalha_personagens_perdidas SET recuperada = 1 "
            "WHERE guild_id = ? AND personagem_id = ? AND jogador_perdedor_id = ?",
            (str(guild_id), personagem_id, str(jogador_perdedor_id)),
        )


def personagens_perdidas_recuperaveis(guild_id, jogador_perdedor_id):
    """Personagens que esse jogador perdeu numa Batalha 5x5 e ainda não
    recuperou - usado pro item ⚔️ Revanche (painel "🎒 Inventário" lista
    isso pra escolher contra qual desafiar de novo)."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT p.* FROM colecao_batalha_personagens_perdidas b "
            "JOIN colecao_personagens p ON p.id = b.personagem_id "
            "WHERE b.guild_id = ? AND b.jogador_perdedor_id = ? AND b.recuperada = 0",
            (str(guild_id), str(jogador_perdedor_id)),
        ).fetchall()
    return [dict(r) for r in linhas]


# --------------------------------------------------------------------------
# Chave da Torre (2026-09-01, Seção 9)
# --------------------------------------------------------------------------

def definir_chave_torre_ativa(guild_id, user_id, ativa):
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_torre_chave_ativa (guild_id, user_id, ativa) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET ativa = excluded.ativa",
            (str(guild_id), str(user_id), 1 if ativa else 0),
        )


def chave_torre_ativa(guild_id, user_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT ativa FROM colecao_torre_chave_ativa WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    return bool(linha["ativa"]) if linha else False


# --------------------------------------------------------------------------
# Chamado (2026-09-01, escolhe o próximo World Boss, Seção 11)
# --------------------------------------------------------------------------

def definir_worldboss_forcado(guild_id, boss_tipo):
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_worldboss_proximo_forcado (guild_id, boss_tipo) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET boss_tipo = excluded.boss_tipo",
            (str(guild_id), boss_tipo),
        )


def consumir_worldboss_forcado(guild_id):
    """Lê e APAGA de uma vez (consumido, vale só pro próximo evento) -
    devolve o `boss_tipo` ou `None` se ninguém usou Chamado."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT boss_tipo FROM colecao_worldboss_proximo_forcado WHERE guild_id = ?", (str(guild_id),),
        ).fetchone()
        if linha is None:
            return None
        conn.execute("DELETE FROM colecao_worldboss_proximo_forcado WHERE guild_id = ?", (str(guild_id),))
    return linha["boss_tipo"]


# --------------------------------------------------------------------------
# Estatísticas de vitória na Torre por personagem (2026-09-01)
# --------------------------------------------------------------------------

def registrar_vitoria_torre_personagens(guild_id, user_id, personagem_ids):
    with conexao() as conn:
        for personagem_id in personagem_ids:
            conn.execute(
                "INSERT INTO colecao_torre_estatisticas (guild_id, user_id, personagem_id, andares_vencidos) "
                "VALUES (?, ?, ?, 1) "
                "ON CONFLICT(guild_id, user_id, personagem_id) DO UPDATE SET andares_vencidos = andares_vencidos + 1",
                (str(guild_id), str(user_id), personagem_id),
            )


def andares_vencidos_personagem(guild_id, user_id, personagem_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT andares_vencidos FROM colecao_torre_estatisticas WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        ).fetchone()
    return linha["andares_vencidos"] if linha else 0


def estatisticas_torre_top(guild_id, user_id, limite=10):
    """[{"personagem_id", "nome", "andares_vencidos"}, ...] - as
    personagens que mais contribuíram pra vitórias na Torre, maior
    primeiro."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT s.personagem_id, s.andares_vencidos, p.nome FROM colecao_torre_estatisticas s "
            "JOIN colecao_personagens p ON p.id = s.personagem_id "
            "WHERE s.guild_id = ? AND s.user_id = ? ORDER BY s.andares_vencidos DESC LIMIT ?",
            (str(guild_id), str(user_id), limite),
        ).fetchall()
    return [dict(r) for r in linhas]
