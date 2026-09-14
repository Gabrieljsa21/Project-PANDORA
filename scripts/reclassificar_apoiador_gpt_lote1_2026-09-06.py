# -*- coding: utf-8 -*-
"""Aplica o 1º lote de sugestões de reclassificação de "Apoiador" geradas
pelo usuário via GPT externo (2026-09-06, "segue a lista de sugestoes de
mudancas do gpt... eu ia jogar no gpt aos poucos") - 162 personagens
revisados manualmente (nome/obra/descrição real), muito mais confiável
que o regex sobre a bio em inglês usado nas levas anteriores deste mesmo
dia.

Cross-referenciado contra o banco ANTES de aplicar (ver conversa): 155
bateram direto, 3 nomes ambíguos (Anna/May/Nana - resolvidos pela série
citada na própria sugestão), 7 não encontrados (fora deste lote, seguem
Apoiador).

3 conflitos de categoria contra classes JÁ ESTABELECIDAS ficaram de FORA
deste lote (seguem Apoiador até o usuário decidir):
- "Místico" já é Support (6 membros) - Nadeko Sengoku/Sanae Kashimura/
  Xiao Xiao vieram como DPS/Místico na sugestão.
- "Psíquico" já é Support (2 membros) - Shirai Kuroko veio como DPS.
- "Autômato" (classe NOVA) veio dividida DPS (Miyu/Ryouko Asakura/RyuZU/
  AnchoR) x Support (Yui, IA de suporte psicológico, não combatente) -
  aplicados os 4 DPS, Yui ficou de fora.

Faz backup do banco ANTES (mesmo padrão dos scripts de reclassificação
anteriores)."""
import shutil
import sys

from pandora import db

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKUP_PATH = db.CAMINHO_BANCO.replace("pandora.db", "pandora_backup_pre_reclassificar_apoiador_gpt_lote1_2026-09-06.db")

