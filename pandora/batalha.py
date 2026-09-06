# -*- coding: utf-8 -*-
"""Batalha 5x5 com Aposta de Personagem (2026-09-01) - spec completa
trazida pelo usuário (ver `PANDORA_batalha_5x5_aposta.md`, raiz deste
repo). PvP 1 contra 1: cada jogador monta uma formação de 5 posições.

🔥 Formação por CATEGORIA (2026-09-02, substitui a Party original - pedido
do usuário: "em vez de eu ter q escolher os personagens q vao participar,
deixar escolher apenas as categorias e suas posições") - o jogador só
escolhe DPS/Tank/Support pra cada uma das 5 posições
(`montar_formacao_por_categoria`). A Party (`colecao_equipe` tipo="party")
continua existindo, só que agora é EXCLUSIVA da Torre (que se importa com
CP/Nível/Afinidade de verdade); Batalha nunca olha CP, só categoria, então
não fazia sentido depender da curadoria manual da Party.

🔥 Sem exigir posse de personagem NENHUMA (2026-09-02, correção do
usuário: "Nem deveria importar se eu tenho personagens ou n, oq estou
definindo é apenas a classe, e o CP n importa de qq forma") - a 1ª versão
escolhia a MELHOR personagem (maior CP) que o jogador possuía de cada
categoria e guardava o `personagem_id`, mas isso nunca teve função
nenhuma (o Jokenpô só olha a categoria) e quebrava a defesa AUTOMÁTICA de
bots quando a conta não tinha personagem suficiente de alguma categoria
sorteada pela defesa aleatória de então, travando o desafio pra sempre em
`aguardando_defensor`. `ordem_desafiante`/`ordem_defensor` guardam a
CATEGORIA direto agora, sem `personagem_id` nenhum no meio.

🔥 Enfrentar bot (2026-09-02, pedido do usuário: "tem q ser possivel eu
enfrentar bot") - desafiar uma personagem de uma conta de bot (GAIA/ERIS,
donas via auto-colecionador) funciona igual a desafiar um jogador
qualquer, só que a "defesa" é auto-montada na hora (`defesa_automatica`) e
a batalha resolve IMEDIATAMENTE - a conta de bot não abre o próprio hub
pra responder. Desafiar um jogador HUMANO continua esperando resposta de
verdade - `aguardando_defensor` até ele montar defesa, recusar, ou
**Auto-Defesa** entrar em ação (2026-09-02, pedido do usuário: "Se o
desafiado n responder em 10min, considera essa defesa automatica...
É possivel deixar configurado p players tbm") - substitui o cancelamento
por inatividade de 24h antigo:
- Sem responder em `paineis.SchedulerBatalha.LIMITE_MINUTOS_AUTO_DEFESA`
  (10) minutos → resolve sozinho com `defesa_automatica` (mesma lógica do
  bot) e anuncia no canal onde o desafio nasceu.
- Jogador pode LIGAR isso de propósito (`db.auto_defesa_batalha_ativa`,
  desligado por padrão) pra ser defendido igual a um bot, na hora, sem
  nem esperar os 10min - resposta MANUAL sempre tem prioridade se ele
  responder primeiro.

Diferente da Torre: CP NÃO decide o resultado aqui (Seção 4/18) - é
Jokenpô de categoria de combate (DPS > Support > Tank > DPS, Seção 5/6)
posição a posição, revelado 1 confronto por vez até alguém fechar 3
vitórias (Seção 11). 🔥 Morte Súbita REMOVIDA (2026-09-02, pedido do
usuário - ver `resolver_rodadas`) - se ninguém fechar 3 depois das 5
posições, quem tiver MAIS vitórias ganha; empate de verdade (placar
igual) vai pro DESAFIANTE, que joga em desvantagem informacional (Seção
8: o defensor vê a composição dele antes de montar a própria defesa).

Desafiante arrisca `preço da Loja daquela raridade × 2` em WiShards (Seção
2, corrigido 2026-09-01) - 🔥 esse valor NUNCA é debitado na criação do
desafio (correção do usuário, 3ª rodada: "se o desafiante ganha, ele não
precisa pagar") - só é checado (ele precisa TER o suficiente) até a
resolução. Se ele vencer: a personagem transfere pra ele e NADA é
debitado (vencer não custa WiShards, só perder custa). Se o defensor
vencer: ele MANTÉM a personagem e SÓ AÍ a aposta sai de verdade da conta
do desafiante, creditada pra ele. Soulmate/item Proteção protegem
permanentemente contra desafio (Seção 14). Preço de mercado = `db.
PRECOS_LOJA` (Seção 16 deixa a fórmula exata como "decisão separada" -
reaproveita a MESMA referência de preço já usada na Loja, nunca um preço de
troca manipulável).

Estado 100% em `colecao_batalha_desafios` (nunca em memória do processo) -
qualquer View pode reconstruir o desafio inteiro a partir do banco a
qualquer momento (mesmo padrão de `_ViewNivel`/`_ViewTorre`, "sempre lê
estado FRESCO"), então um restart do bot no meio de um desafio não perde
WiShards nem trava ninguém - o hub "⚔️ Batalha" sempre relê o estado."""
import json
import random

