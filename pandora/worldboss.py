# -*- coding: utf-8 -*-
"""World Boss: Evento Cooperativo (2026-09-01, spec completa trazida pelo
usuário - ver `PANDORA_worldboss_evento_cooperativo.md`). Aparece 4x/dia em
horários FIXOS (horário de Brasília, UTC-3 fixo - Brasil não observa mais
horário de verão desde 2019, então um offset fixo evita precisar instalar
`tzdata` só pra isso), abre 10 minutos de inscrição, e todo o servidor forma
UM time só contra o Boss - CP é agregado por categoria (DPS/Tank/Support),
nunca tratado personagem por personagem no combate em si.

Diferente da Torre/Batalha (motor puro + View sob demanda), este evento
precisa de um RELÓGIO próprio (spawn nos horários fixos, fechar inscrições
depois de 10min, 1 turno/minuto) - `SchedulerWorldBoss` (`discord.ext.
tasks.loop`, mesmo padrão de `auto_colecionador.py`) é quem dirige isso,
mas cada tick só faz uma coisa: perguntar ao banco "o que já venceu?" e
agir - nenhum estado de jogo mora em memória do processo (só um marcador
anti-duplicidade de spawn, mesmo espírito do `_ultimo_roll` de `auto_
colecionador.py`) - um restart do bot no meio de um combate não perde
turno nem trava o evento, o próximo tick de 30s simplesmente continua de
onde o banco disse que estava."""
import asyncio
import json
import math
import random
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import tasks

from pandora import auto_colecionador, conquistas, consulta, db, gacha, itens, torre
from pandora.config import FUSO_BRASILIA  # 2026-09-03, movido pra config.py - compartilhado com a Recompensa Diária

CATEGORIAS = ("DPS", "Tank", "Support")
HORARIOS_APARICAO = (10, 14, 18, 22)  # Seção 2, horário de Brasília
DURACAO_INSCRICAO_MINUTOS = 10  # Seção 3
DURACAO_TURNO_SEGUNDOS = 60  # Seção 18 - "1 turno por minuto"
LIMITE_TURNOS = 60  # Seção 21 - "pode existir limite máximo de turnos", 1a hora de combate

# 🔥 Recompensas de vitória (2026-09-01, spec "World Boss: Recompensas e
# Conquistas") - materiais básicos, primeiro palpite ("os valores devem
# ser calibrados posteriormente considerando a produção real da Cidade",
# Seção 4) - só participantes HUMANOS recebem (Seção 1, bots não).
RECOMPENSA_WISHARDS_VITORIA = 500
RECOMPENSA_XP_VITORIA = 200
RECOMPENSA_SOULSTONE_VITORIA = 20

# 🔥 Valores-base do TIME (Seção 14) recalibrados (2026-09-02) - os
# originais matavam qualquer time no turno 1 (HP_BASE menor que o ATK de
# QUALQUER Boss do catálogo - achado em produção, ver TODO.md). Novo
# princípio, pedido do usuário: o time real observado (3 jogadores, CP
# ~26.297/categoria) deve ter uma "chance boa de vencer", diminuindo por
# dificuldade - o HP/ATK de cada Boss no catálogo continua quase igual
# entre si de propósito (a MECÂNICA especial de cada um é o diferencial de
# dificuldade, não o número bruto). Validado simulando o motor real
# (`executar_turno`) 40x por Boss com esse CP: **87% de vitória agregada**
# nos 10 Bosses - 8 deles em 70-100%, Senhor da Morte (Ceifar) em 65% como
# um degrau intermediário, e Dragão Ancião (Enfurecer, ATK +10%/turno
# composto) em ~0% - não é bug, é a mecânica dele favorecendo dano BEM mais
# rápido do que este time consegue entregar (esperado ficar inviável pra
# time pequeno, sem mais participantes/composição mais agressiva de DPS).
# `REFERENCIA_CP` (CP-agregado que dobra o multiplicador, Multiplicador(CP)
# = 1 + √(CP/referência)) não precisou mudar, só a escala dos valores-base.
DANO_BASE = 14_000.0
HP_BASE = 45_000.0
CURA_BASE = 7_500.0
REFERENCIA_CP = 20_000.0

# 🔥 Variação leve de dano por turno (2026-09-02, pedido do usuário) -
# ±10% tanto no dano causado pelo time quanto no ATK do Boss, pra o combate
# não ser 100% determinístico turno a turno sem abrir espaço pra um pico de
# sorte/azar decidir o evento sozinho.
VARIACAO_TURNO = 0.10

# 🔥 2 bots SEMPRE entram depois de pelo menos 1 humano (Seção 11) - CP
# deles é a MÉDIA dos participantes humanos (2026-09-01, pedido direto do
# usuário - "o CP dos bots vai ser a media dos players participante"), não
# uma personagem real (o ERIS só tem 1 conta de bot acessível a partir da
# instância que roda este scheduler - ver ARQUITETURA.md). `user_id`
# sintético, nunca colide com um snowflake real do Discord.
BOT_SLOTS = ("bot:1", "bot:2")

_POSTURAS = ("Guerra", "Ruína", "Corrupção")  # Rei Demônio, Seção 22.8

# 🔥 Deus do Caos (Seção 22.10) - 1 sorteado por turno, dura só aquele
# turno. "Ataca duas vezes" implementado como multiplicador ×2 (mesmo
# resultado numérico de repetir o passo, sem duplicar o loop de turno).
_EFEITOS_CAOS = (
    {"descricao": "⚔️ Dano do grupo +30%", "mult_dano": 1.30},
    {"descricao": "✨ Cura do grupo -50%", "mult_cura": 0.50},
    {"descricao": "🛡️ HP máximo do grupo +20% (só este turno)", "bonus_hp_maximo": 0.20},
    {"descricao": "👹 ATK do Boss +40%", "mult_atk": 1.40},
    {"descricao": "❤️ Boss recupera 5% do HP máximo", "cura_boss_percentual": 0.05},
    {"descricao": "💥 O grupo ataca duas vezes", "mult_dano": 2.0},
    {"descricao": "☠️ O Boss ataca duas vezes", "mult_atk": 2.0},
)

