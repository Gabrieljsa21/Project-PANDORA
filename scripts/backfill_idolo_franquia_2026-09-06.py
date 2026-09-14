# -*- coding: utf-8 -*-
"""Backfill de "Ídolo" pra personagens de franquia idol/VTuber que vazaram
pra OUTRAS classes (2026-09-06, achado do usuário perguntando "Vc n
conseguiu diminuir a qnt de Apoiador?" - investigando, achei que 158
personagens são de franquias idol/VTuber/Vocaloid claras (mesmo filtro de
`IDOLO_SERIES_MARCADORES`, criado em `reclassificar_taxonomia_reducao_
2026-09-02.py`), mas só 72 estão em "Ídolo" - os outros 86 ficaram
espalhados (31 Bardo, 28 Apoiador, 9 Estrategista, 18 em mais 7 classes).

Causa raiz: o filtro de franquia só rodou UMA VEZ (2026-09-02, sobre
personagens que estavam em "Bardo" NAQUELE momento) - nunca virou regra
permanente, então qualquer personagem de franquia idol classificada
DEPOIS (ou que nunca passou por "Bardo" pra começar, indo direto pra
Apoiador/Estrategista/etc por outro motivo da descrição) nunca foi
capturada. Sem fix de causa raiz aqui (diferente do caso Idol/Ídolo,
acento - ver `db._classe_canonica_equivalente`) - o sinal é a SÉRIE, não
o nome da classe, GAIA não tem esse contexto na hora de classificar.
Documentado como limitação conhecida - se importar mais séries idol
novas, rodar este script de novo (ou promover `IDOLO_SERIES_MARCADORES`
pra checagem permanente, se o gap continuar reaparecendo).

Faz backup do banco ANTES (mesmo padrão dos scripts de reclassificação
anteriores)."""
import shutil
import sys

from pandora import db

# 🔥 Console do Windows não aceita QUALQUER Unicode no codepage padrão
# (cp1252/850) - alguns nomes/séries do catálogo usam caracteres exóticos
# (ex.: asterisco fullwidth "＊" em títulos de jogos de idol japoneses) que
# derrubavam o script no MEIO do loop com `UnicodeEncodeError`, ANTES do
# `conn.commit()` - toda a rodada era descartada em silêncio (sem
# traceback visível se o stdout for redirecionado, só o exit code não-zero
# denunciava). Força UTF-8 na saída, substituindo o que não couber ao
# imprimir em vez de travar.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKUP_PATH = db.CAMINHO_BANCO.replace("pandora.db", "pandora_backup_pre_backfill_idolo_franquia_2026-09-06.db")

# Mesma lista de `reclassificar_taxonomia_reducao_2026-09-02.py::IDOLO_SERIES_MARCADORES`.
IDOLO_SERIES_MARCADORES = [
    "idolm@ster", "love live", "bang dream", "d4dj", "idol jihen", "pri-chan",
    "idoly pride", "kageki revue starlight", "ongaku shoujo", "hololive",
    "vocaloid", "utaite", "tsukiuta", "youtube", "niconico", "budokan",
    "solmi's channel",
]


def main():
    shutil.copy2(db.CAMINHO_BANCO, BACKUP_PATH)
    print(f"Backup salvo em {BACKUP_PATH}")

    with db.conexao() as conn:
        candidatos = conn.execute(
            "SELECT id, nome, serie, classe FROM colecao_personagens WHERE classe IS NOT NULL AND classe != 'Ídolo'",
        ).fetchall()
        stragglers = [
            r for r in candidatos
            if any(m in (r["serie"] or "").lower() for m in IDOLO_SERIES_MARCADORES)
        ]
        print(f"{len(stragglers)} personagem(ns) de franquia idol/VTuber fora de 'Ídolo' encontrada(s).")
        for r in stragglers:
            print(f"  #{r['id']} {r['nome']} ({r['serie']}): {r['classe']} -> Ídolo")
            conn.execute(
                "UPDATE colecao_personagens SET classe = 'Ídolo', classe_exibicao = 'Ídolo' WHERE id = ?",
                (r["id"],),
            )
        conn.commit()

    print(f"\n{len(stragglers)} personagem(ns) movida(s) pra 'Ídolo'.")


if __name__ == "__main__":
    main()
