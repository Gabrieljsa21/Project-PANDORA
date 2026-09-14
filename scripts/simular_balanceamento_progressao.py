# -*- coding: utf-8 -*-
"""Simulador local para validar e, quando pedido, aplicar um cenário.

Mantém as proporções acordadas: Construção = Progressão ÷ 2, Torre =
Progressão × 2 e a distribuição de trabalhadores observada na conta de
referência. Os valores de coleção, CP da coleção e Party podem ser
sobrescritos para testar cenários diferentes.

Exemplos:
    python scripts/simular_balanceamento_progressao.py --nivel 200
    python scripts/simular_balanceamento_progressao.py --niveis 25,50,100,150,200
    python scripts/simular_balanceamento_progressao.py --nivel 200 --party-cp 201500
    python scripts/simular_balanceamento_progressao.py --nivel 150 --colecao 6000 --cp-colecao 90000000
    python scripts/simular_balanceamento_progressao.py --nivel 150 --aplicar --guild-id 1388541192806989834 --user-id 304469035607916545
    python scripts/simular_balanceamento_progressao.py --tabela-real --guild-id 1388541192806989834 --user-id 304469035607916545 --niveis 10,25,50,100,150,200,250
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# Referência atual usada somente para projetar cenários proporcionais. Todos
# os campos possuem argumento para substituição; o script nunca lê/escreve DB.
NIVEL_REFERENCIA = 200
COLECAO_REFERENCIA = 8_449
CP_COLECAO_REFERENCIA = 146_921_876
PARTY_CP_REFERENCIA = 201_500

# Fração da coleção total em cada área, observada na conta de referência.
# O restante cobre Party e personagens sem função de Cidade.
FRACAO_TRABALHADORES = {
    "Administração": 973 / COLECAO_REFERENCIA,
    "Militar": 3_077 / COLECAO_REFERENCIA,
    "Arcano": 738 / COLECAO_REFERENCIA,
    "Comércio": 1_365 / COLECAO_REFERENCIA,
    "Saúde": 208 / COLECAO_REFERENCIA,
    "Cultura": 526 / COLECAO_REFERENCIA,
}

RARIDADE_MEDIA_CATALOGO = 1.76
XP_BASE_PROGRESSAO = 150
TAXA_XP_ATUAL = 1.06


def nivel_construcao_esperado(nivel_progressao: int) -> int:
    """Arredonda 25/2 para 13; Progressão 200 resulta em Construção 100."""
    return max(1, (nivel_progressao + 1) // 2)


def andar_torre_esperado(nivel_progressao: int) -> int:
    return max(1, nivel_progressao * 2)


def xp_proximo_nivel_atual(nivel: int) -> int:
    return round(XP_BASE_PROGRESSAO * TAXA_XP_ATUAL ** (nivel - 1) / 10) * 10


def xp_proximo_nivel_proposto(nivel: int) -> int:
    """Preserva a curva de 6% até 150 e usa 4% dali em diante."""
    bruto = XP_BASE_PROGRESSAO * 1.06 ** (min(nivel, 150) - 1) * 1.04 ** max(nivel - 150, 0)
    return round(bruto / 10) * 10


def power_torre_atual(andar: int) -> int:
    """Curva legada, preservada apenas para comparação no simulador."""
    return round(1_000 * 1.06 ** (andar - 1) / 10) * 10


def power_torre_proposto(andar: int) -> int:
    """Curva vigente: 100K no 300 e 150K exatos no andar 400."""
    return round(1_000 * (1 + (andar - 1) / 13.31847454785192) ** 1.4597014494970986 / 10) * 10


def _fmt(numero: float | int) -> str:
    numero = round(numero)
    if abs(numero) >= 1_000_000_000:
        return f"{numero / 1_000_000_000:.1f}B".replace(".", ",")
    if abs(numero) >= 1_000_000:
        return f"{numero / 1_000_000:.1f}M".replace(".", ",")
    if abs(numero) >= 1_000:
        return f"{numero / 1_000:.1f}K".replace(".", ",")
    return f"{numero:,}".replace(",", ".")


def _percentual(numero: float) -> str:
    return f"{numero * 100:.1f}%".replace(".", ",")


def _horas(numero: float) -> str:
    if numero < 1:
        return f"{max(1, round(numero * 60))} min"
    return f"{numero:.1f}h".replace(".", ",")


def simular(nivel: int, colecao: int | None, cp_colecao: float | None, party_cp: float | None,
            claims_hora: float, vitorias_worldboss_dia: float) -> dict[str, float | int | dict[str, int]]:
    if nivel < 1:
        raise ValueError("Progressão precisa ser pelo menos 1.")
    escala = nivel / NIVEL_REFERENCIA
    colecao = colecao if colecao is not None else round(COLECAO_REFERENCIA * escala)
    cp_colecao = cp_colecao if cp_colecao is not None else CP_COLECAO_REFERENCIA * escala
    nivel_construcao = nivel_construcao_esperado(nivel)
    trabalhadores = {area: round(colecao * fracao) for area, fracao in FRACAO_TRABALHADORES.items()}
    marcos = {area: quantidade // 5 for area, quantidade in trabalhadores.items()}

    administracao = marcos["Administração"] * 0.00005 * nivel_construcao
    cruzamento = 1 + administracao
    cultura_hora = marcos["Cultura"] * 25 * nivel_construcao * cruzamento
    comercio_hora = marcos["Comércio"] * 50 * nivel_construcao * cruzamento
    saude_hora = marcos["Saúde"] * 0.5 * nivel_construcao * cruzamento
    militar = marcos["Militar"] * 10 * (nivel_construcao * 0.05) * cruzamento
    arcano = marcos["Arcano"] * 0.0001 * (nivel_construcao * 0.05) * cruzamento
    bonus_loot = cp_colecao / 100_000_000
    andar = andar_torre_esperado(nivel)
    xp_claim_hora = claims_hora * RARIDADE_MEDIA_CATALOGO * 15 * (1 + bonus_loot)
    xp_worldboss_dia = vitorias_worldboss_dia * 200 * (1 + bonus_loot)
    party_estimado = None
    if party_cp is not None:
        # Estimativa direcional: acompanha o multiplicador percentual de
        # Progressão + Maestria. CP de classe/Favorita pode divergir.
        multiplicador = 1 + (nivel // 5) / 100 + nivel * 0.02
        multiplicador_referencia = 1 + (NIVEL_REFERENCIA // 5) / 100 + NIVEL_REFERENCIA * 0.02
        party_estimado = party_cp * multiplicador / multiplicador_referencia

    return {
        "nivel": nivel, "colecao": colecao, "cp_colecao": cp_colecao, "construcao": nivel_construcao,
        "andar": andar, "trabalhadores": trabalhadores, "administracao": administracao,
        "cultura_hora": cultura_hora, "comercio_hora": comercio_hora, "saude_hora": saude_hora,
        "militar": militar, "arcano": arcano, "bonus_loot": bonus_loot,
        "xp_claim_hora": xp_claim_hora, "xp_worldboss_dia": xp_worldboss_dia,
        "xp_atual": xp_proximo_nivel_atual(nivel), "xp_proposto": xp_proximo_nivel_proposto(nivel),
        "power_atual": power_torre_atual(andar), "power_proposto": power_torre_proposto(andar),
        "party_estimado": party_estimado,
    }


def mostrar_resumo(dados: dict[str, float | int | dict[str, int]]) -> None:
    print(f"\n=== Progressão Lv{dados['nivel']} ===")
    print(f"Régua: Construções Lv{dados['construcao']} · Torre andar {dados['andar']}")
    print(f"Coleção projetada: {_fmt(dados['colecao'])} · CP coleção: {_fmt(dados['cp_colecao'])} · Loot: +{_percentual(dados['bonus_loot'])}")
    print("Trabalhadores: " + " · ".join(f"{area} {_fmt(qtd)}" for area, qtd in dados['trabalhadores'].items()))
    print(f"Cidade: Administração +{_percentual(dados['administracao'])} · Militar +{_fmt(dados['militar'])} CP · Arcano +{_percentual(dados['arcano'])}")
    print(f"Produção/h: Cultura {_fmt(dados['cultura_hora'])} XP · Comércio {_fmt(dados['comercio_hora'])} WiShards · Saúde {_fmt(dados['saude_hora'])} Soulstone")
    print(f"XP: claim {_fmt(dados['xp_claim_hora'])}/h · World Boss {_fmt(dados['xp_worldboss_dia'])}/dia · próximo nível atual {_fmt(dados['xp_atual'])} · proposto {_fmt(dados['xp_proposto'])}")
    print(f"Torre: alvo legado {_fmt(dados['power_atual'])} · alvo vigente {_fmt(dados['power_proposto'])}")
    if dados['party_estimado'] is not None:
        party = dados['party_estimado']
        print(f"Party estimada: {_fmt(party)} · margem no alvo proposto: {_fmt(party - dados['power_proposto'])}")


def aplicar_cenario(nivel: int, guild_id: str, user_id: str) -> tuple[Path, dict[str, int], dict[str, int]]:
    """Aplica somente os eixos da CONTA e cria backup SQLite consistente.

    Nunca toca em personagens, coleção, afinidade, Soulmate, Party, slots,
    itens ou moedas. O backup é feito antes de qualquer UPDATE.
    """
    from pandora import cidade, db

    nivel_construcao = nivel_construcao_esperado(nivel)
    andar = andar_torre_esperado(nivel)
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    caminho_backup = Path("data") / f"pandora_backup_cenario_lv{nivel}_{agora}.db"
    caminho_backup.parent.mkdir(parents=True, exist_ok=True)

    with db.conexao() as origem:
        destino = sqlite3.connect(caminho_backup)
        try:
            origem.backup(destino)
        finally:
            destino.close()

    with db.conexao() as conn:
        linha_progressao = conn.execute(
            "SELECT nivel, xp, nivel_treinamento_global, nivel_potencial_colecao "
            "FROM colecao_progressao WHERE guild_id = ? AND user_id = ?",
            (str(guild_id), str(user_id)),
        ).fetchone()
        antes = dict(linha_progressao) if linha_progressao else {
            "nivel": 1, "xp": 0, "nivel_treinamento_global": 0, "nivel_potencial_colecao": 0,
        }
        conn.execute(
            "INSERT INTO colecao_progressao (guild_id, user_id, nivel, xp, nivel_treinamento_global, nivel_potencial_colecao) "
            "VALUES (?, ?, ?, 0, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET nivel = excluded.nivel, xp = excluded.xp, "
            "nivel_treinamento_global = excluded.nivel_treinamento_global, "
            "nivel_potencial_colecao = excluded.nivel_potencial_colecao",
            (str(guild_id), str(user_id), nivel, nivel, nivel),
        )
        conn.execute(
            "INSERT INTO colecao_torre_progresso (guild_id, user_id, andar_atual) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET andar_atual = excluded.andar_atual",
            (str(guild_id), str(user_id), andar),
        )
        for area in db.AREAS_CONSTRUCAO:
            conn.execute(
                "INSERT INTO colecao_construcoes (guild_id, user_id, area, nivel) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(guild_id, user_id, area) DO UPDATE SET nivel = excluded.nivel",
                (str(guild_id), str(user_id), area, nivel_construcao),
            )

    cidade.atualizar_snapshot_bonus(guild_id, user_id)
    depois = {
        "nivel": nivel,
        "xp": 0,
        "nivel_treinamento_global": nivel,
        "nivel_potencial_colecao": nivel,
        "construcao": nivel_construcao,
        "andar": andar,
    }
    return caminho_backup, antes, depois


def tabela_real(guild_id: str, user_id: str, niveis: list[int]) -> list[dict[str, float | int]]:
    """Recalcula a Party e a Cidade reais para cada nível, sem gravar nada.

    Nível/Afinidade/Soulmate, Série, Classe, Favoritas, composição e a
    quantidade verdadeira de trabalhadores são preservados. Só Progressão,
    Treinamento, Maestria e níveis das Construções variam conforme a régua.
    """
    from pandora import cidade, db, torre

    equipe = list(db.obter_equipe(guild_id, user_id, "party").values())
    if not equipe:
        raise ValueError("A conta não tem Party montada.")
    niveis_personagem = db.nivel_em_lote(guild_id, user_id)
    _cp_total, por_funcao, _total = cidade._workforce_por_funcao(guild_id, user_id)
    quantidade = {area: por_funcao.get(area, {"qtd": 0})["qtd"] for area in cidade.FUNCOES_CIDADE}
    resultado = []
    for nivel in niveis:
        bonus_global = (
            nivel * db.BONUS_FIXO_POR_NIVEL_PROGRESSAO + nivel * db.BONUS_FIXO_POR_NIVEL_TREINAMENTO,
            ((nivel // db.NIVEIS_PROGRESSAO_POR_PONTO_PERCENTUAL) + nivel * db.BONUS_PERCENTUAL_POR_NIVEL_POTENCIAL) / 100,
        )
        membros = []
        for personagem in equipe:
            power, _nivel, categoria = torre.power_personagem(
                personagem, guild_id, user_id, nivel=niveis_personagem.get(personagem["id"], 1),
                bonus_global=bonus_global,
            )
            membros.append({"nome": personagem["nome"], "power": power, "categoria_combate": categoria})
        categorias = [m["categoria_combate"] for m in membros]
        composicao = torre.BONUS_COMPOSICAO_3_CATEGORIAS if {"DPS", "Tank", "Support"}.issubset(categorias) else 0.0
        apos_composicao = sum(m["power"] for m in membros) * (1 + composicao)
        nivel_construcao = nivel_construcao_esperado(nivel)
        administracao = cidade.bonus_area("Administração", quantidade["Administração"], nivel_construcao)
        cruzamento = 1 + administracao
        militar = cidade.bonus_area("Militar", quantidade["Militar"], nivel_construcao) * cruzamento
        arcano = cidade.bonus_area("Arcano", quantidade["Arcano"], nivel_construcao) * cruzamento
        resultado.append({
            "nivel": nivel,
            "membros": membros,
            "apos_composicao": apos_composicao,
            "cp_final": apos_composicao * (1 + arcano) + militar,
            "requisito_torre": torre.power_alvo_andar(andar_torre_esperado(nivel)),
            "wishards_hora": cidade.bonus_area("Comércio", quantidade["Comércio"], nivel_construcao) * cruzamento,
            "soulstone_hora": cidade.bonus_area("Saúde", quantidade["Saúde"], nivel_construcao) * cruzamento,
            "xp_hora": cidade.bonus_area("Cultura", quantidade["Cultura"], nivel_construcao) * cruzamento,
            "xp_proximo_nivel": db.xp_necessario_nivel(nivel),
        })
    return resultado


def mostrar_tabela_markdown(linhas: list[dict[str, float | int]]) -> None:
    nomes = [membro["nome"] for membro in linhas[0]["membros"]]
    cabecalho = ["Progressão", *(f"CP {nome}" for nome in nomes), "CP Após composição", "CP Final", "Requisito Torre", "WiShards/h", "Soulstone/h", "XP/h", "XP próximo nível", "Horas até próximo nível"]
    print("| " + " | ".join(cabecalho) + " |")
    print("| " + " | ".join("---:" if indice else "---" for indice, _ in enumerate(cabecalho)) + " |")
    for linha in linhas:
        cp_membros = [_fmt(membro["power"]) for membro in linha["membros"]]
        horas_proximo_nivel = linha["xp_proximo_nivel"] / linha["xp_hora"] if linha["xp_hora"] else float("inf")
        print(
            f"| Lv{linha['nivel']} | " + " | ".join(cp_membros) + f" | {_fmt(linha['apos_composicao'])} | "
            f"{_fmt(linha['cp_final'])} | {_fmt(linha['requisito_torre'])} | {_fmt(linha['wishards_hora'])} | "
            f"{_fmt(linha['soulstone_hora'])} | {_fmt(linha['xp_hora'])} | {_fmt(linha['xp_proximo_nivel'])} | {_horas(horas_proximo_nivel)} |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Simula Progressão/Cidade/Torre sem alterar dados.")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--nivel", type=int, help="Nível de Progressão a simular.")
    grupo.add_argument("--niveis", default="25,50,100,150,200", help="Lista de níveis para comparar.")
    parser.add_argument("--colecao", type=int, help="Coleção no cenário (padrão: proporcional à referência).")
    parser.add_argument("--cp-colecao", type=float, help="CP total da coleção no cenário (padrão: proporcional à referência).")
    parser.add_argument("--party-cp", type=float, default=PARTY_CP_REFERENCIA, help="Party de referência no Lv200; 0 desativa a estimativa.")
    parser.add_argument("--claims-hora", type=float, default=1, help="Claims por hora (padrão: 1).")
    parser.add_argument("--worldboss-vitorias-dia", type=float, default=4, help="Vitórias de World Boss por dia (padrão: 4).")
    parser.add_argument("--aplicar", action="store_true", help="Aplica o cenário de --nivel na conta indicada; cria backup antes.")
    parser.add_argument("--tabela-real", action="store_true", help="Tabela com Party/Cidade reais, sem alterar dados.")
    parser.add_argument("--guild-id", help="Guild da conta a alterar com --aplicar.")
    parser.add_argument("--user-id", help="Usuário da conta a alterar com --aplicar.")
    args = parser.parse_args()
    if args.aplicar and (args.nivel is None or not args.guild_id or not args.user_id):
        parser.error("--aplicar exige --nivel, --guild-id e --user-id.")
    if args.tabela_real and (not args.guild_id or not args.user_id):
        parser.error("--tabela-real exige --guild-id e --user-id.")
    niveis = [args.nivel] if args.nivel is not None else [int(valor.strip()) for valor in args.niveis.split(",") if valor.strip()]
    if args.tabela_real:
        mostrar_tabela_markdown(tabela_real(args.guild_id, args.user_id, niveis))
        return
    for nivel in niveis:
        dados = simular(nivel, args.colecao, args.cp_colecao, args.party_cp or None, args.claims_hora, args.worldboss_vitorias_dia)
        mostrar_resumo(dados)
    if args.aplicar:
        backup, antes, depois = aplicar_cenario(args.nivel, args.guild_id, args.user_id)
        print(f"\nCenário aplicado sem tocar nas personagens. Backup: {backup}")
        print(f"Antes: Progressão Lv{antes['nivel']} · Treinamento Lv{antes['nivel_treinamento_global']} · Maestria Lv{antes['nivel_potencial_colecao']}")
        print(f"Depois: Progressão Lv{depois['nivel']} · Treinamento/Maestria Lv{depois['nivel_treinamento_global']} · Construções Lv{depois['construcao']} · Torre {depois['andar']}")


if __name__ == "__main__":
    main()
