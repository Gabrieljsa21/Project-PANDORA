# -*- coding: utf-8 -*-
"""Auto-colecionador: a própria conta de bot (GAIA no papel "principal", ERIS
no papel "musica") também joga o Colecionador como uma jogadora comum -
pedido do usuário (2026-08-29): "coloca para a gaia e a eris tbm coletarem
personagens, cada uma roda seus 50 tiros, a gaia vai rodar sempre aos XX:05,
e apos 5min, vai escolher o de maior raridade, a eris fara o mesmo, mas
rodará aos XX:30 e escolhe aos XX:35".

🔥 Rolls são VISÍVEIS de verdade (2026-08-29, correção do usuário: "os rolls
q os bots fazem tem q mostrar as opcoes, igual os meus. é literalmente
rodar /wa 10 5x") - nada de sortear em memória e só anunciar o resultado
final: cada lote de 10 vira uma mensagem de verdade no canal configurado,
com os MESMOS embeds + botões de Reivindicar (`gacha.montar_embed`/
`ViewClaimMultiplo`) de um `/wa 10` normal. Qualquer humano pode clicar e
levar qualquer uma delas nesse meio tempo - a conta de bot só entra na
jogada 5 minutos depois: "ai da 5min p alguem tentar pegar algum, ele tira
da lista das escolhas os q ja foram pegos, e pega o mais popular" - re-
consulta quem ainda está sem dono entre as que rolou e fica com a mais
POPULAR (não a de maior raridade) dentre as que sobraram.

Cada instância roda no seu próprio horário FIXO (`HORARIOS_POR_PAPEL`).
Reaproveita o motor de `eris/colecao/gacha.py` (`rolar_sem_cooldown`/
`montar_embed`/`ViewClaimMultiplo`/`revelar_classe`) SEM passar pelo
cooldown normal de rolls/claims - a conta do bot tem sua PRÓPRIA linha em
`colecao_estado_jogador`, mas essa linha nunca é lida/escrita por esse
fluxo; é uma mecânica separada.

🔥 Quantidade de tiros SEGUE o máximo configurado no servidor (2026-09-03,
pedido do usuário: "os rolls q os bots fazem tem de ser de acordo com os
maximos permitidos por server") - antes era um número FIXO (`QUANTIDADE_
TIROS = 50`, removido), ignorando totalmente `/pandora_admin rolls` -
usa `config["rolls_por_ciclo"]` (o mesmo valor que rege o roll normal de
QUALQUER jogador humano no servidor), sem somar upgrades/bônus permanentes
de rolls (esses são investimento PESSOAL de jogador de verdade - a conta
de bot nunca compra nenhum, `rolar_sem_cooldown` nem olha pra
`colecao_estado_jogador` dela)."""
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import tasks

from pandora import db, gacha

# 🔥 Minuto de disparo (roll) e de decisão (claim) por papel - pedido
# explícito do usuário. Só os papéis "principal" (GAIA) e "musica" (ERIS)
# jogam - qualquer outro papel futuro fica de fora até o usuário pedir.
# 🔥 "completo" -> "principal" (2026-09-04, "Faz sentido esse nome
# 'Completo'?" -> "Pode renomear para Principal") - mesma chave, MESMO
# papel passado por `eris/bot.py::iniciar_bot`, só o nome mudou.
HORARIOS_POR_PAPEL = {
    "principal": {"minuto_roll": 5, "minuto_claim": 10},
    "musica": {"minuto_roll": 30, "minuto_claim": 35},
}


