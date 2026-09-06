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

from pandora.config import CAMINHO_BANCO, FUSO_BRASILIA, PASTA_DADOS


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
    "duracao_card_segundos": "INTEGER NOT NULL DEFAULT 3600",
    "max_rolls_por_comando": "INTEGER NOT NULL DEFAULT 10",
    "chance_wish_roll": "REAL NOT NULL DEFAULT 0.20",
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
    "cooldown_batalha_ativo": False,
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
        # colunas de snapshot de bônus de CP pra Party, ver `_SCHEMA`
        # acima (`colecao_cidade_estado` já existia só com `ultima_
        # producao_em`, criada mais cedo nesta mesma sessão).
        colunas_cidade = {r["name"] for r in conn.execute("PRAGMA table_info(colecao_cidade_estado)")}
        for coluna_cidade in ("cp_bonus_militar_fixo", "cp_bonus_arcano_percentual", "cp_bonus_colecao_fixo"):
            if coluna_cidade not in colunas_cidade:
                conn.execute(f"ALTER TABLE colecao_cidade_estado ADD COLUMN {coluna_cidade} REAL NOT NULL DEFAULT 0")

        # 🔥 Fusão Wishlist -> Favoritos (2026-09-03, pedido do usuário:
        # "tem Favoritos e Wishlist, Vamos unir tudo em Wishlist... melhor
        # manter o favoritos e apenas renomea-lo para wishlist") - as 2
        # tabelas sempre foram estruturalmente idênticas (`guild_id,
        # user_id, personagem_id`), a diferença toda era regra de
        # aplicação (JOIN/checagem de posse), não schema. Copia toda
        # entrada de `colecao_wishlist` pra `colecao_favoritas` (`INSERT OR
        # IGNORE` - idempotente, roda em TODO boot sem duplicar nem
        # sobrescrever o que já foi migrado) - ninguém perde o que já
        # tinha na wishlist antiga só porque o mecanismo mudou de nome.
        # `colecao_wishlist` continua existindo (sem migração destrutiva,
        # mesmo padrão de toda tabela aposentada neste projeto), só para
        # de ser LIDA por qualquer código novo.
        conn.execute(
            "INSERT OR IGNORE INTO colecao_favoritas (guild_id, user_id, personagem_id) "
            "SELECT guild_id, user_id, personagem_id FROM colecao_wishlist",
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
        "cooldown_batalha_ativo": bool(linha["cooldown_batalha_ativo"]),
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
    taxonomia_*.py`)."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT classe, COUNT(*) AS total FROM colecao_personagens "
            "WHERE classe IS NOT NULL GROUP BY classe ORDER BY total DESC LIMIT ?",
            (limite,),
        ).fetchall()
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
# Preço "primeiro palpite" (mesma régua de sempre, barato -> extremamente
# caro) continuando a curva de crescimento dos 5 primeiros níveis.
PRECOS_UPGRADE_SLOT_SERIE_FAVORITA = {
    1: 5_000, 2: 15_000, 3: 40_000, 4: 100_000, 5: 250_000,
    6: 600_000, 7: 1_400_000, 8: 3_000_000, 9: 6_500_000, 10: 14_000_000,
    11: 30_000_000, 12: 60_000_000, 13: 125_000_000, 14: 250_000_000, 15: 500_000_000,
    16: 1_000_000_000, 17: 2_000_000_000, 18: 4_000_000_000, 19: 8_000_000_000, 20: 16_000_000_000,
}
SLOTS_BASE_SERIE_FAVORITA = 5
NIVEL_MAXIMO_UPGRADE_SLOT_SERIE_FAVORITA = 20


def comprar_slot_serie_favorita(guild_id, user_id):
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
    if saldo_wishards(guild_id, user_id) < preco:
        return False, f"Custa {fmt_numero(preco)} WiShards e você não tem o suficiente."
    creditar_wishards(guild_id, user_id, -preco, "upgrade_slot_serie_favorita", f"nivel {proximo_nivel}")
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


def incrementar_ascensao_personagem_favorita(guild_id, user_id, slot):
    with conexao() as conn:
        conn.execute(
            "UPDATE colecao_personagens_favoritas SET nivel_ascensao = nivel_ascensao + 1 "
            "WHERE guild_id = ? AND user_id = ? AND slot = ?",
            (str(guild_id), str(user_id), slot),
        )


# 🔥 Mesma curva de preço de `PRECOS_UPGRADE_SLOT_SERIE_FAVORITA` (WiShards,
# confirmado com o usuário: "mesma moeda/curva de Série Favorita, não
# Soulstone") - 5 base + até 20 pagos = 25 no total, mesmo teto de opções de
# 1 único `discord.ui.Select`.
PRECOS_UPGRADE_SLOT_PERSONAGEM_FAVORITA = {
    1: 5_000, 2: 15_000, 3: 40_000, 4: 100_000, 5: 250_000,
    6: 600_000, 7: 1_400_000, 8: 3_000_000, 9: 6_500_000, 10: 14_000_000,
    11: 30_000_000, 12: 60_000_000, 13: 125_000_000, 14: 250_000_000, 15: 500_000_000,
    16: 1_000_000_000, 17: 2_000_000_000, 18: 4_000_000_000, 19: 8_000_000_000, 20: 16_000_000_000,
}
SLOTS_BASE_PERSONAGEM_FAVORITA = 5
NIVEL_MAXIMO_UPGRADE_SLOT_PERSONAGEM_FAVORITA = 20


def nivel_upgrade_slots_personagem_favorita(guild_id, user_id):
    with conexao() as conn:
        linha = _estado_jogador(conn, guild_id, user_id)
    return linha["nivel_upgrade_slots_personagem_favorita"] if linha else 0


def comprar_slot_personagem_favorita(guild_id, user_id):
    """Mesmo padrão de `comprar_slot_serie_favorita` - preço escalonado,
    1 slot a mais por nível, `SLOTS_BASE_PERSONAGEM_FAVORITA` (5) + até
    `NIVEL_MAXIMO_UPGRADE_SLOT_PERSONAGEM_FAVORITA` (20) = 25 no total."""
    nivel_atual = nivel_upgrade_slots_personagem_favorita(guild_id, user_id)
    if nivel_atual >= NIVEL_MAXIMO_UPGRADE_SLOT_PERSONAGEM_FAVORITA:
        return False, "Você já tem o número máximo de slots de Waifu."
    proximo_nivel = nivel_atual + 1
    preco = PRECOS_UPGRADE_SLOT_PERSONAGEM_FAVORITA[proximo_nivel]
    if saldo_wishards(guild_id, user_id) < preco:
        return False, f"Custa {fmt_numero(preco)} WiShards e você não tem o suficiente."
    creditar_wishards(guild_id, user_id, -preco, "upgrade_slot_personagem_favorita", f"nivel {proximo_nivel}")
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
    alimenta o select do botão "💞 Prova de Soulmate" do hub `/pandora` (ver
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
        return False, f"Custa {fmt_numero(custo)} WiShards e você não tem o suficiente."
    creditar_wishards(guild_id, user_id, -custo, "upgrade_nivel_personagem", personagem["nome"], str(personagem_id))
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_afinidade (guild_id, user_id, personagem_id, afinidade, nivel) VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(guild_id, user_id, personagem_id) DO UPDATE SET nivel = excluded.nivel",
            (str(guild_id), str(user_id), personagem_id, nivel_alvo),
        )
    xp = custo // 5
    creditar_xp_progressao(guild_id, user_id, xp)
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
        return False, f"Custa {fmt_numero(custo)} Soulstone e você não tem o suficiente."
    creditar_soulstone(guild_id, user_id, -custo, "upgrade_afinidade", personagem["nome"], str(personagem_id))
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_afinidade (guild_id, user_id, personagem_id, afinidade) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, personagem_id) DO UPDATE SET afinidade = excluded.afinidade",
            (str(guild_id), str(user_id), personagem_id, afinidade_alvo),
        )
    return True, f"{personagem['nome']} subiu pra Afinidade {afinidade_alvo}! (custou {fmt_numero(custo)} Soulstone)"


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
        return False, f"Custa {fmt_numero(preco)} WiShards e você não tem o suficiente."

    creditar_wishards(guild_id, user_id, -preco, "loja_compra", personagem["nome"], str(personagem_id))
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

def wishlist_adicionar(guild_id, user_id, personagem_id):
    with conexao() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO colecao_favoritas (guild_id, user_id, personagem_id) VALUES (?, ?, ?)",
            (str(guild_id), str(user_id), personagem_id),
        )


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


def wishlist_disponiveis_no_guild(guild_id, user_id, permitir_nsfw):
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
    filtros.append("p.id NOT IN (SELECT personagem_id FROM colecao_propriedade WHERE guild_id = ?)")
    params.append(str(guild_id))
    sql = (
        "SELECT p.id FROM colecao_favoritas f JOIN colecao_personagens p ON p.id = f.personagem_id "
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
    return (datetime.now(timezone.utc) - ultimo) >= timedelta(hours=24)


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
# 🔥 Curva virou QUADRÁTICA (2026-09-03, pedido do usuário: "aumenta mais
# o custo. Eu tenho 28m, e comprar 25 melhorias ja no lv350 n sai nem por
# 1M") - a curva LINEAR antiga (`custo(n) = C * n`) deixava o Nv.350
# custando só 35.000/17.500 (Potencial/Treinamento) - barato demais pra
# quem já tem dezenas de milhões. `custo(n) = C * n²` cresce muito mais
# rápido em nível alto SEM mexer no preço de quem ainda está no início -
# as 2 constantes abaixo foram escolhidas pra CRUZAR com o preço linear
# antigo exatamente no Nível 50 (`C_novo = C_antigo / 50`): quem está
# abaixo do Nv.50 paga um pouco MENOS que antes, quem está acima paga
# cada vez mais. Ex.: Potencial Nv.350 sozinho vai de 35.000 pra 245.000
# (7x); um pacote de 25 níveis perto do 350 vai de ~845.000 pra ~5,7M.
CUSTO_TREINAMENTO_GLOBAL_POR_NIVEL = 1
CUSTO_POTENCIAL_COLECAO_POR_NIVEL = 2
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
            (linha["quantidade"] // MARCO_QUANTIDADE_CLASSE) * BONUS_POR_MARCO_CLASSE,
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
    return (quantidade // MARCO_QUANTIDADE_CLASSE) * BONUS_POR_MARCO_CLASSE


def bonus_classes_por_categoria(guild_id, user_id):
    """Detalhe do bônus por classe agrupado por categoria de combate
    (2026-09-02, pedido do usuário: "uma nova tela q mostrasse q DPS ta
    ganhando +X Tank +Y... e n sei se separou por classe tbm") - devolve
    {categoria: {"total_bonus": int, "total_personagens": int, "classes":
    [{"classe", "quantidade", "bonus", "proximo_marco"}, ...]}}, só com
    classes que o jogador possui NESSE servidor (classe sem `categoria_
    combate` cadastrada em `colecao_classes` cai em "Sem categoria").
    `total_bonus` é a SOMA do bônus de cada classe da categoria (não
    multiplicado pela quantidade de cada uma) - decisão explícita do
    usuário depois de eu explicar que não existe um "+X do DPS" físico de
    verdade (cada personagem só ganha o bônus da PRÓPRIA classe, nunca o
    das outras classes da mesma categoria) - o número é só a soma dos
    bônus vigentes agrupados, não um valor que se aplica a cada unidade."""
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
        bonus = (quantidade // MARCO_QUANTIDADE_CLASSE) * BONUS_POR_MARCO_CLASSE
        proximo_marco = (quantidade // MARCO_QUANTIDADE_CLASSE + 1) * MARCO_QUANTIDADE_CLASSE
        entrada = categorias.setdefault(categoria, {"total_bonus": 0, "total_personagens": 0, "classes": []})
        entrada["total_bonus"] += bonus
        entrada["total_personagens"] += quantidade
        entrada["classes"].append(
            {"classe": linha["classe"], "quantidade": quantidade, "bonus": bonus, "proximo_marco": proximo_marco}
        )
    for entrada in categorias.values():
        entrada["classes"].sort(key=lambda c: c["bonus"], reverse=True)
    return categorias


def custo_treinamento_global(nivel_alvo):
    return CUSTO_TREINAMENTO_GLOBAL_POR_NIVEL * nivel_alvo * nivel_alvo


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
        return False, f"Custa {fmt_numero(custo)} WiShards e você não tem o suficiente."
    creditar_wishards(guild_id, user_id, -custo, "treinamento_global", f"nível {nivel_atual}->{nivel_alvo}")
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_progressao (guild_id, user_id, nivel_treinamento_global) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel_treinamento_global = excluded.nivel_treinamento_global",
            (str(guild_id), str(user_id), nivel_alvo),
        )
    bonus_total = nivel_alvo * BONUS_FIXO_POR_NIVEL_TREINAMENTO
    return True, f"Treinamento Global Nv.{nivel_alvo}! +{fmt_numero(bonus_total)} CP fixo por personagem, pra sempre (custou {fmt_numero(custo)} WiShards)."


def custo_potencial_colecao(nivel_alvo):
    return CUSTO_POTENCIAL_COLECAO_POR_NIVEL * nivel_alvo * nivel_alvo


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
        return False, f"Custa {fmt_numero(custo)} WiShards e você não tem o suficiente."
    creditar_wishards(guild_id, user_id, -custo, "potencial_colecao", f"nível {nivel_atual}->{nivel_alvo}")
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_progressao (guild_id, user_id, nivel_potencial_colecao) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel_potencial_colecao = excluded.nivel_potencial_colecao",
            (str(guild_id), str(user_id), nivel_alvo),
        )
    bonus_total = nivel_alvo * BONUS_PERCENTUAL_POR_NIVEL_POTENCIAL
    return True, f"Potencial da Coleção Nv.{nivel_alvo}! +{bonus_total}% CP global, pra sempre (custou {fmt_numero(custo)} WiShards)."


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
    if saldo_wishards(guild_id, user_id) < custo:
        return False, f"Custa {fmt_numero(custo)} WiShards e você não tem o suficiente."

    creditar_wishards(guild_id, user_id, -custo, "upgrade_rolls", f"nível {nivel_atual}->{nivel_alvo}")
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


def comprar_upgrade_claims_ate(guild_id, user_id, nivel_alvo):
    """Devolve (ok: bool, mensagem: str) - mesmo padrão de `comprar_
    upgrade_rolls_ate`. +1 claim PERMANENTE por nível em cima do
    `claims_por_ciclo` do servidor (nunca substitui a config do servidor,
    só soma)."""
    nivel_atual = nivel_upgrade_claims(guild_id, user_id)
    if nivel_alvo <= nivel_atual:
        return False, f"Upgrade de claims já está no nível {nivel_atual} ou acima."
    custo = custo_total_upgrade_claims_ate(nivel_atual, nivel_alvo)
    if saldo_wishards(guild_id, user_id) < custo:
        return False, f"Custa {fmt_numero(custo)} WiShards e você não tem o suficiente."

    creditar_wishards(guild_id, user_id, -custo, "upgrade_claims", f"nível {nivel_atual}->{nivel_alvo}")
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
# Conquistas (2026-09-01) - registro puro, nunca concede recompensa.
# --------------------------------------------------------------------------

def conceder_conquista(guild_id, user_id, conquista_id):
    """Devolve True se era NOVA (nunca desbloqueada antes nesse servidor) -
    `False` se já tinha, pra quem chama saber se deve anunciar "NOVA
    CONQUISTA" ou ficar quieto (idempotente - seguro chamar toda vez que a
    condição bater de novo, ex.: "Caçador" checado em toda vitória)."""
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO colecao_conquistas (guild_id, user_id, conquista_id, desbloqueada_em) VALUES (?, ?, ?, ?)",
            (str(guild_id), str(user_id), conquista_id, agora),
        )
        return cursor.rowcount > 0


def conquistas_do_jogador(guild_id, user_id):
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT conquista_id, desbloqueada_em FROM colecao_conquistas WHERE guild_id = ? AND user_id = ? ORDER BY desbloqueada_em",
            (str(guild_id), str(user_id)),
        ).fetchall()
    return [dict(r) for r in linhas]


def contar_vitorias_worldboss(guild_id, user_id):
    """Quantas vitórias de World Boss esse jogador já PARTICIPOU nesse
    servidor - inclui a que acabou de terminar, se `db.worldboss_
    finalizar` já rodou antes desta chamada (ordem que `pandora.worldboss.
    processar_vitoria` respeita)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT COUNT(*) AS n FROM colecao_worldboss_participantes p "
            "JOIN colecao_worldboss_eventos e ON e.id = p.evento_id "
            "WHERE e.guild_id = ? AND p.user_id = ? AND e.status = 'vitoria'",
            (str(guild_id), str(user_id)),
        ).fetchone()
    return linha["n"]


# --------------------------------------------------------------------------
# Inventário de itens (2026-09-01)
# --------------------------------------------------------------------------

def adicionar_item(guild_id, user_id, item, quantidade=1):
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_inventario (guild_id, user_id, item, quantidade) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, item) DO UPDATE SET quantidade = quantidade + excluded.quantidade",
            (str(guild_id), str(user_id), item, quantidade),
        )


def quantidade_item(guild_id, user_id, item):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT quantidade FROM colecao_inventario WHERE guild_id = ? AND user_id = ? AND item = ?",
            (str(guild_id), str(user_id), item),
        ).fetchone()
    return linha["quantidade"] if linha else 0


def consumir_item(guild_id, user_id, item, quantidade=1):
    """Devolve True/False - só desconta se tiver o suficiente (nunca vai
    negativo)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT quantidade FROM colecao_inventario WHERE guild_id = ? AND user_id = ? AND item = ?",
            (str(guild_id), str(user_id), item),
        ).fetchone()
        if linha is None or linha["quantidade"] < quantidade:
            return False
        conn.execute(
            "UPDATE colecao_inventario SET quantidade = quantidade - ? WHERE guild_id = ? AND user_id = ? AND item = ?",
            (quantidade, str(guild_id), str(user_id), item),
        )
        return True


def itens_do_jogador(guild_id, user_id):
    """{item: quantidade} só com quantidade > 0."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT item, quantidade FROM colecao_inventario WHERE guild_id = ? AND user_id = ? AND quantidade > 0",
            (str(guild_id), str(user_id)),
        ).fetchall()
    return {r["item"]: r["quantidade"] for r in linhas}


def total_comprado_item(guild_id, user_id, item):
    """Quantas unidades desse item o jogador JÁ comprou na Loja (vitalício,
    nunca decrementado por uso) - base do preço escalável (`pandora.itens.
    custo_total_item`)."""
    with conexao() as conn:
        linha = conn.execute(
            "SELECT total FROM colecao_compras_item WHERE guild_id = ? AND user_id = ? AND item = ?",
            (str(guild_id), str(user_id), item),
        ).fetchone()
    return linha["total"] if linha else 0


def registrar_compra_item(guild_id, user_id, item, quantidade):
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_compras_item (guild_id, user_id, item, total) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, item) DO UPDATE SET total = total + excluded.total",
            (str(guild_id), str(user_id), item, quantidade),
        )


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
# Construções da Cidade (2026-09-01, item "Upgrade de Construção", Seção 10)
# --------------------------------------------------------------------------

# 🔥 Fonte ÚNICA das 6 áreas (2026-09-03, pedido do usuário: "vc tem
# distinguindo construção de area, mas é a msm coisa, so use area") -
# antes existiam 2 listas quase-duplicadas (`itens.AREAS_CONSTRUCAO`, um
# dict área->nome de construção tipo "Quartel"/"Hospital" nunca usado de
# um jeito que precisasse ser diferente da área; `cidade.FUNCOES_CIDADE`,
# o mesmo tuple de 6 nomes) - unificadas aqui, a única que o teto
# DINÂMICO abaixo pode enxergar sem criar import cíclico (`itens.py` e
# `cidade.py` já importam `db.py`, nunca o contrário). `itens.
# AREAS_CONSTRUCAO`/`cidade.FUNCOES_CIDADE` viraram aliases pra esta.
AREAS_CONSTRUCAO = ("Militar", "Saúde", "Cultura", "Administração", "Comércio", "Arcano")

NIVEL_MAXIMO_CONSTRUCAO_BASE = 10  # primeiro degrau do teto dinâmico, ver `teto_atual_construcao`


def nivel_construcao(guild_id, user_id, area):
    with conexao() as conn:
        linha = conn.execute(
            "SELECT nivel FROM colecao_construcoes WHERE guild_id = ? AND user_id = ? AND area = ?",
            (str(guild_id), str(user_id), area),
        ).fetchone()
    return linha["nivel"] if linha else 0


def niveis_construcoes(guild_id, user_id):
    """{area: nivel} só com nível > 0."""
    with conexao() as conn:
        linhas = conn.execute(
            "SELECT area, nivel FROM colecao_construcoes WHERE guild_id = ? AND user_id = ? AND nivel > 0",
            (str(guild_id), str(user_id)),
        ).fetchall()
    return {r["area"]: r["nivel"] for r in linhas}


def teto_atual_construcao(guild_id, user_id):
    """Teto de nível vigente pra upgrade de QUALQUER área (2026-09-03,
    pedido do usuário: "os upgrades maximos vao ser a cd 10 lv, e o
    limite so é quebrado qnd todas as reas tao no maximo. Ai o limite
    aumenta em +10, e vai indo") - começa em `NIVEL_MAXIMO_CONSTRUCAO_
    BASE` (10); só sobe +10 quando TODAS as 6 áreas já bateram o teto
    anterior - a área MAIS ATRASADA decide o teto vigente pra TODAS, não
    cada uma o seu próprio (área nunca comprada conta como nível 0, o
    pior caso possível). O teto é sempre RECALCULADO na hora (nunca
    gravado) - no instante em que a última área atrasada alcança o teto
    velho, a própria leitura seguinte já devolve o teto novo, sem
    precisar de um passo separado de "destravar"."""
    niveis = niveis_construcoes(guild_id, user_id)
    nivel_minimo = min((niveis.get(area, 0) for area in AREAS_CONSTRUCAO), default=0)
    return NIVEL_MAXIMO_CONSTRUCAO_BASE * (nivel_minimo // NIVEL_MAXIMO_CONSTRUCAO_BASE + 1)


def subir_construcao(guild_id, user_id, area, quantidade=1):
    """`quantidade` (2026-09-03, pedido do usuário: "alguns [itens] pode
    permitir usar varios por vez, como o upgrade de construção, q upo a
    msm construção varios lv por vez") - soma `quantidade` níveis de uma
    vez, 1 única escrita (era sempre +1, chamada em loop faria N
    round-trips no banco à toa pra uma compra em lote)."""
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_construcoes (guild_id, user_id, area, nivel) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, area) DO UPDATE SET nivel = nivel + excluded.nivel",
            (str(guild_id), str(user_id), area, quantidade),
        )
        linha = conn.execute(
            "SELECT nivel FROM colecao_construcoes WHERE guild_id = ? AND user_id = ? AND area = ?",
            (str(guild_id), str(user_id), area),
        ).fetchone()
    return linha["nivel"]


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