# (nome, série pra desambiguar ou None, classe destino, categoria, funcao_cidade)
MUDANCAS = [
    ("Amanda Werner", None, "Piloto", "DPS", "Militar"),
    ("Anak Zahard (Original)", None, "Guerreiro", "DPS", "Militar"),  # não encontrado - fica registrado, ignorado se não achar
    ("Anastasia L", None, "Mago", "DPS", "Militar"),
    ("AnchoR", None, "Autômato", "DPS", "Militar"),
    ("Angelina Kudou Shields", None, "Mago", "DPS", "Militar"),
    ("Anna (Fire Emblem)", "Fire Emblem", "Mercador", "Support", "Comércio"),
    ("Ai Ninomiya", None, "Atleta", "Tank", "Militar"),
    ("Aiko Kudou", None, "Atleta", "Tank", "Militar"),
    ("Aina Rumika", None, "Professor", "Support", "Administração"),
    ("Alisa Haiba", None, "Atleta", "Tank", "Militar"),
    ("Alter Ego", None, "Hacker", "Support", "Arcano"),
    ("707", None, "Hacker", "Support", "Arcano"),
    ("Amy Plie", None, "Curandeiro", "Support", "Saúde"),
    ("Aoi Asahina", None, "Atleta", "Tank", "Militar"),
    ("Aoi Miyamori", None, "Assistente", "Support", "Administração"),
    ("Aoi Ogiyama", None, "Atleta", "Tank", "Militar"),
    ("Aries", None, "Controlador", "Support", "Arcano"),
    ("Arisawa Tatsuki", None, "Lutador", "DPS", "Militar"),
    ("Ark Royal", None, "Piloto", "DPS", "Militar"),
    ("Atla", None, "Lutador", "DPS", "Militar"),
    ("Atsushi Murasakibara", None, "Atleta", "Tank", "Militar"),
    ("Aya Tsuji", None, "Encantador", "Support", "Comércio"),
    ("Ayamine Kei", None, "Piloto", "DPS", "Militar"),
    ("Azusa Hamaoka", None, "Atleta", "Tank", "Militar"),
    ("Baccarat", None, "Encantador", "Support", "Comércio"),
    ("Barbara Parker", None, "Mago", "DPS", "Militar"),
    ("Belzerg Stylish Sword Iris", None, "Espadachim", "DPS", "Militar"),
    ("Black March", None, "Espadachim", "DPS", "Militar"),
    ("Black Rabbit (Kuro Usagi)", None, "Lutador", "DPS", "Militar"),
    ("CFW Magic", None, "Guerreiro", "DPS", "Militar"),
    ("Carissa", None, "Espadachim", "DPS", "Militar"),
    ("Chen", None, "Mago", "DPS", "Militar"),
    ("Chinatsu Hiyama", None, "Atleta", "Tank", "Militar"),
    ("Chisa Kotegawa", None, "Atleta", "Tank", "Militar"),
    ("Chiyuri Kurashima", None, "Curandeiro", "Support", "Saúde"),
    ("Chuubou Sonken (Shoukyou)", None, "Lutador", "DPS", "Militar"),
    ("Claudia Lowetti", None, "Guerreiro", "DPS", "Militar"),
    ("Connie Christensen", None, "Atleta", "Tank", "Militar"),
    ("Cthuko (Kuuko)", None, "Mago", "DPS", "Militar"),
    ("Daichi Shijima", None, "Invocador", "DPS", "Militar"),
    ("Danua", None, "Invocador", "DPS", "Militar"),
    ("Darry Adai", None, "Piloto", "DPS", "Militar"),
    ("Dawn", None, "Invocador", "DPS", "Militar"),
    ("Demencia", None, "Lutador", "DPS", "Militar"),
    ("Dusk of Oolacile", None, "Mago", "DPS", "Militar"),
    ("Eina Tulle", None, "Assistente", "Support", "Administração"),
    ("Emi Ibarazaki", None, "Atleta", "Tank", "Militar"),
    ("Ellen Urnea Ortlinde", None, "Cavaleiro", "Tank", "Militar"),
    ("Erika Chiba", None, "Espadachim", "DPS", "Militar"),
    ("Eris", None, "Encantador", "Support", "Comércio"),
    ("Esmeraude", None, "Dragão", "DPS", "Militar"),
    ("Evan Edrok", None, "Estrategista", "Support", "Administração"),
    ("Filia Medici", None, "Lutador", "DPS", "Militar"),
    ("Futaba Aoi", None, "Protetor", "Tank", "Militar"),
    ("Gardenia", None, "Invocador", "DPS", "Militar"),
    ("Gin Tachibana", None, "Artilheiro", "DPS", "Militar"),
    ("Gray", None, "Guerreiro", "DPS", "Militar"),
    ("Gretel", None, "Mago", "DPS", "Militar"),
    ("Guila", None, "Espadachim", "DPS", "Militar"),
    ("Gwendolyn Stacy", None, "Lutador", "DPS", "Militar"),
    ("Han Song-I", None, "Guerreiro", "DPS", "Militar"),
    ("Haruna", None, "Guerreiro", "DPS", "Militar"),
    ("Hikari Kohinata", None, "Atleta", "Tank", "Militar"),
    ("Hinanawi Tenshi", None, "Espadachim", "DPS", "Militar"),
    ("Hiromi Maiharu", None, "Atleta", "Tank", "Militar"),
    ("Hokuto", None, "Invocador", "DPS", "Militar"),
    ("Houshou", None, "Piloto", "DPS", "Militar"),
    ("Ikaros", None, "Artilheiro", "DPS", "Militar"),
    ("Io Hasekura", None, "Controlador", "Support", "Arcano"),
    ("Isabela", None, "Colosso", "Tank", "Militar"),
    ("Iwaki Yoshimi", None, "Atleta", "Tank", "Militar"),
    ("Izuno Wasabi", None, "Curandeiro", "Support", "Saúde"),
    ("Jenny Realight", None, "Artilheiro", "DPS", "Militar"),
    ("Jessica Jones", None, "Lutador", "DPS", "Militar"),
    ("Josuke Higashikata", None, "Curandeiro", "Support", "Saúde"),
    ("Kahili", None, "Invocador", "DPS", "Militar"),
    ("Kairi", None, "Espadachim", "DPS", "Militar"),
    ("Kanna Kamui", None, "Dragão", "DPS", "Militar"),
    ("Kaoru Shimizu", None, "Atleta", "Tank", "Militar"),
    ("Karen Araragi", None, "Lutador", "DPS", "Militar"),
    ("Kasumi Yoshizawa", None, "Atleta", "Tank", "Militar"),
    ("Kiel", None, "Lutador", "DPS", "Militar"),
    ("Kiruka Ushirode", None, "Atleta", "Tank", "Militar"),
    ("Kiyoh Bachika", None, "Piloto", "DPS", "Militar"),
    ("Kokoa Shuzen", None, "Lutador", "DPS", "Militar"),
    ("Komaru Naegi", None, "Artilheiro", "DPS", "Militar"),
    ("Koyanskaya", None, "Artilheiro", "DPS", "Militar"),
    ("Kris", None, "Invocador", "DPS", "Militar"),
    ("Langa Hasegawa", None, "Atleta", "Tank", "Militar"),
    ("Lissa", None, "Curandeiro", "Support", "Saúde"),
    ("Lizsharte Atismata", None, "Piloto", "DPS", "Militar"),
    ("Makoto Tachibana", None, "Atleta", "Tank", "Militar"),
    ("Margaret", None, "Invocador", "DPS", "Militar"),
    ("Margaret Liones", None, "Curandeiro", "Support", "Saúde"),
    ("Marley", None, "Invocador", "DPS", "Militar"),
    ("Mary Smith", None, "Mago", "DPS", "Militar"),
    ("Masaki Kurosaki", None, "Atirador", "DPS", "Militar"),
    ("May", "Pokemon", "Invocador", "DPS", "Militar"),
    ("Maya Kyoudou", None, "Atirador", "DPS", "Militar"),
    ("Melie", None, "Mago", "DPS", "Militar"),
    ("Mashiro Arisaka", None, "Atleta", "Tank", "Militar"),
    ("Miyu", None, "Autômato", "DPS", "Militar"),
    ("Mogana Kikaijima", None, "Atleta", "Tank", "Militar"),
    ("Momo Nishimiya", None, "Místico", None, None),  # ja existe Support - sem conflito
    ("Morimura Seira", None, "Atleta", "Tank", "Militar"),
    ("Nagi Arisuin", None, "Assassino", "DPS", "Militar"),
    ("Nana", "Darling in the FranXX", "Assistente", "Support", "Administração"),
    ("Nanae Kokonoe", None, "Espadachim", "DPS", "Militar"),
    ("Nakano Ayaka", None, "Atleta", "Tank", "Militar"),
    ("Naomi Tanizaki", None, "Encantador", "Support", "Comércio"),
    ("Naruzo Machio", None, "Atleta", "Tank", "Militar"),
    ("Natsu Takasaki", None, "Atleta", "Tank", "Militar"),
    ("Nelliel Tu Odelschwanck", None, "Espadachim", "DPS", "Militar"),
    ("Nemu Kurotsuchi", None, "Colosso", "Tank", "Militar"),
    ("Neon Nostrade", None, "Oráculo", "Support", "Arcano"),
    ("Nono", None, "Artilheiro", "DPS", "Militar"),
    ("Orange Pekoe", None, "Piloto", "DPS", "Militar"),
    ("Mizuki Shibata", None, "Místico", None, None),
    ("Peorth", None, "Místico", None, None),
    ("Phoebe", None, "Invocador", "DPS", "Militar"),
    ("Raimu Bitou", None, "Hacker", "Support", "Arcano"),
    ("Reina Izumi", None, "Curandeiro", "Support", "Saúde"),
    ("Rikka Isurugi", None, "Assassino", "DPS", "Militar"),
    ("Rin Kaenbyou", None, "Invocador", "DPS", "Militar"),
    ("Ryouko Asakura", None, "Autômato", "DPS", "Militar"),
    ("RyuZU", None, "Autômato", "DPS", "Militar"),
    ("Sakura", None, "Lutador", "DPS", "Militar"),
    ("Satoka Sumihara", None, "Guerreiro", "DPS", "Militar"),
    ("Scavenger", None, "Guerreiro", "DPS", "Militar"),
    ("Seiun Sky", None, "Atleta", "Tank", "Militar"),
    ("Senia", None, "Espadachim", "DPS", "Militar"),
    ("Serena", None, "Curandeiro", "Support", "Saúde"),
    ("Sherria Blendy", None, "Curandeiro", "Support", "Saúde"),
    ("Shia Haulia", None, "Guerreiro", "DPS", "Militar"),
    ("Shion Karanomori", None, "Estrategista", "Support", "Administração"),
    ("Shoukaku", None, "Piloto", "DPS", "Militar"),
    ("Sora Takenouchi", None, "Invocador", "DPS", "Militar"),
    ("Souka", None, "Assassino", "DPS", "Militar"),
    ("Sunny Milk", None, "Encantador", "Support", "Comércio"),
    ("Suzutsuki", None, "Artilheiro", "DPS", "Militar"),
    ("Takenaka Tsubaki", None, "Atleta", "Tank", "Militar"),
    ("Tamiya Ryouko", None, "Lutador", "DPS", "Militar"),
    ("Therese Alexandrite", None, "Mago", "DPS", "Militar"),
    ("Tsugumi", None, "Hacker", "Support", "Arcano"),
    ("Uiharu Kazari", None, "Hacker", "Support", "Arcano"),
    ("Uruka Takemoto", None, "Atleta", "Tank", "Militar"),
    ("Ururu Tsumugiya", None, "Artilheiro", "DPS", "Militar"),
    ("Velvet", None, "Guerreiro", "DPS", "Militar"),
    ("Virgo", None, "Mago", "DPS", "Militar"),
    ("Wasp", None, "Piloto", "DPS", "Militar"),
    ("Yihwa Yeon", None, "Mago", "DPS", "Militar"),
    ("Yunyun", None, "Mago", "DPS", "Militar"),
    ("Yurika Nijino", None, "Mago", "DPS", "Militar"),
    ("Yuu Momokino", None, "Atirador", "DPS", "Militar"),
    ("Zenith Greyrat", None, "Curandeiro", "Support", "Saúde"),
    ("Zorome", None, "Piloto", "DPS", "Militar"),
]

