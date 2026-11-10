# -*- coding: utf-8 -*-
"""Persistência do Colecionador (gacha estilo Mudae) via SQLite (`sqlite3` da
stdlib, sem dependência nova) - EXTRAÍDO do Project-ERIS em 2026-08-29 (era
`eris/db.py`, banco `data/eris.db` - ver `eris.config`/histórico completo em
`CHANGELOG.md`/`docs/ARQUITETURA.md` do ERIS). Banco PRÓPRIO (`data/pandora.db`,
`pandora.config.CAMINHO_BANCO`) - não compartilha arquivo com o `eris.db`
(que ficou só com o núcleo do bot: donos/roteamento/auditoria/cache de
guilds). Ver "Extraído do Project-ERIS" em `docs/ARQUITETURA.md` deste repo pro
motivo da extração (biblioteca Python local, sem processo/HTTP próprio -
diferente do padrão MOIRAI/ECHO - decisão explícita: todo clique de roll/
claim/troca cai no orçamento de 3s do Discord, um satélite HTTP colocaria
uma chamada de rede em cima de CADA clique)."""
import os
import functools
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pandora.config import CAMINHO_BANCO, PASTA_DADOS


_SUFIXOS_FIXOS = ("", "K", "M", "B", "T", "Q")


def _rotulo_letras_abreviacao(indice):
    """Rótulo de 2+ letras estilo "coluna de planilha" (A,B,...Z,AA,AB,...),
    mas começando DIRETO em 2 letras (`indice` 0 -> "AA", 25 -> "AZ", 26 ->
    "BA", ...) - `_sufixo_abreviado` já soma o deslocamento de 26 antes de
    chamar isso, pra pular a faixa de 1 letra (A-Z) inteira. Bijetivo em
    base 26 (nunca "estoura" - continua gerando AAA/AAB/... sozinho se um
    número um dia for grande o bastante pra passar de "ZZ", sem precisar
    de nenhum código novo)."""
    indice += 1
    letras = []
    while indice > 0:
        indice, resto = divmod(indice - 1, 26)
        letras.append(chr(ord("A") + resto))
    return "".join(reversed(letras))


def _sufixo_abreviado(tier):
    """`tier` 0 = sem sufixo, 1=K, 2=M, 3=B, 4=T, 5=Q, 6=AA, 7=AB, ..., 31=AZ,
    32=BA, ... (2026-09-03, pedido do usuário: "K → M → B → T → Q → AA →
    AB → AC... → AZ → BA → BB..., avançando um sufixo a cada ×1.000")."""
    if tier < len(_SUFIXOS_FIXOS):
        return _SUFIXOS_FIXOS[tier]
    return _rotulo_letras_abreviacao(tier - len(_SUFIXOS_FIXOS) + 26)


def fmt_numero(valor, casas_decimais=1):
    """Formato abreviado ÚNICO pra todo número grande do PANDORA (2026-09-03,
    pedido do usuário: "Altere a exibição global de números grandes do
    PANDORA para um formato abreviado e consistente... centralize essa
    lógica em uma única função de formatação para que Power/CP, WiShards,
    Soulstones, XP, preços, produção e demais números... sigam exatamente o
    mesmo padrão" - substitui o formato anterior de milhar com ponto,
    `1.234.567`, usado só nesta mesma sessão antes). Sobe 1 tier a cada
    ×1000 (`_sufixo_abreviado`); `casas_decimais` é o MÁXIMO de casas (1 por
    padrão - "quero apenas 1 casa decimal", reduzido de 2) - zeros à
    direita SEMPRE removidos (1,5M continua 1,5M; 2,0B -> 2B; 500,0 -> 500,
    já que valores abaixo de 1000/tier 0 também passam pelo mesmo corte,
    "e se for 0 pode desconsiderar"). Uma chamada com `casas_decimais`
    menor continua funcionando igual - é só um teto mais apertado, nunca
    força casas que não existem."""
    negativo = valor < 0
    valor = abs(valor)
    tier = 0
    while valor >= 1000:
        valor /= 1000.0
        tier += 1
    # 🔥 Correção de borda (2026-09-03, achado testando 999999) - um valor
    # tipo 999.999 (tier K) ARREDONDA pra 1000,00 na hora de exibir com
    # `casas_decimais` casas, o que sairia "1000K" (4 dígitos antes do
    # sufixo, quebra a promessa de número sempre CURTO da abreviação) -
    # sobe mais 1 tier nesse caso (1000K -> 1M), padrão comum em qualquer
    # abreviação de número (jogos/planilhas).
    if round(valor, casas_decimais) >= 1000:
        valor /= 1000.0
        tier += 1
    texto = f"{valor:.{casas_decimais}f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    texto = texto.replace(".", ",") + _sufixo_abreviado(tier)
    return f"-{texto}" if negativo else texto


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
    duracao_card_segundos INTEGER NOT NULL DEFAULT 900,
    max_rolls_por_comando INTEGER NOT NULL DEFAULT 10,
    chance_wish_roll REAL NOT NULL DEFAULT 0.20,
    teto_bonus_rolls_progressao INTEGER NOT NULL DEFAULT 100,
    teto_bonus_claims_progressao INTEGER NOT NULL DEFAULT 10
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

