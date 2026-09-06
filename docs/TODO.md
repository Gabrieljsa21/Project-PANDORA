# TODO - Project PANDORA

### Validar ordem da Cidade + velocidade da Party ao filtrar por role ao vivo (2026-09-06)

**Prioridade:** Média | **Complexidade:** Baixa

Implementado (troca de ordem em `_embed_cidade`; `_abrir_adicionar`
reaproveitando 1 `_contexto_lote` só pro filtro/ordenação/descrição, em
vez de 3 buscas separadas, uma delas fazendo N consultas) mas só validado
por leitura de código, sem clique real no Discord nem medição de tempo de
verdade. Precisa confirmar ao vivo: abrir "🏙️ Cidade" e ver "Desde sua
última visita" mostrando WiShards/Soulstone/XP de Progressão nessa ordem;
na Party, "➕ Adicionar" -> escolher uma role (DPS/Tank/Support) numa
conta com MUITAS personagens (idealmente centenas, pra sentir a diferença
de verdade) e comparar a demora percebida com antes da correção - o
resultado final (quem aparece, em qual ordem, com qual descrição) precisa
ser IDÊNTICO ao de antes, só mais rápido.

### Validar dropdowns de personagem padronizados + 3 bugs corrigidos ao vivo (2026-09-06)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado (classe + CP base em `_descricao_personagem_dropdown`/novo
`_descricao_personagem_livre_dropdown`, Trocas corrigido pro formato
padrão, defer() no botão Coleção do Perfil, botão de Slot de Série
Favorita removido da Loja, card completo com imagem nas Waifus) mas só
validado por leitura de código, sem clique real no Discord. Precisa
confirmar ao vivo: abrir Party/Fusão/Trocas/"🔍 Personagem"/Batalha/
Proteção/Prova de Soulmate e ver a classe + CP base aparecendo certos no
dropdown (e sem estourar o limite de 100 caracteres de `SelectOption.
description` em nome de classe muito longo); "Comprar Tudo"/Loja "Comprar"
mostrando classe/CP base sem Nível/Afinidade; clicar "📚 Coleção" dentro do
Perfil e confirmar que responde mesmo com coleção grande; conferir que a
Loja não tem mais o botão "Slot de Série Favorita" e que comprar slot
ainda funciona normal pela tela de Séries; abrir um slot de Waifu ocupado
e ver a imagem/classe da personagem aparecendo no card.

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

### Validar fix de "GAIA nao respondeu a tempo" na Party (Adicionar/Remover/Limpar) ao vivo (2026-09-03)

**Prioridade:** Alta | **Complexidade:** Baixa

Achado em PRODUÇÃO pelo usuário (filtro por role ao adicionar na Party) -
corrigidos os 4 pontos da `ViewEquipe` com o mesmo padrão (`defer()`
faltando antes de trabalho síncrono/caro) - só validado por revisão de
código até agora (a auditoria dos outros 3 pontos foi proativa, não
reportada pelo usuário). PRECISA confirmar ao vivo: "👥 Party" -> "➕
Adicionar" -> escolher uma role (DPS/Tank/Support, não "Todas") e
confirmar que não trava mais; adicionar personagens de verdade; "➖
Remover"; "🗑️ Limpar tudo" - os 3 continuam funcionando normalmente.

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
mensagem clara, não abrir o Modal).

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
sempre).

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
`self.personagem`/`self.montar_embed()` da view reescrita). Também falta
confirmar a imagem da 5★ ganha no World Boss (DM de recompensa com 2
embeds - resumo + card com imagem, só quando alguma 5★ foi de fato
concedida).

### Validar valor de loja + mínimo do bot na Troca ao vivo no Discord (2026-09-02)

**Prioridade:** Média | **Complexidade:** Baixa

Implementado e validado só contra uma cópia do `pandora.db` real (cálculo
de `economia.valor_loja_personagens`/limiar de 10x) - falta confirmar ao
vivo: "🔄 Trocar" -> escolher alvo humano -> OFERECE/PEDE -> conferir que
o texto de valor de loja aparece certo antes do botão "💰 Definir
WiShards"; repetir escolhendo uma conta de BOT (GAIA#9308/ERIS#0983) como
alvo e confirmar que a linha extra do mínimo aparece e o valor bate com
o que `economia.avaliar_proposta_npc` de fato aceita depois de enviar.

