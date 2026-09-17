# TODO - Project PANDORA

### Decidir o que fazer com `andar_atual_torre` inflado (2026-09-06)

**Prioridade:** Alta | **Complexidade:** Baixa (decisão) / Média (se migrar)

Com o Power da Party corrigido (bug de fórmula + 2 recalibrações da
Cidade, ver CHANGELOG), o andar HONESTO alcançável pela conta testada
hoje é ~104 - mas `andar_atual_torre` continua gravado em 398 (artefato
do bug acumulado, nunca reduzido - Torre nunca pune). Pendente decisão
do usuário: (1) deixar como está - a conta só não avança/vence
tentativas novas até reconstruir Power de verdade, sem nenhuma migração;
(2) resetar `andar_atual_torre` pra refletir o Power real de cada conta
(script de migração, provavelmente afeta TODAS as contas que já
progrediram na Torre, não só a testada - qualquer andar alcançado
enquanto os bugs de CP estavam ativos está igualmente inflado). Opção
(1) é mais simples e já é o comportamento atual, sem precisar de nada
novo.

### Validar teto de Construção em 50 + clamp de 25 opções ao vivo (2026-09-07)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado (ver `ARQUITETURA.md` - "Teto dinâmico de Construção: degrau
10 -> 50"): `db.NIVEL_MAXIMO_CONSTRUCAO_BASE` virou 50 (era 10),
permanente - "P subir p 51, todas tem de ta 50. P subir p 101, todas tem
de ta em 100" (pedido do usuário, depois de descartar uma 1ª versão
condicional que nunca chegou a subir). Testado só via script direto
contra o banco real (teto calculado certo pros níveis reais da conta -
30/30/30/30/40/30 -> teto 50). Clamp de 25 opções em `_ViewEscolherAlvo`
testado isolado (área no Lv1/teto 50 -> exatamente 25 opções geradas, sem
estourar o limite do Discord). Falta confirmar ao vivo: abrir "🏙️ Cidade",
clicar "💰 Upar Construção" ou "🏗️ Usar Upgrade de Construção" numa área
com margem grande até o teto (diferença > 25) e conferir que o dropdown
abre normalmente (sem erro do Discord) mostrando só as primeiras 25
opções; comprar aos poucos e confirmar que uma 2ª rodada do dropdown
continua de onde parou; deixar TODAS as 6 áreas baterem o teto de 50 e
conferir que o próximo teto vira 100 (não trava nem quebra a leitura).

### Validar "Upar Construção" + Comércio recalibrado + botão "📈 Progressão" ao vivo (2026-09-07)

**Prioridade:** Alta | **Complexidade:** Baixa

🔥 **SUPERA o item anterior sobre preço LINEAR do item da Loja** (mesmo
dia - o usuário pediu pra tirar o item da Loja de vez, ver `ARQUITETURA.md`
- "Upar Construção substitui o item da Loja"). Estado final: "🏗️ Upgrade
de Construção" SAIU da Loja (só drop/prêmio agora); novo botão "💰 Upar
Construção" no painel da Cidade paga WiShards direto por área, preço
FIXO por faixa de 10 níveis (`itens.FAIXAS_CUSTO_CONSTRUCAO`, igual pras
6 áreas - Lv19→20=250K, Lv99→100=2M, testado exato contra os 8 exemplos
do usuário); `cidade.BONUS_BASE_POR_AREA["Comércio"]` caiu de 250 pra 50.
`db.creditar_xp_progressao` ganhou `origem` obrigatório + ledger novo
(`colecao_xp_progressao_ledger`, 10 pontos do código etiquetados, incluindo
World Boss que tinha ficado de fora na 1ª leva) + botão "📈 Progressão" no
painel da Cidade (`db.xp_por_origem`). **Tudo só validado por script
direto contra o banco real** (compra de "Upar Construção" testada e
revertida manualmente, sem sujar a conta real) - nenhum clique real no
Discord ainda. Falta confirmar ao vivo: abrir "🛒 Loja" e ver que "🏗️
Upgrade de Construção" SUMIU da lista de compra; abrir "🏙️ Cidade",
clicar "💰 Upar Construção", escolher uma área e conferir o preço/nível
subindo certo (e o bônus de CP/produção da Party refletindo NA HORA, sem
precisar reabrir a Cidade - fix do achado sobre `atualizar_snapshot_bonus`
que faltava nos 2 fluxos); clicar "🏗️ Usar Upgrade de Construção" com um
item guardado (de drop) e conferir que continua funcionando de graça;
vencer um World Boss e conferir que o XP aparece em "📈 Progressão" sob
"🐉 World Boss (vitória)"; abrir "📈 Progressão" - conferir Nível/XP atual
+ próximo limiar, e que uma
ação que credita XP (Claim, Upar Nível, vencer andar da Torre, etc.)
aparece na lista "Fontes de XP acumuladas" depois de feita.