# 🔥 Catálogo FECHADO (Seção 22) - hp/atk são o perfil-BASE de cada Boss
# (primeiro palpite, Seção 24: "os valores podem ser calibrados usando
# dados históricos... nunca pra alterar retroativamente o Boss atual" - só
# os PRÓXIMOS bosses mudam). Corrigido 2026-09-02 (achado do usuário: "cada
# boss pode variar entre todas as dificuldades") - dificuldade NÃO é mais
# uma propriedade fixa do Boss (não existia isso antes desta sessão, só
# hp/atk fixos por Boss) - qualquer um dos 10 pode sortear qualquer uma das
# 5 dificuldades (`DIFICULDADES`, abaixo) no spawn. O hp/atk daqui continua
# sendo a base "🟠 Difícil" ("mantém os status atual como difícil", pedido
# do usuário) - as outras 4 dificuldades escalam esses mesmos números pra
# cima/baixo, nunca trocam o número base do Boss.
CATALOGO_BOSSES = {
    "dragao_anciao": {"nome": "🐉 Dragão Ancião", "hp": 480_000.0, "atk": 14_000.0, "mecanica": "enfurecer"},
    "rei_vampiro": {"nome": "🩸 Rei Vampiro", "hp": 420_000.0, "atk": 15_000.0, "mecanica": "drenar_vida"},
    "doppelganger": {"nome": "🪞 Doppelgänger", "hp": 380_000.0, "atk": 14_500.0, "mecanica": "adaptacao"},
    "senhor_da_morte": {"nome": "☠️ Senhor da Morte", "hp": 420_000.0, "atk": 12_500.0, "mecanica": "ceifar"},
    "fenix_eterna": {"nome": "🔥 Fênix Eterna", "hp": 300_000.0, "atk": 14_500.0, "mecanica": "renascimento"},
    "colosso_de_pedra": {
        "nome": "🗿 Colosso de Pedra", "hp": 420_000.0, "atk": 12_000.0, "mecanica": "barreira", "barreira_hp": 150_000.0,
    },
    "devorador_do_abismo": {"nome": "🌑 Devorador do Abismo", "hp": 400_000.0, "atk": 13_500.0, "mecanica": "consumir"},
    "rei_demonio": {"nome": "👑 Rei Demônio", "hp": 440_000.0, "atk": 15_000.0, "mecanica": "posturas"},
    "hidra": {"nome": "🐍 Hidra", "hp": 500_000.0, "atk": 13_000.0, "mecanica": "cabecas"},
    "deus_do_caos": {"nome": "🌌 Deus do Caos", "hp": 380_000.0, "atk": 14_000.0, "mecanica": "caos"},
}

# 🔥 5 dificuldades (2026-09-02, pedido do usuário: "Facil Normal Dificil
# Elite Pesadelo") - multiplicador aplicado no hp/atk BASE do Boss sorteado
# (independente de qual dos 10 saiu). "Difícil" = 1,0× (o próprio pedido:
# "mantém os status atual como difícil", os números originais do
# catálogo). Calibrado simulando `executar_turno` de verdade pros 10
# Bosses no CP real observado (26.297/categoria): Fácil/Normal ficam
# vitória garantida nesse CP (a mecânica de nenhum Boss segura sozinha
# contra um ATK/HP tão baixo), Difícil já reproduz a mesma distribuição da
# recalibração anterior (87% agregado, Enfurecer sendo a exceção dura),
# Elite derruba a maioria pra bem menos que isso, Pesadelo fica
# inatingível nesse CP em QUALQUER Boss (esperado - é o teto).
DIFICULDADES = {
    "facil": {"nome": "🟢 Fácil", "mult": 0.45},
    "normal": {"nome": "🔵 Normal", "mult": 0.70},
    "dificil": {"nome": "🟠 Difícil", "mult": 1.0},
    "elite": {"nome": "🔴 Elite", "mult": 1.20},
    "pesadelo": {"nome": "🟣 Pesadelo", "mult": 1.5},
}


def _arredondar_fechado(valor):
    """"Sempre valores fechados, nada de 1378 por exemplo, fecha em 1400"
    (pedido do usuário, 2026-09-02) - arredonda pro múltiplo de 100 mais
    próximo."""
    return int(round(valor / 100.0) * 100)


def _taxa_vitoria_simulada(boss_tipo, mult_dificuldade, cp, n):
    """Roda `n` combates sintéticos (motor real, `executar_turno`, sem
    tocar no banco) com esse CP-por-categoria contra o Boss/dificuldade
    dados - devolve a fração de vitórias."""
    dados = CATALOGO_BOSSES[boss_tipo]
    hp = dados["hp"] * mult_dificuldade
    atk = dados["atk"] * mult_dificuldade
    mult_cp = multiplicador_cp(cp)
    vitorias = 0
    for _ in range(n):
        evento = {
            "boss_tipo": boss_tipo,
            "boss_hp_atual": hp, "boss_hp_maximo": hp,
            "boss_atk_atual": atk, "boss_atk_base": atk,
            "time_hp_atual": HP_BASE * mult_cp, "time_hp_maximo": HP_BASE * mult_cp,
            "time_dano_turno": DANO_BASE * mult_cp, "time_cura_turno": CURA_BASE * mult_cp,
            "turno_atual": 0,
            "estado_mecanica": json.dumps(_estado_inicial_mecanica(boss_tipo, categoria_dominante="DPS")),
        }
        while True:
            novo_estado, _linhas, terminou, resultado = executar_turno(evento)
            novo_estado["estado_mecanica"] = json.dumps(novo_estado["estado_mecanica"])
            evento.update(novo_estado)
            if terminou:
                if resultado == "vitoria":
                    vitorias += 1
                break
    return vitorias / n


# 🔥 Meta de vitória usada pra achar o "CP recomendado" (2026-09-02) - 65%
# em vez de 50% (favorece o time recomendado ganhar mais vezes que perde,
# já contando com a variação leve de turno, `VARIACAO_TURNO`) e bem abaixo
# de 100% (senão o recomendado empurraria pra MUITO mais CP do que
# necessário).
META_VITORIA_CP_RECOMENDADO = 0.65


def cp_recomendado(boss_tipo, dificuldade):
    """CP recomendado (por categoria) pra bater esse Boss NESSA dificuldade,
    achado por BUSCA BINÁRIA contra o motor de combate real (2026-09-02,
    correção do usuário: "se vc ta multiplicando em cima do personagem mais
    forte, vai ser impossível bater o recomendado" - a versão anterior
    multiplicava o CP do personagem mais forte do servidor por um fator
    fixo, o que confundia "CP de UMA personagem" com "CP AGREGADO da
    categoria no combate" - pra dificuldades mais altas, isso podia pedir
    mais CP do que qualquer agregado plausível alcançaria. Esta versão
    devolve o CP agregado que a PRÓPRIA simulação prova ser alcançável -
    nunca uma meta artificial). ~20 rodadas de busca binária (cada uma
    simulando alguns combates curtos) leva frações de segundo - aceitável
    rodar 1x por spawn (4x/dia)."""
    lo, hi = 0.0, 2_000_000.0
    mult = DIFICULDADES[dificuldade]["mult"]
    for _ in range(20):
        meio = (lo + hi) / 2
        if _taxa_vitoria_simulada(boss_tipo, mult, meio, n=12) >= META_VITORIA_CP_RECOMENDADO:
            hi = meio
        else:
            lo = meio
    return _arredondar_fechado(hi)


def _estado_inicial_mecanica(boss_tipo, categoria_dominante=None):
    dados = CATALOGO_BOSSES[boss_tipo]
    mecanica = dados["mecanica"]
    if mecanica == "adaptacao":
        return {"categoria_dominante": categoria_dominante}
    if mecanica == "renascimento":
        return {"renascimentos": 0}
    if mecanica == "barreira":
        return {"barreira_hp": dados["barreira_hp"], "barreira_viva": True}
    if mecanica == "consumir":
        return {"reducao_acumulada": 1.0}
    if mecanica == "posturas":
        return {"indice": 0}
    if mecanica == "cabecas":
        return {"vermelha_viva": True, "verde_viva": True, "roxa_viva": True}
    return {}