### Validar Auto-Defesa da Batalha ao vivo no Discord (2026-09-02)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado e validado só contra uma cópia do `pandora.db` real (toggle,
criação com `canal_id`, `defesa_automatica_para_desafio` produzindo o
counter-pick certo, resolução fim a fim) - falta confirmar ao vivo: ligar
"Auto-Defesa" no hub de Batalha e ser desafiado por outro jogador (deve
resolver IMEDIATAMENTE, sem esperar clique); desafiar sem que o defensor
responda por 10 minutos de verdade (`paineis.SchedulerBatalha`, tick de
30s) e conferir que o resultado é anunciado no MESMO canal onde o desafio
foi criado; desafiar uma conta de bot (GAIA#9308/ERIS#0983) e confirmar
que a defesa automática continua contra-escolhendo certo (não virou
aleatória de novo). O loop do `SchedulerBatalha` em si (rodando de
verdade por 10 minutos reais contra um desafio pendente) nunca foi
observado ao vivo, só simulado chamando as funções direto.

### Validar fix de "GAIA nao respondeu a tempo" na Batalha ao vivo (2026-09-02)

**Prioridade:** Alta | **Complexidade:** Baixa

Achado em PRODUÇÃO pelo usuário (não simulação) - desafiar um bot travava
ao confirmar. Corrigido movendo `response.defer()` pra antes de qualquer
`to_thread` nos 3 fluxos de confirmação de Batalha (Desafiar/Montar
Defesa/Revanche) - só validado por revisão de código até agora, PRECISA
confirmar contra um bot de verdade (o cenário exato que travou):
desafiar ERIS#0983/GAIA#9308 por uma personagem 5⭐ com aposta alta,
confirmar, e checar que resolve sem travar - e também os outros 2 fluxos
(Montar Defesa contra um humano, Revanche).

### Validar Merge (escolha na mesma raridade) ao vivo no Discord (2026-09-02)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado e validado só contra uma cópia do `pandora.db` real (nunca um
clique de verdade) - testar: sacrificar 5 personagens da mesma raridade,
conferir a lista de "livres" dessa raridade aparecendo certo (até 25),
escolher uma e confirmar que vira dona de verdade; testar especificamente
com 5⭐ (bloqueado antes, "não tem pra onde subir" - agora deve funcionar
normal); testar a corrida (escolher uma personagem que outra pessoa
reivindicou no meio-tempo - deve recusar com mensagem clara, não travar).

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

### Validar Batalha por categoria + enfrentar bot + Diária/Rankings ao vivo (2026-09-02)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado e validado só em cópia da produção - falta confirmar ao
vivo: criar um desafio de Batalha 5x5 escolhendo categoria por posição
(os 5 seletores avançando sozinhos), montar defesa do mesmo jeito,
Revanche com a formação nova; desafiar a conta GAIA#9308 ou ERIS#0983
(dona de personagens via auto-colecionador) e confirmar que resolve
IMEDIATAMENTE sem esperar nada; clicar "🎁 Diária" (credita 1x, botão
muda de cor depois de resgatada, WiShards = 150 × nível de Progressão
ATUAL da conta - 2026-09-02, "multiplicada os wishards pelo nivel da
progressao" - conferir que o valor mostrado bate com o nível de verdade,
não um valor cacheado velho, e que o item raro garantido some no
inventário "🎒"); os 3 rankings novos (Coleção/Soulmates/Torre) no
seletor do botão "Ranking" ("📖 Perfil" saiu daqui - virou seu próprio
item acima, redesenhado).

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

### Validar "Bônus por Classe" ao vivo no Discord (2026-09-02)

**Prioridade:** Média | **Complexidade:** Baixa

Implementado e validado só em cópia da produção (soma por categoria,
ordenação por bônus, progresso pro próximo marco, categoria vazia
some) - falta confirmar ao vivo: abrir "⚔️ Bônus por Classe" numa conta
com coleção real e conferir que os números fazem sentido contra o que já
é aplicado de fato no CP (`torre.power_personagem`), e que o layout (1
campo por categoria + lista de classes embaixo) fica legível mesmo com
muitas classes numa categoria só (limite de 1024 caracteres por campo do
Discord, sem paginação ainda).

