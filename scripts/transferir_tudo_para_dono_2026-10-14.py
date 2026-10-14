# -*- coding: utf-8 -*-
"""Transfere TODAS as personagens já adquiridas (qualquer dono, qualquer
servidor) para a conta do dono (2026-10-14, pedido do usuário: "transfere
todos os personagens ja adquiridos para a minha conta").

Usa `db.transferir_personagem`, o mesmo caminho da troca e da batalha
apostada: Afinidade do dono antigo fica intacta, o novo dono ganha
Afinidade inicial (ou retoma a antiga). Personagens que já são do dono
não são tocadas.

Faz backup do banco ANTES (mesmo padrão dos scripts anteriores).

Uso (da RAIZ do repo): python scripts/transferir_tudo_para_dono_2026-10-14.py <id_discord_do_dono>"""
import shutil
import sys

from pandora import db

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKUP_PATH = db.CAMINHO_BANCO.replace("pandora.db", "pandora_backup_pre_transferir_tudo_para_dono_2026-10-14.db")


def main():
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print("Uso: python scripts/transferir_tudo_para_dono_2026-10-14.py <id_discord_do_dono>")
        sys.exit(1)
    dono_id = sys.argv[1]
    shutil.copy2(db.CAMINHO_BANCO, BACKUP_PATH)
    print(f"Backup: {BACKUP_PATH}")
    with db.conexao() as conn:
        linhas = [dict(r) for r in conn.execute(
            "SELECT guild_id, personagem_id, dono_id FROM colecao_propriedade WHERE dono_id != ? ORDER BY guild_id, dono_id, personagem_id",
            (dono_id,),
        ).fetchall()]
    por_dono = {}
    for linha in linhas:
        db.transferir_personagem(linha["guild_id"], linha["personagem_id"], dono_id)
        chave = (linha["guild_id"], linha["dono_id"])
        por_dono[chave] = por_dono.get(chave, 0) + 1
    for (guild_id, antigo), total in sorted(por_dono.items()):
        print(f"Servidor {guild_id}: {total} personagem(ns) de {antigo} -> {dono_id}")
    print(f"Total transferido: {len(linhas)}")


if __name__ == "__main__":
    main()