def multiplicador_cp(cp):
    """Multiplicador(CP) = 1 + √(CP / referência) - Seção 14, crescimento
    desacelerado (nunca 1:1) - evita "20.000 CP = 20.000 de dano"."""
    return 1.0 + math.sqrt(max(0.0, cp) / REFERENCIA_CP)


def categoria_dominante(soma_cp_por_categoria):
    """Categoria de maior CP agregado - Seção "Doppelgänger/Adaptação",
    decidida 1 VEZ no fechamento das inscrições (nunca recalculada durante
    o combate - o documento não fala em recalcular, e recalcular a cada
    turno tornaria a composição irrelevante pra essa mecânica)."""
    return max(soma_cp_por_categoria, key=soma_cp_por_categoria.get)


def escolher_melhor_personagem(guild_id, user_id, categorias_permitidas):
    """A personagem de MAIOR CP do jogador entre as categorias permitidas
    (Seção 4/5) - devolve (personagem, categoria_da_personagem, cp) ou
    (None, None, None) se não tiver nenhuma elegível. Selecionar as 3
    categorias equivale a "melhor CP da conta, categoria nenhuma importa"."""
    colecao = db.colecao_do_usuario(guild_id, user_id)
    if not colecao:
        return None, None, None
    niveis, bonus_global, cache_classe, bonus_series, favoritas_ocupantes = torre._contexto_lote(guild_id, user_id)
    melhor = None
    melhor_cp = -1.0
    melhor_categoria = None
    for personagem in colecao:
        categoria = torre.categoria_personagem(personagem)
        if categoria not in categorias_permitidas:
            continue
        nivel = niveis.get(personagem["id"], 1)
        cp, _nivel, _categoria = torre.power_personagem(
            personagem, guild_id, user_id, nivel=nivel, bonus_global=bonus_global, cache_bonus_classe=cache_classe,
            bonus_series=bonus_series, favoritas_ocupantes=favoritas_ocupantes,
        )
        if cp > melhor_cp:
            melhor, melhor_cp, melhor_categoria = personagem, cp, categoria
    if melhor is None:
        return None, None, None
    return melhor, melhor_categoria, melhor_cp


def iniciar_evento(guild_id, canal_id):
    """Sorteia um tipo de Boss (catálogo fechado, Seção 22) E, separado
    disso, uma dificuldade (2026-09-02, correção do usuário: "cada boss
    pode variar entre todas as dificuldades" - dificuldade não é mais fixa
    por Boss, qualquer um dos 10 pode sortear qualquer uma das 5) - abre a
    janela de inscrição (Seção 3) - devolve o `evento_id`. 🔥 Item 📯
    Chamado (2026-09-01) - se alguém usou um Chamado nesse servidor, o Boss
    ESCOLHIDO aparece no lugar do sorteio aleatório (consumido na hora,
    "não cria um evento adicional... determina qual Boss aparecerá em um
    dos horários normais") - só o TIPO é forçado, a dificuldade continua
    sorteada normalmente."""
    boss_tipo = db.consumir_worldboss_forcado(guild_id) or random.choice(list(CATALOGO_BOSSES.keys()))
    dificuldade = random.choice(list(DIFICULDADES.keys()))
    mult = DIFICULDADES[dificuldade]["mult"]
    dados = CATALOGO_BOSSES[boss_tipo]
    hp = dados["hp"] * mult
    atk = dados["atk"] * mult
    agora = datetime.now(timezone.utc)
    inscricoes_fecham_em = (agora + timedelta(minutes=DURACAO_INSCRICAO_MINUTOS)).isoformat()
    estado_mecanica = _estado_inicial_mecanica(boss_tipo)
    return db.worldboss_criar_evento(
        guild_id, canal_id, boss_tipo, hp, atk, estado_mecanica, inscricoes_fecham_em,
        dificuldade=dificuldade, cp_recomendado=cp_recomendado(boss_tipo, dificuldade),
    )


def alternar_categoria(evento_id, guild_id, user_id, categoria):
    """Alterna 1 categoria no conjunto permitido do jogador (Seção 4/5/6) -
    clicar na MESMA categoria de novo REMOVE ela do conjunto (toggle de
    verdade), o que dá pro jogador tanto entrar/ampliar quanto sair sem
    precisar de um botão "sair" separado - esvaziar o conjunto remove a
    participação. Devolve (ok, mensagem, personagem_ou_None, cp_ou_None) -
    `ok=False` só quando as inscrições já encerraram."""
    evento = db.worldboss_evento_por_id(evento_id)
    if evento is None or evento["status"] != "inscricoes":
        return False, "As inscrições desse World Boss já encerraram.", None, None
    participante_atual = db.worldboss_participante(evento_id, user_id)
    categorias_atuais = set(json.loads(participante_atual["categorias_selecionadas"])) if participante_atual else set()
    if categoria in categorias_atuais:
        categorias_atuais.discard(categoria)
    else:
        categorias_atuais.add(categoria)
    if not categorias_atuais:
        db.worldboss_remover_participante(evento_id, user_id)
        return True, "Você saiu do World Boss.", None, None
    personagem, categoria_escolhida, cp = escolher_melhor_personagem(guild_id, user_id, list(categorias_atuais))
    if personagem is None:
        db.worldboss_remover_participante(evento_id, user_id)
        return False, f"Você não tem nenhuma personagem classificada em {'/'.join(sorted(categorias_atuais))}.", None, None
    db.worldboss_definir_participante(
        evento_id, user_id, personagem["id"], categoria_escolhida, list(categorias_atuais), cp, origem="manual",
    )
    return True, f"Selecionada: {categoria_escolhida} **{personagem['nome']}** ({db.fmt_numero(cp)} CP).", personagem, cp


def _entrar_bots(evento_id, participantes_humanos, media_cp):
    """Seção 11 - prioridade 1: garantir 1 DPS + 1 Tank + 1 Support (até 2
    bots cobrem categorias faltando); prioridade 2: bot(s) sem categoria
    obrigatória reforçam a categoria de MENOR CP agregado até agora
    (critério escolhido pra "melhor contribuição disponível" - sem
    personagem própria pra bot escolher no modelo de CP-média, reforçar o
    elo mais fraco é a escolha mais defensável). Sempre EXATAMENTE 2 bots
    (`BOT_SLOTS`), nunca mais nem menos."""
    soma_cp = {"DPS": 0.0, "Tank": 0.0, "Support": 0.0}
    contagem = {"DPS": 0, "Tank": 0, "Support": 0}
    for p in participantes_humanos:
        contagem[p["categoria"]] += 1
        soma_cp[p["categoria"]] += p["cp"]

    categorias_bots = [c for c in CATEGORIAS if contagem[c] == 0]
    while len(categorias_bots) < len(BOT_SLOTS):
        soma_com_bots_ja_alocados = dict(soma_cp)
        for c in categorias_bots:
            soma_com_bots_ja_alocados[c] += media_cp
        categorias_bots.append(min(CATEGORIAS, key=lambda c: soma_com_bots_ja_alocados[c]))

    for indice, categoria in enumerate(categorias_bots[:len(BOT_SLOTS)]):
        db.worldboss_definir_participante(evento_id, BOT_SLOTS[indice], None, categoria, [categoria], media_cp, origem="bot")


