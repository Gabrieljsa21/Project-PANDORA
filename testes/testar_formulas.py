"""Fórmulas puras de balance (sem banco) e o contrato usado pelo bot."""
import inspect

from pandora import batalha, db, economia, itens, paineis, torre


def testar_custo_de_construcao_bate_com_os_exemplos_do_pedido():
    # "Lv19->20 = 250K, Lv99->100 = 2M" (2026-09-07)
    assert itens.custo_construcao(20) == 250_000
    assert itens.custo_construcao(100) == 2_000_000


def testar_custo_de_construcao_nunca_cai_com_o_nivel():
    custos = [itens.custo_construcao(n) for n in range(2, 400)]
    assert custos == sorted(custos)


def testar_custo_total_de_construcao_e_a_soma_dos_degraus():
    assert itens.custo_total_construcao(18, 3) == sum(itens.custo_construcao(n) for n in (19, 20, 21))
    assert itens.custo_total_construcao(5, 0) == 0


def testar_custo_total_ate_nivel_e_aditivo():
    for raridade in (1, 3, 5):
        teto = db.NIVEL_MAXIMO_PERSONAGEM
        inteiro = db.custo_total_ate_nivel(raridade, 1, teto)
        partes = db.custo_total_ate_nivel(raridade, 1, 4) + db.custo_total_ate_nivel(raridade, 4, teto)
        assert inteiro == partes


def testar_power_alvo_da_torre_cresce_com_o_andar():
    alvos = [torre.power_alvo_andar(andar) for andar in range(1, 500)]
    assert alvos == sorted(alvos)
    assert all(alvo % 10 == 0 for alvo in alvos)


def testar_confronto_de_categorias_e_antissimetrico():
    categorias = ["DPS", "Tank", "Support", None]
    for a in categorias:
        assert batalha.resolver_confronto(a, a) == 0
        for b in categorias:
            assert batalha.resolver_confronto(a, b) == -batalha.resolver_confronto(b, a)
    vitorias = [batalha.resolver_confronto(a, b) for a in categorias[:3] for b in categorias[:3]]
    assert vitorias.count(1) == 3 and vitorias.count(-1) == 3


def testar_precos_de_garantia_sao_metade_da_loja():
    for raridade, preco in db.PRECOS_GARANTIA.items():
        assert preco == db.PRECOS_LOJA[raridade] // 2


def testar_fmt_numero_aceita_inteiro_e_decimal():
    assert isinstance(db.fmt_numero(1_250_000), str)
    assert isinstance(db.fmt_numero(0.5), str)


def testar_contrato_usado_pelo_bot():
    """O ERIS importa estes nomes direto. Mudar assinatura aqui sem mudar
    lá foi o que quebrou o `/merge` por 2 meses."""
    assert list(inspect.signature(economia.executar_merge).parameters) == ["guild_id", "user_id", "ids", "escolha_id"]
    assert list(inspect.signature(economia.validar_merge).parameters) == ["guild_id", "user_id", "ids", "confirmar"]
    assert inspect.iscoroutinefunction(paineis.abrir_fusao)
    for nome in ("ViewHubWaifu", "montar_embed_hub", "SchedulerBatalha"):
        assert hasattr(paineis, nome)