from pandora import db

# 🔥 Jokenpô fechado (Seção 5/6) - cada categoria vence exatamente 1 e
# perde pra exatamente 1, nunca duas superiores/inferiores (senão
# quebraria a simetria 33,3%/33,3%/33,3% contra uma escolha desconhecida
# que a Seção 5 exige).
_VENCE_DE = {"DPS": "Support", "Support": "Tank", "Tank": "DPS"}

COOLDOWN_HORAS = 24  # Seção 15 - mesmo par desafiante->defensor
LIMITE_DEFESAS_POR_DIA = 3  # Seção 15 - por DEFENSOR, qualquer desafiante
VITORIAS_PARA_GANHAR = 3  # Seção 11


def preco_mercado(personagem):
    """"Preço de mercado" (Seção 16, "a definição exata... fica como
    decisão separada") - 🔥 2026-09-01, correção do usuário: "tem de ser o
    valor daquela raridade na loja... multiplica por 2" - usa `db.
    PRECOS_LOJA` (o preço de "Comprar" da Loja pra essa raridade, já
    escalado por raridade sozinho) × 2, substituindo a 1ª versão
    (`db.valor_base_wishards`, raridade×20, multiplicada de novo pela
    raridade - dava só 500 WiShards de aposta pra um 5⭐, baixo demais
    comparado ao preço de 5.000 da própria Loja pra comprar um)."""
    return db.PRECOS_LOJA[personagem["raridade"]] * 2


def calcular_aposta(personagem):
    """Aposta = Preço de Mercado (Seção 2) - já inclui o ×2 (2026-09-01),
    NÃO multiplica de novo pela raridade (`PRECOS_LOJA` já escala por
    raridade)."""
    return preco_mercado(personagem)


def resolver_confronto(categoria_a, categoria_b):
    """1 se A vence, -1 se B vence, 0 se empate (Seção 5/6 - mesma
    categoria SEMPRE empata, CP nunca desempata). Categoria `None`
    (personagem nunca classificada) só empata contra qualquer coisa - não
    existe no vocabulário do Jokenpô, mas não deveria travar a batalha."""
    if categoria_a == categoria_b:
        return 0
    if _VENCE_DE.get(categoria_a) == categoria_b:
        return 1
    if _VENCE_DE.get(categoria_b) == categoria_a:
        return -1
    return 0


def composicao(categorias):
    """{"DPS": n, "Tank": n, "Support": n} (Seção 8) - o que o DEFENSOR vê
    antes de montar a defesa: só a contagem, nunca quem/CP/ordem."""
    return {"DPS": categorias.count("DPS"), "Tank": categorias.count("Tank"), "Support": categorias.count("Support")}


CATEGORIAS_VALIDAS = ("DPS", "Tank", "Support")