🔥 2 ajustes de UI na MESMA leva (também só testados via script): "🏗️
Usar Upgrade de Construção" só aparece com pelo menos 1 item guardado
(rótulo mostra a quantidade, "(x3)") - conferir que uma conta SEM item
não vê o botão, e que ganhar um (drop/Diária) faz ele aparecer depois de
clicar "🔄 Atualizar" (a View é reconstruída do zero agora, não reaproveita
mais a mesma instância - conferir que isso não quebrou nada mais do
painel); "📈 Progressão" foi pra ANTES de "🔄 Atualizar" na 1ª fileira
("Coloca o progressao antes do botao atualizar, na primeira fileira") -
conferir a ordem visual real no Discord.

### Validar Marcos da Cidade por Construção + tela de detalhe reformulada ao vivo (2026-09-07)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado a partir de `C:\Workspace\PANDORA_marcos_cidade.md` (especificação
completa do usuário, salva em arquivo à parte - fórmula: "M = floor(P/5);
B_marco = B_base × Lv; B_total = M × B_marco"): as 6 áreas (Militar/Saúde/
Cultura/Administração/Comércio/Arcano) usam essa MESMA fórmula agora, sem
retorno decrescente, Nível de Construção multiplicando direto o
bônus-base (`cidade.bonus_area`/`BONUS_BASE_POR_AREA`). Correção no mesmo
dia: "tem q começar ja no lv1" - uma área sem NENHUM Upgrade de Construção
comprado floreava Lv0 (bônus zero); `cidade.nivel_efetivo_construcao`
agora usa piso de 1. 2ª correção no mesmo dia: **"A tela das areas parece
q n teve modificações"** - a tela de detalhe por área (`_embed_cidade_
area_detalhe`, aberta pelos 6 botões do painel) ainda usava o layout
ANTIGO (tabela ✅/🔒 de 50 a 10.000 personagens, de antes deste
documento) - reformulada pro layout que o documento pede (campos
"Trabalhando aqui"/"Bônus atual"/"Marcos"/"Próximo marco"/"📊 Detalhes do
cálculo", sem listar marcos individualmente). 3ª correção no mesmo dia:
**"Quero q as areas tenham as infos do calculo mais detalhadas... B_final
= M × B_base × Lv × (1 + A)"** - "📊 Detalhes do cálculo" virou 3 blocos
(Fórmula/Variáveis/Cálculo, `_texto_detalhe_calculo`) com a fórmula do
usuário, conferida certa contra o código (Administração sai sem o termo
`(1 + A)`, nunca cruza sobre si mesma). Tudo validado só via script
direto contra a conta real (valores batendo com os exemplos do
documento E com o exemplo numérico do pedido de detalhamento - Militar
595 marcos × 10 × Lv10 × (1+0,179) = 70,2K CP), NENHUM clique real no
Discord ainda. Falta confirmar ao vivo: abrir "🏙️ Cidade" e conferir os 6
bônus do painel principal; clicar em
cada um dos 6 botões de área e comparar a tela de detalhe com a seção
"Exibição sugerida no Discord" do documento (Trabalhando aqui/Bônus
atual/Marcos/Próximo marco/📊 Detalhes batendo); conferir que uma área
sem NENHUM Upgrade de Construção comprado mostra "Lv1" (não "Lv0") e já
rende bônus; comprar um Upgrade de Construção numa área e ver TUDO
escalar (Bônus atual, valor de cada marco, e a linha de Detalhes); abrir
a Torre e ver o Power da Party refletindo o novo bônus de Militar/Arcano.

### Conferir 2 personagens não encontrados no catálogo (2026-09-06)

**Prioridade:** Baixa | **Complexidade:** Baixa

**Gwendolyn Stacy** (Spider-Gwen/Marvel) e **Shia Haulia** não foram
achados no catálogo mesmo testando variantes de nome/gênero - ou não
existem no banco sob nenhuma grafia próxima, ou pertencem a uma série
que nunca foi importada. Confirmar se vale re-adicionar manualmente
depois (fora do escopo desta leva de reclassificação).

### Expandir desconto de Nível de Progressão pros outros custos (2026-09-06)

**Prioridade:** Baixa | **Complexidade:** Média

Usuário pediu Nível de Progressão influenciando "tudo, desde custo ate
drop e rolls" - implementado por enquanto só em Treinamento Global/
Potencial da Coleção (`db.desconto_por_nivel_progressao`, ver CHANGELOG).
Faltam: Loja "Comprar"/"Garantir raridade"/Upgrade de Rolls/Upgrade de
Claims/itens (`itens.custo_total_item`); Upar Nível/Aumentar Afinidade
(individual E "Investir em Massa", `torre.investir_nivel_em_massa`/
`investir_afinidade_em_massa`). Escopo reduzido de propósito nesta leva -
threading de `guild_id`/`user_id` em várias funções de custo hoje PURAS
(só recebem nível/raridade) espalhadas por `db.py`/`itens.py`/`torre.py`
é um refactor maior, arriscado de fazer com pressa (`custo_proximo_
nivel`/`custo_proxima_afinidade` são chamados em LOOP pra coleção inteira
no Investir em Massa - precisa calcular o desconto 1x FORA do loop, nunca
por personagem, mesmo cuidado já tomado em `gacha.rolar_varios`/
`db.pontos_bonus_raridade_por_nivel` nesta mesma leva, senão reabre a
classe de bug "GAIA não respondeu a tempo" por N+1 de consulta).

### `/merge` (comando de barra) provavelmente quebra ao ser usado (achado 2026-09-06)

**Prioridade:** Alta | **Complexidade:** Baixa

Achado auditando o código pra escrever `FUNCIONALIDADES.md`: o comando
`/merge` em `C:\Workspace\Project-ERIS\eris\bot.py` (linha ~1094) chama
`economia.executar_merge(guild_id, user_id, ids, confirmar)` (4 argumentos)
e tenta desempacotar 3 valores de retorno, mas a função real em
`pandora/economia.py` tem assinatura `executar_merge(guild_id, user_id,
ids, escolha_id)` e devolve só 2 valores - assinatura mudou em 2026-09-02
(Merge virou escolha do jogador em vez de sorteio aleatório) e o comando de
barra nunca foi atualizado junto. Precisa: (1) confirmar ao vivo que `/merge`
de fato quebra com `TypeError`; (2) decidir se o comando é corrigido pra
bater com a assinatura nova (a UI real da Fusão hoje é um fluxo de 2 etapas
- escolher as 5 pra sacrificar, depois escolher o alvo entre até 25 livres
- que não cabe bem num único comando de slash sem parâmetros; talvez o
comando deva só abrir o mesmo painel do botão "🧬 Fusão" em vez de tentar
replicar o fluxo por parâmetro) ou removido, já que o botão "🧬 Fusão" do
hub `/pandora` já cobre o fluxo funcionando de verdade.

### Validar navegador de Waifus + dropdown de Fortalecimento ao vivo (2026-09-06)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado (`_ViewPersonagensFavoritas` virou navegador único com ◀️/▶️
**+ dropdown "💖 Ir direto pro slot..."** (`_montar_select_slots`, add-on
depois de faltar na 1ª versão), mesmo espírito de "🔍 Personagem"; "💪
Fortalecer" virou dropdown "até qual patamar ir" reaproveitando
`_ViewEscolherAlvo` generalizado) mas só validado por leitura de código,
sem clique real no Discord - substitui o item anterior (validar "⚡
Fortalecer ao Máximo"), que não existe mais. Precisa confirmar ao vivo:
abrir "💖 Waifus" e navegar por TODOS os slots com ◀️/▶️ (vazios e
ocupados, setas desabilitando certo nas pontas) E com o dropdown (escolher
um slot longe da posição atual e conferir que pula direto pra lá, com a
opção certa marcada como `default` da próxima vez que abrir o dropdown;
cada slot ocupado mostrando classe/CP final/CP base/Nível/Afinidade/ícone
de categoria, igual todo outro dropdown de personagem do jogo - CP final
batendo com o "Power atual" mostrado no card, não com o Power natural);
conferir que o card completo mostra imagem/classe/vínculo + campos de
Power/Fortalecimento/Ascensão juntos, com o rodapé "X/Y" certo; clicar
"💪 Fortalecer" e ver o dropdown listando cada patamar com custo
ACUMULADO certo (bate com a soma de `CUSTOS_FORTALECIMENTO`); escolher a
1ª opção (equivale ao antigo 1 clique) e a ÚLTIMA (equivale ao antigo
"gastar tudo") e conferir que ambas cobram/desbloqueiam certo; testar com
saldo insuficiente pro custo total escolhido (mensagem de erro, nada
cobrado); conferir que Trocar/Esvaziar/Ascender/Comprar slot continuam
funcionando iguais dentro do novo navegador.

### Validar 💖 Personagens Favoritas (Fortalecimento/Ascensão) ao vivo (2026-09-03)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado por completo (novo módulo `pandora/personagens_favoritas.py`,
tabela `colecao_personagens_favoritas`, hook em `torre.power_final`/
`power_personagem`, botão "💖 Favoritas" no hub) e validado só por
simulação isolada contra um banco temporário (algoritmo de gap-filling
batendo com os exemplos do pedido original, Fortalecimento sequencial
custando certo, `power_personagem` refletindo o Power Base do slot) -
NENHUM clique real no Discord ainda. Precisa confirmar ao vivo: escolher
personagem pro slot (Modal de busca), Fortalecer algumas vezes seguidas
(saldo de Soulstone descontando certo, embed atualizando), trocar a
personagem do slot e confirmar que o Fortalecimento comprado PERSISTE
(não reseta) mas a nova personagem só aproveita depois de preencher a
lacuna dela mesma, e o fluxo de Ascensão (precisa de uma personagem real
no teto de Nível/Afinidade/Soulmate pra testar de verdade - pode não
haver uma disponível na conta de teste ainda). Também confirmar que
"👥 Party"/`/party` (mesma tabela `colecao_equipe`) não foi afetado pela
remoção da Vitrine.

### Validar novo bônus de Série Favorita (exige série inteira + Afinidade) ao vivo (2026-09-03)

**Prioridade:** Média | **Complexidade:** Baixa

Implementado e validado contra o banco real em modo leitura (KonoSuba
100% possuída/maximizada -> 15%; Naruto 100% possuída mas não maximizada
-> só 5%) - falta confirmar ao vivo: abrir "📖 Perfil" e conferir que a
nova linha "❤️" (Afinidade) aparece certa nas Séries Favoritas; trocar
uma série favorita incompleta por outra e ver o bônus recalcular na
hora; se der pra testar, completar de verdade uma série pequena (100%
posse + nível + afinidade) e conferir que os 4 marcos aparecem com ✅ e
o bônus bate com +20%.

### Validar navegação por posição/bloco/busca no navegador de Série ao vivo (2026-09-03)

**Prioridade:** Média | **Complexidade:** Baixa

Implementado e validado só contra uma cópia ISOLADA do banco real (série
com 166 personagens - posição 93 -> bloco 76-100, posição 101 -> bloco
101-125, pulo de bloco, busca por posição e por nome resolvendo certo,
clamping além do total) - falta confirmar ao vivo: abrir o navegador de
uma série grande (mais de 25 personagens) e segurar "▶️"/"⏭️" até passar
do 25º sem travar; conferir que o select "🔄 Trocar de personagem"
sempre mostra o bloco certo (com a posição no rótulo); clicar "🔎
Buscar" e testar tanto um número (posição) quanto um nome; conferir que
"🛒 Comprar"/"⭐ Favoritar" continuam funcionando normalmente dentro
desse novo esquema de navegação.

### Validar "Maximizar Nível/Afinidade" escopado à Série ao vivo (2026-09-03)

**Prioridade:** Baixa | **Complexidade:** Baixa

Implementado e validado só contra uma cópia isolada do banco real (166
personagens de Naruto de uma conta real - investir em massa escopado
subiu nível/afinidade só delas, personagens de outras séries
confirmadas intocadas) - falta confirmar ao vivo: no navegador de
Série, clicar "⬆️ Maximizar Nível" ou "💕 Maximizar Afinidade", digitar
um orçamento e conferir que só as personagens DAQUELA série (que você
já possui) sobem - o resto da coleção não deve ser afetado; tentar
clicar sem possuir nenhuma personagem da série (deve recusar com
mensagem clara, não abrir o Modal). Também falta confirmar (2026-09-06,
`_reeditar_apos_acao_em_massa`) que o CARD do navegador (o que estava
aberto quando o Modal foi chamado) é reeditado sozinho com o CP/Nível/
Afinidade atualizados da personagem exibida no momento, sem precisar
fechar e reabrir o navegador.

### Validar "Comprar Tudo" + revelação de classe na compra ao vivo (2026-09-03)

**Prioridade:** Média | **Complexidade:** Baixa

Implementado e validado só contra uma cópia do banco real (`comprar_com_
revelacao` não trava com a GAIA fora do ar, preview do "Comprar Tudo"
calcula certo, confirmar compra todas as livres de uma série real e
zera as livres restantes) - falta confirmar ao vivo: no navegador de
Série, clicar "🛍️ Comprar Tudo" e conferir que a mensagem nova mostra
quantidade+preço total+saldo certos; clicar "Confirmar" e ver o resumo
final (quantas compradas, quanto gastou); clicar "Cancelar" e conferir
que não compra nada; comprar uma personagem NUNCA reivindicada em
nenhum servidor (tanto pela Loja quanto pelo "🛒 Comprar"/"🛍️ Comprar
Tudo" do navegador) com a GAIA rodando de verdade e confirmar que a
classe é revelada igual um claim normal (antes saía sem classe pra
sempre). Também falta confirmar (2026-09-06, `_reeditar_apos_acao_em_
massa`) que, depois de "Confirmar", o CARD do navegador original (por
trás da mensagem de confirmação) é reeditado sozinho mostrando "✅ Já é
sua"/dono certo pra personagem exibida no momento, sem precisar fechar e
reabrir o navegador.

### Validar navegador de Série Favorita (com Favoritar) + teto de 25 slots ao vivo (2026-09-03)

**Prioridade:** Média | **Complexidade:** Baixa

Implementado e validado só contra uma cópia do banco real (18
personagens de Fate/Stay Night carregados, comprar uma livre transfere
posse certa e libera o Favoritar na hora, os 3 estados de card -
livre/sua/de outro jogador - mostram certo, favoritar/desfavoritar
funciona pra quem já possui e recusa pra quem não possui, 20 upgrades
de slot chegam em exatamente 25 sem estourar limite do Discord) - falta
confirmar ao vivo: abrir "❤️ Séries Favoritas" e conferir que agora é
1 SELECT "✏️ Escolher/trocar/limpar um slot..." em vez de botões
individuais (comportamento de escolher/trocar/limpar deve continuar
igual, só a forma de abrir mudou); comprar alguns slots de verdade e
ver o preço subindo pela curva nova; escolher uma série no "🎬 Navegar
por uma Série Favorita..." e clicar "⭐ Favoritar" numa personagem que
já é sua (deve favoritar e aparecer depois em "⭐ Favoritos" no Perfil);
tentar favoritar uma que não é sua (deve recusar com mensagem clara).

### Validar busca por nome na Loja "Comprar" ao vivo (2026-09-03)

**Prioridade:** Média | **Complexidade:** Baixa

Implementado e validado só contra uma cópia do banco real (busca vazia
= amostra aleatória de sempre; "gerheade" = 1 resultado exato; "aoi" =
12 resultados; comprar um resultado da busca transfere posse certa) -
falta confirmar ao vivo: "🛒 Loja" -> "Comprar" -> escolher raridade ->
Modal abre; digitar um nome parcial mostra o dropdown filtrado certo;
deixar vazio mantém o comportamento antigo (amostra aleatória); comprar
uma personagem achada pela busca debita WiShards e transfere a posse.

### Validar lista de Favoritos + Favoritos/Wishlist no Perfil, e cooldown removido (2026-09-03)

**Prioridade:** Média | **Complexidade:** Baixa

Implementado e validado só contra uma cópia do banco real (lista de
favoritos batendo, hub sem botão Wishlist, Perfil com Favoritos/Wishlist,
troca de slot repetida sem bloqueio) - falta confirmar ao vivo: abrir
"📖 Perfil" -> "⭐ Favoritos" com personagens favoritadas de verdade
(paginação ◀️/▶️ se tiver mais de 10); abrir "📖 Perfil" -> "⭐ Wishlist"
e confirmar que funciona igual antes (agora só mudou de lugar); nas
Séries Favoritas, trocar o MESMO slot 2x seguidas de verdade no Discord
e confirmar que não aparece mais "Esse slot só pode trocar de novo em N
dia(s)".

### Validar dropdown de desambiguação ao escolher Série Favorita ao vivo (2026-09-02)

**Prioridade:** Média | **Complexidade:** Baixa

Implementado e validado só contra uma cópia do banco real (busca
ambígua "fate" -> 13 candidatas, dropdown real; busca com 1 candidata só
via substring "konosuba" -> TAMBÉM mostra o dropdown, com 1 opção só;
nome EXATO com case errado -> aplica direto, sem dropdown) - falta
confirmar ao vivo: digitar um nome exato (deve aplicar direto, sem
dropdown); digitar um termo aproximado que bate só 1 série (deve abrir
o dropdown com 1 opção, não aplicar sozinho); digitar um termo ambíguo
tipo "fate"/"sword art" (deve abrir um select de verdade com várias
opções - escolher uma deve aplicar E atualizar o painel "❤️ Séries
Favoritas" original); digitar algo que não bate com nada (deve dar erro
claro, sem dropdown nenhum).

### Validar fix DE VERDADE de "GAIA nao respondeu a tempo" nas Séries Favoritas (2026-09-02)

**Prioridade:** Alta | **Complexidade:** Baixa

Achado em PRODUÇÃO pelo usuário, 2 rodadas - o 1º fix (`str`/`int` no
dono do painel) era um bug real mas NÃO era a causa do sintoma; um log
`[SERIES]` passo a passo provou que o clique nunca chegava no callback.
Causa raiz de verdade (ver "⚠️ Nunca construir uma `discord.ui.View`
dentro de `asyncio.to_thread`" em `ARQUITETURA.md`): `_ViewSeriesFavoritas.
criar` construía a View inteira dentro de um `to_thread`, deixando o
`__stopped` interno do discord.py como `None` pra sempre - `_dispatch_
item` descartava QUALQUER clique em silêncio por causa disso. Corrigido
separando o fetch caro (`to_thread`) da construção da View (thread
principal) - validado chamando `View._dispatch_item` de verdade (o
mecanismo real do discord.py, não um mock aproximado): antes devolvia
`None` (clique descartado), depois devolve uma `Task` que roda o callback
até o fim. Ainda assim, **nenhum clique real no Discord** - falta
confirmar: abrir "❤️ Séries", clicar num slot (deve abrir o Modal),
escolher uma série e confirmar que salva; clicar "Comprar Slot" e
confirmar que desbloqueia (debita WiShards, aparece o slot novo).

### Validar remoção em massa da Wishlist ao vivo (2026-09-02)

**Prioridade:** Baixa | **Complexidade:** Baixa

Implementado (select "Remover da wishlist" ganhou `max_values=len(página
atual)`) - falta confirmar ao vivo: abrir "⭐ Wishlist", marcar vários
itens de uma vez no select "Remover" e confirmar que todos somem da lista
numa única ação.

### Validar renomeação `/pandora`/`/pandora_admin` + botões + Perfil ao vivo (2026-09-02)

**Prioridade:** Média | **Complexidade:** Baixa

Implementado e validado só via import/construção de View contra uma cópia
do banco real (rótulos conferidos um a um) - falta confirmar ao vivo:
`/pandora` abre o hub com o título "🎴 Pandora" e sem o footer antigo;
`/pandora_admin` (autocomplete do Discord) aparece no lugar de
`/colecao_admin` (o antigo pode continuar registrado no Discord por até
1h até o cache de slash commands da 1ª sincronização expirar - normal,
não é bug); os 7 botões renomeados aparecem certos (Claim All/PvP/
Classes/Diária ✓/Séries/Trocas, e o toggle de Auto-claim mostrando ON/OFF
certo); abrir "📖 Perfil" e conferir que Auto-claim/Ranking/Conquistas
aparecem lá (não mais no hub) e que clicar Auto-claim alterna e ATUALIZA
o próprio Perfil (não mais o hub) sem travar.

### Validar "🔍 Personagem" (posição/bloco/busca) e imagem da 5★ do World Boss ao vivo (2026-09-02)

**Prioridade:** Alta | **Complexidade:** Média

`_ViewNivel` foi reescrita por completo nesta sessão (navegação por
posição global em vez de lista de candidatos acumulada) - implementado e
validado só contra uma cópia do `pandora.db` real (posição 93 -> bloco
76-100, posição 101 -> bloco 101-125, pulo direto pra posição 2750, busca
por nome resolvendo pra posição certa, clamping além do total) - **nenhum
clique real no Discord ainda desta versão** (a versão anterior, mais
simples, já tinha sido parcialmente exercitada ao vivo, mas essa reescrita
troca a estrutura de dados inteira). Testar: abrir "🔍 Personagem" (deve
abrir direto na posição 1/total); "◀️"/"▶️" andando 1 por 1 e o rodapé
"X/Y" acompanhando; "⏮️"/"⏭️" pulando um bloco de 25 inteiro (conferir que
o select "🔄 Trocar de personagem" some as opções do NOVO bloco, não do
antigo); "🔎 Buscar" digitando um NOME (deve abrir direto nela) e depois
uma POSIÇÃO numérica (deve abrir direto na posição, e o select deve
refletir o bloco correspondente); digitar uma posição maior que o total
(deve clampar pro fim com aviso, não travar); confirmar que Upar Nível/
Aumentar Afinidade/Favoritar/Divorciar/Atualizar continuam funcionando
normalmente dentro desse novo fluxo (não devem ter mudado, mas usam
`self.personagem`/`self.montar_embed()` da view reescrita).

### Validar valor de loja + mínimo do bot na Troca ao vivo no Discord (2026-09-02)

**Prioridade:** Média | **Complexidade:** Baixa

Implementado e validado só contra uma cópia do `pandora.db` real (cálculo
de `economia.valor_loja_personagens`/limiar de 10x) - falta confirmar ao
vivo: "🔄 Trocar" -> escolher alvo humano -> OFERECE/PEDE -> conferir que
o texto de valor de loja aparece certo antes do botão "💰 Definir
WiShards"; repetir escolhendo uma conta de BOT (GAIA#9308/ERIS#0983) como
alvo e confirmar que a linha extra do mínimo aparece e o valor bate com
o que `economia.avaliar_proposta_npc` de fato aceita depois de enviar.

### Validar Perfil redesenhado + Séries Favoritas ao vivo no Discord (2026-09-02)

**Prioridade:** Alta | **Complexidade:** Média

Implementado e validado só simulando contra uma CÓPIA do `pandora.db` real
(consultas SQL/`torre.power_personagem`/embeds construídos e conferidos
fora do Discord) - nenhum clique real ainda. `/perfil` (pedido do usuário,
endossando uma sugestão externa: "remover aquelas séries... deixar lá
informações importantes apenas do jogador") virou resumo + tabela por
raridade (1★-5★, cada linha com % de nível máximo/afinidade máxima/
soulmates) + até 10 Séries Favoritas, em vez da lista de TODA série já
tocada (removida - `db.progresso_por_serie` não existe mais). Testar:
abrir "📖 Perfil" com uma conta de coleção real; abrir "❤️ Séries
Favoritas" (botão novo no hub), escolher uma série num slot vazio (deve
ser instantâneo), tentar trocar esse MESMO slot de novo (deve recusar com
a data de liberação, cooldown de 7 dias), escolher uma série NUM slot
DIFERENTE ainda vazio (deve ser instantâneo de novo); comprar 1 slot extra
na Loja ("❤️ Slot de Série Favorita") e confirmar que o 6º slot aparece;
subir uma personagem de uma série favoritada até o nível máximo/Soulmate e
conferir que o bônus de CP (+5%/+5%/+10%) aparece refletido no CP dela em
algum painel (Party/dropdown) sem precisar reabrir o Perfil.

**Escopo intencionalmente fora desta leva** (não implementado, considerar
se o usuário pedir depois): abrir uma Série Favorita pra ver a lista
completa de quem falta coletar (a sugestão original mencionava isso -
"ao abrir uma delas, aí sim mostra todos os personagens e quem está
faltando") - hoje só mostra os números agregados, sem drill-down pra lista
de personagens específicos.

### GAIA precisa reiniciar pro prompt de classificação novo valer (2026-09-02)

**Prioridade:** Média | **Complexidade:** Baixa

O prompt de `classificar_personagem_colecao` (`core/agent/turno.py`, repo
da GAIA) foi ajustado - reforça não traduzir classe existente pra outro
idioma (evita repetir o drift `Assassin`/`Invoker` achado durante esta
própria sessão de correção), nomeia Cavaleiro/Defensor explicitamente no
critério de Tank, e adiciona mais exemplos + um fallback genérico
("Apoiador") pra evitar classes-lixo tipo "Criança"/"Deus"/"Piloto". Só
vale pra personagens classificadas DAQUI PRA FRENTE - a GAIA (`run.py`)
não recarrega código sozinha, e não foi reiniciada ainda nesta sessão
(processo mais sensível que o ERIS - validar com o usuário antes de
reiniciar). Depois do restart, vale acompanhar se Tank realmente fica
menos raro nas próximas levas de reivindicações.

### Validar fix de Upar Nível/Afinidade em massa + saldo no Modal ao vivo (2026-09-01)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado e validado só em cópia da produção - falta confirmar ao vivo:
"⬆️ Upar Nível"/"💕 Aumentar Afinidade" respondendo rápido mesmo com
coleção grande (achado original: "upar level apenas de 1 personagem para
o maximo, gaia nao respondeu a tempo" - causa raiz era o recálculo do
bônus da Cidade, não o Upar Nível em si, então testar também Party/
Divórcio/Merge, que disparam o mesmo recálculo); Modal de "📈 Investir em
Massa" mostrando o saldo disponível (WiShards/Soulstone) no rótulo antes
de pedir o valor.

### Validar Conquistas do Colecionador ao vivo (2026-09-01)

**Prioridade:** Média | **Complexidade:** Baixa

Implementado e validado só em cópia da produção (métricas batendo,
progresso, concessão com pagamento de WiShards, idempotência, contadores
de rolls/merges incrementando certo) - falta confirmar ao vivo: abrir
"🏆 Conquistas" de uma conta com histórico real e conferir que os 17
limiares (primeiro palpite, "balanceável depois") fazem sentido pra
progressão de verdade (podem estar fáceis/difíceis demais - ninguém
testou contra uma conta desenvolvida ainda). `col_series_completas`
merece atenção especial - depende de `serie` estar preenchido igual no
catálogo pra bater certo, nunca testado contra a diversidade real de
séries da produção.

### Validar correções de achados ao vivo (2026-09-01)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado e validado só em cópia da produção - falta confirmar ao vivo:
claim (botão E reação) voltando a responder rápido mesmo com coleção
grande (o achado original foi reportado em produção, então esse é o mais
crítico de confirmar); Batalha 5x5 voltando a virar sink quando o
desafiante vence; Roll/Claim Permanente da Loja e do World Boss aparecendo
separados no "🎒 Inventário"; setas ◀️▶️ do card "🔍 Personagem" avançando
além de 25 (testar com uma conta de coleção grande de verdade, carregando
página por página); Adicionar à wishlist com várias linhas de uma vez;
botão "📊 Estatísticas" da Torre; botão "📈 Investir em Massa" (Nível e
Afinidade) investindo na ordem certa (maior CP primeiro) e batendo o
orçamento informado.

### GAIA precisa reiniciar pra `funcao_cidade` valer em classificações NOVAS (2026-08-30)

**Prioridade:** Alta | **Complexidade:** Baixa

O prompt de `classificar_personagem_colecao` (GAIA) já pede `funcao_
cidade` na mesma chamada de classe/categoria_combate, mas a GAIA não foi
reiniciada ainda nesta sessão - toda personagem reivindicada AGORA (antes
do reinício) fica sem `funcao_cidade`, ficando de fora da produção da
Cidade até uma reclassificação manual futura. As 39 classes já existentes
foram cobertas por backfill manual (`backfill_funcao_cidade_2026-08-30.py`)
- só personagens com classe NOVA (nunca vista) dependem do reinício.
Avisado ao usuário antes de reiniciar, não feito sem confirmação.

### Limpeza de nomenclatura duplicada em `colecao_classes` (achado 2026-08-30)

Ao remigrar `funcao_cidade` pra v2, apareceram 2 pares de classe
duplicada só por idioma - "Assassin"/"Assassino" e "Invoker"/"Invocador"
(claims novos criaram a variante em inglês em algum momento entre a
sessão que criou `colecao_classes` e esta). Não corrigido agora (fora do
escopo desta leva) - fica registrado como candidato a uma limpeza futura
(reatribuir as personagens da variante em inglês pra canônica em
português e apagar a entrada duplicada de `colecao_classes`, mesmo
padrão já usado pra "Summoner"->"Invocador"/"Assassin"->"Assassino" numa
correção anterior - parece que voltou a acontecer).

## Pendências da extração (2026-08-29)

### Reclassificar as 2 últimas personagens com classe "Maid"/"Mediador"

**Prioridade:** Baixa | **Complexidade:** Baixa

As outras 7 de 9 já foram reclassificadas manualmente (ver CHANGELOG.md,
2026-08-30) - restam Ayame Satsuki (Qwaser of Stigmata, "Maid") e Hina
Ebina (Oregairu, "Mediador"), deixadas de propósito por terem bio fina
demais pra decidir sem chutar: Ayame é personagem de apoio/fanservice,
obcecada por outra personagem, sem estilo de combate nem poder próprio
descrito (o Soma dela é SUGADO por outra personagem, não usado por ela);
Hina tem descrição de só 1 frase ("garota quieta que anda com a turma de
Hayama"), sem personalidade suficiente pra traduzir com confiança.
Precisa de mais contexto (bio mais completa/conferir a obra de verdade)
antes de reclassificar essas 2 - não é um find-and-replace, cada uma
precisa de julgamento individual.

### Validar Modo Auto-coleta por usuário ao vivo (:50/:55 de verdade)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado e testado só na camada de dados (toggle liga/desliga, `db.
rolls_disponiveis` respeitando ciclo intocado) - falta esperar um :50/:55
de verdade passar com o toggle ligado (`/waifu` -> Perfil -> "🤖
Auto-coleta") pra confirmar que `AutoColecionadorUsuarios` rola/coleta
igual ao das contas de bot, gastando a cota real da pessoa. Confirmar
também que NADA acontece se a pessoa já tiver rolado manualmente antes de
:50 (pedido explícito de não dar roll "de graça").

### Limpar tabelas `colecao_*` órfãs em `Project-ERIS/data/eris.db`

**Prioridade:** Baixa | **Complexidade:** Baixa

Ver "Migração de dado" em `ARQUITETURA.md` - as tabelas antigas continuam
fisicamente no banco do ERIS (nunca mais lidas/escritas) como rede de
segurança temporária. Apagar depois que este repo rodar em produção por um
tempo sem incidente.

## Roadmap futuro

- **Geração de andares da Torre via IA** - Difficulty Engine determinístico
  + GAIA escolhe blocos de um catálogo FECHADO de mecânicas + Validator,
  já validada em princípio numa sessão anterior ("depende da Torre existir
  primeiro" - agora existe). A Torre de hoje é 100% determinística
  (fórmula geométrica de Power-alvo + rotação fixa de restrições) - a
  geração por IA substituiria isso por andares temáticos únicos, mas fica
  pra uma leva futura separada.
- **Cidade - IMPLEMENTADA (2026-08-30)**, ver "Progressão Global da conta
  + Cidade" em `ARQUITETURA.md` - a "Função da cidade" que este item
  cogitava (Produção/Comércio/Serviço/Cultura/Saúde/Administração/
  Militar) foi exatamente a taxonomia usada, `colecao_classes.
  funcao_cidade`, decidida pela GAIA na mesma classificação de sempre.
  Classes NÃO combatentes (Ferreiro, Mercador, etc.) ainda não existem no
  catálogo de propósito - a Cidade de hoje já dá função útil pras classes
  combatentes existentes (a maioria vira "Militar"), inventar classes
  civis novas sem personagem nenhuma pra usá-las ficaria pra uma leva
  futura separada, se fizer sentido.
