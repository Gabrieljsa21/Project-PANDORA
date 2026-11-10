# -*- coding: utf-8 -*-
"""Loja, garantia de raridade, Merge, Trocas, Recompensa Diária, upgrades de rolls/claims e Roll/Claim Permanente.

Parte de `pandora.db` (dividido por domínio em 2026-11-10); de fora do
pacote, continuar usando `from pandora import db` e `db.<nome>`."""
import json
from datetime import datetime, timedelta, timezone
from pandora.config import FUSO_BRASILIA
from pandora.db.nucleo import (
    conexao,
    fmt_numero,
    serializar_por_jogador,
)
from pandora.db.colecao import (
    creditar_wishards,
    debitar_wishards,
    definir_afinidade_inicial,
    dono_do_personagem,
    obter_configuracao_colecao,
    personagem_por_id,
    progressao_conta,
    reivindicar,
)


# --------------------------------------------------------------------------
# Loja e Guaranteed Roll (ERIS_sistema_colecao_wishards.md Seções 10/12)
# --------------------------------------------------------------------------

# 🔥 "Valores configuráveis para balanceamento" (Seção 10) - por enquanto
# constantes fixas (não por servidor ainda, diferente do resto da
# dificuldade) - primeira versão, ajustável depois se pedirem.
PRECOS_LOJA = {1: 250, 2: 500, 3: 1000, 4: 2500, 5: 5000}

