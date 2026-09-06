# -*- coding: utf-8 -*-
"""Loja, Merge/Sacrifício e Trocas bilaterais do Colecionador
(ERIS_sistema_colecao_wishards.md Seções 10-14) - roll/claim/reencontro
ficam em `eris/colecao/gacha.py`, consulta/coleção/wishlist em `eris/
colecao/consulta.py`. Aqui ficam as ações econômicas que não nascem de um
roll.

🔥 Trocas SEM reserva ativa de recursos durante a proposta (simplificação
deliberada pra escala pessoal, diferente do que o plano original sugeria) -
`validar_proposta` é chamada tanto ao criar quanto ao aceitar, nunca
confiando no que a proposta dizia na hora de criar."""
import discord

from pandora import db

_ESTRELAS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}

# 🔥 Trocas com uma conta de BOT (GAIA/ERIS, donas de personagem via
# `eris/colecao/auto_colecionador.py`) são resolvidas na hora, sem esperar
# clique - pedido do usuário (2026-08-29): "elas aceitam trocar se o valor
# oferecido for 10x oq pagaram... contanto q a soma seja superior ou igual a
# 10x". Qualquer conta de bot no servidor conta como NPC (não só as duas
# conhecidas hoje - evita hardcodar ID de conta, mesmo padrão de "não
# hardcode" já seguido no resto do ERIS).
LIMIAR_TROCA_NPC = 10


def valor_loja_personagens(personagem_ids):
    """Soma `db.valor_base_wishards` (o preço que cada uma custaria se
    fosse comprada na Loja agora) das personagens dadas - mesmo número
    usado como "valor" de uma personagem em toda regra econômica do
    Colecionador (claim/reencontro/troca com NPC). Pública (2026-09-02,
    pedido do usuário: mostrar esse valor na UI de Trocar antes de digitar
    quanto pagar) - era `_valor_personagens`, só usada aqui dentro."""
    total = 0
    for pid in personagem_ids:
        p = db.personagem_por_id(pid)
        if p:
            total += db.valor_base_wishards(p["raridade"])
    return total


def avaliar_proposta_npc(proposta):
    """"O que pagaram" = `db.valor_base_wishards` da(s) personagem(ns)/
    WiShards que a NPC está sendo pedida a dar - mesmo número usado em todo
    lugar como "valor" de uma personagem (recompensa de claim/reencontro).
    Devolve (aceita: bool, motivo: str)."""
    custo = proposta["pede_wishards"] + valor_loja_personagens(proposta["pede_personagens"])
    oferecido = proposta["oferece_wishards"] + valor_loja_personagens(proposta["oferece_personagens"])
    limiar = custo * LIMIAR_TROCA_NPC
    if oferecido >= limiar:
        return True, f"{oferecido} de valor recebido (≥ {limiar}, 10x o que estava dando)."
    return False, f"só {oferecido} de valor ofertado - precisava de pelo menos {limiar} (10x o que estava pedindo)."


def formatar_loja(raridade, personagens):
    preco = db.PRECOS_LOJA[raridade]
    if not personagens:
        return f"Nenhuma personagem {_ESTRELAS[raridade]} livre nesse servidor agora (será que já foi tudo comprado/reivindicado?)."
    linhas = [f"`#{p['id']}` {p['nome']}" for p in personagens]
    return f"{_ESTRELAS[raridade]} custam {db.fmt_numero(preco)} WiShards cada - use `/loja comprar <#id>`:\n" + "\n".join(linhas)


def parse_ids_personagens(texto):
    """"12, 45,78" -> [12, 45, 78] - vazio/None vira lista vazia. Ignora
    pedaços que não são número em vez de quebrar o comando inteiro."""
    if not texto:
        return []
    return [int(pedaco.strip()) for pedaco in texto.split(",") if pedaco.strip().isdigit()]


