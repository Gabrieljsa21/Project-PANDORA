# -*- coding: utf-8 -*-
"""Divide "Apoiador" em 3 arquétipos funcionais NOVOS (2026-09-06, pedido
do usuário depois de "mas ainda é muito, preciso diminuir" - Apoiador
tinha 1133 personagens, de longe a maior classe do jogo, por ser o balde
genérico "personagem comum, sem arquétipo").

Investigação (ver conversa) testou 14 arquétipos funcionais candidatos
(Comandante/Cientista/Médico/Alquimista/Oráculo/Sacerdote/Ilusionista/
Controlador/Hacker/Operador/Professor/Diplomata/Serviçal/Assistente) +
Cozinheiro, MAIS 3 candidatos a Tank (Protetor/Atleta/Delinquente) via
regex sobre a descrição em inglês de cada personagem - a maioria teve
sinal fraco demais (população baixa) ou alta taxa de falso positivo
confirmada por amostragem manual (ex.: "Miko Iino" batia em "Sacerdote"
pelo NOME dela, não pelo cargo; "homeroom" sozinho pegava ALUNOS de uma
sala em vez de professoras; termos de "Controlador" batiam em
personagens sem nenhuma relação com selamento/controle). Usuário pediu
pra NÃO criar uma 4ª categoria de combate nem usar relações familiares
(irmã mais velha/mais nova, colega de classe, amigo de infância) como
classe - só arquétipo funcional real.

Restaram 3 com sinal limpo E população que justifica a existência:
- Serviçal (maid/mordomo/serva) - Support/Comércio, mesma função de
  Apoiador/Encantador/Artífice.
- Assistente (secretário/assessor) - Support/Administração, mesma função
  de Estrategista/Sábio.
- Cientista (cientista/pesquisadora) - Support/Arcano, mesma função de
  Místico/Ocultista/Elementalista (bucket do "conhecimento" da Cidade).

Os candidatos a Tank (Protetor/Atleta/Delinquente) e o resto dos
arquétipos de Support (Professor/Cozinheiro/Sacerdote/Médico/
Controlador/Hacker/Diplomata/Comandante/Ilusionista/Oráculo/Alquimista/
Operador) foram DESCARTADOS por sinal fraco/população baixa - Apoiador
segue sendo o fallback legítimo pro resto (958 depois desta leva),
exatamente como o usuário concordou ("Apoiador pode continuar sendo o
fallback e não tem problema ele ser a maior classe").

Faz backup do banco ANTES (mesmo padrão dos scripts de reclassificação
anteriores)."""
import re
import shutil
import sys

from pandora import db

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKUP_PATH = db.CAMINHO_BANCO.replace("pandora.db", "pandora_backup_pre_reclassificar_apoiador_2026-09-06.db")

# (classe nova, categoria_combate, funcao_cidade, regex) - ordem de
# prioridade (mais específico primeiro), mesma validada na análise.
REGRAS = [
    ("Cientista", "Support", "Arcano", r"\b(scientist|researcher|research (institute|lab)|laboratory)\b"),
    ("Serviçal", "Support", "Comércio", r"\b(\bmaid\b|butler|servant|housekeeper|valet)\b"),
    ("Assistente", "Support", "Administração", r"\b(secretary|personal assistant|\baide\b|adjutant)\b"),
]


def main():
    shutil.copy2(db.CAMINHO_BANCO, BACKUP_PATH)
    print(f"Backup salvo em {BACKUP_PATH}")

    with db.conexao() as conn:
        restantes = conn.execute(
            "SELECT id, nome, descricao FROM colecao_personagens WHERE classe = 'Apoiador'",
        ).fetchall()
        restantes = list(restantes)
        total_inicial = len(restantes)
        print(f"Total Apoiador antes: {total_inicial}\n")

        for classe_nova, categoria, funcao, pattern in REGRAS:
            match, sobra = [], []
            for r in restantes:
                if re.search(pattern, (r["descricao"] or "").lower()):
                    match.append(r)
                else:
                    sobra.append(r)
            conn.execute(
                "INSERT INTO colecao_classes (classe, categoria_combate, funcao_cidade) VALUES (?, ?, ?) "
                "ON CONFLICT(classe) DO UPDATE SET categoria_combate = excluded.categoria_combate, funcao_cidade = excluded.funcao_cidade",
                (classe_nova, categoria, funcao),
            )
            for r in match:
                conn.execute(
                    "UPDATE colecao_personagens SET classe = ?, classe_exibicao = ? WHERE id = ?",
                    (classe_nova, classe_nova, r["id"]),
                )
            print(f"{classe_nova} ({categoria}/{funcao}): {len(match)} personagem(ns)")
            restantes = sobra

        conn.commit()

    print(f"\nApoiador ficou com {len(restantes)} personagem(ns) (era {total_inicial}).")


if __name__ == "__main__":
    main()
