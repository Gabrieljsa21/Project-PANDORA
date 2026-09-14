# -*- coding: utf-8 -*-
"""Mescla classes duplicadas (2026-09-06, achado do usuário auditando o
"Bônus por Classe": "Idol" (23 personagens) e "Ídolo" (85 personagens)
contadas como classes DIFERENTES). Investigação achou 2 causas
DIFERENTES, cada uma tratada à parte:

1. Acento/maiúscula (`_MERGES_AUTOMATICOS` abaixo, via `db._normalizar_
   classe`) - "Estrategista"/"Estratégista" JÁ tinha sido resolvido pelo
   backfill anterior (`validar_classes_wishlist_waifus_2026-09-06.py`) e
   continua resolvido (checado nesta sessão, sem duplicata sobrando) -
   fica automático aqui só pra proteger qualquer OUTRO par accent-only
   que apareça no futuro sem precisar de outro script novo.
2. Sinônimo INGLÊS/PORTUGUÊS ("Idol"/"Ídolo") - NÃO é acento, é uma
   PALAVRA diferente (`_normalizar_classe` não unifica "idol" com
   "idolo"), então precisa de mapeamento manual (`_SINONIMOS_MANUAIS`).

Causa raiz do caso (1) corrigida em paralelo (`db.definir_classe_
personagem`, ver `db._classe_canonica_equivalente`) - toda classificação
NOVA converge sozinha pra uma classe equivalente ignorando acento/
maiúscula. O caso (2) não tem correção automática equivalente (a GAIA
classificando em inglês por engano não é um padrão de string previsível)
- se reaparecer, adicionar o par em `_SINONIMOS_MANUAIS` e rodar de novo.

Faz backup do banco ANTES (mesmo padrão dos scripts de reclassificação
anteriores)."""
import shutil
from datetime import datetime

from pandora import db

BACKUP_PATH = db.CAMINHO_BANCO.replace("pandora.db", "pandora_backup_pre_mesclar_classes_2026-09-06.db")

# (variante em inglês/errada, canônica em português) - `classe` E
# `classe_exibicao` são ambos migrados pra canônica (`classe_exibicao`
# também não deve sobrar em inglês num texto que o jogador vê).
_SINONIMOS_MANUAIS = [
    ("Idol", "Ídolo"),
]


def main():
    shutil.copy2(db.CAMINHO_BANCO, BACKUP_PATH)
    print(f"Backup salvo em {BACKUP_PATH}")

    with db.conexao() as conn:
        linhas = conn.execute("SELECT classe, categoria_combate, funcao_cidade FROM colecao_classes").fetchall()
        contagens = {
            r["classe"]: conn.execute(
                "SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = ?", (r["classe"],),
            ).fetchone()["n"]
            for r in linhas
        }

        # Agrupa por forma normalizada (acento/maiúscula ignorados).
        grupos = {}
        for r in linhas:
            grupos.setdefault(db._normalizar_classe(r["classe"]), []).append(r["classe"])

        print("=== Fusões ===")
        fundidas = 0
        for _normalizado, classes in grupos.items():
            if len(classes) <= 1:
                continue
            # Canônica = a com MAIS personagens (mesmo critério do backfill
            # de Estrategista/Estratégista, "grafia majoritária vence").
            canonica = max(classes, key=lambda c: contagens.get(c, 0))
            for classe in classes:
                if classe == canonica:
                    continue
                qtd = contagens.get(classe, 0)
                conn.execute("UPDATE colecao_personagens SET classe = ? WHERE classe = ?", (canonica, classe))
                conn.execute("DELETE FROM colecao_classes WHERE classe = ?", (classe,))
                print(f"  {classe!r} ({qtd} personagem(ns)) -> {canonica!r}")
                fundidas += 1
        if not fundidas:
            print("  Nenhuma duplicata por acento/maiúscula encontrada.")

        print("\n=== Sinônimos manuais ===")
        for variante, canonica in _SINONIMOS_MANUAIS:
            qtd = conn.execute("SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = ?", (variante,)).fetchone()["n"]
            if qtd == 0:
                print(f"  {variante!r} - nenhum personagem (nada a fazer).")
                continue
            conn.execute("UPDATE colecao_personagens SET classe = ? WHERE classe = ?", (canonica, variante))
            conn.execute(
                "UPDATE colecao_personagens SET classe_exibicao = ? WHERE classe = ? AND classe_exibicao = ?",
                (canonica, canonica, variante),
            )
            conn.execute("DELETE FROM colecao_classes WHERE classe = ?", (variante,))
            print(f"  {variante!r} ({qtd} personagem(ns)) -> {canonica!r}")
            fundidas += 1
        conn.commit()

    print(f"\n{fundidas} classe(s) fundida(s) no total.")


if __name__ == "__main__":
    main()