def validar_proposta(guild_id, proponente_id, oferece_personagens, oferece_wishards, alvo_id, pede_personagens, pede_wishards):
    """Revalidação COMPLETA - usada tanto ao criar quanto ao aceitar a
    proposta. Devolve (ok: bool, erro: str)."""
    for pid in oferece_personagens:
        if db.dono_do_personagem(guild_id, pid) != str(proponente_id):
            return False, f"Você não tem (mais) a personagem #{pid}."
    if oferece_wishards and db.saldo_wishards(guild_id, proponente_id) < oferece_wishards:
        return False, "Você não tem WiShards suficientes pra essa oferta."
    for pid in pede_personagens:
        if db.dono_do_personagem(guild_id, pid) != str(alvo_id):
            return False, f"A outra pessoa não tem (mais) a personagem #{pid}."
    if pede_wishards and db.saldo_wishards(guild_id, alvo_id) < pede_wishards:
        return False, "A outra pessoa não tem WiShards suficientes pra dar."
    return True, ""


def _executar_troca(guild_id, proposta):
    for pid in proposta["oferece_personagens"]:
        db.transferir_personagem(guild_id, pid, proposta["alvo_id"])
    for pid in proposta["pede_personagens"]:
        db.transferir_personagem(guild_id, pid, proposta["proponente_id"])
    if proposta["oferece_wishards"]:
        db.creditar_wishards(guild_id, proposta["proponente_id"], -proposta["oferece_wishards"], "troca", referencia=str(proposta["id"]))
        db.creditar_wishards(guild_id, proposta["alvo_id"], proposta["oferece_wishards"], "troca", referencia=str(proposta["id"]))
    if proposta["pede_wishards"]:
        db.creditar_wishards(guild_id, proposta["alvo_id"], -proposta["pede_wishards"], "troca", referencia=str(proposta["id"]))
        db.creditar_wishards(guild_id, proposta["proponente_id"], proposta["pede_wishards"], "troca", referencia=str(proposta["id"]))


def formatar_proposta(proposta):
    def _lado(personagens, wishards):
        partes = []
        for pid in personagens:
            p = db.personagem_por_id(pid)
            partes.append(p["nome"] if p else f"#{pid}")
        if wishards:
            partes.append(f"{db.fmt_numero(wishards)} WiShards")
        return ", ".join(partes) if partes else "nada"

    return (
        f"<@{proposta['proponente_id']}> propõe pra <@{proposta['alvo_id']}>:\n"
        f"Oferece: {_lado(proposta['oferece_personagens'], proposta['oferece_wishards'])}\n"
        f"Pede: {_lado(proposta['pede_personagens'], proposta['pede_wishards'])}"
    )


class ViewTroca(discord.ui.View):
    """Aceitar/Recusar restrito ao ALVO da proposta - revalida tudo de novo
    no aceite (`validar_proposta`, nada fica reservado entre a proposta e o
    aceite)."""

    def __init__(self, proposta_id, alvo_id):
        super().__init__(timeout=600)
        self.proposta_id = proposta_id
        self.alvo_id = str(alvo_id)

    async def _checar_alvo(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.alvo_id:
            await interaction.response.send_message("Essa proposta não é pra você.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Aceitar", style=discord.ButtonStyle.success, emoji="🤝")
    async def aceitar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        if not await self._checar_alvo(interaction):
            return
        proposta = db.obter_proposta_troca(self.proposta_id)
        if proposta is None or proposta["status"] != "pendente":
            await interaction.response.send_message("Essa proposta não existe mais ou já foi resolvida.", ephemeral=True)
            return
        ok, erro = validar_proposta(
            proposta["guild_id"], proposta["proponente_id"], proposta["oferece_personagens"], proposta["oferece_wishards"],
            proposta["alvo_id"], proposta["pede_personagens"], proposta["pede_wishards"],
        )
        for item in self.children:
            item.disabled = True
        if not ok:
            db.atualizar_status_proposta(self.proposta_id, "cancelada")
            await interaction.response.edit_message(content=f"Troca cancelada - {erro}", view=self)
            return
        _executar_troca(proposta["guild_id"], proposta)
        db.atualizar_status_proposta(self.proposta_id, "aceita")
        await interaction.response.edit_message(content="✅ Troca concluída!", view=self)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, emoji="✖️")
    async def recusar(self, interaction: discord.Interaction, botao: discord.ui.Button):
        if not await self._checar_alvo(interaction):
            return
        db.atualizar_status_proposta(self.proposta_id, "recusada")
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ Troca recusada.", view=self)