def montar_formacao_por_categoria(categorias_ordem):
    """🔥 Só valida e devolve a ORDEM DE CATEGORIAS diretamente (2026-09-02,
    correção do usuário depois de achar 2 bugs vindos da mesma causa: "Nem
    deveria importar se eu tenho personagens ou n, oq estou definindo é
    apenas a classe, e o CP n importa de qq forma") - a versão anterior
    escolhia a MELHOR personagem que o jogador possuía de cada categoria e
    guardava o `personagem_id`, mas isso nunca teve função nenhuma: Batalha
    "nunca olha CP, só categoria" (Seção 4/18 - Jokenpô puro), e a única
    coisa que `_categorias_da_ordem` fazia com aquele `personagem_id` era
    reconverter ele de volta pra categoria. Exigir posse suficiente de cada
    categoria (a) trava o jogador sem motivo (não é o que decide o
    resultado) e (b) quebrava a defesa AUTOMÁTICA de bots - `formacao_
    aleatoria()` sorteia categoria sem saber o que a conta de bot possui de
    verdade, então "faltam Tanks" podia estourar tentando montar a DEFESA
    do bot, travando o desafio em `aguardando_defensor` pra sempre (achado
    real, desafio #2 - Artoria Pendragon). Devolve (ordem_categorias,
    erro_ou_None)."""
    if len(categorias_ordem) != db.MAX_POSICOES_EQUIPE:
        return None, f"Escolha exatamente {db.MAX_POSICOES_EQUIPE} categorias."
    if any(categoria not in CATEGORIAS_VALIDAS for categoria in categorias_ordem):
        return None, "Categoria inválida - só DPS, Tank ou Support."
    return list(categorias_ordem), None


def composicao_ordem(ordem_categorias):
    return composicao(ordem_categorias)


def iniciar_desafio(guild_id, desafiante_id, defensor_id, personagem_id, categorias_ordem, _ignorar_cooldown_e_limite=False, canal_id=None):
    """Valida tudo (Seções 1/7/14/15) e cria o desafio - devolve (ok,
    erro_ou_None, desafio_id_ou_None).

    `categorias_ordem` (2026-09-02, substitui a Party como formação - ver
    `montar_formacao_por_categoria`) - 5 categorias na ordem escolhida
    pelo desafiante; o sistema monta a formação sozinho com as melhores
    personagens de cada categoria.

    🔥 2026-09-01, correção do usuário: "se o desafiante ganha, ele não
    precisa pagar" - a aposta NÃO é mais debitada na criação do desafio
    (só checa se ele TEM o suficiente, sem tirar nada ainda). O débito de
    verdade só acontece se ele PERDER (`_finalizar_vitoria_defensor`) -
    vencer não custa WiShards nenhum, só a personagem que ele ganha muda
    de mão.

    `_ignorar_cooldown_e_limite` (uso interno - `iniciar_desafio_com_
    revanche` é o único caller que passa True) pula SÓ o cooldown de 24h e
    o limite diário de defesas (Seção 8 do item Revanche: "não devolve
    automaticamente... ainda precisa disputar através das regras da
    batalha" - todo o RESTO da validação continua valendo, inclusive
    Soulmate/Proteção/aposta/Party completa)."""
    desafiante_id, defensor_id = str(desafiante_id), str(defensor_id)
    if desafiante_id == defensor_id:
        return False, "Você não pode desafiar a si mesmo.", None
    if db.batalha_ativa_do_jogador(guild_id, desafiante_id):
        return False, "Você já está em uma batalha ativa - resolva ela antes de abrir outra.", None
    if db.batalha_ativa_do_jogador(guild_id, defensor_id):
        return False, "Esse jogador já está em uma batalha ativa agora - tenta de novo depois.", None
    personagem = db.personagem_por_id(personagem_id)
    if personagem is None:
        return False, "Personagem não encontrada.", None
    if str(db.dono_do_personagem(guild_id, personagem_id)) != defensor_id:
        return False, "Esse jogador não tem (mais) essa personagem.", None
    if db.is_soulmate(guild_id, defensor_id, personagem_id):
        return False, "💕 Personagens Soulmate são protegidas contra desafios.", None
    if db.esta_protegida_pvp(guild_id, defensor_id, personagem_id):
        return False, "🛡️ Essa personagem está protegida (item Proteção) contra desafios.", None
    if not _ignorar_cooldown_e_limite:
        # 🔥 Cooldown de 24h entre desafios ao MESMO jogador virou opcional
        # por servidor (2026-09-02, pedido do usuário: "remove esse
        # bloqueio... deixa ele opcional e desmarcado por padrao") -
        # DESLIGADO por padrão (`cooldown_batalha_ativo`, `/colecao_admin`
        # liga de volta pra quem quiser). O limite diário de defesas
        # continua sempre ativo - só o cooldown por PAR desafiante/
        # defensor que virou opcional.
        if db.obter_configuracao_colecao(guild_id)["cooldown_batalha_ativo"] and not db.cooldown_batalha_ok(guild_id, desafiante_id, defensor_id):
            return False, f"Espera pelo menos {COOLDOWN_HORAS}h entre desafios ao MESMO jogador.", None
        if db.defesas_hoje(guild_id, defensor_id) >= LIMITE_DEFESAS_POR_DIA:
            return False, "Esse jogador já recebeu desafios demais hoje - tenta de novo amanhã.", None
    ordem_desafiante, erro_formacao = montar_formacao_por_categoria(categorias_ordem)
    if ordem_desafiante is None:
        return False, erro_formacao, None
    aposta = calcular_aposta(personagem)
    if db.saldo_wishards(guild_id, desafiante_id) < aposta:
        return False, (
            f"Você precisa de {db.fmt_numero(aposta)} WiShards em risco pra desafiar por essa personagem "
            f"(raridade {personagem['raridade']} × {db.fmt_numero(preco_mercado(personagem))} de preço de mercado)."
        ), None

    desafio_id = db.criar_desafio_batalha(guild_id, desafiante_id, defensor_id, personagem_id, aposta, ordem_desafiante, canal_id=canal_id)
    db.registrar_desafio_cooldown(guild_id, desafiante_id, defensor_id)
    db.registrar_defesa_hoje(guild_id, defensor_id)
    return True, None, desafio_id


