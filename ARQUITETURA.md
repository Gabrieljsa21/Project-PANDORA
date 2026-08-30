# Arquitetura do Project PANDORA

## Extraído do Project-ERIS (2026-08-29)

O Colecionador (gacha estilo Mudae) nasceu dentro do [Project-ERIS](../Project-ERIS)
(bot de Discord) e cresceu MUITO ao longo de uma sessão de desenvolvimento
intensa - `/waifu` (painel com 8 botões), economia completa (WiShards/loja/
Merge/trocas), Party/Vitrine, e a Prova de Soulmate (situação + 3 opções de
resposta geradas por LLM, chance/pity por raridade). Na hora da extração:
`eris/colecao/*` tinha ~2.780 linhas (`gacha.py` 961, `paineis.py` 1045,
`economia.py` 249, `consulta.py` 173, `auto_colecionador.py` 169,
`sincronizador.py` 64) e `eris/db.py` tinha 1.773 linhas, das quais 14 de 19
tabelas eram `colecao_*` - o Colecionador já era a MAIORIA do peso do ERIS.

Usuário perguntou se valia separar num projeto próprio, possivelmente numa
linguagem diferente. Decisão tomada depois de pesar 3 caminhos:

1. **Satélite HTTP** (padrão já usado por MOIRAI/ECHO/HESTIA/IRIS - processo
   próprio + ponte HTTP, sem UI própria) - REJEITADO. Esse padrão pressupõe
   consulta esporádica (ECHO: 1x/semana; MOIRAI: 1x/dia); o Colecionador é
   consultado em TODO clique de roll/claim/troca, dentro do orçamento de 3s
   de resposta do Discord - orçamento que já causou 2 bugs reais de timeout
   nesta mesma sessão (roll-cooldown drenado por uma chamada síncrona lenta;
   `/colecao_disponiveis` sem responder). Um satélite HTTP colocaria uma
   chamada de REDE em cima de CADA clique - risco concreto de regredir
   exatamente essa categoria de bug, não hipotético.