async def _reivindicar_varios(guild_id, pendentes, quantidade_maxima, claim_fn):
    """Núcleo compartilhado de "reivindica até N das que sobraram livres,
    sempre a mais popular primeiro" (2026-09-04, pedido do usuário: "A
    ideia é consumir todos os claim q tem disponivel" - antes, tanto
    `AutoColecionador` quanto `AutoColecionadorUsuarios` reivindicavam
    SEMPRE só 1 por ciclo, mesmo que sobrasse mais cota que isso).

    Reconsulta quem ainda está sem dono a CADA tentativa (não só no
    início) - um humano pode clicar em qualquer uma das pendentes a
    qualquer momento desse processo, mesmo padrão que já existia pro caso
    de 1 claim só. Se uma tentativa perder a corrida (`claim_fn` devolve
    `ok=False` - já foi pega por um clique humano nesse meio-tempo), NÃO
    conta pra `quantidade_maxima` - tenta a próxima melhor candidata em
    vez de desperdiçar aquela vaga da cota.

    `claim_fn(personagem)` faz o claim de verdade (varia entre bot/
    jogador) e devolve `(ok, erro_ou_None, embed_ou_None)`. Devolve TODAS
    as tentativas feitas (sucesso ou não) como `[(item_pendente, ok,
    embed_ou_None), ...]` - quem chama decide como anotar cada card
    (`marcar_reivindicada_externamente`), mesmo padrão de sempre."""
    tentativas = []
    sucessos = 0
    candidatos = list(pendentes)
    while sucessos < quantidade_maxima and candidatos:
        ainda_livres = []
        for item in candidatos:
            dono = await asyncio.to_thread(db.dono_do_personagem, guild_id, item["personagem"]["id"])
            if dono is None:
                ainda_livres.append(item)
        if not ainda_livres:
            break
        melhor = max(ainda_livres, key=lambda item: item["personagem"].get("popularidade", 0))
        candidatos = [i for i in ainda_livres if i is not melhor]
        ok, _erro, embed = await claim_fn(melhor["personagem"])
        tentativas.append((melhor, ok, embed))
        if ok:
            sucessos += 1
    return tentativas


def _canal_dos_rolls(guild, config):
    """Módulo-level (2026-08-30, extraído de dentro de `AutoColecionador` pra
    ser compartilhado com `AutoColecionadorUsuarios` abaixo - mesmo espírito
    de `gacha.enviar_resultados_em_lotes`, nunca duas cópias da mesma regra)."""
    canal = None
    if config.get("canal_anuncio_id"):
        canal = guild.get_channel(int(config["canal_anuncio_id"]))
    return canal or guild.system_channel