-- Busca por personagem em qualquer servidor (fila do catálogo não adquirido,
-- `NOT EXISTS ... WHERE c.personagem_id = p.id`): sem este índice a PK
-- (guild_id, personagem_id) não serve e a contagem levava 16s (2026-10-14).
CREATE INDEX IF NOT EXISTS idx_colecao_propriedade_personagem ON colecao_propriedade (personagem_id);

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
-- docs/ARQUITETURA.md) - tudo é revalidado (dono ainda é dono, saldo ainda
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
-- 🔥 PK composta (2026-09-01, favoritar/trocar direto do roll: "emoji pra
-- favoritar personagem qnd aparece no roll, outro emoji que coleta mas
-- coloca tag trade") - cada mensagem de roll agora tem ATÉ 3 reações
-- válidas (claim normal/claim+favoritar/claim+tag "trade"), cada uma sua
-- própria linha aqui (mesmo `personagem_id`, `acao` diferente). Migração
-- de ruptura em `inicializar()` (tabela antiga tinha PK só em `message_id`
-- e não tinha `acao`) - aceitável porque toda linha aqui é EFÊMERA
-- (expira em minutos), nunca dado de economia/coleção de verdade.
CREATE TABLE IF NOT EXISTS colecao_cards_pendentes (
    message_id TEXT NOT NULL,
    emoji TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    personagem_id INTEGER NOT NULL,
    acao TEXT NOT NULL DEFAULT 'claim',
    expira_em TEXT NOT NULL,
    PRIMARY KEY (message_id, emoji)
);

CREATE INDEX IF NOT EXISTS idx_cards_pendentes_guild ON colecao_cards_pendentes (guild_id, expira_em);

-- Tags pessoais por personagem (2026-09-01, pedido do usuário: "outro
-- emoji que coleta mas coloca tag trade, permitir filtrar por tag
-- depois") - "trade" é a 1ª tag usada (reação 🔄 no roll), mas o campo é
-- LIVRE (qualquer texto) pra não precisar migrar schema de novo se surgir
-- outra tag no futuro. NUNCA confundir com `colecao_personagens.tags`
-- (metadado do CATÁLOGO, importado da fonte externa) - esta aqui é do
-- VÍNCULO jogador+personagem, mesmo escopo de `colecao_favoritas`.
CREATE TABLE IF NOT EXISTS colecao_tags (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    personagem_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, personagem_id, tag)
);

-- Batalha 5x5 com Aposta de Personagem (2026-09-01, spec completa do
-- usuário - ver `pandora/batalha.py`) - 1 linha por desafio, estado 100%
-- aqui (nunca em memória do processo) pra sobreviver a um restart do bot
-- no meio de um desafio sem perder WiShards nem travar ninguém. `ordem_*`
-- é a Party CONGELADA do jogador no momento em que ele fecha aquele lado
-- (JSON, lista de personagem_id em ordem de posição 1..5) - a ordem em si
-- é o que o documento chama de "secreta" (Seção 7), nunca muda depois de
-- congelada. `status`: aguardando_defensor -> em_andamento (as 2 ordens já
-- fechadas, mas ainda não resolvido - só existe internamente, o resolver
-- roda tudo synchronous) -> concluida/cancelada (terminais). 🔥 Morte
-- Súbita REMOVIDA (2026-09-02, pedido do usuário - ver `batalha.
-- resolver_rodadas`) - status 'morte_subita' e as 2 colunas `escolha_
-- morte_subita_*` abaixo ficam ÓRFÃS de propósito (nunca mais escritas,
-- mesmo padrão de outras colunas órfãs já aceitas no ecossistema - não
-- vale a pena uma migração destrutiva só pra limpar isso agora).
CREATE TABLE IF NOT EXISTS colecao_batalha_desafios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    canal_id TEXT,
    desafiante_id TEXT NOT NULL,
    defensor_id TEXT NOT NULL,
    personagem_id INTEGER NOT NULL,
    aposta_wishards INTEGER NOT NULL,
    ordem_desafiante TEXT NOT NULL,
    ordem_defensor TEXT,
    placar_desafiante INTEGER NOT NULL DEFAULT 0,
    placar_defensor INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'aguardando_defensor',
    escolha_morte_subita_desafiante TEXT,
    escolha_morte_subita_defensor TEXT,
    criado_em TEXT NOT NULL,
    resolvido_em TEXT
);

CREATE INDEX IF NOT EXISTS idx_batalha_desafios_guild_status ON colecao_batalha_desafios (guild_id, status);

-- Cooldown por PAR desafiante->defensor (Seção 15: "24h pra desafiá-lo de
-- novo") - evita perseguição do mesmo alvo em sequência.
CREATE TABLE IF NOT EXISTS colecao_batalha_cooldown (
    guild_id TEXT NOT NULL,
    desafiante_id TEXT NOT NULL,
    defensor_id TEXT NOT NULL,
    ultimo_desafio_em TEXT NOT NULL,
    PRIMARY KEY (guild_id, desafiante_id, defensor_id)
);

-- Limite de desafios RECEBIDOS por dia, por defensor (Seção 15: "máximo de
-- 3 desafios recebidos por jogador por dia") - conta QUALQUER desafiante,
-- reseta sozinho por `data` (YYYY-MM-DD UTC) mudar, sem job nenhum.
CREATE TABLE IF NOT EXISTS colecao_batalha_defesas_hoje (
    guild_id TEXT NOT NULL,
    defensor_id TEXT NOT NULL,
    data TEXT NOT NULL,
    quantidade INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, defensor_id, data)
);

-- World Boss: evento cooperativo (2026-09-01, spec completa do usuário -
-- ver `pandora/worldboss.py`) - 1 linha por aparição do Boss, POR guild.
-- `estado_mecanica` (JSON) guarda o estado PRÓPRIO de cada mecânica
-- especial (turnos de Enfurecer já passados, HP da Barreira, cabeças
-- vivas da Hidra, renascimentos da Fênix, etc.) - cada mecânica só lê/
-- escreve as chaves que usa, o motor genérico nunca olha pra dentro.
-- `status`: inscricoes -> em_combate -> vitoria/derrota/expirado_por_turnos
-- (terminais). `proximo_turno_em`/`inscricoes_fecham_em` são os ÚNICOS
-- "relógios" que o scheduler (`pandora.worldboss.SchedulerWorldBoss`)
-- confere a cada tick de 30s - todo o resto é derivado do banco, sem
-- estado em memória do processo (restart-safe, mesmo espírito da Batalha
-- 5x5 - um World Boss em andamento não pode travar nem "sumir" se o bot
-- reiniciar no meio de um turno).
CREATE TABLE IF NOT EXISTS colecao_worldboss_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    canal_id TEXT,
    boss_tipo TEXT NOT NULL,
    boss_hp_maximo REAL NOT NULL,
    boss_hp_atual REAL NOT NULL,
    boss_atk_base REAL NOT NULL,
    boss_atk_atual REAL NOT NULL,
    estado_mecanica TEXT NOT NULL DEFAULT '{}',
    time_hp_maximo REAL,
    time_hp_atual REAL,
    time_dano_turno REAL,
    time_cura_turno REAL,
    turno_atual INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'inscricoes',
    dificuldade TEXT,
    cp_recomendado REAL,
    criado_em TEXT NOT NULL,
    inscricoes_fecham_em TEXT NOT NULL,
    proximo_turno_em TEXT,
    concluido_em TEXT
);

CREATE INDEX IF NOT EXISTS idx_worldboss_eventos_guild_status ON colecao_worldboss_eventos (guild_id, status);

-- 1 personagem por (evento, jogador) - Seção 6: trocar de categoria
-- SUBSTITUI a linha (`ON CONFLICT` faz upsert), nunca acumula 2. `origem`
-- ("manual"/"automatica"/"bot", Seção 8/11) é só informativo, não muda a
-- mecânica. `categorias_selecionadas` (JSON, ex.: '["DPS","Support"]') é o
-- CONJUNTO de categorias que o jogador permitiu (Seção 5) - `personagem_
-- id`/`categoria`/`cp` são sempre recalculados a partir desse conjunto
-- (a personagem de maior CP entre as categorias permitidas), nunca
-- editados diretamente. `personagem_id` NULO só pra `origem='bot'`
-- (2026-09-01, pedido do usuário: "o CP dos bots vai ser a media dos
-- players participante" - bot não tem personagem de verdade, `user_id`
-- sintético "bot:1"/"bot:2", nunca um snowflake real do Discord).
CREATE TABLE IF NOT EXISTS colecao_worldboss_participantes (
    evento_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    personagem_id INTEGER,
    categoria TEXT NOT NULL,
    categorias_selecionadas TEXT NOT NULL,
    cp REAL NOT NULL,
    origem TEXT NOT NULL DEFAULT 'manual',
    entrou_em TEXT NOT NULL,
    PRIMARY KEY (evento_id, user_id)
);

-- Preferência de Entrada Automática por jogador (Seção 8/9) - só usada
-- DEPOIS que as inscrições manuais encerram (Seção 10), pra quem não
-- entrou manualmente nesse evento.
CREATE TABLE IF NOT EXISTS colecao_worldboss_auto (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 0,
    categorias TEXT NOT NULL DEFAULT '["DPS","Tank","Support"]',
    PRIMARY KEY (guild_id, user_id)
);

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

-- Ledger de XP de Progressão (2026-09-07, pedido do usuário: "traz um
-- botao de progressao, mostrando as fontes de xp acumaladas ate entao") -
-- mesma estrutura do ledger de WiShards/Soulstone (`colecao_wishards_
-- ledger`/`colecao_soulstone_ledger` acima) - só criado agora, então só
-- soma XP creditado a PARTIR de hoje pra frente (XP de antes desta tabela
-- existir não tem como ser atribuído a uma origem retroativamente).
CREATE TABLE IF NOT EXISTS colecao_xp_progressao_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    quantidade INTEGER NOT NULL,
    origem TEXT NOT NULL,
    motivo TEXT,
    referencia TEXT,
    nivel_resultante INTEGER NOT NULL,
    criado_em TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_colecao_xp_progressao_ledger_usuario ON colecao_xp_progressao_ledger (guild_id, user_id);

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
    bonus_colecao_loot_percentual REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

-- Histórico de produção da Cidade (2026-09-06, pedido do usuário: "meu
-- farm ta sempre aumentando, seria ate bom manter uns logs disso p vc ter
-- controle e dar sugestoes no futuro" - qualquer decisão de balance
-- (preço de upgrade, etc.) baseada num ÚNICO snapshot do momento fica
-- velha rápido demais numa economia que escala tão rápido; 1 ponto por
-- visita à Cidade (throttlado, ver `db.registrar_producao_historico`) dá
-- dado real de TENDÊNCIA ao longo do tempo, não só "quanto produz hoje".
-- Guild-scoped (mesmo critério de tudo mais - cada servidor é uma
-- progressão independente).
CREATE TABLE IF NOT EXISTS colecao_producao_historico (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    registrado_em TEXT NOT NULL,
    wishards_por_hora REAL NOT NULL,
    soulstone_por_hora REAL NOT NULL,
    xp_por_hora REAL NOT NULL,
    cp_total REAL NOT NULL,
    nivel_progressao INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_producao_historico ON colecao_producao_historico (guild_id, user_id, registrado_em);

-- World Boss: Recompensas e Conquistas (2026-09-01, spec completa do
-- usuário - ver `pandora/conquistas.py`/`pandora/itens.py`) - Conquistas
-- são um registro PURO (Seção 15: "não concedem WiShards/XP/Soulstones/
-- itens/personagens/bônus"), guild-scoped (mesmo critério de tudo mais no
-- ecossistema - cada servidor é uma progressão independente).
CREATE TABLE IF NOT EXISTS colecao_conquistas (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    conquista_id TEXT NOT NULL,
    desbloqueada_em TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, conquista_id)
);

-- Inventário genérico de itens consumíveis (Seção 6 do documento de
-- recompensas - Proteção/Revanche/Chave da Torre/Upgrade de Construção/
-- Chamado/Roll Permanente/Claim Permanente). `item` é a chave do
-- catálogo fechado em `pandora.itens.CATALOGO_ITENS`.
CREATE TABLE IF NOT EXISTS colecao_inventario (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    item TEXT NOT NULL,
    quantidade INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, item)
);

-- 🔥 Contador VITALÍCIO de compras por item na Loja (2026-09-03, pedido do
-- usuário: "Todos os itens da loja tem q aumentar o preço a medida q são
-- compradas") - separado de `colecao_inventario.quantidade` de propósito:
-- o inventário CAI quando o item é usado/consumido, mas o preço tem que
-- continuar subindo mesmo depois de gasto - nunca decrementado.
CREATE TABLE IF NOT EXISTS colecao_compras_item (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    item TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, item)
);

-- 🛡️ Proteção (Seção 7) aplicada - permanente até o jogador remover (sem
-- prazo definido na spec, "balanceável depois") - mesmo espírito de
-- `colecao_favoritas`, mas voltada pra proteção contra a Batalha 5x5
-- especificamente (`pandora.batalha.iniciar_desafio` confere isso).
CREATE TABLE IF NOT EXISTS colecao_protecao_pvp (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    personagem_id INTEGER NOT NULL,
    aplicada_em TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, personagem_id)
);

-- ⚔️ Revanche (Seção 8) - registra toda personagem PERDIDA via Batalha
-- 5x5 (`jogador_perdedor_id` é quem tinha antes) - usar uma Revanche
-- contra essa linha ignora cooldown/limite diário normais do desafio
-- (Seção 8: "ainda precisa disputar através das regras da batalha" -
-- só a RESTRIÇÃO de frequência é ignorada, não o combate em si).
-- `recuperada` só vira 1 quando o jogador original vence de volta.
CREATE TABLE IF NOT EXISTS colecao_batalha_personagens_perdidas (
    guild_id TEXT NOT NULL,
    personagem_id INTEGER NOT NULL,
    jogador_perdedor_id TEXT NOT NULL,
    perdida_em TEXT NOT NULL,
    recuperada INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, personagem_id, jogador_perdedor_id)
);

