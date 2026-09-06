# -*- coding: utf-8 -*-
"""Migração de RUPTURA na taxonomia de classes (2026-09-02, pedido do
usuário: "Da uma analisada nos nomes de classes, tem algumas q n fazem
sentido e pode corrigir. E ainda acho q tem poucas classes tank" + "Ta bem
desproporcional essas distribuições, varios bardos").

3 correções, nessa ordem:

1) Merge de duplicatas/inconsistências (mesma classe, nomes diferentes):
   Assassin -> Assassino, Estratégista (acento errado) -> Estrategista,
   Invoker -> Invocador. Repointa `colecao_personagens.classe` de quem
   estava na forma errada, depois remove a linha órfã de `colecao_classes`.

2) Recategoriza classes cuja `categoria_combate` não bate com a própria
   classe (mesmo `funcao_cidade`="Militar" que os irmãos DPS/Tank, mas
   caíram em Support por inconsistência da classificação anterior):
   Defensor -> Tank (literalmente "quem defende"), Ninja e Lutador de Rua
   -> DPS (combate físico direto, sem papel de proteger os aliados).

3) Reclassificação individual das 14 personagens que estavam em "Criança"
   (idade, não classe) ou "Tonto" (traço de personalidade, não classe) -
   ambas violam a própria regra do prompt de classificação (`core/agent/
   turno.py::classificar_personagem_colecao` no repo da GAIA: "nunca sua
   profissão, cargo, personalidade... papel social do dia a dia"). Cada
   uma foi lida (descrição + conhecimento externo do personagem) e
   reclassificada numa classe EXISTENTE do catálogo que faça sentido de
   verdade, nunca inventando uma nova - ver justificativa por personagem
   no dict abaixo.

Roda contra `data/pandora.db` de PRODUÇÃO (backup feito ANTES em
`data/pandora_backup_pre_reclassificacao_classes_2026-09-02.db`) - não
precisa de migração nenhuma pro bônus de CP por classe
(`db.bonus_cp_classe`/`db.info_classes_em_lote`) porque ele é calculado
DIRETO de `colecao_personagens.classe` a cada chamada, nunca guardado num
snapshot por jogador; o bônus de CP da Cidade (Militar/Arcano) É um
snapshot, mas já é aceito que ele demora até a próxima ação (Party/Upar
Nível/etc) pra atualizar, mesmo comportamento de sempre."""
import sqlite3

CAMINHO_BANCO = "data/pandora.db"

# --- 1) Merge de duplicatas -------------------------------------------
MERGES = {
    "Assassin": "Assassino",
    "Estratégista": "Estrategista",
    "Invoker": "Invocador",
}

# --- 2) Recategorização (só a categoria_combate muda, a classe em si
# continua a mesma) ------------------------------------------------------
RECATEGORIZACOES = {
    "Defensor": "Tank",
    "Ninja": "DPS",
    "Lutador de Rua": "DPS",
}

# --- 3) Reclassificação individual (id -> nova classe canônica +
# justificativa) --------------------------------------------------------
RECLASSIFICACOES_INDIVIDUAIS = {
    632: ("Atirador", "Kino (Kino's Journey) é uma atiradora habilidosa com seu revólver 'Cannon', traço central da personagem em toda a série."),
    8271: ("Atirador", "Rosé Thomas (FMA:B) pega um rifle e luta na batalha final de Lior contra as forças do Father."),
    18197: ("Arqueiro", "Suika (Dr. Stone) atua como caçadora/atiradora de longo alcance do grupo, usa arma de longo alcance depois que Senku corrige sua visão."),
    4291: ("Místico", "Niko (OneShot) é a protagonista de uma jornada mística pra devolver o Sol à Torre e salvar o mundo - poder central é sobrenatural/de missão, não combate direto."),
    20213: ("Espírito", "Eika Ebisu (Touhou) é literalmente o espírito de uma criança morta (mizuko) - encaixe direto, não força a categoria."),
    4176: ("Eremita", "Suzuna Ayuzawa (Maid Sama!) é descrita como apática, mostra pouca emoção, não participa de nada - arquétipo de reclusa/desapegada."),
    28455: ("Bardo", "Natsu Hinata (Haikyu!!) é descrita como alto-astral, anima o irmão constantemente - bate com a definição de Barda usada no próprio prompt de classificação."),
    19934: ("Truqueiro", "Chiru Kondo (Gal Gun) é matadora de aula, prefere jogos antigos - traço de personagem avessa a regras/travessa."),
    2336: ("Apoiador", "Ushio Okazaki (Clannad) é um bebê/criança pequena sem poder ou combate - sem arquétipo de RPG real, fallback genérico de apoio (é o coração emocional da família, não uma combatente)."),
    14622: ("Apoiador", "Emily Shirase (Adventure of a Lifetime) é uma colega de colégio comum, sem combate/poder descrito - fallback genérico."),
    15707: ("Apoiador", "Hana Shirosaki (Wataten!) é uma criança comum do ensino fundamental, sem combate/poder - fallback genérico."),
    27839: ("Apoiador", "Ayane Mitahora (A Sister's All You Need) é um personagem de flashback sem combate/poder descrito - fallback genérico."),
    30548: ("Apoiador", "Anne (No Guns Life) é vítima de experimentos, sem poder de combate próprio descrito - fallback genérico."),
    4128: ("Apoiador", "Maron (Dragon Ball) não tem poder nem combate, só o traço de personalidade 'air-headed/ditsy' que a classe antiga ('Tonto') capturava errado - fallback genérico."),
}