def iniciar_desafio_com_revanche(guild_id, desafiante_id, defensor_id, personagem_id, categorias_ordem, canal_id=None):
    """Item ⚔️ Revanche (2026-09-01) - só se aplica a uma personagem que
    `desafiante_id` REALMENTE perdeu numa Batalha 5x5 anterior e ainda não
    recuperou; consome 1 Revanche e ignora cooldown/limite diário (ver
    `iniciar_desafio`). Devolve (ok, erro_ou_None, desafio_id_ou_None)."""
    if not db.personagem_perdida_por(guild_id, personagem_id, desafiante_id):
        return False, "Você não perdeu essa personagem numa Batalha 5x5 - Revanche não se aplica.", None
    if not db.consumir_item(guild_id, desafiante_id, "revanche", 1):
        return False, "Você não tem nenhuma Revanche.", None
    return iniciar_desafio(
        guild_id, desafiante_id, defensor_id, personagem_id, categorias_ordem,
        _ignorar_cooldown_e_limite=True, canal_id=canal_id,
    )


def montar_defesa(guild_id, desafio_id, defensor_id, categorias_ordem):
    """Defensor monta a formação de defesa por CATEGORIA (2026-09-02,
    substitui a Party - ver `montar_formacao_por_categoria`; ele já viu a
    composição do desafiante antes de montar, Seção 8). Devolve (ok,
    erro_ou_None, desafio_atualizado_ou_None)."""
    desafio = db.batalha_por_id(desafio_id)
    if desafio is None or desafio["status"] != "aguardando_defensor":
        return False, "Esse desafio não existe mais ou já foi resolvido.", None
    if str(desafio["defensor_id"]) != str(defensor_id):
        return False, "Esse desafio não é seu.", None
    if str(db.dono_do_personagem(guild_id, desafio["personagem_id"])) != str(defensor_id):
        db.cancelar_desafio_batalha(desafio_id)
        return False, "Você não tem mais essa personagem - desafio cancelado.", None
    ordem_defensor, erro_formacao = montar_formacao_por_categoria(categorias_ordem)
    if ordem_defensor is None:
        return False, erro_formacao, None
    db.definir_ordem_defensor(desafio_id, ordem_defensor)
    return True, None, db.batalha_por_id(desafio_id)


def defesa_automatica(ordem_desafiante):
    """Auto-Defesa (2026-09-02, pedido do usuário, substitui `formacao_
    aleatoria` - "ele vai considerar cada escolha do desafiante, e montar
    sua escolha com base no q venceria ela, se tem 5 papel, ele pega 5
    tesoura") - pra CADA categoria do desafiante, escolhe quem BATE nela
    (Jokenpô, `_VENCE_DE` invertido), "e distribui em ordem aleatória" -
    embaralha a ORDEM antes de devolver, nunca alinhado 1:1 pela posição
    original (só garante que o CONJUNTO é o counter perfeito, não que
    TODA rodada individual vai bater certinho - a posição embaralhada
    ainda pode perder pontualmente contra a ordem congelada do
    desafiante). Usada tanto pra bots (GAIA/ERIS, "bots respondem na hr
    com essa lógica") quanto por jogadores com Auto-Defesa ligada ou que
    não responderam em `paineis.SchedulerBatalha.LIMITE_MINUTOS_AUTO_
    DEFESA`."""
    contra = {vencido: vencedor for vencedor, vencido in _VENCE_DE.items()}
    escolhas = [contra[categoria] for categoria in ordem_desafiante]
    random.shuffle(escolhas)
    return escolhas