-- 🗝️ Chave da Torre (Seção 9) - flag de "próxima tentativa de andar
-- ignora a restrição" (consumida no próximo `torre.tentar_andar`,
-- vença ou perca - a Chave paga pela TENTATIVA sem restrição, não pela
-- vitória).
CREATE TABLE IF NOT EXISTS colecao_torre_chave_ativa (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    ativa INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

-- 🏗️ Upgrade de Construção (Seção 10) - nível permanente por área da
-- Cidade, por jogador - cada nível aumenta o efeito daquela área
-- (`pandora.cidade` aplica o bônus na conversão de Poder).
CREATE TABLE IF NOT EXISTS colecao_construcoes (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    area TEXT NOT NULL,
    nivel INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, area)
);

-- 📯 Chamado (Seção 11) - escolhe o Boss do PRÓXIMO horário fixo desse
-- servidor (não cria evento extra) - `pandora.worldboss.iniciar_evento`
-- confere e consome isso antes de sortear aleatoriamente.
CREATE TABLE IF NOT EXISTS colecao_worldboss_proximo_forcado (
    guild_id TEXT PRIMARY KEY,
    boss_tipo TEXT NOT NULL
);

-- Estatística de participação com sucesso na Torre, por personagem
-- (2026-09-01, pedido do usuário: "estatísticas de participação com
-- sucesso na torre por personagens, p saber quais personagens mais
-- subiram torre") - incrementado 1x por personagem TODA VEZ que a Party
-- dela vence um andar (`torre.tentar_andar`), nunca em tentativas
-- perdidas (só "participação com SUCESSO").
CREATE TABLE IF NOT EXISTS colecao_torre_estatisticas (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    personagem_id INTEGER NOT NULL,
    andares_vencidos INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, personagem_id)
);

