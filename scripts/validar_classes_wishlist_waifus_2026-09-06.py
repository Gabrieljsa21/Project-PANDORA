# -*- coding: utf-8 -*-
"""Auditoria pontual de classes (2026-09-06, pedido do usuário: "Valida as
classes existentes, ainda acho q existem poucos tanks. Valida principalmente
as personagens q registrei na wishlist ou na lista de waifus, veja se a
classe deles esta condizente") - rodado 1x manualmente, faz backup do banco
ANTES de escrever (mesmo padrão dos scripts de reclassificação anteriores,
`pandora_backup_pre_*`).

Achados na auditoria (leitura manual dos 24 personagens únicos entre
Wishlist + slots de Waifu do único jogador com dados nessas 2 listas):

1. **"Estrategista" x "Estratégista"** - a MESMA classe (Support/
   Administração nos dois) gravada com 2 grafias diferentes no catálogo
   inteiro (421 personagens com a grafia correta, sem acento; 31 com
   "Estratégista", grafia errada em português - "estrategista" é
   paroxítona terminada em "a", não leva acento). Isso fragmenta o bônus
   de classe pra qualquer jogador que tenha personagens dos dois lados
   (a cada 5 da MESMA classe = +50 CP, mas a contagem fica dividida entre
   as 2 grafias). Mesma classe de bug já documentada e corrigida antes
   pra outras classes ("Assassin"/"Assassino" em outro idioma) - essa é
   uma divergência de ACENTUAÇÃO, não de idioma, nunca corrigida.
   Corrigido fundindo pra "Estrategista" (a grafia correta e majoritária)
   e removendo a linha duplicada de `colecao_classes`.

2. **10 personagens femininas com `classe_exibicao` NULL** numa classe
   masculina conhecida (Guerreiro/Mago/Assassino/Artilheiro) - cai no
   fallback de mostrar a forma masculina pra elas (`personagem.get(
   "classe_exibicao") or personagem.get("classe")`), mesmo padrão de bug
   já corrigido pro resto do catálogo (2026-08-29, "separaria nome
   canônico de nome exibido"), só que ficou pra trás pra esses 10
   especificamente (bug de importação/classificação antiga, nunca
   corrigido). Corrigido preenchendo a forma feminina certa.

3. **Kurumi Tokisaki (Date A Live, #78, na Wishlist E no slot 12 de
   Waifu) estava classificada "Místico"/Support** - descrição real: mata
   gente com armas de fogo e um "exército" de clones-sombra de si mesma
   (habilidade de invocar clones de outras linhas do tempo, todos com
   personalidade própria mas lutando por ela) - combate REAL e ativo,
   não um papel de suporte/cura. Prioridade da hierarquia de classificação
   já estabelecida no projeto ("combate real > poder sobrenatural >
   personalidade") - o combate dela (armas + exército de invocações) pesa
   mais que "ser um Espírito sobrenatural" isolado. Reclassificada pra
   "Invocador" (DPS/Militar) - a classe que já existe no catálogo
   justamente pra esse padrão (invocar aliados pra lutar).

4. **"Poucos tanks" (preocupação recorrente do usuário)** - CONFIRMADO que
   é estrutural, não um bug desta amostra: só 3 das ~29 classes do
   catálogo inteiro (`Cavaleiro`/`Colosso`/`Guardião`) mapeiam pra Tank,
   e Tank é 5,1% do catálogo classificado (231/4.553) - bate com o
   crescimento já esperado desde o ~4,3% da última auditoria grande
   (2026-09-02). Dos 24 personagens únicos entre Wishlist/Waifus, só Zero
   Two (Cavaleira) é Tank - proporcionalmente em linha com o catálogo
   inteiro, não uma anomalia específica dessas 2 listas. NENHUM outro
   personagem revisado tinha descrição batendo com "feita pra aguentar/
   absorver dano no lugar dos aliados" o suficiente pra justificar virar
   Tank sem forçar - o desbalanço de fundo (Support 54,6% dominando) é o
   mesmo problema de CRITÉRIO de classificação de personagem NOVA já
   registrado no TODO, não algo que uma auditoria de personagens JÁ
   classificados resolve retroativamente sem inventar critério novo."""