# 🔥 SEMPRE metade do preço de "Comprar" da MESMA raridade (2026-08-30,
# pedido do usuário: "Da p comprar um 5* por 5k mas pegar uma aleatório
# custa 8k? Aleatorio deveria ser metade" - achado real: a versão antiga
# tinha número fixo por raridade, sem ligação nenhuma com `PRECOS_LOJA`,
# e o 5⭐ tinha ficado MAIS CARO (8.000) que comprar uma personagem
# ESPECÍFICA e escolhida (5.000) - ao contrário do esperado, já que
# Garantir dá MENOS controle (a personagem em si continua aleatória, só
# a raridade mínima é garantida). Derivado direto de `PRECOS_LOJA` agora
# (não mais uma tabela solta) - nunca mais pode divergir de novo.
PRECOS_GARANTIA = {raridade: preco // 2 for raridade, preco in PRECOS_LOJA.items() if raridade >= 3}


@serializar_por_jogador
def comprar_personagem(guild_id, user_id, personagem_id):
    """Só personagens LIVRES nesse servidor podem ser compradas (Seção 10).
    Desconta o preço ANTES de tentar `reivindicar` - se perder a corrida
    (outra pessoa comprou/reivindicou no meio), reembolsa na hora. Devolve
    (ok: bool, mensagem: str)."""
    personagem = personagem_por_id(personagem_id)
    if personagem is None:
        return False, "Não achei nenhum personagem com esse #id."
    if dono_do_personagem(guild_id, personagem_id) is not None:
        return False, "Essa personagem já tem dono nesse servidor."
    preco = PRECOS_LOJA.get(personagem["raridade"])
    if debitar_wishards(guild_id, user_id, preco, "loja_compra", personagem["nome"], str(personagem_id)) is None:
        return False, f"Custa {fmt_numero(preco)} WiShards e você não tem o suficiente."
    if not reivindicar(guild_id, personagem_id, user_id):
        creditar_wishards(guild_id, user_id, preco, "loja_reembolso", personagem["nome"], str(personagem_id))
        return False, "Alguém conseguiu essa personagem antes de você - reembolsado."

    definir_afinidade_inicial(guild_id, user_id, personagem_id)
    return True, f"{personagem['nome']} comprada por {fmt_numero(preco)} WiShards."


def definir_garantia(guild_id, user_id, raridade_minima):
    """Compra de Guaranteed Roll - vale pro PRÓXIMO roll (`/wa`/`/ha`/`/ma`),
    qualquer um. Cria a linha de estado se ainda não existir (mesmos
    defaults de sempre pros outros campos, ver `_consumir_recurso`)."""
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_estado_jogador ("
            "guild_id, user_id, rolls_restantes, rolls_resetam_em, "
            "claims_restantes, claims_resetam_em, garantia_raridade_minima"
            ") VALUES (?, ?, 0, ?, 1, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET garantia_raridade_minima = excluded.garantia_raridade_minima",
            (str(guild_id), str(user_id), datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(), raridade_minima),
        )


def consumir_garantia(guild_id, user_id):
    """Lê e LIMPA a garantia pendente (consumo único) - devolve a raridade
    mínima que estava marcada, ou None se não havia nenhuma."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT garantia_raridade_minima FROM colecao_estado_jogador WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
        valor = linha["garantia_raridade_minima"] if linha else None
        if valor is not None:
            conn.execute(
                "UPDATE colecao_estado_jogador SET garantia_raridade_minima = NULL WHERE guild_id = ? AND user_id = ?",
                (str(guild_id), str(user_id)),
            )
        return valor


def resetar_rolls_admin(guild_id, user_id):
    """Força o ciclo de rolls de alguém a recarregar AGORA, sem esperar o
    horário fixo passar (`/colecao_admin resetar_rolls`, 2026-08-29,
    pedido do usuário: "cria um comando q me permite resetar rolls de
    alguem... qnd sou admin") - mesmo cálculo que o reset PREGUIÇOSO já
    faz sozinho (`_restantes_validos`/`_fim_ciclo_fixo`), só que forçado
    na hora em vez de esperar o ciclo atual vencer. Devolve o novo limite
    (quantos rolls a pessoa passou a ter)."""
    config = obter_configuracao_colecao(guild_id)
    bonus_rolls, _bonus_claims = bonus_permanente_total(guild_id, user_id)
    bonus_progressao_rolls, _bonus_progressao_claims = bonus_acoes_por_progressao(guild_id, user_id, config)
    limite_rolls = config["rolls_por_ciclo"] + bonus_progressao_rolls + bonus_rolls
    agora = datetime.now(timezone.utc)
    fim_ciclo = _fim_ciclo_fixo(agora, config["ciclo_rolls_minutos"])
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_estado_jogador (guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em) "
            "VALUES (?, ?, ?, ?, 1, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET rolls_restantes = excluded.rolls_restantes, rolls_resetam_em = excluded.rolls_resetam_em",
            (str(guild_id), str(user_id), limite_rolls, fim_ciclo.isoformat(), agora.isoformat()),
        )
    return limite_rolls


def resetar_claims_admin(guild_id, user_id):
    """Mesma ideia de `resetar_rolls_admin`, só que pro ciclo de CLAIMS
    (`/colecao_admin resetar_claims`, 2026-08-29, pedido do usuário
    "comando p resetar claim tbm"). Devolve o novo limite (quantos claims
    a pessoa passou a ter, já incluindo o upgrade permanente dela -
    `bonus_acoes_por_progressao`)."""
    config = obter_configuracao_colecao(guild_id)
    _bonus_rolls, bonus_claims = bonus_permanente_total(guild_id, user_id)
    _bonus_progressao_rolls, bonus_progressao_claims = bonus_acoes_por_progressao(guild_id, user_id, config)
    limite_claims = config["claims_por_ciclo"] + bonus_progressao_claims + bonus_claims
    agora = datetime.now(timezone.utc)
    fim_ciclo = _fim_ciclo_fixo(agora, config["ciclo_claims_minutos"])
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_estado_jogador (guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em) "
            "VALUES (?, ?, 0, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET claims_restantes = excluded.claims_restantes, claims_resetam_em = excluded.claims_resetam_em",
            (str(guild_id), str(user_id), agora.isoformat(), limite_claims, fim_ciclo.isoformat()),
        )
    return limite_claims


# 🔥 `atribuir_personagem_admin` MUDOU de módulo (2026-08-29, usuário: "qnd
# vc da personagem p alguem, n faz os esquemas de por classe... tem de
# seguir o msm fluxo de coletar") - virou `gacha.atribuir_personagem_
# admin` (async, reaproveita `revelar_classe`/`_embed_confirmacao_claim`
# do claim normal) porque a revelação de classe pede a GAIA por HTTP,
# fluxo que só existe em `gacha.py`; `db.py` não teria como chamar isso
# sem criar um ciclo de import.


# --------------------------------------------------------------------------
# Merge / Sacrifício (ERIS_sistema_colecao_wishards.md Seção 14)
# --------------------------------------------------------------------------

def remover_propriedade_sem_pagamento(guild_id, personagem_id, user_id):
    """Usado SÓ pelo Merge - diferente de `divorciar`, não paga nada (as 5
    personagens são "consumidas", não divorciadas). Devolve True se de fato
    removeu."""
    with conexao() as conn:
        cursor = conn.execute(
            "DELETE FROM colecao_propriedade WHERE guild_id = ? AND personagem_id = ? AND dono_id = ?",
            (str(guild_id), personagem_id, str(user_id)),
        )
        return cursor.rowcount > 0


# --------------------------------------------------------------------------
# Trocas bilaterais (ERIS_sistema_colecao_wishards.md Seção 13)
# --------------------------------------------------------------------------

def transferir_personagem(guild_id, personagem_id, novo_dono_id):
    """Troca de dono direta (não passa por `reivindicar`/`divorciar` - não é
    claim nem divórcio) - Afinidade NUNCA se transfere (Seção 13): o dono
    antigo mantém o histórico dele intacto (útil se recuperar a personagem
    de volta um dia); o novo dono ganha Afinidade 1 se nunca tiver sido dono
    antes, ou retoma o vínculo antigo se já tinha sido (mesma regra do
    resgate pós-divórcio, `definir_afinidade_inicial`)."""
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "DELETE FROM colecao_propriedade WHERE guild_id = ? AND personagem_id = ?",
            (str(guild_id), personagem_id),
        )
        conn.execute(
            "INSERT INTO colecao_propriedade (guild_id, personagem_id, dono_id, reivindicado_em) VALUES (?, ?, ?, ?)",
            (str(guild_id), personagem_id, str(novo_dono_id), agora),
        )
    definir_afinidade_inicial(guild_id, novo_dono_id, personagem_id)


def criar_proposta_troca(guild_id, proponente_id, alvo_id, oferece_personagens, oferece_wishards, pede_personagens, pede_wishards):
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        cursor = conn.execute(
            "INSERT INTO colecao_troca_proposta "
            "(guild_id, proponente_id, alvo_id, oferece_personagens, oferece_wishards, pede_personagens, pede_wishards, status, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pendente', ?)",
            (
                str(guild_id), str(proponente_id), str(alvo_id),
                json.dumps(list(oferece_personagens)), oferece_wishards,
                json.dumps(list(pede_personagens)), pede_wishards, agora,
            ),
        )
        return cursor.lastrowid


def obter_proposta_troca(proposta_id):
    with conexao() as conn:
        linha = conn.execute("SELECT * FROM colecao_troca_proposta WHERE id = ?", (proposta_id,)).fetchone()
    if linha is None:
        return None
    proposta = dict(linha)
    proposta["oferece_personagens"] = json.loads(proposta["oferece_personagens"])
    proposta["pede_personagens"] = json.loads(proposta["pede_personagens"])
    return proposta


def atualizar_status_proposta(proposta_id, status):
    with conexao() as conn:
        conn.execute("UPDATE colecao_troca_proposta SET status = ? WHERE id = ?", (status, proposta_id))


# ---- Tabela `colecao_wishlist` original (2026-09-03, MECANISMO
# APOSENTADO - fundido no antigo Favoritos, que herdou o nome "wishlist"
# pras funções, ver seção "Wishlist" acima) - a tabela em si continua
# existindo (sem migração destrutiva), mas nada mais escreve/lê nela;
# `db.inicializar()` copiou 1x todo o conteúdo pra `colecao_favoritas`
# (ver comentário lá). `wishlist_adicionar`/`wishlist_remover`/
# `wishlist_listar`/`wishlist_disponiveis_no_guild`/`esta_na_wishlist`
# (seção "Wishlist" acima) são o caminho único agora, pra possuída ou não.


# ---- Cooldowns (rolls/claims por ciclo) ----

def _estado_jogador(conn, guild_id, user_id):
    return conn.execute(
        "SELECT * FROM colecao_estado_jogador WHERE guild_id = ? AND user_id = ?",
        (str(guild_id), str(user_id)),
    ).fetchone()


_EPOCA_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _fim_ciclo_fixo(agora, janela_minutos):
    """Fim do ciclo ATUAL num cronograma fixo, ancorado na Época Unix (meia-
    noite UTC de 1970-01-01) - pedido do usuário: "os resets tem de ser a
    cada hora, 1h, 2h, 3h... não 1h após interação do usuário, vai ser fixo
    pra geral". Como a Época já cai em cheio, qualquer janela que divida 24h
    em partes iguais (1h/2h/3h/4h/6h/8h/12h/24h) também cai em horários
    "redondos" em UTC (ex.: janela de 1h reseta às XX:00 pra TODO MUNDO, não
    numa hora diferente por jogador dependendo de quando cada um rolou por
    último)."""
    janela = timedelta(minutes=janela_minutos)
    ciclos_completos = (agora - _EPOCA_UTC) // janela
    return _EPOCA_UTC + (ciclos_completos + 1) * janela


def _restantes_validos(linha, coluna_restante, coluna_reset, limite, janela_minutos, agora):
    """Lê `restantes`/reset de uma linha de `colecao_estado_jogador`
    reconciliando com o cronograma FIXO (`_fim_ciclo_fixo`) - um valor
    salvo que não bate com o ciclo fixo ATUAL (sobra de ANTES da correção
    de 2026-08-29, quando o reset ainda era calculado relativo à última
    ação de CADA jogador - achado real: um jogador continuou vendo "tenta
    de novo em ~7 min" mesmo depois do reset fixo já ter passado, porque o
    valor antigo salvo não tinha por que coincidir com a nova grade) é
    tratado como expirado NA HORA, em vez de esperar a data antiga
    (possivelmente desalinhada) passar sozinha. Devolve (restantes,
    reset_correto_iso)."""
    fim_ciclo_atual = _fim_ciclo_fixo(agora, janela_minutos)
    if linha is None:
        return limite, fim_ciclo_atual.isoformat()
    reset_salvo = datetime.fromisoformat(linha[coluna_reset])
    if reset_salvo <= agora or reset_salvo != fim_ciclo_atual:
        return limite, fim_ciclo_atual.isoformat()
    return linha[coluna_restante], fim_ciclo_atual.isoformat()


def _consumir_recurso(guild_id, user_id, coluna_restante, coluna_reset, limite, janela_minutos, quantidade=1):
    """Reset PREGUIÇOSO (sem job/cron varrendo jogador por jogador, ver
    PLANO_COLECAO_WAIFUS.md Seção 10: "calcula o ciclo atual matematicamente")
    - se o ciclo já expirou (ou tá desalinhado com o cronograma fixo, ver
    `_restantes_validos`), recarrega o contador ANTES de checar/consumir.
    O ciclo em si é FIXO/compartilhado (`_fim_ciclo_fixo`), não relativo à
    última ação do jogador. Devolve QUANTO foi consumido de fato (0 se não
    sobrava nada; pode ser menos que `quantidade` se sobrar menos que isso
    no ciclo - pedido de N rolls de uma vez nunca dá erro, só entrega o que
    der, ver `eris/colecao/gacha.py::rolar_varios`)."""
    agora = datetime.now(timezone.utc)
    with conexao() as conn:
        linha = _estado_jogador(conn, guild_id, user_id)
        restantes, novo_reset = _restantes_validos(linha, coluna_restante, coluna_reset, limite, janela_minutos, agora)
        a_consumir = min(quantidade, restantes)
        if a_consumir <= 0:
            return 0
        valores = {
            "rolls_restantes": linha["rolls_restantes"] if linha else 10,
            "rolls_resetam_em": linha["rolls_resetam_em"] if linha else agora.isoformat(),
            "claims_restantes": linha["claims_restantes"] if linha else 1,
            "claims_resetam_em": linha["claims_resetam_em"] if linha else agora.isoformat(),
        }
        valores[coluna_restante] = restantes - a_consumir
        valores[coluna_reset] = novo_reset
        conn.execute(
            "INSERT INTO colecao_estado_jogador ("
            "guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em"
            ") VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
            "rolls_restantes = excluded.rolls_restantes, rolls_resetam_em = excluded.rolls_resetam_em, "
            "claims_restantes = excluded.claims_restantes, claims_resetam_em = excluded.claims_resetam_em",
            (
                str(guild_id), str(user_id),
                valores["rolls_restantes"], valores["rolls_resetam_em"],
                valores["claims_restantes"], valores["claims_resetam_em"],
            ),
        )
        return a_consumir


def consumir_roll(guild_id, user_id, limite, janela_minutos):
    return _consumir_recurso(guild_id, user_id, "rolls_restantes", "rolls_resetam_em", limite, janela_minutos) > 0


def consumir_rolls(guild_id, user_id, quantidade, limite, janela_minutos):
    """Versão em lote de `consumir_roll` - pedido do usuário pra permitir
    "puxadas" de várias personagens num comando só (`/wa quantidade:10`).
    Devolve quantos rolls foram consumidos de fato (ver `_consumir_recurso`)."""
    return _consumir_recurso(guild_id, user_id, "rolls_restantes", "rolls_resetam_em", limite, janela_minutos, quantidade)


def consumir_claim(guild_id, user_id, limite, janela_minutos):
    return _consumir_recurso(guild_id, user_id, "claims_restantes", "claims_resetam_em", limite, janela_minutos) > 0


def rolls_disponiveis(guild_id, user_id, limite, janela_minutos):
    """Só CONSULTA, sem consumir - mesmo padrão de `claims_disponiveis`
    abaixo. Usado pelo Modo Auto-coleta por usuário (2026-08-30) pra
    checar SE a pessoa ainda não usou nenhum roll neste ciclo antes de
    rolar por ela (`rolls_disponiveis(...) == limite` significa "ciclo
    intocado")."""
    agora = datetime.now(timezone.utc)
    with conexao() as conn:
        linha = _estado_jogador(conn, guild_id, user_id)
    restantes, _ = _restantes_validos(linha, "rolls_restantes", "rolls_resetam_em", limite, janela_minutos, agora)
    return restantes


def claims_disponiveis(guild_id, user_id, limite, janela_minutos):
    """Só CONSULTA, sem consumir - usado pra bloquear ANTES de tentar
    reivindicar. O consumo de verdade (`consumir_claim`) só acontece se a
    reivindicação VENCER a corrida (PLANO_COLECAO_WAIFUS.md, Seção 9, passo
    6: "Consumir o claim somente se a conquista vencer") - perder pra outro
    clique não deveria gastar o cooldown de quem tentou. Mesma reconciliação
    de `_restantes_validos` (2026-08-29) - nunca reporta um valor zerado só
    porque o reset salvo é de antes do cronograma fixo."""
    agora = datetime.now(timezone.utc)
    with conexao() as conn:
        linha = _estado_jogador(conn, guild_id, user_id)
    restantes, _ = _restantes_validos(linha, "claims_restantes", "claims_resetam_em", limite, janela_minutos, agora)
    return restantes


def tempo_restante(guild_id, user_id, coluna_restante, coluna_reset, limite, janela_minutos):
    """Segundos até o cooldown resetar - só é maior que 0 quando o recurso já
    zerou (pra mensagem de erro amigável nos comandos). Passa pela mesma
    reconciliação de `_restantes_validos` (2026-08-29) - um reset salvo de
    antes do cronograma fixo (desalinhado com `_fim_ciclo_fixo`) conta como
    já expirado, nunca reporta um tempo de espera que não existe mais."""
    agora = datetime.now(timezone.utc)
    with conexao() as conn:
        linha = _estado_jogador(conn, guild_id, user_id)
    restantes, reset_correto = _restantes_validos(linha, coluna_restante, coluna_reset, limite, janela_minutos, agora)
    if restantes > 0:
        return 0
    reset_em = datetime.fromisoformat(reset_correto)
    return max(0, int((reset_em - agora).total_seconds()))


# --------------------------------------------------------------------------
# Recompensa Diária (2026-09-02, pedido do usuário - Seção 6/29 do plano
# original: "eventual recompensa diária") - reset por DIA DE CALENDÁRIO em
# horário de BRASÍLIA (`FUSO_BRASILIA`, 2026-09-03 - achado do usuário
# "Recompensa Diária tem q resetar as 0h": comparar por data em UTC fazia o
# resgate liberar de novo às 21h de Brasília, não à meia-noite local),
# diferente de rolls/claims (janela rolante fixa em minutos) - dá pra
# resgatar de novo a partir da meia-noite de Brasília, não 24h exatas
# depois do último clique. O timestamp GRAVADO continua em UTC (mesmo
# padrão do resto do banco) - só a COMPARAÇÃO de "que dia é hoje" converte
# pro fuso local antes de extrair `.date()`.
# --------------------------------------------------------------------------

RECOMPENSA_DIARIA_WISHARDS = 150  # valor POR NÍVEL de Progressão (2026-09-02, pedido do usuário: "multiplicada os wishards pelo nivel da progressao") - fica pra balanceamento, como o resto


def diaria_disponivel(guild_id, user_id):
    """True se o jogador ainda não resgatou a Recompensa Diária HOJE (data
    de calendário em horário de Brasília) - nunca ter resgatado (linha/
    coluna None) conta como disponível."""
    with conexao() as conn:
        linha = _estado_jogador(conn, guild_id, user_id)
    if linha is None or linha["diaria_reivindicada_em"] is None:
        return True
    ultima = datetime.fromisoformat(linha["diaria_reivindicada_em"]).astimezone(FUSO_BRASILIA)
    return ultima.date() < datetime.now(FUSO_BRASILIA).date()


def reivindicar_diaria(guild_id, user_id):
    """Marca a Recompensa Diária como resgatada HOJE - devolve False sem
    escrever nada se já tiver sido resgatada hoje (checagem por DENTRO da
    mesma conexão/transação de `diaria_disponivel`, não só a leitura solta
    - evita 2 cliques quase simultâneos concedendo 2x)."""
    agora = datetime.now(timezone.utc)
    with conexao() as conn:
        linha = _estado_jogador(conn, guild_id, user_id)
        if linha is not None and linha["diaria_reivindicada_em"] is not None:
            ultima_local = datetime.fromisoformat(linha["diaria_reivindicada_em"]).astimezone(FUSO_BRASILIA)
            if ultima_local.date() >= agora.astimezone(FUSO_BRASILIA).date():
                return False
        conn.execute(
            "INSERT INTO colecao_estado_jogador "
            "(guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em, diaria_reivindicada_em) "
            "VALUES (?, ?, 0, ?, 0, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET diaria_reivindicada_em = excluded.diaria_reivindicada_em",
            (str(guild_id), str(user_id), agora.isoformat(), agora.isoformat(), agora.isoformat()),
        )
    return True


def bonus_acoes_por_progressao(guild_id, user_id, config=None):
    """Bônus pessoal de ações conquistado pela Progressão.

    Em cada bloco de 25 níveis, os níveis 5, 10, 15 e 20 concedem +5
    rolls por ciclo; o nível 25 concede +1 claim por ciclo. Os dois totais
    respeitam os tetos definidos pelo administrador do servidor.
    """
    config = config or obter_configuracao_colecao(guild_id)
    nivel = progressao_conta(guild_id, user_id)["nivel"]
    recompensas_roll = (nivel // 5) - (nivel // 25)
    bonus_rolls = min(config["teto_bonus_rolls_progressao"], recompensas_roll * 5)
    bonus_claims = min(config["teto_bonus_claims_progressao"], nivel // 25)
    return bonus_rolls, bonus_claims


def reivindicar_diaria_com_recompensa(guild_id, user_id):
    """Resgata a Recompensa Diária + credita `RECOMPENSA_DIARIA_WISHARDS ×
    nível de Progressão` em WiShards (2026-09-02, pedido do usuário:
    "multiplicada os wishards pelo nivel da progressao" - Progressão é
    SEM TETO, `db.progressao_conta`, então o valor da Diária cresce junto
    com a conta em vez de ficar defasado pra sempre nos 150 originais).
    Devolve (ok, novo_saldo_ou_None, wishards_creditados) - `ok=False` = já
    resgatou hoje, não credita nada de novo (`wishards_creditados=0`). O
    item raro (Seção "e da 1 item raro") é concedido por quem chama
    (`paineis._diaria`), não aqui - `db.py` não importa `pandora.itens`."""
    if not reivindicar_diaria(guild_id, user_id):
        return False, None, 0
    nivel = progressao_conta(guild_id, user_id)["nivel"]
    wishards = RECOMPENSA_DIARIA_WISHARDS * nivel
    novo_saldo = creditar_wishards(guild_id, user_id, wishards, "diaria")
    return True, novo_saldo, wishards


# --------------------------------------------------------------------------
# Upgrade permanente de rolls máximos (Seção 11) - único upgrade do plano
# com preços concretos; os outros ("ampliar wishlist", "claims
# armazenáveis", bônus de divórcio/reencontro/terceiro, desconto de loja,
# "wishlist luck", rerolls, slots de vitrine extras) ficaram sem número no
# plano ("valores ficam para balanceamento") - não implementados ainda.
# --------------------------------------------------------------------------

PRECOS_UPGRADE_ROLLS = {1: 1000, 2: 2500, 3: 5000, 4: 10000, 5: 25000}
BONUS_ROLLS_POR_NIVEL = 5
# 🔥 Nível máximo REMOVIDO (2026-09-03, pedido do usuário: "vamos remover
# limite de compra de upgrade de rolls e claims") - preço dos 5 primeiros
# níveis preservado (`PRECOS_UPGRADE_ROLLS`, ninguém que já comprou paga
# retroativo diferente); a partir do nível 6, `preco_upgrade_rolls` continua
# a mesma progressão geométrica (dobra por nível), mesmo espírito SEM TETO
# de Treinamento Global/Potencial da Coleção.


def preco_upgrade_rolls(nivel):
    if nivel in PRECOS_UPGRADE_ROLLS:
        return PRECOS_UPGRADE_ROLLS[nivel]
    return PRECOS_UPGRADE_ROLLS[5] * (2 ** (nivel - 5))


def custo_total_upgrade_rolls_ate(nivel_atual, nivel_alvo):
    """Soma o custo de CADA nível de `nivel_atual` até `nivel_alvo` (mesmo
    padrão de `custo_total_treinamento_ate`) - 0 se `nivel_alvo` não for
    maior que o atual."""
    if nivel_alvo <= nivel_atual:
        return 0
    return sum(preco_upgrade_rolls(n) for n in range(nivel_atual + 1, nivel_alvo + 1))


def nivel_upgrade_rolls(guild_id, user_id):
    with conexao() as conn:
        linha = _estado_jogador(conn, guild_id, user_id)
    return linha["nivel_upgrade_rolls"] if linha else 0


@serializar_por_jogador
def comprar_upgrade_rolls_ate(guild_id, user_id, nivel_alvo):
    """Devolve (ok: bool, mensagem: str) - pula DIRETO pro `nivel_alvo`
    (2026-09-03, substitui o antigo "+1 nível por clique" agora que o
    upgrade não tem mais teto - dropdown escolhe o alvo, custo é a soma de
    todos os degraus, mesmo padrão de `comprar_treinamento_global_ate`).
    +5 rolls PERMANENTES por nível em cima do `rolls_por_ciclo` do
    servidor (nunca substitui a config do servidor, só soma)."""
    nivel_atual = nivel_upgrade_rolls(guild_id, user_id)
    if nivel_alvo <= nivel_atual:
        return False, f"Upgrade de rolls já está no nível {nivel_atual} ou acima."
    custo = custo_total_upgrade_rolls_ate(nivel_atual, nivel_alvo)
    if debitar_wishards(guild_id, user_id, custo, "upgrade_rolls", f"nível {nivel_atual}->{nivel_alvo}") is None:
        return False, f"Custa {fmt_numero(custo)} WiShards e você não tem o suficiente."
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_estado_jogador ("
            "guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em, nivel_upgrade_rolls"
            ") VALUES (?, ?, 0, ?, 1, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel_upgrade_rolls = excluded.nivel_upgrade_rolls",
            (str(guild_id), str(user_id), agora, agora, nivel_alvo),
        )
    bonus_total = nivel_alvo * BONUS_ROLLS_POR_NIVEL
    return True, f"Upgrade de rolls nível {nivel_alvo}! +{fmt_numero(bonus_total)} rolls por ciclo, pra sempre (custou {fmt_numero(custo)} WiShards)."


# --------------------------------------------------------------------------
# Upgrade permanente de claims máximos (2026-08-29, pedido do usuário: "claim
# tem q ter upgrade permanente tbm") - mesmo espírito do upgrade de rolls
# acima, só que o bônus por nível é bem menor (+1, não +5) porque claim é o
# recurso que decide de verdade quem fica com a personagem - preços também
# mais altos por isso (sem número oficial em nenhum plano, escolhidos aqui
# como ponto de partida, mesmo espírito do upgrade de rolls original).
# --------------------------------------------------------------------------

PRECOS_UPGRADE_CLAIMS = {1: 2000, 2: 5000, 3: 10000, 4: 20000, 5: 40000}
BONUS_CLAIMS_POR_NIVEL = 1
# 🔥 Nível máximo REMOVIDO (2026-09-03) - mesmo motivo/padrão de
# `preco_upgrade_rolls` acima.


def preco_upgrade_claims(nivel):
    if nivel in PRECOS_UPGRADE_CLAIMS:
        return PRECOS_UPGRADE_CLAIMS[nivel]
    return PRECOS_UPGRADE_CLAIMS[5] * (2 ** (nivel - 5))


def custo_total_upgrade_claims_ate(nivel_atual, nivel_alvo):
    if nivel_alvo <= nivel_atual:
        return 0
    return sum(preco_upgrade_claims(n) for n in range(nivel_atual + 1, nivel_alvo + 1))


def nivel_upgrade_claims(guild_id, user_id):
    with conexao() as conn:
        linha = _estado_jogador(conn, guild_id, user_id)
    return linha["nivel_upgrade_claims"] if linha else 0


@serializar_por_jogador
def comprar_upgrade_claims_ate(guild_id, user_id, nivel_alvo):
    """Devolve (ok: bool, mensagem: str) - mesmo padrão de `comprar_
    upgrade_rolls_ate`. +1 claim PERMANENTE por nível em cima do
    `claims_por_ciclo` do servidor (nunca substitui a config do servidor,
    só soma)."""
    nivel_atual = nivel_upgrade_claims(guild_id, user_id)
    if nivel_alvo <= nivel_atual:
        return False, f"Upgrade de claims já está no nível {nivel_atual} ou acima."
    custo = custo_total_upgrade_claims_ate(nivel_atual, nivel_alvo)
    if debitar_wishards(guild_id, user_id, custo, "upgrade_claims", f"nível {nivel_atual}->{nivel_alvo}") is None:
        return False, f"Custa {fmt_numero(custo)} WiShards e você não tem o suficiente."
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_estado_jogador ("
            "guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em, nivel_upgrade_claims"
            ") VALUES (?, ?, 0, ?, 1, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel_upgrade_claims = excluded.nivel_upgrade_claims",
            (str(guild_id), str(user_id), agora, agora, nivel_alvo),
        )
    bonus_total = nivel_alvo * BONUS_CLAIMS_POR_NIVEL
    return True, f"Upgrade de claims nível {nivel_alvo}! +{fmt_numero(bonus_total)} claim(s) por ciclo, pra sempre (custou {fmt_numero(custo)} WiShards)."


# --------------------------------------------------------------------------
# Roll/Claim Permanente (2026-09-01, drop raro do World Boss OU compra na
# Loja) - contadores SEPARADOS por origem (pedido do usuário: "os rolls/
# claims permanentes vendidos na loja sao contados diferentes se ganhos
# dos boss"), cada um com seu próprio teto - `gacha._limite_rolls_atual`/
# o cálculo de claims somam os DOIS juntos no limite final.
# --------------------------------------------------------------------------

def bonus_permanente_drop(guild_id, user_id):
    """(bonus_rolls, bonus_claims) só da origem "drop do World Boss"."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT bonus_rolls_permanente_drop, bonus_claims_permanente_drop FROM colecao_estado_jogador "
            "WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    if linha is None:
        return 0, 0
    return linha["bonus_rolls_permanente_drop"], linha["bonus_claims_permanente_drop"]


def bonus_permanente_loja(guild_id, user_id):
    """(bonus_rolls, bonus_claims) só da origem "comprado na Loja"."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT bonus_rolls_permanente_loja, bonus_claims_permanente_loja FROM colecao_estado_jogador "
            "WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    if linha is None:
        return 0, 0
    return linha["bonus_rolls_permanente_loja"], linha["bonus_claims_permanente_loja"]


def bonus_permanente_total(guild_id, user_id):
    """(bonus_rolls, bonus_claims) somando AS DUAS origens - único valor
    que `gacha._limite_rolls_atual`/o cálculo de claims usam de verdade."""
    rolls_drop, claims_drop = bonus_permanente_drop(guild_id, user_id)
    rolls_loja, claims_loja = bonus_permanente_loja(guild_id, user_id)
    return rolls_drop + rolls_loja, claims_drop + claims_loja


def _adicionar_bonus_permanente(guild_id, user_id, coluna, quantidade):
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            f"INSERT INTO colecao_estado_jogador (guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em, {coluna}) "
            "VALUES (?, ?, 0, ?, 1, ?, ?) "
            f"ON CONFLICT(guild_id, user_id) DO UPDATE SET {coluna} = {coluna} + excluded.{coluna}",
            (str(guild_id), str(user_id), agora, agora, quantidade),
        )


def adicionar_bonus_permanente_drop(guild_id, user_id, campo, quantidade=1):
    """`campo` em {"rolls", "claims"} - vocabulário FECHADO, nunca
    interpolado a partir de entrada externa."""
    coluna = {"rolls": "bonus_rolls_permanente_drop", "claims": "bonus_claims_permanente_drop"}[campo]
    _adicionar_bonus_permanente(guild_id, user_id, coluna, quantidade)


def adicionar_bonus_permanente_loja(guild_id, user_id, campo, quantidade=1):
    """`campo` em {"rolls", "claims"} - vocabulário FECHADO, nunca
    interpolado a partir de entrada externa."""
    coluna = {"rolls": "bonus_rolls_permanente_loja", "claims": "bonus_claims_permanente_loja"}[campo]
    _adicionar_bonus_permanente(guild_id, user_id, coluna, quantidade)