-- Séries Favoritas (2026-09-02, `pandora.series_favoritas`) - até
-- `SLOTS_MAXIMO` slots por jogador (5 base + upgrades pagos), cada um
-- guardando a série ESCOLHIDA nesse slot. A linha só existe depois do
-- slot ser usado 1x - "vazio" (nunca usado) é AUSÊNCIA de linha, o que
-- permite a 1ª escolha ser instantânea; depois disso a linha nunca é
-- apagada (só `serie` vira NULL pra "esvaziar"), porque `bloqueado_ate`
-- precisa sobreviver pra impedir trocar de novo antes do cooldown -
-- devolver ao estado "nunca usado" reabriria a brecha de trocar toda hora
-- sem esperar.
CREATE TABLE IF NOT EXISTS colecao_series_favoritas (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    slot INTEGER NOT NULL,
    serie TEXT,
    trocado_em TEXT NOT NULL,
    bloqueado_ate TEXT,
    PRIMARY KEY (guild_id, user_id, slot)
);

-- Snapshot do bônus de CP por Série Favorita (2026-09-02) - CARO calcular
-- (precisa saber, pra cada série favoritada, se a coleção/nível/soulbond
-- daquela série estão completos - varre a coleção do jogador FILTRADA por
-- série), então nunca é recalculado no caminho quente (`torre.
-- power_personagem`/`_contexto_lote` só LEEM esta tabela) - só depois de
-- ações que mudam completude (claim/nível/afinidade/divórcio/merge/troca
-- de série favorita), mesmo padrão de `colecao_cidade_estado`/
-- `atualizar_snapshot_bonus`. 1 linha por série favoritada ATUAL - trocar
-- a série de um slot REMOVE a linha antiga (`pandora.series_favoritas.
-- recalcular_bonus` apaga o que não está mais nas favoritas do jogador).
CREATE TABLE IF NOT EXISTS colecao_series_favoritas_bonus (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    serie TEXT NOT NULL,
    bonus_percentual REAL NOT NULL DEFAULT 0,
    colecao_completa INTEGER NOT NULL DEFAULT 0,
    maestria_completa INTEGER NOT NULL DEFAULT 0,
    soulbond_completo INTEGER NOT NULL DEFAULT 0,
    atualizado_em TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, serie)
);