2. **Não separar** - REJEITADO pelo usuário ("Oq sugere? Deixar a eris
   gigante?") depois de eu apontar o risco do satélite HTTP.
3. **Biblioteca Python local, sem HTTP** - ESCOLHIDO. Foge do padrão dos
   outros satélites de propósito - ganha separação de repositório/histórico
   de commits sem introduzir latência de rede em nenhum clique. Instalada
   via dependência de PATH do `uv` (`[tool.uv.sources]` no `pyproject.toml`
   do ERIS, `editable = true`) - importada DIRETO (`from pandora import
   gacha, paineis, ...`), zero round-trip de rede.

## Estrutura movida (sem refatorar UI/lógica nesta leva)

`eris/colecao/*` NÃO separava UI de lógica pura antes da extração -
`consulta.py` (paginação `ViewColecao`) e `economia.py` (`ViewTroca`, botão
de aceitar/recusar troca) misturam `discord.ui.View` com regra de negócio
no MESMO arquivo; `gacha.py`/`paineis.py`/`auto_colecionador.py` também
importam `discord` direto. Só `importar_get_waifu.py` é puro. A extração
moveu os arquivos COMO ESTAVAM (Views inclusas) - separar UI de lógica de
verdade fica pra uma fatia futura, se algum dia fizer sentido (ex.: reusar
o motor do Colecionador num bot Discord diferente sem reusar as Views).

- `pandora/db.py` - as 14 tabelas `colecao_*` + funções relacionadas,
  schema/migração idênticos ao que existia em `eris/db.py`. Banco PRÓPRIO
  (`data/pandora.db`) - não compartilha arquivo com `eris.db` (que ficou só
  com o núcleo do bot: `donos`/`config_roteamento`/`guilds_desativados`/
  `guilds_cache`/`auditoria_moderacao`).
- `pandora/gaia_webhook.py` - só as 2 funções do Colecionador extraídas de
  `eris/integrations/gaia_webhook.py` (`pedir_classe_personagem`,
  `pedir_prova_soulmate`) - as outras (`pedir_resposta_persona`, voz/
  música/lista de desejo) ficaram no ERIS, que continua sendo quem tem a
  conexão Discord de verdade e fala com a GAIA pra tudo mais.
- `pandora/gacha.py`/`paineis.py`/`consulta.py`/`economia.py`/
  `auto_colecionador.py`/`sincronizador.py`/`importar_get_waifu.py` -
  movidos de `eris/colecao/*`, só com os imports `eris.*` trocados por
  `pandora.*` (`from eris import db` -> `from pandora import db`, etc.) -
  NENHUMA lógica mudou na extração em si.

## Como o ERIS consome este pacote

`Project-ERIS/pyproject.toml`:
```toml
dependencies = [..., "pandora"]

[tool.uv.sources]
pandora = { path = "../Project-PANDORA", editable = true }
```

`eris/bot.py` importa `from pandora import auto_colecionador, consulta,
economia, gacha, paineis, sincronizador` e `from pandora import db as
colecao_db` (ALIAS de propósito - `eris.db` continua existindo pro núcleo
do bot, então `_registrar_slash_colecao` usa `colecao_db.*` pra tudo do
Colecionador, nunca confundindo os dois bancos SQLite distintos).

## Migração de dado (2026-08-29, rodada 1x em produção)

`migrar_de_eris.py` (raiz deste repo) copiou as 14 tabelas de
`Project-ERIS/data/eris.db` pra `data/pandora.db` (`INSERT OR IGNORE`,
idempotente) - validado numa cópia antes de rodar contra produção de
verdade (30.965 personagens, 43 propriedades, 47 lançamentos de WiShards,
169 cards pendentes, etc. - todos os números batendo entre origem/destino).
As tabelas antigas continuam existindo em `eris.db` (não apagadas de
propósito - rede de segurança; `eris/db.py` só parou de CRIAR/migrar o
schema delas, o arquivo físico ainda as tem) - útil enquanto a extração é
recente, pode ser limpo depois que o PANDORA rodar em produção por um
tempo sem incidente.

## Tabela de classes - fonte única da categoria de combate (2026-08-30)

Pedido direto do usuário ("n estamos criando uma tabela de classes?"),
disparado por uma pergunta de escopo adjacente (Merge não classificar
personagens novas). Investigando, achei um problema JÁ manifestado nos
dados reais: `categoria_combate` era decidido pela GAIA de novo A CADA
personagem, mesmo quando a classe era REAPROVEITADA - nada garantia que
"Guerreiro" continuasse sempre a mesma categoria. Medido em produção antes
do fix: `Guerreiro` (19 DPS / 2 Tank), `Berserker` (3 DPS / 1 Tank),
`Encantador` (3 Support / 1 DPS), `Mago` (3 Support / 3 DPS - empate real).

Tabela nova `colecao_classes` (`classe` PRIMARY KEY, `categoria_combate`) -
`db.definir_classe_personagem` agora SEMPRE confere essa tabela primeiro:
classe já conhecida usa a categoria JÁ REGISTRADA (a sugestão nova da GAIA
pra esse personagem específico é descartada); só uma classe nunca vista
grava uma entrada nova, virando a canônica pra sempre a partir daí.
`classes_existentes()` passou a ler dessa tabela em vez de fazer `DISTINCT
classe` em `colecao_personagens` (mesma lista de nomes, mas agora a fonte
de verdade de verdade).

Migração 1x em `inicializar()` fez o backfill: pra cada classe já em uso,
a categoria canônica é a MAIORIA entre os personagens que já a têm
(empate cai pro default mais seguro do resto do sistema, "DPS" - mesmo
critério de `classificar_personagem_colecao`, GAIA), e TODA personagem
daquela classe foi normalizada pra bater com a canônica (os outliers
minoritários, tipo os 2 "Guerreiro"/Tank, viraram DPS).

**Normalização de verdade, não só a tabela nova (mesmo dia, achado do
usuário: "vc so criou a tabela ou ta salvando id delas e pondo nos
personagens?")** - a 1ª versão desta mudança criou `colecao_classes`, mas
`colecao_personagens.categoria_combate` continuava existindo como uma
CÓPIA (sincronizada só no momento da escrita) - qualquer código futuro
que escrevesse ali direto reabriria a mesma divergência que motivou criar
a tabela. Corrigido de vez: coluna `categoria_combate` REMOVIDA de
`colecao_personagens` (`ALTER TABLE ... DROP COLUMN`, mesma técnica já
usada pra `prova_soulmate_intro`) - `colecao_classes` é agora a ÚNICA
dona desse dado. `gacha.revelar_classe` busca a categoria via `db.
categoria_combate_da_classe(classe)` sempre que a classe já é conhecida
(cache hit), em vez de confiar num valor guardado na própria personagem.
`classe` (TEXT) funciona como a chave que liga a personagem à sua entrada
em `colecao_classes` - natural key, não um `classe_id` numérico
separado; como o nome da classe já é único por natureza (é a própria
`PRIMARY KEY` de `colecao_classes`), um ID substituto não adicionaria
garantia nenhuma a mais.

🔥 **Achado resolvido no mesmo dia**: a migração revelou classes inválidas
("Maid"/"Mediador" - mesma categoria de erro do prompt da GAIA, só que de
ANTES da correção existir). O usuário trouxe uma análise própria feita com
o GPT revisando TODAS as 97 personagens classificadas até então, não só
essas - achado mais amplo: a GAIA classificava por personalidade/função
narrativa em vez de estilo de combate/poder real (ex.: "Rem" virou
Curandeira ignorando a transformação Oni de combate dela; "Akame" virou
Guerreira genérica quando ela É uma Assassina). 40 personagens
reclassificadas manualmente (`reclassificar_2026-08-30.py`, ver
`CHANGELOG.md`), 14 classes novas registradas com categoria canônica já na
criação. 2 casos verificados por bio ANTES de decidir não trocar (Shiro é
de *Deadman Wonderland*, não *No Game No Life* - a alternativa que
motivaria a troca; Mii é de *Interspecies Reviewers*, não BOFURI) - nunca
confiar num nome igual sem checar qual personagem de verdade é.

**Hierarquia de decisão explícita no prompt da GAIA** (`core.agent.turno.
classificar_personagem_colecao`, `Project G.A.I.A/assistant`) - 3 níveis
testados EM ORDEM, só desce pro próximo se o anterior não resolveu: (1)
estilo de combate/poder real da personagem; (2) se não houver, habilidade
sobrenatural central à identidade dela; (3) só se nenhum dos dois se
aplicar, traduzir personalidade/competência pra um arquétipo de RPG. Antes
disso o prompt só pedia "priorize o papel de combate explícito" numa frase
solta, sem essa ordem clara - a raiz de várias das 40 classificações
erradas encontradas.

## Modo Auto-coleta por usuário (2026-08-30)

Pedido do usuário depois de ver o `AutoColecionador` das contas de bot em
ação: "faz a msm coisa q os bots de rodar auto os 50 e so 5min depois
coletar o mais popular. Vai fazer os rolls aos 50min e coletar ao 55min".
Diferença crucial de propósito, esclarecida numa pergunta direta: a conta
de bot usa `rolar_sem_cooldown` (cota FIXA, sem gastar nada real); pra um
usuário de verdade isso seria um exploit de economia - `AutoColecionador
Usuarios` (`auto_colecionador.py`) usa os MESMOS `gacha.rolar_varios`/
`gacha._processar_claim` que um comando normal usaria, gastando a cota
REAL da pessoa. Só ativa o roll automático se `db.rolls_disponiveis(...)
== limite` (ciclo intocado) - pedido explícito: "isso so sera feito se n
tiver usado os rolls ainda", pra nunca dar um roll "de graça" em cima do
que a pessoa já fez sozinha nem confundir o resultado de quem já estava
jogando manualmente.

Horário FIXO próprio (:50 roll, :55 claim - distinto de `AutoColecionador`,
que usa :05/:10 pra GAIA e :30/:35 pra ERIS-musica), roda só na instância
"completo" (`eris/bot.py::on_ready`, onde vive o toggle - `paineis.
ViewPerfilAcoes`, botão "🤖 Auto-coleta"). `_canal_dos_rolls` foi extraída
de dentro de `AutoColecionador` pra função de módulo, compartilhada pelas
duas classes (mesmo espírito "nunca duas cópias da mesma regra" já
aplicado ao loop de lotes).

Tabela nova `colecao_auto_colecionar_usuarios` (guild_id, user_id, ativo);
`db.rolls_disponiveis` (leitura pura, espelha `claims_disponiveis` que já
existia só pra claims).

## Canal de anúncio sempre vence, nunca o de onde o comando foi digitado (2026-08-30)

Pedido do usuário depois de reportar `/caos`/comandos do Colecionador
"sempre respondendo no canal definido" - na 1ª leitura pareceu bug (canal
de anúncio pinado desde a criação da sessão de música/desde sempre no
roll), mas uma pergunta direta revelou o oposto: é o comportamento
DESEJADO, só que faltava aplicar ao Colecionador também - "quero q tudo
relacionado a musica so seja respondido no canal de musica definido,
independente se mandar o comando em outro canal... o msm p os
colecionar". `gacha.enviar_resultados` passou a resolver `canal_anuncio_
id` (config do servidor) ANTES de decidir onde postar cards/botões de um
roll - se for diferente do canal de onde o comando saiu, a interação em
si vira só um ack ephemeral (apagado em seguida), e o conteúdo de
verdade vai como mensagem comum no canal configurado (não dá pra fazer
uma resposta de interação aparecer num canal diferente de onde ela
nasceu - limitação da própria API do Discord, contornada assim). O fix
espelho do lado da música (`_canal_anuncio_musica`/`_responder_no_canal_
de_musica`, `/musica canal`) fica documentado no ERIS (`ARQUITETURA.md`
dele) - não é código deste repo.

Telas privadas/ephemeral do Colecionador (seleção de personagem, perfil,
wishlist, trocas, Prova de Soulmate) ficam DE FORA de propósito -
mensagens ephemeral são inerentemente escopadas ao canal/interação onde
nasceram, a própria API do Discord não permite redirecioná-las.

## Torre (2026-08-30) - `ERIS_power_afinidade_soulmate_niveis.md`

Pedido do usuário: "cria a torre". A Fórmula de Power/Afinidade/Soulmate
já estava fechada nesse documento, mas o mecanismo de combate em si
(Seção 11: "impacto exato das classes no combate da Torre") nunca tinha
sido decidido - nem COMO um andar é resolvido, nem como os andares são
estruturados. Perguntei diretamente e o usuário escolheu: (1) resolução
DETERMINÍSTICA por threshold (soma de Power da Party vs. alvo do andar,
sem RNG - não existe nenhuma mecânica de combate simulado hoje pra
reaproveitar, e a fórmula de Power já fechada é suficiente pra decidir
quem vence); (2) fórmula INFINITA de andares desde já (sem lista fixa).

**Nível de Personagem, implementado pela 1ª vez** - o documento original
dizia que só faria sentido quando a Torre existisse ("Toda personagem
obtida começa em Nível 1... aumentado via investimento de WiShards...
+50 Power fixo por nível, nunca percentual - personagens já populares
não podiam receber aumentos absolutos muito maiores"). Mora em `colecao_
afinidade.nivel` (mesmo escopo de Afinidade/Soulmate - propriedade do
VÍNCULO jogador+personagem, não do catálogo). Custo em WiShards (Seção 11
do documento, nunca definido): `25 × raridade × nível-alvo` - um 5⭐
totalmente upado custa 6.750 WiShards no total.

**`pandora/torre.py`** - motor PURO (zero discord.py), reaproveitado por
`preview_andar` (mostra o resultado ANTES de arriscar - como não tem RNG,
o jogador pode SABER com certeza se vai vencer antes de clicar; a Torre é
sobre planejamento, não sorte) e `tentar_andar` (mesmo cálculo + credita/
avança se venceu) via `_calcular_contexto` compartilhada (evita a MESMA
duplicação de lógica já corrigida hoje em outro lugar da sessão).

- `power_base(popularidade)` - compressão logarítmica (Seção 1), validada
  BYTE A BYTE contra a tabela de exemplo do documento original: a
  popularidade máxima real do catálogo (11.266) bate exatamente com o
  "com 11.266 curtidas como máximo atual" do texto; `power_final` com
  Base 300/Nv.10/Soulmate dá exatamente 1.500, Base 1.000/Nv.10/Soulmate
  dá exatamente 2.900 (os 2 extremos que o documento tabula).
- `power_alvo_andar(andar) = round(1000 × 1,06^(andar-1), -1)` - número
  novo (não estava no documento original), decidido nesta leva: andar 1
  pede ~1.000 (alcançável até solo por 1-2 personagens recém-obtidas),
  andar 50 pede ~17.000 (perto do teto de uma Party de 5 totalmente
  desenvolvida, ≈15.950 com o bônus de composição), continua crescendo
  depois disso pra quem quiser seguir subindo.
- `restricao_andar(andar)` - rotação FIXA de 6 padrões (índice `(andar-1)
  % 6`, andar 1 sempre sem restrição) - usa Categoria de combate como
  "vocabulário de restrição" (decisão já fechada numa sessão anterior)
  SEM precisar de geração por IA ainda. `checar_restricao` valida contra
  a Party (min_tank/min_support/max_1_tank/todas_categorias/so_dps).
- `calcular_power_party` - soma `power_final` de cada membro + bônus de
  composição (+10% se DPS+Tank+Support presentes, ÚNICO bônus de
  categoria, decisão já fechada - nunca um multiplicador individual).
- `recompensa_andar(andar) = 50 × andar` - cresce com o andar, incentivo
  pra continuar subindo.
- **Sem cooldown de retry** (diferente da Prova de Soulmate, que tem RNG
  de propósito) - como a resolução é determinística, perder um andar só
  significa "a Party ainda não é forte o suficiente"; tentar de novo é
  sempre permitido.

**UI**: botão "🗼 Torre" no hub `/waifu` (mostra o preview: andar atual,
Power da Party vs. alvo, restrição, breakdown por personagem + botão
único "Subir" que ataca o andar e edita a MESMA mensagem com o resultado
- mesmo padrão de mensagem única já usado na Prova de Soulmate/Party) e
botão "⬆️ Nível" no Perfil (reaproveita o mesmo select genérico de
Favoritar/Divorciar/Merge/Prova de Soulmate).

🔥 **Achado ao validar (sanidade extra depois da Torre)**: uma varredura
instanciando toda `View` de `paineis.py` com argumentos plausíveis (sem
precisar de um clique real no Discord) achou que `ViewPerfilAcoes`
estava QUEBRADA desde a implementação do Modo Auto-coleta mais cedo
nesta sessão - o botão "🤖 Auto-coleta" referenciava `self._toggle_
auto_coleta` como callback, mas o método nunca tinha sido escrito. Como
essa referência é avaliada na hora de CONSTRUIR a View (não só no
clique), todo `/waifu` -> Perfil quebrava - corrigido junto.

**Fora desta leva**: geração de andares via IA (Difficulty Engine +
GAIA escolhe blocos de um catálogo fechado + Validator - já validada em
princípio numa sessão anterior, mas "depende da Torre existir primeiro";
agora existe, mas a geração via IA fica pra uma leva futura separada).

**Ícone de categoria + CP na Party/Torre (mesmo dia, pedido do usuário:
"coloca a role antes do nome com base no icone e em Ex: 🛡️ - Asuna" +
"é importante informar o CP tbm")** - `torre.icone_categoria(categoria)`
(vocabulário fechado `{"DPS": "⚔️", "Tank": "🛡️", "Support": "✨"}`, mesmo
das restrições) e `torre.power_personagem(personagem, guild_id, user_id)`
(CP avulso de UMA personagem - `_calcular_contexto` da Party inteira
passou a reaproveitar essa mesma função por membro, em vez de recalcular
Power inline). Aplicado em 3 lugares: (1) embed da Torre (`ícone - Nome -
Nv.X · vínculo · CP N`, o texto cru de categoria que existia antes foi
removido - o ícone já basta); (2) texto "Sua Party" (`consulta.
formatar_equipe` ganhou `formatador_linha` opcional, mesmo padrão já usado
em `ViewColecao`/`linha_populares` - default continua igual, só a Party
passa uma versão com ícone+CP); (3) descrição dos itens dos SELECTs de
Adicionar/Remover da Party (`_ViewSelecionarPersonagem` ganhou `descricao`
opcional que devolve `(texto, emoji)` - o `emoji` usa o slot NATIVO do
`discord.SelectOption`, não texto concatenado no label; default continua
sem ícone pra quem mais usa esse select, Favoritar/Divorciar/Merge/Nível).

**Perfil eliminado, absorvido no hub + Divorciar mudou pro card
"🔍 Personagem" (mesmo dia, pedido do usuário: "botão de perfil é meio
inutil, da p por todos os botoes e info dele ja no waifu... ai pode mover
o divorciar para o lado do upar nivel")** - `montar_embed_perfil`/
`ViewPerfilAcoes` DELETADOS. `montar_embed_hub` virou o superset (WiShards
+ Coleção que já tinha + Favoritas + Ranking do servidor que só existiam
no Perfil). `ViewHubWaifu` ganhou Favoritar/Merge/Prova de Soulmate/toggle
Auto-coleta num `row=2` novo (os 2 rows anteriores já estavam com 5
botões cada, o teto do Discord por linha) - 13 botões no hub agora, 3
linhas. Divorciar NÃO veio pro hub - foi pro card "🔍 Personagem"
(`_ViewNivel`), ao lado de "⬆️ Upar Nível": já que o card já mostra UMA
personagem específica, divorciar ali é direto, sem precisar abrir outro
select só pra escolher de novo quem. O aviso de "está favoritada, tem
certeza?" (regra de sempre, preservada) agora volta pro MESMO card se
cancelar - `_ViewConfirmar` ganhou um `ao_cancelar` opcional (default
continua sendo o comportamento antigo, apagar a mensagem) só pra esse
caso, os outros usos (Merge, Garantia da Loja, upgrades de rolls/claims)
ficam exatamente como estavam.

🔥 **Acerto de rota durante a implementação**: a exclusão em massa que
tirou `montar_embed_perfil`/`ViewPerfilAcoes` (feita editando um
INTERVALO DE LINHAS do arquivo, não uma substituição de texto exato)
calculou a fronteira errada e apagou 4 classes que não tinham nada a ver
com o Perfil (`_ViewSelecionarPersonagem`, `_ViewConfirmar`,
`_ModalBuscarPersonagem`, `_ViewNivel`) - descoberto na hora (o arquivo
parou de compilar/a varredura de sanidade não achou mais essas classes),
reconstruídas do zero a partir do conteúdo já escrito nesta mesma sessão
(estavam registrados nas mensagens anteriores desta conversa) e
validadas de novo (compilação + varredura de sanidade de TODAS as Views +
smoke test específico de `_ViewNivel` com Upar/Divorciar) antes de
reiniciar o ERIS. Lição: editar por INTERVALO DE LINHAS é mais arriscado
que substituição de texto exato quando várias edições já mudaram os
números de linha - preferir sempre âncoras de texto.

**"⬆️ Nível" removido, "🔍 Personagem" vira o único jeito de ver/upar +
todo dropdown de coleção ordenado por CP/popularidade (mesmo dia, pedido
do usuário: "Pode remover o botão de nivel, renomeie o ver para
personagem e deixe apenas ele. Todo dropdwon q listar waifu, sempre
ordene pelas com maior CP/popularidade")** - 2 mudanças:

1. Com o card do "🔍 Ver" já mostrando Nível + botão de upar (achado
   anterior), o botão "⬆️ Nível" separado do Perfil virou redundante -
   removido (`_abrir_nivel`/`_nivel_selecionado` deletados), botão
   renomeado "🔍 Ver" -> "🔍 Personagem".
2. `torre.ordenar_por_power(personagens, guild_id, user_id)` (novo, usa
   `power_personagem` por trás) - aplicado em TODO dropdown de personagem
   JÁ POSSUÍDA antes de cortar em 25: Favoritar/Divorciar/Merge
   (`_colecao_ate_25` tinha o bug de cortar em 25 ANTES de ordenar - dava
   um recorte arbitrário por raridade/nome, nunca as 25 de maior CP de
   verdade), Prova de Soulmate, Adicionar/Remover da Party (o filtro de
   role já filtrava por categoria, agora também ordena por CP dentro do
   filtro), e as 2 etapas de Trocar (coleção de quem propõe e do alvo).
   Wishlist (personagem NÃO possuída, sem Nível/Afinidade de vínculo -
   CP não faz sentido) trocou pra `ORDER BY p.popularidade DESC` direto
   no SQL de `db.wishlist_listar`, mais simples que ordenar em Python já
   que não precisa de nenhum contexto de vínculo. A Loja (`_ViewComprarPersonagem`)
   ficou de propósito FORA - `personagens_livres_por_raridade` já é
   `ORDER BY RANDOM()` por design (rotação/variedade do estoque
   disponível pra compra); ordenar por popularidade ali sempre mostraria
   as mesmas personagens toda vez e mataria a variedade que o `RANDOM()`
   existe pra dar.

**Card e Party ganharam Nível (mesmo dia, 2 achados do usuário em
sequência - "ta faltando informacao do level e opcao de upar" e depois
"na pt tbm esta faltando informa o level")** - `_ViewNivel` deixou de ser
exclusiva do fluxo "⬆️ Nível" do Perfil e virou a MESMA tela que "🔍 Ver"
usa (`montar_embed()` monta `consulta.embed_carta_personagem` + campo
"Nível" + o botão "⬆️ Upar Nível" reaproveitável já existente) - ver
"tanto Ver quanto Nível abrem o mesmo card com botão de upar" abaixo. Em
"Sua Party"/`_descricao_combate` (Adicionar/Remover), `torre.power_
personagem` já devolvia `(power, nivel, categoria)` mas o `nivel` vinha
descartado (`_nivel`) - só usado pra CALCULAR o CP, nunca exibido -
corrigido pra aparecer como `Nv.X` ao lado do CP nos 2 lugares.

**Botão "🔍 Ver" no hub - card completo fora do momento do claim (mesmo
dia, pedido do usuário: "qnd eu coleto a personagem, mostra a raridade,
classe e foto dela. Tem outra forma de ver isso?")** - conferido: essas 3
infos só existiam no embed de confirmação do claim
(`gacha._embed_confirmacao_claim`, `set_thumbnail`) - a lista da Coleção
(`consulta.linha_personagem`) é só texto, nunca mostrou foto. Botão "Ver"
novo no `ViewHubWaifu` (row 1, 5º slot - a última vaga livre na linha, já
que a linha 0 já tem os 5 botões que o Discord permite) reaproveita a
MESMA busca por nome do "⬆️ Nível" (`_ModalBuscarPersonagem`, ver abaixo)
- só que com `editar_mensagem_original=False` (parâmetro novo do Modal),
já que "Ver" precisa mandar mensagem NOVA (mesmo padrão de Coleção/
Perfil/Party, que nunca editam o hub), diferente do fluxo de Nível
(raiz no Perfil, edita a própria mensagem do painel). `consulta.
embed_carta_personagem(personagem)` monta o card (raridade, classe -
"_(ainda não revelada)_" se nunca foi reivindicada em nenhum servidor,
série, Afinidade/Soulmate se já tiver, `set_image` em vez de `set_
thumbnail` - card grande, já que aqui é o card em si, não uma confirmação
ao lado de outra info).

**Busca por nome + Nível reaproveitável (mesmo dia, pedido do usuário:
"ja tenho mais de 50 personagens, e discord so lista 25... ta muito ruim
subir nivel. E qnd eu confirmo, podia ser igual é na torre, ja trocar o
texto p permitir upando mais vezes")** - 2 problemas distintos no mesmo
fluxo de "⬆️ Nível":

1. `_ViewSelecionarPersonagem` é limitado a 25 opções (teto do PRÓPRIO
   Discord pra um `discord.ui.Select`) - com coleção de 50+, a maioria
   nunca aparecia (dependia de qual ordem `colecao_do_usuario` devolvia).
   `_ModalBuscarPersonagem` (novo) abre ANTES do select, pede um nome
   (campo `discord.ui.TextInput`, pode ficar vazio) e filtra a coleção
   INTEIRA por `consulta.buscar_por_nome` antes de montar o select -
   substring vira prioridade máxima, resto cai pra similaridade de texto
   (`difflib.SequenceMatcher`). Comparar só com o NOME INTEIRO penalizava
   demais um erro de digitação numa palavra só (`"asnua"` vs `"asuna
   yuuki"` ficava com nota baixa por causa do "yuuki" sobrando) -
   corrigido comparando TAMBÉM palavra por palavra e ficando com a melhor
   nota das duas formas. Validado: "asnua" acha "Asuna Yuuki" em 1º
   lugar. Campo vazio cai no comportamento de sempre (primeiros 25 pela
   ordem de quem chama).
2. Depois de confirmar, o fluxo antigo (`_ViewConfirmar` genérico)
   terminava a conversa (`view=None`) - upar de novo exigia reabrir a
   busca inteira. `_ViewNivel` (novo) troca isso por um botão único
   reaproveitável, mesmo padrão de `_ViewTorre` - `_atualizar_estado()`
   lê nível/custo FRESCOS do banco a cada clique e só desabilita o botão
   quando bate no nível máximo, deixando upar várias vezes seguidas na
   MESMA mensagem.

Nota técnica: `_ModalBuscarPersonagem.on_submit` usa `interaction.
response.edit_message(...)` mesmo sendo o submit de um Modal (não um
componente) - funciona porque o Modal foi aberto a partir de um CLIQUE DE
BOTÃO (`interaction.response.send_modal`), e o Discord/discord.py carrega
a mensagem original desse botão pro submit do Modal também poder editá-la
(mesmo padrão de mensagem única de sempre, sem precisar abrir conversa
nova).

🔥 **O select de busca não some mais ao escolher UMA personagem
(2026-08-30, pedido do usuário: "quero q o dropdown de selecionar
personagem nao suma ao escolher um")** - antes, `_ViewSelecionarPersonagem`
(mostrado depois do Modal) era substituído INTEIRO por `_ViewNivel` (o
card) assim que a pessoa escolhia - pra ver outra personagem da mesma
busca era preciso reabrir `_ModalBuscarPersonagem` do zero. Correção em 2
partes:
- `_ModalBuscarPersonagem.on_submit` passou a envolver o `ao_selecionar`
  de quem chamou numa closure local (`_selecionar_com_pool`) que também
  repassa `candidatos` (o pool INTEIRO já filtrado pela busca, não só a
  personagem escolhida) - `_ViewSelecionarPersonagem` continua com seu
  contrato de 2 argumentos de sempre (`ao_selecionar(interaction,
  personagens)`), então Merge/Party (os outros 2 usos de `_ViewSelecionar
  Personagem`, que NÃO passam por este Modal) não mudam nada. Só `_ver_
  selecionado` (único `ao_selecionar` passado a este Modal) ganhou o 3º
  parâmetro `candidatos`.
- `_ViewNivel` ganhou um parâmetro opcional `candidatos` - quando tem MAIS
  de 1, monta seu PRÓPRIO `discord.ui.Select` ("🔄 Trocar de personagem",
  `row=1`, separado dos 4 botões de sempre que ficam em `row=0` por
  auto-layout do discord.py) com uma opção por candidato. Escolher ali
  chama `_trocar_personagem` - troca `self.personagem` e re-renderiza
  `montar_embed()` na MESMA View (não reconstrói `_ViewNivel` do zero,
  então o próprio select "Trocar de personagem" permanece intacto pra
  trocar de novo). Sem `candidatos` (ou só 1) - comportamento de sempre,
  sem select nenhum (dropdown de 1 opção só não ajudaria ninguém).

Validado numa cópia da produção: o select lista os 25 candidatos certos
(mesma ordem/CP de `torre.ordenar_por_power`), trocar de personagem
atualiza CP/Nível/Afinidade/Vínculo pro novo alvo mantendo a mesma View
(instância idêntica, só o conteúdo interno muda), nenhum select aparece
quando a busca só traz 1 resultado.

🔥 **`_descricao_personagem_dropdown` - 1 função ÚNICA pra descrição de
personagem em QUALQUER dropdown + setas ◀️▶️ no card (2026-08-30, pedido
do usuário: "no dropdwon de ver personagem tem q informar o icone da
classe, CP, lv e afinidade. Tem varios locais q repetem esse padrao, pq
vc n esta usando 1 p tudo?" + "quando estou na tela de personagem, quero
q tenha as setas p direita e esquerda p trocar entre eles rapido, sem
precisar passar pelo dropdwon")** - antes de hoje existiam 2
implementações levemente diferentes do mesmo texto "#id · raridade" pra
opção de select: o default sem detalhe nenhum de `_ViewSelecionarPersonagem`
(usado por Merge e pelo select de busca do "🔍 Personagem") e `ViewEquipe.
_descricao_combate` (usado por Party Adicionar/Remover, com CP+Nível mas
SEM Afinidade). O usuário notou a duplicação e pediu 1 função só:
- **`_descricao_personagem_dropdown(personagem, guild_id, user_id,
  contexto_lote=None)`** (módulo `paineis.py`, função solta - não é método
  de nenhuma View, já que é reaproveitada por várias) - monta `(texto,
  emoji)` no formato `"#id · raridade · Nv.X · CP Y · 💞Z"` + ícone de
  `torre.icone_categoria`. `contexto_lote` (opcional, de `torre.
  _contexto_lote`) evita reabrir uma conexão SQLite por personagem ao
  montar uma lista inteira de até 25 opções - mesmo mecanismo do fix de
  performance do Auto-Party (`ARQUITETURA.md`, seção Auto-Party acima).
  `ViewEquipe._descricao_combate` foi REMOVIDA (não deixada como
  duplicata morta) - Merge (`_abrir_merge`), Party Adicionar/Remover
  (`_abrir_adicionar`/`_abrir_remover`) e "🔍 Personagem" (`_ver`) agora
  passam `descricao=lambda p: _descricao_personagem_dropdown(p, guild_id,
  user_id, contexto_lote)` (`contexto_lote` calculado 1x por chamador,
  antes de montar a lista de opções). O default sem detalhe de
  `_ViewSelecionarPersonagem` fica só como fallback genérico pra um
  eventual chamador futuro sem `guild_id`/`user_id` à mão - nenhum
  caller de hoje usa mais ele.
- **Setas "◀️"/"▶️" em `_ViewNivel`** (linha própria, `row=2`, abaixo do
  select "Trocar de personagem" em `row=1`) - navegam pelo MESMO
  `self._candidatos` por índice (`self._indice_atual`), sem precisar
  abrir o select. Desabilitam nas pontas (não dá volta ao início/fim),
  mesmo padrão de paginação já usado em `consulta.ViewColecao`
  (`disabled=self._indice_atual <= 0` / `>= len(candidatos) - 1`) -
  recalculado dentro de `montar_embed()`, mesmo lugar que já sincroniza
  o estado de todos os outros botões (Upar Nível/Afinidade/Favoritar) a
  cada render.

Validado numa cópia da produção: descrição bate com/sem `contexto_lote`,
opção do select mostra ícone/CP/Nível/Afinidade corretos, setas avançam/
recuam pelo índice certo e desabilitam nas pontas sem estourar os limites
da lista, Merge/Party/hub continuam construindo sem erro com a nova
descrição.

**Auto-Party (mesmo dia, pedido do usuário: "coloca um auto-party. Que
pega as restrições do andar p montar a pt com maior CP")** - botão
"🤖 Auto-Party" no painel da Torre, ao lado do "🗼 Subir". Substitui a
Party INTEIRA (`db.limpar_equipe` + `db.definir_posicao_equipe` pra cada
selecionado), usando TODA a coleção do jogador (não só quem já tava na
Party) - `torre.montar_auto_party` resolve a restrição do andar ATUAL
(`db.andar_atual_torre`/`restricao_andar`) e delega pra `_selecionar_
auto_party`:

- Estratégia gulosa: parte do TOP 5 por CP bruto (`sorted(...)[:tamanho]`)
  - já é válido de graça pra andares sem restrição, e é o CASO COMUM (a
  maioria dos andares não restringe nada).
- `so_dps` filtra Tank/Support ANTES de ordenar (não dá pra "consertar"
  depois, tem que nunca entrar).
- `min_tank`/`min_support` (`_garantir_categoria`): se a categoria já
  não tá presente, troca o membro de MENOR CP pelo melhor candidato
  daquela categoria fora da seleção - perde o mínimo de CP possível pra
  cumprir a restrição.
- `max_1_tank` (`_aplicar_max_1_tank`): se tiver 2+ Tanks, troca os
  excedentes (do mais fraco pro mais forte) pelo melhor não-Tank
  disponível, mantendo só o Tank de maior CP.
- `todas_categorias` (`_aplicar_todas_categorias`): mesma lógica de
  `_garantir_categoria`, mas BLOQUEIA quem já garante uma categoria de
  ser removido pela troca seguinte (senão a 2ª/3ª troca podia desfazer a
  1ª - ex.: garantir Tank e depois "consertar" Support removendo
  justamente o Tank que acabou de entrar).
- Sem candidato disponível pra uma categoria exigida (ex.: jogador não
  tem NENHUM Tank na coleção) - segue sem, a restrição fica parcialmente
  cumprida (não trava o Auto-Party) - o preview seguinte mostra ❌ e o
  jogador sabe que precisa obter aquela categoria.

Validado numa CÓPIA do banco de produção (nunca o banco real), forçando
`colecao_torre_progresso.andar_atual` pelos 6 índices de restrição -
confirma restrição cumprida em cada caso e CP maximizado (andar sem
restrição bate exatamente com a soma do top-5 bruto; andar `so_dps`
troca corretamente os Support do top-5 pelos próximos DPS).

🔥 **Correção de performance - N+1 de query estourava o teto de 3s do
Discord (2026-08-30, achado do usuário: "o auto-party esta atualizando a
pt logicamente, mas n troca visualmente, da erro de GAIA não respondeu a
tempo")** - `montar_auto_party` chamava `power_personagem` uma vez por
personagem da coleção INTEIRA pra montar o `pool`; `power_personagem`,
por sua vez, chamava `db.nivel_personagem`/`db.bonus_cp_global`/`db.
bonus_cp_classe` (esse último, novo no mesmo dia) - CADA uma dessas
abrindo uma conexão SQLite NOVA (`db.conexao()` não faz pool, é
`sqlite3.connect()` puro por chamada, decisão original documentada logo
no topo deste arquivo pra evitar lock de escrita concorrente entre
processos). Numa coleção de ~530 personagens isso é 1.500+ conexões
abertas/fechadas num único clique - tempo suficiente pra estourar os 3s
que o Discord dá pra responder uma interação, mesmo com a escrita no
banco (`limpar_equipe`/`definir_posicao_equipe`) já tendo terminado por
baixo (por isso "atualiza a pt logicamente mas não troca visualmente" -
o `response.edit_message` chegava tarde demais, Discord já tinha
descartado o token da interação).

Correção em 2 camadas:
- **`power_personagem` ganhou 3 parâmetros opcionais** (`nivel`,
  `bonus_global`, `cache_bonus_classe`, todos `None` por padrão -
  chamada avulsa de 1 personagem continua idêntica, sem quebrar nenhum
  dos outros ~10 call sites em `paineis.py`). `db.nivel_em_lote` (nova) -
  1 query só devolvendo `{personagem_id: nivel}` de TODO o vínculo, no
  lugar de 1 query por personagem. `torre._contexto_lote` (nova) monta
  os 3 - nível em lote, `bonus_cp_global` (calculado 1x só, não depende
  de personagem nenhuma) e um dict vazio de cache por classe (só
  preenche 1x por classe ÚNICA encontrada, não por personagem).
- **`montar_auto_party` e `ordenar_por_power`** (esta última usada pelos
  dropdowns de Favoritar/Divorciar/Merge/Trocar - mesmo N+1, menos grave
  porque corta em 25 depois, mas presente) passaram a chamar `_contexto_
  lote` UMA VEZ antes do loop e repassar pra cada `power_personagem`.
  Resultado (~530 personagens, cópia da produção): `montar_auto_party`
  caiu de bem acima de 3s pra **0,83s**; `ordenar_por_power`, **0,77s**.
- **Botão "🤖 Auto-Party" ganhou `interaction.response.defer()`** antes
  de calcular (`edit_original_response` no lugar de `response.
  edit_message` depois) - rede de segurança independente da otimização
  de query, já que qualquer operação que varre a coleção inteira e
  escreve no banco é candidata a esbarrar no teto de 3s de novo conforme
  a coleção cresce. O botão "🗼 Subir" não precisou do mesmo tratamento -
  só itera sobre a Party (≤5 membros), nunca a coleção inteira.

🔥 **Causa raiz DE VERDADE do timeout - bloqueio do event loop inteiro,
não só da própria interação (2026-08-30, achado do usuário: "Auto-party
esta demorando e as vezes cai em GAIA não respondeu a tempo. O Cidade e
Personagem cai com frequencia nesse erro tbm")** - o fix de N+1 acima
(0,83s pra ~530 personagens) e o `defer()` do Auto-Party já estavam em
produção, mas o usuário continuou vendo o erro - e agora também no
"🏙️ Cidade" e no "🔍 Personagem", que NEM SÃO tão pesados quanto o
Auto-Party. A explicação: `db.conexao()` é `sqlite3` **síncrono** (não
`aiosqlite`), e TODO o pacote roda num único event loop asyncio por
processo ERIS (`completo`/`musica`, 1 thread cada). Uma função `async def`
que chama uma função SÍNCRONA que demora (ex.: `torre.ordenar_por_power`
varrendo 530-634 personagens, ~0,8-1,4s) **bloqueia esse event loop
inteiro** durante esse tempo - não trava só a interação que disparou a
varredura, trava TODO o processo, incluindo o despacho de QUALQUER outra
interação (de QUALQUER usuário, em QUALQUER comando) que chegue nesse
meio-tempo. Por isso o `defer()` do Auto-Party sozinho não bastava: se a
PRÓPRIA chamada de `defer()` de uma interação for despachada enquanto o
loop já está ocupado rodando a varredura de OUTRA interação, essa
corrotina nem começa a executar até o bloqueio acabar - `defer()` não é
mágico, ele também precisa do loop livre pra ser enviado a tempo. Isso
explica por que Cidade/Personagem (mais leves, mas ainda scanners de
coleção inteira) caíam "com frequência": bastava a interação deles
chegar durante a janela de bloqueio de QUALQUER OUTRA varredura pesada
rodando em paralelo (a do próprio usuário ou a de outra pessoa no mesmo
servidor).

**Correção: `asyncio.to_thread` em TODO scan de coleção inteira** (mesmo
padrão que "Rolar" já usava desde antes, `gacha.rolar_varios` via
`asyncio.to_thread` em `ViewHubWaifu._rolar`) - roda a função síncrona
pesada numa thread do executor padrão, liberando o event loop pro resto
do bot continuar despachando/respondendo em paralelo. Aplicado em:
- `_ViewTorre.auto_party` - `torre.montar_auto_party` via `to_thread`
  (mantendo o `defer()` já existente).
- `ViewHubWaifu._cidade` - ganhou `defer()` (não tinha) + `cidade.
  coletar_producao_pendente` via `to_thread`.
- `ViewHubWaifu._ver` (🔍 Personagem) - `torre.ordenar_por_power` E
  `torre._contexto_lote` via `to_thread` (a busca acontece ANTES de
  `send_modal`, que não pode ser precedido de `defer()` - modal tem que
  ser a PRIMEIRA resposta - então aqui só o `to_thread` resolve).
- `ViewHubWaifu._colecao_ate_25` (Merge) - virou `async def`, `db.
  colecao_do_usuario` + `torre.ordenar_por_power` + `torre._contexto_lote`
  via `to_thread`.
- `ViewEquipe._abrir_adicionar` (Party Adicionar) - `torre.ordenar_por_
  power` + `torre._contexto_lote` via `to_thread` dentro do `prosseguir`
  do filtro de role. `_abrir_remover` NÃO precisou (só itera sobre a
  Party, ≤5 membros - bounded, não vale o overhead de mais uma thread).
- `_ViewEscolherAlvoTroca._selecionou` e `_ViewEscolherPersonagensTroca.
  _avancar` (as 2 etapas de "🔄 Trocar" que buscam a coleção do outro
  jogador) - via `to_thread`.
- **`ViewColecaoHub` (modo "📚 Minha coleção")** - caso mais delicado: a
  varredura acontecia dentro de `__init__` (síncrono por natureza, uma
  `discord.ui.View` não pode ter `__init__` `async`). Extraído pra um
  `@staticmethod colecao_minha_ordenada(guild_id, membro_id)` que `_dados_
  do_modo` usa se NADA for passado (fallback síncrono, mesmo
  comportamento de antes) - mas os 2 pontos que de fato CONSTROEM a View
  (`ViewHubWaifu._colecao` e `ViewColecaoHub._trocar_modo`, ambos `async`)
  agora chamam `colecao_minha_ordenada` via `to_thread` ANTES de
  construir/atualizar a View e passam o resultado pronto
  (`colecao_minha_precomputada`).

Validado numa cópia da produção (634 personagens, coleção cresceu desde
o fix anterior): resultado de `ordenar_por_power` idêntico rodando direto
vs. via `to_thread`; e a prova concreta de que o event loop fica LIVRE -
uma corrotina de fundo (`asyncio.sleep(0.01)` num loop) continuou
"tiquetaqueando" 90 vezes durante os ~1,4s de `montar_auto_party` via
`to_thread` (antes, ficaria travada o tempo inteiro, 0 tiques).

**Filtro de role ao Adicionar na Party (mesmo dia, pedido do usuário: "na
hora de adicionar, deixa selecionar a role p filtrar e ficar facil de
preencher oq precisa")** - `_ViewFiltrarCategoria`, passo extra SÓ no
fluxo de Adicionar (Remover não precisa - a lista já é só quem tá na
Party): select com Todas/DPS/Tank/Support, filtra os candidatos por
`torre.categoria_personagem` antes de abrir o select de personagens de
sempre - útil pra caçar rápido "preciso de 1 Tank pro andar X" sem rolar
25 opções manualmente. Mesma mensagem única de sempre, só ganhou mais uma
etapa editada em sequência.

## Progressão Global da conta + Cidade (2026-08-30)

Usuário trouxe uma análise própria (16 seções) depois de a Torre expor um
problema real na prática (Andar 36: Party principal já quase maximizada
individualmente - Nv.10/Afinidade 10/Soulmate em várias personagens -
mas o Power exigido pela Torre continuando a subir). Regra de ouro da
análise: "a personagem possui um limite de desenvolvimento. A conta
não." Perguntado sobre escopo, o usuário confirmou querer TUDO
implementado junto com a Cidade, com uma condição explícita: "n iremos
setar personagens em funcoes manualmente, sera automatico com base na
classe/profissão."

**Decisão de arquitetura**: Progressão Global (Nível/XP/bônus de CP/
upgrades da Loja) mora inteira em `db.py`, NÃO num módulo `progressao.py`
separado - mesmo lugar de `custo_proximo_nivel`/`comprar_upgrade_rolls`,
que também são "conceitualmente de um sistema" mas já vivem lá. Isso
evita um ciclo de import: `torre.power_personagem` só CHAMA `db.bonus_cp_
global`, nunca o contrário. Cidade (`pandora/cidade.py`) já É um módulo
próprio, porque PRECISA de `torre.power_personagem` (CP dos
trabalhadores) - não podia morar em `db.py` (`db.py` nunca pode importar
`torre.py`, que já importa `db.py`).

### Nível de Progressão + XP

`colecao_progressao` (guild_id, user_id, nivel, xp, nivel_treinamento_
global, nivel_potencial_colecao). `db.xp_necessario_nivel(nivel) = round(
150 × 1,06^(nivel-1), -1)` - geométrico, mesmo estilo de `torre.power_
alvo_andar` (número novo, a análise autoriza "valores exatos podem ser
balanceados posteriormente"). `db.creditar_xp_progressao` sobe de nível
em CASCATA se o XP creditado de uma vez passar de mais de 1 limiar (ex.:
marco de coleção grande).

**Fontes de XP** (Seção 4 da análise) - hooks em cada lugar que já
credita alguma coisa, nunca um sistema separado: claim (`gacha.py`,
`raridade × 15`), subir Nível de personagem (`db.subir_nivel`, `custo ÷
5`), Divórcio (`db.divorciar`, NOVO - `raridade × 10 + nível × 15 +
(Soulmate: 50, senão Afinidade × 3)`, sempre uma FRAÇÃO do investido,
nunca lucro, a fórmula de WiShards que já existia não mudou), Merge
(`economia.executar_merge`, `25 × raridade`), andar da Torre vencido
(`torre.tentar_andar`, `10 × andar`, ×5 em checkpoints de 50), marcos de
coleção única (`db.checar_marcos_colecao`, 100/200/500/1.000/2.000/5.000/
10.000 personagens - `colecao_progressao_marcos` guarda o maior já pago,
nunca credita 2x). Fora do escopo: incremento bruto de Afinidade (não
achei uma ação discreta isolada no código pra isso - arriscado hookar às
cegas); Soulmate já é coberto indiretamente (o bônus de 50 no Divórcio).

### Bônus global de CP

`db.bonus_cp_global(guild_id, user_id) -> (bonus_fixo, bonus_
percentual)`:
```
bonus_fixo = 10 × nivel_conta + 25 × nivel_treinamento_global
bonus_percentual = ((nivel_conta // 5) × 1 + 2 × nivel_potencial_colecao) / 100
```
Números batem EXATAMENTE com os 2 exemplos concretos que a análise deu
(validado em teste): Nível de Progressão 20 -> +200 CP fixo/+4% (10×20=200,
20//5=4); Treinamento Global Nv.14->15 soma +25 (350->375) custando 700
(50×14); Potencial da Coleção Nv.9->10 soma +2% custando 1.000 (100×10).
Os 2 upgrades da Loja (`db.comprar_treinamento_global`/`comprar_
potencial_colecao`) são os ÚNICOS do Colecionador SEM nível máximo, de
propósito - a análise pede isso explicitamente ("podem continuar
crescendo indefinidamente").

**Único ponto de aplicação**: `torre.power_personagem` faz `power = (power
+ bonus_fixo) × (1 + bonus_percentual)` logo depois de calcular `power_
final` - como TODO o pacote calcula CP através dessa função (confirmado
numa exploração antes de implementar: `ordenar_por_power`, `_calcular_
contexto`, os dropdowns de CP em `paineis.py` - todos passam por ela),
nenhum outro lugar precisou mudar. Uma personagem no teto individual
(Nv.10/Afinidade 10/Soulmate) continua ficando mais forte no futuro
conforme a CONTA evolui - exatamente o objetivo da análise.

### Cidade

`pandora/cidade.py` - taxonomia FECHADA de "Função da Cidade" (`FUNCOES_
CIDADE`: Produção, Comércio, Serviço, Cultura, Saúde, Administração,
Militar - já validada em princípio numa sessão anterior, `TODO.md`
"Roadmap futuro", antes da Cidade existir de verdade). Uma personagem
"trabalha" se: possuída + NÃO está na Party atual (`db.obter_equipe`) +
já tem `classe` revelada (mesma janela de `categoria_combate`) - **zero
configuração manual**, exatamente o pedido do usuário.

**Produção ACUMULADA NO TEMPO (pull-based), sem scheduler novo** -
`colecao_cidade_estado` guarda só `ultima_producao_em`; `cidade.
coletar_producao_pendente` calcula tudo na hora que o jogador abre o
painel "🏙️ Cidade" (`horas = min((agora - ultima) em horas, 168)` - teto
de 7 dias). `wishards = round(cp_total × 0,01 × horas)`, `xp = round(
cp_total × 0,005 × horas)`. TODAS as 7 funções produzem na MESMA taxa -
a função existe pra AGRUPAR/mostrar quem tá fazendo o quê (breakdown no
embed), não pra virar 7 números de balanceamento inventados sem nenhum
dado real pra calibrar (mesmo princípio de "não complicar sem
justificativa" já aplicado antes nesta sessão). Fica registrado no
`TODO.md` como candidato a taxas diferenciadas por função numa leva
futura, se fizer sentido depois de validar ao vivo.

### Extensão do pipeline de classificação (`funcao_cidade`)

Mesmo padrão ponta a ponta que `categoria_combate` já usa (achado numa
exploração: 4 pontos de toque confirmados) - `assistant/core/agent/
turno.py::classificar_personagem_colecao` (GAIA) ganhou `_FUNCOES_
CIDADE_VALIDAS`, extensão do prompt (pede o campo na MESMA chamada de
LLM) e validação/normalização com fallback seguro ("Serviço", a mais
genérica das 7); `assistant/integrations/iris_bridge.py` (dict de
fallback); `pandora/gaia_webhook.py::pedir_classe_personagem` (mudança
OBRIGATÓRIA - reconstrói o dict por 3 chaves fixas, o 4º campo seria
descartado em silêncio sem isso); `pandora/db.py::definir_classe_
personagem` (persiste em `colecao_classes.funcao_cidade`, mesma lógica de
"classe conhecida nunca é sobrescrita por sugestão nova" que já vale pra
`categoria_combate`).

**Backfill único das classes já existentes** (`classe` é write-once,
`backfill_funcao_cidade_2026-08-30.py` na raiz do repo) - mapeamento
manual (revisado por mim, não pela GAIA - as 39 classes já eram
conhecidas desta sessão), aplicado direto no banco de produção depois de
validado numa cópia. A GAIA só decide `funcao_cidade` pra classificações
NOVAS a partir de agora - **GAIA precisa reiniciar** pra isso valer (não
feito ainda, avisado antes de reiniciar).

**Reinício da GAIA confirmado (mesmo dia)** - watchdog (`scripts/
watchdog.py`, roda como supervisor separado) detectou o `run.py` morto e
subiu de volta sozinho, sem precisar montar o comando de novo na mão -
confirmado via `logs/run.log` (subprocesso Mascot + todos os
monitoramentos voltaram limpos, nenhum erro relacionado às mudanças).

## Ajustes no painel da Cidade + bônus por classe (2026-08-30)

**Painel mostra CAPACIDADE ATUAL, não mais o acumulado por área** (pedido
do usuário: "o painel deve mostrar sempre o bônus atual por hora,
independentemente de quanto tempo passou desde a última coleta") -
`cidade.coletar_producao_pendente` devolve `taxas_por_funcao` (a TAXA de
cada área, calculada SEM multiplicar pelas horas passadas desde a última
visita) separado do acumulado (`wishards`/`xp`/`soulstone`, que continua
só no resumo do topo do painel, esse sim proporcional ao tempo). Cada
área no card ganhou 3 linhas (`Personagens`/`CP`/`Bônus`) - `_embed_
cidade` (`paineis.py`) usa `_fmt_numero` (padrão BR - ponto de milhar,
vírgula decimal) pra formatar tudo.

🔥 Achado meu próprio, durante o teste em cópia: a 1ª versão desta
mudança tinha 2 chamadas `embed.set_footer(...)` seguidas (a 2ª, sem
formatação, sobrescrevia a 1ª) - `set_footer` sempre substitui o valor
anterior, nunca acumula. Achado comparando o footer esperado ("522.684")
com o que o teste realmente devolveu ("512955", sem separador) antes de
aplicar em produção.

**"Poder da Área" - quantidade E CP, nunca só CP** (pedido do usuário:
"os bônus das áreas não devem depender apenas do CP total... quantidade
e CP devem sempre participar do cálculo"):
```
Poder = CP_total × PESO_CP_POR_PODER + quantidade × PESO_PERSONAGEM_POR_PODER
```
(`cidade._poder_area`, pesos 1,0 e 50 - primeiro palpite, deliberadamente
MODESTO pro termo de quantidade - um Nv.1 já contribui ~300-1000 CP
próprio; se a quantidade valesse o mesmo que isso, hoardear fracas
ficaria tão bom quanto desenvolver, o oposto do que o usuário pediu:
"impede que simplesmente acumular centenas de personagens Nv.1 seja mais
eficiente do que desenvolvê-las"). Todas as 6 áreas (Militar/Saúde/
Cultura/Administração/Comércio/Arcano) convertem esse Poder pra sua
unidade - o "Bônus da Coleção" continua SEM esse termo (só CP total×1%,
não é uma área, é a coleção inteira, exemplo do usuário não tinha
quantidade nele).

**Bônus de CP por CLASSE (novo, taxonomia ABERTA - não confundir com as
6 "Funções da Cidade", que são a taxonomia FECHADA)** - pedido do
usuário: "a cd 5 aumenta 50" (a cada 5 personagens da MESMA classe
possuídas nesse servidor, +50 CP fixo pra TODAS daquela classe - não só
as na Party). `db.bonus_cp_classe`/`db.quantidade_possuida_da_classe`,
aplicado no MESMO ponto único de `torre.power_personagem`, junto do
bônus global de Progressão, antes do multiplicador percentual - incentiva
colecionar várias cópias da MESMA classe (ex.: várias "Bardo"), diferente
da Progressão Global (recompensa a conta inteira) e da Cidade (recompensa
por Função fechada). Validado: 44 "Bardo" possuídas -> +400 CP fixo pra
CADA Bardo (44 // 5 = 8, 8 × 50 = 400); classe com menos de 5 não ganha
nada ainda.

**"💎 Soulstone" substituiu "⭐ Favoritas" no hub `/waifu`** (pedido do
usuário) - `db.contar_favoritas` REMOVIDA (ficou sem nenhum outro
caller depois da troca - `db.eh_favorita`, usado por Favoritar/
Divorciar, é uma função diferente e continua existindo).

## 4 achados do usuário testando ao vivo (2026-08-30)

- **"Garantir raridade" mais caro que "Comprar" na mesma raridade** -
  `PRECOS_GARANTIA` (5⭐: 8.000) não tinha ligação nenhuma com `PRECOS_
  LOJA` (5⭐: 5.000) - contra-intuitivo, já que Garantir dá MENOS
  controle (a personagem em si continua aleatória). Virou `{r: PRECOS_
  LOJA[r] // 2 for r in (3, 4, 5)}` - derivado, nunca mais diverge.
- **"🎲 Rolar" do hub voltou a rolar `quantidade=0` (ciclo inteiro)** -
  reverte de propósito o `quantidade=1` de 2026-08-29 (ver seção do hub
  acima) - usuário decidiu que prefere o comportamento original.
- **CP faltando em "📚 Minha coleção" e no card "🔍 Personagem"** - os
  dois ganharam ícone de categoria + CP (`torre.power_personagem`), no
  mesmo padrão já usado em Party/Torre/dropdowns. "Minha coleção" também
  passou a ordenar por CP (a única coisa que faltava pra ficar
  consistente com "todo dropdown que listar personagem" - tecnicamente
  não é um dropdown, mas a mesma regra fazia sentido aqui).
- **Favoritar mudou do hub pro card "🔍 Personagem"** - mesmo padrão de
  Divorciar (implementado mais cedo no mesmo dia): botão ao lado de
  Upar Nível/Divorciar, rótulo/estilo alternam Favoritar/Desfavoritar
  sempre lendo o estado fresco do banco em `montar_embed()`.

## Cidade v2 - efeitos diferenciados por área + Soulstone/Afinidade (2026-08-30)

Usuário voltou com um design concreto de efeitos DIFERENCIADOS por área
(a v1, "todas produzem igual", tinha ficado registrada explicitamente
como "candidato a leva futura, se fizer sentido depois de testar" - foi
essa leva) + uma mudança maior no mecanismo de Afinidade/Soulmate.

**Taxonomia 7 -> 6** (`cidade.FUNCOES_CIDADE`) - "Produção"/"Serviço"
saem, "Arcano" entra (absorve o que era místico/oculto de Cultura -
Místico/Ocultista/Oráculo - e de Serviço - Exorcista/Psíquico - + as 2
classes inválidas pendentes de limpeza, Maid/Mediador). Remigração das
40 classes já existentes no catálogo (`remigrar_funcao_cidade_2026-08-
30.py`, mesmo padrão do backfill v1) - achado ao remigrar: existem 2
pares de classe duplicada por nomenclatura (inglês x português -
"Assassin"/"Assassino", "Invoker"/"Invocador") que surgiram entre a v1 e
a v2 (claims novos aconteceram nesse meio-tempo) - fica registrado como
candidato a limpeza de consistência numa leva futura, fora do escopo
desta remigração.

**2 famílias mecânicas diferentes, distinção importante**:
- Saúde/Cultura/Comércio continuam RECURSO ACUMULADO NO TEMPO (mesmo
  mecanismo pull-based de sempre, `cidade.coletar_producao_pendente`) -
  a diferença é que cada um agora só alimenta o SEU recurso (antes os 3
  produziam WiShards+XP juntos, uniforme): Saúde -> Soulstone/h, Cultura
  -> XP de Progressão/h, Comércio -> WiShards/h.
- Militar/Arcano/Administração viraram BÔNUS DE CP AO VIVO pra Party -
  não dá pra "acumular" um bônus percentual/fixo de CP no tempo, é um
  MODIFICADOR de estado, não um recurso. Pra não escanear a coleção
  INTEIRA a cada cálculo de Torre (roda muito mais vezes que a visita à
  Cidade), os 3 (+ o "Bônus da Coleção" abaixo) são calculados e
  GRAVADOS como SNAPSHOT toda vez que `coletar_producao_pendente` roda -
  3 colunas novas em `colecao_cidade_estado` (`cp_bonus_militar_fixo`,
  `cp_bonus_arcano_percentual`, `cp_bonus_colecao_fixo`). `torre.
  calcular_power_party(membros, guild_id, user_id)` (assinatura ganhou
  guild_id/user_id) só LÊ esse snapshot via `db.cidade_bonus_party` (1
  SELECT barato), nunca recalcula a partir da coleção inteira.

**"Bônus da Coleção" (4º ingrediente, adicionado pelo usuário no meio da
implementação)** - 1% do CP de TODA a coleção (dentro ou fora da Party,
não é limitado a uma função) vira CP FIXO na Party, sempre - "cada
personagem coletada e evoluída contribui permanentemente pra sua
força" (exemplo do usuário: 50.000 CP de coleção -> +500 CP). Fórmula
final (`torre.calcular_power_party`):
```
CP Party Efetivo = (CP_base_da_Party + Bônus_Coleção + Bônus_Militar) × (1 + Bônus_Arcano)
```
`CP_base_da_Party` já inclui o bônus de Progressão (por personagem, via
`power_personagem`) e o bônus de composição (+10% se DPS+Tank+Support),
na ordem de sempre. Administração multiplica Militar/Arcano/Saúde/
Cultura/Comércio (as 5 outras ÁREAS) - NÃO multiplica o Bônus da
Coleção, que é um mecanismo à parte, sempre 1% fixo.

🔥 **Recalibração de constantes depois de testar contra uma conta REAL**
(~400 personagens, CP total na casa das centenas de milhares) - o
primeiro palpite de `TAXA_MILITAR_PARA_CP_FIXO`/`TAXA_ARCANO_PARA_
PERCENTUAL`/`TAXA_ADMINISTRACAO_PARA_PERCENTUAL` (do plano original)
tinha sido calibrado pra uma escala de CP ~10x menor que a real - o
teste mostrou Arcano+Administração combinados dando **+100% de CP**
sozinhos (Party quase triplicando de 9.190 pra 31.708 CP). Cortadas
~20-50x pra virar um SUPLEMENTO modesto (Party foi pra ~13.695, a maior
parte do ganho vindo do Bônus da Coleção, que é literal do usuário, não
palpite meu). `TAXA_BONUS_COLECAO` (1%) NÃO mudou - só as 3 que eram meu
próprio palpite.

🔥 **`TAXA_MILITAR_PARA_CP_FIXO` de 0,0005 pra 0,01 (2026-08-30, ajuste
manual pedido pelo usuário: "troca o 0,0005 do militar por 0.01")** - 20x
a mais em cima da recalibração acima, só nesta taxa (Arcano/Administração
ficaram como estavam). Validado numa cópia da produção (242 personagens
Militares, Poder ~706.980, Administração em +2,8%): bônus fixo de CP
Militar pra Party subiu de ~360 pra **~7.267 CP** - `cidade_bonus_party`
(snapshot gravado) bate exatamente com o cálculo manual.

**Soulstone (item novo)** - `colecao_soulstone_saldo`/`_ledger`, cópia
estrutural de WiShards (`db.saldo_soulstone`/`db.creditar_soulstone`) -
não existe nenhum outro padrão de "item" no código pra reaproveitar.
Usado SÓ pra upar Afinidade (`db.subir_afinidade_ate`, custo por degrau =
nível-alvo: 1->2 custa 2 Soulstone, 2->3 custa 3... pedido literal do
usuário) - **NUNCA compra Soulmate**. Botão "💕 Aumentar Afinidade" no
card "🔍 Personagem" (`_ViewNivel`), mesmo padrão reativo de "⬆️ Upar
Nível".

**"Upar Nível"/"Aumentar Afinidade" viraram dropdown (2026-08-30, pedido
do usuário: "o botao de upar nivel e afinidade tem de ser um dropdown, p
permitir pular ate o maximo")** - os dois clicavam +1 por vez; agora
abrem `_ViewEscolherAlvo` (novo, genérico - `paineis.py`, logo antes de
`_ModalBuscarPersonagem`), um `discord.ui.Select` com TODO alvo possível
(atual+1 até o máximo) já mostrando o custo TOTAL de cada opção, mais um
botão Cancelar. Escolher um alvo abre a tela de confirmação de sempre
(`_ViewConfirmar`, reaproveitada) com o custo total antes de debitar.
`db.subir_nivel`/`subir_afinidade` (incremento de +1) foram SUBSTITUÍDOS
(não hardenizados com wrapper) por `db.subir_nivel_ate`/
`subir_afinidade_ate` - pulam direto pro alvo, custo = soma de cada
degrau no caminho (`custo_total_ate_nivel`/`custo_total_ate_afinidade`,
somando `custo_proximo_nivel`/`custo_proximo_afinidade` que ficaram
intactos). Validado numa cópia da produção antes de aplicar: soma total
bate com a soma passo a passo, rejeita alvo <= atual ou > máximo,
`subir_afinidade_ate` nunca seta Soulmate.

🔥 **`_ViewEscolherAlvo` ganhou `saldo_atual` + reaproveitado pela Loja
(2026-08-30, pedido do usuário: "quando vai aumentar afinidade/nivel tem
q informar no dropdwon qnd q possuo. E na loja... tbm tem de permitr
comprar varios leveis por vez, tbm informando custo e qnt possuo no
proprio dropdown")** - 2 mudanças:
- **`saldo_atual` (opcional, `None` por padrão)** - quando passado,
  aparece no PLACEHOLDER do próprio select (visível ANTES de abrir o
  dropdown, sem gastar espaço de embed): `"Você tem {saldo} {unidade} -
  escolha o {rótulo} alvo..."`, formatado em BR (`_fmt_numero`, mesma
  função da Cidade). `_ViewNivel.upar`/`upar_afinidade` passam `db.
  saldo_wishards`/`saldo_soulstone` do autor.
- **"🏋️ Treinamento Global"/"📊 Potencial da Coleção" (Loja) migraram do
  "compra +1 por clique" pro MESMO `_ViewEscolherAlvo`** - diferença
  importante: esses 2 upgrades NÃO têm nível máximo (decisão original da
  Seção 7, "de propósito, os únicos upgrades SEM teto"), então não dá
  pra listar "até o máximo" como Nível/Afinidade de personagem fazem.
  Solução: as opções vão do nível atual+1 até
  `_TETO_OPCOES_DROPDOWN_LOJA` (= 25) níveis à frente - 25 é o limite de
  verdade de quantas opções um `discord.ui.Select` aceita (API do
  Discord), não um palpite de balanceamento. `db.custo_total_treinamento_
  ate`/`custo_total_potencial_ate` (somam `custo_treinamento_global`/
  `custo_potencial_colecao` de cada degrau, mesmo padrão de `custo_total_
  ate_nivel`) + `db.comprar_treinamento_global_ate`/`comprar_potencial_
  colecao_ate` (pulam DIRETO pro alvo, SUBSTITUEM as versões de +1 sem
  wrapper - eram os únicos 2 callers) alimentam o dropdown.
- **`_ViewEscolherAlvo._selecionou` passou a funcionar em 2 tipos de
  tela** - antes só sabia atualizar `embed` (card "🔍 Personagem", que
  sempre tem embed); a Loja usa mensagens só de `content` (texto puro,
  sem embed) - agora checa `interaction.message.embeds` e edita
  `content` OU `embed`, o que a mensagem original tiver.

Validado numa cópia da produção: soma de custo bate com a soma passo a
passo pros 2 upgrades da Loja, pular direto funciona, rejeita comprar de
novo no mesmo nível, rejeita saldo insuficiente, placeholder mostra o
saldo formatado certo tanto no card de personagem quanto na Loja.

**Soulmate mudou de mecanismo** (`gacha._resolver_resultado`, 3 ramos no
reencontro agora) - reencontro (rolar uma personagem já sua) continua
IDÊNTICO a antes quando Afinidade < 10 (+1 Afinidade + WiShards). NOVO:
reencontro numa personagem JÁ em Afinidade 10 e ainda NÃO Soulmate faz
ela virar Soulmate ali mesmo (`db.tornar_soulmate`, função nova e
mínima, DESACOPLADA de `registrar_tentativa_soulmate` da "Prova"
antiga) - substitui a "Prova de Soulmate" (RNG/pity) como o jeito de
virar Soulmate. Reencontro numa personagem JÁ Soulmate ("cópia") credita
+10 Soulstone extra (Afinidade não mexe mais, já no teto).

**"Prova de Soulmate" - só o botão saiu** (decisão explícita do usuário:
"só tirar o botão do hub, recomendado") - `gacha.tentar_prova_soulmate`/
`obter_textos_prova_soulmate`, `db.registrar_tentativa_soulmate`/
`personagens_prontas_para_prova`, `paineis._ViewEscolherRespostaProva`/
`_ViewEnfrentarProva`/`_embed_resultado_prova`, `gaia_webhook.
pedir_prova_soulmate` ficam intactos e DORMENTES (ninguém mais aciona) -
reaproveitar ou apagar de vez fica pra quando a conversão por Soulstone
for desenhada de verdade.

## Pendências

- UI (`paineis.py`/`consulta.py`/`economia.py`) continua misturada com
  lógica de negócio - refatorar pra separar de verdade só faz sentido se
  algum dia existir um 2º consumidor (outro bot Discord) que precise só da
  lógica sem as Views.
- Torre/Cidade (mecânicas do LegendsAwaken, ver histórico em
  `ARQUITETURA.md`/`TODO.md` do ERIS antes da extração) - documentadas,
  não implementadas. Entram aqui quando forem desenhadas, não no ERIS.
- Tabelas `colecao_*` órfãs em `Project-ERIS/data/eris.db` (ver seção
  "Migração de dado" acima) - candidatas a limpeza depois que este repo
  provar estabilidade em produção.