### Validar "Reivindicar Tudo" ao vivo no Discord (2026-09-02)

**Prioridade:** Média | **Complexidade:** Baixa

Implementado e validado só em cópia da produção (para exatamente quando os
claims acabam, ordem de popularidade, pula quem já tem dono, remove card
pendente, e agora também a otimização de paralelizar `revelar_classe` -
benchmark simulado 5s → 1,5s pra 5 personagens nunca-classificadas) -
falta confirmar ao vivo: clicar "🎯 Reivindicar Tudo" no hub com
pendentes de verdade no servidor (rolados por outras pessoas também,
idealmente algumas NUNCA reivindicadas antes em nenhum servidor, pra
sentir a velocidade real da classificação em paralelo), conferir que o
resumo fica legível mesmo reivindicando várias de uma vez, e que perder a
corrida pra outro clique no meio do processo (2 pessoas reivindicando ao
mesmo tempo) não gasta claim de quem perdeu.

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

### Validar World Boss (evento + recompensas/conquistas) ao vivo no Discord (2026-09-01)

**Prioridade:** Alta | **Complexidade:** Alta

Implementado e validado só em simulação isolada/cópia da produção (motor
de combate, ciclo de vida completo, os 7 itens, as 20 conquistas, granting
de 5★ via mock de `discord.Member`) - **nenhum clique real no Discord
ainda, nenhum evento real esperou o horário fixo de verdade**. Testar:
esperar um horário fixo (10h/14h/18h/22h Brasília) de verdade, entrar
manualmente pela mensagem/hub, alternar categoria (toggle liga/desliga),
ativar Entrada Automática e conferir que só entra DEPOIS das inscrições
fecharem, os 2 bots entrando de verdade com CP = média dos humanos, o
combate rodando 1 turno/minuto de verdade (não só em loop apertado do
teste) com o log aparecendo no canal certo, e a vitória entregando DM de
recompensa + resumo público + notificação de conquista nova.

**RESOLVIDO (2026-09-02)** - achado em produção de verdade (print real de
um evento contra o Devorador do Abismo, time de 3 jogadores, CP
26.297/categoria): o time morria SEMPRE no turno 1 - HP_BASE (6000) já
nascia menor que o ATK de QUALQUER Boss do catálogo (12-17 mil). Duas
causas, as duas corrigidas em `worldboss.py`:
1. **Bug de ordem contra a própria Seção 18** - o cheque de derrota rodava
   logo depois do ataque do Boss, ANTES da cura (passo 6) ser aplicada -
   Support nunca conseguia evitar uma morte. Corrigido pra dano líquido
   por turno (`dano recebido = dano causado pelo Boss - dano curado`,
   pedido do usuário), com o cheque de derrota só depois da cura.
2. **`DANO_BASE`/`HP_BASE`/`CURA_BASE` descalibrados** - recalibrados
   (10.000→14.000 / 6.000→45.000 / 500→7.500) e validados simulando o
   motor real (`executar_turno`) 60x por Boss com o CP observado: 87% de
   vitória agregada nos 10 Bosses (8 deles em 70-100%, Senhor da Morte/
   Ceifar em 70% como degrau intermediário, Dragão Ancião/Enfurecer em 0% -
   não é bug, ATK composto +10%/turno cresce mais rápido do que este time
   consegue acompanhar, mecânica sendo o diferencial real de dificuldade,
   como pedido). Também foi adicionada variação leve (±10%, `VARIACAO_
   TURNO`) no dano causado e recebido a cada turno, pra o combate não ser
   100% determinístico. HP/ATK de cada Boss no catálogo NÃO mudou -
   mecânica continua sendo o que diferencia a dificuldade entre eles, não
   o número bruto.

Continua pendente (não coberto pelo fix acima): validar ao vivo com
Discord de verdade (o fix foi validado só via simulação do motor,
`executar_turno` chamado direto, nunca um evento real rodando no
scheduler) - conferir se o "88% de vitória" simulado se sustenta com
composições reais de jogadores (nem todo mundo concentra CP numa
categoria só como no teste) e se o ritmo de ~15-25 turnos (15-25 minutos
reais, 1 turno/minuto) fica bom de acompanhar no canal.

