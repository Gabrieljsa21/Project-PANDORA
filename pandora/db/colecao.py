# -*- coding: utf-8 -*-
"""Catálogo de personagens, posse, Afinidade/Nível, saldo e ledger (WiShards/Soulstone) e Progressão Global da conta. Ficam juntos porque se chamam em ciclo.

Parte de `pandora.db` (dividido por domínio em 2026-11-10); de fora do
pacote, continuar usando `from pandora import db` e `db.<nome>`."""
import unicodedata
from datetime import datetime, timezone
from pandora.db.nucleo import (
    _CONFIG_COLECAO_PADRAO,
    _CORTES_RARIDADE,
    conexao,
    fmt_numero,
    serializar_por_jogador,
)


# --------------------------------------------------------------------------
# Coleção - catálogo de personagens
# --------------------------------------------------------------------------

def importar_personagens(personagens):
    """Upsert em lote por `fonte_id` (id original na fonte externa, ex.:
    get_waifu) - permite reimportar/atualizar o mesmo dataset sem duplicar
    linhas. `personagens`: iterável de {"fonte_id", "slug", "nome",
    "nome_original", "nome_romanizado", "imagem_url", "descricao", "serie",
    "genero", "nsfw", "popularidade", "tags"}."""
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.executemany(
            """
            INSERT INTO colecao_personagens (
                fonte_id, slug, nome, nome_original, nome_romanizado,
                imagem_url, descricao, serie, genero, nsfw, popularidade,
                tags, importado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fonte_id) DO UPDATE SET
                slug = excluded.slug,
                nome = excluded.nome,
                nome_original = excluded.nome_original,
                nome_romanizado = excluded.nome_romanizado,
                imagem_url = excluded.imagem_url,
                descricao = excluded.descricao,
                serie = excluded.serie,
                genero = excluded.genero,
                nsfw = excluded.nsfw,
                popularidade = excluded.popularidade,
                tags = excluded.tags,
                importado_em = excluded.importado_em
            """,
            [
                (
                    p["fonte_id"], p["slug"], p["nome"], p.get("nome_original"),
                    p.get("nome_romanizado"), p.get("imagem_url"), p.get("descricao"),
                    p.get("serie"), p["genero"], 1 if p.get("nsfw") else 0,
                    p.get("popularidade", 0), p.get("tags"), agora,
                )
                for p in personagens
            ],
        )


def contar_personagens():
    with conexao() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM colecao_personagens").fetchone()["n"]


def exportar_classificacao_personagens():
    """Snapshot de TODA a classificação já feita (via LLM, `gacha.
    revelar_classe`/`classificar_personagem_colecao`) - `classe`/
    `classe_exibicao`, indexado por `fonte_id` (id estável do catálogo
    externo, sobrevive a uma reimportação inteira, diferente do `id`
    interno). Usado por `scripts/exportar_classificacao_personagens.py`
    pra gerar um backup VERSIONADO no git (2026-09-14, pedido do usuário:
    "n quero ter q redefinir as classes de novo" - `raridade` NÃO entra
    aqui porque é derivada automaticamente por `recalcular_raridade` a
    cada reimportação, nunca precisa de backup)."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT fonte_id, classe, classe_exibicao FROM colecao_personagens "
            "WHERE classe IS NOT NULL ORDER BY fonte_id"
        ).fetchall()
        return [dict(r) for r in linhas]


def aplicar_classificacao_personagens(classificacoes):
    """Reaplica um snapshot de `exportar_classificacao_personagens` -
    usado por `scripts/aplicar_classificacao_personagens.py` num banco
    novo (PC novo, ou banco recriado do zero) depois de reimportar o
    catálogo bruto (`importar_get_waifu.importar`), pra não perder o
    trabalho de classificação. Só grava em quem já existe no banco
    (`fonte_id` desconhecido é ignorado - personagem ainda não
    importada) e só atualiza `classe`/`classe_exibicao`, nunca mexe em
    mais nada da personagem. Devolve quantas linhas foram de fato
    aplicadas (fonte_id encontrado)."""
    agora_aplicadas = 0
    with conexao() as conn:
        for item in classificacoes:
            cursor = conn.execute(
                "UPDATE colecao_personagens SET classe = ?, classe_exibicao = ? WHERE fonte_id = ?",
                (item.get("classe"), item.get("classe_exibicao"), item["fonte_id"]),
            )
            agora_aplicadas += cursor.rowcount
    return agora_aplicadas


def nsfw_permitido(guild_id):
    """Sem configuração salva, o padrão é permitido (`pode incluir o NSFW`,
    decisão do usuário) - cada servidor pode desabilitar depois, sem precisar
    reiniciar o ERIS."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT nsfw_permitido FROM colecao_configuracao_guild WHERE guild_id = ?",
            (str(guild_id),),
        ).fetchone()
    return bool(linha["nsfw_permitido"]) if linha else True


def definir_nsfw_permitido(guild_id, permitido):
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_configuracao_guild (guild_id, nsfw_permitido) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET nsfw_permitido = excluded.nsfw_permitido",
            (str(guild_id), 1 if permitido else 0),
        )


