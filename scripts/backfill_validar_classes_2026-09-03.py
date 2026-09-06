# -*- coding: utf-8 -*-
"""Backfill de classe pra personagens já reivindicadas com `classe IS NULL`
(2026-09-03, pedido do usuário: "acho q existem personagens sem classe
definida" - confirmado, 5205 no banco real). Mesmo caminho de `/pandora_admin
validar_classes` (`gacha.revelar_classe`), mas SEM o teto de 20 por chamada
(rodado fora do orçamento de 3s de uma interação do Discord) - roda os 5205
de uma vez, sequencial (1 chamada de rede pra GAIA por personagem), log de
progresso a cada 50.

Faz um backup do banco ANTES de começar (mesmo padrão dos scripts de
reclassificação anteriores, `pandora_backup_pre_*`) - roda contra o banco
de PRODUÇÃO de verdade, não uma cópia.

Uso: `.venv/Scripts/python.exe backfill_validar_classes_2026-09-03.py`
"""
import asyncio
import os
import shutil
from datetime import datetime

from pandora import db, gacha

BACKUP_PATH = db.CAMINHO_BANCO.replace("pandora.db", "pandora_backup_pre_validar_classes_2026-09-03.db")

# 🔥 Disjuntor (2026-09-03, achado rodando a 1ª tentativa) - a 1ª execução
# esgotou o orçamento DIÁRIO de tokens da Groq depois de só ~23 sucessos, e
# sem isso o script continuou queimando ~3800 chamadas de rede a mais, TODAS
# fadadas a falhar em silêncio (rejeição imediata, sem nem chegar a
# processar) - tempo perdido sem ganho nenhum. Agora para sozinho depois de
# N falhas SEGUIDAS (contador reseta a cada sucesso) - o resto fica pendente
# pra próxima execução (o script sempre rebusca do banco quem ainda está sem
# classe, nunca perde progresso).
FALHAS_SEGUIDAS_PARA_PARAR = 8

# 🔥 Pausa entre chamadas (2026-09-03, achado do usuário: mesmo com 9 contas
# Groq configuradas e a cota diária claramente tendo espaço [voltou a
# funcionar minutos depois de travar], o disjuntor acima seguia disparando
# rápido demais (~13s pra 8 falhas) - suspeita: limite de RAJADA (requests
# por minuto), separado do limite DIÁRIO de tokens, sem pausa nenhuma entre
# uma chamada e a próxima. `PAUSA_ENTRE_CHAMADAS_SEGUNDOS` dá um respiro
# real entre cada personagem, mesmo pagando o preço de o backfill total
# demorar mais tempo corrido.
PAUSA_ENTRE_CHAMADAS_SEGUNDOS = 2.5


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


async def main():
    if os.path.exists(BACKUP_PATH):
        log(f"Backup já existe ({BACKUP_PATH}) - preservando o snapshot ORIGINAL, não sobrescrevendo.")
    else:
        shutil.copy2(db.CAMINHO_BANCO, BACKUP_PATH)
        log(f"Backup criado: {BACKUP_PATH}")

    pendentes = db.personagens_possuidos_sem_classe(None)
    total = len(pendentes)
    log(f"Total a classificar: {total}")

    classificadas = 0
    falhas = []
    falhas_seguidas = 0
    parado_cedo = False
    for i, personagem in enumerate(pendentes, 1):
        try:
            classe, _categoria = await gacha.revelar_classe(personagem)
        except Exception as exc:
            classe = None
            falhas.append(f"{personagem['nome']} (exceção: {exc})")
        else:
            if classe:
                classificadas += 1
            else:
                falhas.append(personagem["nome"])
        if classe:
            falhas_seguidas = 0
        else:
            falhas_seguidas += 1
            if falhas_seguidas >= FALHAS_SEGUIDAS_PARA_PARAR:
                log(f"{falhas_seguidas} falhas SEGUIDAS - provável orçamento diário da Groq esgotado de novo. Parando cedo (rode de novo mais tarde).")
                parado_cedo = True
                break
        if i % 50 == 0 or i == total:
            log(f"{i}/{total} processados - {classificadas} ok, {len(falhas)} falha(s) até agora")
        if i < total:
            await asyncio.sleep(PAUSA_ENTRE_CHAMADAS_SEGUNDOS)

    if not parado_cedo:
        log(f"CONCLUÍDO: {classificadas}/{total} classificadas, {len(falhas)} falha(s).")
    else:
        log(f"PARADO CEDO: {classificadas} classificadas antes de parar, {len(falhas)} falha(s) no total.")
    restante = db.contar_personagens_possuidos_sem_classe()
    log(f"Ainda sem classe no banco (checagem final): {restante}")
    if falhas:
        amostra = falhas[:30]
        log("Amostra de falhas: " + "; ".join(amostra) + (f" ... e mais {len(falhas) - 30}" if len(falhas) > 30 else ""))


if __name__ == "__main__":
    asyncio.run(main())