def formar_time(evento_id):
    """Agrega CP por categoria (Seção 13) e converte pros atributos finais
    do time (Seção 14/15) - motor PURO, só lê `colecao_worldboss_
    participantes` (já inclui bots, se houver)."""
    participantes = db.worldboss_participantes(evento_id)
    soma_cp = {"DPS": 0.0, "Tank": 0.0, "Support": 0.0}
    qtd = {"DPS": 0, "Tank": 0, "Support": 0}
    for p in participantes:
        soma_cp[p["categoria"]] += p["cp"]
        qtd[p["categoria"]] += 1
    return {
        "participantes": len(participantes), "soma_cp": soma_cp, "qtd": qtd,
        "dano": DANO_BASE * multiplicador_cp(soma_cp["DPS"]),
        "hp": HP_BASE * multiplicador_cp(soma_cp["Tank"]),
        "cura": CURA_BASE * multiplicador_cp(soma_cp["Support"]),
    }


def _candidatos_5_estrela_elegiveis(guild_id, user_id, permitir_nsfw):
    """5★ do catálogo que ou (a) não têm dono nesse servidor, ou (b) já
    pertencem a ESTE jogador (Seção 2/3 do doc de recompensas) - exclui
    quem pertence a OUTRO jogador, pra garantir que a recompensa
    "garantida" sempre beneficie quem ganhou (nunca vira um roll de
    "terceiro" que premia outra pessoa em vez de quem lutou)."""
    ids_5_estrela = db.candidatos_por_raridade(guild_id, 5, None, permitir_nsfw)
    return [pid for pid in ids_5_estrela if db.dono_do_personagem(guild_id, pid) in (None, str(user_id), user_id)]


def _conquistas_situacionais(evento, resultado_time):
    """Condições que valem IGUAL pra todo participante dessa vitória
    (Seção 16 "Situações especiais" + "Tipos de Boss") - calculadas 1 vez
    só, fora do loop por jogador."""
    candidatas = []
    fracao_hp_final = (evento["time_hp_atual"] / evento["time_hp_maximo"]) if evento["time_hp_maximo"] else 0.0
    total_cp = sum(resultado_time["soma_cp"].values())
    fracao_dps = (resultado_time["soma_cp"]["DPS"] / total_cp) if total_cp else 0.0
    if evento["turno_atual"] >= LIMITE_TURNOS:
        candidatas.append("wb_ultimo_segundo")
    if fracao_hp_final < 0.05:
        candidatas.append("wb_por_um_fio")
    if fracao_hp_final >= 1.0:
        candidatas.append("wb_intocaveis")
    if fracao_dps > 0.70:
        candidatas.append("wb_ataque_total")
    if total_cp > 0:
        dominante = categoria_dominante(resultado_time["soma_cp"])
        if dominante == "Tank":
            candidatas.append("wb_fortaleza")
        elif dominante == "Support":
            candidatas.append("wb_sustentacao")
    conquista_boss = conquistas.BOSS_TIPO_PARA_CONQUISTA.get(evento["boss_tipo"])
    if conquista_boss:
        candidatas.append(conquista_boss)
    return candidatas


def _conquistas_por_vitoria_individual(guild_id, user_id, evento, resultado_time, candidatas_situacionais):
    candidatas = list(candidatas_situacionais)
    vitorias = db.contar_vitorias_worldboss(guild_id, user_id)
    if vitorias == 1:
        candidatas.append("wb_primeiro_sangue")
    if vitorias >= 10:
        candidatas.append("wb_cacador")
    if vitorias >= 100:
        candidatas.append("wb_veterano")
    if vitorias >= 1000:
        candidatas.append("wb_lenda_da_cacada")
    return [c for c in candidatas if conquistas.conceder(guild_id, user_id, c)]


def fechar_inscricoes(evento_id):
    """Ordem de entrada da Seção 10 (manuais já estão feitas até aqui):
    entrada automática dos ausentes -> bots -> composição fechada -> forma
    o time -> inicia o combate. Devolve (iniciou: bool, motivo_ou_None) -
    `iniciou=False` só quando NENHUM humano participou (Seção 11: "os bots
    nunca iniciam um World Boss sozinhos")."""
    evento = db.worldboss_evento_por_id(evento_id)
    guild_id = evento["guild_id"]

    ja_participantes = {p["user_id"] for p in db.worldboss_participantes(evento_id)}
    for user_id, categorias in db.worldboss_usuarios_auto_ativos(guild_id):
        if user_id in ja_participantes:
            continue
        personagem, categoria, cp = escolher_melhor_personagem(guild_id, user_id, categorias)
        if personagem is None:
            continue
        db.worldboss_definir_participante(evento_id, user_id, personagem["id"], categoria, categorias, cp, origem="automatica")

    participantes_humanos = db.worldboss_participantes(evento_id)
    if not participantes_humanos:
        db.worldboss_finalizar(evento_id, "cancelado_sem_participantes")
        return False, "Nenhum jogador participou - o World Boss foi cancelado."

    media_cp_humanos = sum(p["cp"] for p in participantes_humanos) / len(participantes_humanos)
    _entrar_bots(evento_id, participantes_humanos, media_cp_humanos)

    resultado_time = formar_time(evento_id)
    estado_mecanica = json.loads(evento["estado_mecanica"])
    if CATALOGO_BOSSES[evento["boss_tipo"]]["mecanica"] == "adaptacao":
        estado_mecanica["categoria_dominante"] = categoria_dominante(resultado_time["soma_cp"])
    proximo_turno_em = (datetime.now(timezone.utc) + timedelta(seconds=DURACAO_TURNO_SEGUNDOS)).isoformat()
    db.worldboss_iniciar_combate(
        evento_id, resultado_time["hp"], resultado_time["dano"], resultado_time["cura"], estado_mecanica, proximo_turno_em,
    )
    return True, None


def _montar_resultado(estado, boss_hp, boss_atk, time_hp, turno, linhas, resultado):
    terminou = resultado is not None
    proximo_turno_em = None if terminou else (datetime.now(timezone.utc) + timedelta(seconds=DURACAO_TURNO_SEGUNDOS)).isoformat()
    novo_estado = {
        "turno_atual": turno, "boss_hp_atual": max(0.0, boss_hp), "boss_atk_atual": boss_atk,
        "time_hp_atual": max(0.0, time_hp), "estado_mecanica": estado, "proximo_turno_em": proximo_turno_em,
    }
    return novo_estado, linhas, terminou, resultado