-- Personagens Favoritas (2026-09-03, `pandora.personagens_favoritas`) -
-- mesmo espírito de Série Favorita acima, só que a progressão (Fortalecimento/
-- Ascensão) pertence ao SLOT, não à personagem que o ocupa - trocar de
-- ocupante NUNCA reseta `fortalecimento_bitmask`/`nivel_ascensao` (pedido
-- explícito do usuário). `fortalecimento_bitmask` guarda os 14 patamares de
-- 300 a 1000 (50 em 50) como bits (bit N = patamar N comprado NESSE slot) -
-- nunca uma lista de strings, ver `pandora.personagens_favoritas.
-- PATAMARES_FORTALECIMENTO`. `nivel_ascensao` é um contador simples (sempre
-- comprado em ordem, mesmo padrão de todo "nível de upgrade" já existente).
CREATE TABLE IF NOT EXISTS colecao_personagens_favoritas (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    slot INTEGER NOT NULL,
    personagem_id INTEGER,
    fortalecimento_bitmask INTEGER NOT NULL DEFAULT 0,
    nivel_ascensao INTEGER NOT NULL DEFAULT 0,
    trocado_em TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, slot)
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
    "duracao_card_segundos": "INTEGER NOT NULL DEFAULT 900",
    "max_rolls_por_comando": "INTEGER NOT NULL DEFAULT 10",
    "chance_wish_roll": "REAL NOT NULL DEFAULT 0.20",
    # Tetos dos bônus pessoais de ações obtidos pela Progressão. A base
    # (rolls_por_ciclo/claims_por_ciclo) continua sendo configurada à parte.
    "teto_bonus_rolls_progressao": "INTEGER NOT NULL DEFAULT 100",
    "teto_bonus_claims_progressao": "INTEGER NOT NULL DEFAULT 10",
    # 🔥 Canal onde o auto-colecionador (GAIA/ERIS, ver eris/colecao/auto_
    # colecionador.py) anuncia o que reivindicou - NULL = cai no
    # `guild.system_channel` na hora (sem migração pra preencher, ver
    # `/colecao_admin canal`).
    "canal_anuncio_id": "TEXT",
    # 🔥 Cooldown de 24h entre desafios de Batalha ao MESMO jogador
    # (2026-09-02, pedido do usuário: "remove esse bloqueio... deixa ele
    # opcional e desmarcado por padrao") - era fixo/obrigatório antes;
    # virou config por servidor, DESLIGADO por padrão (`DEFAULT 0`) - um
    # admin que preferir o cooldown de volta liga via `/colecao_admin`.
    "cooldown_batalha_ativo": "INTEGER NOT NULL DEFAULT 0",
    "cooldown_batalha_horas": "INTEGER NOT NULL DEFAULT 24",
    "worldboss_ativo": "INTEGER NOT NULL DEFAULT 1",
    "worldboss_horarios": "TEXT NOT NULL DEFAULT '10,14,18,22'",
    "worldboss_inscricao_minutos": "INTEGER NOT NULL DEFAULT 10",
    "worldboss_turno_segundos": "INTEGER NOT NULL DEFAULT 60",
    "worldboss_limite_turnos": "INTEGER NOT NULL DEFAULT 60",
    "worldboss_recompensa_wishards": "INTEGER NOT NULL DEFAULT 500",
    "worldboss_recompensa_xp": "INTEGER NOT NULL DEFAULT 200",
    "worldboss_recompensa_soulstone": "INTEGER NOT NULL DEFAULT 20",
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
    "duracao_card_segundos": 900,
    "max_rolls_por_comando": 10,
    "chance_wish_roll": 0.20,
    "teto_bonus_rolls_progressao": 100,
    "teto_bonus_claims_progressao": 10,
    "canal_anuncio_id": None,
    "cooldown_batalha_ativo": False,
    "cooldown_batalha_horas": 24,
    "worldboss_ativo": True,
    "worldboss_horarios": "10,14,18,22",
    "worldboss_inscricao_minutos": 10,
    "worldboss_turno_segundos": 60,
    "worldboss_limite_turnos": 60,
    "worldboss_recompensa_wishards": 500,
    "worldboss_recompensa_xp": 200,
    "worldboss_recompensa_soulstone": 20,
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
    # `timeout` = quanto uma escrita espera outra terminar antes de falhar
    # com "database is locked" (os cliques rodam em threads diferentes via
    # `asyncio.to_thread`). O modo WAL é ligado 1x em `inicializar()`.
    conn = sqlite3.connect(CAMINHO_BANCO, timeout=ESPERA_BANCO_OCUPADO_SEGUNDOS)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


