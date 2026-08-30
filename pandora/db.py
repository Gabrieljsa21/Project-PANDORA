# -*- coding: utf-8 -*-
"""Persistência do Colecionador (gacha estilo Mudae) via SQLite (`sqlite3` da
stdlib, sem dependência nova) - EXTRAÍDO do Project-ERIS em 2026-08-29 (era
`eris/db.py`, banco `data/eris.db` - ver `eris.config`/histórico completo em
`CHANGELOG.md`/`ARQUITETURA.md` do ERIS). Banco PRÓPRIO (`data/pandora.db`,
`pandora.config.CAMINHO_BANCO`) - não compartilha arquivo com o `eris.db`
(que ficou só com o núcleo do bot: donos/roteamento/auditoria/cache de
guilds). Ver "Extraído do Project-ERIS" em `ARQUITETURA.md` deste repo pro
motivo da extração (biblioteca Python local, sem processo/HTTP próprio -
diferente do padrão MOIRAI/ECHO - decisão explícita: todo clique de roll/
claim/troca cai no orçamento de 3s do Discord, um satélite HTTP colocaria
uma chamada de rede em cima de CADA clique)."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from pandora.config import CAMINHO_BANCO, PASTA_DADOS

_SCHEMA = """
-- Coleção de personagens (colecionador estilo Mudae, ver
-- PLANO_COLECAO_WAIFUS.md) - catálogo carregado de uma fonte externa
-- (get_waifu, ~31 mil personagens); dono por personagem/roll/economia
-- entram como tabelas próprias quando essas mecânicas forem implementadas.
CREATE TABLE IF NOT EXISTS colecao_personagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte_id INTEGER UNIQUE NOT NULL,
    slug TEXT NOT NULL,
    nome TEXT NOT NULL,
    nome_original TEXT,
    nome_romanizado TEXT,
    imagem_url TEXT,
    descricao TEXT,
    serie TEXT,
    genero TEXT NOT NULL,
    nsfw INTEGER NOT NULL DEFAULT 0,
    popularidade INTEGER NOT NULL DEFAULT 0,
    tags TEXT,
    ativo INTEGER NOT NULL DEFAULT 1,
    importado_em TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_colecao_personagens_nome ON colecao_personagens (nome);