def executar_turno(evento):
    """Executa 1 turno (Seção 18/19) - devolve (novo_estado, linhas_de_log,
    terminou, resultado) onde `resultado` em {"vitoria", "derrota",
    "expirado_por_turnos", None} (None enquanto o combate continua). Motor
    PURO (sem discord.py) - `SchedulerWorldBoss` decide COMO postar o log.

    `boss_atk_atual` (persistido) só muda de verdade em Enfurecer (cresce
    10%/turno) e Renascimento (novo patamar por morte) - todo o resto
    (Adaptação-Tank/Barreira/Posturas-Ruína/Cabeça Vermelha/Caos) é um
    multiplicador TEMPORÁRIO só pra este turno (`atk_efetivo`), nunca
    gravado de volta."""
    tipo = evento["boss_tipo"]
    mecanica = CATALOGO_BOSSES[tipo]["mecanica"]
    estado = json.loads(evento["estado_mecanica"])
    turno = evento["turno_atual"] + 1

    boss_hp = evento["boss_hp_atual"]
    boss_hp_max = evento["boss_hp_maximo"]
    boss_atk = evento["boss_atk_atual"]
    time_hp = evento["time_hp_atual"]
    time_hp_max = evento["time_hp_maximo"]
    dano_base = evento["time_dano_turno"]
    cura_base = evento["time_cura_turno"]

    linhas = [f"**Turno {turno}**"]

    # --- Passo 1 (Seção 18): efeito especial do Boss, quando aplicável ---
    efeito_caos = None
    if mecanica == "caos":
        efeito_caos = random.choice(_EFEITOS_CAOS)
        linhas.append(f"🌌 CAOS! {efeito_caos['descricao']}")
    if mecanica == "ceifar" and turno % 3 == 0:
        dano_ceifar = time_hp_max * 0.30
        time_hp = max(0.0, time_hp - dano_ceifar)
        linhas.append(f"☠️ CEIFAR! O grupo perde {dano_ceifar:.0f} HP direto")
        if time_hp <= 0:
            return _montar_resultado(estado, boss_hp, boss_atk, time_hp, turno, linhas, "derrota")

    # --- Passo 2/3: time ataca, boss recebe dano ---
    dano = dano_base * random.uniform(1 - VARIACAO_TURNO, 1 + VARIACAO_TURNO)
    if mecanica == "adaptacao" and estado.get("categoria_dominante") == "DPS":
        dano *= 0.75
    if mecanica == "consumir":
        dano *= estado["reducao_acumulada"]
    if mecanica == "posturas" and _POSTURAS[estado["indice"]] == "Guerra":
        dano *= 0.70
    if efeito_caos:
        dano *= efeito_caos.get("mult_dano", 1.0)

    if mecanica == "barreira" and estado.get("barreira_viva"):
        absorvido = min(dano, estado["barreira_hp"])
        estado["barreira_hp"] -= absorvido
        excedente = dano - absorvido
        boss_hp = max(0.0, boss_hp - excedente)
        linhas.append(f"⚔️ O grupo atacou a Barreira! -{absorvido:.0f} HP (Barreira: {estado['barreira_hp']:.0f})")
        if excedente > 0:
            linhas.append(f"⚔️ Excedente atingiu o núcleo: -{excedente:.0f} HP")
        if estado["barreira_hp"] <= 0:
            estado["barreira_hp"] = 0.0
            estado["barreira_viva"] = False
            linhas.append("💥 Núcleo exposto! A Barreira se rompeu - o ATK do Boss aumenta.")
    else:
        boss_hp = max(0.0, boss_hp - dano)
        linhas.append(f"⚔️ O grupo atacou! -{dano:.0f} HP")

    if boss_hp <= 0:
        if mecanica == "renascimento" and estado["renascimentos"] < 2:
            estado["renascimentos"] += 1
            if estado["renascimentos"] == 1:
                boss_hp = boss_hp_max * 0.70
                boss_atk = evento["boss_atk_base"] * 1.20
                linhas.append(f"🔥 Renascimento! HP: {boss_hp:.0f} · ATK: {boss_atk:.0f}")
            else:
                boss_hp = boss_hp_max * 0.40
                boss_atk = evento["boss_atk_base"] * 1.40
                linhas.append(f"🔥 Segundo Renascimento! HP: {boss_hp:.0f} · ATK: {boss_atk:.0f}")
        else:
            return _montar_resultado(estado, 0.0, boss_atk, time_hp, turno, linhas, "vitoria")

    # --- Passo 4/5/6 (Seção 18): boss ataca, cura é calculada, e só ENTÃO o
    # HP do time muda por um dano líquido (dano causado pelo Boss - dano
    # curado no mesmo turno, pedido do usuário 2026-09-02) - corrige um bug
    # real: a versão anterior checava derrota logo depois do ataque do Boss,
    # ANTES de aplicar a cura (contrariando a própria Seção 18, que só
    # calcula o "estado final" no passo 7, depois do passo 6/cura) - isso
    # fazia o Support nunca conseguir evitar uma morte, exatamente quando
    # mais importa.
    atk_efetivo = boss_atk * random.uniform(1 - VARIACAO_TURNO, 1 + VARIACAO_TURNO)
    if mecanica == "adaptacao" and estado.get("categoria_dominante") == "Tank":
        atk_efetivo *= 1.25
    if mecanica == "barreira":
        atk_efetivo *= 0.70 if estado.get("barreira_viva") else 1.30
    if mecanica == "posturas" and _POSTURAS[estado["indice"]] == "Ruína":
        atk_efetivo *= 1.30
    if mecanica == "cabecas" and estado.get("vermelha_viva"):
        atk_efetivo *= 1.20
    if efeito_caos:
        atk_efetivo *= efeito_caos.get("mult_atk", 1.0)
    linhas.append(f"🐉 O Boss atacou! -{atk_efetivo:.0f} HP")

    if mecanica == "drenar_vida":
        curado_boss = atk_efetivo * 0.30
        boss_hp = min(boss_hp_max, boss_hp + curado_boss)
        linhas.append(f"🩸 Drenar Vida! O Boss recupera {curado_boss:.0f} HP")
    if mecanica == "cabecas" and estado.get("verde_viva"):
        regen = boss_hp_max * 0.03
        boss_hp = min(boss_hp_max, boss_hp + regen)
        linhas.append(f"💚 Cabeça Verde regenera {regen:.0f} HP")
    if efeito_caos and "cura_boss_percentual" in efeito_caos:
        cura_boss = boss_hp_max * efeito_caos["cura_boss_percentual"]
        boss_hp = min(boss_hp_max, boss_hp + cura_boss)
        linhas.append(f"❤️ O Boss recupera {cura_boss:.0f} HP")

    cura = cura_base * random.uniform(1 - VARIACAO_TURNO, 1 + VARIACAO_TURNO)
    if mecanica == "adaptacao" and estado.get("categoria_dominante") == "Support":
        cura *= 0.75
    if mecanica == "consumir":
        cura *= estado["reducao_acumulada"]
    if mecanica == "posturas" and _POSTURAS[estado["indice"]] == "Corrupção":
        cura *= 0.50
    if mecanica == "cabecas" and estado.get("roxa_viva"):
        cura *= 0.80
    teto_hp = time_hp_max
    if efeito_caos:
        cura *= efeito_caos.get("mult_cura", 1.0)
        if "bonus_hp_maximo" in efeito_caos:
            teto_hp = time_hp_max * (1 + efeito_caos["bonus_hp_maximo"])
    linhas.append(f"✨ O grupo se recuperou! +{cura:.0f} HP")

    dano_liquido = atk_efetivo - cura
    time_hp = max(0.0, min(teto_hp, time_hp - dano_liquido))

    if time_hp <= 0:
        return _montar_resultado(estado, boss_hp, boss_atk, 0.0, turno, linhas, "derrota")

    # --- Passo 7: pós-turno (mudanças persistentes/periódicas) ---
    if mecanica == "enfurecer":
        boss_atk = boss_atk * 1.10
        linhas.append(f"🔥 ENFURECER! ATK do Boss sobe pra {boss_atk:.0f}")
    elif mecanica == "consumir":
        estado["reducao_acumulada"] *= 0.95
        linhas.append(f"🌑 CONSUMIR! Redução acumulada do grupo: {(1 - estado['reducao_acumulada']) * 100:.0f}%")
    elif mecanica == "posturas":
        estado["indice"] = (estado["indice"] + 1) % 3
        linhas.append(f"👑 Nova postura: {_POSTURAS[estado['indice']]}")
    elif mecanica == "cabecas":
        fracao = boss_hp / boss_hp_max if boss_hp_max else 0.0
        if fracao <= 0.75 and estado.get("vermelha_viva"):
            estado["vermelha_viva"] = False
            linhas.append("🔥 Cabeça Vermelha destruída!")
        elif fracao <= 0.50 and estado.get("verde_viva"):
            estado["verde_viva"] = False
            linhas.append("💚 Cabeça Verde destruída!")
        elif fracao <= 0.25 and estado.get("roxa_viva"):
            estado["roxa_viva"] = False
            linhas.append("💜 Cabeça Roxa destruída!")

    if turno >= LIMITE_TURNOS:
        return _montar_resultado(estado, boss_hp, boss_atk, time_hp, turno, linhas, "expirado_por_turnos")
    return _montar_resultado(estado, boss_hp, boss_atk, time_hp, turno, linhas, None)