def defesa_automatica_para_desafio(desafio_id):
    """Mesma coisa que `defesa_automatica`, mas lendo a ordem do
    desafiante direto do banco - conveniência pra quem só tem o
    `desafio_id` à mão (o caminho comum, `paineis.py`/`SchedulerBatalha`)."""
    desafio = db.batalha_por_id(desafio_id)
    return defesa_automatica(json.loads(desafio["ordem_desafiante"]))


def recusar_desafio(desafio_id, defensor_id):
    """Recusar não é RENDER a personagem - Seção 1 deixa claro que o
    desafiante reivindica direto, sem depender do dono topar, então
    "recusar" aqui só cancela (equivalente a nunca montar defesa) - existe
    pra o defensor não precisar esperar o desafio ficar parado
    indefinidamente se não quiser lutar. 🔥 2026-09-01 - sem reembolso
    nenhum: desde que a aposta parou de ser debitada na criação do
    desafio ("se o desafiante ganha, ele não precisa pagar"), cancelar
    nunca tirou WiShards de ninguém pra começar."""
    desafio = db.batalha_por_id(desafio_id)
    if desafio is None or desafio["status"] != "aguardando_defensor":
        return False, "Esse desafio não existe mais ou já foi resolvido."
    if str(desafio["defensor_id"]) != str(defensor_id):
        return False, "Esse desafio não é seu."
    db.cancelar_desafio_batalha(desafio_id)
    return True, None


# 🔥 `cancelar_expirados` (cancelamento por inatividade de 24h, sob
# demanda no hub) REMOVIDA (2026-09-02, pedido do usuário - Auto-Defesa
# substitui isso) - `paineis.SchedulerBatalha` resolve sozinho (nunca só
# cancela) qualquer desafio esquecido depois de só 10 minutos, rodando em
# background - o cancelamento de 24h nunca chegaria a executar primeiro.


def resolver_rodadas(categorias_a, categorias_b):
    """Resolve as 5 posições EM ORDEM, parando assim que alguém fechar 3
    vitórias (Seção 11) - devolve (rodadas, placar_desafiante,
    placar_defensor, vencedor) onde `rodadas` é uma lista de dicts
    (posicao, categoria_a, categoria_b, resultado) na ordem jogada (pode
    ter menos de 5 se decidiu antes) e `vencedor` é SEMPRE "desafiante" ou
    "defensor", nunca `None` (2026-09-02, correção do usuário - ver
    abaixo). Motor PURO (sem discord.py) - quem chama (`paineis.
    _resolver_e_revelar`) decide COMO revelar (edições sucessivas com
    pausa, pro suspense da Seção 10). `categorias_a`/`categorias_b` já são
    listas de categoria (2026-09-02 - `ordem_desafiante`/`ordem_defensor`
    guardam a categoria direto agora, não mais um `personagem_id`
    intermediário sem função).

    🔥 Mecânica de Morte Súbita REMOVIDA (2026-09-02, 2 achados do usuário
    na MESMA mensagem, revisando uma batalha real): 1) o placar só
    comparava contra `VITORIAS_PARA_GANHAR` (3) - um resultado tipo 1x2
    (ninguém fechou 3, mas os placares NÃO são iguais) caía em `vencedor =
    None` e ia pra Morte Súbita à toa, mesmo o defensor já estando
    claramente na frente ("Nesse tipo de empate, nem deveria ir p morte
    subita"); 2) mesmo num empate DE VERDADE (placar igual), o usuário
    pediu pra tirar a Morte Súbita inteira e o DESAFIANTE vencer direto -
    "se por acaso terminar 2x2, o desafiante vence, ja q ele estava em
    desvantagem por permitir o adversario ver suas escolhas" (Seção 8: o
    defensor vê a COMPOSIÇÃO do desafiante antes de montar a própria
    defesa - vantagem informacional real que a Morte Súbita não
    compensava)."""
    rodadas = []
    placar_a = placar_b = 0
    for posicao in range(min(len(categorias_a), len(categorias_b))):
        resultado = resolver_confronto(categorias_a[posicao], categorias_b[posicao])
        if resultado == 1:
            placar_a += 1
        elif resultado == -1:
            placar_b += 1
        rodadas.append({
            "posicao": posicao + 1, "categoria_a": categorias_a[posicao], "categoria_b": categorias_b[posicao],
            "resultado": resultado,
        })
        if placar_a >= VITORIAS_PARA_GANHAR or placar_b >= VITORIAS_PARA_GANHAR:
            break
    if placar_b > placar_a:
        vencedor = "defensor"
    else:
        # 🔥 `placar_a >= placar_b` cai tudo aqui de propósito - cobre
        # tanto o desafiante fechando 3 (ou tendo mais rodadas) quanto o
        # empate genuíno (placar igual), que o desafiante vence por regra
        # agora, nunca mais Morte Súbita.
        vencedor = "desafiante"
    return rodadas, placar_a, placar_b, vencedor