**5 dificuldades independentes + CP recomendado (2026-09-02, pedido do
usuário depois do fix acima, corrigido 2x - ver ARQUITETURA.md pro
histórico completo do erro)** - `worldboss.cp_recomendado` agora busca por
simulação real contra o motor (`_taxa_vitoria_simulada`, ~0,1-0,6s por
chamada) em vez de multiplicar sobre o CP do personagem mais forte do
servidor (1ª versão, corrigida - virava meta inatingível pra servidor
pequeno). Validado só spawnando eventos numa CÓPIA do `pandora.db` real e
conferindo os embeds - nunca um clique real no Discord. Vale reconferir o
tempo de `cp_recomendado` (busca binária, ~20 simulações curtas) com uma
carga real de scheduler rodando pra vários servidores ao mesmo tempo,
antes de confiar cegamente nisso não atrasar outros ticks do scheduler de
30s.

Também falta: usar item Proteção/Revanche/Chave da Torre/Upgrade de
Construção/Chamado através da UI de verdade (só as funções de regra de
negócio foram testadas, os botões do painel "🎒 Inventário" nunca foram
clicados de verdade), e comprar os 5 itens compráveis (`itens.ITENS_LOJA`
- Roll/Claim Permanente saíram da Loja em 2026-09-03, ver CHANGELOG.md)
pela Loja através da UI.

### Validar Batalha 5x5 com Aposta de Personagem ao vivo no Discord (2026-09-01)

**Prioridade:** Alta | **Complexidade:** Média

Implementada e validada só numa CÓPIA da produção via script direto
(Jokenpô, transferência+sink na vitória do desafiante, WiShards+
manutenção na vitória do defensor, proteção de Soulmate, cooldown de 24h,
bloqueio de "1 batalha por vez", Morte Súbita completa - ver
`ARQUITETURA.md`) - **nenhum clique real no Discord ainda**. Testar com 2
contas de verdade: `/waifu` -> ⚔️ Batalha -> Desafiar (UserSelect + busca
por nome na coleção ALHEIA, `_ViewEscolherAlvoBatalha`), confirmar que a
composição mostrada ao defensor bate com a Party real do desafiante
(só contagem, nunca quem/CP/ordem), Montar Defesa revelando as rodadas
com pausa visível editando a MESMA mensagem, Recusar reembolsando de
verdade, Morte Súbita funcionando com os 2 jogadores cada um no PRÓPRIO
painel, cooldown/limite diário bloqueando na hora certa, e o caso do
defensor perder a personagem (troca/divórcio) ENQUANTO o desafio está
pendente (deveria cancelar+reembolsar ao tentar montar defesa). Também
falta validar que o preço de mercado (`raridade × valor_base_wishards`) dá
uma aposta que parece razoável contra o economy real de uma conta
desenvolvida - primeiro palpite, "balanceável depois" mesmo padrão de
toda fórmula nova do PANDORA.

### Validar reações de roll novas (favoritar/tag trade) e reclassificação de classe ao vivo (2026-09-01)

**Prioridade:** Média | **Complexidade:** Baixa

Migração de `colecao_cards_pendentes` (nova PK `(message_id, emoji)`) já
rodou em produção sem erro (`db.inicializar()`) - falta confirmar ao vivo
que um roll novo mostra as 3 reações (claim colorido/⭐/🔄) no card, que
reagir com ⭐ reivindica E favorita, que 🔄 reivindica E aparece depois em
"📚 Coleção" -> "🏷️ Marcadas pra troca", e que a reação de reencontro
("já é sua") mostra o formato novo (compacto, marcando o dono) em vez do
formato antigo. A reclassificação de `funcao_cidade` (Alquimista/
Engenheiro/Elementalista) já rodou em produção - só falta conferir que o
painel "🏙️ Cidade" reflete a mudança pras contas que têm essas 3 classes.

### Validar que "GAIA não respondeu a tempo" parou de verdade (2026-08-30)

**Prioridade:** Alta | **Complexidade:** Baixa