# ==========================================================================
# Discord - embeds compartilhados pelo scheduler (postagem automática) e
# pelo hub (`paineis.ViewWorldBossHub`, consulta sob demanda).
# ==========================================================================

# 🔥 Alias pra `db.fmt_numero` (2026-09-03, pedido do usuário: "separa por
# . as casas de todos os numeros") - era uma implementação PRÓPRIA idêntica
# em espírito à de `paineis.py` (mesma duplicação, unificada agora).
_fmt = db.fmt_numero


def _campo_dificuldade(evento):
    """Rótulo + valor pra Dificuldade/CP recomendado (2026-09-02) -
    compartilhado por `embed_aparicao`/`embed_status` - `cp_recomendado`
    fica `None` quando o servidor ainda não tinha nenhuma personagem
    reivindicada no spawn (nada de recomendado pra mostrar)."""
    dificuldade = evento.get("dificuldade")
    nome_dificuldade = DIFICULDADES[dificuldade]["nome"] if dificuldade in DIFICULDADES else (dificuldade or "?")
    if evento.get("cp_recomendado"):
        return nome_dificuldade, f"CP recomendado: {_fmt(evento['cp_recomendado'])}/categoria"
    return nome_dificuldade, "CP recomendado: -"


def embed_aparicao(evento):
    dados = CATALOGO_BOSSES[evento["boss_tipo"]]
    embed = discord.Embed(
        title=f"{dados['nome']} apareceu!",
        description=f"Inscrições abertas por {DURACAO_INSCRICAO_MINUTOS} minutos - escolha sua categoria em `/pandora` -> 🐉 World Boss.",
        color=0xC0392B,
    )
    embed.add_field(name="❤️ HP", value=_fmt(evento["boss_hp_maximo"]), inline=True)
    embed.add_field(name="⚔️ ATK", value=f"{_fmt(evento['boss_atk_base'])}/turno", inline=True)
    nome_dificuldade, valor_cp = _campo_dificuldade(evento)
    embed.add_field(name=f"🎯 Dificuldade: {nome_dificuldade}", value=valor_cp, inline=False)
    return embed