def _finalizar_vitoria_desafiante(desafio):
    """Seção 3/13 - transferência PERMANENTE (`db.transferir_personagem`
    já garante que Afinidade NUNCA acompanha, mesma regra de sempre).
    🔥 2026-09-01, correção do usuário (3ª rodada - "se o desafiante ganha,
    ele não precisa pagar") - NENHUMA movimentação de WiShards aqui: a
    aposta só existe como RISCO (checado em `iniciar_desafio`), nunca
    debitada de verdade quando ele vence - só perde WiShards se PERDER
    (`_finalizar_vitoria_defensor`, que debita dele e credita o defensor
    NA HORA da derrota, não antes)."""
    guild_id, personagem_id = desafio["guild_id"], desafio["personagem_id"]
    db.transferir_personagem(guild_id, personagem_id, desafio["desafiante_id"])
    # 🔥 Revanche (2026-09-01) - registra a personagem como PERDIDA pelo
    # defensor (pra ele poder tentar recuperar via item Revanche depois);
    # se o DESAFIANTE que acabou de vencer já tinha perdido ESSA MESMA
    # personagem antes, marca como recuperada (fecha o ciclo, com ou sem
    # Revanche de verdade - qualquer vitória de volta conta).
    db.registrar_personagem_perdida(guild_id, personagem_id, desafio["defensor_id"])
    if db.personagem_perdida_por(guild_id, personagem_id, desafio["desafiante_id"]):
        db.marcar_personagem_recuperada(guild_id, personagem_id, desafio["desafiante_id"])


def _finalizar_vitoria_defensor(desafio):
    """Seção 3 - defensor MANTÉM a personagem + recebe a aposta. 🔥
    2026-09-01 - esta é a ÚNICA hora em que a aposta de verdade sai da
    conta do desafiante (nunca na criação do desafio) - perder é o que
    custa WiShards, vencer não custa nada."""
    db.creditar_wishards(
        desafio["guild_id"], desafio["defensor_id"], desafio["aposta_wishards"],
        "batalha_vitoria_defesa", None, str(desafio["id"]),
    )
    db.creditar_wishards(
        desafio["guild_id"], desafio["desafiante_id"], -desafio["aposta_wishards"],
        "batalha_perdeu_aposta", None, str(desafio["id"]),
    )


def concluir_batalha(desafio, placar_desafiante, placar_defensor, vencedor):
    """Aplica o resultado final e marca a linha 'concluida' - só chamado
    depois de `vencedor` decidido (nunca None aqui)."""
    if vencedor == "desafiante":
        _finalizar_vitoria_desafiante(desafio)
    else:
        _finalizar_vitoria_defensor(desafio)
    db.finalizar_desafio_batalha(desafio["id"], placar_desafiante, placar_defensor)


def papel_do_jogador(desafio, user_id):
    """"desafiante"/"defensor"/None - `None` se esse jogador não faz parte
    desse desafio."""
    user_id = str(user_id)
    if user_id == str(desafio["desafiante_id"]):
        return "desafiante"
    if user_id == str(desafio["defensor_id"]):
        return "defensor"
    return None
    return True, vencedor