ESPERA_BANCO_OCUPADO_SEGUNDOS = 15

_travas_por_jogador = {}
_trava_do_mapa_de_travas = threading.Lock()


def serializar_por_jogador(funcao):
    """Decorador pra função `f(guild_id, user_id, ...)` que confere um
    estado e depois o altera (comprar, upar, fortalecer). Dois cliques
    simultâneos do MESMO jogador rodam um depois do outro, então o segundo
    já enxerga o saldo e o nível deixados pelo primeiro (sem isso, os dois
    liam o mesmo nível e pagavam duas vezes pelo mesmo degrau). Reentrante:
    uma função decorada pode chamar outra do mesmo jogador."""
    @functools.wraps(funcao)
    def embrulho(guild_id, user_id, *args, **kwargs):
        chave = (str(guild_id), str(user_id))
        with _trava_do_mapa_de_travas:
            trava = _travas_por_jogador.setdefault(chave, threading.RLock())
        with trava:
            return funcao(guild_id, user_id, *args, **kwargs)
    return embrulho


def _ligar_wal():
    """Modo WAL: leitura não espera escrita e vice-versa (no modo antigo,
    "delete", um clique de consulta ficava parado atrás de qualquer
    gravação). Fica gravado no próprio arquivo do banco, então basta 1x.
    Com WAL existem também `pandora.db-wal`/`-shm` ao lado do banco: pra
    copiar o banco com o bot ligado, usar `db.copia_de_seguranca`, nunca
    copiar só o `.db`."""
    conn = sqlite3.connect(CAMINHO_BANCO, timeout=ESPERA_BANCO_OCUPADO_SEGUNDOS)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    finally:
        conn.close()


def copia_de_seguranca(destino):
    """Cópia consistente do banco (API de backup do SQLite), segura com o
    bot ligado e com o modo WAL. Devolve `destino`."""
    origem = sqlite3.connect(CAMINHO_BANCO, timeout=ESPERA_BANCO_OCUPADO_SEGUNDOS)
    try:
        copia = sqlite3.connect(destino)
        try:
            origem.backup(copia)
        finally:
            copia.close()
    finally:
        origem.close()
    return destino