def embed_status(evento):
    """Painel do hub (`/pandora` -> 🐉 World Boss) - adapta ao `status` atual,
    sempre lido fresco do banco (mesmo padrão de `_ViewNivel`/`_ViewTorre`)."""
    dados = CATALOGO_BOSSES[evento["boss_tipo"]]
    embed = discord.Embed(title=dados["nome"], color=0xC0392B)
    if evento["status"] == "inscricoes":
        participantes = db.worldboss_participantes(evento["id"])
        contagem = {"DPS": 0, "Tank": 0, "Support": 0}
        for p in participantes:
            contagem[p["categoria"]] += 1
        fecha_em = datetime.fromisoformat(evento["inscricoes_fecham_em"])
        restante = max(0, int((fecha_em - datetime.now(timezone.utc)).total_seconds() // 60))
        embed.description = f"⏳ Inscrições abertas - encerram em ~{restante} min."
        embed.add_field(
            name="Participantes",
            value=f"⚔️ DPS: {contagem['DPS']} · 🛡️ Tank: {contagem['Tank']} · ✨ Support: {contagem['Support']}",
            inline=False,
        )
        embed.add_field(name="❤️ HP do Boss", value=_fmt(evento["boss_hp_maximo"]), inline=True)
        embed.add_field(name="⚔️ ATK do Boss", value=f"{_fmt(evento['boss_atk_base'])}/turno", inline=True)
        nome_dificuldade, valor_cp = _campo_dificuldade(evento)
        embed.add_field(name=f"🎯 Dificuldade: {nome_dificuldade}", value=valor_cp, inline=False)
    elif evento["status"] == "em_combate":
        embed.description = f"⚔️ Combate em andamento - Turno {evento['turno_atual']}."
        embed.add_field(name="❤️ Boss", value=f"{_fmt(evento['boss_hp_atual'])} / {_fmt(evento['boss_hp_maximo'])}", inline=True)
        embed.add_field(name="🛡️ Time", value=f"{_fmt(evento['time_hp_atual'])} / {_fmt(evento['time_hp_maximo'])}", inline=True)
        embed.add_field(
            name="Time do servidor",
            value=f"⚔️ Dano: {_fmt(evento['time_dano_turno'])}/turno · ✨ Cura: {_fmt(evento['time_cura_turno'])}/turno",
            inline=False,
        )
    else:
        embed.description = {
            "vitoria": "🏆 O servidor venceu o World Boss!",
            "derrota": "💀 O servidor foi derrotado pelo World Boss.",
            "expirado_por_turnos": "⏱️ O combate expirou pelo limite de turnos.",
            "cancelado_sem_participantes": "🚫 Cancelado - ninguém participou.",
        }.get(evento["status"], evento["status"])
    return embed


def embed_inicio_combate(evento, resultado_time):
    """Seção 15 - resumo do time recém-formado, mandado 1x quando as
    inscrições fecham e o combate começa de verdade."""
    dados = CATALOGO_BOSSES[evento["boss_tipo"]]
    embed = discord.Embed(title=f"⚔️ TIME DO SERVIDOR vs. {dados['nome']}", color=0x2ECC71)
    embed.add_field(name="Participantes", value=db.fmt_numero(resultado_time["participantes"]), inline=False)
    embed.add_field(
        name="⚔️ DPS", value=f"{resultado_time['qtd']['DPS']} · CP {_fmt(resultado_time['soma_cp']['DPS'])} · Dano {_fmt(resultado_time['dano'])}/turno",
        inline=False,
    )
    embed.add_field(
        name="🛡️ Tank", value=f"{resultado_time['qtd']['Tank']} · CP {_fmt(resultado_time['soma_cp']['Tank'])} · HP {_fmt(resultado_time['hp'])}",
        inline=False,
    )
    embed.add_field(
        name="✨ Support", value=f"{resultado_time['qtd']['Support']} · CP {_fmt(resultado_time['soma_cp']['Support'])} · Cura {_fmt(resultado_time['cura'])}/turno",
        inline=False,
    )
    embed.add_field(name="🐉 Boss", value=f"❤️ {_fmt(evento['boss_hp_maximo'])} · ⚔️ {_fmt(evento['boss_atk_base'])}/turno", inline=False)
    return embed


def embed_turno(evento, linhas, terminou, resultado):
    """Seção 20 - log de 1 turno."""
    dados = CATALOGO_BOSSES[evento["boss_tipo"]]
    cor = 0x2ECC71 if resultado == "vitoria" else 0xE74C3C if resultado in ("derrota", "expirado_por_turnos") else 0x3498DB
    embed = discord.Embed(title=f"{dados['nome']} - Turno {evento['turno_atual']}", description="\n".join(linhas), color=cor)
    embed.add_field(name="❤️ Time", value=f"{_fmt(evento['time_hp_atual'])} / {_fmt(evento['time_hp_maximo'])}", inline=True)
    embed.add_field(name="🐉 Boss", value=f"{_fmt(evento['boss_hp_atual'])} / {_fmt(evento['boss_hp_maximo'])}", inline=True)
    if terminou:
        embed.add_field(
            name="Resultado",
            value={
                "vitoria": "🏆 **VITÓRIA!** O servidor derrotou o Boss.",
                "derrota": "💀 **DERROTA.** O time foi derrotado.",
                "expirado_por_turnos": "⏱️ **Combate expirou** pelo limite de turnos.",
            }.get(resultado, resultado),
            inline=False,
        )
    return embed


# ==========================================================================
# Scheduler (discord.ext.tasks) - só roda na instância "principal" (mesmo
# critério de `auto_colecionador.AutoColecionadorUsuarios`), 3 checagens
# independentes por tick de 30s, cada uma 100% derivada do banco.
# ==========================================================================

class SchedulerWorldBoss:
    def __init__(self, client):
        self.client = client
        self._ultimo_spawn_por_guild = {}
        self._loop.start()

    def parar(self):
        self._loop.cancel()

    @tasks.loop(seconds=30)
    async def _loop(self):
        await self.client.wait_until_ready()
        try:
            await self._checar_spawn()
        except Exception as e:
            print(f" [ERIS] World Boss falhou ao checar spawn: {e}")
        try:
            await self._checar_fechamento_inscricoes()
        except Exception as e:
            print(f" [ERIS] World Boss falhou ao checar fechamento de inscrições: {e}")
        try:
            await self._checar_turnos()
        except Exception as e:
            print(f" [ERIS] World Boss falhou ao checar turnos: {e}")

    async def _checar_spawn(self):
        agora = datetime.now(FUSO_BRASILIA)
        if agora.minute != 0 or agora.hour not in HORARIOS_APARICAO:
            return
        marca = (agora.year, agora.month, agora.day, agora.hour)
        for guild in list(self.client.guilds):
            if self._ultimo_spawn_por_guild.get(guild.id) == marca:
                continue
            self._ultimo_spawn_por_guild[guild.id] = marca
            try:
                await self._spawnar_guild(guild)
            except Exception as e:
                print(f" [ERIS] World Boss falhou ao aparecer em {guild.id}: {e}")

    async def _spawnar_guild(self, guild):
        if await asyncio.to_thread(db.worldboss_evento_ativo, guild.id):
            return
        config = await asyncio.to_thread(db.obter_configuracao_colecao, guild.id)
        canal = auto_colecionador._canal_dos_rolls(guild, config)
        if canal is None:
            print(f" [ERIS] World Boss sem canal configurado em \"{guild.name}\" (configure com /colecao_admin canal).")
            return
        evento_id = await asyncio.to_thread(iniciar_evento, guild.id, canal.id)
        evento = await asyncio.to_thread(db.worldboss_evento_por_id, evento_id)
        try:
            await canal.send(
                content="🐉 **World Boss apareceu!** Abra `/pandora` -> 🐉 World Boss pra entrar.",
                embed=embed_aparicao(evento),
            )
        except discord.HTTPException:
            pass

    async def _checar_fechamento_inscricoes(self):
        agora = datetime.now(timezone.utc).isoformat()
        for evento_id in await asyncio.to_thread(db.worldboss_eventos_com_inscricoes_vencidas, agora):
            try:
                await self._fechar_evento(evento_id)
            except Exception as e:
                print(f" [ERIS] World Boss falhou ao fechar inscrições do evento {evento_id}: {e}")

    async def _fechar_evento(self, evento_id):
        iniciou, motivo = await asyncio.to_thread(fechar_inscricoes, evento_id)
        evento = await asyncio.to_thread(db.worldboss_evento_por_id, evento_id)
        canal = self.client.get_channel(int(evento["canal_id"])) if evento["canal_id"] else None
        if canal is None:
            return
        if not iniciou:
            try:
                await canal.send(f"🔒 Inscrições encerradas. {motivo}")
            except discord.HTTPException:
                pass
            return
        resultado_time = await asyncio.to_thread(formar_time, evento_id)
        try:
            await canal.send(content="🔒 **Inscrições encerradas!** O combate começou.", embed=embed_inicio_combate(evento, resultado_time))
        except discord.HTTPException:
            pass

    async def _checar_turnos(self):
        agora = datetime.now(timezone.utc).isoformat()
        for evento_id in await asyncio.to_thread(db.worldboss_eventos_com_turno_pendente, agora):
            try:
                await self._executar_e_postar_turno(evento_id)
            except Exception as e:
                print(f" [ERIS] World Boss falhou ao executar turno do evento {evento_id}: {e}")

    async def _executar_e_postar_turno(self, evento_id):
        evento = await asyncio.to_thread(db.worldboss_evento_por_id, evento_id)
        if evento is None or evento["status"] != "em_combate":
            return
        novo_estado, linhas, terminou, resultado = await asyncio.to_thread(executar_turno, evento)
        await asyncio.to_thread(
            db.worldboss_atualizar_turno, evento_id, novo_estado["turno_atual"], novo_estado["boss_hp_atual"],
            novo_estado["boss_atk_atual"], novo_estado["time_hp_atual"], novo_estado["estado_mecanica"],
            novo_estado["proximo_turno_em"] or datetime.now(timezone.utc).isoformat(),
        )
        if terminou:
            await asyncio.to_thread(db.worldboss_finalizar, evento_id, resultado)
        evento_atualizado = await asyncio.to_thread(db.worldboss_evento_por_id, evento_id)
        canal = self.client.get_channel(int(evento["canal_id"])) if evento["canal_id"] else None
        if canal is not None:
            try:
                await canal.send(embed=embed_turno(evento_atualizado, linhas, terminou, resultado))
            except discord.HTTPException:
                pass
        if terminou and resultado == "vitoria":
            try:
                await self._processar_recompensas_e_anunciar(evento_atualizado, canal)
            except Exception as e:
                print(f" [ERIS] World Boss falhou ao processar recompensas do evento {evento_id}: {e}")

    async def _conceder_5_estrela(self, guild_id, membro):
        """Seção 2/3 do doc de recompensas - sorteia 1 5★ elegível (sem
        dono OU já do jogador) e resolve via o MESMO motor de roll/
        reencontro (`gacha._resolver_resultado`) - "funciona exatamente
        como se tivesse obtido pelo fluxo normal". Devolve `(texto, personagem)`
        - os 2 `None` se não sobrar nenhuma 5★ elegível (catálogo pequeno
        demais/todas com outro dono - caso extremo, "balanceável depois").
        `personagem` (2026-09-02, pedido do usuário: "tbm quero q mostre a
        imagem da personagem 5* adquirida, assim como no roll") vai pro
        chamador montar o MESMO card com imagem de sempre
        (`consulta.embed_carta_personagem`) - devolvido daqui em vez de
        recalculado, já que já foi buscado (`db.personagem_por_id`) e
        resolvido (`gacha._resolver_resultado`)."""
        config = await asyncio.to_thread(db.obter_configuracao_colecao, guild_id)
        elegiveis = await asyncio.to_thread(
            _candidatos_5_estrela_elegiveis, guild_id, membro.id, config["nsfw_permitido"],
        )
        if not elegiveis:
            return None, None
        personagem_id = random.choice(elegiveis)
        personagem = await asyncio.to_thread(db.personagem_por_id, personagem_id)
        resultado = await asyncio.to_thread(gacha._resolver_resultado, guild_id, membro.id, personagem)
        tipo = resultado.get("resultado_tipo", "livre")
        if tipo == "livre":
            ok, _erro, _embed = await gacha._claim_sem_cooldown(guild_id, personagem_id, membro, "worldboss_recompensa")
            if not ok:
                return None, None
            return f"⭐ **{personagem['nome']}** (nova!)", personagem
        # 🔥 reencontro/reencontro_soulmate/reencontro_copia - já creditado
        # dentro de `_resolver_resultado` (Afinidade/WiShards/Soulstone),
        # sem chamada extra - Seção 3: "segue normalmente as regras
        # existentes de Afinidade/Soulmate/progressão por cópias".
        afinidade_txt = f" (Afinidade {resultado.get('afinidade_anterior', '?')} → {resultado.get('afinidade', '?')})" if tipo == "reencontro" else " (Soulmate!)" if tipo != "reencontro_copia" else " (cópia da Soulmate)"
        return f"⭐ **{personagem['nome']}**{afinidade_txt}", personagem

    async def _processar_recompensas_e_anunciar(self, evento, canal):
        """Seção 1-6/15-17 do doc de recompensas - só participantes
        HUMANOS (Seção 1: "os bots participam normalmente do combate, mas
        não recebem recompensas"). Recompensa individual vai por DM
        (Seção 17, "Suas recompensas" - pessoal, não faz sentido público
        pra um evento sem limite de participantes); resumo agregado
        (quem ganhou o quê, resumido) vai no canal."""
        guild_id = evento["guild_id"]
        guild = self.client.get_guild(int(guild_id))
        participantes = await asyncio.to_thread(db.worldboss_participantes, evento["id"])
        humanos = [p for p in participantes if p["origem"] != "bot"]
        resultado_time = await asyncio.to_thread(formar_time, evento["id"])
        candidatas_situacionais = await asyncio.to_thread(_conquistas_situacionais, evento, resultado_time)
        dados_boss = CATALOGO_BOSSES[evento["boss_tipo"]]

        linhas_publicas = []
        for p in humanos:
            user_id = p["user_id"]
            membro = guild.get_member(int(user_id)) if guild else None
            linhas = []
            personagem_5estrela = None
            if membro is not None:
                texto_estrela, personagem_5estrela = await self._conceder_5_estrela(guild_id, membro)
                if texto_estrela:
                    linhas.append(texto_estrela)
            await asyncio.to_thread(db.creditar_wishards, guild_id, user_id, RECOMPENSA_WISHARDS_VITORIA, "worldboss_vitoria")
            await asyncio.to_thread(db.creditar_xp_progressao, guild_id, user_id, RECOMPENSA_XP_VITORIA)
            await asyncio.to_thread(db.creditar_soulstone, guild_id, user_id, RECOMPENSA_SOULSTONE_VITORIA, "worldboss_vitoria")
            linhas.append(
                f"💎 +{db.fmt_numero(RECOMPENSA_WISHARDS_VITORIA)} WiShards · 📈 +{db.fmt_numero(RECOMPENSA_XP_VITORIA)} XP · "
                f"💠 +{db.fmt_numero(RECOMPENSA_SOULSTONE_VITORIA)} Soulstone",
            )
            item_raro = await asyncio.to_thread(itens.sortear_drop_raro)
            if item_raro:
                texto_item = await asyncio.to_thread(itens.conceder_item_drop, guild_id, user_id, item_raro)
                linhas.append(f"🎁 DROP RARO! {texto_item}")
            novas_conquistas = await asyncio.to_thread(
                _conquistas_por_vitoria_individual, guild_id, user_id, evento, resultado_time, candidatas_situacionais,
            )

            nome_exibicao = membro.display_name if membro else f"jogador {user_id}"
            linhas_publicas.append(f"**{nome_exibicao}**: " + " · ".join(linhas))
            if membro is not None:
                embed_dm = discord.Embed(
                    title="🏆 WORLD BOSS DERROTADO", description=f"{dados_boss['nome']} derrotado no turno {evento['turno_atual']}.",
                    color=0xF1C40F,
                )
                embed_dm.add_field(name="🎁 Suas recompensas", value="\n".join(linhas), inline=False)
                # 🔥 Card com imagem da 5★ ganha (2026-09-02, pedido do
                # usuário: "na recompensa da raid, tbm quero q mostre a
                # imagem da personagem 5* adquirida, assim como no roll") -
                # MESMO card usado em toda parte (`consulta.embed_carta_
                # personagem`, o roll/`🔍 Personagem` usam o idêntico) -
                # embed extra na MESMA DM, não substitui o resumo textual.
                embeds_dm = [embed_dm]
                if personagem_5estrela:
                    embeds_dm.append(consulta.embed_carta_personagem(personagem_5estrela))
                try:
                    await membro.send(embeds=embeds_dm)
                except discord.HTTPException:
                    pass
                for conquista_id in novas_conquistas:
                    dados_conquista = conquistas.CATALOGO[conquista_id]
                    try:
                        await membro.send(f"🏆 **NOVA CONQUISTA**\n{dados_conquista['nome']}\n{dados_conquista['descricao']}")
                    except discord.HTTPException:
                        pass

        if canal is not None and linhas_publicas:
            embed_publico = discord.Embed(
                title="🎁 Recompensas da vitória", description="\n".join(linhas_publicas), color=0xF1C40F,
            )
            try:
                await canal.send(embed=embed_publico)
            except discord.HTTPException:
                pass