class AutoColecionador:
    def __init__(self, client, papel):
        self.client = client
        self.horarios = HORARIOS_POR_PAPEL.get(papel)
        # guild_id (str) -> [{"personagem": resultado, "view": ViewClaimMultiplo, "indice": int}, ...]
        # só entram aqui as personagens "livre" (têm botão pra reivindicar).
        self._pendentes_por_guild = {}
        self._ultimo_roll = None
        self._ultimo_claim = None
        if self.horarios is not None:
            self._loop.start()

    def parar(self):
        if self.horarios is not None:
            self._loop.cancel()

    @tasks.loop(seconds=30)
    async def _loop(self):
        await self.client.wait_until_ready()
        agora = datetime.now(timezone.utc)
        marca = (agora.year, agora.month, agora.day, agora.hour, agora.minute)
        if agora.minute == self.horarios["minuto_roll"] and self._ultimo_roll != marca:
            self._ultimo_roll = marca
            await self._rodar_tiros()
        if agora.minute == self.horarios["minuto_claim"] and self._ultimo_claim != marca:
            self._ultimo_claim = marca
            await self._decidir_claims()

    async def _rodar_tiros(self):
        for guild in list(self.client.guilds):
            try:
                await self._rodar_tiros_guild(guild)
            except Exception as e:
                print(f" [ERIS] Auto-colecionador ({self.client.user}) falhou ao rolar em {guild.id}: {e}")

    async def _rodar_tiros_guild(self, guild):
        config = await asyncio.to_thread(db.obter_configuracao_colecao, guild.id)
        canal = _canal_dos_rolls(guild, config)
        if canal is None:
            print(f" [ERIS] Auto-colecionador ({self.client.user}) sem canal pra rolar em \"{guild.name}\" (configure com /colecao_admin canal).")
            return

        user_id = self.client.user.id
        quantidade_tiros = config["rolls_por_ciclo"]
        # 🔥 Rola tudo de UMA VEZ, não mais em N chamadas manuais de 10
        # (2026-08-29, achado: essa cópia manual do loop de lotes nunca
        # recebeu o fix de "Puxada N/M" feito em `enviar_resultados` pro
        # roll de jogador, e voltou a mostrar "Puxada X/10" reiniciando a
        # cada lote - usuário: "vc ta ignorando alguns principios... é a
        # msm coisa, n deveria ter de corrigir em locais diferentes").
        # `enviar_resultados_em_lotes` (gacha.py) é a ÚNICA implementação
        # de "dividir em lotes de 10 pro Discord" agora - reaproveitada
        # aqui, ainda produz mensagens de 10 cards cada visíveis no canal
        # ("literalmente rodar /wa 10 Nx" continua valendo pra quem olha o
        # canal, só a numeração do rodapé fica certa: 1/N, 2/N... N/N, em
        # vez de reiniciar a cada lote).
        resultados = await asyncio.to_thread(
            gacha.rolar_sem_cooldown, guild.id, user_id, quantidade_tiros, config["nsfw_permitido"], config["chance_wish_roll"],
        )
        if not resultados:
            self._pendentes_por_guild[str(guild.id)] = []
            return
        lotes = await gacha.enviar_resultados_em_lotes(canal, guild.id, resultados, len(resultados))
        pendentes = []
        for view, lote in lotes:
            for indice, resultado in enumerate(lote):
                if resultado.get("resultado_tipo", "livre") == "livre":
                    pendentes.append({"personagem": resultado, "view": view, "indice": indice})

        self._pendentes_por_guild[str(guild.id)] = pendentes
        print(f" [ERIS] Auto-colecionador ({self.client.user}) rolou {len(resultados)} personagens em \"{guild.name}\" ({len(lotes)} mensagens, {len(pendentes)} livres) - decide em 5min.")

    async def _decidir_claims(self):
        pendentes_todos, self._pendentes_por_guild = self._pendentes_por_guild, {}
        for guild_id, pendentes in pendentes_todos.items():
            if not pendentes:
                continue
            try:
                await self._reivindicar_melhor(guild_id, pendentes)
            except Exception as e:
                print(f" [ERIS] Auto-colecionador ({self.client.user}) falhou ao reivindicar em {guild_id}: {e}")

    async def _reivindicar_melhor(self, guild_id, pendentes):
        """🔥 Até `claims_por_ciclo` reivindicações por ciclo (2026-09-04,
        pedido do usuário: "A ideia é consumir todos os claim q tem
        disponivel" - antes era sempre só 1, mesmo que o servidor
        permitisse mais). MESMO valor que rege claim normal de QUALQUER
        jogador humano no servidor (`/pandora_admin claims`), sem somar
        upgrade/bônus permanente - a conta de bot nunca compra nenhum
        (mesmo espírito já aplicado aos rolls, `config["rolls_por_ciclo"]`,
        2026-09-03)."""
        config = await asyncio.to_thread(db.obter_configuracao_colecao, guild_id)

        async def _claim(personagem):
            # 🔥 MESMO núcleo de `atribuir_personagem_admin` (2026-08-30,
            # achado do usuário: "isso tao sendo geradas do mesmo codigo
            # ne? ja falamos sobre retrabalho antes") - claim+WiShards+
            # Afinidade+classe+embed numa função ÚNICA (`gacha.
            # _claim_sem_cooldown`), nunca reimplementada aqui de novo.
            return await gacha._claim_sem_cooldown(guild_id, personagem["id"], self.client.user, "auto_colecionador")

        tentativas = await _reivindicar_varios(guild_id, pendentes, config["claims_por_ciclo"], _claim)
        for item, ok, embed in tentativas:
            personagem = item["personagem"]
            rotulo = f"Reivindicada por {self.client.user.display_name}" if ok else "Já reivindicada"
            await item["view"].marcar_reivindicada_externamente(item["indice"], rotulo)
            if not ok:
                continue  # corrida de última hora - um humano clicou entre o filtro e agora
            print(f" [ERIS] Auto-colecionador ({self.client.user}) reivindicou {personagem['nome']} (popularidade {personagem.get('popularidade', 0)}) em {guild_id}.")
            if item["view"].mensagem is not None:
                try:
                    await item["view"].mensagem.channel.send(embed=embed)
                except discord.HTTPException:
                    pass