Causa raiz corrigida (`asyncio.to_thread` em todo scan de coleção
inteira - ver `ARQUITETURA.md`, seção Auto-Party) e validada só em
cópia/script (resultado idêntico direto vs. via thread + prova de que o
event loop fica livre durante a chamada) - nenhuma validação ao vivo sob
uso concorrente de verdade ainda. Testar: Auto-Party, "🏙️ Cidade" e
"🔍 Personagem" repetidas vezes, IDEALMENTE com outra pessoa usando o bot
ao mesmo tempo (é exatamente esse cenário - 2 interações concorrentes -
que expunha o bug), confirmar que nenhum dos 3 cai mais em "GAIA não
respondeu a tempo". Se cair de novo, o próximo suspeito é algum OUTRO
scan de coleção inteira que ainda não foi convertido pra `to_thread`
(checar `torre.ordenar_por_power`/`power_personagem` por chamadas soltas
fora das já corrigidas).

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

### Validar Progressão Global + Cidade ao vivo no Discord (2026-08-30)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado e validado só na camada de dados/matemática numa CÓPIA do
banco de produção (curva de XP, cascata de nível, `bonus_cp_global`
batendo com os exemplos da análise, `power_personagem` com bônus,
marcos de coleção, Divórcio/Merge/Torre creditando XP, produção da
Cidade com teto de 168h) - nenhum clique real no Discord ainda. Testar:
campo "📈 Progressão" aparece certo no hub, comprar "🏋️ Treinamento
Global"/"📊 Potencial da Coleção" na Loja, abrir "🏙️ Cidade" (1ª visita
não credita nada, visita seguinte credita proporcional ao tempo), CP
mostrado em qualquer tela (Party/Torre/card) já reflete o bônus global.

**Já validado ao vivo pelo usuário no mesmo dia** (achados corrigidos):
"🎲 Rolar" do hub volta a rolar o ciclo inteiro, preço de "Garantir" bate
com metade de "Comprar", CP aparece em "📚 Minha coleção" e no card
"🔍 Personagem", Favoritar mudou pro card "🔍 Personagem" - só falta
confirmar que essas 4 correções específicas também se comportam certo
depois do próximo reinício do ERIS.

### ~~Taxas diferenciadas por Função da Cidade~~ RESOLVIDO (2026-08-30)

Virou Cidade v2 - cada área tem efeito próprio (Militar/Arcano/
Administração são bônus de CP ao vivo pra Party; Saúde/Cultura/Comércio
geram Soulstone/XP/WiShards, cada um só o seu) - ver "Cidade v2" no
`ARQUITETURA.md`. Taxas ainda são primeiro palpite (exceto `TAXA_BONUS_
COLECAO`, literal do usuário) - já recalibradas 1x depois de testar
contra uma conta real, mas continuam candidatas a ajuste fino depois de
validar ao vivo por mais tempo.

### Validar Cidade v2 + Soulstone/Afinidade + dropdown de nível ao vivo no Discord (2026-08-30)

**Prioridade:** Alta | **Complexidade:** Baixa

Implementado e validado só na camada de dados/matemática numa CÓPIA da
produção (3 ramos do reencontro, `subir_afinidade_ate` nunca seta
Soulmate, remigração das 40 classes sem nenhuma fora da taxonomia v2,
`calcular_power_party` batendo com a fórmula esperada, dropdown de
nível/afinidade com custo total certo e rejeitando alvo inválido, select
"Trocar de personagem" listando os candidatos certos e atualizando o
card sem reconstruir a View) - nenhum clique real no Discord ainda.
Testar: botão "💕 Aumentar Afinidade" e "⬆️ Upar Nível" abrindo o
dropdown certo no card "🔍 Personagem" (opções/custos batendo, confirmar
debitando certo, Cancelar voltando pro card, placeholder mostrando o
saldo de WiShards/Soulstone certo), select "🔄 Trocar de personagem" no
mesmo card trocando pra outra personagem da busca SEM sumir (dropdown
continua ali depois de escolher, dá pra trocar de novo em seguida),
"🏋️ Treinamento Global"/"📊 Potencial da Coleção" na Loja abrindo
o mesmo tipo de dropdown (25 opções à frente, sem nível máximo, saldo de
WiShards certo no placeholder, pular vários níveis de uma vez debitando
o total certo), opções do select "🔍 Personagem"/"🔄 Trocar de
personagem"/Merge/Party Adicionar-Remover mostrando ícone+CP+Nível+
Afinidade certos (`_descricao_personagem_dropdown`, 1 função só pras 4),
setas "◀️"/"▶️" no card "🔍 Personagem" trocando de personagem sem abrir
o select e desabilitando certo nas pontas da lista, reencontro numa
personagem em Afinidade 10 virando Soulmate de verdade, reencontro numa
já-Soulmate creditando Soulstone, painel "🏙️ Cidade" mostrando o efeito
certo de cada área, CP da Party já refletindo Bônus da Coleção/Militar/
Arcano, bônus de CP por classe aparecendo na Torre/Party.

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

