# -*- coding: utf-8 -*-
"""Painel-raiz `/pandora` (renomeado de `/waifu` em 2026-09-02, pedido do
usuário) do Colecionador (2026-08-29, pedido do usuário: "os
bots estão ficando muito poluídos" - inspirado no LegendsAwaken,
`C:\\Workspace\\LegendsAwaken`, projeto próprio dele). Reduz o Colecionador
de ~18 comandos raiz pra 1 hub com botões (embed + View editada/reenviada
na mesma conversa), no mesmo espírito do LA: 1 comando por sistema,
navegação depois via componente, sem subcomando.

Módulo NOVO dedicado a painel (mirror do `Panels/` do LA) - `gacha.py`/
`consulta.py`/`economia.py` continuam sendo a camada de dado/regra, SEM
mudança de lógica interna; aqui só orquestra embed+View a partir do que
elas já expõem. Cada botão do hub manda uma resposta NOVA (nunca edita a
mensagem do hub) - o hub continua clicável pra abrir outro sub-painel, sem
precisar de botão de "◀️ Voltar" nesta 1ª leva.

🔥 Fase 1 (aprovada, EM ANDAMENTO) - passo 1 (Rolar/Coleção) e passo 2
(Perfil/Wishlist) prontos; Party/Loja/Trocar/Ranking entram em passos
seguintes, ver o plano da sessão que criou isto. Os comandos antigos
equivalentes (`/colecao`, `/populares`, `/colecao_disponiveis`,
`/carteira`, `/ranking`, `/favoritar`, `/divorciar`, `/merge`,
`/wishlist`) continuam existindo até cada botão ser validado ao vivo -
`/pandora` é aditivo, não remove nada ainda.

Desde 2026-11-10 é um pacote dividido por tela (era um arquivo só de 5,9
mil linhas). Este `__init__` reexporta tudo, então `from pandora import
paineis` e `paineis.<nome>` continuam valendo. Dependência entre os
módulos sempre nesta ordem (nunca o contrário, senão vira import
circular): comum -> personagem -> equipe -> cidade -> colecao -> loja -> batalha -> inventario -> series -> waifus -> hub."""
from pandora.paineis.comum import (
    _COR_HUB,
    _MODOS_COLECAO,
    _ModalBuscarCatalogoWishlist,
    _ModalBuscarPersonagem,
    _ModalBuscarPosicaoOuNome,
    _TETO_OPCOES_DROPDOWN_LOJA,
    _ViewConfirmar,
    _ViewConfirmarComprarTudo,
    _ViewEscolherAlvo,
    _ViewEscolherMergeAlvo,
    _ViewEscolherRanking,
    _ViewFiltrarCategoria,
    _ViewSelecionarPersonagem,
    _descricao_personagem_dropdown,
    _descricao_personagem_livre_dropdown,
    _fmt_numero,
    _posicao_por_nome,
)
from pandora.paineis.personagem import (
    _ROTULO_ORIGEM_XP,
    _TEXTO_BONUS_POR_FUNCAO,
    _UNIDADE_CURTA_POR_FUNCAO,
    _ViewNivel,
    _embed_detalhes_cp_personagem,
    _embed_progressao_cidade,
    _fluxo_progressao_cidade,
    _numero_valor_curto,
    _pips_construcao,
    _sufixo_aviso_sem_classe,
    _texto_detalhe_calculo,
    _texto_valor_curto,
)
from pandora.paineis.equipe import (
    ViewEquipe,
    _fluxo_comprar_item_view,
    _fluxo_upar_construcao_direto,
    _fluxo_usar_upgrade_construcao,
)
from pandora.paineis.cidade import (
    ViewCidadeHub,
    _ViewTorre,
    _embed_cidade,
    _embed_cidade_area_detalhe,
    _embed_detalhes_party,
    _embed_torre,
    _fluxo_detalhe_area_cidade,
    _resumo_subir_max,
)
from pandora.paineis.colecao import (
    ViewColecaoHub,
    ViewWishlistHub,
    _ModalAdicionarWishlist,
    _ModalBuscarPosicaoOuNomeWishlist,
)
from pandora.paineis.loja import (
    ViewLoja,
    _ModalBuscarNomeLoja,
    _ModalWishardsTroca,
    _SUFIXOS_ENTRADA_NUMERO,
    _ViewComprarPersonagem,
    _ViewConfirmarValoresTroca,
    _ViewEscolherAlvoTroca,
    _ViewEscolherPersonagensTroca,
    _ViewEscolherRaridadeLoja,
    _embed_batalha,
    _embed_resultado_final,
    _int_seguro,
    _membro_ou_none,
    _texto_valores_troca,
)
from pandora.paineis.batalha import (
    SchedulerBatalha,
    ViewBatalhaHub,
    ViewWorldBossHub,
    _ViewEscolherAlvoBatalha,
    _ViewEscolherFormacaoBatalha,
    _ViewWorldBossAuto,
    _anunciar_desafio,
    _resolver_e_revelar,
)
from pandora.paineis.inventario import (
    ViewBonusClasseHub,
    ViewConquistasHub,
    ViewInventarioHub,
    _ModalInvestirEmMassa,
    _ORDEM_CATEGORIAS_BONUS,
    _ViewInvestirEmMassa,
)
from pandora.paineis.series import (
    _LARGURA_TITULO_SERIE,
    _ModalBuscarPosicaoOuNomeSerie,
    _ModalDefinirSerieFavorita,
    _ViewEscolherSerieFavorita,
    _ViewNavegarSerie,
    _ViewPerfil,
    _ViewSeriesFavoritas,
    _definir_serie_e_atualizar,
    _enviar_series_favoritas,
    _fmt_pct,
    _montar_embed_perfil,
    _montar_embed_series_favoritas,
    _nome_campo_serie,
)
from pandora.paineis.waifus import (
    _ViewPersonagensFavoritas,
)
from pandora.paineis.hub import (
    ViewHubWaifu,
    abrir_fusao,
    montar_embed_hub,
)
