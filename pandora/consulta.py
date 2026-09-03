# -*- coding: utf-8 -*-
"""Consulta/coleção/wishlist/ranking do colecionador - separação inspirada
no `getInventory.ts`/`findCharacters.ts` do Fable (github.com/ker0olos/fable,
MIT). O roll/claim em si fica em `eris/colecao/gacha.py`."""
import difflib
import math

import discord

_PAGINA_TAMANHO = 10
_ESTRELAS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}
_CORTE_SIMILARIDADE_BUSCA = 0.3


def buscar_por_nome(personagens, consulta, limite=25):
    """Busca aproximada por nome (2026-08-30, pedido do usuário: "ja tenho
    mais de 50 personagens, e discord so lista 25... msm eu n acertando
    nome, traz os mais proximos") - substring vira prioridade máxima (o
    caso comum, digitar parte certa do nome), o resto cai pra similaridade
    de texto (`difflib`) pra tolerar erro de digitação/memória errada do
    nome. `consulta` vazia devolve os primeiros `limite` sem filtrar (a
    ordem de quem chama, ex. `db.colecao_do_usuario` já vem por raridade)."""
    consulta_normalizada = consulta.strip().lower()
    if not consulta_normalizada:
        return personagens[:limite]

    def pontuacao(personagem):
        nome = personagem["nome"].lower()
        if consulta_normalizada in nome:
            return 1.0 + len(consulta_normalizada) / len(nome)
        # 🔥 comparar só com o NOME INTEIRO penaliza demais um erro de
        # digitação numa palavra só (ex.: "asnua" vs "asuna yuuki" fica
        # com nota baixa por causa do "yuuki" sobrando) - compara também
        # palavra por palavra e fica com a MELHOR nota entre as duas
        # formas, pra tolerar erro de digitação em nome de 1 palavra só.
        nota_nome_inteiro = difflib.SequenceMatcher(None, consulta_normalizada, nome).ratio()
        nota_por_palavra = max(
            (difflib.SequenceMatcher(None, consulta_normalizada, palavra).ratio() for palavra in nome.split()),
            default=0.0,
        )
        return max(nota_nome_inteiro, nota_por_palavra)

    pontuados = [(pontuacao(p), p) for p in personagens]
    pontuados = [par for par in pontuados if par[0] > _CORTE_SIMILARIDADE_BUSCA]
    pontuados.sort(key=lambda par: par[0], reverse=True)
    return [p for _pontuacao, p in pontuados[:limite]]


def _truncar_seguro(texto):
    """Rede de segurança contra o limite de 2000 caracteres do Discord
    (2026-08-29, achado real em produção - `formatar_pendentes` sem corte
    deixou `/colecao_disponiveis` estourar 2700 caracteres depois de uma
    puxada grande, e `interaction.response.send_message` falhava OUTRO
    lugar não tratava isso, virando "aplicativo não respondeu" sem
    nenhuma pista). Usada por todo formatador de LISTA aqui - nenhum
    corta de propósito (ver `_LIMITE_TEXTO_PENDENTES`/`_PAGINA_TAMANHO`),
    isso só protege contra nomes/séries incomumente longos empurrando o
    total pra cima do limite mesmo com poucos itens."""
    return texto if len(texto) <= 1990 else texto[:1990] + "…"


def linha_personagem(personagem):
    estrelas = _ESTRELAS.get(personagem["raridade"], "?")
    linha = f"{estrelas} **{personagem['nome']}**"
    # 🔥 Classe só aparece se JÁ foi revelada (reivindicada ao menos 1 vez em
    # algum servidor) - continua "secreta" pra quem nunca foi reivindicada
    # ainda, ver `eris/colecao/gacha.py::revelar_classe`. Mostra a forma de
    # EXIBIÇÃO (concorda com o gênero da personagem, ex. "Ladina"), nunca a
    # canônica salva pra estatísticas ("Ladino") - cai pra `classe` se não
    # tiver `classe_exibicao` (linhas antigas, de antes dessa distinção).
    if personagem.get("classe"):
        linha += f" [{personagem.get('classe_exibicao') or personagem['classe']}]"
    if personagem.get("serie"):
        linha += f" ({personagem['serie']})"
    # 🔥 Afinidade só existe quando `personagem` veio de `db.colecao_do_
    # usuario` (join com `colecao_afinidade`) - busca/wishlist não têm essa
    # chave, por isso o `.get` em vez de `[...]` (ERIS_sistema_colecao_
    # wishards.md Seção 7).
    if personagem.get("afinidade") is not None:
        # 🔥 Soulmate (2026-08-29, Prova de Soulmate) - `is_soulmate` é o
        # status REAL (só vira 1 depois de vencer a Prova em Afinidade 10),
        # não mais um auto-flag de "afinidade >= 10". Marcador cosmético
        # próprio (`💞`, trocado de `💍`) em vez de "❤️10" - mesmo estado
        # visual de sempre, só a condição que muda.
        linha += " 💞" if personagem.get("is_soulmate") else f" ❤️{personagem['afinidade']}"
    return linha


