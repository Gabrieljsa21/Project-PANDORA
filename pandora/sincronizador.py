# -*- coding: utf-8 -*-
"""Sincronização contínua do catálogo do Colecionador (2026-08-29) - até
aqui a importação do get_waifu (`eris/colecao/importar_get_waifu.py`) era
carga ÚNICA, precisava rodar na mão (ver TODO.md, "Roadmap futuro"). Rebaixa
pra um job PERIÓDICO, mesmo espírito de `eris/colecao/auto_colecionador.py`
(loop `discord.ext.tasks` checando de tempos em tempos, sem precisar de
cron/Task Scheduler externo).

Frequência é SEMANAL (pedido do usuário, 2026-08-29) - dataset de terceiro
de baixo churn, não precisa de nada mais agressivo. Checa a cada hora se já
passou uma semana desde o ÚLTIMO SUCESSO (`db.estado_sincronizacao_
catalogo`) - nunca dispara de novo só porque o processo reiniciou (comum
neste ecossistema, ver `scripts/reiniciar_ecossistema.py` da GAIA), só
quando o prazo de verdade já venceu. Roda só na instância `papel="completo"`
(GAIA) - rodar nas duas seria download/reimportação duplicados à toa, sem
ganho nenhum (upsert por `fonte_id` já deixa isso seguro, mas
desnecessário)."""
import asyncio
from datetime import datetime, timedelta, timezone

from discord.ext import tasks

from pandora import db, importar_get_waifu

INTERVALO_SINCRONIZACAO = timedelta(days=7)
INTERVALO_CHECAGEM_SEGUNDOS = 3600


class SincronizadorCatalogo:
    def __init__(self, client):
        self.client = client
        self._loop.start()

    def parar(self):
        self._loop.cancel()

    @tasks.loop(seconds=INTERVALO_CHECAGEM_SEGUNDOS)
    async def _loop(self):
        await self.client.wait_until_ready()
        if not self._devido():
            return
        await self._sincronizar()

    def _devido(self):
        estado = db.estado_sincronizacao_catalogo()
        if estado is None or not estado.get("ultimo_sucesso_em"):
            return True
        ultimo_sucesso = datetime.fromisoformat(estado["ultimo_sucesso_em"])
        return datetime.now(timezone.utc) - ultimo_sucesso >= INTERVALO_SINCRONIZACAO

    async def _sincronizar(self):
        agora = datetime.now(timezone.utc).isoformat()
        await asyncio.to_thread(db.registrar_tentativa_sincronizacao_catalogo, agora)
        print(" [ERIS] Sincronização semanal do catálogo - baixando get_waifu...")
        try:
            resumo = await asyncio.to_thread(importar_get_waifu.sincronizar)
        except Exception as e:
            erro = f"falhou: {e}"
            print(f" [ERIS] Sincronização do catálogo {erro}")
            await asyncio.to_thread(db.registrar_resultado_sincronizacao_catalogo, agora, False, erro)
            return
        print(f" [ERIS] Sincronização do catálogo OK - {resumo}")
        await asyncio.to_thread(db.registrar_resultado_sincronizacao_catalogo, agora, True, resumo)