def obter_configuracao_colecao(guild_id):
    """Toda a config ajustável do colecionador NESSE servidor, com fallback
    pros defaults (`_CONFIG_COLECAO_PADRAO`) quando ele nunca configurou
    nada - fonte única lida por `eris/colecao/gacha.py` a cada roll/claim,
    nunca mais uma constante fixa no código (pedido do usuário 2026-08-29)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT * FROM colecao_configuracao_guild WHERE guild_id = ?", (str(guild_id),),
        ).fetchone()
    if linha is None:
        return dict(_CONFIG_COLECAO_PADRAO)
    return {
        "nsfw_permitido": bool(linha["nsfw_permitido"]),
        "rolls_por_ciclo": linha["rolls_por_ciclo"],
        "ciclo_rolls_minutos": linha["ciclo_rolls_minutos"],
        "claims_por_ciclo": linha["claims_por_ciclo"],
        "ciclo_claims_minutos": linha["ciclo_claims_minutos"],
        "duracao_card_segundos": linha["duracao_card_segundos"],
        "max_rolls_por_comando": linha["max_rolls_por_comando"],
        "chance_wish_roll": linha["chance_wish_roll"],
        "teto_bonus_rolls_progressao": linha["teto_bonus_rolls_progressao"],
        "teto_bonus_claims_progressao": linha["teto_bonus_claims_progressao"],
        "canal_anuncio_id": linha["canal_anuncio_id"],
        "cooldown_batalha_ativo": bool(linha["cooldown_batalha_ativo"]),
        "cooldown_batalha_horas": linha["cooldown_batalha_horas"],
        "worldboss_ativo": bool(linha["worldboss_ativo"]),
        "worldboss_horarios": linha["worldboss_horarios"],
        "worldboss_inscricao_minutos": linha["worldboss_inscricao_minutos"],
        "worldboss_turno_segundos": linha["worldboss_turno_segundos"],
        "worldboss_limite_turnos": linha["worldboss_limite_turnos"],
        "worldboss_recompensa_wishards": linha["worldboss_recompensa_wishards"],
        "worldboss_recompensa_xp": linha["worldboss_recompensa_xp"],
        "worldboss_recompensa_soulstone": linha["worldboss_recompensa_soulstone"],
    }


def definir_configuracao_colecao(guild_id, campo, valor):
    """Atualiza UM campo da config do colecionador (`campo` precisa ser uma
    chave de `_CONFIG_COLECAO_PADRAO`) - cria a linha com os demais campos
    no padrão se o servidor nunca tiver configurado nada ainda."""
    if campo not in _CONFIG_COLECAO_PADRAO:
        raise ValueError(f"Campo de configuração desconhecido: {campo!r}")
    with conexao() as conn:
        conn.execute(
            f"INSERT INTO colecao_configuracao_guild (guild_id, {campo}) VALUES (?, ?) "
            f"ON CONFLICT(guild_id) DO UPDATE SET {campo} = excluded.{campo}",
            (str(guild_id), valor),
        )


def estado_sincronizacao_catalogo():
    """Devolve a linha única de `colecao_sincronizacao` (dict) ou `None` se
    o job de sincronização (`eris/colecao/sincronizador.py`) nunca rodou
    ainda nesse banco."""
    with conexao() as conn:
        linha = conn.execute("SELECT * FROM colecao_sincronizacao WHERE id = 1").fetchone()
        return dict(linha) if linha else None


def registrar_tentativa_sincronizacao_catalogo(agora_iso):
    """Marca uma TENTATIVA (sucesso ou não) - usado antes de baixar/importar
    pra já contar como "não devido de novo" mesmo se a tentativa falhar no
    meio (evita bater no GitHub de novo a cada checagem enquanto a rede
    estiver com problema)."""
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_sincronizacao (id, ultima_tentativa_em) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET ultima_tentativa_em = excluded.ultima_tentativa_em",
            (agora_iso,),
        )


def registrar_resultado_sincronizacao_catalogo(agora_iso, sucesso, resultado):
    with conexao() as conn:
        if sucesso:
            conn.execute(
                "UPDATE colecao_sincronizacao SET ultimo_sucesso_em = ?, ultimo_resultado = ? WHERE id = 1",
                (agora_iso, resultado),
            )
        else:
            conn.execute(
                "UPDATE colecao_sincronizacao SET ultimo_resultado = ? WHERE id = 1",
                (resultado,),
            )


def recalcular_raridade():
    """Reatribui o tier de TODO personagem ativo, por percentil de
    popularidade (ver `_CORTES_RARIDADE`) - chamado depois de cada
    (re)importação do catálogo, nunca durante um roll."""
    with conexao() as conn:
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM colecao_personagens WHERE ativo = 1 ORDER BY popularidade ASC"
        ).fetchall()]
        total = len(ids)
        if not total:
            return
        atualizacoes = []
        for indice, personagem_id in enumerate(ids):
            fracao = (indice + 1) / total
            tier = next(t for limite, t in _CORTES_RARIDADE if fracao <= limite)
            atualizacoes.append((tier, personagem_id))
        conn.executemany("UPDATE colecao_personagens SET raridade = ? WHERE id = ?", atualizacoes)


def personagem_por_id(personagem_id):
    with conexao() as conn:
        linha = conn.execute("SELECT * FROM colecao_personagens WHERE id = ?", (personagem_id,)).fetchone()
        return dict(linha) if linha else None


def buscar_personagens(termo, limite=10):
    padrao = f"%{termo.lower()}%"
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT * FROM colecao_personagens WHERE ativo = 1 AND ("
            "LOWER(nome) LIKE ? OR LOWER(nome_romanizado) LIKE ? OR LOWER(nome_original) LIKE ?"
            ") ORDER BY popularidade DESC LIMIT ?",
            (padrao, padrao, padrao, limite),
        ).fetchall()
        return [dict(r) for r in linhas]


def personagens_por_popularidade(limite, permitir_nsfw):
    """Top `limite` do CATÁLOGO INTEIRO por popularidade (likes da fonte
    get_waifu) - pedido do usuário (2026-08-29): "tem comando para listar
    personagens por popularidade?". Cobre o catálogo todo (não só quem já
    apareceu/foi reivindicado num servidor - decisão explícita do usuário),
    com o mesmo filtro de NSFW dos rolls (`/colecao_admin nsfw`)."""
    filtros = ["ativo = 1"]
    if not permitir_nsfw:
        filtros.append("nsfw = 0")
    with conexao() as conn:
        linhas = conn.execute(
            f"SELECT * FROM colecao_personagens WHERE {' AND '.join(filtros)} "
            "ORDER BY popularidade DESC LIMIT ?",
            (limite,),
        ).fetchall()
        return [dict(r) for r in linhas]


def personagens_livres_por_raridade(guild_id, raridade, permitir_nsfw, limite=10):
    """Amostra ALEATÓRIA de personagens SEM DONO nesse servidor, pra
    `/loja ver` - diferente de `candidatos_por_raridade` (pool de ROLL,
    que desde 2026-08-29 inclui personagens já reivindicadas de
    propósito), a loja só pode vender quem está livre (Seção 10). Usada
    quando o jogador não digita nome nenhum (ver `personagens_livres_
    por_raridade_e_nome` pra busca por SUBSTRING)."""
    filtros = ["p.ativo = 1", "p.raridade = ?"]
    params = [raridade]
    if not permitir_nsfw:
        filtros.append("p.nsfw = 0")
    filtros.append("p.id NOT IN (SELECT personagem_id FROM colecao_propriedade WHERE guild_id = ?)")
    params.append(str(guild_id))
    sql = f"SELECT p.* FROM colecao_personagens p WHERE {' AND '.join(filtros)} ORDER BY RANDOM() LIMIT ?"
    params.append(limite)
    with conexao() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def personagens_livres_por_raridade_e_nome(guild_id, raridade, permitir_nsfw, nome, limite=25):
    """Mesma regra de `personagens_livres_por_raridade` (SEM DONO nesse
    servidor) - mas filtrando por SUBSTRING do nome (case-insensitive) em
    vez de amostra ALEATÓRIA (2026-09-03, pedido do usuário: "Coloca para
    o comprar deixar escrever parte do nome tbm, assim como foi na
    serie") - a Loja só mostrava uma amostra aleatória de até 25 livres
    por raridade, impossível de achar uma personagem ESPECÍFICA numa
    raridade com milhares de livres. Ordenado por popularidade DESC
    (mesmo critério de todo dropdown que lista personagem)."""
    filtros = ["p.ativo = 1", "p.raridade = ?", "LOWER(p.nome) LIKE LOWER(?)"]
    params = [raridade, f"%{nome}%"]
    if not permitir_nsfw:
        filtros.append("p.nsfw = 0")
    filtros.append("p.id NOT IN (SELECT personagem_id FROM colecao_propriedade WHERE guild_id = ?)")
    params.append(str(guild_id))
    sql = f"SELECT p.* FROM colecao_personagens p WHERE {' AND '.join(filtros)} ORDER BY p.popularidade DESC LIMIT ?"
    params.append(limite)
    with conexao() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def classes_existentes():
    """Taxonomia de classes já usada no catálogo INTEIRO (não por servidor) -
    passada pra GAIA classificar a próxima personagem reivindicada, pra ela
    reaproveitar uma classe existente em vez de inventar uma quase-sinônima
    toda hora (ver `pandora.gaia_webhook.pedir_classe_personagem`). Lê de
    `colecao_classes` (2026-08-30, fonte única depois do backfill de
    `inicializar()`) - antes lia `DISTINCT classe` direto de `colecao_
    personagens`, o que funcionava igual pra listar nomes, mas não dava
    onde guardar a categoria_combate CANÔNICA de cada uma.

    🔥 Lista COMPLETA, sem teto - usada só pelos scripts de reclassificação
    (auditoria/consolidação de taxonomia). O caminho quente de classificação
    (`gacha.revelar_classe`) usa `classes_mais_populares` (abaixo), não esta -
    ver comentário lá pro porquê."""
    with conexao() as conn:
        linhas = conn.execute("SELECT classe FROM colecao_classes ORDER BY classe").fetchall()
        return [r["classe"] for r in linhas]


def classes_mais_populares(limite=30):
    """Como `classes_existentes`, mas só as `limite` MAIS USADAS (por
    contagem de personagens no catálogo, não por servidor) - 2026-09-03,
    achado do usuário investigando por que o limite DIÁRIO de tokens da
    Groq esgotava rápido: `classes_existentes()` manda a lista INTEIRA (já
    chegou a 45 itens antes de uma consolidação manual) sem nenhum teto de
    tamanho no prompt da GAIA (`pandora.gaia_webhook.pedir_classe_
    personagem` -> `core.agent.turno.classificar_personagem_colecao`) -
    cada classificação nova pagava o custo de token da lista INTEIRA.
    Cortar pras mais populares mantém a maior parte do valor prático de
    reaproveitar classe existente (a distribuição de uso tende a ser bem
    concentrada nas mais comuns) por uma fração do tamanho. Classes fora
    do topo N ainda podem ser reaproveitadas por coincidência (a GAIA pode
    devolver o mesmo nome de novo mesmo sem ver na lista), e duplicatas/
    quase-sinônimos que escaparem disso são corrigíveis depois com os
    mesmos scripts de reclassificação já usados antes (`reclassificar_
    taxonomia_*.py`).

    🔥 "Apoiador" NUNCA aparece aqui (2026-09-06, pedido do usuário: "Apoiador
    deixa de ser uma classe de destino. Nada é reclassificado para
    Apoiador... a meta passa a ser [reduzir], e cada revisão só pode tirar
    personagens dali, nunca colocar novos") - é o balde genérico legado
    (964 membros, congelados), não deveria mais ser sugerido como opção
    "popular" pra nenhuma classificação nova (`db.definir_classe_
    personagem` também recusa a gravação se a GAIA insistir mesmo assim,
    ver lá - dupla proteção)."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT classe, COUNT(*) AS total FROM colecao_personagens "
            "WHERE classe IS NOT NULL AND classe != 'Apoiador' GROUP BY classe ORDER BY total DESC LIMIT ?",
            (limite,),
        ).fetchall()
        return [r["classe"] for r in linhas]


def _normalizar_classe(classe):
    """Forma canônica de comparação (minúsculo, sem acento) - 2026-09-06,
    achado do usuário auditando o Bônus por Classe ("Idol"/"Ídolo" com 23
    e 85 personagens respectivamente, tratadas como classes DIFERENTES;
    "Estrategista"/"Estratégista" fragmentou de novo depois do backfill de
    2026-09-06 que já tinha consolidado o mesmo par). `classe`/`classes_
    mais_populares` sempre comparavam por igualdade EXATA de string - a
    GAIA (`gaia_webhook.pedir_classe_personagem`) não é determinística
    entre acento/maiúscula pro mesmo conceito, então cada variação virava
    uma entrada NOVA em `colecao_classes`, perpetuando a fragmentação pra
    sempre (um backfill manual resolve o passado, mas não impede a
    próxima classificação de reabrir o mesmo buraco)."""
    sem_acento = unicodedata.normalize("NFKD", classe).encode("ascii", "ignore").decode("ascii")
    return sem_acento.strip().lower()


def categoria_combate_da_classe(classe):
    """Categoria de combate CANÔNICA já registrada pra essa classe, ou
    `None` se for uma classe nova (nunca vista antes)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT categoria_combate FROM colecao_classes WHERE classe = ?", (classe,),
        ).fetchone()
    return linha["categoria_combate"] if linha else None


def _classe_canonica_equivalente(conn, classe):
    """Varre `colecao_classes` procurando uma entrada JÁ EXISTENTE que seja
    o mesmo conceito de `classe` ignorando acento/maiúscula (`_normalizar_
    classe`) - usada por `definir_classe_personagem` ANTES de decidir criar
    uma classe nova, pra toda variação (nova ou já vista) convergir pra UMA
    única grafia canônica (a 1ª que existiu), em vez de cada acento
    diferente virar uma entrada própria pra sempre. `None` se `classe` for
    realmente inédita (nenhuma equivalente registrada ainda)."""
    alvo = _normalizar_classe(classe)
    for linha in conn.execute("SELECT classe, categoria_combate, funcao_cidade FROM colecao_classes"):
        if _normalizar_classe(linha["classe"]) == alvo:
            return linha
    return None


def definir_classe_personagem(personagem_id, classe, categoria_combate=None, classe_exibicao=None, funcao_cidade=None):
    """Só grava se ainda não tinha classe (`WHERE classe IS NULL`) - a
    classificação é feita 1 vez só, na 1ª reivindicação em QUALQUER
    servidor, e nunca reescrita depois (mesmo se um roll futuro em outro
    servidor pedisse de novo por engano). `classe_exibicao` (forma
    gramatical concordando com o gênero da personagem - "Ladina" pra uma
    "Ladino" canônica) cai pra `classe` se vier vazia (nunca fica sem
    exibição por causa disso).

    🔥 `categoria_combate` NÃO é mais gravado em `colecao_personagens`
    (2026-08-30, pedido do usuário: "n estamos criando uma tabela de
    classes?", seguido de "vc so criou a tabela ou ta salvando id delas e
    pondo nos personagens?" - achado: a versão anterior desta função só
    tinha adicionado a tabela nova, mas continuava DUPLICANDO a categoria
    em `colecao_personagens`, reabrindo a mesma brecha de inconsistência
    se qualquer outra rota escrevesse ali direto). `colecao_classes` é
    agora a ÚNICA dona desse dado - a classe (`colecao_personagens.
    classe`) funciona como a chave que liga uma personagem à sua entrada
    em `colecao_classes` (natural key, não um `classe_id` numérico - o
    próprio nome da classe já É único por natureza). Devolve a categoria
    de combate REALMENTE em vigor pra essa classe (a canônica, se ela já
    existia - nunca a sugestão nova da GAIA pra esse personagem
    específico) - quem chama (`gacha.revelar_classe`) usa esse retorno em
    vez de tentar ler a coluna antiga.

    🔥 `funcao_cidade` (2026-08-30, Cidade - "n iremos setar personagens
    em funcoes manualmente, sera automatico com base na classe/profissão")
    - 2º campo derivado da CLASSE, MESMO tratamento canônico de
    `categoria_combate` acima (classe conhecida nunca é sobrescrita por
    sugestão nova) - não entra no valor de retorno porque nada no fluxo de
    claim precisa mostrar isso na hora, só a Cidade lê depois via
    `funcao_cidade_da_classe`.

    🔥 Convergência por acento/maiúscula (2026-09-06, `_classe_canonica_
    equivalente`) - ANTES de checar `classe` por igualdade exata, procura
    uma classe já registrada equivalente ignorando acento/maiúscula; se
    achar, `classe` vira a grafia JÁ EXISTENTE (nunca cria uma entrada nova
    pra "Idol" se "Ídolo" já existe) - impede a MESMA fragmentação que já
    precisou de 2 backfills manuais (`Estrategista`/`Estratégista`,
    `Idol`/`Ídolo`) de se repetir pra sempre a cada classificação nova.

    🔥 "Apoiador" aposentado como destino de classificação NOVA (2026-09-06,
    pedido do usuário: "Apoiador deixa de ser uma classe de destino. Nada
    é reclassificado para Apoiador... a meta passa a ser [reduzir], e
    cada revisão só pode tirar personagens dali, nunca colocar novos") -
    se a GAIA insistir em "Apoiador" (mesmo já excluído de `classes_mais_
    populares`, ela pode "coincidir" o nome de novo sem ver na lista, ver
    comentário lá) pra uma personagem NUNCA classificada antes, a
    sugestão é RECUSADA - nada é gravado, a personagem continua com
    `classe IS NULL` (pendente, `/pandora_admin validar_classes` tenta de
    novo depois). Os 964 membros que Apoiador já tinha continuam
    intocados - esta função só roda pra classificação NOVA (`revelar_
    classe` só chama aqui quando `personagem.get("classe")` ainda é
    vazio). Devolve `(recusado: bool, categoria_combate)` - `recusado=
    True` sinaliza que NADA foi gravado, quem chama (`gacha.revelar_
    classe`) trata igual a "GAIA não decidiu nada"."""
    with conexao() as conn:
        canonica = conn.execute(
            "SELECT categoria_combate, funcao_cidade FROM colecao_classes WHERE classe = ?", (classe,),
        ).fetchone()
        if canonica is None:
            canonica = _classe_canonica_equivalente(conn, classe)
            if canonica is not None:
                classe = canonica["classe"]
        if classe == "Apoiador":
            return True, None
        if canonica is not None:
            categoria_combate = canonica["categoria_combate"]
        elif categoria_combate is not None:
            conn.execute(
                "INSERT INTO colecao_classes (classe, categoria_combate, funcao_cidade) VALUES (?, ?, ?) "
                "ON CONFLICT(classe) DO NOTHING",
                (classe, categoria_combate, funcao_cidade),
            )
        conn.execute(
            "UPDATE colecao_personagens SET classe = ?, classe_exibicao = ? WHERE id = ? AND classe IS NULL",
            (classe, classe_exibicao or classe, personagem_id),
        )
    return False, categoria_combate


def personagens_possuidos_sem_classe(limite=20, apenas_falhas=False):
    """Personagens já reivindicadas (por alguém, em QUALQUER servidor) mas
    ainda sem `classe` (2026-09-03, pedido do usuário: "Validar Classes, e
    se todos personagens coletados tem" - achado ao investigar: o Merge
    (`economia.executar_merge`) nunca chamava `gacha.revelar_classe`, então
    uma personagem NUNCA reivindicada antes podia sair do Merge sem classe
    pra sempre - corrigido em `paineis._ViewEscolherMergeAlvo._escolher`,
    mas personagens que já passaram por esse gap antes do fix ficam sem
    classe até alguém rodar isso). `DISTINCT` porque a mesma personagem
    pode ter dono em vários servidores ao mesmo tempo (ownership é por
    guild, classe é global) - contaria repetido sem isso. `limite=None`
    devolve tudo (usado só por `contar_personagens_possuidos_sem_classe`).

    🔥 `apenas_falhas` (2026-09-03, "coloca algo p as q derem erro n
    voltarem p fila, validamos elas depois. Voce so tem q conseguir
    diferenciar elas depois") - por padrão (`False`) a fila PULA quem já
    falhou antes (`classe_falhou = 1`, marcado por
    `marcar_falha_classificacao`), então a fila sempre AVANÇA pra
    personagens nunca tentadas em vez de reprocessar as mesmas primeiras N
    (por `p.id`) toda vez que a GAIA está fora do ar. `apenas_falhas=True`
    inverte o filtro - devolve SÓ quem já falhou antes, pra uma revisão
    manual separada quando for a hora."""
    filtro_falha = "p.classe_falhou = 1" if apenas_falhas else "p.classe_falhou = 0"
    sql = (
        "SELECT DISTINCT p.id, p.nome, p.serie, p.genero, p.descricao "
        "FROM colecao_personagens p "
        "JOIN colecao_propriedade c ON c.personagem_id = p.id "
        f"WHERE p.classe IS NULL AND {filtro_falha} ORDER BY p.id"
    )
    with conexao() as conn:
        if limite is not None:
            linhas = conn.execute(sql + " LIMIT ?", (limite,)).fetchall()
        else:
            linhas = conn.execute(sql).fetchall()
        return [dict(r) for r in linhas]


def contar_personagens_possuidos_sem_classe(apenas_falhas=False):
    filtro_falha = "p.classe_falhou = 1" if apenas_falhas else "p.classe_falhou = 0"
    with conexao() as conn:
        linha = conn.execute(
            "SELECT COUNT(DISTINCT p.id) AS total FROM colecao_personagens p "
            f"JOIN colecao_propriedade c ON c.personagem_id = p.id WHERE p.classe IS NULL AND {filtro_falha}",
        ).fetchone()
    return linha["total"]


_FILTRO_NAO_ADQUIRIDOS_SEM_CLASSE = (
    "FROM colecao_personagens p WHERE p.ativo = 1 AND p.classe IS NULL AND p.classe_falhou = ? AND NOT EXISTS "
    "(SELECT 1 FROM colecao_propriedade c WHERE c.personagem_id = p.id)"
)


def personagens_nao_adquiridos_sem_classe(limite=100, apenas_falhas=False):
    """Fila global do catálogo sem classe e sem qualquer propriedade. Quem
    já falhou (`marcar_falha_classificacao`) sai da fila padrão, igual a
    `personagens_possuidos_sem_classe` (2026-10-14: antes as mesmas
    falhas voltavam no topo de toda rodada)."""
    with conexao() as conn:
        linhas = conn.execute(
            f"SELECT p.id, p.nome, p.serie, p.genero, p.descricao {_FILTRO_NAO_ADQUIRIDOS_SEM_CLASSE} ORDER BY p.id LIMIT ?",
            (1 if apenas_falhas else 0, limite),
        ).fetchall()
    return [dict(r) for r in linhas]


def contar_personagens_nao_adquiridos_sem_classe(apenas_falhas=False):
    with conexao() as conn:
        linha = conn.execute(
            f"SELECT COUNT(*) AS total {_FILTRO_NAO_ADQUIRIDOS_SEM_CLASSE}",
            (1 if apenas_falhas else 0,),
        ).fetchone()
    return linha["total"]


def marcar_falha_classificacao(personagem_id):
    """Tira a personagem da fila PADRÃO de `/pandora_admin validar_classes`
    sem perder o registro dela - só quem chama com `apenas_falhas=True`
    volta a ver essa personagem (revisão manual separada, ver
    `personagens_possuidos_sem_classe`). `AND classe IS NULL` defensivo -
    nunca marca falha em quem já foi classificado por outro caminho
    enquanto essa chamada estava em voo."""
    with conexao() as conn:
        conn.execute(
            "UPDATE colecao_personagens SET classe_falhou = 1 WHERE id = ? AND classe IS NULL",
            (personagem_id,),
        )


def candidatos_por_raridade(guild_id, raridade, generos, permitir_nsfw):
    """IDs elegíveis pra um roll: raridade exata, gênero filtrado, NSFW só se
    o servidor permitir, série não bloqueada nesse servidor. NÃO exclui mais
    quem já tem dono nesse servidor (2026-08-29, ERIS_sistema_colecao_
    wishards.md Seção 4: "personagem já reivindicada continua podendo
    aparecer, pois isso alimenta Afinidade e WiShards") - dono único
    continua valendo (`reivindicar` só deixa UM vencer), mas rolar de novo
    agora é o caminho normal de reencontro/roll de terceiro (ver
    `eris/colecao/gacha.py`)."""
    filtros = ["ativo = 1", "raridade = ?"]
    params = [raridade]
    if generos:
        filtros.append(f"genero IN ({','.join('?' for _ in generos)})")
        params.extend(generos)
    if not permitir_nsfw:
        filtros.append("nsfw = 0")
    filtros.append(
        "(serie IS NULL OR LOWER(serie) NOT IN (SELECT LOWER(serie) FROM colecao_series_bloqueadas WHERE guild_id = ?))"
    )
    params.append(str(guild_id))
    sql = f"SELECT id FROM colecao_personagens WHERE {' AND '.join(filtros)}"
    with conexao() as conn:
        return [r["id"] for r in conn.execute(sql, params).fetchall()]


def reivindicar(guild_id, personagem_id, user_id):
    """Insert atômico - `ON CONFLICT DO NOTHING` garante um único dono por
    (guild, personagem); `rowcount` diz se ESTA chamada venceu a corrida
    (mesmo padrão sugerido no PLANO_COLECAO_WAIFUS.md, Seção 9)."""
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        cursor = conn.execute(
            "INSERT INTO colecao_propriedade (guild_id, personagem_id, dono_id, reivindicado_em) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, personagem_id) DO NOTHING",
            (str(guild_id), personagem_id, str(user_id), agora),
        )
        return cursor.rowcount > 0


def divorciar(guild_id, personagem_id, user_id):
    """Só o dono atual pode divorciar. Paga `valor_base × afinidade` em
    WiShards (ERIS_sistema_colecao_wishards.md, Seção 9) - a Afinidade em si
    é MANTIDA (só remove `colecao_propriedade`), pra um resgate futuro dessa
    MESMA personagem continuar com o vínculo anterior. Devolve
    (ok: bool, recompensa_wishards: int, recompensa_xp: int) - ambos 0 se
    `ok` for False.

    🔥 XP de Progressão (2026-08-30, análise do usuário Seção 5: "o
    Divórcio passa a ter duas recompensas... WiShards + XP de Progressão")
    - SEMPRE uma FRAÇÃO do que foi investido (nível/Afinidade/Soulmate),
    nunca lucro - a fórmula de WiShards acima NÃO mudou (já calibrada),
    o XP é um bônus novo por cima, nunca mexe no que já existia."""
    with conexao() as conn:
        cursor = conn.execute(
            "DELETE FROM colecao_propriedade WHERE guild_id = ? AND personagem_id = ? AND dono_id = ?",
            (str(guild_id), personagem_id, str(user_id)),
        )
        removeu = cursor.rowcount > 0
    if not removeu:
        return False, 0, 0
    personagem = personagem_por_id(personagem_id)
    pontos_afinidade = afinidade(guild_id, user_id, personagem_id)
    recompensa = valor_base_wishards(personagem["raridade"]) * pontos_afinidade
    if recompensa > 0:
        creditar_wishards(guild_id, user_id, recompensa, "divorcio", personagem["nome"], str(personagem_id))
    nivel_atingido = nivel_personagem(guild_id, user_id, personagem_id)
    eh_soulmate = is_soulmate(guild_id, user_id, personagem_id)
    xp = personagem["raridade"] * 10 + nivel_atingido * 15 + (50 if eh_soulmate else pontos_afinidade * 3)
    creditar_xp_progressao(guild_id, user_id, xp, "divorcio", personagem["nome"], str(personagem_id))
    return True, recompensa, xp


def colecao_do_usuario(guild_id, user_id):
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT p.*, c.reivindicado_em, COALESCE(a.afinidade, 1) AS afinidade, "
            "COALESCE(a.is_soulmate, 0) AS is_soulmate "
            "FROM colecao_propriedade c "
            "JOIN colecao_personagens p ON p.id = c.personagem_id "
            "LEFT JOIN colecao_afinidade a "
            "  ON a.guild_id = c.guild_id AND a.user_id = c.dono_id AND a.personagem_id = c.personagem_id "
            "WHERE c.guild_id = ? AND c.dono_id = ? ORDER BY p.raridade DESC, p.nome",
            (str(guild_id), str(user_id)),
        ).fetchall()
        return [dict(r) for r in linhas]


def contar_colecao_do_usuario(guild_id, user_id):
    """Só a CONTAGEM (2026-09-01, achado do usuário: "qnd eu dou claim
    pelos botoes... da GAIA não respondeu a tempo") - `checar_marcos_
    colecao` só precisava de `len(colecao_do_usuario(...))`, mas isso
    materializa a coleção INTEIRA (JOIN com 2 tabelas + um dict por linha)
    só pra jogar fora e contar - ficava rodando em TODO claim (o caminho
    mais quente do jogo), sem `to_thread`, bloqueando o event loop pra
    coleções grandes (usuário já tinha citado "mesmo q tenha mais de
    10k"). `COUNT(*)` puro nunca materializa linha nenhuma."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT COUNT(*) AS total FROM colecao_propriedade WHERE guild_id = ? AND dono_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    return linha["total"]


def colecao_do_usuario_paginada(guild_id, user_id, offset, limite=25):
    """Página da coleção, ordenada por uma aproximação BARATA de CP
    (Nível do vínculo + popularidade do catálogo - ambas colunas SQL
    diretas, sem calcular o CP de verdade de ninguém só pra paginar) -
    2026-09-01, pedido do usuário: "o botão de passar pros lados... deveria
    ser todos os possuídos, mesmo q tenha mais de 10k... não precisa
    carregar tudo, mas pode carregar de 25 em 25". CP EXATO de cada item
    da página é calculado depois, só pra exibir (`torre.power_personagem`),
    nunca pra ordenar a coleção inteira - a ordem aqui é uma aproximação
    (Nível/popularidade correlacionam bem com CP, mas não são o cálculo
    exato) trocada de propósito pela função barata de paginar."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT p.*, c.reivindicado_em, COALESCE(a.afinidade, 1) AS afinidade, "
            "COALESCE(a.is_soulmate, 0) AS is_soulmate "
            "FROM colecao_propriedade c "
            "JOIN colecao_personagens p ON p.id = c.personagem_id "
            "LEFT JOIN colecao_afinidade a "
            "  ON a.guild_id = c.guild_id AND a.user_id = c.dono_id AND a.personagem_id = c.personagem_id "
            "WHERE c.guild_id = ? AND c.dono_id = ? "
            "ORDER BY COALESCE(a.nivel, 1) DESC, p.popularidade DESC "
            "LIMIT ? OFFSET ?",
            (str(guild_id), str(user_id), limite, offset),
        ).fetchall()
    return [dict(r) for r in linhas]


def dono_do_personagem(guild_id, personagem_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT dono_id FROM colecao_propriedade WHERE guild_id = ? AND personagem_id = ?",
            (str(guild_id), personagem_id),
        ).fetchone()
        return linha["dono_id"] if linha else None


# 🔥 Rankings expandidos (2026-09-02, pedido do usuário - Seção 25 do
# plano original: "rankings futuros podem considerar tamanho/valor da
# coleção, Soulmates, séries completas, conquistas e Torre") - só as
# métricas com query BARATA de 1 tabela só, sem N+1 (séries completas/
# conquistas por jogador ficam de fora por enquanto - exigiriam varrer a
# coleção de CADA jogador do servidor, caro pra um ranking do servidor
# inteiro; `estatisticas_series`, abaixo, já cobre completude por série mas
# só das SÉRIES FAVORITADAS de um jogador, nunca em lote pra um servidor
# todo). Todas
# devolvem as mesmas colunas (`dono_id`, `total`) - `consulta.
# formatar_ranking` nunca precisa saber qual métrica está lendo.
_RANKING_QUERIES = {
    "colecao": (
        "SELECT dono_id, COUNT(*) AS total FROM colecao_propriedade "
        "WHERE guild_id = ? GROUP BY dono_id ORDER BY total DESC LIMIT ?"
    ),
    "soulmates": (
        "SELECT user_id AS dono_id, COUNT(*) AS total FROM colecao_afinidade "
        "WHERE guild_id = ? AND is_soulmate = 1 GROUP BY user_id ORDER BY total DESC LIMIT ?"
    ),
    "torre": (
        "SELECT user_id AS dono_id, andar_atual AS total FROM colecao_torre_progresso "
        "WHERE guild_id = ? ORDER BY total DESC LIMIT ?"
    ),
}
RANKINGS_DISPONIVEIS = {"colecao": "📚 Coleção", "soulmates": "💞 Soulmates", "torre": "🗼 Torre"}


def ranking_guild(guild_id, metrica="colecao", limite=10):
    query = _RANKING_QUERIES.get(metrica, _RANKING_QUERIES["colecao"])
    with conexao() as conn:
        linhas = conn.execute(query, (str(guild_id), limite)).fetchall()
        return [dict(r) for r in linhas]


def resumo_perfil_raridade(guild_id, user_id):
    """1 linha por raridade (1-5★) com contagem de nível máximo/afinidade
    máxima/soulmates DENTRO daquela raridade (2026-09-02, redesenho do
    `/perfil` - pedido do usuário: "tabela de progressão por raridade...
    conforme sua coleção chegar a milhares, 310 personagens no nível
    máximo isoladamente começa a dizer pouco" - por isso o percentual
    sempre acompanha a contagem, calculado por quem exibe). 1 query só
    (GROUP BY raridade), nunca materializa a coleção inteira em memória.
    Devolve `[{"raridade", "total", "nivel_maximo", "afinidade_maxima",
    "soulmates"}, ...]` ordenado 1★->5★ - só raridades com pelo menos 1
    personagem possuída aparecem."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT p.raridade AS raridade, COUNT(*) AS total, "
            "SUM(CASE WHEN COALESCE(a.nivel, 1) >= ? THEN 1 ELSE 0 END) AS nivel_maximo, "
            "SUM(CASE WHEN COALESCE(a.afinidade, 1) >= ? THEN 1 ELSE 0 END) AS afinidade_maxima, "
            "SUM(CASE WHEN COALESCE(a.is_soulmate, 0) = 1 THEN 1 ELSE 0 END) AS soulmates "
            "FROM colecao_propriedade c "
            "JOIN colecao_personagens p ON p.id = c.personagem_id "
            "LEFT JOIN colecao_afinidade a "
            "  ON a.guild_id = c.guild_id AND a.user_id = c.dono_id AND a.personagem_id = c.personagem_id "
            "WHERE c.guild_id = ? AND c.dono_id = ? "
            "GROUP BY p.raridade ORDER BY p.raridade",
            (NIVEL_MAXIMO_PERSONAGEM, NIVEL_MAXIMO_AFINIDADE, str(guild_id), str(user_id)),
        ).fetchall()
    return [dict(r) for r in linhas]


def resumo_perfil_geral(guild_id, user_id):
    """Totais do topo do `/perfil` (personagens/nível máximo/afinidade
    máxima/soulmates) - soma direto de `resumo_perfil_raridade` (mesma
    query, sem escanear a coleção de novo)."""
    por_raridade = resumo_perfil_raridade(guild_id, user_id)
    return {
        "total": sum(r["total"] for r in por_raridade),
        "nivel_maximo": sum(r["nivel_maximo"] for r in por_raridade),
        "afinidade_maxima": sum(r["afinidade_maxima"] for r in por_raridade),
        "soulmates": sum(r["soulmates"] for r in por_raridade),
    }


def estatisticas_series(guild_id, user_id, series):
    """Estatísticas de completude por série, só das séries em `series`
    (2026-09-02, usado tanto pelo snapshot de bônus de Série Favorita
    quanto pela exibição delas no `/perfil` - nunca escaneia séries que o
    jogador não favoritou). Devolve `{serie: {"total_catalogo",
    "possuidas", "nivel_maximo", "afinidade_maxima", "soulmates"}}` -
    séries sem NENHUMA personagem possuída ainda aparecem com
    `possuidas=0` (pra mostrar "0/total" em vez de sumir da lista).
    `afinidade_maxima` (2026-09-03, pedido do usuário: "sao 5% de possuir
    tudo, 5% de tudo nivel max, 5% afinidade max, 5% soulbound") - conta
    separada de `nivel_maximo`, mesmo padrão de `resumo_perfil_raridade`."""
    series = [s for s in series if s]
    if not series:
        return {}
    with conexao() as conn:
        marcadores = ",".join("?" * len(series))
        totais = conn.execute(
            f"SELECT serie, COUNT(*) AS total FROM colecao_personagens "
            f"WHERE serie IN ({marcadores}) GROUP BY serie",
            series,
        ).fetchall()
        possuidas = conn.execute(
            f"SELECT p.serie AS serie, COUNT(*) AS possuidas, "
            f"SUM(CASE WHEN COALESCE(a.nivel, 1) >= ? THEN 1 ELSE 0 END) AS nivel_maximo, "
            f"SUM(CASE WHEN COALESCE(a.afinidade, 1) >= ? THEN 1 ELSE 0 END) AS afinidade_maxima, "
            f"SUM(CASE WHEN COALESCE(a.is_soulmate, 0) = 1 THEN 1 ELSE 0 END) AS soulmates "
            f"FROM colecao_propriedade c JOIN colecao_personagens p ON p.id = c.personagem_id "
            f"LEFT JOIN colecao_afinidade a "
            f"  ON a.guild_id = c.guild_id AND a.user_id = c.dono_id AND a.personagem_id = c.personagem_id "
            f"WHERE c.guild_id = ? AND c.dono_id = ? AND p.serie IN ({marcadores}) "
            f"GROUP BY p.serie",
            [NIVEL_MAXIMO_PERSONAGEM, NIVEL_MAXIMO_AFINIDADE, str(guild_id), str(user_id), *series],
        ).fetchall()
    resultado = {
        s: {"total_catalogo": 0, "possuidas": 0, "nivel_maximo": 0, "afinidade_maxima": 0, "soulmates": 0}
        for s in series
    }
    for linha in totais:
        resultado[linha["serie"]]["total_catalogo"] = linha["total"]
    for linha in possuidas:
        resultado[linha["serie"]]["possuidas"] = linha["possuidas"]
        resultado[linha["serie"]]["nivel_maximo"] = linha["nivel_maximo"]
        resultado[linha["serie"]]["afinidade_maxima"] = linha["afinidade_maxima"]
        resultado[linha["serie"]]["soulmates"] = linha["soulmates"]
    return resultado


def encontrar_serie_por_nome(nome):
    """Resolve o nome CANÔNICO (grafia exata do catálogo) por busca
    case-insensitive (2026-09-02, favoritar série - jogador digita de
    cabeça, não copia/cola do catálogo) - devolve `None` se não achar
    nenhuma série com esse nome (nem parecido)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT DISTINCT serie FROM colecao_personagens WHERE serie IS NOT NULL AND LOWER(serie) = LOWER(?) LIMIT 1",
            (nome,),
        ).fetchone()
    return linha["serie"] if linha else None


def series_do_catalogo(prefixo=None, limite=25):
    """Lista de séries distintas do catálogo, opcionalmente filtradas por
    prefixo (case-insensitive) - usado pra sugerir nomes parecidos quando
    o jogador erra a grafia ao favoritar uma série."""
    with conexao() as conn:
        if prefixo:
            linhas = conn.execute(
                "SELECT DISTINCT serie FROM colecao_personagens "
                "WHERE serie IS NOT NULL AND serie != '' AND LOWER(serie) LIKE LOWER(?) "
                "ORDER BY serie LIMIT ?",
                (f"%{prefixo}%", limite),
            ).fetchall()
        else:
            linhas = conn.execute(
                "SELECT DISTINCT serie FROM colecao_personagens WHERE serie IS NOT NULL AND serie != '' ORDER BY serie LIMIT ?",
                (limite,),
            ).fetchall()
    return [r["serie"] for r in linhas]


def personagens_da_serie(guild_id, serie, permitir_nsfw=True):
    """TODOS os personagens ATIVOS do catálogo de uma série - devolve o
    `dono_id` (`None` se livre nesse servidor) junto, pra quem chama saber
    se pode comprar. Usado pelo navegador rápido de Série Favorita
    (2026-09-03, pedido do usuário: "qnd seleciono uma serie, ele abre os
    personagens... soq com um botao de comprar tbm") - ordenado por
    popularidade DESC, mesmo critério de sempre."""
    filtros = ["p.serie = ?", "p.ativo = 1"]
    params = [serie]
    if not permitir_nsfw:
        filtros.append("p.nsfw = 0")
    sql = (
        "SELECT p.*, c.dono_id FROM colecao_personagens p "
        "LEFT JOIN colecao_propriedade c ON c.personagem_id = p.id AND c.guild_id = ? "
        f"WHERE {' AND '.join(filtros)} ORDER BY p.popularidade DESC"
    )
    with conexao() as conn:
        return [dict(r) for r in conn.execute(sql, [str(guild_id)] + params).fetchall()]


def contar_personagens_da_serie(serie, permitir_nsfw=True):
    """Só a CONTAGEM (COUNT(*) puro, barato) de personagens ATIVOS de uma
    série - pro navegador de Série Favorita paginar por POSIÇÃO igual o
    "🔍 Personagem" faz pra coleção (2026-09-03, pedido do usuário: "Faz
    o msm esquemas das personagens, o skip com 25, o dropdown com base na
    posição. E corrige o limite q hj é so 25" - até aqui o navegador
    carregava só os 25 primeiros por popularidade e parava)."""
    filtros = ["serie = ?", "ativo = 1"]
    params = [serie]
    if not permitir_nsfw:
        filtros.append("nsfw = 0")
    sql = f"SELECT COUNT(*) AS total FROM colecao_personagens WHERE {' AND '.join(filtros)}"
    with conexao() as conn:
        return conn.execute(sql, params).fetchone()["total"]


def personagens_da_serie_paginada(guild_id, serie, permitir_nsfw, offset, limite=25):
    """Página (`OFFSET`/`LIMIT`) dos personagens ATIVOS de uma série, com
    `dono_id` - MESMA ordem de `personagens_da_serie` (popularidade DESC,
    crítico: é a ordem que numera a POSIÇÃO usada pelo navegador,
    `contar_personagens_da_serie` tem que contar sobre a mesma base)."""
    filtros = ["p.serie = ?", "p.ativo = 1"]
    params = [serie]
    if not permitir_nsfw:
        filtros.append("p.nsfw = 0")
    sql = (
        "SELECT p.*, c.dono_id FROM colecao_personagens p "
        "LEFT JOIN colecao_propriedade c ON c.personagem_id = p.id AND c.guild_id = ? "
        f"WHERE {' AND '.join(filtros)} ORDER BY p.popularidade DESC LIMIT ? OFFSET ?"
    )
    with conexao() as conn:
        return [dict(r) for r in conn.execute(sql, [str(guild_id)] + params + [limite, offset]).fetchall()]


# --------------------------------------------------------------------------
# Afinidade e WiShards (ERIS_sistema_colecao_wishards.md)
# --------------------------------------------------------------------------

def valor_base_wishards(raridade):
    """20 × estrelas (Seção 3 do plano) - preço-base usado em claim/
    reencontro/roll de terceiro/divórcio."""
    return raridade * 20


def afinidade(guild_id, user_id, personagem_id):
    """0 é só o estado IMPLÍCITO de "nunca foi sua" (sem linha na tabela) -
    nunca confundir com "afinidade zerada de propósito", que não existe
    nessa mecânica (ela só sobe, nunca desce)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT afinidade FROM colecao_afinidade WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        ).fetchone()
    return linha["afinidade"] if linha else 0


def is_soulmate(guild_id, user_id, personagem_id):
    """Status REAL de Soulmate (2026-08-29) - vira True via `tornar_soulmate`
    quando a Afinidade chega no teto (sem RNG). Usado por `gacha._resolver_
    resultado` pra decidir o texto de reencontro (`montar_embed`)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT is_soulmate FROM colecao_afinidade WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        ).fetchone()
    return bool(linha["is_soulmate"]) if linha else False


def definir_afinidade_inicial(guild_id, user_id, personagem_id):
    """Chamado no 1º claim de uma personagem (nunca em reencontro - ver
    `incrementar_afinidade`) - nasce em 1. `DO NOTHING` protege um resgate
    da MESMA personagem depois de um divórcio (a linha antiga já existe,
    com o vínculo anterior preservado - não reseta pra 1)."""
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_afinidade (guild_id, user_id, personagem_id, afinidade) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(guild_id, user_id, personagem_id) DO NOTHING",
            (str(guild_id), str(user_id), personagem_id),
        )


def incrementar_afinidade(guild_id, user_id, personagem_id):
    """Reencontro (o dono rola a própria personagem de novo) - +1 até o teto
    de 10 (Seção 7/8 do plano - Afinidade 10 é Soulmate e para de subir, mas
    continua pagando o máximo). Devolve o novo valor."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT afinidade FROM colecao_afinidade WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        ).fetchone()
        novo = min(10, (linha["afinidade"] if linha else 0) + 1)
        conn.execute(
            "INSERT INTO colecao_afinidade (guild_id, user_id, personagem_id, afinidade) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, personagem_id) DO UPDATE SET afinidade = excluded.afinidade",
            (str(guild_id), str(user_id), personagem_id, novo),
        )
        return novo


def definir_afinidade_admin(guild_id, user_id, personagem_id, valor):
    """Ferramenta de admin (2026-08-29, pedido do usuário: "n existe ninguem
    com afinidade 10, de comando de admin p editar" - testar o teto de
    Afinidade ao vivo sem esperar 9 reencontros de verdade) - ajusta a
    coluna `afinidade` DIRETO, sem passar pelo incremento normal de +1 por
    reencontro (`incrementar_afinidade`). `valor` é travado em 0-10, mesmo
    teto natural da mecânica. Não mexe em `is_soulmate` - só a Afinidade em
    si."""
    valor = max(0, min(10, valor))
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_afinidade (guild_id, user_id, personagem_id, afinidade) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, personagem_id) DO UPDATE SET afinidade = excluded.afinidade",
            (str(guild_id), str(user_id), personagem_id, valor),
        )
    return valor


def nivel_personagem(guild_id, user_id, personagem_id):
    """Nível 1-10 do VÍNCULO do jogador com essa personagem (2026-08-30,
    Torre/`ERIS_power_afinidade_soulmate_niveis.md` Seção 5) - 1 se nunca
    foi upada (default da coluna)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT nivel FROM colecao_afinidade WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        ).fetchone()
    return linha["nivel"] if linha else 1


# 🔥 Custo de nível (2026-08-30) - o documento original (Seção 11) deixava
# isso em aberto ("custo em WiShards de cada nível... se depende da
# raridade"). Escala com raridade E com o nível-alvo (upar do 9 pro 10
# custa mais que do 1 pro 2) - mesma família de "preço escala com
# raridade" de `PRECOS_LOJA`/`PRECOS_GARANTIA`. Um 5⭐ totalmente upado
# (Nv.1->10) custa 6.750 WiShards no total; um 1⭐, 1.350.
CUSTO_NIVEL_POR_PONTO = 25
NIVEL_MAXIMO_PERSONAGEM = 10


def custo_proximo_nivel(raridade, nivel_atual):
    """Custo em WiShards pra subir de `nivel_atual` pro próximo nível -
    `None` se já está no máximo."""
    if nivel_atual >= NIVEL_MAXIMO_PERSONAGEM:
        return None
    nivel_alvo = nivel_atual + 1
    return CUSTO_NIVEL_POR_PONTO * raridade * nivel_alvo


def custo_total_ate_nivel(raridade, nivel_atual, nivel_alvo):
    """Soma o custo de CADA degrau de `nivel_atual` até `nivel_alvo`
    (2026-08-30, pedido do usuário: "o botao de upar nivel... tem de ser
    um dropdown, p permitir pular ate o maximo... vc retorna o custo") -
    0 se `nivel_alvo` não for maior que o atual."""
    if nivel_alvo <= nivel_atual:
        return 0
    return sum(custo_proximo_nivel(raridade, n) for n in range(nivel_atual, nivel_alvo))


@serializar_por_jogador
def subir_nivel_ate(guild_id, user_id, personagem_id, nivel_alvo):
    """Devolve (ok: bool, mensagem: str) - pula DIRETO pro `nivel_alvo`
    (2026-08-30, substitui o antigo "+1 por clique" - dropdown escolhe o
    alvo, custo é a soma de todos os degraus). Exige ser o DONO da
    personagem nesse servidor - mesma checagem de outras ações do Perfil
    (Favoritar/Divorciar/Merge).

    🔥 XP de Progressão (análise do usuário Seção 4) - proporcional ao
    investimento (`custo // 5`), nunca a fonte principal por si só."""
    if str(dono_do_personagem(guild_id, personagem_id)) != str(user_id):
        return False, "Essa personagem não é sua."
    personagem = personagem_por_id(personagem_id)
    if personagem is None:
        return False, "Não achei essa personagem."
    nivel_atual = nivel_personagem(guild_id, user_id, personagem_id)
    if nivel_alvo <= nivel_atual:
        return False, f"{personagem['nome']} já está no Nível {nivel_atual} ou acima."
    if nivel_alvo > NIVEL_MAXIMO_PERSONAGEM:
        return False, f"Nível máximo é {NIVEL_MAXIMO_PERSONAGEM}."
    custo = custo_total_ate_nivel(personagem["raridade"], nivel_atual, nivel_alvo)
    if debitar_wishards(guild_id, user_id, custo, "upgrade_nivel_personagem", personagem["nome"], str(personagem_id)) is None:
        return False, f"Custa {fmt_numero(custo)} WiShards e você não tem o suficiente."
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_afinidade (guild_id, user_id, personagem_id, afinidade, nivel) VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(guild_id, user_id, personagem_id) DO UPDATE SET nivel = excluded.nivel",
            (str(guild_id), str(user_id), personagem_id, nivel_alvo),
        )
    xp = custo // 5
    creditar_xp_progressao(guild_id, user_id, xp, "upar_nivel_personagem", personagem["nome"], str(personagem_id))
    return True, f"{personagem['nome']} subiu pro nível {nivel_alvo}! (custou {fmt_numero(custo)} WiShards, +{fmt_numero(xp)} XP de Progressão)"


NIVEL_MAXIMO_AFINIDADE = 10


def custo_proximo_afinidade(afinidade_atual):
    """Custo em Soulstone pra subir de `afinidade_atual` pro próximo nível
    - `None` se já está no máximo. Custo = o PRÓPRIO nível-alvo (2026-08-30,
    pedido literal do usuário: "do nv1 ao 2 precisa de 2 soulstone, 2 para
    o 3, precisa de 3") - mais barato que Nível de Personagem de propósito,
    Soulstone é mais raro que WiShards."""
    if afinidade_atual >= NIVEL_MAXIMO_AFINIDADE:
        return None
    return afinidade_atual + 1


def custo_total_ate_afinidade(afinidade_atual, afinidade_alvo):
    """Soma o custo de CADA degrau de `afinidade_atual` até `afinidade_
    alvo` (2026-08-30, mesmo dropdown-com-total de `custo_total_ate_
    nivel`) - 0 se `afinidade_alvo` não for maior que a atual."""
    if afinidade_alvo <= afinidade_atual:
        return 0
    return sum(a + 1 for a in range(afinidade_atual, afinidade_alvo))


@serializar_por_jogador
def subir_afinidade_ate(guild_id, user_id, personagem_id, afinidade_alvo):
    """Devolve (ok: bool, mensagem: str) - pula DIRETO pra `afinidade_
    alvo` (2026-08-30, mesmo padrão de `subir_nivel_ate`), gasta SOULSTONE
    em vez de WiShards. NUNCA seta `is_soulmate` (decisão do usuário: "o
    soulmate final so vai ser possivel rodando a pesonagem. N vai ser
    possivel upar com soulstone") - Soulmate continua exclusivo de
    reencontro (`gacha._resolver_resultado`), esta função só empurra
    Afinidade até o teto."""
    if str(dono_do_personagem(guild_id, personagem_id)) != str(user_id):
        return False, "Essa personagem não é sua."
    personagem = personagem_por_id(personagem_id)
    if personagem is None:
        return False, "Não achei essa personagem."
    afinidade_atual = afinidade(guild_id, user_id, personagem_id)
    if afinidade_alvo <= afinidade_atual:
        return False, f"{personagem['nome']} já está na Afinidade {afinidade_atual} ou acima."
    if afinidade_alvo > NIVEL_MAXIMO_AFINIDADE:
        return False, f"Afinidade máxima é {NIVEL_MAXIMO_AFINIDADE}."
    custo = custo_total_ate_afinidade(afinidade_atual, afinidade_alvo)
    if debitar_soulstone(guild_id, user_id, custo, "upgrade_afinidade", personagem["nome"], str(personagem_id)) is None:
        return False, f"Custa {fmt_numero(custo)} Soulstone e você não tem o suficiente."
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_afinidade (guild_id, user_id, personagem_id, afinidade) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, personagem_id) DO UPDATE SET afinidade = excluded.afinidade",
            (str(guild_id), str(user_id), personagem_id, afinidade_alvo),
        )
    return True, f"{personagem['nome']} subiu pra Afinidade {afinidade_alvo}! (custou {fmt_numero(custo)} Soulstone)"


def tornar_soulmate(guild_id, user_id, personagem_id):
    """Marca `is_soulmate = 1` direto - função NOVA e mínima (2026-08-30),
    já desacoplada desde então da antiga "Prova de Soulmate" (removida por
    completo em 2026-09-14, dead code). Chamada só por `gacha._resolver_
    resultado` quando um reencontro acontece numa personagem já em Afinidade
    máxima e ainda não Soulmate - vira Soulmate ali mesmo, sem RNG."""
    with conexao() as conn:
        conn.execute(
            "UPDATE colecao_afinidade SET is_soulmate = 1 WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        )


def saldo_wishards(guild_id, user_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT saldo FROM colecao_wishards_saldo WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    return linha["saldo"] if linha else 0


def _movimentar_saldo(moeda, guild_id, user_id, quantidade, origem, motivo, referencia, exigir_saldo):
    """Saldo + ledger de `moeda` ("wishards"/"soulstone") na MESMA
    transação de escrita (`BEGIN IMMEDIATE` trava o banco ANTES de ler o
    saldo, então duas movimentações simultâneas nunca partem do mesmo
    saldo). Com `exigir_saldo`, não grava nada e devolve None se o saldo
    ficaria negativo. Devolve o novo saldo."""
    agora = datetime.now(timezone.utc).isoformat()
    chave = (str(guild_id), str(user_id))
    with conexao() as conn:
        conn.execute("BEGIN IMMEDIATE")
        linha = conn.execute(
            f"SELECT saldo FROM colecao_{moeda}_saldo WHERE guild_id = ? AND user_id = ?", chave,
        ).fetchone()
        novo_saldo = (linha["saldo"] if linha else 0) + quantidade
        if exigir_saldo and novo_saldo < 0:
            return None
        conn.execute(
            f"INSERT INTO colecao_{moeda}_saldo (guild_id, user_id, saldo) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET saldo = excluded.saldo",
            (*chave, novo_saldo),
        )
        conn.execute(
            f"INSERT INTO colecao_{moeda}_ledger "
            "(guild_id, user_id, quantidade, origem, motivo, referencia, saldo_resultante, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (*chave, quantidade, origem, motivo, referencia, novo_saldo, agora),
        )
        return novo_saldo


def creditar_wishards(guild_id, user_id, quantidade, origem, motivo=None, referencia=None):
    """Ledger + saldo sempre juntos na mesma transação - nunca só um dos
    dois (Seção 6 do plano: "a economia deve usar preferencialmente um
    ledger"). Devolve o novo saldo. Pra GASTO, usar `debitar_wishards`
    (recusa saldo insuficiente); `quantidade` negativa aqui continua aceita
    só por compatibilidade e não confere saldo."""
    return _movimentar_saldo("wishards", guild_id, user_id, quantidade, origem, motivo, referencia, exigir_saldo=False)


def debitar_wishards(guild_id, user_id, custo, origem, motivo=None, referencia=None):
    """Gasta `custo` WiShards se houver saldo: conferir e descontar são 1
    operação só. Devolve o novo saldo, ou None (nada cobrado) se faltar."""
    return _movimentar_saldo("wishards", guild_id, user_id, -custo, origem, motivo, referencia, exigir_saldo=True)


def saldo_soulstone(guild_id, user_id):
    """Item usado só pra upar Afinidade (`subir_afinidade`) - NUNCA
    Soulmate (2026-08-30, ver `subir_afinidade`/`gacha._resolver_
    resultado`). Mesmo padrão saldo+ledger de WiShards acima."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT saldo FROM colecao_soulstone_saldo WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    return linha["saldo"] if linha else 0


def creditar_soulstone(guild_id, user_id, quantidade, origem, motivo=None, referencia=None):
    """Mesmo contrato de `creditar_wishards`."""
    return _movimentar_saldo("soulstone", guild_id, user_id, quantidade, origem, motivo, referencia, exigir_saldo=False)


def debitar_soulstone(guild_id, user_id, custo, origem, motivo=None, referencia=None):
    """Mesmo contrato de `debitar_wishards`."""
    return _movimentar_saldo("soulstone", guild_id, user_id, -custo, origem, motivo, referencia, exigir_saldo=True)


# --------------------------------------------------------------------------
# Progressão Global da conta (2026-08-30, análise trazida pelo usuário -
# "a personagem possui um limite de desenvolvimento. A conta não") -
# resolve o teto que a Torre expôs (Andar 36: Party já quase maximizada
# individualmente, mas o Power exigido continuando a subir). Nível de
# Progressão SEM TETO, alimentado por XP (nunca uma moeda - só enche a
# barra) de praticamente toda interação com a coleção. Vive em `db.py`
# (não um módulo próprio) de propósito - mesmo lugar de `custo_proximo_
# nivel`/`comprar_upgrade_rolls`, que também são "conceitualmente de um
# sistema" mas já moram aqui; `pandora.torre.power_personagem` só CHAMA
# `db.bonus_cp_global` (import de mão única, sem risco de ciclo).
# --------------------------------------------------------------------------

XP_BASE_NIVEL_PROGRESSAO = 150
XP_TAXA_CRESCIMENTO_PROGRESSAO = 1.06
# 🔥 Nível da CONTA dá bônus automático (Seção 9) - fixo por nível +
# percentual a cada N níveis. Números batem com o exemplo concreto da
# análise (Nível de Progressão 20 -> +200 CP fixo, +4%): 10×20=200,
# (20//5)×1=4.
BONUS_FIXO_POR_NIVEL_PROGRESSAO = 10
NIVEIS_PROGRESSAO_POR_PONTO_PERCENTUAL = 5
# 🔥 Upgrades da Loja (Seção 7) - SEM nível máximo, ao contrário de
# upgrade_rolls/upgrade_claims acima (a análise pede isso explicitamente:
# "esses upgrades podem continuar crescendo indefinidamente"). Números
# batem com os 2 exemplos concretos da análise: Treinamento Nv.14->15
# soma +25 (350->375) custando 700 (50×14); Potencial Nv.9->10 soma +2%
# (18%->19%... a análise arredondou, mas +2/nível bate com "9 níveis =
# 18%") custando 1.000 (100×10).
BONUS_FIXO_POR_NIVEL_TREINAMENTO = 25
BONUS_PERCENTUAL_POR_NIVEL_POTENCIAL = 2
# 🔥 Curva virou QUÁRTICA (2026-09-06, achado do usuário auditando a
# própria conta: "estou ja no upgrade 500, e preço ainda esta em 250k,
# sendo q eu produzo ja milhoes por hora" - ~1,67B WiShards/hora medidos
# na Cidade, contra um custo QUADRÁTICO que só cobra 250k/500k no Nv.500 -
# menos de 1 SEGUNDO de renda por nível. A curva quadrática (2026-09-03)
# já tinha sido uma correção da linear original, mas a renda escalou
# ordens de magnitude mais rápido que qualquer correção pontual consegue
# acompanhar - pedido explícito do usuário: "não é correto colocar custo
# baseado em produção, seria injusto [pra quem produz menos]. Acho que
# pode ser um valor fixo. Mas quero que você consiga ir ajustando a
# fórmula até chegarmos num valor ideal, à medida que for analisando os
# logs" (ver `colecao_producao_historico`, novo nesta mesma leva - ainda
# sem histórico suficiente pra calibrar por TENDÊNCIA real, só pelo
# snapshot de hoje).
#
# `custo(n) = FATOR_CUSTO_PROGRESSAO_CONTA × C × n⁴` - calibrado pra
# Treinamento Global custar ~300M no Nv.500 (real do usuário agora, ~11min
# da renda medida) - Potencial da Coleção (C=2) sai o dobro, mesmo
# critério de sempre ("cresce mais rápido de propósito"). Efeito colateral
# ACEITO conscientemente (grau 4 é bem mais agressivo que quadrático) -
# níveis baixos/médios (~50-300) também ficam mais caros que antes, não só
# o topo - não dá pra escalar TANTO no fim sem também subir no meio com
# uma curva de potência só; documentado aqui pra não parecer regressão
# não-intencional numa auditoria futura. Valor de partida, não final - a
# CADA revisão futura (nova conversa de balance, olhando `colecao_
# producao_historico` acumulado), reavaliar `FATOR_CUSTO_PROGRESSAO_CONTA`
# contra a renda/hora real observada NAQUELE momento, do mesmo jeito que
# esta leva usou a renda de hoje.
FATOR_CUSTO_PROGRESSAO_CONTA = 0.0048
CUSTO_TREINAMENTO_GLOBAL_POR_NIVEL = 1
CUSTO_POTENCIAL_COLECAO_POR_NIVEL = 2
# 🔥 Marcos de coleção única (Seção 11 - "não deve ser a principal fonte
# infinita de CP", só milestone pontual). XP = marco × 10 (100
# personagens -> 1.000 XP, 1.000 -> 10.000 XP).
MARCOS_COLECAO = (100, 200, 500, 1000, 2000, 5000, 10000)


def xp_necessario_nivel(nivel, guild_id=None, user_id=None):
    """XP pra sair de nível: seis horas da produção de Cultura atual.

    Sem conta informada mantém a curva antiga apenas para compatibilidade
    com utilitários legados que não têm uma Cidade para consultar.
    """
    if guild_id is not None and user_id is not None:
        from pandora import cidade
        return max(1, round(cidade.taxa_xp_progressao_por_hora(guild_id, user_id) * 6))
    bruto = XP_BASE_NIVEL_PROGRESSAO * (XP_TAXA_CRESCIMENTO_PROGRESSAO ** (nivel - 1))
    return round(bruto / 10) * 10


def progressao_conta(guild_id, user_id):
    """Estado bruto da Progressão da conta - nunca `None`, cai pros
    defaults da coluna (nível 1, 0 XP, upgrades da Loja no nível 0) se a
    linha ainda não existir."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT nivel, xp, nivel_treinamento_global, nivel_potencial_colecao FROM colecao_progressao "
            "WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    if linha is None:
        return {"nivel": 1, "xp": 0, "nivel_treinamento_global": 0, "nivel_potencial_colecao": 0}
    return dict(linha)


def creditar_xp_progressao(guild_id, user_id, quantidade, origem, motivo=None, referencia=None):
    """Credita XP de Progressão (Seção 3/4) - sobe de Nível em CASCATA se
    a quantidade creditada de uma vez ultrapassar mais de 1 limiar (ex.:
    um marco de coleção grande de uma vez). NUNCA é moeda - só preenche a
    barra. Devolve (nivel_novo, xp_novo, subiu_de_nivel: bool).

    🔥 `origem` (2026-09-07, pedido do usuário: "botao de progressao,
    mostrando as fontes de xp acumaladas ate entao") - agora OBRIGATÓRIO
    (mesmo padrão de `creditar_wishards`/`creditar_soulstone`, nunca
    opcional) - grava um ledger próprio (`colecao_xp_progressao_ledger`)
    além do nível/XP em si, pra `xp_por_origem` conseguir montar o
    "📈 Progressão" da Cidade."""
    estado = progressao_conta(guild_id, user_id)
    if quantidade <= 0:
        return estado["nivel"], estado["xp"], False
    nivel, xp = estado["nivel"], estado["xp"] + quantidade
    subiu = False
    while xp >= xp_necessario_nivel(nivel, guild_id, user_id):
        xp -= xp_necessario_nivel(nivel, guild_id, user_id)
        nivel += 1
        subiu = True
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_progressao (guild_id, user_id, nivel, xp) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel = excluded.nivel, xp = excluded.xp",
            (str(guild_id), str(user_id), nivel, xp),
        )
        conn.execute(
            "INSERT INTO colecao_xp_progressao_ledger "
            "(guild_id, user_id, quantidade, origem, motivo, referencia, nivel_resultante, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(guild_id), str(user_id), quantidade, origem, motivo, referencia, nivel, agora),
        )
    return nivel, xp, subiu


def xp_por_origem(guild_id, user_id):
    """{origem: soma_de_xp}, do ledger (`colecao_xp_progressao_ledger`) -
    só cobre XP creditado DEPOIS que o ledger passou a existir (2026-09-07),
    ver comentário da tabela. Usado pelo "📈 Progressão" da Cidade."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT origem, SUM(quantidade) AS soma FROM colecao_xp_progressao_ledger "
            "WHERE guild_id = ? AND user_id = ? GROUP BY origem ORDER BY soma DESC",
            (str(guild_id), str(user_id)),
        ).fetchall()
    return {linha["origem"]: linha["soma"] for linha in linhas}


def bonus_cp_global(guild_id, user_id):
    """(bonus_fixo, bonus_percentual) da Progressão Global - `pandora.
    torre.power_personagem` é o ÚNICO ponto que aplica isso (Seção 8),
    então todo Power calculado no pacote já sai com o bônus embutido sem
    precisar mudar mais nenhum outro lugar. `bonus_percentual` já vem
    pronto pra multiplicar (0,04 = +4%, não "4").

    🔥 `bonus_percentual` só multiplica a BASE, `bonus_fixo` entra como
    soma por cima (2026-09-06, ver comentário completo em `torre.
    power_personagem` - o Potencial da Coleção sem teto tinha virado um
    multiplicador de ×11+ aplicado em cima de TUDO, deixando a base
    natural da personagem em <1% do CP final numa conta real)."""
    estado = progressao_conta(guild_id, user_id)
    bonus_fixo = (
        BONUS_FIXO_POR_NIVEL_PROGRESSAO * estado["nivel"]
        + BONUS_FIXO_POR_NIVEL_TREINAMENTO * estado["nivel_treinamento_global"]
    )
    bonus_percentual = (
        (estado["nivel"] // NIVEIS_PROGRESSAO_POR_PONTO_PERCENTUAL) * 1
        + BONUS_PERCENTUAL_POR_NIVEL_POTENCIAL * estado["nivel_potencial_colecao"]
    ) / 100
    return bonus_fixo, bonus_percentual


# 🔥 Nível de Progressão influenciando MAIS coisas (2026-09-06, pedido do
# usuário: "acho interessante se o Nivel de Progressao da conta tivesse
# mais influencia em tudo, desde custo ate drop e rolls... Nao é p ser
# algo tao quebrado, mas uma leve mudança por level q chega a fazer
# diferença" - escolheu a opção "Tudo" entre custo/drop/odds de raridade
# do roll quando perguntado). Até aqui o Nível só afetava CP (`bonus_cp_
# global` acima) - os 3 bônus abaixo são NOVOS, cada um com teto próprio
# (nunca sem limite - "não quebrado") e granularidade mais larga que o
# bônus de CP (menos generosos de propósito, são 3 sistemas a mais
# empilhando no mesmo Nível, não só mais um).
#
# 1) Desconto de custo (WiShards/Soulstone) - aplicado por enquanto só em
# Treinamento Global/Potencial da Coleção (`custo_total_treinamento_ate`/
# `custo_total_potencial_ate`) - os 2 upgrades que motivaram esta conversa
# inteira de balance. Loja "Comprar"/Upgrade de Rolls/Claims/Investir em
# Massa (Upar Nível/Afinidade) ainda NÃO usam este desconto - ver
# `docs/TODO.md` ("expandir desconto de Nível de Progressão pros outros
# custos") pra não esquecer a expansão.
NIVEIS_POR_PONTO_DESCONTO_CUSTO = 20
DESCONTO_POR_PONTO_NIVEL = 0.005
DESCONTO_MAXIMO_NIVEL = 0.25


def desconto_por_nivel_progressao(nivel):
    """0.05 = 5% de desconto - recebe o NÍVEL já lido (não guild_id/
    user_id) de propósito, pra quem já tem `progressao_conta` em mãos
    (a maioria dos chamadores) não pagar outra consulta ao banco só pra
    ler de novo o mesmo valor."""
    pontos = nivel // NIVEIS_POR_PONTO_DESCONTO_CUSTO
    return min(DESCONTO_MAXIMO_NIVEL, pontos * DESCONTO_POR_PONTO_NIVEL)


# 2) Bônus na chance de drop raro (World Boss) - pequeno, aditivo, teto
# baixo (a Seção 5 já pede "significativamente mais raros que as
# recompensas básicas" pro drop raro - não é o lugar de dar um empurrão
# grande).
NIVEIS_POR_PONTO_BONUS_DROP = 25
BONUS_DROP_POR_PONTO_NIVEL = 0.002
BONUS_DROP_MAXIMO_NIVEL = 0.05


def bonus_drop_raro_por_nivel(nivel):
    """+0.02 = +2 pontos percentuais na chance de drop raro (`itens.
    CHANCE_DROP_RARO`, base 15%) - mesmo motivo acima, recebe `nivel` já
    lido."""
    pontos = nivel // NIVEIS_POR_PONTO_BONUS_DROP
    return min(BONUS_DROP_MAXIMO_NIVEL, pontos * BONUS_DROP_POR_PONTO_NIVEL)


# 3) Odds de raridade do roll - o sistema MAIS sensível dos 3 (rege toda a
# economia de personagens), por isso o mais conservador: desloca uma
# fração pequena do peso do tier 1 (mais comum) pra 4⭐/5⭐, proporcional
# ao peso ATUAL deles (preserva a proporção 4:1 entre eles, só aumenta os
# 2 juntos) - a SOMA dos pesos nunca muda, então `random.choices` nem
# precisa normalizar diferente.
NIVEIS_POR_PONTO_RARIDADE = 40
TETO_PONTOS_RARIDADE_NIVEL = 10


def pontos_bonus_raridade_por_nivel(nivel):
    """Quantos pontos de peso mover do tier 1 pro 4⭐/5⭐ (ver `gacha.
    _PESOS_RARIDADE`, soma 100) - no teto (Nível >= 400), desloca 10 dos
    50 pontos do tier 1 (20% dele) - ~3x mais chance de 5⭐, ~3x mais
    chance de 4⭐, tier 1/2/3 continuam na MESMA proporção entre si."""
    return min(TETO_PONTOS_RARIDADE_NIVEL, nivel // NIVEIS_POR_PONTO_RARIDADE)


# 🔥 Bônus por CLASSE (2026-08-30, pedido do usuário: "a cada 50
# personagens da classe ganho +500 bonus p todos daquela classe na
# torre" - depois revisado pro mesmo RATIO com granularidade menor: "a cd
# 5 aumenta 50", 50/5 = 10 CP por personagem no marco, igual 500/50) -
# incentiva colecionar VÁRIAS da MESMA classe (taxonomia ABERTA, não a
# categoria/função fechada) - toda personagem daquela classe ganha o
# bônus, não só as que estão na Party/Torre.
#
# 🔥 Marco por CATEGORIA (2026-09-06, achado do usuário: Tank era ~11x
# mais raro que Support) e depois REVERTIDO no mesmo dia (Guerreiro/
# Dragão/Lutador viraram Tank, deixou de ser raro) - histórico completo
# no CHANGELOG, removido daqui porque a raiz quadrada abaixo tornou o
# conceito de "marco por categoria" obsoleto (a curva já se auto-ajusta
# pra qualquer tamanho de classe, sem precisar de exceção manual).
#
# 🔥 Linear -> RAIZ QUADRADA -> FAIXAS CUMULATIVAS (2026-09-06, achado do
# usuário: "Kokoro, classe Apoiador (~960 possuídas)" empatava com uma
# waifu MAXADA de "Mago" (~400 possuídas) só pela diferença de população
# entre as 2 classes - `(quantidade // 5) × 50` sem teto dava +9.600 pra
# Apoiador contra +4.000 pra Mago, diferença MAIOR que o próprio teto de
# investimento numa personagem (Fortalecimento vai só até 1000 de Power
# Base). A raiz quadrada resolveu o exploit mas o usuário achou o
# resultado pouco "desenhado" - pediu algo mais explícito e ajustável:
# "Quero alterar o bônus dos marcos de classe para ter retorno
# decrescente conforme a classe cresce... A progressão deve ser
# cumulativa por faixa" - cada marco de 5 vale um CP diferente dependendo
# de EM QUE FAIXA de quantidade ele foi conquistado (1-100 = +5/marco,
# 101-250 = +4, 251-500 = +3, 501-1000 = +2, 1000+ = +1) - "ao entrar em
# uma nova faixa, os marcos anteriores mantêm o valor que tinham quando
# foram conquistados" (nunca retroage, só os marcos NOVOS entram mais
# baratos). Exemplo do próprio usuário validado: 300 personagens = 20
# marcos×5 (até 100) + 30 marcos×4 (101-250) + 10 marcos×3 (251-300) =
# 100+120+30 = 250 CP.
MARCO_QUANTIDADE_CLASSE_PADRAO = 5
# (limite superior da faixa - quantidade de personagens, CP por marco DENTRO dela)
FAIXAS_BONUS_CLASSE = (
    (100, 5),
    (250, 4),
    (500, 3),
    (1000, 2),
    (None, 1),  # sem teto - último item, `None` = "resto, sem limite"
)


def _marco_atual_classe(quantidade):
    """Maior múltiplo de `MARCO_QUANTIDADE_CLASSE_PADRAO` (5) que
    `quantidade` já cobre - 0 se ainda não bateu o 1º marco."""
    return (quantidade // MARCO_QUANTIDADE_CLASSE_PADRAO) * MARCO_QUANTIDADE_CLASSE_PADRAO


def pontos_por_marco(quantidade, passo=MARCO_QUANTIDADE_CLASSE_PADRAO):
    """Pontos acumulados pelos marcos de `passo` em `passo` já batidos por
    `quantidade`, com retorno decrescente por FAIXA (`FAIXAS_BONUS_CLASSE`
    - cada marco vale os pontos da faixa em que ele caiu, nunca
    recalculado pra trás quando a quantidade total avança de faixa).
    Função GENÉRICA (2026-09-06, "vamos começar a usar marcos na cidade
    tbm p dar esses buffs") - originalmente só pro Bônus por Classe
    (`quantidade` = personagens da mesma classe possuídas), reaproveitada
    também pelos bônus da Cidade (`pandora.cidade` - `quantidade` =
    trabalhadores numa área, ou personagens da coleção inteira pro Bônus
    da Coleção) - cada contexto multiplica os "pontos" devolvidos aqui
    pelo seu PRÓPRIO valor-por-ponto (CP fixo, % percentual, etc.), sem
    duplicar a lógica de faixas."""
    marco_atual = (quantidade // passo) * passo
    if marco_atual <= 0:
        return 0
    total = 0
    piso_faixa = 0
    for teto_faixa, pontos_por_marco_faixa in FAIXAS_BONUS_CLASSE:
        limite = marco_atual if teto_faixa is None else min(marco_atual, teto_faixa)
        if limite <= piso_faixa:
            break
        total += ((limite - piso_faixa) // passo) * pontos_por_marco_faixa
        if teto_faixa is None or marco_atual <= teto_faixa:
            break
        piso_faixa = teto_faixa
    return total


def _bonus_por_quantidade_classe(quantidade):
    """CP fixo que uma classe com `quantidade` personagens possuídas dá
    (Bônus por Classe) - 1 CP por ponto (`pontos_por_marco`), ver
    comentário lá pro raciocínio completo e o exemplo validado."""
    return pontos_por_marco(quantidade)


def nivel_em_lote(guild_id, user_id):
    """{personagem_id: nivel} de TODO o vínculo, numa query só (2026-08-30,
    achado do usuário: "auto-party atualiza a pt logicamente mas n troca
    visualmente, da erro de GAIA não respondeu a tempo") - `torre.
    power_personagem`/`ordenar_por_power` chamavam `nivel_personagem` (+
    `bonus_cp_global`/`bonus_cp_classe`) UMA VEZ POR PERSONAGEM ao varrer a
    coleção inteira (Auto-Party, dropdowns de Favoritar/Divorciar/Merge/
    Trocar) - cada chamada abre uma conexão SQLite NOVA (`conexao()` não
    faz pool), então uma coleção de ~400 virava 1000+ conexões abertas num
    clique só, estourando o teto de 3s do Discord pra responder a
    interação (a escrita no banco já tinha terminado por baixo, só a
    resposta visual que não chegava a tempo). Personagem sem linha em
    `colecao_afinidade` ainda = Nível 1 (mesmo default de `nivel_
    personagem`), decidido por quem lê o dict (`.get(id, 1)`)."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT personagem_id, nivel FROM colecao_afinidade WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchall()
    return {linha["personagem_id"]: linha["nivel"] for linha in linhas}


def info_classes_em_lote(guild_id, user_id):
    """{classe: (bonus_cp_classe, categoria_combate, funcao_cidade)} de
    TODA classe que o jogador possui NESSE servidor, numa query só
    (2026-09-01, achado do usuário: "Quando fui upar level apenas de 1
    personagem para o maximo, gaia nao respondeu a tempo") - `torre.
    power_personagem` já cacheava `bonus_cp_classe`/`categoria_combate_
    da_classe` DURANTE o loop (2 por classe NOVA encontrada), mas isso
    ainda abria 1 conexão SQLite por classe distinta (`quantidade_
    possuida_da_classe`/`categoria_combate_da_classe`, `conexao()` não
    faz pool) - pra uma coleção com muitas classes diferentes, isso
    sozinho já dominava o tempo de `cidade._workforce_por_funcao` (2,7s
    pra ~1.100 personagens/49 classes, quase tudo em conexões repetidas).
    `funcao_cidade` (2026-09-01, mesmo achado) - `cidade._workforce_por_
    funcao` chamava `db.funcao_cidade_da_classe` por PERSONAGEM (não só
    por classe), pior ainda que os outros 2; incluído aqui pra também
    virar cache em vez de 1 conexão por personagem. Esta função pré-
    calcula TUDO numa única query (`GROUP BY` + `JOIN` com `colecao_
    classes`), preenchendo o cache de `torre._contexto_lote` de uma vez -
    zero conexão extra por classe/personagem depois disso."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT p.classe AS classe, cc.categoria_combate AS categoria_combate, "
            "cc.funcao_cidade AS funcao_cidade, COUNT(*) AS quantidade "
            "FROM colecao_propriedade c "
            "JOIN colecao_personagens p ON p.id = c.personagem_id "
            "LEFT JOIN colecao_classes cc ON cc.classe = p.classe "
            "WHERE c.guild_id = ? AND c.dono_id = ? AND p.classe IS NOT NULL "
            "GROUP BY p.classe",
            (str(guild_id), str(user_id)),
        ).fetchall()
    return {
        linha["classe"]: (
            _bonus_por_quantidade_classe(linha["quantidade"]),
            linha["categoria_combate"],
            linha["funcao_cidade"],
        )
        for linha in linhas
    }


def quantidade_possuida_da_classe(guild_id, user_id, classe):
    """Quantas personagens DESSA classe (taxonomia aberta) o jogador
    possui NESSE servidor - base do bônus por classe."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT COUNT(*) AS n FROM colecao_propriedade c JOIN colecao_personagens p ON p.id = c.personagem_id "
            "WHERE c.guild_id = ? AND c.dono_id = ? AND p.classe = ?",
            (str(guild_id), str(user_id), classe),
        ).fetchone()
    return linha["n"] if linha else 0


def bonus_cp_classe(guild_id, user_id, classe):
    """CP fixo que TODA personagem dessa classe ganha (2026-08-30) -
    `pandora.torre.power_personagem` aplica isso junto do bônus global de
    Progressão. `None`/sem classe revelada ainda = sem bônus."""
    if not classe:
        return 0
    quantidade = quantidade_possuida_da_classe(guild_id, user_id, classe)
    return _bonus_por_quantidade_classe(quantidade)


def bonus_classes_por_categoria(guild_id, user_id):
    """Detalhe do bônus por classe agrupado por categoria de combate
    (2026-09-02, pedido do usuário: "uma nova tela q mostrasse q DPS ta
    ganhando +X Tank +Y... e n sei se separou por classe tbm") - devolve
    {categoria: {"total_bonus": int, "total_personagens": int, "classes":
    [{"classe", "quantidade", "bonus", "ganho_proximo_marco"}, ...]}}, só
    com classes que o jogador possui NESSE servidor (classe sem
    `categoria_combate` cadastrada em `colecao_classes` cai em "Sem
    categoria"). `total_bonus` é a SOMA do bônus de cada classe da
    categoria (não multiplicado pela quantidade de cada uma) - decisão
    explícita do usuário depois de eu explicar que não existe um "+X do
    DPS" físico de verdade (cada personagem só ganha o bônus da PRÓPRIA
    classe, nunca o das outras classes da mesma categoria) - o número é
    só a soma dos bônus vigentes agrupados, não um valor que se aplica a
    cada unidade.

    🔥 `ganho_proximo_marco` substitui `proximo_marco` (2026-09-06,
    achado do usuário: "esse p proximo marco ficou sem necessidade,
    podia informar qnt vai aumentar no proximo marco" - mostrar a
    QUANTIDADE do próximo marco (ex.: "453/455") não dizia nada sobre o
    IMPACTO real, ainda mais agora que cada marco vale um CP diferente
    conforme a faixa (`FAIXAS_BONUS_CLASSE`) - o número que interessa é
    quanto CP a MAIS o próximo marco concede, não em que quantidade ele
    acontece."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT p.classe AS classe, cc.categoria_combate AS categoria_combate, COUNT(*) AS quantidade "
            "FROM colecao_propriedade c "
            "JOIN colecao_personagens p ON p.id = c.personagem_id "
            "LEFT JOIN colecao_classes cc ON cc.classe = p.classe "
            "WHERE c.guild_id = ? AND c.dono_id = ? AND p.classe IS NOT NULL "
            "GROUP BY p.classe",
            (str(guild_id), str(user_id)),
        ).fetchall()
    categorias = {}
    for linha in linhas:
        categoria = linha["categoria_combate"] or "Sem categoria"
        quantidade = linha["quantidade"]
        bonus = _bonus_por_quantidade_classe(quantidade)
        proximo_marco = _marco_atual_classe(quantidade) + MARCO_QUANTIDADE_CLASSE_PADRAO
        ganho_proximo_marco = _bonus_por_quantidade_classe(proximo_marco) - bonus
        entrada = categorias.setdefault(categoria, {"total_bonus": 0, "total_personagens": 0, "classes": []})
        entrada["total_bonus"] += bonus
        entrada["total_personagens"] += quantidade
        entrada["classes"].append(
            {"classe": linha["classe"], "quantidade": quantidade, "bonus": bonus, "ganho_proximo_marco": ganho_proximo_marco}
        )
    for entrada in categorias.values():
        entrada["classes"].sort(key=lambda c: c["bonus"], reverse=True)
    return categorias


def custo_treinamento_global(nivel_alvo):
    return round(CUSTO_TREINAMENTO_GLOBAL_POR_NIVEL * FATOR_CUSTO_PROGRESSAO_CONTA * nivel_alvo ** 4)


def custo_total_treinamento_ate(nivel_atual, nivel_alvo, desconto=0.0):
    """Soma o custo de CADA nível de `nivel_atual` até `nivel_alvo`
    (2026-08-30, pedido do usuário: "na loja, qnd vou fazer treinamento
    global... tbm tem de permitr comprar varios leveis por vez" - mesmo
    padrão de `custo_total_ate_nivel`) - 0 se `nivel_alvo` não for maior
    que o atual. `desconto` (2026-09-06, `desconto_por_nivel_progressao`)
    - 0.0 = sem desconto, mesmo comportamento de sempre."""
    if nivel_alvo <= nivel_atual:
        return 0
    bruto = sum(custo_treinamento_global(n) for n in range(nivel_atual + 1, nivel_alvo + 1))
    return round(bruto * (1 - desconto))


@serializar_por_jogador
def comprar_treinamento_global_ate(guild_id, user_id, nivel_alvo):
    """+CP FIXO por personagem, pra sempre, SEM nível máximo (Seção 7) -
    pula DIRETO pro `nivel_alvo` (2026-08-30, substitui o antigo "+1 por
    clique" - dropdown escolhe o alvo, custo é a soma de todos os
    degraus, mesmo padrão de `subir_nivel_ate`)."""
    estado = progressao_conta(guild_id, user_id)
    nivel_atual = estado["nivel_treinamento_global"]
    if nivel_alvo <= nivel_atual:
        return False, f"Treinamento da Coleção já está no Nível {nivel_atual} ou acima."
    desconto = desconto_por_nivel_progressao(estado["nivel"])
    custo = custo_total_treinamento_ate(nivel_atual, nivel_alvo, desconto)
    if debitar_wishards(guild_id, user_id, custo, "treinamento_global", f"nível {nivel_atual}->{nivel_alvo}") is None:
        return False, f"Custa {fmt_numero(custo)} WiShards e você não tem o suficiente."
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_progressao (guild_id, user_id, nivel_treinamento_global) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel_treinamento_global = excluded.nivel_treinamento_global",
            (str(guild_id), str(user_id), nivel_alvo),
        )
    bonus_total = nivel_alvo * BONUS_FIXO_POR_NIVEL_TREINAMENTO
    return True, f"Treinamento da Coleção Nv.{nivel_alvo}! +{fmt_numero(bonus_total)} CP fixo por personagem, pra sempre (custou {fmt_numero(custo)} WiShards)."


def custo_potencial_colecao(nivel_alvo):
    return round(CUSTO_POTENCIAL_COLECAO_POR_NIVEL * FATOR_CUSTO_PROGRESSAO_CONTA * nivel_alvo ** 4)


def custo_total_potencial_ate(nivel_atual, nivel_alvo, desconto=0.0):
    """Soma o custo de CADA nível de `nivel_atual` até `nivel_alvo` (mesmo
    padrão de `custo_total_treinamento_ate`) - 0 se `nivel_alvo` não for
    maior que o atual. `desconto` - ver `custo_total_treinamento_ate`."""
    if nivel_alvo <= nivel_atual:
        return 0
    bruto = sum(custo_potencial_colecao(n) for n in range(nivel_atual + 1, nivel_alvo + 1))
    return round(bruto * (1 - desconto))


@serializar_por_jogador
def comprar_potencial_colecao_ate(guild_id, user_id, nivel_alvo):
    """+CP PERCENTUAL global, pra sempre, SEM nível máximo (Seção 7) -
    custo cresce mais rápido que o Treinamento Global de propósito ("a
    eficiência cresce junto com o CP total"). Pula DIRETO pro `nivel_alvo`
    (2026-08-30, mesmo padrão de `comprar_treinamento_global_ate`)."""
    estado = progressao_conta(guild_id, user_id)
    nivel_atual = estado["nivel_potencial_colecao"]
    if nivel_alvo <= nivel_atual:
        return False, f"Maestria da Coleção já está no Nível {nivel_atual} ou acima."
    desconto = desconto_por_nivel_progressao(estado["nivel"])
    custo = custo_total_potencial_ate(nivel_atual, nivel_alvo, desconto)
    if debitar_wishards(guild_id, user_id, custo, "potencial_colecao", f"nível {nivel_atual}->{nivel_alvo}") is None:
        return False, f"Custa {fmt_numero(custo)} WiShards e você não tem o suficiente."
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_progressao (guild_id, user_id, nivel_potencial_colecao) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel_potencial_colecao = excluded.nivel_potencial_colecao",
            (str(guild_id), str(user_id), nivel_alvo),
        )
    bonus_total = nivel_alvo * BONUS_PERCENTUAL_POR_NIVEL_POTENCIAL
    return True, f"Maestria da Coleção Nv.{nivel_alvo}! +{bonus_total}% CP global, pra sempre (custou {fmt_numero(custo)} WiShards)."


def maior_marco_colecao_atingido(guild_id, user_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT maior_marco FROM colecao_progressao_marcos WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    return linha["maior_marco"] if linha else 0


def checar_marcos_colecao(guild_id, user_id):
    """Credita XP de todo marco (100/200/500...) que a coleção do jogador
    já cruzou e ainda não tinha sido pago - devolve a lista de marcos
    novos pagos AGORA (vazia se nenhum). Chamado a cada claim bem-
    sucedido (`gacha.py`) - `maior_marco` guardado garante que nunca paga
    2x o mesmo marco, mesmo se a coleção oscilar perto dele (Merge reduz
    contagem, por exemplo).

    🔥 `contar_colecao_do_usuario` (2026-09-01) em vez de `len(colecao_do_
    usuario(...))` - só precisa do NÚMERO, nunca materializar a coleção
    inteira (JOIN + 1 dict por linha) só pra jogar fora e contar; isso
    rodava em TODO claim (via `gacha._processar_claim`, sem `to_thread`),
    achado do usuário: "qnd eu dou claim pelos botoes... da GAIA não
    respondeu a tempo" - claim por BOTÃO tem prazo de 3s pra responder
    (claim por REAÇÃO não, daí só aparecer nesse caminho)."""
    total = contar_colecao_do_usuario(guild_id, user_id)
    ja_pago = maior_marco_colecao_atingido(guild_id, user_id)
    novos = [m for m in MARCOS_COLECAO if ja_pago < m <= total]
    if not novos:
        return []
    for marco in novos:
        creditar_xp_progressao(guild_id, user_id, marco * 10, "marco_colecao", f"{marco} personagens únicas", str(marco))
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_progressao_marcos (guild_id, user_id, maior_marco) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET maior_marco = excluded.maior_marco",
            (str(guild_id), str(user_id), max(novos)),
        )
    return novos


def cidade_ultima_producao(guild_id, user_id):
    """`None` se a Cidade nunca foi visitada ainda (`pandora.cidade.
    coletar_producao_pendente` decide o que fazer nesse caso - não credita
    nada na 1ª visita, só marca o relógio pra começar a contar)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT ultima_producao_em FROM colecao_cidade_estado WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    if linha is None or linha["ultima_producao_em"] is None:
        return None
    return datetime.fromisoformat(linha["ultima_producao_em"])


def definir_cidade_ultima_producao(
    guild_id, user_id, momento, cp_bonus_militar_fixo=0.0, cp_bonus_arcano_percentual=0.0, bonus_colecao_loot_percentual=0.0,
):
    """Grava o relógio da Cidade JUNTO com o snapshot de bônus de CP pra
    Party (2026-08-30, Cidade v2 - efeitos diferenciados por área) - os 2
    sempre mudam juntos (mesma visita ao painel "🏙️ Cidade",
    `pandora.cidade.coletar_producao_pendente`), nunca precisam de 2
    `UPDATE`s separados na mesma linha."""
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_cidade_estado ("
            "guild_id, user_id, ultima_producao_em, cp_bonus_militar_fixo, cp_bonus_arcano_percentual, bonus_colecao_loot_percentual"
            ") VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
            "ultima_producao_em = excluded.ultima_producao_em, "
            "cp_bonus_militar_fixo = excluded.cp_bonus_militar_fixo, "
            "cp_bonus_arcano_percentual = excluded.cp_bonus_arcano_percentual, "
            "bonus_colecao_loot_percentual = excluded.bonus_colecao_loot_percentual",
            (
                str(guild_id), str(user_id), momento.isoformat(),
                cp_bonus_militar_fixo, cp_bonus_arcano_percentual, bonus_colecao_loot_percentual,
            ),
        )


# 🔥 Intervalo mínimo entre 2 pontos de histórico (2026-09-06, pedido do
# usuário: "seria ate bom manter uns logs disso") - registrar em TODA
# visita ao painel "🏙️ Cidade" cresceria sem teto pra jogador que fica
# abrindo o painel repetidamente, sem ganhar granularidade nenhuma (a taxa
# por hora só muda quando a coleção/construção muda, não a cada clique).
# 6h dá pontos suficientes pra ver TENDÊNCIA dia a dia sem virar ruído.
INTERVALO_MINIMO_PRODUCAO_HISTORICO_HORAS = 6


def registrar_producao_historico(guild_id, user_id, wishards_por_hora, soulstone_por_hora, xp_por_hora, cp_total, nivel_progressao):
    """Snapshot de "quanto este jogador produz por hora agora" (2026-09-06,
    pedido do usuário: "meu farm ta sempre aumentando, seria ate bom
    manter uns logs disso p vc ter controle e dar sugestoes no futuro, e
    tentar prever as proximas producoes" - qualquer decisão de preço/
    balance baseada num ÚNICO número (o de hoje) fica velha assim que a
    produção sobe de novo; isto aqui acumula pontos ao longo do tempo pra
    uma futura conversa de balance comparar contra dado REAL de
    crescimento, em vez de mais um chute). Chamado de `pandora.cidade.
    coletar_producao_pendente` a cada visita à Cidade, mas só GRAVA um
    ponto novo se o último já tiver pelo menos `INTERVALO_MINIMO_
    PRODUCAO_HISTORICO_HORAS` de idade (ou não existir nenhum ainda) -
    sem isso o histórico cresceria 1 linha por clique, sem ganhar
    granularidade nenhuma (a taxa não muda entre 2 cliques segundos
    depois um do outro)."""
    agora = datetime.now(timezone.utc)
    with conexao() as conn:
        ultimo = conn.execute(
            "SELECT registrado_em FROM colecao_producao_historico WHERE guild_id = ? AND user_id = ? "
            "ORDER BY registrado_em DESC LIMIT 1",
            (str(guild_id), str(user_id)),
        ).fetchone()
        if ultimo is not None:
            idade_horas = (agora - datetime.fromisoformat(ultimo["registrado_em"])).total_seconds() / 3600
            if idade_horas < INTERVALO_MINIMO_PRODUCAO_HISTORICO_HORAS:
                return
        conn.execute(
            "INSERT INTO colecao_producao_historico "
            "(guild_id, user_id, registrado_em, wishards_por_hora, soulstone_por_hora, xp_por_hora, cp_total, nivel_progressao) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(guild_id), str(user_id), agora.isoformat(), wishards_por_hora, soulstone_por_hora, xp_por_hora, cp_total, nivel_progressao),
        )


def producao_historico(guild_id, user_id, limite=60):
    """Snapshots mais RECENTES primeiro (`registrado_em` desc) - usada pra
    olhar tendência de crescimento (ex.: "quanto o farm deste jogador
    cresceu nos últimos N dias") numa conversa de balance futura, em vez
    de decidir preço/custo olhando só o momento atual."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT registrado_em, wishards_por_hora, soulstone_por_hora, xp_por_hora, cp_total, nivel_progressao "
            "FROM colecao_producao_historico WHERE guild_id = ? AND user_id = ? "
            "ORDER BY registrado_em DESC LIMIT ?",
            (str(guild_id), str(user_id), limite),
        ).fetchall()
    return [dict(r) for r in linhas]


def cidade_bonus_party(guild_id, user_id):
    """(bonus_militar_fixo, bonus_arcano_percentual) -
    snapshot já calculado (Administração já multiplicada dentro dos 2
    primeiros) - `pandora.torre.calcular_power_party` só LÊ isso, nunca
    recalcula a partir da coleção inteira (ver `pandora.cidade`).
    (0.0, 0.0, 0.0) se a Cidade nunca foi visitada ainda."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT cp_bonus_militar_fixo, cp_bonus_arcano_percentual "
            "FROM colecao_cidade_estado WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    if linha is None:
        return 0.0, 0.0
    return linha["cp_bonus_militar_fixo"], linha["cp_bonus_arcano_percentual"]


def bonus_loot_colecao(guild_id, user_id):
    """Fração extra de loot no snapshot da Cidade; 0 se nunca visitada."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT bonus_colecao_loot_percentual FROM colecao_cidade_estado WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    return linha["bonus_colecao_loot_percentual"] if linha else 0.0


def funcao_cidade_da_classe(classe):
    """Função da Cidade CANÔNICA já registrada pra essa classe, ou `None`
    se a personagem nunca foi classificada OU se a classe ainda não tem
    função definida (pendente de backfill). Mesmo padrão de
    `categoria_combate_da_classe` - 2º campo derivado da mesma tabela."""
    if classe is None:
        return None
    with conexao() as conn:
        linha = conn.execute(
            "SELECT funcao_cidade FROM colecao_classes WHERE classe = ?", (classe,),
        ).fetchone()
    return linha["funcao_cidade"] if linha else None