_CORES_RARIDADE = {1: 0x95A5A6, 2: 0x2ECC71, 3: 0x3498DB, 4: 0x9B59B6, 5: 0xF1C40F}


def embed_carta_personagem(personagem):
    """Card completo de UMA personagem - raridade, classe, série, imagem e
    vínculo (Afinidade/Soulmate, se já tiver) - MESMAS infos de quando ela
    foi reivindicada (`gacha._embed_confirmacao_claim`), disponíveis a
    qualquer momento depois (2026-08-30, pedido do usuário: "qnd eu coleto
    a personagem, mostra a raridade, classe e foto dela. Tem outra forma
    de ver isso?" - botão "🔍 Personagem" do hub `/pandora`)."""
    embed = discord.Embed(title=personagem["nome"], color=_CORES_RARIDADE.get(personagem["raridade"], 0x2ECC71))
    embed.add_field(name="Raridade", value=_ESTRELAS.get(personagem["raridade"], "?"), inline=True)
    if personagem.get("classe"):
        embed.add_field(name="Classe", value=personagem.get("classe_exibicao") or personagem["classe"], inline=True)
    else:
        embed.add_field(name="Classe", value="_(ainda não revelada)_", inline=True)
    if personagem.get("serie"):
        embed.add_field(name="Série", value=personagem["serie"], inline=True)
    if personagem.get("afinidade") is not None:
        vinculo = "💞 Soulmate" if personagem.get("is_soulmate") else f"❤️ Afinidade {personagem['afinidade']}"
        embed.add_field(name="Vínculo", value=vinculo, inline=True)
    if personagem.get("imagem_url"):
        embed.set_image(url=personagem["imagem_url"])
    return embed


def linha_populares(indice_global, personagem):
    """Linha do `/populares` (2026-08-29, pedido do usuário: "tem comando
    para listar personagens por popularidade?") - mesma linha de sempre
    (`linha_personagem`), com a posição no ranking global (não só na
    página atual) e o número de curtidas da fonte."""
    return f"{indice_global}. {linha_personagem(personagem)} - {personagem.get('popularidade', 0)} curtidas"


class ViewColecao(discord.ui.View):
    """Paginação simples (◀️/▶️) - mesmo padrão de `musica.ViewListaVotos`,
    sem select por enquanto (nenhuma ação por item ainda). `formatador_linha`
    (opcional) recebe `(posição_global, personagem)` - default reaproveita
    `linha_personagem` ignorando a posição (mesmo texto de sempre pra
    `/colecao`/wishlist); `/populares` passa `linha_populares`."""

    def __init__(self, titulo, personagens, pagina=0, formatador_linha=None):
        super().__init__(timeout=180)
        self._titulo = titulo
        self._personagens = personagens
        self._pagina = pagina
        self._formatador_linha = formatador_linha or (lambda indice, p: linha_personagem(p))
        self._montar()

    @property
    def _total_paginas(self):
        return max(1, math.ceil(len(self._personagens) / _PAGINA_TAMANHO))

    def _pagina_atual(self):
        inicio = self._pagina * _PAGINA_TAMANHO
        return self._personagens[inicio:inicio + _PAGINA_TAMANHO]

    def _montar(self):
        self.clear_items()
        anterior = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary, disabled=self._pagina == 0)
        anterior.callback = self._ir_anterior
        self.add_item(anterior)
        proxima = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary, disabled=self._pagina >= self._total_paginas - 1)
        proxima.callback = self._ir_proxima
        self.add_item(proxima)

    def formatar(self):
        if not self._personagens:
            return f"{self._titulo}\n\nNenhuma personagem ainda."
        inicio = self._pagina * _PAGINA_TAMANHO
        linhas = [self._formatador_linha(inicio + indice + 1, p) for indice, p in enumerate(self._pagina_atual())]
        return (
            f"{self._titulo} ({len(self._personagens)} no total, página {self._pagina + 1}/{self._total_paginas}):\n"
            + "\n".join(linhas)
        )

    async def _ir_anterior(self, interaction: discord.Interaction):
        self._pagina -= 1
        self._montar()
        await interaction.response.edit_message(content=self.formatar(), view=self)

    async def _ir_proxima(self, interaction: discord.Interaction):
        self._pagina += 1
        self._montar()
        await interaction.response.edit_message(content=self.formatar(), view=self)