# Ficam de FORA deste lote (conflito de categoria, ver docstring):
# Nadeko Sengoku, Sanae Kashimura, Xiao Xiao (Místico DPS x Support já
# existente), Shirai Kuroko (Psíquico DPS x Support já existente), Yui
# (Autômato Support x DPS já aplicado nos outros 4).


def main():
    shutil.copy2(db.CAMINHO_BANCO, BACKUP_PATH)
    print(f"Backup salvo em {BACKUP_PATH}")

    aplicados, nao_encontrados, ambiguos = [], [], []
    with db.conexao() as conn:
        for nome, serie_filtro, classe_destino, categoria, funcao in MUDANCAS:
            if categoria is not None:
                conn.execute(
                    "INSERT INTO colecao_classes (classe, categoria_combate, funcao_cidade) VALUES (?, ?, ?) "
                    "ON CONFLICT(classe) DO NOTHING",
                    (classe_destino, categoria, funcao),
                )
            query = "SELECT id, nome, serie FROM colecao_personagens WHERE nome = ? AND classe = 'Apoiador'"
            params = [nome]
            if serie_filtro:
                query += " AND serie = ?"
                params.append(serie_filtro)
            candidatos = conn.execute(query, params).fetchall()
            if not candidatos:
                nao_encontrados.append(nome)
                continue
            if len(candidatos) > 1:
                ambiguos.append((nome, [(c["id"], c["serie"]) for c in candidatos]))
                continue
            personagem = candidatos[0]
            conn.execute(
                "UPDATE colecao_personagens SET classe = ?, classe_exibicao = ? WHERE id = ?",
                (classe_destino, classe_destino, personagem["id"]),
            )
            aplicados.append((personagem["nome"], classe_destino))
        conn.commit()

    print(f"\n{len(aplicados)} personagem(ns) reclassificado(s).")
    if nao_encontrados:
        print(f"\n{len(nao_encontrados)} não encontrado(s) (fora deste lote):")
        for n in nao_encontrados:
            print(f"  {n}")
    if ambiguos:
        print(f"\n{len(ambiguos)} ainda ambíguo(s):")
        for n, opcoes in ambiguos:
            print(f"  {n}: {opcoes}")


if __name__ == "__main__":
    main()