def inicializar():
    _garantir_pasta()
    _ligar_wal()
    with conexao() as conn:
        # 🔥 Migração de RUPTURA (2026-09-01) - `colecao_cards_pendentes`
        # trocou a PK de `message_id` sozinho pra `(message_id, emoji)`
        # (favoritar/trocar direto do roll, ver `_SCHEMA` acima) - SQLite
        # não altera PRIMARY KEY de tabela existente, então derruba a
        # tabela ANTIGA (sem a coluna `acao`) antes do `executescript`
        # recriar do zero - só descarta cards de roll ainda pendentes bem
        # no instante do deploy (efêmero, nunca economia/coleção real).
        tabelas = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "colecao_cards_pendentes" in tabelas:
            colunas_cards = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_cards_pendentes)")}
            if "acao" not in colunas_cards:
                conn.execute("DROP TABLE colecao_cards_pendentes")
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
        # 🔥 `classe_falhou` (2026-09-03, pedido do usuário: "Aumenta o
        # limite do pandora_admin validar_classes para 100, e coloca algo p
        # as q derem erro n voltarem p fila, validamos elas depois") -
        # `/pandora_admin validar_classes` reprocessava sempre as MESMAS
        # primeiras N personagens (ordenado por `p.id`) quando a GAIA
        # estava fora do ar - a fila nunca avançava. Esse flag marca quem
        # falhou (`db.marcar_falha_classificacao`) pra sair da fila padrão
        # (`personagens_possuidos_sem_classe` default já filtra
        # `classe_falhou = 0`) sem perder o registro - `apenas_falhas=True`
        # devolve exatamente essas pra uma revisão manual separada, depois.
        if "classe_falhou" not in colunas:
            conn.execute("ALTER TABLE colecao_personagens ADD COLUMN classe_falhou INTEGER NOT NULL DEFAULT 0")
        # 🔥 Prova de Soulmate (mini-game antigo, 2026-08-29) REMOVIDA em
        # 2026-09-14 - virou dead code depois que Afinidade máxima passou a
        # virar Soulmate automaticamente (`tornar_soulmate`, sem RNG/botão).
        # Migração de limpeza: descarta as colunas de texto gerado que
        # sobraram em bancos antigos (suporte a DROP COLUMN exige SQLite
        # >= 3.35, confirmado no ambiente do projeto).
        for coluna_prova in (
            "prova_soulmate_intro", "prova_soulmate_nome", "prova_soulmate_descricao",
            "prova_soulmate_situacao", "prova_soulmate_opcoes", "prova_soulmate_reacao_acerto",
            "prova_soulmate_reacao_erro", "prova_soulmate_derrota", "prova_soulmate_vitoria",
        ):
            if coluna_prova in colunas:
                conn.execute(f"ALTER TABLE colecao_personagens DROP COLUMN {coluna_prova}")

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
        # 🔥 Roll/Claim Permanente (2026-09-01, drop raro do World Boss/Loja,
        # Seção 12/13) - bônus SEPARADO do upgrade pago (`nivel_upgrade_
        # rolls`/`nivel_upgrade_claims` acima), nunca substitui, só soma.
        # `_drop` (ganho no World Boss) e `_loja` (comprado com WiShards)
        # são CONTADOS SEPARADOS (2026-09-01, pedido do usuário: "os
        # rolls/claims permanentes vendidos na loja sao contados diferentes
        # se ganhos do boss") - cada um com seu próprio teto (`pandora.
        # itens.LIMITE_ROLL_PERMANENTE`/`LIMITE_CLAIM_PERMANENTE`), então o
        # máximo combinado é o dobro de um só (5+5=10 rolls, por exemplo).
        if "bonus_rolls_permanente_drop" not in colunas_estado:
            conn.execute("ALTER TABLE colecao_estado_jogador ADD COLUMN bonus_rolls_permanente_drop INTEGER NOT NULL DEFAULT 0")
        if "bonus_claims_permanente_drop" not in colunas_estado:
            conn.execute("ALTER TABLE colecao_estado_jogador ADD COLUMN bonus_claims_permanente_drop INTEGER NOT NULL DEFAULT 0")
        if "bonus_rolls_permanente_loja" not in colunas_estado:
            conn.execute("ALTER TABLE colecao_estado_jogador ADD COLUMN bonus_rolls_permanente_loja INTEGER NOT NULL DEFAULT 0")
        if "bonus_claims_permanente_loja" not in colunas_estado:
            conn.execute("ALTER TABLE colecao_estado_jogador ADD COLUMN bonus_claims_permanente_loja INTEGER NOT NULL DEFAULT 0")
        # 🔥 Contadores VITALÍCIOS pras Conquistas do Colecionador
        # (2026-09-01, `ERIS_sistema_colecao_wishards.md` Seções 22/24,
        # excluindo Seção 23 "Conquistas musicais" - pedido do usuário:
        # "so a parte de musica que acho que n é direto com pandora") -
        # rolls/merges não deixam nenhum outro rastro histórico no banco
        # (diferente de claims/trocas, deriváveis do ledger/`colecao_
        # troca_proposta`), por isso são os 2 ÚNICOS contadores novos
        # precisos - o resto de `pandora.conquistas.verificar_colecionador`
        # é tudo calculado sob demanda a partir de tabelas que já existem.
        if "total_rolls_realizados" not in colunas_estado:
            conn.execute("ALTER TABLE colecao_estado_jogador ADD COLUMN total_rolls_realizados INTEGER NOT NULL DEFAULT 0")
        if "total_merges_realizados" not in colunas_estado:
            conn.execute("ALTER TABLE colecao_estado_jogador ADD COLUMN total_merges_realizados INTEGER NOT NULL DEFAULT 0")

        # 🔥 Recompensa Diária (2026-09-02, pedido do usuário: "recompensa
        # diária" - Seção 6/29 do plano original) - `diaria_reivindicada_em`
        # guarda só a DATA (não hora) da última reivindicação, comparada em
        # UTC - reset é por DIA DE CALENDÁRIO, não uma janela rolante de 24h
        # (diferente de rolls/claims), pra sempre poder resgatar de novo a
        # partir da meia-noite UTC, não 24h exatas depois do último clique.
        if "diaria_reivindicada_em" not in colunas_estado:
            conn.execute("ALTER TABLE colecao_estado_jogador ADD COLUMN diaria_reivindicada_em TEXT")
        # 🔥 Slots extras de Série Favorita (2026-09-02, `pandora.series_
        # favoritas`) - 5 slots base (sem custo, sem coluna) + até 5 slots
        # pagos aqui (nível 0-5), mesmo espírito do upgrade de rolls/claims.
        if "nivel_upgrade_slots_serie_favorita" not in colunas_estado:
            conn.execute("ALTER TABLE colecao_estado_jogador ADD COLUMN nivel_upgrade_slots_serie_favorita INTEGER NOT NULL DEFAULT 0")
        # 🔥 Slots extras de Personagem Favorita (2026-09-03, `pandora.
        # personagens_favoritas`) - mesmo espírito de Série Favorita acima,
        # 5 slots base (sem custo, sem coluna) + até 20 pagos aqui.
        if "nivel_upgrade_slots_personagem_favorita" not in colunas_estado:
            conn.execute("ALTER TABLE colecao_estado_jogador ADD COLUMN nivel_upgrade_slots_personagem_favorita INTEGER NOT NULL DEFAULT 0")
        # 🔥 Auto-Defesa de Batalha (2026-09-02, pedido do usuário: "É
        # possivel deixar configurado p players tbm") - jogador liga essa
        # opção pra ser defendido automaticamente na hora (mesma lógica de
        # `batalha.defesa_automatica` usada pra bots), sem precisar esperar
        # nem responder manualmente - desligado por padrão.
        if "auto_defesa_batalha_ativa" not in colunas_estado:
            conn.execute("ALTER TABLE colecao_estado_jogador ADD COLUMN auto_defesa_batalha_ativa INTEGER NOT NULL DEFAULT 0")

        # 🔥 Canal do desafio de Batalha (2026-09-02) - pra o scheduler de
        # auto-defesa (`batalha.SchedulerBatalha`) saber ONDE postar o
        # resultado de um desafio resolvido sem interação nenhuma do
        # Discord (o defensor nunca respondeu, 10min se esgotaram) -
        # `canal_id` já é coluna nova em `colecao_batalha_desafios` desde a
        # criação da tabela, então só bancos ANTIGOS (antes de hoje)
        # precisam da migração aditiva.
        colunas_batalha = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_batalha_desafios)")}
        if "canal_id" not in colunas_batalha:
            conn.execute("ALTER TABLE colecao_batalha_desafios ADD COLUMN canal_id TEXT")

        # 🔥 `is_soulmate` (2026-08-29) - status real do vínculo (2,0× de
        # multiplicador de Power, cosmético `💞`), setado direto por
        # `tornar_soulmate` quando a Afinidade chega no teto (sem RNG/botão
        # - a Prova de Soulmate que gerava esse flag por tentativa foi
        # removida em 2026-09-14, dead code).
        colunas_afinidade = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_afinidade)")}
        if "is_soulmate" not in colunas_afinidade:
            conn.execute("ALTER TABLE colecao_afinidade ADD COLUMN is_soulmate INTEGER NOT NULL DEFAULT 0")
        for coluna_prova in ("soulmate_tentativas", "soulmate_ultima_tentativa_em"):
            if coluna_prova in colunas_afinidade:
                conn.execute(f"ALTER TABLE colecao_afinidade DROP COLUMN {coluna_prova}")
        # 🔥 Nível de Personagem (2026-08-30, Torre, ERIS_power_afinidade_
        # soulmate_niveis.md Seção 5) - investimento DELIBERADO do jogador
        # (gasta WiShards, ver `subir_nivel`), 1-10, +50 Power fixo por
        # nível acima do 1º. Mora em `colecao_afinidade` porque é a MESMA
        # propriedade de escopo (guild+user+personagem) que Afinidade/
        # Soulmate - o vínculo do jogador com ESSA personagem específica.
        if "nivel" not in colunas_afinidade:
            conn.execute("ALTER TABLE colecao_afinidade ADD COLUMN nivel INTEGER NOT NULL DEFAULT 1")

        # 🔥 Dificuldade/CP recomendado do World Boss (2026-09-02, pedido do
        # usuário: "seria bom se as dificuldades fossem fixas, mostrando CP
        # recomendado") - snapshot calculado 1x no spawn (Seção 7, mesmo
        # espírito do CP congelado dos participantes), nunca recalculado
        # durante o evento.
        colunas_worldboss = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_worldboss_eventos)")}
        if "dificuldade" not in colunas_worldboss:
            conn.execute("ALTER TABLE colecao_worldboss_eventos ADD COLUMN dificuldade TEXT")
        if "cp_recomendado" not in colunas_worldboss:
            conn.execute("ALTER TABLE colecao_worldboss_eventos ADD COLUMN cp_recomendado REAL")

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
        # colunas de snapshot da Cidade, ver `_SCHEMA`
        # acima (`colecao_cidade_estado` já existia só com `ultima_
        # producao_em`, criada mais cedo nesta mesma sessão).
        colunas_cidade = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_cidade_estado)")}
        for coluna_cidade in ("cp_bonus_militar_fixo", "cp_bonus_arcano_percentual", "bonus_colecao_loot_percentual"):
            if coluna_cidade not in colunas_cidade:
                conn.execute(f"ALTER TABLE colecao_cidade_estado ADD COLUMN {coluna_cidade} REAL NOT NULL DEFAULT 0")

        _aplicar_migracoes_numeradas(conn)