class AutoColecionadorUsuarios:
    """Modo Auto-coleta por usuário (2026-08-30, pedido do usuário: "faz a
    msm coisa q os bots de rodar auto os 50 e so 5min depois coletar o mais
    popular... vai fazer os rolls aos 50min e coletar ao 55min") - espelha
    `AutoColecionador` acima, com 3 diferenças de propósito:

    1. Roda só na instância "principal" (`eris/bot.py::on_ready`) - é onde
       vivem os comandos/o toggle de jogador (`paineis.ViewHubWaifu`),
       não faz sentido rodar de novo na instância "musica".
    2. Itera POR USUÁRIO que ativou o toggle (`db.usuarios_auto_
       colecionar_ativos`), não uma conta de bot fixa.
    3. Gasta a cota REAL de rolls/claims da pessoa (`gacha.rolar_varios`/
       `gacha._processar_claim`, os MESMOS usados por um comando de
       verdade) - NUNCA `rolar_sem_cooldown` (isso é só pra contas NPC). Só
       ativa o roll automático se o ciclo dela ainda estiver INTOCADO
       (pedido explícito do usuário: "isso so sera feito se n tiver usado
       os rolls ainda" - alguém que já rolou manualmente antes de :50 fica
       de fora dessa rodada, não recebe rolls "de graça" em cima do que já
       fez por conta própria)."""

    MINUTO_ROLL = 50
    MINUTO_CLAIM = 55

    def __init__(self, client):
        self.client = client
        # (guild_id, user_id) (str, str) -> [{"personagem", "view", "indice"}, ...]
        self._pendentes = {}
        self._ultimo_roll = None
        self._ultimo_claim = None
        self._loop.start()

    def parar(self):
        self._loop.cancel()

    @tasks.loop(seconds=30)
    async def _loop(self):
        await self.client.wait_until_ready()
        agora = datetime.now(timezone.utc)
        marca = (agora.year, agora.month, agora.day, agora.hour, agora.minute)
        if agora.minute == self.MINUTO_ROLL and self._ultimo_roll != marca:
            self._ultimo_roll = marca
            await self._rodar_tiros()
        if agora.minute == self.MINUTO_CLAIM and self._ultimo_claim != marca:
            self._ultimo_claim = marca
            await self._decidir_claims()

    async def _rodar_tiros(self):
        for guild in list(self.client.guilds):
            try:
                await self._rodar_tiros_guild(guild)
            except Exception as e:
                print(f" [ERIS] Auto-coleta (usuários) falhou ao rolar em {guild.id}: {e}")

    async def _rodar_tiros_guild(self, guild):
        ids_ativos = await asyncio.to_thread(db.usuarios_auto_colecionar_ativos, guild.id)
        if not ids_ativos:
            return
        config = await asyncio.to_thread(db.obter_configuracao_colecao, guild.id)
        canal = _canal_dos_rolls(guild, config)
        if canal is None:
            print(f" [ERIS] Auto-coleta (usuários) sem canal configurado em \"{guild.name}\" (configure com /colecao_admin canal).")
            return
        for user_id in ids_ativos:
            try:
                await self._rodar_tiros_usuario(guild, canal, config, user_id)
            except Exception as e:
                print(f" [ERIS] Auto-coleta (usuários) falhou pra {user_id} em {guild.id}: {e}")

    async def _rodar_tiros_usuario(self, guild, canal, config, user_id):
        # 🔥 "isso so sera feito se n tiver usado os rolls ainda" - reaproveita
        # `gacha._limite_rolls_atual` (a MESMA conta de limite que um roll de
        # verdade usa, já incluindo upgrade permanente) pra comparar contra
        # `db.rolls_disponiveis` (leitura pura, sem consumir nada).
        limite_rolls = await asyncio.to_thread(gacha._limite_rolls_atual, guild.id, user_id, config)
        disponiveis = await asyncio.to_thread(db.rolls_disponiveis, guild.id, user_id, limite_rolls, config["ciclo_rolls_minutos"])
        if disponiveis != limite_rolls:
            return  # já rolou manualmente algo neste ciclo - fica de fora dessa rodada automática
        ok, resultados = await asyncio.to_thread(gacha.rolar_varios, guild.id, user_id, "ma", 0)
        if not ok or not resultados:
            return
        lotes = await gacha.enviar_resultados_em_lotes(canal, guild.id, resultados, limite_rolls)
        pendentes = []
        for view, lote in lotes:
            for indice, resultado in enumerate(lote):
                if resultado.get("resultado_tipo", "livre") == "livre":
                    pendentes.append({"personagem": resultado, "view": view, "indice": indice})
        self._pendentes[(str(guild.id), str(user_id))] = pendentes
        membro = guild.get_member(int(user_id))
        nome_exibicao = membro.display_name if membro else f"<@{user_id}>"
        print(f" [ERIS] Auto-coleta ({nome_exibicao}) rolou {len(resultados)} personagens em \"{guild.name}\" ({len(lotes)} mensagens, {len(pendentes)} livres) - decide em 5min.")

    async def _decidir_claims(self):
        pendentes_todos, self._pendentes = self._pendentes, {}
        for (guild_id, user_id), pendentes in pendentes_todos.items():
            if not pendentes:
                continue
            try:
                await self._reivindicar_melhor(guild_id, user_id, pendentes)
            except Exception as e:
                print(f" [ERIS] Auto-coleta (usuários) falhou ao reivindicar pra {user_id} em {guild_id}: {e}")

    async def _reivindicar_melhor(self, guild_id, user_id, pendentes):
        """🔥 Até o TOTAL de claims que a pessoa tem disponível nesse ciclo
        (2026-09-04, pedido do usuário: "A ideia é consumir todos os claim
        q tem disponivel" - antes era sempre só 1, mesmo que sobrasse mais
        cota). `gacha._limite_claims_atual` é a MESMA conta de limite que
        um claim manual usa (base do servidor + Upgrade de Claims pago +
        bônus permanente); `db.claims_disponiveis` lê quanto REALMENTE
        ainda resta nesse ciclo (já descontando claim manual que a pessoa
        tenha feito antes desse horário - `_processar_claim`, chamado
        abaixo, consome de verdade a cada sucesso)."""
        guild = self.client.get_guild(int(guild_id))
        membro = guild.get_member(int(user_id)) if guild else None
        if membro is None:
            return  # saiu do servidor/fora do cache - não dá pra confirmar o claim como esse usuário

        config = await asyncio.to_thread(db.obter_configuracao_colecao, guild_id)
        limite_claims = await asyncio.to_thread(gacha._limite_claims_atual, guild_id, user_id, config)
        quantidade_maxima = await asyncio.to_thread(
            db.claims_disponiveis, guild_id, user_id, limite_claims, config["ciclo_claims_minutos"],
        )
        if quantidade_maxima <= 0:
            return

        async def _claim(personagem):
            # 🔥 `_processar_claim` é o MESMO núcleo de um claim humano de
            # verdade (checa/consome o claim REAL da pessoa, credita
            # WiShards, define Afinidade, chama `revelar_classe`) - nunca
            # `atribuir_personagem_admin` (esse pula o cooldown de
            # propósito, é presente de admin, não o que a auto-coleta
            # representa).
            return await gacha._processar_claim(guild_id, personagem, membro)

        tentativas = await _reivindicar_varios(guild_id, pendentes, quantidade_maxima, _claim)
        for item, ok, embed in tentativas:
            personagem = item["personagem"]
            rotulo = f"Reivindicada por {membro.display_name}" if ok else "Já reivindicada"
            await item["view"].marcar_reivindicada_externamente(item["indice"], rotulo)
            if not ok:
                print(f" [ERIS] Auto-coleta ({membro.display_name}) não conseguiu reivindicar {personagem['nome']} em {guild_id}.")
                continue
            print(f" [ERIS] Auto-coleta ({membro.display_name}) reivindicou {personagem['nome']} (popularidade {personagem.get('popularidade', 0)}) em {guild_id}.")
            if item["view"].mensagem is not None:
                try:
                    await item["view"].mensagem.channel.send(embed=embed)
                except discord.HTTPException:
                    pass