def formatar_equipe(titulo, equipe, max_posicoes, formatador_linha=None):
    """`equipe`: {posicao: personagem_dict} de `db.obter_equipe` - Party
    (Seção 17) e Vitrine (Seção 15) usam a mesma forma, só o título muda.
    `formatador_linha` (opcional, recebe só a personagem) - default
    reaproveita `linha_personagem`; a Party passa uma versão com ícone de
    categoria de combate + CP (2026-08-30, ver `paineis.ViewPartyEquipe`)."""
    formatador_linha = formatador_linha or linha_personagem
    linhas = []
    for posicao in range(1, max_posicoes + 1):
        personagem = equipe.get(posicao)
        if personagem:
            linhas.append(f"{posicao}. {formatador_linha(personagem)}")
        else:
            linhas.append(f"{posicao}. _(vazio)_")
    return f"**{titulo}:**\n" + "\n".join(linhas)


def formatar_pendentes(pendentes, raridade_filtrada=None):
    """`pendentes`: [(message_id, personagem), ...] de `gacha.personagens_
    pendentes` (2026-08-29, `/colecao_disponiveis`) - já vem ordenado por
    POPULARIDADE DESC e cortado na FONTE pelo `limite` de quem chamou
    (`/colecao_disponiveis` usa `limite=10` - "retornar apenas os 10
    melhores", pedido original do usuário) - aqui só formata o que já
    chegou, sem cortar de novo."""
    if not pendentes:
        if raridade_filtrada is not None:
            return f"Nenhuma personagem {_ESTRELAS.get(raridade_filtrada, '?')} disponível pra reivindicar agora."
        return "Nenhuma personagem disponível pra reivindicar agora."
    linhas = [f"{indice + 1}. {linha_personagem(p)}" for indice, (_, p) in enumerate(pendentes)]
    titulo = "Personagens mais populares ainda disponíveis pra reivindicar"
    if raridade_filtrada is not None:
        titulo += f" ({_ESTRELAS.get(raridade_filtrada, '?')})"
    return _truncar_seguro(f"**{titulo}**:\n" + "\n".join(linhas))


def formatar_busca(termo, personagens):
    if not personagens:
        return f'Nenhum personagem encontrado pra "{termo}".'
    linhas = [f"{linha_personagem(p)} - `#{p['id']}`" for p in personagens]
    return _truncar_seguro(f'Resultados pra "{termo}":\n' + "\n".join(linhas))


_LIMITE_TEXTO_WISHLIST = 25  # mesma folga de `_LIMITE_TEXTO_PENDENTES` - sem cap em `db.wishlist_listar`, cresce livre


def formatar_wishlist(personagens):
    if not personagens:
        return "Sua wishlist tá vazia - use `/wishlist adicionar` com o `#id` de um personagem (ver `/personagem <nome>`)."
    total = len(personagens)
    personagens = personagens[:_LIMITE_TEXTO_WISHLIST]
    sufixo = f" (mostrando as {_LIMITE_TEXTO_WISHLIST} de {total} - use o painel `/pandora` -> Wishlist pra ver todas)" if total > _LIMITE_TEXTO_WISHLIST else ""
    linhas = [f"{linha_personagem(p)} - `#{p['id']}`" for p in personagens]
    return _truncar_seguro(f"Sua wishlist{sufixo}:\n" + "\n".join(linhas))


# 🔥 Título/unidade por métrica (2026-09-02, "rankings expandidos" -
# Seção 25 do plano original) - `db.ranking_guild` devolve sempre
# {"dono_id", "total"} pra QUALQUER métrica (`db.RANKINGS_DISPONIVEIS`
# lista as chaves válidas), mas o TEXTO precisa dizer o que "total"
# significa em cada uma (personagens/Soulmates/andar da Torre) - mapeado
# aqui em vez de importar `db` (este módulo é formatação pura, sempre
# recebeu os dados já prontos de quem chamou)."""
_RANKINGS = {
    "colecao": ("📚 Coleção", "personagens"),
    "soulmates": ("💞 Soulmates", "Soulmates"),
    "torre": ("🗼 Torre", "andar da Torre"),
}


def formatar_ranking(guild, ranking, metrica="colecao"):
    if not ranking:
        return "Ninguém tem essa métrica registrada nesse servidor ainda."
    titulo, unidade = _RANKINGS.get(metrica, _RANKINGS["colecao"])
    linhas = []
    for posicao, linha in enumerate(ranking, start=1):
        membro = guild.get_member(int(linha["dono_id"])) if guild else None
        nome = membro.display_name if membro else f"<@{linha['dono_id']}>"
        linhas.append(f"{posicao}. {nome} - {linha['total']} {unidade}")
    return _truncar_seguro(f"**{titulo} do servidor:**\n" + "\n".join(linhas))