-- Taxonomia de classes (2026-08-30, pedido do usuário: "n estamos criando
-- uma tabela de classes?") - fonte ÚNICA de verdade da categoria de combate
-- POR CLASSE. Antes disso, `categoria_combate` era decidido pela GAIA de
-- novo a cada personagem, mesmo REAPROVEITANDO uma classe já existente -
-- achado real ao investigar: "Guerreiro" já tinha 19 personagens DPS e 2
-- Tank, "Mago" tinha 3 Support e 3 DPS, um empate de verdade. Categoria de
-- combate é taxonomia FECHADA de propósito (pensada pra restrições da
-- Torre no futuro) - não devia variar por personagem dentro da MESMA
-- classe. Daqui pra frente, uma classe REAPROVEITADA sempre usa a
-- categoria JÁ REGISTRADA aqui (nunca a nova sugestão da GAIA pra aquele
-- personagem específico); só uma classe NOVA (nunca vista) grava uma
-- entrada nova.
CREATE TABLE IF NOT EXISTS colecao_classes (
    classe TEXT PRIMARY KEY,
    categoria_combate TEXT NOT NULL
);

-- Config do colecionador por servidor - NSFW + todos os números de
-- dificuldade (rolls/claims/duração do card/tamanho da puxada/chance de
-- wish-roll), pedido do usuário 2026-08-29 ("o certo seria tudo q
-- definimos ali ser configurável") depois de ajustar esses valores no
-- código à mão - nenhum admin deveria precisar editar `gacha.py` e
-- reiniciar o processo só pra mudar um número. Ver `_CONFIG_COLECAO_
-- PADRAO` pros defaults quando o servidor nunca configurou nada.
CREATE TABLE IF NOT EXISTS colecao_configuracao_guild (
    guild_id TEXT PRIMARY KEY,
    nsfw_permitido INTEGER NOT NULL DEFAULT 1,
    rolls_por_ciclo INTEGER NOT NULL DEFAULT 50,
    ciclo_rolls_minutos INTEGER NOT NULL DEFAULT 60,
    claims_por_ciclo INTEGER NOT NULL DEFAULT 1,
    ciclo_claims_minutos INTEGER NOT NULL DEFAULT 60,
    duracao_card_segundos INTEGER NOT NULL DEFAULT 3600,
    max_rolls_por_comando INTEGER NOT NULL DEFAULT 10,
    chance_wish_roll REAL NOT NULL DEFAULT 0.20
);

-- Dono único por personagem POR SERVIDOR (decisão do usuário: nada de
-- duplicatas como no Fable) - continua único dono por (guild, personagem),
-- mas ela NÃO sai mais do pool de roll (2026-08-29, pedido do usuário: "vc
-- vai gerando classe..."/ERIS_sistema_colecao_wishards.md, seção 4 -
-- personagem já reivindicada volta a poder aparecer, alimentando Afinidade/
-- reencontro, ver eris/colecao/gacha.py).
CREATE TABLE IF NOT EXISTS colecao_propriedade (
    guild_id TEXT NOT NULL,
    personagem_id INTEGER NOT NULL,
    dono_id TEXT NOT NULL,
    reivindicado_em TEXT NOT NULL,
    PRIMARY KEY (guild_id, personagem_id)
);

CREATE INDEX IF NOT EXISTS idx_colecao_propriedade_dono ON colecao_propriedade (guild_id, dono_id);

CREATE TABLE IF NOT EXISTS colecao_wishlist (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    personagem_id INTEGER NOT NULL,
    adicionado_em TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, personagem_id)
);

-- Cooldown de rolls/claims - reset PREGUIÇOSO (checado sob demanda, sem job
-- por trás varrendo jogador por jogador), ver `_consumir_recurso`.
CREATE TABLE IF NOT EXISTS colecao_estado_jogador (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    rolls_restantes INTEGER NOT NULL,
    rolls_resetam_em TEXT NOT NULL,
    claims_restantes INTEGER NOT NULL,
    claims_resetam_em TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

-- Afinidade (0-10) por (guild, dono, personagem) - ERIS_sistema_colecao_
-- wishards.md, Seção 7. 0 é só o estado IMPLÍCITO de "nunca foi sua" (sem
-- linha na tabela); nasce em 1 no 1º claim (`definir_afinidade_inicial`) e
-- SOBREVIVE ao divórcio (removendo só `colecao_propriedade`) - "se o
-- usuário recuperar a personagem futuramente, o vínculo anterior continua".
CREATE TABLE IF NOT EXISTS colecao_afinidade (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    personagem_id INTEGER NOT NULL,
    afinidade INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (guild_id, user_id, personagem_id)
);

-- WiShards ("Wish Shards", pedido do usuário) - moeda única do Colecionador,
-- por (guild, usuário). Saldo é só leitura rápida; `colecao_wishards_ledger`
-- é a fonte de verdade contábil (ERIS_sistema_colecao_wishards.md, Seção 6:
-- "a economia deve usar preferencialmente um ledger").
CREATE TABLE IF NOT EXISTS colecao_wishards_saldo (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    saldo INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS colecao_wishards_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    quantidade INTEGER NOT NULL,
    origem TEXT NOT NULL,
    motivo TEXT,
    referencia TEXT,
    saldo_resultante INTEGER NOT NULL,
    criado_em TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_colecao_wishards_ledger_usuario ON colecao_wishards_ledger (guild_id, user_id);

-- Soulstone (2026-08-30, pedido do usuário) - item usado SÓ pra upar
-- Afinidade (nunca vira Soulmate - isso continua exclusivo de reencontro,
-- ver `gacha._resolver_resultado`). Mesma estrutura saldo+ledger de
-- WiShards (`colecao_wishards_saldo`/`_ledger` acima) - não existe nenhum
-- outro padrão de "item"/recurso no código pra reaproveitar em vez disso.
CREATE TABLE IF NOT EXISTS colecao_soulstone_saldo (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    saldo INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS colecao_soulstone_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    quantidade INTEGER NOT NULL,
    origem TEXT NOT NULL,
    motivo TEXT,
    referencia TEXT,
    saldo_resultante INTEGER NOT NULL,
    criado_em TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_colecao_soulstone_ledger_usuario ON colecao_soulstone_ledger (guild_id, user_id);

-- Proposta de troca bilateral (ERIS_sistema_colecao_wishards.md Seção 13) -
-- `oferece_personagens`/`pede_personagens` são listas de IDs em JSON (não
-- uma tabela associativa própria - baixa cardinalidade por proposta, no
-- máximo algumas personagens de cada lado). SEM reserva ativa de recursos
-- durante a proposta (simplificação deliberada pra escala pessoal - ver
-- ARQUITETURA.md) - tudo é revalidado (dono ainda é dono, saldo ainda
-- alcança) no momento do aceite, nunca confiando só no que a proposta dizia
-- na hora de criar.
CREATE TABLE IF NOT EXISTS colecao_troca_proposta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    proponente_id TEXT NOT NULL,
    alvo_id TEXT NOT NULL,
    oferece_personagens TEXT NOT NULL,
    oferece_wishards INTEGER NOT NULL DEFAULT 0,
    pede_personagens TEXT NOT NULL,
    pede_wishards INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pendente',
    criado_em TEXT NOT NULL
);

-- Séries bloqueadas por servidor (ERIS_sistema_colecao_wishards.md Seção 21
-- /PLANO_COLECAO_WAIFUS.md Seção 4 - única config administrativa do plano
-- original que ainda faltava).
CREATE TABLE IF NOT EXISTS colecao_series_bloqueadas (
    guild_id TEXT NOT NULL,
    serie TEXT NOT NULL,
    PRIMARY KEY (guild_id, serie)
);

-- Favoritas/Protegidas - por (guild, dono, personagem). Seção 15: impede
-- AÇÕES DESTRUTIVAS ACIDENTAIS (bloqueio duro no Merge, confirmação extra
-- no Divórcio - ver eris/bot.py).
CREATE TABLE IF NOT EXISTS colecao_favoritas (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    personagem_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id, personagem_id)
);

-- Cards individuais com reação AINDA pendentes (2026-08-29, pedido do
-- usuário: "cria uma tabela com a msm logica dos colecoes disponiveis...
-- checa o tempo de duração configurado no server p ficar disponivel")-
-- antes vivia só em memória (`gacha._CARDS_REACAO_PENDENTES`), perdido a
-- cada restart do processo (achado real: usuário perdeu acesso a uma
-- personagem rolada porque o bot reiniciou no meio da janela de 1h).
-- `expira_em` é calculado na hora de registrar (`duracao_card_segundos`
-- da config do servidor NAQUELE momento) - igual o comportamento antigo.
CREATE TABLE IF NOT EXISTS colecao_cards_pendentes (
    message_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    personagem_id INTEGER NOT NULL,
    emoji TEXT NOT NULL,
    expira_em TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cards_pendentes_guild ON colecao_cards_pendentes (guild_id, expira_em);

-- Party (equipe de gameplay, ainda sem Torre pra jogar - protege contra
-- Merge desde já) e Vitrine (mostruário público) - MESMA forma (até 5
-- posições por dono), `tipo` distingue as duas em vez de 2 tabelas quase
-- idênticas (Seções 15/17).
CREATE TABLE IF NOT EXISTS colecao_equipe (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    tipo TEXT NOT NULL,
    posicao INTEGER NOT NULL,
    personagem_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id, tipo, posicao)
);

-- Estado da sincronização contínua do catálogo (2026-08-29,
-- `eris/colecao/sincronizador.py`) - linha ÚNICA (`id = 1`), não é por
-- servidor nem por personagem. Guarda quando rodou pela última vez (pra
-- decidir se já está "devido" de novo) e o resultado, só pra dar pra ver
-- em log/estado sem precisar grepar o arquivo de log inteiro.
CREATE TABLE IF NOT EXISTS colecao_sincronizacao (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    ultima_tentativa_em TEXT,
    ultimo_sucesso_em TEXT,
    ultimo_resultado TEXT
);

-- Modo Auto-coleta por usuário (2026-08-30, pedido do usuário: "faz a msm
-- coisa q os bots de rodar auto os 50 e so 5min depois coletar o mais
-- popular... vai fazer os rolls aos 50min e coletar ao 55min") - toggle
-- opt-in POR (guild, usuário), gasta a cota REAL de rolls/claims da
-- pessoa (nunca uma cota separada tipo NPC) - só ativa o roll automático
-- se o ciclo ainda estiver INTOCADO (`rolls_disponiveis == limite`).
CREATE TABLE IF NOT EXISTS colecao_auto_colecionar_usuarios (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (guild_id, user_id)
);

-- Torre (2026-08-30, ERIS_power_afinidade_soulmate_niveis.md) - progresso é
-- só o ANDAR ATUAL por (guild, usuário), nasce em 1. Determinístico (sem
-- RNG) - perder um andar não consome nada, só significa "a Party ainda não
-- é forte o suficiente"; tentar de novo é sempre permitido.
CREATE TABLE IF NOT EXISTS colecao_torre_progresso (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    andar_atual INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (guild_id, user_id)
);

-- Progressão Global da conta (2026-08-30, análise trazida pelo usuário:
-- "a personagem possui um limite de desenvolvimento. A conta não") -
-- resolve o teto que a Torre expôs (Andar 36, Party já quase maximizada
-- individualmente, mas o Power exigido continuando a subir). Nível de
-- Progressão SEM TETO, alimentado por XP (claim/nível/divórcio/merge/
-- andar da Torre/marco de coleção - nunca uma moeda, só enche a barra).
-- `nivel_treinamento_global`/`nivel_potencial_colecao` são os upgrades
-- da Loja (`pandora/progressao.py`) - também SEM TETO de propósito
-- (diferente de `comprar_upgrade_rolls`/`comprar_upgrade_claims`, que
-- têm nível máximo).
CREATE TABLE IF NOT EXISTS colecao_progressao (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    nivel INTEGER NOT NULL DEFAULT 1,
    xp INTEGER NOT NULL DEFAULT 0,
    nivel_treinamento_global INTEGER NOT NULL DEFAULT 0,
    nivel_potencial_colecao INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

-- Marcos de quantidade de personagens ÚNICAS coletadas (2026-08-30,
-- análise do usuário Seção 11 - "não deve ser a principal fonte infinita
-- de CP", só milestone) - guarda o MAIOR marco já pago pra nunca creditar
-- de novo, mesmo se o jogador ficar oscilando perto de um marco (Merge
-- reduz contagem, por exemplo).
CREATE TABLE IF NOT EXISTS colecao_progressao_marcos (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    maior_marco INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

-- Cidade (2026-08-30, análise do usuário Seção 13 + pedido explícito:
-- "n iremos setar personagens em funcoes manualmente, sera automatico
-- com base na classe/profissão") - produção é ACUMULADA NO TEMPO (pull-
-- based, sem scheduler novo) - só guarda quando foi a última coleta,
-- `pandora.cidade.coletar_producao_pendente` calcula o resto na hora que
-- o jogador abre o painel.
-- 🔥 3 colunas de bônus de CP pra Party viraram um SNAPSHOT aqui
-- (2026-08-30, Cidade v2 - efeitos diferenciados por área) - calculadas
-- junto no mesmo momento que `ultima_producao_em` é atualizado (visita
-- ao painel "🏙️ Cidade"), nunca recalculadas a cada cálculo de Torre
-- (evita escanear a coleção inteira nesse hot path, ver `pandora.torre.
-- calcular_power_party`/`pandora.cidade`).
CREATE TABLE IF NOT EXISTS colecao_cidade_estado (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    ultima_producao_em TEXT,
    cp_bonus_militar_fixo REAL NOT NULL DEFAULT 0,
    cp_bonus_arcano_percentual REAL NOT NULL DEFAULT 0,
    cp_bonus_colecao_fixo REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);
"""

# 🔥 Usado só pela migração de `inicializar()` acima - precisa ficar em SQL
# cru (não dá pra usar `_CONFIG_COLECAO_PADRAO` direto porque o tipo SQL de
# `chance_wish_roll` é REAL, os outros são INTEGER).
_NOVAS_COLUNAS_CONFIG_COLECAO = {
    "rolls_por_ciclo": "INTEGER NOT NULL DEFAULT 50",
    "ciclo_rolls_minutos": "INTEGER NOT NULL DEFAULT 60",
    "claims_por_ciclo": "INTEGER NOT NULL DEFAULT 1",
    "ciclo_claims_minutos": "INTEGER NOT NULL DEFAULT 60",
    "duracao_card_segundos": "INTEGER NOT NULL DEFAULT 3600",
    "max_rolls_por_comando": "INTEGER NOT NULL DEFAULT 10",
    "chance_wish_roll": "REAL NOT NULL DEFAULT 0.20",
    # 🔥 Canal onde o auto-colecionador (GAIA/ERIS, ver eris/colecao/auto_
    # colecionador.py) anuncia o que reivindicou - NULL = cai no
    # `guild.system_channel` na hora (sem migração pra preencher, ver
    # `/colecao_admin canal`).
    "canal_anuncio_id": "TEXT",
}

# 🔥 Defaults quando o servidor nunca configurou nada (`colecao_
# configuracao_guild` sem linha) - mesmos valores "VIP fácil" decididos em
# 2026-08-29 (ver CHANGELOG.md), agora como PONTO DE PARTIDA editável por
# servidor via `/colecao_admin`, não mais constante fixa em `gacha.py`.
_CONFIG_COLECAO_PADRAO = {
    "nsfw_permitido": True,
    "rolls_por_ciclo": 50,
    "ciclo_rolls_minutos": 60,
    "claims_por_ciclo": 1,
    "ciclo_claims_minutos": 60,
    "duracao_card_segundos": 3600,
    "max_rolls_por_comando": 10,
    "chance_wish_roll": 0.20,
    "canal_anuncio_id": None,
}

# 🔥 Tiers de raridade fixos por personagem (1=comum .. 5=lendária),
# calculados por percentil de popularidade dentro do catálogo ativo - mesma
# distribuição 50/30/15/4/1% do `gacha.ts` do Fable, só que lá é a
# PROBABILIDADE de sortear cada rating no momento do roll (personagem pode
# ter qualquer rating); aqui vira uma característica FIXA do personagem
# (recalculada só quando o catálogo é reimportado), e o roll sorteia o tier
# com essas mesmas probabilidades antes de escolher um personagem dentro dele
# (ver `eris/colecao/gacha.py`).
_CORTES_RARIDADE = [
    (0.50, 1),
    (0.80, 2),
    (0.95, 3),
    (0.99, 4),
    (1.00, 5),
]

def _garantir_pasta():
    os.makedirs(PASTA_DADOS, exist_ok=True)


@contextmanager
def conexao():
    _garantir_pasta()
    conn = sqlite3.connect(CAMINHO_BANCO)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def inicializar():
    with conexao() as conn:
        conn.executescript(_SCHEMA)
        # 🔥 Migração aditiva (2026-08-29) - `colecao_personagens` já tinha
        # 30 mil linhas importadas antes da coluna `raridade` existir;
        # `ALTER TABLE` não tem `IF NOT EXISTS` pra coluna no SQLite, então
        # checamos via `PRAGMA table_info` (mesmo espírito de "migrar dados,
        # nunca resetar" já seguido no resto do ecossistema).
        colunas = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_personagens)")}
        if "raridade" not in colunas:
            conn.execute("ALTER TABLE colecao_personagens ADD COLUMN raridade INTEGER NOT NULL DEFAULT 1")
        # 🔥 Classe (2026-08-29, pedido do usuário) - NUNCA pré-calculada em
        # lote (diferente da raridade) - fica NULL até a personagem ser
        # reivindicada pela 1ª vez em QUALQUER servidor; só aí o ERIS pede
        # pra GAIA classificar via LLM (`pandora.gaia_webhook.
        # pedir_classe_personagem`), reaproveitando uma classe já existente
        # no catálogo quando fizer sentido, ou inventando uma nova - taxonomia
        # aberta, cresce sozinha (ver `pandora.gacha`). "Secreta" até a
        # personagem ser coletada, de propósito - não aparece no card do roll.
        if "classe" not in colunas:
            conn.execute("ALTER TABLE colecao_personagens ADD COLUMN classe TEXT")
        # 🔥 Categoria de combate (DPS/Tank/Support, Seção 16) - decidida
        # pela GAIA JUNTO com a classe (mesma chamada, mesmo gatilho: 1ª
        # reivindicação em qualquer servidor) - diferente da classe (aberta),
        # é uma taxonomia FECHADA de propósito, pra permitir regras de
        # restrição por andar da Torre no futuro (ex.: "só 1 Mage") sem
        # depender de uma lista que pode crescer sem limite.
        if "categoria_combate" not in colunas:
            conn.execute("ALTER TABLE colecao_personagens ADD COLUMN categoria_combate TEXT")
        # 🔥 Classe canônica x exibição (2026-08-29, mesmo dia - correção do
        # usuário depois de ver classes tipo "Comediante"/"Maid" em vez de
        # arquétipo de RPG, e de notar que forçar SEMPRE a forma masculina
        # deixava cards femininos "artificiais": "eu manteria a taxonomia
        # internamente no masculino... mas separaria nome canônico de nome
        # exibido... o nome exibido pode concordar com o gênero da
        # personagem"). `classe` continua sendo a forma CANÔNICA (masculina/
        # singular, é o que entra em `classes_existentes()`/estatísticas -
        # "Ladino"/"Bardo", nunca duplica em "Ladina" separado);
        # `classe_exibicao` é o que aparece pro jogador (concorda com o
        # gênero da personagem - "Ladina" pra Ai Hayasaka, mas continua
        # contada como "Ladino" nas estatísticas). NULL cai pra `classe` na
        # exibição (`consulta.linha_personagem`/`gacha`).
        if "classe_exibicao" not in colunas:
            conn.execute("ALTER TABLE colecao_personagens ADD COLUMN classe_exibicao TEXT")
        # 🔥 Prova de Soulmate (2026-08-29, ERIS_power_afinidade_soulmate_
        # niveis.md) - conteúdo gerado 1x pela GAIA na 1ª vez que a
        # personagem chega em Afinidade 10 (mesmo padrão de `classe`/
        # `classe_exibicao`: NULL até então, nunca regenerado depois de
        # preenchido).
        #
        # 🔥 REDESENHADA no mesmo dia (feedback do usuário testando ao vivo
        # com Hyuga Hinata: "a mensagem não mostra nenhuma escolha... faz o
        # texto parecer cenográfico, não uma prova de verdade") - `intro`
        # (narrativa solta seguida direto do botão "Enfrentar") foi
        # SUBSTITUÍDA por `situacao` + `opcoes` (3 respostas, uma marcada
        # como a que combina com a personagem - escolher a certa dá um
        # bônus de chance SÓ NESSA tentativa, nunca garante sucesso
        # sozinho) - `reacao_acerto`/`reacao_erro` são as falas curtas
        # mostradas na hora da escolha. `derrota` continua existindo (fala
        # de quando o jogador perde o RNG em si), só o PROMPT mudou (agora
        # pede 1 frase curta, sem "dar conselho" - antes soava genérico
        # demais de tanto se repetir a cada tentativa perdida).
        if "prova_soulmate_intro" in colunas:
            conn.execute("ALTER TABLE colecao_personagens DROP COLUMN prova_soulmate_intro")
        for coluna_prova in (
            "prova_soulmate_nome", "prova_soulmate_descricao", "prova_soulmate_situacao",
            "prova_soulmate_opcoes", "prova_soulmate_reacao_acerto", "prova_soulmate_reacao_erro",
            "prova_soulmate_derrota", "prova_soulmate_vitoria",
        ):
            if coluna_prova not in colunas:
                conn.execute(f"ALTER TABLE colecao_personagens ADD COLUMN {coluna_prova} TEXT")

        # 🔥 Migração aditiva (2026-08-29) - `colecao_configuracao_guild` já
        # tinha guilds configuradas só com `nsfw_permitido` antes de virar
        # "toda a dificuldade é configurável" - `ADD COLUMN ... DEFAULT`
        # preenche as linhas existentes automaticamente com o padrão.
        colunas_config = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_configuracao_guild)")}
        for coluna, definicao_sql in _NOVAS_COLUNAS_CONFIG_COLECAO.items():
            if coluna not in colunas_config:
                conn.execute(f"ALTER TABLE colecao_configuracao_guild ADD COLUMN {coluna} {definicao_sql}")

        # 🔥 Guaranteed Roll (2026-08-29, ERIS_sistema_colecao_wishards.md
        # Seção 12) - comprado na loja, consumido no PRÓXIMO roll (qualquer
        # `/wa`/`/ha`/`/ma`). NULL = sem garantia pendente.
        colunas_estado = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_estado_jogador)")}
        if "garantia_raridade_minima" not in colunas_estado:
            conn.execute("ALTER TABLE colecao_estado_jogador ADD COLUMN garantia_raridade_minima INTEGER")
        # 🔥 Upgrade permanente de rolls máximos (Seção 11) - único upgrade do
        # plano com preços concretos (os outros ficaram "pra balancear
        # depois"); nível 0-5, cada nível soma +5 ao `rolls_por_ciclo` do
        # SERVIDOR (é bônus PESSOAL em cima da config do servidor, não
        # substitui ela).
        if "nivel_upgrade_rolls" not in colunas_estado:
            conn.execute("ALTER TABLE colecao_estado_jogador ADD COLUMN nivel_upgrade_rolls INTEGER NOT NULL DEFAULT 0")
        # 🔥 Upgrade permanente de claims máximos (2026-08-29, pedido do
        # usuário: "claim tem q ter upgrade permanente tbm", espelhando o
        # upgrade de rolls acima) - nível 0-5, cada nível soma +1 ao
        # `claims_por_ciclo` do SERVIDOR (bônus PESSOAL, não substitui a
        # config do servidor - mesmo espírito do upgrade de rolls).
        if "nivel_upgrade_claims" not in colunas_estado:
            conn.execute("ALTER TABLE colecao_estado_jogador ADD COLUMN nivel_upgrade_claims INTEGER NOT NULL DEFAULT 0")

        # 🔥 Prova de Soulmate (2026-08-29) - substitui o auto-flag antigo
        # ("Afinidade 10 == Soulmate", só cosmético `💍`) por uma tentativa de
        # verdade que o jogador precisa vencer. `is_soulmate` é o status real
        # (2,0× de multiplicador de Power no futuro, cosméticos `💞` hoje);
        # `soulmate_tentativas`/`soulmate_ultima_tentativa_em` alimentam a
        # chance crescente por falha e o cooldown de 1h/personagem.
        colunas_afinidade = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_afinidade)")}
        if "is_soulmate" not in colunas_afinidade:
            conn.execute("ALTER TABLE colecao_afinidade ADD COLUMN is_soulmate INTEGER NOT NULL DEFAULT 0")
        if "soulmate_tentativas" not in colunas_afinidade:
            conn.execute("ALTER TABLE colecao_afinidade ADD COLUMN soulmate_tentativas INTEGER NOT NULL DEFAULT 0")
        if "soulmate_ultima_tentativa_em" not in colunas_afinidade:
            conn.execute("ALTER TABLE colecao_afinidade ADD COLUMN soulmate_ultima_tentativa_em TEXT")
        # 🔥 Nível de Personagem (2026-08-30, Torre, ERIS_power_afinidade_
        # soulmate_niveis.md Seção 5) - investimento DELIBERADO do jogador
        # (gasta WiShards, ver `subir_nivel`), 1-10, +50 Power fixo por
        # nível acima do 1º. Mora em `colecao_afinidade` porque é a MESMA
        # propriedade de escopo (guild+user+personagem) que Afinidade/
        # Soulmate - o vínculo do jogador com ESSA personagem específica.
        if "nivel" not in colunas_afinidade:
            conn.execute("ALTER TABLE colecao_afinidade ADD COLUMN nivel INTEGER NOT NULL DEFAULT 1")

        # 🔥 Backfill ÚNICO de `colecao_classes` (2026-08-30) - só roda se a
        # tabela nova estiver vazia (idempotente, nunca sobrescreve uma
        # reconciliação manual futura). Pra cada classe já usada no
        # catálogo, a categoria_combate CANÔNICA é a MAIORIA entre os
        # personagens que já têm essa classe (empate cai pro default mais
        # seguro do resto do sistema, "DPS" - mesmo critério de
        # `classificar_personagem_colecao` do lado da GAIA). Depois de
        # decidir a canônica, NORMALIZA `colecao_personagens.categoria_
        # combate` de toda personagem dessa classe pra bater com ela -
        # antes disso, "Guerreiro" tinha 19 DPS + 2 Tank, "Mago" tinha 3
        # Support + 3 DPS (empate de verdade, resolvido como DPS aqui).
        if conn.execute("SELECT COUNT(*) AS n FROM colecao_classes").fetchone()["n"] == 0:
            classes_ja_usadas = [
                r["classe"] for r in conn.execute(
                    "SELECT DISTINCT classe FROM colecao_personagens WHERE classe IS NOT NULL"
                )
            ]
            for classe in classes_ja_usadas:
                contagens = conn.execute(
                    "SELECT categoria_combate, COUNT(*) AS n FROM colecao_personagens "
                    "WHERE classe = ? AND categoria_combate IS NOT NULL "
                    "GROUP BY categoria_combate ORDER BY n DESC",
                    (classe,),
                ).fetchall()
                if not contagens:
                    continue
                melhor_n = contagens[0]["n"]
                empatadas = [c["categoria_combate"] for c in contagens if c["n"] == melhor_n]
                categoria_canonica = "DPS" if len(empatadas) > 1 and "DPS" in empatadas else empatadas[0]
                conn.execute(
                    "INSERT INTO colecao_classes (classe, categoria_combate) VALUES (?, ?) "
                    "ON CONFLICT(classe) DO NOTHING",
                    (classe, categoria_canonica),
                )
                conn.execute(
                    "UPDATE colecao_personagens SET categoria_combate = ? WHERE classe = ?",
                    (categoria_canonica, classe),
                )

        # 🔥 `categoria_combate` REMOVIDA de `colecao_personagens` (2026-08-30,
        # pedido do usuário: "vc so criou a tabela ou ta salvando id delas e
        # pondo nos personagens?") - depois do backfill acima (que ainda
        # precisa da coluna pra existir, roda 1x só, ANTES desta linha),
        # `colecao_classes` vira a ÚNICA dona desse dado - manter a coluna
        # aqui seria uma cópia duplicada, sujeita a divergir nas mesma forma
        # que motivou criar a tabela. `colunas` foi recarregado (a variável
        # de cima já não reflete colunas adicionadas nesta mesma chamada).
        colunas_personagens_atual = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_personagens)")}
        if "categoria_combate" in colunas_personagens_atual:
            conn.execute("ALTER TABLE colecao_personagens DROP COLUMN categoria_combate")

        # 🔥 Cidade (2026-08-30, análise do usuário + pedido explícito: "n
        # iremos setar personagens em funcoes manualmente, sera automatico
        # com base na classe/profissão") - `funcao_cidade` é um 2º campo
        # derivado da CLASSE, mesmo espírito de `categoria_combate` (a IA
        # decide o aberto/temático - a classe -, o código valida o fechado/
        # mecânico - a função). Mora em `colecao_classes` (não em `colecao_
        # personagens`), mesma razão de sempre: uma classe reaproveitada
        # nunca deveria ter função diferente pra personagens diferentes.
        # NULL pra classes já existentes até o backfill manual rodar
        # (`backfill_funcao_cidade_2026-08-30.py`, raiz do repo).
        colunas_classes = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_classes)")}
        if "funcao_cidade" not in colunas_classes:
            conn.execute("ALTER TABLE colecao_classes ADD COLUMN funcao_cidade TEXT")

        # 🔥 Cidade v2 (2026-08-30, efeitos diferenciados por área) - 3
        # colunas de snapshot de bônus de CP pra Party, ver `_SCHEMA`
        # acima (`colecao_cidade_estado` já existia só com `ultima_
        # producao_em`, criada mais cedo nesta mesma sessão).
        colunas_cidade = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_cidade_estado)")}
        for coluna_cidade in ("cp_bonus_militar_fixo", "cp_bonus_arcano_percentual", "cp_bonus_colecao_fixo"):
            if coluna_cidade not in colunas_cidade:
                conn.execute(f"ALTER TABLE colecao_cidade_estado ADD COLUMN {coluna_cidade} REAL NOT NULL DEFAULT 0")


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
        "canal_anuncio_id": linha["canal_anuncio_id"],
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
    """Amostra de personagens SEM DONO nesse servidor, pra `/loja ver` -
    diferente de `candidatos_por_raridade` (pool de ROLL, que desde
    2026-08-29 inclui personagens já reivindicadas de propósito), a loja só
    pode vender quem está livre (Seção 10)."""
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


def classes_existentes():
    """Taxonomia de classes já usada no catálogo INTEIRO (não por servidor) -
    passada pra GAIA classificar a próxima personagem reivindicada, pra ela
    reaproveitar uma classe existente em vez de inventar uma quase-sinônima
    toda hora (ver `pandora.gaia_webhook.pedir_classe_personagem`). Lê de
    `colecao_classes` (2026-08-30, fonte única depois do backfill de
    `inicializar()`) - antes lia `DISTINCT classe` direto de `colecao_
    personagens`, o que funcionava igual pra listar nomes, mas não dava
    onde guardar a categoria_combate CANÔNICA de cada uma."""
    with conexao() as conn:
        linhas = conn.execute("SELECT classe FROM colecao_classes ORDER BY classe").fetchall()
        return [r["classe"] for r in linhas]


def categoria_combate_da_classe(classe):
    """Categoria de combate CANÔNICA já registrada pra essa classe, ou
    `None` se for uma classe nova (nunca vista antes)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT categoria_combate FROM colecao_classes WHERE classe = ?", (classe,),
        ).fetchone()
    return linha["categoria_combate"] if linha else None


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
    `funcao_cidade_da_classe`."""
    with conexao() as conn:
        canonica = conn.execute(
            "SELECT categoria_combate, funcao_cidade FROM colecao_classes WHERE classe = ?", (classe,),
        ).fetchone()
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
    return categoria_combate


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
    creditar_xp_progressao(guild_id, user_id, xp)
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


def dono_do_personagem(guild_id, personagem_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT dono_id FROM colecao_propriedade WHERE guild_id = ? AND personagem_id = ?",
            (str(guild_id), personagem_id),
        ).fetchone()
        return linha["dono_id"] if linha else None


def ranking_guild(guild_id, limite=10):
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT dono_id, COUNT(*) AS total FROM colecao_propriedade WHERE guild_id = ? "
            "GROUP BY dono_id ORDER BY total DESC LIMIT ?",
            (str(guild_id), limite),
        ).fetchall()
        return [dict(r) for r in linhas]


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
    """Status REAL de Soulmate (2026-08-29, Prova de Soulmate) - só vira
    True depois de vencer a Prova (`registrar_tentativa_soulmate`), nunca
    mais um auto-flag de "afinidade >= 10". Usado por `gacha._resolver_
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


def personagens_prontas_para_prova(guild_id, user_id):
    """Candidatas à Prova de Soulmate: Afinidade 10 E ainda não é Soulmate -
    alimenta o select do botão "💞 Prova de Soulmate" do hub `/waifu` (ver
    `pandora/paineis.py::ViewHubWaifu`)."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT p.*, a.afinidade, a.soulmate_tentativas, a.soulmate_ultima_tentativa_em "
            "FROM colecao_afinidade a JOIN colecao_personagens p ON p.id = a.personagem_id "
            "WHERE a.guild_id = ? AND a.user_id = ? AND a.afinidade >= 10 AND a.is_soulmate = 0 "
            "ORDER BY p.nome",
            (str(guild_id), str(user_id)),
        ).fetchall()
        return [dict(r) for r in linhas]


def definir_textos_prova_soulmate(personagem_id, nome, descricao, situacao, opcoes_json, reacao_acerto, reacao_erro, derrota, vitoria):
    """Só grava se ainda não tinha (`WHERE prova_soulmate_opcoes IS NULL`,
    não mais `prova_soulmate_nome` - 2026-08-29, achado ao redesenhar:
    personagens já testadas no schema ANTIGO tinham `nome` preenchido mas
    nenhuma `opcoes`, e o guard antigo travava a regeneração pra sempre;
    checar a coluna NOVA faz o cache se auto-curar sozinho pra quem já
    tinha dado a Prova antes do redesenho, sem precisar de UPDATE manual).
    `opcoes_json` é `prova_soulmate_opcoes` já serializado (`json.dumps`) -
    mesmo padrão de cache 1x-pra-sempre de `definir_classe_personagem`."""
    with conexao() as conn:
        conn.execute(
            "UPDATE colecao_personagens SET prova_soulmate_nome = ?, prova_soulmate_descricao = ?, "
            "prova_soulmate_situacao = ?, prova_soulmate_opcoes = ?, prova_soulmate_reacao_acerto = ?, "
            "prova_soulmate_reacao_erro = ?, prova_soulmate_derrota = ?, prova_soulmate_vitoria = ? "
            "WHERE id = ? AND prova_soulmate_opcoes IS NULL",
            (nome, descricao, situacao, opcoes_json, reacao_acerto, reacao_erro, derrota, vitoria, personagem_id),
        )


def registrar_tentativa_soulmate(guild_id, user_id, personagem_id, venceu, agora_iso):
    """Vitória: `is_soulmate = 1`, zera `soulmate_tentativas` (não importa
    mais depois de virar Soulmate). Derrota: incrementa `soulmate_tentativas`
    (alimenta a chance crescente por falha e o pity) e marca
    `soulmate_ultima_tentativa_em` (cooldown de 1h/personagem)."""
    with conexao() as conn:
        if venceu:
            conn.execute(
                "UPDATE colecao_afinidade SET is_soulmate = 1, soulmate_tentativas = 0, "
                "soulmate_ultima_tentativa_em = ? WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
                (agora_iso, str(guild_id), str(user_id), personagem_id),
            )
        else:
            conn.execute(
                "UPDATE colecao_afinidade SET soulmate_tentativas = soulmate_tentativas + 1, "
                "soulmate_ultima_tentativa_em = ? WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
                (agora_iso, str(guild_id), str(user_id), personagem_id),
            )


def definir_afinidade_admin(guild_id, user_id, personagem_id, valor):
    """Ferramenta de admin (2026-08-29, pedido do usuário: "n existe ninguem
    com afinidade 10, de comando de admin p editar" - testar a Prova de
    Soulmate ao vivo sem esperar 9 reencontros de verdade) - ajusta a coluna
    `afinidade` DIRETO, sem passar pelo incremento normal de +1 por
    reencontro (`incrementar_afinidade`). `valor` é travado em 0-10, mesmo
    teto natural da mecânica. Não mexe em `is_soulmate`/`soulmate_
    tentativas` - só a Afinidade em si."""
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
    if saldo_wishards(guild_id, user_id) < custo:
        return False, f"Custa {custo} WiShards e você não tem o suficiente."
    creditar_wishards(guild_id, user_id, -custo, "upgrade_nivel_personagem", personagem["nome"], str(personagem_id))
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_afinidade (guild_id, user_id, personagem_id, afinidade, nivel) VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(guild_id, user_id, personagem_id) DO UPDATE SET nivel = excluded.nivel",
            (str(guild_id), str(user_id), personagem_id, nivel_alvo),
        )
    xp = custo // 5
    creditar_xp_progressao(guild_id, user_id, xp)
    return True, f"{personagem['nome']} subiu pro nível {nivel_alvo}! (custou {custo} WiShards, +{xp} XP de Progressão)"


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
    if saldo_soulstone(guild_id, user_id) < custo:
        return False, f"Custa {custo} Soulstone e você não tem o suficiente."
    creditar_soulstone(guild_id, user_id, -custo, "upgrade_afinidade", personagem["nome"], str(personagem_id))
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_afinidade (guild_id, user_id, personagem_id, afinidade) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, personagem_id) DO UPDATE SET afinidade = excluded.afinidade",
            (str(guild_id), str(user_id), personagem_id, afinidade_alvo),
        )
    return True, f"{personagem['nome']} subiu pra Afinidade {afinidade_alvo}! (custou {custo} Soulstone)"


def tornar_soulmate(guild_id, user_id, personagem_id):
    """Marca `is_soulmate = 1` direto - função NOVA e mínima (2026-08-30),
    DESACOPLADA de `registrar_tentativa_soulmate` (que ficou dormente com
    a "Prova de Soulmate" antiga, junto de campos irrelevantes agora tipo
    `soulmate_tentativas`). Chamada só por `gacha._resolver_resultado`
    quando um reencontro acontece numa personagem já em Afinidade máxima
    e ainda não Soulmate - vira Soulmate ali mesmo, sem RNG."""
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


def creditar_wishards(guild_id, user_id, quantidade, origem, motivo=None, referencia=None):
    """Ledger + saldo sempre juntos na mesma transação - nunca só um dos
    dois (Seção 6 do plano: "a economia deve usar preferencialmente um
    ledger"). `quantidade` pode ser negativa (gasto - fases futuras de loja/
    upgrades). Devolve o novo saldo."""
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        linha = conn.execute(
            "SELECT saldo FROM colecao_wishards_saldo WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
        novo_saldo = (linha["saldo"] if linha else 0) + quantidade
        conn.execute(
            "INSERT INTO colecao_wishards_saldo (guild_id, user_id, saldo) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET saldo = excluded.saldo",
            (str(guild_id), str(user_id), novo_saldo),
        )
        conn.execute(
            "INSERT INTO colecao_wishards_ledger "
            "(guild_id, user_id, quantidade, origem, motivo, referencia, saldo_resultante, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(guild_id), str(user_id), quantidade, origem, motivo, referencia, novo_saldo, agora),
        )
        return novo_saldo


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
    """Cópia estrutural de `creditar_wishards` - ledger + saldo sempre
    juntos na mesma transação, `quantidade` pode ser negativa (gasto)."""
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        linha = conn.execute(
            "SELECT saldo FROM colecao_soulstone_saldo WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
        novo_saldo = (linha["saldo"] if linha else 0) + quantidade
        conn.execute(
            "INSERT INTO colecao_soulstone_saldo (guild_id, user_id, saldo) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET saldo = excluded.saldo",
            (str(guild_id), str(user_id), novo_saldo),
        )
        conn.execute(
            "INSERT INTO colecao_soulstone_ledger "
            "(guild_id, user_id, quantidade, origem, motivo, referencia, saldo_resultante, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(guild_id), str(user_id), quantidade, origem, motivo, referencia, novo_saldo, agora),
        )
        return novo_saldo


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
    if saldo_wishards(guild_id, user_id) < preco:
        return False, f"Custa {preco} WiShards e você não tem o suficiente."

    creditar_wishards(guild_id, user_id, -preco, "loja_compra", personagem["nome"], str(personagem_id))
    if not reivindicar(guild_id, personagem_id, user_id):
        creditar_wishards(guild_id, user_id, preco, "loja_reembolso", personagem["nome"], str(personagem_id))
        return False, "Alguém conseguiu essa personagem antes de você - reembolsado."

    definir_afinidade_inicial(guild_id, user_id, personagem_id)
    return True, f"{personagem['nome']} comprada por {preco} WiShards."


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
    limite_rolls = config["rolls_por_ciclo"] + nivel_upgrade_rolls(guild_id, user_id) * BONUS_ROLLS_POR_NIVEL
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
    `nivel_upgrade_claims`)."""
    config = obter_configuracao_colecao(guild_id)
    limite_claims = config["claims_por_ciclo"] + nivel_upgrade_claims(guild_id, user_id) * BONUS_CLAIMS_POR_NIVEL
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


# ---- Wishlist ----

def wishlist_adicionar(guild_id, user_id, personagem_id):
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO colecao_wishlist (guild_id, user_id, personagem_id, adicionado_em) "
            "VALUES (?, ?, ?, ?)",
            (str(guild_id), str(user_id), personagem_id, agora),
        )


def wishlist_remover(guild_id, user_id, personagem_id):
    with conexao() as conn:
        conn.execute(
            "DELETE FROM colecao_wishlist WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        )


def wishlist_listar(guild_id, user_id):
    # 🔥 ordenado por popularidade DESC, não por nome (2026-08-30, pedido
    # do usuário: "Todo dropdwon q listar waifu, sempre ordene pelas com
    # maior CP/popularidade") - wishlist é NÃO possuída (sem Nível/
    # Afinidade de vínculo nenhum), então CP não se aplica aqui.
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT p.* FROM colecao_wishlist w JOIN colecao_personagens p ON p.id = w.personagem_id "
            "WHERE w.guild_id = ? AND w.user_id = ? ORDER BY p.popularidade DESC",
            (str(guild_id), str(user_id)),
        ).fetchall()
        return [dict(r) for r in linhas]


def wishlist_disponiveis_no_guild(guild_id, user_id, permitir_nsfw):
    """Itens da wishlist que ainda não têm dono NESSE servidor - candidatos
    reais pro "wish roll" (ver `eris/colecao/gacha.py`) - a wishlist aumenta
    moderadamente a chance, nunca garante o aparecimento (PLANO_COLECAO_
    WAIFUS.md, Seção 12)."""
    filtros = ["w.guild_id = ?", "w.user_id = ?", "p.ativo = 1"]
    params = [str(guild_id), str(user_id)]
    if not permitir_nsfw:
        filtros.append("p.nsfw = 0")
    filtros.append("p.id NOT IN (SELECT personagem_id FROM colecao_propriedade WHERE guild_id = ?)")
    params.append(str(guild_id))
    sql = (
        "SELECT p.id FROM colecao_wishlist w JOIN colecao_personagens p ON p.id = w.personagem_id "
        f"WHERE {' AND '.join(filtros)}"
    )
    with conexao() as conn:
        return [r["id"] for r in conn.execute(sql, params).fetchall()]


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
# Favoritas/Protegidas (Seção 15)
# --------------------------------------------------------------------------

def favoritar(guild_id, user_id, personagem_id):
    with conexao() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO colecao_favoritas (guild_id, user_id, personagem_id) VALUES (?, ?, ?)",
            (str(guild_id), str(user_id), personagem_id),
        )


def desfavoritar(guild_id, user_id, personagem_id):
    with conexao() as conn:
        conn.execute(
            "DELETE FROM colecao_favoritas WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        )


def eh_favorita(guild_id, user_id, personagem_id):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT 1 FROM colecao_favoritas WHERE guild_id = ? AND user_id = ? AND personagem_id = ?",
            (str(guild_id), str(user_id), personagem_id),
        ).fetchone()
    return linha is not None




# --------------------------------------------------------------------------
# Cards de reação pendentes (2026-08-29) - persistido, sobrevive a um
# restart do processo (antes vivia só em `gacha._CARDS_REACAO_PENDENTES`,
# em memória). `_limpar_cards_expirados` é chamada de dentro das outras
# funções aqui - reset PREGUIÇOSO, mesmo padrão de sempre no ERIS (nenhum
# job/cron varrendo a tabela sozinho).
# --------------------------------------------------------------------------

def registrar_card_pendente(guild_id, message_id, personagem_id, emoji, expira_em_iso):
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_cards_pendentes (message_id, guild_id, personagem_id, emoji, expira_em) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(message_id) DO UPDATE SET expira_em = excluded.expira_em",
            (str(message_id), str(guild_id), personagem_id, emoji, expira_em_iso),
        )


def _limpar_cards_expirados(conn, agora_iso):
    conn.execute("DELETE FROM colecao_cards_pendentes WHERE expira_em <= ?", (agora_iso,))


def card_pendente_por_mensagem(message_id):
    """Usado por `gacha.processar_reacao_claim` - devolve {"guild_id",
    "personagem_id", "emoji", "expira_em"} ou None (nunca existiu, já foi
    reivindicado, ou expirou - os 3 casos tratados como "ignora essa
    reação", igual o comportamento antigo em memória)."""
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        _limpar_cards_expirados(conn, agora)
        linha = conn.execute(
            "SELECT guild_id, personagem_id, emoji, expira_em FROM colecao_cards_pendentes WHERE message_id = ?",
            (str(message_id),),
        ).fetchone()
    return dict(linha) if linha else None


def remover_card_pendente(message_id):
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
# Party e Vitrine - até 5 posições cada, mesma tabela (`tipo` distingue,
# Seções 15/17). Party ainda não tem Torre pra jogar, mas já protege contra
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
CUSTO_TREINAMENTO_GLOBAL_POR_NIVEL = 50
CUSTO_POTENCIAL_COLECAO_POR_NIVEL = 100
# 🔥 Marcos de coleção única (Seção 11 - "não deve ser a principal fonte
# infinita de CP", só milestone pontual). XP = marco × 10 (100
# personagens -> 1.000 XP, 1.000 -> 10.000 XP).
MARCOS_COLECAO = (100, 200, 500, 1000, 2000, 5000, 10000)


def xp_necessario_nivel(nivel):
    """XP pra sair de `nivel` pro próximo - geométrico, mesmo estilo de
    `torre.power_alvo_andar` (número novo, a análise autoriza "valores
    exatos podem ser balanceados posteriormente")."""
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


def creditar_xp_progressao(guild_id, user_id, quantidade):
    """Credita XP de Progressão (Seção 3/4) - sobe de Nível em CASCATA se
    a quantidade creditada de uma vez ultrapassar mais de 1 limiar (ex.:
    um marco de coleção grande de uma vez). NUNCA é moeda - só preenche a
    barra. Devolve (nivel_novo, xp_novo, subiu_de_nivel: bool)."""
    estado = progressao_conta(guild_id, user_id)
    if quantidade <= 0:
        return estado["nivel"], estado["xp"], False
    nivel, xp = estado["nivel"], estado["xp"] + quantidade
    subiu = False
    while xp >= xp_necessario_nivel(nivel):
        xp -= xp_necessario_nivel(nivel)
        nivel += 1
        subiu = True
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_progressao (guild_id, user_id, nivel, xp) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel = excluded.nivel, xp = excluded.xp",
            (str(guild_id), str(user_id), nivel, xp),
        )
    return nivel, xp, subiu


def bonus_cp_global(guild_id, user_id):
    """(bonus_fixo, bonus_percentual) da Progressão Global - `pandora.
    torre.power_personagem` é o ÚNICO ponto que aplica isso (`(CP +
    bonus_fixo) × (1 + bonus_percentual)`, Seção 8), então todo Power
    calculado no pacote já sai com o bônus embutido sem precisar mudar
    mais nenhum outro lugar. `bonus_percentual` já vem pronto pra
    multiplicar (0,04 = +4%, não "4")."""
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


# 🔥 Bônus por CLASSE (2026-08-30, pedido do usuário: "a cada 50
# personagens da classe ganho +500 bonus p todos daquela classe na
# torre" - depois revisado pro mesmo RATIO com granularidade menor: "a cd
# 5 aumenta 50", 50/5 = 10 CP por personagem no marco, igual 500/50) -
# incentiva colecionar VÁRIAS da MESMA classe (taxonomia ABERTA, não a
# categoria/função fechada) - toda personagem daquela classe ganha o
# bônus, não só as que estão na Party/Torre.
MARCO_QUANTIDADE_CLASSE = 5
BONUS_POR_MARCO_CLASSE = 50


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
    return (quantidade // MARCO_QUANTIDADE_CLASSE) * BONUS_POR_MARCO_CLASSE


def custo_treinamento_global(nivel_alvo):
    return CUSTO_TREINAMENTO_GLOBAL_POR_NIVEL * nivel_alvo


def custo_total_treinamento_ate(nivel_atual, nivel_alvo):
    """Soma o custo de CADA nível de `nivel_atual` até `nivel_alvo`
    (2026-08-30, pedido do usuário: "na loja, qnd vou fazer treinamento
    global... tbm tem de permitr comprar varios leveis por vez" - mesmo
    padrão de `custo_total_ate_nivel`) - 0 se `nivel_alvo` não for maior
    que o atual."""
    if nivel_alvo <= nivel_atual:
        return 0
    return sum(custo_treinamento_global(n) for n in range(nivel_atual + 1, nivel_alvo + 1))


def comprar_treinamento_global_ate(guild_id, user_id, nivel_alvo):
    """+CP FIXO por personagem, pra sempre, SEM nível máximo (Seção 7) -
    pula DIRETO pro `nivel_alvo` (2026-08-30, substitui o antigo "+1 por
    clique" - dropdown escolhe o alvo, custo é a soma de todos os
    degraus, mesmo padrão de `subir_nivel_ate`)."""
    nivel_atual = progressao_conta(guild_id, user_id)["nivel_treinamento_global"]
    if nivel_alvo <= nivel_atual:
        return False, f"Treinamento Global já está no Nível {nivel_atual} ou acima."
    custo = custo_total_treinamento_ate(nivel_atual, nivel_alvo)
    if saldo_wishards(guild_id, user_id) < custo:
        return False, f"Custa {custo} WiShards e você não tem o suficiente."
    creditar_wishards(guild_id, user_id, -custo, "treinamento_global", f"nível {nivel_atual}->{nivel_alvo}")
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_progressao (guild_id, user_id, nivel_treinamento_global) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel_treinamento_global = excluded.nivel_treinamento_global",
            (str(guild_id), str(user_id), nivel_alvo),
        )
    bonus_total = nivel_alvo * BONUS_FIXO_POR_NIVEL_TREINAMENTO
    return True, f"Treinamento Global Nv.{nivel_alvo}! +{bonus_total} CP fixo por personagem, pra sempre (custou {custo} WiShards)."


def custo_potencial_colecao(nivel_alvo):
    return CUSTO_POTENCIAL_COLECAO_POR_NIVEL * nivel_alvo


def custo_total_potencial_ate(nivel_atual, nivel_alvo):
    """Soma o custo de CADA nível de `nivel_atual` até `nivel_alvo` (mesmo
    padrão de `custo_total_treinamento_ate`) - 0 se `nivel_alvo` não for
    maior que o atual."""
    if nivel_alvo <= nivel_atual:
        return 0
    return sum(custo_potencial_colecao(n) for n in range(nivel_atual + 1, nivel_alvo + 1))


def comprar_potencial_colecao_ate(guild_id, user_id, nivel_alvo):
    """+CP PERCENTUAL global, pra sempre, SEM nível máximo (Seção 7) -
    custo cresce mais rápido que o Treinamento Global de propósito ("a
    eficiência cresce junto com o CP total"). Pula DIRETO pro `nivel_alvo`
    (2026-08-30, mesmo padrão de `comprar_treinamento_global_ate`)."""
    nivel_atual = progressao_conta(guild_id, user_id)["nivel_potencial_colecao"]
    if nivel_alvo <= nivel_atual:
        return False, f"Potencial da Coleção já está no Nível {nivel_atual} ou acima."
    custo = custo_total_potencial_ate(nivel_atual, nivel_alvo)
    if saldo_wishards(guild_id, user_id) < custo:
        return False, f"Custa {custo} WiShards e você não tem o suficiente."
    creditar_wishards(guild_id, user_id, -custo, "potencial_colecao", f"nível {nivel_atual}->{nivel_alvo}")
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_progressao (guild_id, user_id, nivel_potencial_colecao) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel_potencial_colecao = excluded.nivel_potencial_colecao",
            (str(guild_id), str(user_id), nivel_alvo),
        )
    bonus_total = nivel_alvo * BONUS_PERCENTUAL_POR_NIVEL_POTENCIAL
    return True, f"Potencial da Coleção Nv.{nivel_alvo}! +{bonus_total}% CP global, pra sempre (custou {custo} WiShards)."


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
    contagem, por exemplo)."""
    total = len(colecao_do_usuario(guild_id, user_id))
    ja_pago = maior_marco_colecao_atingido(guild_id, user_id)
    novos = [m for m in MARCOS_COLECAO if ja_pago < m <= total]
    if not novos:
        return []
    for marco in novos:
        creditar_xp_progressao(guild_id, user_id, marco * 10)
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
    guild_id, user_id, momento, cp_bonus_militar_fixo=0.0, cp_bonus_arcano_percentual=0.0, cp_bonus_colecao_fixo=0.0,
):
    """Grava o relógio da Cidade JUNTO com o snapshot de bônus de CP pra
    Party (2026-08-30, Cidade v2 - efeitos diferenciados por área) - os 2
    sempre mudam juntos (mesma visita ao painel "🏙️ Cidade",
    `pandora.cidade.coletar_producao_pendente`), nunca precisam de 2
    `UPDATE`s separados na mesma linha."""
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_cidade_estado ("
            "guild_id, user_id, ultima_producao_em, cp_bonus_militar_fixo, cp_bonus_arcano_percentual, cp_bonus_colecao_fixo"
            ") VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
            "ultima_producao_em = excluded.ultima_producao_em, "
            "cp_bonus_militar_fixo = excluded.cp_bonus_militar_fixo, "
            "cp_bonus_arcano_percentual = excluded.cp_bonus_arcano_percentual, "
            "cp_bonus_colecao_fixo = excluded.cp_bonus_colecao_fixo",
            (
                str(guild_id), str(user_id), momento.isoformat(),
                cp_bonus_militar_fixo, cp_bonus_arcano_percentual, cp_bonus_colecao_fixo,
            ),
        )


def cidade_bonus_party(guild_id, user_id):
    """(bonus_militar_fixo, bonus_arcano_percentual, bonus_colecao_fixo) -
    snapshot já calculado (Administração já multiplicada dentro dos 2
    primeiros) - `pandora.torre.calcular_power_party` só LÊ isso, nunca
    recalcula a partir da coleção inteira (ver `pandora.cidade`).
    (0.0, 0.0, 0.0) se a Cidade nunca foi visitada ainda."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT cp_bonus_militar_fixo, cp_bonus_arcano_percentual, cp_bonus_colecao_fixo "
            "FROM colecao_cidade_estado WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
    if linha is None:
        return 0.0, 0.0, 0.0
    return linha["cp_bonus_militar_fixo"], linha["cp_bonus_arcano_percentual"], linha["cp_bonus_colecao_fixo"]


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


# --------------------------------------------------------------------------
# Upgrade permanente de rolls máximos (Seção 11) - único upgrade do plano
# com preços concretos; os outros ("ampliar wishlist", "claims
# armazenáveis", bônus de divórcio/reencontro/terceiro, desconto de loja,
# "wishlist luck", rerolls, slots de vitrine extras) ficaram sem número no
# plano ("valores ficam para balanceamento") - não implementados ainda.
# --------------------------------------------------------------------------

PRECOS_UPGRADE_ROLLS = {1: 1000, 2: 2500, 3: 5000, 4: 10000, 5: 25000}
BONUS_ROLLS_POR_NIVEL = 5
NIVEL_MAXIMO_UPGRADE_ROLLS = 5


def nivel_upgrade_rolls(guild_id, user_id):
    with conexao() as conn:
        linha = _estado_jogador(conn, guild_id, user_id)
    return linha["nivel_upgrade_rolls"] if linha else 0


def comprar_upgrade_rolls(guild_id, user_id):
    """Devolve (ok: bool, mensagem: str). Nível N custa `PRECOS_UPGRADE_
    ROLLS[N]` e soma +5 rolls PERMANENTES em cima do `rolls_por_ciclo` do
    servidor (nunca substitui a config do servidor, só soma)."""
    nivel_atual = nivel_upgrade_rolls(guild_id, user_id)
    if nivel_atual >= NIVEL_MAXIMO_UPGRADE_ROLLS:
        return False, "Você já está no nível máximo desse upgrade."
    proximo_nivel = nivel_atual + 1
    preco = PRECOS_UPGRADE_ROLLS[proximo_nivel]
    if saldo_wishards(guild_id, user_id) < preco:
        return False, f"Custa {preco} WiShards e você não tem o suficiente."

    creditar_wishards(guild_id, user_id, -preco, "upgrade_rolls", f"nivel {proximo_nivel}")
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_estado_jogador ("
            "guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em, nivel_upgrade_rolls"
            ") VALUES (?, ?, 0, ?, 1, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel_upgrade_rolls = excluded.nivel_upgrade_rolls",
            (str(guild_id), str(user_id), agora, agora, proximo_nivel),
        )
    bonus_total = proximo_nivel * BONUS_ROLLS_POR_NIVEL
    return True, f"Upgrade de rolls nível {proximo_nivel}! +{bonus_total} rolls por ciclo, pra sempre (custou {preco} WiShards)."


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
NIVEL_MAXIMO_UPGRADE_CLAIMS = 5


def nivel_upgrade_claims(guild_id, user_id):
    with conexao() as conn:
        linha = _estado_jogador(conn, guild_id, user_id)
    return linha["nivel_upgrade_claims"] if linha else 0


def comprar_upgrade_claims(guild_id, user_id):
    """Devolve (ok: bool, mensagem: str). Nível N custa `PRECOS_UPGRADE_
    CLAIMS[N]` e soma +1 claim PERMANENTE em cima do `claims_por_ciclo` do
    servidor (nunca substitui a config do servidor, só soma) - mesmo
    padrão de `comprar_upgrade_rolls`."""
    nivel_atual = nivel_upgrade_claims(guild_id, user_id)
    if nivel_atual >= NIVEL_MAXIMO_UPGRADE_CLAIMS:
        return False, "Você já está no nível máximo desse upgrade."
    proximo_nivel = nivel_atual + 1
    preco = PRECOS_UPGRADE_CLAIMS[proximo_nivel]
    if saldo_wishards(guild_id, user_id) < preco:
        return False, f"Custa {preco} WiShards e você não tem o suficiente."

    creditar_wishards(guild_id, user_id, -preco, "upgrade_claims", f"nivel {proximo_nivel}")
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_estado_jogador ("
            "guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em, nivel_upgrade_claims"
            ") VALUES (?, ?, 0, ?, 1, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel_upgrade_claims = excluded.nivel_upgrade_claims",
            (str(guild_id), str(user_id), agora, agora, proximo_nivel),
        )
    bonus_total = proximo_nivel * BONUS_CLAIMS_POR_NIVEL
    return True, f"Upgrade de claims nível {proximo_nivel}! +{bonus_total} claim(s) por ciclo, pra sempre (custou {preco} WiShards)."