def main():
    conn = sqlite3.connect(CAMINHO_BANCO)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("=== 1) Merge de duplicatas ===")
    for antiga, nova in MERGES.items():
        linha = cur.execute("SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = ?", (antiga,)).fetchone()
        qtd = linha["n"]
        cur.execute("UPDATE colecao_personagens SET classe = ? WHERE classe = ?", (nova, antiga))
        cur.execute("DELETE FROM colecao_classes WHERE classe = ?", (antiga,))
        print(f"  {antiga} -> {nova}: {qtd} personagem(ns) repontada(s), classe antiga removida do catálogo.")

    print("\n=== 2) Recategorização ===")
    for classe, nova_categoria in RECATEGORIZACOES.items():
        linha = cur.execute("SELECT categoria_combate FROM colecao_classes WHERE classe = ?", (classe,)).fetchone()
        categoria_antiga = linha["categoria_combate"] if linha else None
        cur.execute("UPDATE colecao_classes SET categoria_combate = ? WHERE classe = ?", (nova_categoria, classe))
        qtd = cur.execute("SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = ?", (classe,)).fetchone()["n"]
        print(f"  {classe}: {categoria_antiga} -> {nova_categoria} ({qtd} personagem(ns) afetada(s))")

    print("\n=== 3) Reclassificação individual (Criança/Tonto) ===")
    for personagem_id, (nova_classe, justificativa) in RECLASSIFICACOES_INDIVIDUAIS.items():
        linha = cur.execute("SELECT nome, classe, genero FROM colecao_personagens WHERE id = ?", (personagem_id,)).fetchone()
        if linha is None:
            print(f"  #{personagem_id}: NÃO ENCONTRADO - pulei.")
            continue
        cur.execute(
            "UPDATE colecao_personagens SET classe = ?, classe_exibicao = ? WHERE id = ?",
            (nova_classe, nova_classe, personagem_id),
        )
        print(f"  #{personagem_id} {linha['nome']}: {linha['classe']} -> {nova_classe}")
        print(f"      {justificativa}")

    # Limpa as 2 classes-lixo do catálogo depois que ninguém mais as usa.
    for classe_invalida in ("Criança", "Tonto"):
        restantes = cur.execute("SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = ?", (classe_invalida,)).fetchone()["n"]
        if restantes == 0:
            cur.execute("DELETE FROM colecao_classes WHERE classe = ?", (classe_invalida,))
            print(f"\n  Classe '{classe_invalida}' sem nenhum personagem restante - removida do catálogo.")
        else:
            print(f"\n  ATENÇÃO: '{classe_invalida}' ainda tem {restantes} personagem(ns) - NÃO removida do catálogo.")

    conn.commit()

    print("\n=== Conferência final ===")
    linhas = cur.execute("SELECT classe, categoria_combate FROM colecao_classes ORDER BY categoria_combate, classe").fetchall()
    por_cat = {}
    for l in linhas:
        por_cat.setdefault(l["categoria_combate"], []).append(l["classe"])
    for cat, classes in sorted(por_cat.items()):
        total = sum(
            cur.execute("SELECT COUNT(*) AS n FROM colecao_personagens WHERE classe = ?", (c,)).fetchone()["n"]
            for c in classes
        )
        print(f"  {cat}: {len(classes)} classes, {total} personagens")

    conn.close()


if __name__ == "__main__":
    main()
