# -*- coding: utf-8 -*-
"""Migração ÚNICA de dado - `data/eris.db` (Project-ERIS) -> `data/pandora.db`
(este repo), rodada 1x manualmente na extração do Colecionador (2026-08-29).
NÃO é uma migração aditiva de schema (isso continua em `pandora.db.
inicializar()`) - é mudança de ARQUIVO, então fica fora do fluxo normal de
boot, só roda quando alguém chama explicitamente (SEMPRE a partir da raiz
do repo, não de dentro de `scripts/` - o caminho padrão do eris.db é
relativo à raiz):

    python scripts/migrar_de_eris.py [caminho pro eris.db, opcional]

Copia as 14 tabelas `colecao_*` inteiras (`INSERT OR IGNORE`, seguro rodar
mais de uma vez sem duplicar) - NUNCA apaga nada do `eris.db` original, só lê.
Depois de migrar e validar, quem decide apagar as tabelas antigas do `eris.db`
é o passo 5 do plano de extração (`eris/db.py` perde as tabelas `colecao_*`),
não este script."""
import os
import sqlite3
import sys

from pandora import db as pandora_db

_TABELAS_COLECAO = [
    "colecao_personagens", "colecao_configuracao_guild", "colecao_propriedade",
    "colecao_wishlist", "colecao_estado_jogador", "colecao_afinidade",
    "colecao_wishards_saldo", "colecao_wishards_ledger", "colecao_troca_proposta",
    "colecao_series_bloqueadas", "colecao_favoritas", "colecao_cards_pendentes",
    "colecao_equipe", "colecao_sincronizacao",
]


def migrar(caminho_eris_db):
    if not os.path.isfile(caminho_eris_db):
        print(f"Não achei o banco do ERIS em {caminho_eris_db!r}.")
        return

    pandora_db.inicializar()  # garante o schema novo criado ANTES de copiar dado

    origem = sqlite3.connect(caminho_eris_db)
    origem.row_factory = sqlite3.Row
    destino = sqlite3.connect(pandora_db.CAMINHO_BANCO)

    try:
        for tabela in _TABELAS_COLECAO:
            linhas = origem.execute(f"SELECT * FROM {tabela}").fetchall()
            if not linhas:
                print(f"{tabela}: 0 linhas (nada pra migrar).")
                continue
            colunas = linhas[0].keys()
            marcadores = ", ".join("?" for _ in colunas)
            sql = f"INSERT OR IGNORE INTO {tabela} ({', '.join(colunas)}) VALUES ({marcadores})"
            destino.executemany(sql, [tuple(linha) for linha in linhas])
            destino.commit()
            total_destino = destino.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
            print(f"{tabela}: {len(linhas)} linhas na origem, {total_destino} no destino depois da migração.")
    finally:
        origem.close()
        destino.close()

    print(f"\nMigração concluída - banco novo em {pandora_db.CAMINHO_BANCO}")


if __name__ == "__main__":
    # 🔥 2 ".." (não 1) - o script mora em `scripts/` desde a reorganização
    # de raiz (2026-09-06), então precisa subir um nível a mais que antes
    # (`scripts/` -> raiz do PANDORA -> `C:\Workspace`) pra achar o repo
    # irmão `Project-ERIS`.
    caminho_padrao = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Project-ERIS", "data", "eris.db")
    migrar(sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(caminho_padrao))