def validar_merge(guild_id, user_id, ids, confirmar=False):
    """1ª etapa do Merge (2026-09-02, pedido do usuário: "ele vai deixar
    trocar 5 da msm raridade por 1 da msm raridade disponivel, a escolha"
    - deixou de subir sorteado pra raridade seguinte, virou escolha do
    jogador DENTRO da mesma raridade) - só valida as 5 personagens a
    sacrificar, SEM escolher/reivindicar nada ainda (quem chama mostra a
    lista de disponíveis pro jogador escolher, depois chama `executar_
    merge` com a escolha). Devolve (ok, mensagem_ou_None, raridade_ou_None,
    precisa_confirmar) - `precisa_confirmar` só é True no caso específico
    de Afinidade > 1 sem `confirmar=True` (os outros erros são
    definitivos); quem chama decide como pedir essa confirmação."""
    if len(set(ids)) != 5:
        return False, "As 5 personagens precisam ser diferentes entre si.", None, False
    personagens = {i: db.personagem_por_id(i) for i in ids}
    faltando = [i for i, p in personagens.items() if p is None]
    if faltando:
        return False, f"Esse #id não existe no catálogo: {faltando[0]}.", None, False
    for i in ids:
        if db.dono_do_personagem(guild_id, i) != str(user_id):
            return False, f"Você não tem a personagem #{i} nesse servidor.", None, False

    # 🔥 Bloqueio DURO pra Party, sem opção de confirmar (Seção 15: "nunca
    # selecionar... Party" - diferente de favorita/Afinidade alta, que só
    # pedem confirmação, a Party nem deixa passar).
    na_party = [i for i in ids if db.esta_na_party(guild_id, user_id, i)]
    if na_party:
        return False, f"A personagem #{na_party[0]} está na sua Party - tire ela de lá antes de sacrificar.", None, False

    raridade = personagens[ids[0]]["raridade"]
    if any(p["raridade"] != raridade for p in personagens.values()):
        return False, "As 5 personagens precisam ser da MESMA raridade.", None, False

    afinidades = [db.afinidade(guild_id, user_id, i) for i in ids]
    if any(a > 1 for a in afinidades) and not confirmar:
        return False, "Pelo menos uma dessas personagens tem vínculo (Afinidade > 1).", raridade, True

    return True, None, raridade, False


def executar_merge(guild_id, user_id, ids, escolha_id):
    """2ª etapa do Merge - o jogador JÁ escolheu (`escolha_id`) qual
    personagem DISPONÍVEL da MESMA raridade quer receber (`validar_merge`
    já rodou antes, é quem chama que garante isso). REVALIDA TUDO de novo
    aqui, incluindo Party (2026-09-02, pedido do usuário: "N permita fazer
    merge de personagens no grupo" - `validar_merge` já bloqueava isso na
    1ª etapa, mas o jogador pode adicionar uma das 5 à Party DEPOIS de
    validar e ANTES de escolher quem recebe, nessa janela entre as 2
    etapas) - devolve (ok: bool, mensagem: str).

    🔥 Ordem das ações (2026-09-02, correção do usuário: "Não pode de
    forma alguma deixar 2 jogadores terem a msm personagem... só de fato
    realizar todas as ações após o claim") - `db.reivindicar` (INSERT
    atômico, `ON CONFLICT DO NOTHING`) roda PRIMEIRO e é o único ponto que
    decide se o Merge acontece; as 5 sacrificadas só são removidas DEPOIS
    dele confirmar sucesso. A versão anterior fazia o oposto (removia as 5
    ANTES de reivindicar, sem checar o resultado) - se a escolhida fosse
    reivindicada por outra pessoa bem no meio disso, o jogador perdia as 5
    personagens sem receber nada em troca."""
    personagens = {i: db.personagem_por_id(i) for i in ids}
    if any(p is None for p in personagens.values()) or any(db.dono_do_personagem(guild_id, i) != str(user_id) for i in ids):
        return False, "Uma das personagens sacrificadas não é mais sua - Merge cancelado."
    raridade = personagens[ids[0]]["raridade"]
    if any(p["raridade"] != raridade for p in personagens.values()):
        return False, "As 5 personagens precisam ser da MESMA raridade - Merge cancelado."
    na_party = [i for i in ids if db.esta_na_party(guild_id, user_id, i)]
    if na_party:
        return False, f"A personagem #{na_party[0]} entrou na sua Party nesse meio-tempo - tire ela de lá e tente de novo."
    escolhida = db.personagem_por_id(escolha_id)
    if escolhida is None or escolhida["raridade"] != raridade:
        return False, "Personagem escolhida inválida - Merge cancelado."

    if not db.reivindicar(guild_id, escolha_id, user_id):
        return False, "Essa personagem já foi reivindicada por outra pessoa nesse meio-tempo - escolha outra."

    for i in ids:
        db.remover_propriedade_sem_pagamento(guild_id, i, user_id)
    db.definir_afinidade_inicial(guild_id, user_id, escolha_id)
    # 🔥 XP de Progressão (2026-08-30, análise do usuário Seção 4:
    # "desenvolver personagens" inclui o Merge) - baseado na raridade das
    # 5 sacrificadas (a nova é da MESMA raridade agora, não faria diferença
    # de qualquer forma).
    db.creditar_xp_progressao(guild_id, user_id, 25 * raridade)
    # 🔥 Contador vitalício (2026-09-01, Conquistas do Colecionador,
    # "col_merges") - sem rastro histórico em nenhuma outra tabela (só
    # claims/trocas são deriváveis do ledger/`colecao_troca_proposta`).
    db.incrementar_merges_realizados(guild_id, user_id)
    estrelas = "⭐" * raridade
    mensagem = f"🔮 Merge concluído! 5 personagens {estrelas} viraram **{escolhida['nome']}** {estrelas}."
    return True, mensagem