import shutil

from pandora import config, db

BACKUP_PATH = db.CAMINHO_BANCO.replace("pandora.db", "pandora_backup_pre_validar_classes_wishlist_waifus_2026-09-06.db")

_EXIBICAO_FEMININA = {
    (7496, "Artilheiro"): "Artilheira",
    (157, "Assassino"): "Assassina",
    (1308, "Guerreiro"): "Guerreira",
    (2987, "Guerreiro"): "Guerreira",
    (382, "Guerreiro"): "Guerreira",
    (1669, "Guerreiro"): "Guerreira",
    (1267, "Guerreiro"): "Guerreira",
    (631, "Guerreiro"): "Guerreira",
    (220, "Guerreiro"): "Guerreira",
    (718, "Mago"): "Maga",
}

ID_KURUMI_TOKISAKI = 78


def _contar(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def main():
    print(f"Fazendo backup: {config.CAMINHO_BANCO} -> {BACKUP_PATH}")
    shutil.copy2(config.CAMINHO_BANCO, BACKUP_PATH)

    with db.conexao() as conn:
        # 1) Fusão "Estratégista" -> "Estrategista"
        antes = _contar(conn, "SELECT COUNT(*) FROM colecao_personagens WHERE classe = 'Estratégista'")
        conn.execute("UPDATE colecao_personagens SET classe = 'Estrategista' WHERE classe = 'Estratégista'")
        conn.execute(
            "UPDATE colecao_personagens SET classe_exibicao = 'Estrategista' WHERE classe_exibicao = 'Estratégista'"
        )
        conn.execute("DELETE FROM colecao_classes WHERE classe = 'Estratégista'")
        print(f"1) Estratégista -> Estrategista: {antes} personagem(ns) migrada(s).")

        # 2) classe_exibicao feminina faltando
        preenchidas = 0
        for (personagem_id, classe_esperada), exibicao in _EXIBICAO_FEMININA.items():
            linha = conn.execute(
                "SELECT nome, classe, classe_exibicao FROM colecao_personagens WHERE id = ?", (personagem_id,)
            ).fetchone()
            if linha is None:
                print(f"   ⚠️ #{personagem_id} não encontrado - pulando.")
                continue
            if linha["classe"] != classe_esperada or linha["classe_exibicao"] is not None:
                print(f"   ⚠️ #{personagem_id} ({linha['nome']}) mudou desde a auditoria (classe={linha['classe']!r}, exibicao={linha['classe_exibicao']!r}) - pulando.")
                continue
            conn.execute("UPDATE colecao_personagens SET classe_exibicao = ? WHERE id = ?", (exibicao, personagem_id))
            preenchidas += 1
            print(f"   #{personagem_id} {linha['nome']}: classe_exibicao = {exibicao!r}")
        print(f"2) classe_exibicao feminina preenchida: {preenchidas}/{len(_EXIBICAO_FEMININA)}.")

        # 3) Kurumi Tokisaki: Místico -> Invocador
        linha = conn.execute("SELECT nome, classe FROM colecao_personagens WHERE id = ?", (ID_KURUMI_TOKISAKI,)).fetchone()
        if linha and linha["classe"] == "Místico":
            conn.execute("UPDATE colecao_personagens SET classe = 'Invocador', classe_exibicao = 'Invocadora' WHERE id = ?", (ID_KURUMI_TOKISAKI,))
            print(f"3) #{ID_KURUMI_TOKISAKI} {linha['nome']}: Místico -> Invocador (Support -> DPS).")
        else:
            print(f"3) #{ID_KURUMI_TOKISAKI} já não está mais em 'Místico' ({linha['classe'] if linha else 'não encontrado'}) - pulando.")

    print("\nConcluído.")


if __name__ == "__main__":
    main()