# --------------------------------------------------------------------------
# Métricas das Conquistas do Colecionador (2026-09-01,
# `ERIS_sistema_colecao_wishards.md` Seções 22/24) - todas de leitura
# barata (agregado SQL, nunca materializa a coleção inteira em Python) -
# ver `pandora.conquistas.verificar_colecionador`, que só roda sob
# demanda (painel "🏆 Conquistas"), nunca num caminho quente como claim.
# --------------------------------------------------------------------------

def incrementar_rolls_realizados(guild_id, user_id, quantidade):
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_estado_jogador (guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em, total_rolls_realizados) "
            "VALUES (?, ?, 0, ?, 1, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET total_rolls_realizados = total_rolls_realizados + excluded.total_rolls_realizados",
            (str(guild_id), str(user_id), agora, agora, quantidade),
        )


def incrementar_merges_realizados(guild_id, user_id):
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO colecao_estado_jogador (guild_id, user_id, rolls_restantes, rolls_resetam_em, claims_restantes, claims_resetam_em, total_merges_realizados) "
            "VALUES (?, ?, 0, ?, 1, ?, 1) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET total_merges_realizados = total_merges_realizados + 1",
            (str(guild_id), str(user_id), agora, agora),
        )


def metricas_colecionador(guild_id, user_id):
    """Todas as métricas das Conquistas do Colecionador NUMA função só (1
    dict) - cada valor vem de um agregado SQL barato, nunca de
    materializar a coleção inteira em Python."""
    guild_id, user_id = str(guild_id), str(user_id)
    with conexao() as conn:
        total_personagens = conn.execute(
            "SELECT COUNT(*) AS n FROM colecao_propriedade WHERE guild_id = ? AND dono_id = ?",
            (guild_id, user_id),
        ).fetchone()["n"]

        por_raridade = {r["raridade"]: r["n"] for r in conn.execute(
            "SELECT p.raridade AS raridade, COUNT(*) AS n FROM colecao_propriedade c "
            "JOIN colecao_personagens p ON p.id = c.personagem_id "
            "WHERE c.guild_id = ? AND c.dono_id = ? GROUP BY p.raridade",
            (guild_id, user_id),
        )}

        claims = conn.execute(
            "SELECT COUNT(*) AS n FROM colecao_wishards_ledger WHERE guild_id = ? AND user_id = ? AND origem = 'claim'",
            (guild_id, user_id),
        ).fetchone()["n"]

        rolls = conn.execute(
            "SELECT total_rolls_realizados AS n FROM colecao_estado_jogador WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
        rolls = rolls["n"] if rolls else 0

        wishlist_obtidas = conn.execute(
            "SELECT COUNT(*) AS n FROM colecao_wishlist w JOIN colecao_propriedade c "
            "ON c.guild_id = w.guild_id AND c.dono_id = w.user_id AND c.personagem_id = w.personagem_id "
            "WHERE w.guild_id = ? AND w.user_id = ?",
            (guild_id, user_id),
        ).fetchone()["n"]

        afinidade_acumulada = conn.execute(
            "SELECT COALESCE(SUM(afinidade), 0) AS soma FROM colecao_afinidade WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()["soma"]

        soulmates = conn.execute(
            "SELECT COUNT(*) AS n FROM colecao_afinidade WHERE guild_id = ? AND user_id = ? AND is_soulmate = 1",
            (guild_id, user_id),
        ).fetchone()["n"]

        trocas = conn.execute(
            "SELECT COUNT(*) AS n FROM colecao_troca_proposta WHERE guild_id = ? AND status = 'aceita' "
            "AND (proponente_id = ? OR alvo_id = ?)",
            (guild_id, user_id, user_id),
        ).fetchone()["n"]

        merges = conn.execute(
            "SELECT total_merges_realizados AS n FROM colecao_estado_jogador WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
        merges = merges["n"] if merges else 0

        # 🔥 Séries completas - só entre séries onde o jogador já tem
        # PELO MENOS 1 personagem (bounded pelo tamanho da COLEÇÃO DELE,
        # nunca pelo catálogo inteiro) comparadas contra o total daquela
        # série no catálogo.
        series_possuidas = conn.execute(
            "SELECT p.serie AS serie, COUNT(*) AS n FROM colecao_propriedade c "
            "JOIN colecao_personagens p ON p.id = c.personagem_id "
            "WHERE c.guild_id = ? AND c.dono_id = ? AND p.serie IS NOT NULL AND p.serie != '' "
            "GROUP BY p.serie",
            (guild_id, user_id),
        ).fetchall()
        series_completas = 0
        for linha_serie in series_possuidas:
            total_da_serie = conn.execute(
                "SELECT COUNT(*) AS n FROM colecao_personagens WHERE serie = ? AND ativo = 1",
                (linha_serie["serie"],),
            ).fetchone()["n"]
            if total_da_serie > 0 and linha_serie["n"] >= total_da_serie:
                series_completas += 1

        valor_colecao = conn.execute(
            "SELECT COALESCE(SUM(p.raridade * 20), 0) AS soma FROM colecao_propriedade c "
            "JOIN colecao_personagens p ON p.id = c.personagem_id "
            "WHERE c.guild_id = ? AND c.dono_id = ?",
            (guild_id, user_id),
        ).fetchone()["soma"]

        wishards_movimentados = conn.execute(
            "SELECT COALESCE(SUM(ABS(quantidade)), 0) AS soma FROM colecao_wishards_ledger WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()["soma"]

    andar_torre = andar_atual_torre(guild_id, user_id)

    return {
        "personagens_totais": total_personagens,
        "raridade_1": por_raridade.get(1, 0), "raridade_2": por_raridade.get(2, 0),
        "raridade_3": por_raridade.get(3, 0), "raridade_4": por_raridade.get(4, 0), "raridade_5": por_raridade.get(5, 0),
        "claims": claims, "rolls": rolls, "wishlist_obtidas": wishlist_obtidas,
        "afinidade_acumulada": afinidade_acumulada, "soulmates": soulmates,
        "trocas": trocas, "merges": merges, "series_completas": series_completas,
        "valor_colecao": valor_colecao, "wishards_movimentados": wishards_movimentados,
        "andares_torre": andar_torre,
    }