def criar_e_avaliar_troca(guild_id, proponente_id, alvo, oferece_ids, oferece_wishards, pede_ids, pede_wishards):
    """Núcleo de `/trocar propor` - extraído de `eris/bot.py::_trocar_
    propor` (2026-08-29) pra ser compartilhado com o painel `🔄 Trocas`
    (`eris/colecao/paineis.py`). `alvo`: `discord.Member`/`discord.User` de
    verdade (usa `.id`/`.bot`/`.display_name`/`.mention`). Devolve (status,
    mensagem, view_ou_None):
    - "erro" - mensagem já pronta pra mandar ephemeral, sem view.
    - "npc_aceita"/"npc_recusada" - conta de bot decidiu na hora (`avaliar_
      proposta_npc`), sem view; só "npc_recusada" deve ser ephemeral.
    - "pendente" - proposta de verdade criada, `view` é o `ViewTroca` pra
      mandar junto (NUNCA ephemeral - o alvo precisa poder clicar)."""
    if alvo.id == proponente_id:
        return "erro", "Não dá pra propor uma troca com você mesmo.", None
    if not oferece_ids and not oferece_wishards and not pede_ids and not pede_wishards:
        return "erro", "Oferta vazia dos dois lados - proponha alguma personagem ou WiShards.", None

    ok, erro = validar_proposta(guild_id, proponente_id, oferece_ids, oferece_wishards, alvo.id, pede_ids, pede_wishards)
    if not ok:
        return "erro", erro, None

    proposta_id = db.criar_proposta_troca(guild_id, proponente_id, alvo.id, oferece_ids, oferece_wishards, pede_ids, pede_wishards)
    proposta = db.obter_proposta_troca(proposta_id)

    # 🔥 Conta de BOT (GAIA/ERIS) decide na hora, sem esperar clique - ver
    # `avaliar_proposta_npc`.
    if alvo.bot:
        aceita, motivo = avaliar_proposta_npc(proposta)
        if aceita:
            _executar_troca(guild_id, proposta)
            db.atualizar_status_proposta(proposta_id, "aceita")
            return "npc_aceita", f"{formatar_proposta(proposta)}\n🤖 {alvo.display_name} topou na hora - {motivo}", None
        db.atualizar_status_proposta(proposta_id, "recusada")
        return "npc_recusada", f"{formatar_proposta(proposta)}\n🤖 {alvo.display_name} recusou - {motivo}", None

    view = ViewTroca(proposta_id, alvo.id)
    return "pendente", f"{alvo.mention} {formatar_proposta(proposta)}", view