def _migracao_001_wishlist_para_favoritos(conn):
    """Fusão Wishlist -> Favoritos (2026-09-03, pedido do usuário: "tem
    Favoritos e Wishlist, Vamos unir tudo em Wishlist... melhor manter o
    favoritos e apenas renomea-lo para wishlist"): copia toda entrada de
    `colecao_wishlist` pra `colecao_favoritas`. `colecao_wishlist` continua
    existindo (sem migração destrutiva), só não é mais lida.

    Até a 0.2.0 isto rodava em TODO boot, e como `colecao_wishlist` nunca
    é apagada, um favorito removido depois da fusão voltava sozinho a cada
    reinício do bot. Agora roda 1x só."""
    conn.execute(
        "INSERT OR IGNORE INTO colecao_favoritas (guild_id, user_id, personagem_id) "
        "SELECT guild_id, user_id, personagem_id FROM colecao_wishlist",
    )


# Migrações de dado ou de schema que precisam rodar EXATAMENTE 1x, em
# ordem. Mudança nova entra aqui com o próximo número (nunca reordenar nem
# reaproveitar número; nunca destrutiva, ver CLAUDE.md). O que cada banco
# já aplicou fica em `colecao_schema_version`.
#
# O bloco acima, em `inicializar()` (`_SCHEMA` + `ALTER TABLE` condicionado
# por `PRAGMA table_info`), é o esquema-base de antes deste mecanismo:
# idempotente, continua rodando em todo boot e não recebe mais nada novo
# além de `CREATE TABLE IF NOT EXISTS` em `_SCHEMA`.
_MIGRACOES = [
    (1, "Fusão Wishlist -> Favoritos (cópia única)", _migracao_001_wishlist_para_favoritos),
]


def _aplicar_migracoes_numeradas(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS colecao_schema_version ("
        "versao INTEGER PRIMARY KEY, descricao TEXT NOT NULL, aplicada_em TEXT NOT NULL)"
    )
    aplicadas = {r["versao"] for r in conn.execute("SELECT versao FROM colecao_schema_version")}
    for versao, descricao, migrar in _MIGRACOES:
        if versao in aplicadas:
            continue
        migrar(conn)
        conn.execute(
            "INSERT INTO colecao_schema_version (versao, descricao, aplicada_em) VALUES (?, ?, ?)",
            (versao, descricao, datetime.now(timezone.utc).isoformat()),
        )


def versao_schema():
    """Maior migração numerada já aplicada neste banco (0 = nenhuma)."""
    with conexao() as conn:
        linha = conn.execute("SELECT MAX(versao) AS v FROM colecao_schema_version").fetchone()
    return linha["v"] or 0