### Validar ao vivo no Discord depois do cutover

**Prioridade:** Alta | **Complexidade:** Baixa

O cutover (ERIS apontando pro pacote novo, banco de produção migrado,
processo reiniciado) foi validado via script direto contra o banco e via
atividade automática do auto-colecionador (rolou/gravou no `pandora.db`
novo com sucesso) - mas nenhum fluxo que depende de CLICAR um botão no
Discord foi testado manualmente ainda depois do cutover (roll/claim via
`/waifu`, trocas, Party, Prova de Soulmate). Testar isso é o próximo passo
antes de considerar a extração 100% encerrada.

### ~~Limpar personagens com classe "Maid"/"Mediador"~~ QUASE RESOLVIDO (2026-08-30)

7 das 9 reclassificadas manualmente (bio de cada uma lida direto do
banco, `colecao_personagens.descricao` - mesmo texto que a GAIA veria):
Mei Tachibana -> Eremita (guardada/desconfiada, mas honesta - classe
NOVA, só ela usa até agora), Setsuna Kiyoura -> Curandeira (protege a
felicidade da amiga, acalma com empatia), Erasa -> Barda (carismática,
anima o grupo), Rio Nanase -> Sábia (severa, supervisiona os estudos dos
outros), Madoka Yachi -> Sábia (dura por fora, guia a filha a crescer),
Aisha Hart -> Curandeira ("muito gentil e misericordiosa"), Fiona Thyme
-> Guardiã/Tank (Huntress leal, protege seu povo em vez de buscar
glória).

**2 ficaram de propósito, bio fina demais pra decidir sem chutar**:
Ayame Satsuki (Qwaser of Stigmata, "Maid") - personagem de apoio/
fanservice, obcecada por outra personagem, sem estilo de combate nem
poder próprio descrito (o Soma dela é SUGADO por outra personagem, não
usado por ela); Hina Ebina (Oregairu, "Mediador") - descrição de só 1
frase ("garota quieta que anda com a turma de Hayama"), sem
personalidade suficiente pra traduzir com confiança. Precisa de mais
contexto (bio mais completa/conferir a obra de verdade) antes de
reclassificar essas 2 - não é um find-and-replace, cada uma precisa de
julgamento individual.

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

### Validar Torre ao vivo no Discord

**Prioridade:** Alta | **Complexidade:** Baixa

Implementada e validada só na camada de dados/matemática (Power bate com
a tabela do documento original, andar/restrição seguem a fórmula, vitória
credita recompensa e avança andar - ver `ARQUITETURA.md`) - nenhum clique
real no Discord ainda (as Views novas/alteradas passaram só pela varredura
de sanidade de construção, não por um clique de verdade). Testar: upar
nível e divorciar pelo card "🔍 Personagem" (`/waifu` -> "🔍 Personagem" -
o Perfil não existe mais, tudo isso e Favoritar/Merge/Prova de Soulmate/
Auto-coleta vieram pro hub principal, 3 linhas de botão agora), montar uma
Party usando o filtro de role novo ao Adicionar, tentar o andar 1 na Torre
(`/waifu` -> "🗼 Torre"), confirmar que perder não trava nada (retry sem
cooldown), que os andares seguintes ficam mais difíceis de verdade e que
o ícone de categoria + CP/Nível aparecem certos no embed da Torre, no
texto "Sua Party" e nos SELECTs de Adicionar/Remover.

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
