# -*- coding: utf-8 -*-
"""Reaplica o snapshot de `data/classificacao_personagens.json`
(`scripts/exportar_classificacao_personagens.py`) num banco que acabou de
importar o catálogo bruto - PC novo, ou banco recriado do zero. Sem isso,
todo personagem voltaria a `classe = NULL` e reprecisaria de uma chamada de
LLM nova pra cada uma (~8,7k chamadas refeitas à toa).

Catálogo bruto primeiro (`pandora.importar_get_waifu`): `sincronizar()`
baixa a versão mais atual e já importa numa chamada só, ou espere o job
semanal do `sincronizador.py` rodar sozinho.

Faz backup do banco ANTES (mesmo padrão dos scripts de reclassificação -
`pandora_backup_pre_aplicar_classificacao_<timestamp>.db`).

Uso (rodar da RAIZ do repo, DEPOIS de importar o catálogo bruto):
    python -m scripts.aplicar_classificacao_personagens"""
import json
import os
import shutil
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pandora import db
from pandora.config import PASTA_DADOS

ORIGEM = os.path.join(PASTA_DADOS, "classificacao_personagens.json")


def main():
    if not os.path.exists(ORIGEM):
        print(f"Nada em {ORIGEM} - nenhum snapshot pra aplicar.")
        return
    if os.path.exists(db.CAMINHO_BANCO):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup = db.CAMINHO_BANCO.replace("pandora.db", f"pandora_backup_pre_aplicar_classificacao_{timestamp}.db")
        shutil.copy(db.CAMINHO_BANCO, backup)
        print(f"Backup salvo em {backup}.")

    db.inicializar()
    with open(ORIGEM, encoding="utf-8") as f:
        classificacoes = json.load(f)
    aplicadas = db.aplicar_classificacao_personagens(classificacoes)
    print(f"{aplicadas} de {len(classificacoes)} personagens do snapshot encontradas e reclassificadas.")
    if aplicadas < len(classificacoes):
        print(
            f"{len(classificacoes) - aplicadas} não encontradas nesse banco - importe o catálogo bruto "
            "primeiro (`pandora.importar_get_waifu.sincronizar()`) antes de rodar este script."
        )


if __name__ == "__main__":
    main()
