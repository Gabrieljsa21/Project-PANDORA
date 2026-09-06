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
mecanismo à parte cobrindo a coleção INTEIRA, não uma área - exemplo do
usuário não tinha quantidade nele).

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

## Batalha 5x5 com Aposta de Personagem (2026-09-01)

Pedido do usuário ("Batalha apostando waifu - Obrigatorio ser junto 5x5 -
1 batalha por vez - 3vit ganha") - especificação COMPLETA (18 seções)
trazida pelo próprio usuário depois de eu perguntar o que a aposta
realmente move (transferência de personagem de verdade, não só
recompensa) e como o time é formado (1 jogador = 1 Party de 5, não 5
pessoas). PvP 1x1 novo, arquitetura DELIBERADAMENTE separada da Torre:

- **Reaproveita a Party existente, mas dá peso NOVO à ordem** - até esta
  leva, `colecao_equipe.posicao` existia mas nada no jogo lia o VALOR da
  posição (só o conjunto de quem tá lá dentro). A Batalha usa a ordem como
  a "formação secreta" dos 5 confrontos (Seção 7) - motivo de reaproveitar
  a Party em vez de inventar uma formação própria só pra isso.
- **CP não decide nada aqui** (Seção 4/18, ao contrário da Torre) - é
  Jokenpô de categoria de combate: DPS vence Support, Support vence Tank,
  Tank vence DPS (fechado, cada categoria vence 1 e perde pra 1, nunca
  duas - preserva a simetria 33,3%/33,3%/33,3% contra uma escolha
  desconhecida que a Seção 5 exige). Categorias iguais SEMPRE empatam,
  mesmo com CP muito diferente - de propósito, senão quebraria a simetria
  do sistema (Seção 6).
- **Resolução determinística + revelação gradual** - as 5 posições são
  fixadas no momento em que cada lado "fecha" a Party (desafiante na
  criação do desafio, defensor ao montar defesa), reveladas 1 confronto
  por vez (Seção 10, suspense) até alguém fechar 3 vitórias (Seção 11).
  Empate nas 5 posições = Morte Súbita (Seção 12): escolha secreta de
  categoria por AMBOS os jogadores, repetida até sair um vencedor -
  diferente do resto da resolução (que é 100% determinística a partir das
  Parties já fixadas), a Morte Súbita É a única mecânica com escolha em
  tempo real dos 2 lados.
- **Aposta = Raridade × Preço de Mercado (Seção 2)** - preço de mercado
  reaproveita `db.valor_base_wishards` (a MESMA referência estável de
  raridade usada em claim/reencontro/divórcio) - a Seção 16 do documento
  original avisa explicitamente contra usar "último preço negociado"
  (manipulável por negociação artificial) e deixa a fórmula exata como
  "decisão separada"; `db.valor_base_wishards` já é resistente a
  manipulação por natureza (fixo por raridade, não depende de trocas).
- **Risco assimétrico (Seção 3/13/17)** - desafiante arrisca WiShards
  (debitados NA HORA da criação do desafio, antes até do defensor
  responder); defensor arrisca a PRÓPRIA personagem. Se o desafiante
  vencer: leva a personagem (`db.transferir_personagem`, Afinidade NUNCA
  acompanha - mesma regra de sempre) e os WiShards apostados simplesmente
  SOMEM da economia (sink - "João não recebeu os 3.600 WiShards", nunca
  voltam pro desafiante nem vão pro defensor). Se o defensor vencer: ele
  MANTÉM a personagem E recebe a aposta inteira do desafiante.
- **Soulmate é proteção permanente contra desafio** (Seção 14) - checado
  na criação do desafio E de novo se o dono mudar no meio do caminho
  (proteção contra corrida - ver "restart-safe" abaixo).
- **Anti-perseguição (Seção 15)** - cooldown de 24h por PAR desafiante→
  defensor (`colecao_batalha_cooldown`) + limite de 3 desafios RECEBIDOS
  por dia por defensor, qualquer desafiante (`colecao_batalha_defesas_
  hoje`, reseta sozinho por `data` mudar, sem job/scheduler). "1 batalha
  por vez" (pedido original do usuário) interpretado como POR JOGADOR -
  nem desafiante nem defensor podem estar em 2 desafios ativos ao mesmo
  tempo (`db.batalha_ativa_do_jogador`), guild-wide.

**Estado 100% em `colecao_batalha_desafios` (nunca em memória do
processo)** - decisão deliberada, diferente de `ViewClaimMultiplo`/
`ViewTroca` (que aceitam "estado em memória, não sobrevive a um restart"
como limitação conhecida). Como há WiShards já debitados e uma personagem
em risco real, um restart do bot no meio de um desafio NÃO PODE travar
ninguém nem perder dinheiro - `ViewBatalhaHub` (botão "⚔️ Batalha" no hub)
sempre RECONSTRÓI o estado inteiro a partir do banco a cada abertura/
clique (mesmo padrão já usado por `_ViewNivel`/`_ViewTorre`, "sempre lê
estado FRESCO"), nunca depende de uma mensagem específica sobreviver. A
notificação do desafio ao defensor (`_anunciar_desafio`) é só INFORMATIVA
(texto simples, sem botão nenhum) - a ação de verdade sempre passa pelo
hub, cada jogador abrindo o PRÓPRIO (`/waifu` -> ⚔️ Batalha), nunca um
botão que os 2 dividem numa mensagem só.

`pandora/batalha.py` - motor PURO (zero discord.py, mesmo espírito de
`torre.py`): `resolver_confronto`/`resolver_rodadas` (Jokenpô + parada em
3 vitórias), `calcular_aposta`/`preco_mercado`, `iniciar_desafio` (valida
Seções 1/7/14/15 + debita a aposta), `montar_defesa` (congela a Party do
defensor, re-checa que ele ainda tem a personagem - cancela+reembolsa se
não tiver mais), `registrar_escolha_morte_subita` (compara as 2 escolhas
assim que a 2ª chega, limpa e repete se empatar). `cancelar_expirados`
(desafios `aguardando_defensor` há mais de 24h sem resposta - reset
preguiçoso sob demanda, chamado sempre que `ViewBatalhaHub` abre, sem job
novo) devolve o dinheiro ao desafiante se o defensor nunca responder.

**Validado numa CÓPIA da produção** (nunca o banco real - 2 guilds de
teste sintéticas, times de DPS/Support/Tank reais do catálogo): Jokenpô
fechado nos 6 confrontos possíveis, desafiante vencendo 3-0 (transferência
+ WiShards SOME, defensor não recebe nada), defensor vencendo 3-0 (recebe
a aposta, mantém a personagem), proteção de Soulmate rejeitando o
desafio, cooldown de 24h bloqueando um 2º desafio ao mesmo alvo, bloqueio
de "1 batalha por vez", Morte Súbita completa (5 empates -> escolha
secreta -> 1ª escolha não resolve sozinha -> 2ª escolha decide, DPS vence
Support). **Nenhum clique real no Discord ainda** - a busca de personagem
na coleção ALHEIA (`_ViewEscolherAlvoBatalha`, reaproveita `_ModalBuscar
Personagem` sem nenhuma mudança, já aceitava qualquer coleção como
parâmetro) e a revelação gradual editando a mesma mensagem (`_resolver_e_
revelar`, pausa de 1,5s por rodada) só passaram por leitura de código,
não por um teste ao vivo ainda.

## World Boss: Evento Cooperativo (2026-09-01)

Pedido do usuário - spec completa (25 seções) trazida de uma vez, ver
`PANDORA_worldboss_evento_cooperativo.md`. Evento PvE cooperativo,
diferente de tudo que existia até aqui no PANDORA (Torre/Batalha são sob
demanda, iniciados por um clique) - precisa de um RELÓGIO PRÓPRIO: aparece
4x/dia em horários fixos (10h/14h/18h/22h, **horário de Brasília, UTC-3
fixo** - Brasil não observa mais horário de verão desde 2019, então um
offset fixo é correto e evita depender do pacote `tzdata`, que não vem por
padrão no Python do Windows - testado nesta sessão, faltava), abre 10min
de inscrição, e resolve 1 turno/minuto sozinho depois disso.

- **`SchedulerWorldBoss`** (`pandora/worldboss.py`, `discord.ext.tasks.
  loop(seconds=30)`, mesmo padrão de `auto_colecionador.py`) - só roda na
  instância "completo" do ERIS (mesmo critério de `AutoColecionadorUsuarios`
  - é onde vive o painel `/waifu` -> 🐉 World Boss). 3 checagens
  independentes por tick, cada uma 100% derivada do banco: (1) spawnar um
  Boss novo nos 4 horários fixos por guild (marcador anti-duplicidade em
  memória, mesmo espírito de `_ultimo_roll`); (2) fechar inscrições vencidas
  (`inscricoes_fecham_em <= agora`); (3) executar turnos vencidos
  (`proximo_turno_em <= agora`). Nenhum estado de JOGO mora em memória do
  processo - um restart do bot no meio de um combate não perde turno nem
  trava o evento, o próximo tick de 30s simplesmente continua de onde o
  banco disse que estava (mesma filosofia "restart-safe" da Batalha 5x5).
- **Time agregado, não personagens individuais (Seção 13)** - depois de
  fechadas as inscrições, o CP congelado (snapshot, Seção 7) de cada
  categoria é SOMADO; o combate resolve "1 TIME vs. 1 BOSS", nunca
  personagem-por-personagem. Conversão (Seção 14/15):
  `Multiplicador(CP) = 1 + √(CP / REFERENCIA_CP)` (crescimento
  desacelerado, primeiro palpite igual toda constante nova do PANDORA) -
  `Dano Base × mult(CP DPS)` / `HP Base × mult(CP Tank)` /
  `Cura Base × mult(CP Support)`.
- **Entrada manual por TOGGLE (Seção 4/5/6)** - `worldboss.
  alternar_categoria` alterna 1 categoria no conjunto permitido do jogador
  (clicar de novo na MESMA categoria REMOVE ela, esvaziar o conjunto tira o
  jogador do evento) - decisão de design (não estava explícito na spec,
  mas resolve "como sair"/"como reduzir o conjunto" sem precisar de um
  botão "sair" separado, com só 3 botões DPS/Tank/Support persistentes).
  `personagem_id`/`categoria`/`cp` são sempre RECALCULADOS a partir do
  conjunto (nunca editados direto) - a personagem de maior CP dentre as
  categorias permitidas.
- **Entrada automática (Seção 8/9)** - só processada em `fechar_
  inscricoes`, DEPOIS de fechar as manuais (prioridade manual > automática
  garantida pela ORDEM de execução, nunca precisa checar explicitamente).
  Preferência de categorias em `colecao_worldboss_auto`, mesmo padrão de
  `colecao_auto_colecionar_usuarios` (Modo Auto-coleta do Colecionador).
- **Identidade dos bots (Seção 11, pergunta feita ao usuário)** - o ERIS
  tem 2 contas de bot reais (papel "completo"/GAIA e papel "musica"), mas
  `SchedulerWorldBoss` só roda na instância "completo" e não tinha acesso
  ao ID Discord da conta "musica" à mão. Resposta do usuário: "o CP dos
  bots vai ser a média dos players participante" - `_entrar_bots` usa 2
  `user_id` SINTÉTICOS ("bot:1"/"bot:2", nunca colidem com um snowflake
  real), `personagem_id = NULL`, CP = média dos participantes HUMANOS
  daquele evento (calculada 1x no fechamento). Prioridade de categoria
  (Seção 11): primeiro cobre categorias com ZERO humanos (garante 1 DPS+1
  Tank+1 Support); bot(s) sem categoria obrigatória reforçam a de MENOR CP
  agregado (critério escolhido pra "melhor contribuição disponível" - sem
  personagem própria pra bot escolher no modelo de CP-média).
- **10 mecânicas especiais (Seção 22)** - `pandora.worldboss.
  executar_turno` resolve todas num único motor genérico (7 passos da
  Seção 18), com branches explícitos por `mecanica` (decisão deliberada:
  um hook/plugin totalmente abstrato pra só 10 casos, cada um bem
  diferente, seria uma abstração prematura - "3 linhas parecidas é melhor
  que abstração prematura"). `boss_atk_atual` (persistido) só muda de
  verdade em Enfurecer (cresce 10%/turno) e Renascimento (novo patamar por
  morte) - todo o resto (Adaptação-Tank/Barreira/Posturas-Ruína/Cabeça
  Vermelha/Caos) é multiplicador TEMPORÁRIO só daquele turno
  (`atk_efetivo`), nunca gravado de volta - decisão explícita pra não
  confundir "crescimento permanente" com "modificador de fase/estado".
- **Sem recompensa nesta leva (pergunta feita ao usuário)** - a spec
  original não define WiShards/Soulstone/XP por vencer; resposta do
  usuário: "só o combate, sem recompensa por enquanto". Implementado
  exatamente assim - fica pra um pedido futuro separado, quando os
  valores forem definidos.
- **Validado só via simulação isolada** (nunca a produção nem um clique
  real no Discord) - as 10 mecânicas testadas uma a uma com `evento`
  sintético (Enfurecer/Drenar Vida/Adaptação nos 2 ramos/Ceifar (dispara
  só no turno certo)/Renascimento (as 2 mortes + a 3ª que encerra)/
  Barreira (absorve, quebra, excedente, fase de ATK)/Consumir/Posturas
  (as 3 fases)/Cabeças (efeitos vivos + destruição por limiar)/Caos), MAIS
  um ciclo de vida completo (spawn -> toggle de categoria (entra/sai/
  reentra) -> auto-entrada -> bots -> fechar inscrições -> formar time ->
  combate turno-a-turno persistido via banco até resolução) numa cópia do
  banco de produção. **Achado do próprio teste**: com CP real do catálogo
  (na casa das centenas/poucos milhares por personagem), o time perde no
  1º turno contra o ATK dos Bosses (12-17 mil primeiro-palpite) - confirma
  que os valores-base (Seção 14, "devem ser calibrados com os dados reais
  das contas") estão claramente descalibrados pra uso real, registrado
  como pendência de alta prioridade no `TODO.md` (mesmo padrão da Cidade,
  que precisou de recalibração depois de testar contra uma conta real).

## Correção na Batalha 5x5 - aposta paga ao desafiado + fórmula da Loja (2026-09-01)

Duas correções do usuário na MESMA mensagem que trouxe a spec de
Recompensas/Conquistas do World Boss (ver abaixo):

- **"Desafios por waifus tem de pagar os WiShards para o desafiado, n
  sumir"** - `batalha._finalizar_vitoria_desafiante` passou a creditar a
  aposta ao DEFENSOR mesmo quando o desafiante vence (reverte o "sink" da
  1ª implementação, que seguia a spec original à risca - Seção 17: "João
  não recebeu os 3.600 WiShards"). Agora perder a personagem SEMPRE vem
  com uma compensação em WiShards, nunca fica só no prejuízo.
- **"tem de ser o valor daquela raridade na loja... multiplica por 2"** -
  `batalha.preco_mercado` trocou `db.valor_base_wishards(raridade)`
  (raridade×20, dava só 500 WiShards de aposta pra uma 5⭐) por `db.
  PRECOS_LOJA[raridade] × 2` (5⭐: 10.000 WiShards) - `calcular_aposta`
  não multiplica mais pela raridade de novo (`PRECOS_LOJA` já escala
  sozinho). Validado numa cópia da produção: desafiante vence → defensor
  recebe a aposta (não é mais sink); nova fórmula bate com `PRECOS_LOJA[r]
  × 2` pra todas as raridades.

## World Boss: Recompensas e Conquistas (2026-09-01)

Pedido do usuário - spec completa (18 seções), ver
`PANDORA_worldboss_recompensas_conquistas.md`. Recompensas na vitória
(Seção 1: só participantes HUMANOS, nunca bots) + Conquistas (registro
puro, Seção 15). Trouxe 2 subsistemas NOVOS reutilizáveis por qualquer
sistema futuro (`pandora/conquistas.py`, `pandora/itens.py`), não só pro
World Boss.

- **`pandora/conquistas.py`** - catálogo FECHADO de 20 conquistas (4 por
  contagem de vitórias, 10 por tipo de Boss, 6 situacionais), registro
  guild-scoped (`colecao_conquistas`, PK guild+user+conquista - mesmo
  critério guild-scoped de tudo mais no ecossistema, "conquistas da conta"
  interpretado como "da conta NESSE servidor"). `conceder()` é idempotente
  (`INSERT OR IGNORE`, devolve se era nova) - seguro chamar toda vitória
  mesmo pra condições por contagem (Caçador/Veterano/Lenda da Caçada).
- **`pandora/itens.py`** - catálogo FECHADO de 7 itens consumíveis
  (Proteção/Revanche/Chave da Torre/Upgrade de Construção/Chamado/Roll
  Permanente/Claim Permanente), inventário genérico (`colecao_
  inventario`) + rolagem de drop raro (15% de chance por vitória,
  pesos por item - Roll/Claim Permanente são os mais raros de propósito)
  + compra na Loja normal (`comprar_item`, mesmos preços/itens do drop).
  Cada "usar item" de verdade mora no sistema que ele afeta:
  - **🛡️ Proteção** (`db.aplicar_protecao_pvp`/`esta_protegida_pvp`) -
    `batalha.iniciar_desafio` confere isso ANTES de aceitar um desafio
    (mesmo nível de proteção que Soulmate, mas via item em vez de
    progressão).
  - **⚔️ Revanche** (`colecao_batalha_personagens_perdidas`) - toda
    vitória do desafiante REGISTRA a personagem como perdida pelo
    defensor (`_finalizar_vitoria_desafiante`); se o jogador que venceu
    JÁ tinha perdido essa mesma personagem antes, marca como recuperada
    automaticamente (fecha o ciclo, com ou sem Revanche de verdade -
    qualquer vitória de volta conta). `batalha.iniciar_desafio_com_
    revanche` reaproveita `iniciar_desafio` com um parâmetro interno
    (`_ignorar_cooldown_e_limite`) que pula SÓ o cooldown de 24h e o
    limite diário - todo o resto da validação (Soulmate/Proteção/aposta/
    Party completa) continua valendo, "ainda precisa disputar através
    das regras da batalha".
  - **🗝️ Chave da Torre** (`colecao_torre_chave_ativa`, flag por
    jogador) - `torre._calcular_contexto` ganhou `ignorar_restricao`
    (usado por `preview_andar` E `tentar_andar`); consumida só em
    `tentar_andar` (tentativa REAL), nunca em `preview_andar` - "a Chave
    paga pelo direito de tentar sem a restrição, não pelo resultado".
  - **🏗️ Upgrade de Construção** (`colecao_construcoes`, nível por
    guild+user+área) - `cidade._poder_area` ganhou `multiplicador_
    construcao` (1 + 10%×nível), aplicado nos DOIS lugares que calculam
    Poder (`coletar_producao_pendente` E `atualizar_snapshot_bonus`, via
    um helper `_multiplicador_construcao` novo) - áreas batem 1:1 com
    `cidade.FUNCOES_CIDADE` (Militar/Saúde/Cultura/Administração/
    Comércio/Arcano), nenhuma tradução de nome necessária.
  - **📯 Chamado** (`colecao_worldboss_proximo_forcado`, 1 boss forçado
    por guild) - `worldboss.iniciar_evento` consome isso ANTES do sorteio
    aleatório (`db.consumir_worldboss_forcado` já apaga a linha ao ler,
    nunca aplica 2x).
  - **🎲/💎 Roll/Claim Permanente** - 2 colunas novas em `colecao_
    estado_jogador` (`bonus_rolls_permanente_drop`/`bonus_claims_
    permanente_drop`), SEPARADAS do upgrade pago da Loja (`nivel_
    upgrade_rolls`/`nivel_upgrade_claims`) - `gacha._limite_rolls_atual`
    e o cálculo de `limite_claims` em `_processar_claim` somam esse
    bônus junto. Mesmo limite (5, primeiro palpite) vale pra drop E
    compra juntos (`itens.LIMITE_ROLL_PERMANENTE`/`LIMITE_CLAIM_
    PERMANENTE`) - um drop que ultrapassaria o teto vira WiShards de
    consolação em vez de simplesmente descartado.
- **Granting da 5★ garantida reaproveita o motor de roll/claim de
  verdade** (`worldboss.SchedulerWorldBoss._conceder_5_estrela`) - sorteia
  entre 5★ sem dono OU já do próprio jogador (nunca de outro jogador, pra
  a recompensa "garantida" nunca virar prêmio de terceiro), resolve via
  `gacha._resolver_resultado` (mesma função de um roll normal - decide
  livre/reencontro sozinha) e, se "livre", credita de verdade via
  `gacha._claim_sem_cooldown` (mesmo núcleo do claim humano/auto-
  colecionador - Seção 2: "funciona exatamente como se tivesse obtido
  através do fluxo normal"). Precisa de um `discord.Member` de verdade
  (embed de confirmação usa `.mention`/`.display_name`) - só roda dentro
  do scheduler (que tem acesso a `client.get_guild(...).get_member(...)`),
  nunca no motor puro de `pandora.worldboss`.
- **Entrega por DM + resumo público** - recompensa individual (Seção 17,
  claramente pessoal, "Suas recompensas") vai por DM pro jogador; um
  resumo agregado (quem ganhou o quê, condensado) vai no canal do evento.
  Notificação de Nova Conquista também por DM, mensagem separada da
  recompensa.
- **Validado numa CÓPIA da produção** (nunca a produção, nenhum clique
  real no Discord ainda): compra de item + limite de Roll/Claim
  Permanente respeitado (recusa a 6ª compra), bônus refletido em `gacha.
  _limite_rolls_atual`, Proteção bloqueando um desafio de verdade,
  Upgrade de Construção aumentando o multiplicador de Poder da Cidade
  (Nível 1 = ×1,10 confirmado), Chamado forçando o Boss do próximo evento
  E sendo consumido (não aplica 2x), Chave da Torre ativando, as 20
  conquistas concedidas idempotentemente, Revanche ignorando o limite
  diário de defesas (desafio normal rejeitado no limite, desafio com
  Revanche aceito), e a 5★ garantida creditada de verdade via um mock de
  `discord.Member` chamando o MESMO `gacha._claim_sem_cooldown` de um
  claim humano.

## World Boss: correção de ordem do turno e recalibração (2026-09-02)

Achado em produção de verdade (não simulação) - print real de um evento
contra o 🌑 Devorador do Abismo, time de 3 jogadores (1 DPS/1 Tank/1
Support, CP 26.297/categoria): o time morreu no turno 1 (Boss ATK 13.500
> HP do time 12.880). Duas causas distintas em `pandora/worldboss.py`:

- **Bug de ordem contra a própria Seção 18** de
  `PANDORA_worldboss_evento_cooperativo.md` ("5. Time recebe dano → 6.
  Support aplica cura → 7. Estado final é calculado") - o código antigo
  checava derrota logo depois do ataque do Boss, ANTES de aplicar a cura -
  Support nunca conseguia evitar uma morte, justamente quando mais
  importava. **Corrigido pra dano líquido por turno** (pedido do usuário:
  "dano recebido = dano causado - dano curado") - `atk_efetivo` e `cura`
  são calculados primeiro (com todos os modificadores de mecânica de cada
  um), só então `dano_liquido = atk_efetivo - cura` muda o HP do time de
  uma vez, e o cheque de derrota roda depois disso.
- **`DANO_BASE`/`HP_BASE`/`CURA_BASE` descalibrados** (Seção 14 pedia
  calibração com dados reais, nunca tinha acontecido - HP_BASE=6000 já
  nascia menor que o ATK de QUALQUER Boss do catálogo, 12-17 mil).
  Recalibrados (10.000→14.000 / 6.000→45.000 / 500→7.500) via simulação
  do motor real (`executar_turno` chamado direto, 60 combates por Boss,
  script descartável) usando o CP observado na print (26.297/categoria):
  **87% de vitória agregada** nos 10 Bosses - 8 deles em 70-100%, ☠️
  Senhor da Morte (Ceifar, dano periódico direto) em 70% como degrau
  intermediário, 🐉 Dragão Ancião (Enfurecer, ATK +10%/turno composto) em
  ~0% - não é bug: a mecânica dele favorece dano MUITO mais rápido do que
  esse time entrega, exatamente o "efeito do Boss como diferencial real de
  dificuldade" pedido pelo usuário, em vez de tunar HP/ATK Boss a Boss (o
  catálogo `CATALOGO_BOSSES` não mudou nenhum valor).
- **Variação leve por turno** (`VARIACAO_TURNO = 0.10`, novo) - ±10% tanto
  no dano causado pelo time quanto no ATK do Boss a cada turno, pra o
  combate não ser 100% determinístico turno a turno (pedido do usuário).
- **Validado só via simulação do motor** (`executar_turno` chamado direto
  com um `evento` sintético, nunca um evento real no scheduler/Discord) -
  continua pendente confirmar ao vivo se a taxa de vitória se sustenta com
  composições reais (jogadores nem sempre concentram CP numa categoria só
  como no teste) e se o ritmo de ~15-25 turnos fica bom de acompanhar no
  canal (ver `TODO.md`).

## World Boss: 5 dificuldades independentes + CP recomendado por simulação (2026-09-02)

Pedido do usuário depois da recalibração acima, em 2 rodadas de correção
sobre a 1ª tentativa (registro do erro fica aqui de propósito, pra não
repetir):

1. **1ª tentativa (errada)**: dei a cada um dos 10 Bosses uma dificuldade
   FIXA no catálogo (Dragão Ancião sempre "difícil", etc.). Corrigido pelo
   usuário: **"cada boss pode variar entre todas as dificuldades"** -
   dificuldade não é propriedade do Boss, é sorteada à parte no spawn,
   independente de qual dos 10 saiu. E não existia nenhuma dificuldade
   nomeada antes desta sessão (só hp/atk fixos por Boss) - pedido final:
   **"mantém os status atual como difícil"** (os números originais do
   catálogo viram a base "Difícil") **"e tenha 5 dificuldades Facil Normal
   Dificil Elite Pesadelo"**.
2. **"CP recomendado"" também estava errado** - a 1ª versão calculava
   `personagem_mais_forte_do_servidor × multiplicador`. Achado do usuário:
   **"se vc ta multiplicando em cima do personagem mais forte, vai ser
   impossivel bater o recomendado"** - confunde CP de UMA personagem com o
   CP AGREGADO de uma categoria inteira no combate; numa categoria com
   poucos jogadores fortes, o agregado nunca passa de ~1× o CP do
   personagem mais forte sozinho, então multiplicadores >1× viravam metas
   inatingíveis pra servidores pequenos. `torre.personagem_mais_forte_do_
   guild`/`db.donos_do_guild` (da 1ª tentativa) foram REMOVIDAS - não sobrou
   nenhum uso pra elas depois da correção.

**Desenho final**:
- **`DIFICULDADES`** (`worldboss.py`) - 5 tiers (🟢 Fácil/🔵 Normal/🟠
  Difícil/🔴 Elite/🟣 Pesadelo), cada um só um multiplicador de HP/ATK
  aplicado sobre o hp/atk BASE do Boss sorteado (`CATALOGO_BOSSES`
  continua com só 1 número por Boss, o "Difícil" original) - Difícil =
  1,0× (pedido: "mantém os status atual"), os outros escalam pra cima/
  baixo (0,45× / 0,70× / 1,20× / 1,50×, calibrados simulando os 10 Bosses
  no CP real observado: Fácil/Normal ficam vitória garantida nesse CP,
  Difícil reproduz a mesma distribuição de antes (87% agregado, Enfurecer
  sendo a exceção dura), Elite/Pesadelo sobem bem além do que esse CP
  aguenta - teto de propósito).
- **`iniciar_evento`** sorteia o TIPO do Boss e a DIFICULDADE em 2 sorteios
  independentes (`random.choice` cada um) - qualquer um dos 10 Bosses pode
  sair em qualquer uma das 5 dificuldades, 50 combinações possíveis. Item
  📯 Chamado continua só forçando o TIPO, dificuldade sempre sorteada.
- **`worldboss.cp_recomendado(boss_tipo, dificuldade)`** - REESCRITA
  (2026-09-02, correção acima): busca binária (~20 rodadas) contra o motor
  de combate REAL (`_taxa_vitoria_simulada`, `executar_turno` chamado
  direto com um evento sintético) achando o CP-por-categoria que bate 65%
  de taxa de vitória contra ESSE Boss NESSA dificuldade - nunca mais
  baseado no personagem mais forte de ninguém, sempre um valor que a
  PRÓPRIA simulação prova ser alcançável. ~0,1-0,6s por chamada (aceitável,
  roda 1x por spawn, 4x/dia).
- **Snapshot no spawn, nunca recalculado** (mesmo espírito do CP congelado
  dos participantes, Seção 7) - `dificuldade`/`cp_recomendado` gravados 1x
  em `colecao_worldboss_eventos` (2 colunas novas, migração aditiva
  guardada por `PRAGMA table_info`).
- **Exibido em `embed_aparicao` e `embed_status`** (fase de inscrições) -
  campo "🎯 Dificuldade: {tier}" com o CP recomendado por categoria.
- **Validado**: migração + `iniciar_evento` + os 2 embeds rodados contra
  uma CÓPIA do `pandora.db` real (nunca produção) - conferido que o hp/atk
  do evento batem com base×multiplicador da dificuldade sorteada, e que
  `cp_recomendado` cresce monoticamente Fácil→Pesadelo pro mesmo Boss
  (ex.: Devorador do Abismo: 0 / 4.000 / 23.500 / 45.000 / 90.500). Nunca
  clicado de verdade no Discord ainda (mesma pendência da seção anterior).

## Perfil redesenhado + Séries Favoritas (2026-09-02)

Pedido do usuário: "Vamos remover aquelas séries que vc pos no perfil,
deixar lá informações importantes apenas do jogador" + uma sugestão
externa colada e endossada ("acho bem melhor") - resumo do jogador virou
compacto, listar TODA série tocada virou uma escolha deliberada (Séries
Favoritas) com bônus de CP de verdade em cima.

- **`/perfil` (`paineis._montar_embed_perfil`)** - resumo do topo
  (personagens/nível máximo/afinidade máxima/soulmates, `db.resumo_
  perfil_geral`) + tabela por raridade 1★-5★ (`db.resumo_perfil_
  raridade`, 1 query só via `GROUP BY p.raridade`, sempre com percentual
  junto da contagem - "310 personagens no nível máximo isoladamente
  começa a dizer pouco") + Séries Favoritas + Conquistas/Torre/
  Soulstones (`db.conquistas_do_jogador`/`db.andar_atual_torre`/`db.
  saldo_soulstone`, já existiam). `db.progresso_por_serie` (listava TODA
  série já tocada, até 25) foi REMOVIDA - não sobrou nenhum uso.
- **Séries Favoritas (`pandora/series_favoritas.py`, módulo novo)** - até
  `SLOTS_MAXIMO` (25 desde 2026-09-03 - era 10 = 5 base + 5 upgrades,
  subiu pra 5 base + 20 upgrades pagos, `db.PRECOS_UPGRADE_SLOT_SERIE_
  FAVORITA`, mesmo padrão de preço escalonado do upgrade de rolls/claims
  - 25 é o TETO de opções de 1 único `discord.ui.Select`, não arbitrário,
  ver "Navegador de Série + teto de 25" mais abaixo) séries escolhidas
  pelo jogador, cada uma com 3 marcos
  INDEPENDENTES calculados por `db.estatisticas_series` (1 query
  agregada, só das séries favoritadas, nunca escaneia o catálogo
  inteiro):
  - 📚 **Coleção Completa** - possui 100% do catálogo daquela série.
  - ⭐ **Maestria Completa** - toda personagem QUE TEM daquela série está
    no nível máximo (`db.NIVEL_MAXIMO_PERSONAGEM`).
  - 💕 **Soulbond Completo** - toda personagem que tem daquela série é
    Soulmate.
  - Bônus CUMULATIVO (+5%/+5%/+10%, até +20%) - só sobre personagens
    DAQUELA série (nunca CP global, pedido explícito do usuário: "isso
    inevitavelmente vira outra fonte enorme de power creep").
- **Snapshot pré-calculado** (`colecao_series_favoritas_bonus`, mesmo
  padrão de `cidade.atualizar_snapshot_bonus`) - calcular completude é
  caro (varre a coleção filtrada por série), nunca roda no caminho quente.
  `series_favoritas.recalcular_bonus` é chamado depois de trocar uma
  série favorita E nos MESMOS 8 pontos de `paineis.py` que já chamavam
  `cidade.atualizar_snapshot_bonus` (claim/nível/afinidade/divórcio/
  merge/Party) - reaproveita o gatilho existente em vez de duplicar a
  lista.
- **`torre.power_personagem` ganhou `bonus_series`** (4º item novo de
  `torre._contexto_lote`, leitura barata de `db.bonus_series_favoritas`) -
  aplicado como mais um multiplicador (`× (1 + bonus_serie)`), mesmo
  princípio do bônus global/de classe já existentes. Os 7 lugares que
  desempacotavam `_contexto_lote` em 3 valores (`batalha.py`, `cidade.py`,
  `paineis.py` ×2, `torre.py` ×2, `worldboss.py`) foram atualizados pros
  4 - bônus de série passa a valer em QUALQUER cálculo de CP (Torre,
  Batalha, World Boss, Cidade), não só no Perfil.
- ~~Cooldown de 7 dias pra trocar um slot já ocupado~~ **REMOVIDO
  (2026-09-03)** - existia (`db.COOLDOWN_DIAS_TROCA_SERIE_FAVORITA`,
  pedido do usuário: "trocar uma Série Favorita não pode ser
  instantaneamente explorável... vou usar Megumin -> favorito KonoSuba
  -> ganho +20% -> luto -> tiro KonoSuba"), mas o próprio usuário pediu
  pra tirar depois de esbarrar nele na prática ("remove esse bloqueio
  Esse slot só pode trocar de novo em 7 dia(s)") - `db.definir_serie_
  favorita` não checa mais `bloqueado_ate`, sempre grava `None` (coluna
  mantida na tabela, sem migração destrutiva). Trocar Série Favorita
  volta a ser sempre instantâneo, sem limite de frequência.
- **Busca de série case-insensitive** (`db.encontrar_serie_por_nome`,
  resolve pra grafia canônica do catálogo) com sugestões por prefixo
  (`db.series_do_catalogo`) quando o nome digitado não bate com nada.
- **Validado**: migração + fluxo completo (1ª escolha instantânea, 2ª
  tentativa no MESMO slot bloqueada com a data certa, slot DIFERENTE
  ainda instantâneo, bônus de +20% aplicado de verdade em `power_
  personagem` num teste sintético, embed do `/perfil` renderizado)
  rodados contra uma CÓPIA do `pandora.db` real (nunca produção). Nunca
  clicado de verdade no Discord ainda.
- **Fora de escopo desta leva** (ver TODO.md): abrir uma Série Favorita
  pra ver a lista completa de personagens faltando - hoje só mostra os
  números agregados.

## "GAIA nao respondeu a tempo" ao confirmar Batalha (2026-09-02)

Achado do usuário testando ao vivo: confirmar um desafio de Batalha 5x5
contra um bot (Ai Hayasaka/Artoria Pendragon, 10.000 WiShards em risco)
travava nesse erro genérico - mesma classe de bug já vista antes no
projeto (interação do Discord expira em 3s, qualquer coisa bloqueante
ANTES do primeiro ack derruba o token).

- **Causa**: os 3 fluxos de confirmação de Batalha (`paineis.py`) chamavam
  `batalha.iniciar_desafio`/`montar_defesa`/`iniciar_desafio_com_revanche`
  via `asyncio.to_thread` ANTES de qualquer `response.defer()`/
  `edit_message` - o caso mais grave era desafiar um BOT: 2 chamadas
  `to_thread` em sequência (`iniciar_desafio` + `montar_defesa`) rodavam
  as DUAS antes do primeiro ack. `_resolver_e_revelar` já documentava a
  precondição no próprio docstring ("interaction já precisa estar
  deferida/respondida") - só quem chamava não cumpria.
- **Corrigido nos 3**: `Desafiar` (`_personagem_escolhida` -> `_confirmar`,
  inclusive o ramo "enfrentar bot"), `Montar Defesa`
  (`ViewBatalhaHub._montar_defesa` -> `_apos_formacao`), `Revanche`
  (`_apos_formacao` da Revanche) - `response.defer()` sempre a PRIMEIRA
  linha da função, antes de qualquer `to_thread`; as respostas
  subsequentes (erro ou sucesso) viraram `edit_original_response` (a
  interação já foi consumida pelo `defer()`, `response.edit_message` não
  serve mais).
- **Não validado ao vivo ainda** (só revisão de código + syntax/import
  check) - o achado original foi reportado em produção, então confirmar
  isso contra um bot de verdade é prioridade alta.

## Auditoria de corrida claim/merge + correção do Merge (2026-09-02)

Pedido do usuário depois de revisar o Merge novo: "Não pode de forma
alguma deixar 2 jogadores terem a msm personagem. Antes do claim/merge
tem q ter uma validação rigida, so de fato realizar todas as acoes apos o
claim" + "N permita fazer merge de personagens no grupo".

- **Auditoria dos 3 lugares que chamam `db.reivindicar`** (INSERT
  atômico, `ON CONFLICT(guild_id, personagem_id) DO NOTHING`, PK
  `(guild_id, personagem_id)` - estruturalmente impossível 2 linhas pro
  mesmo personagem):
  - `gacha._processar_claim`/`_claim_sem_cooldown` - já corretos (checa
    `if not db.reivindicar(...)` ANTES de qualquer recompensa/efeito).
  - `db.comprar_personagem` - já correto (debita, tenta reivindicar,
    reembolsa se perder a corrida).
  - `economia.executar_merge` (Merge novo) - **TINHA o bug**: removia as
    5 sacrificadas ANTES de reivindicar a escolhida, sem checar o
    resultado - se perdesse a corrida (ou se uma das 5 entrasse na Party
    no meio do caminho, a checagem de Party só rodava na 1ª etapa),
    ficava com as 5 removidas E nada em troca. Corrigido: reivindicar
    primeiro, checar sucesso, só então remover as 5 - e revalidar Party
    de novo na 2ª etapa (`validar_merge` bloqueia na 1ª, mas o jogador
    escolhe o alvo numa interação separada depois, dando tempo de mudar a
    Party no meio).
  - `batalha._finalizar_vitoria_desafiante` usa `db.transferir_
    personagem` (DELETE+INSERT pro MESMO personagem_id, não uma corrida
    por um personagem LIVRE) - fora do escopo dessa auditoria (não hà
    "2 pretendentes pra 1 vaga livre" nesse caso, a personagem já tem
    dono conhecido no início da Batalha).
- **Validado** (3 cenários: escolhida reivindicada por outra pessoa no
  meio do Merge, uma das 5 entrando na Party no meio do Merge, fluxo
  normal) contra uma CÓPIA do `pandora.db` real - nos 2 cenários de erro,
  as 5 sacrificadas continuam do jogador (antes seriam perdidas).
- **Desafio de Batalha travado cancelado** (2026-09-02, pedido do
  usuário: "Desfaz esse desafio q ta aberto, foi de antes das
  melhorias") - `id=1`, Ai Hayasaka (#3977), criado 2026-09-01 antes das
  melhorias de Batalha por categoria, `aguardando_defensor` (não era bug -
  "enfrentar bot" só resolve na hora quando o alvo É um bot de verdade,
  `alvo.bot`; esse desafio provava por construção que o defensor era
  humano, já que nunca teria ficado nesse status se fosse bot). Cancelado
  direto no `pandora.db` de PRODUÇÃO via `db.cancelar_desafio_batalha(1)`
  (sem reembolso necessário - nada tinha sido debitado na criação).

## Merge vira escolha do jogador na mesma raridade (2026-09-02)

Pedido do usuário: "Muda funcao do merge, ele vai deixar trocar 5 da msm
raridade por 1 da msm raridade disponivel, a escolha".

- **`economia.validar_merge`** (era `executar_merge`) - só valida as 5
  personagens a sacrificar (distintas/donas/mesma raridade/fora da Party/
  confirmação de Afinidade>1), devolve a raridade em vez de escolher um
  alvo sozinha. O bloqueio de `raridade >= 5` ("não têm pra onde subir")
  SUMIU - deixou de fazer sentido, o alvo agora é da MESMA raridade, então
  5⭐ também mergeia (pra outra 5⭐).
- **`economia.executar_merge`** (assinatura nova: `ids, escolha_id`) - só
  executa depois que o jogador já escolheu. Revalida o essencial de novo
  (corrida: a escolhida pode ter sido reivindicada por outra pessoa entre
  a lista aparecer e o clique).
- **`paineis._ViewEscolherMergeAlvo`** (nova) - 2º passo da UI, lista até
  25 personagens LIVRES da mesma raridade (`db.personagens_livres_por_
  raridade`, mesma fonte que a Loja usa pra "Comprar") num Select -
  `_merge_selecionado` chama `validar_merge`, monta essa lista, só chama
  `executar_merge` quando o jogador escolhe.
- **Validado**: fluxo completo (sacrificar 5× 5⭐, listar livres da mesma
  raridade, escolher, confirmar que as 5 sumiram e a escolhida é do
  jogador) contra uma CÓPIA do `pandora.db` real. Nunca clicado de
  verdade no Discord ainda.

## Recompensa Diária escala com Progressão + item garantido (2026-09-02)

Pedido do usuário: "Recompensa diaria multiplicada os wishards pelo nivel
da progressao. e da 1 item raro".

- **`db.reivindicar_diaria_com_recompensa`** - WiShards deixam de ser
  `RECOMPENSA_DIARIA_WISHARDS` fixo (150) e viram `150 × nível de
  Progressão` (`db.progressao_conta(...)["nivel"]`, SEM TETO - "a
  personagem possui um limite de desenvolvimento. A conta não", mesmo
  princípio já usado no bônus de CP global) - devolve `(ok, novo_saldo,
  wishards_creditados)` agora (3-tupla, era 2 - único chamador,
  `paineis._diaria`, já atualizado).
- **`itens.sortear_item_diario()`** (novo) - reaproveita o MESMO catálogo/
  pesos do drop raro do World Boss (`PESOS_DROP_RARO`), mas sem o portão
  de `CHANCE_DROP_RARO` (15%) - todo resgate da Diária dá exatamente 1
  item, nunca `None`. `paineis._diaria` chama isso + `itens.
  conceder_item_drop` na sequência, mesmo padrão de concessão que o
  World Boss já usava.
- **Validado** numa CÓPIA do `pandora.db` real: nível de Progressão 17 ->
  2.550 WiShards, nível simulado 7 -> 1.050 (bate com `150 × nível` nos
  dois casos), 2ª tentativa no mesmo dia continua bloqueada, item sorteado
  e concedido de verdade via `itens.conceder_item_drop`. Nunca clicado de
  verdade no Discord ainda.

## Auto-Defesa na Batalha + Morte Súbita removida (2026-09-02)

Pedido do usuário: "coloca um modo defesa automatica, ele vai considerar
cada escolha do desafiante, e montar sua escolha com base naq venceria
ela, se tem 5 papel, ele pega 5 tesouras. E distribui em ordem aleatoria.
Se o desafiado n responder em 10min, considera essa defesa automatica.
Bots respondem na hr com essa logica. É possivel deixar configurado p
players tbm" - veio logo depois de reportar um bug real de Morte Súbita
(1x2 caindo em empate à toa) e pedir a remoção completa da mecânica (ver
CHANGELOG.md, "Morte Súbita removida + bug real de empate").

- **`batalha.defesa_automatica(ordem_desafiante)`** (nova) - pro Jokenpô
  puro do jogo (`_VENCE_DE`: DPS>Support>Tank>DPS), monta o dict inverso
  (`vencido -> vencedor`) e mapeia cada categoria da ordem do desafiante
  pra quem vence ELA - se o desafiante põe 5× DPS, a defesa é 5× Tank,
  sempre. Só a ORDEM das 5 escolhas é embaralhada (`random.shuffle`) -
  a categoria de cada posição nunca é aleatória, é sempre a que vence.
  `defesa_automatica_para_desafio(desafio_id)` busca a `ordem_desafiante`
  salva e delega - substitui a antiga `formacao_aleatoria` (verdadeiramente
  aleatória, sem contra-escolha nenhuma) em TODO lugar que resolvia contra
  bot instantaneamente.
- **3 gatilhos pro mesmo counter-pick, não 3 mecânicas diferentes**:
  1. **Bot** (`alvo.bot`) - já existia (resolvia na hora), só trocou
     `formacao_aleatoria` por `defesa_automatica_para_desafio`.
  2. **Jogador com a opção ligada** - `colecao_estado_jogador.
     auto_defesa_batalha_ativa` (coluna nova, migração guardada,
     `db.auto_defesa_batalha_ativa`/`definir_auto_defesa_batalha`, mesmo
     padrão INSERT...ON CONFLICT de outros toggles por jogador) - botão
     novo "Auto-Defesa: Ligada/Desligada" no `ViewBatalhaHub` (sempre
     visível, não só quando há desafio pendente). Os 3 pontos que já
     resolviam contra bot (`_confirmar` do Desafiar, `_montar_defesa`,
     Revanche) ganharam a MESMA condição extra: `alvo.bot or
     db.auto_defesa_batalha_ativa(guild_id, alvo.id)` - resolve na hora
     nos 2 casos, sem distinguir bot de humano com a opção ligada.
  3. **Timeout de 10 minutos sem resposta** - `paineis.SchedulerBatalha`
     (novo, `discord.ext.tasks.loop(seconds=30)`, mesmo padrão de
     `SchedulerWorldBoss`: instanciado só no `on_ready` do papel
     "completo", 1 tick de 30s varrendo TODOS os guilds do client) - a
     cada tick, busca desafios `aguardando_defensor` com mais de
     `LIMITE_MINUTOS_AUTO_DEFESA = 10` minutos (`db.
     desafios_batalha_expirados`, já existia, só não tinha consumidor
     desde que `cancelar_expirados` foi removido) e resolve cada um via
     `defesa_automatica_para_desafio` -> `montar_defesa` ->
     `resolver_rodadas` -> `concluir_batalha`, anunciando o resultado com
     `canal.send` (não edita a mensagem original - ninguém está olhando
     a interação depois de 10 minutos).
- **`colecao_batalha_desafios.canal_id`** (coluna nova, migração
  guardada) - o `SchedulerBatalha` precisa saber ONDE anunciar um desafio
  que ninguém respondeu; guardado desde a criação (`iniciar_desafio`/
  `iniciar_desafio_com_revanche`, `canal_id=None` opcional - `paineis.py`
  sempre passa o canal real da interação).
- **Efeito colateral do teste**: o desafio de teste esbarrou no desafio
  #3 real (Aoi Asahina) ainda preso em `status='morte_subita'` - resolvido
  manualmente antes de testar de verdade (ver CHANGELOG.md).
- **Validado** contra uma cópia do `pandora.db` real: toggle liga/
  desliga, criação de desafio com `canal_id` salvo corretamente,
  `defesa_automatica_para_desafio` retornando o counter-pick certo pra
  cada posição do desafiante (`['DPS','DPS','DPS','Tank','Tank']` ->
  `['Tank','Tank','Support','Tank','Support']`, ordem embaralhada mas
  cada posição vencendo a original), `montar_defesa`/`resolver_rodadas`/
  `concluir_batalha` fim a fim fechando a batalha (`status='concluida'`).
  **Não validado**: o `SchedulerBatalha` rodando de verdade por 10
  minutos reais contra um desafio pendente (só as funções que ele chama
  foram testadas direto, o loop de 30s em si nunca foi observado vencendo
  o prazo ao vivo).

## "🔍 Personagem" - navegação por posição global (2026-09-02)

Pedido do usuário comparando com o Mudae: "consegue passar bem mais de 25
profiles... quero passar de 25 e ter registro de posição qnd uso o
comando p ver personagem... Além das setas de personagem anterior/
próxima, adicione botões para pular diretamente para o bloco anterior ou
seguinte de 25 posições. Também adicione um botão 🔎 Buscar que abra um
modal do Discord permitindo informar o nome da personagem ou uma posição
específica". Reescrita completa de `_ViewNivel` - a versão de 2026-09-01
(`_candidatos` crescendo sob demanda, 25 em 25, nunca encolhendo) tinha um
bug real (◀️▶️ travava exatamente no item 25, corrigido antes desta
reescrita) e não dava pra pular DIRETO pra uma posição arbitrária sem
passar por todas as intermediárias.

- **Modelo novo**: a view guarda só `_indice_global` (posição 0-indexed),
  `_total` (`db.contar_colecao_do_usuario`) e `_bloco` (até 25 personagens,
  `db.colecao_do_usuario_paginada(guild_id, user_id, offset, 25)`) - o
  bloco que CONTÉM a posição atual. Pular pra qualquer posição (2750,
  50000...) é sempre 1 SELECT por `OFFSET`/`LIMIT`, nunca precisa carregar
  a coleção inteira nem iterar posição por posição. `_ir_para(indice_
  global)` é o núcleo ÚNICO de toda navegação (setas/bloco/busca/select) -
  clampa contra o total, só troca de bloco (refaz o SELECT) quando a nova
  posição realmente cai fora do bloco já carregado, e sempre recalcula
  `_total` do zero (COUNT(*) barato) pra cobrir a coleção ter mudado de
  tamanho (troca/claim/divórcio) desde a última navegação.
- **Select "🔄 Trocar de personagem"** sempre reflete o BLOCO de 25 que
  contém a posição atual (posições 1-25 -> bloco 1-25, 26-50 -> 26-50, 93
  -> 76-100, 101 -> 101-125 - virada exata de bloco) - reconstruído
  (`_atualizar_select_options`) toda vez que `_ir_para` troca de bloco,
  com a posição absoluta no rótulo de cada opção ("2750. Nome") e a opção
  atual marcada `default=True`.
- **Navegação**: "◀️"/"▶️" (já existiam) andam 1 posição; "⏮️"/"⏭️" (novos)
  pulam um bloco INTEIRO de 25, sempre pro INÍCIO do bloco vizinho (mesmo
  padrão de página de `consulta.ViewColecao` - nunca desloca por 25 a
  partir da posição atual, vira pro primeiro item da página vizinha).
- **"🔎 Buscar"** (novo botão) abre `_ModalBuscarPosicaoOuNome` (1 campo) -
  texto 100% dígito vira posição direta (`2750` abre a posição 2750);
  qualquer outra coisa vira busca por NOME (`_posicao_por_nome`, usa
  `consulta.buscar_por_nome` - MESMO algoritmo de sempre, substring
  primeiro/similaridade depois - contra a coleção INTEIRA carregada via
  `db.colecao_do_usuario_paginada(..., 0, 1_000_000)`, mesma ordem exata
  da navegação por posição, crítico pra bater com onde as setas/blocos
  realmente chegam) - fica só com o MELHOR resultado e abre direto nele,
  sem lista intermediária pra escolher (diferente do "🔄 Trocar de
  personagem", que continua mostrando as opções do bloco). Pular além do
  total clampa pra última posição válida com um aviso inline, em vez de
  travar.
- **`_ModalBuscarPersonagem`** (Battle/Proteção, únicos callers restantes)
  perdeu os parâmetros `paginacao_lazy`/`editar_mensagem_original` (só
  "🔍 Personagem" os usava, e ele não usa mais este Modal - contrato de
  lista fechada de candidatos não se encaixa em navegação por posição).
- Validado contra uma cópia do banco real (conta com 4.764 personagens):
  posição 93 -> bloco 76-100, posição 101 -> bloco 101-125, pulo de bloco
  pro vizinho certo, pulo direto pra posição 2750, busca por nome
  ("megumin") resolvendo pra posição certa, posição muito além do total
  clampando pro fim com aviso. Nenhum clique real no Discord ainda desta
  versão.

## ⚠️ Nunca construir uma `discord.ui.View` dentro de `asyncio.to_thread` (achado 2026-09-02)

Achado real em produção, achado DIFÍCIL - o usuário reportou "GAIA não
respondeu a tempo" ao clicar em qualquer slot/"Comprar Slot" das Séries
Favoritas; um 1º fix (bug real, `str` vs `int` no dono do painel) não
resolveu; um log passo a passo (`[SERIES]`, mesmo padrão já usado na
Batalha) provou que o clique NUNCA chegava no callback - só a abertura do
painel logava, o clique em si não deixava rastro NENHUM, nem exceção.

**Causa raiz**: `_ViewSeriesFavoritas.criar` (`pandora/paineis.py`) rodava
`await asyncio.to_thread(_ViewSeriesFavoritas.criar, ...)` - construía a
View INTEIRA (`__init__` -> `discord.ui.view.BaseView.__init__`) dentro da
thread WORKER do `to_thread`, sem event loop rodando ali. `BaseView.
__init__` tenta `asyncio.get_running_loop()` pra criar o `Future` interno
`__stopped` (usado pelo `wait()`/timeout/dispatch da View); sem loop
rodando, cai no `except RuntimeError` e deixa `__stopped = None` PRA
SEMPRE (nunca mais corrigido depois, mesmo quando a View passa a ser
usada de verdade na thread principal). `discord.ui.View._dispatch_item` -
o método do PRÓPRIO discord.py que roteia TODO clique de botão/select pro
callback certo - começa com:
```python
def _dispatch_item(self, item, interaction):
    if self.__stopped is None or self.__stopped.done():
        return None
    ...
```
Com `__stopped=None`, isso devolve `None` IMEDIATAMENTE - o callback do
item NUNCA é chamado, nenhuma exceção é levantada, nada é logado. Do
ponto de vista de quem clicou, a interação simplesmente nunca é
respondida ("app não respondeu") - sintoma IDÊNTICO a um timeout de 3s
comum, mas a causa é estrutural, não de performance.

**Prova** (reproduzida e depois validada corrigida, chamando o mecanismo
REAL do discord.py direto, sem mock): `View._dispatch_item(item, fake_
interaction)` devolvia `None` antes do fix; depois do fix, devolve uma
`Task` de verdade que executa o callback até o fim.

**Fix**: NUNCA construir o objeto View (nem chamar `__init__` de uma
View, direto ou indireto) dentro de `asyncio.to_thread` - só o FETCH DE
DADO caro pode rodar lá. Padrão certo (`_ViewSeriesFavoritas.criar`
depois do fix):
```python
@classmethod
async def criar(cls, guild_id, user_id):
    dados = await asyncio.to_thread(fetch_caro, guild_id, user_id)  # thread OK
    return cls(guild_id, user_id, dados)  # construção na THREAD PRINCIPAL

def __init__(self, guild_id, user_id, dados):
    super().__init__(timeout=300)  # BaseView.__init__ roda com loop de verdade
    ...
```
Mesma regra vale pra RECONSTRUIR itens de uma View já existente
(`_montar`/`_montar_botoes`, chamado de novo depois de uma mudança) -
isso É seguro chamar direto (sem `to_thread`) de dentro de um callback de
interação já rodando na thread principal, contanto que a View em si
tenha sido CRIADA na thread principal originalmente; só a CRIAÇÃO
(`__init__`) é sensível ao loop, não `add_item`/`clear_items` depois.

**Auditoria feita**: `grep` por `asyncio.to_thread(.*View` e `to_thread(.*
\.criar` em todo `pandora/*.py` - `_ViewSeriesFavoritas` era o ÚNICO
lugar com esse padrão. Nenhum outro sistema afetado, mas vale MEMORIZAR
essa regra pra qualquer código futuro que combine "buscar dado caro" +
"construir View" numa função só.

## Navegador de Série Favorita + teto de 25 slots (2026-09-03)

Pedido do usuário: "quero colocar um dropdown na tela de series, com a
lista de series q favoritei. E qnd seleciono uma serie, ele abre os
personagens, igual na tela de personagens, soq com um botao de comprar
tbm, q funcionaria da msm forma d como é na loja, seria so uma forma
rapida", depois "Nos personagens das series favoritas, permita favoritar
tbm. E aumente o limite de series para 25 se conseguir".

- **`db.personagens_da_serie(guild_id, serie, permitir_nsfw)`** (nova) -
  TODO personagem ATIVO do catálogo de uma série + `dono_id` (`None` se
  livre nesse servidor, via `LEFT JOIN colecao_propriedade`).
- **`_ViewNavegarSerie`** (nova, `pandora/paineis.py`) - até 25
  personagens da série (ordenados por popularidade - "forma rápida", não
  pagina séries enormes inteiras como o "🔍 Personagem" faz pra coleção
  do usuário). Card = MESMO `consulta.embed_carta_personagem` de sempre +
  campo "Status" com 3 estados (🛒 Disponível com preço/botão Comprar
  habilitado, ✅ Já é sua com CP, 🔒 Possuída por outro jogador
  mencionando quem) + "⭐ Favoritar/Desfavoritar" (nessa época ainda só
  habilitado quando `dono_id == autor` - restrição removida em 2026-09-03
  na fusão Favoritos+Wishlist, ver seção correspondente mais abaixo).
  "🛒 Comprar" reaproveita `db.
  comprar_personagem` (MESMA função da Loja de verdade, preço/corrida
  idênticos) e atualiza o `dono_id` LOCAL na hora (sem isso o card
  continuaria mostrando "Disponível" até reabrir, e o botão Favoritar
  não liberaria no mesmo clique). `criar()` segue o MESMO padrão de
  fábrica assíncrona de `_ViewSeriesFavoritas` (fetch caro em `to_thread`,
  construção da View de volta na thread principal - ver seção acima).
- **Entrada**: select "🎬 Navegar por uma Série Favorita..." novo no
  painel "❤️ Séries Favoritas" (só aparece com pelo menos 1 slot
  ocupado) - `value=str(indice)` (nunca o nome cru da série, mesmo motivo
  do próximo item).
- **Teto de slots 10 -> 25** (`db.NIVEL_MAXIMO_UPGRADE_SLOT_SERIE_
  FAVORITA` 5 -> 20, `PRECOS_UPGRADE_SLOT_SERIE_FAVORITA` estendido
  continuando a curva de crescimento "primeiro palpite" já usada,
  chegando a 16 bilhões de WiShards no 20º nível - deliberadamente quase
  inatingível, mesmo espírito de todo teto máximo de upgrade) - **25 não
  foi escolha arbitrária**: é o TETO REAL de opções de 1 único `discord.
  ui.Select` do Discord. Isso forçou redesenhar `_ViewSeriesFavoritas`:
  os slots eram 1 BOTÃO cada (`row=(slot-1)//5`) - 25 botões sozinhos
  estourariam as 5 linhas x 5 itens do Discord, sem sobrar espaço nem
  pro "Comprar slot" nem pro "Navegar". Viraram 1 SELECT só ("✏️
  Escolher/trocar/limpar um slot...", `value=str(slot)`) - `_callback_
  slot` (fábrica por item) virou `_callback_slot_select` (1 dispatcher
  só, lê o slot escolhido do `interaction.data["values"]`).
- Validado contra uma cópia do banco real: comprar os 20 upgrades chega
  em exatamente 25 slots, o 21º é recusado; favoritar 25 séries reais e
  montar o painel resulta em só 2 linhas de select (nenhum "Comprar
  slot" quando já no teto), sem estourar limite nenhum do Discord;
  comprar uma personagem livre no navegador libera o botão Favoritar no
  mesmo clique, sem precisar reabrir; tentar favoritar uma não-possuída
  recusa com mensagem clara.

**Reescrita pra posição/bloco/busca (2026-09-03, "Faz o msm esquemas das
personagens, o skip com 25, o dropdown com base na posição. E corrige o
limite q hj é so 25")** - `_ViewNavegarSerie` tinha um teto FIXO de 25
personagens por série (top-25 por popularidade, `personagens[:25]`, sem
jeito de ver o resto - EXATAMENTE o mesmo bug já corrigido no "🔍
Personagem" em 2026-09-02, só que reintroduzido aqui de propósito como
"forma rápida"). Reescrita pra usar o MESMO modelo de `_ViewNivel`
(posição global + bloco de 25 via `OFFSET`/`LIMIT`), trocando só a fonte
de dado:
- **`db.contar_personagens_da_serie(serie, permitir_nsfw)`** (nova) -
  `COUNT(*)` puro sobre o catálogo da série.
- **`db.personagens_da_serie_paginada(guild_id, serie, permitir_nsfw,
  offset, limite=25)`** (nova) - MESMA query/ordem de `personagens_da_
  serie` (popularidade DESC - crítico, é a ordem que numera a posição),
  só com `LIMIT`/`OFFSET`.
- **`_ModalBuscarPosicaoOuNomeSerie`** (nova) - MESMO contrato de
  `_ModalBuscarPosicaoOuNome` (texto 100% dígito vira posição direta,
  resto vira busca por nome via `consulta.buscar_por_nome` contra
  `db.personagens_da_serie` inteira, MESMA ordem da paginação).
- `_ViewNavegarSerie.__init__` ganhou `⏮️`/`⏭️` (pula bloco) e "🔎
  Buscar" ao lado de `◀️`/`▶️` já existentes - row 0 (select) + row 1 (5
  botões de navegação) + row 2 (Comprar/Comprar Tudo/Favoritar) + row 3
  (Maximizar Nível/Afinidade) = 4 linhas, dentro do limite do Discord.
- Validado contra uma cópia ISOLADA do banco real (Naruto, 166
  personagens de catálogo): posição 93 -> bloco 76-100, posição 101 ->
  bloco 101-125, pulo de bloco pro vizinho certo, busca por posição 120
  e por nome "sasuke" resolvendo certo, posição além do total clampando
  pro fim - mesma bateria de testes já usada pra validar `_ViewNivel`.

## 4 correções/melhorias de 2026-09-03 (Classes, Perfil, Diária, Loja)

Ver CHANGELOG.md pro texto completo com as citações do usuário - aqui só o
"porquê" técnico de cada uma.

**Classes - Merge era o último buraco.** `gacha.revelar_classe` só roda
hoje em 4 pontos: claim normal (`_processar_claim`), claim sem cooldown
(admin/auto-colecionador, `_claim_sem_cooldown`), e compra (`gacha.
comprar_com_revelacao`, Loja/navegador de série). `economia.executar_merge`
reivindica a personagem escolhida direto via `db.reivindicar` - nunca
passou por nenhum desses 4. Corrigido chamando `await gacha.revelar_classe
(escolhida)` de dentro de `paineis._ViewEscolherMergeAlvo._escolher`
(depois do merge confirmar sucesso), não dentro de `economia.py` - evita a
reestruturação maior que exigiria tornar `economia.py` `async`/importar
`gacha` só pra isso (mesma razão que tinha deixado esse gap registrado no
TODO.md desde 2026-08-30). `db.personagens_possuidos_sem_classe`/
`contar_personagens_possuidos_sem_classe` (novas) + `/pandora_admin
validar_classes` cobrem o que ficou classless de ANTES desse fix (ou de
uma GAIA fora do ar na hora).

**Perfil - truncamento era estrutural, não um bug de tamanho.** O campo
"❤️ Séries Favoritas" juntava N séries num `"\n\n".join(linhas)[:1024]` -
um ÚNICO campo de embed tem teto de 1024 chars, bem menor que o total real
com até 25 séries (~5 linhas cada). Como o embed inteiro aceita até 25
CAMPOS com 6000 chars de soma, a correção certa nunca foi "cortar menos" -
foi trocar de "1 campo com tudo" pra "1 campo por série"
(`_montar_embed_series_favoritas`), o que também elimina o corte por
construção (nunca mais existe um único campo grande o bastante pra
estourar). Movido pra trás de um botão (`_ViewPerfil._series`, mesmo
painel do hub via `_enviar_series_favoritas` compartilhado) em vez de ficar
inline no embed principal - `_montar_embed_perfil` parou de chamar `series_
favoritas.listar` (documentado como caro - varre a coleção inteira
filtrada por série) toda vez que o Perfil abre.

**Recompensa Diária - UTC não é "meia-noite" no Brasil.** `diaria_
disponivel`/`reivindicar_diaria` comparavam `.date()` em UTC - com
Brasília fixo em UTC-3 (mesmo raciocínio já usado no World Boss, sem
horário de verão desde 2019), isso liberava o resgate de novo às 21h
locais. `FUSO_BRASILIA` migrou de `pandora.worldboss` (onde só ele usava)
pra `pandora.config` (compartilhado agora); a comparação de data em `db.py`
passou a `.astimezone(FUSO_BRASILIA).date()` antes de comparar - o
timestamp GRAVADO continua em UTC (consistente com o resto do banco), só a
pergunta "já virou o dia?" mudou de fuso.

**Loja - preço escalável + upgrade sem teto + itens direto como botão,
as 3 mudanças se encaixam.** Removido o teto de nível 5 do Upgrade de
Rolls/Claims (`db.comprar_upgrade_rolls_ate`/`comprar_upgrade_claims_ate`
substituem as versões de 1-nível-por-clique, mesmo padrão "pula direto pro
alvo, soma o custo de cada degrau" de Treinamento Global/Potencial da
Coleção) tornou Roll/Claim Permanente (item da Loja normal, preço fixo,
teto de 5 compras) redundante - removidos de `itens.ITENS_LOJA` (mas NÃO
de `itens.CATALOGO_ITENS`/`PESOS_DROP_RARO` - o World Boss continua
podendo dropar os dois normalmente, só a compra direta por WiShards fixos
saiu). Sobrando 5 itens compráveis, o wrapper "🎁 Itens" -> dropdown
(`_ViewLojaItens`, removida) virou 5 botões diretos na Loja - "poucos
itens" deixou de justificar o nível extra de navegação. Preço escalável
(`itens.custo_total_item`/`preco_unidade_loja`, +15% composto por unidade
já comprada) precisou de um contador NOVO (`colecao_compras_item`,
`db.total_comprado_item`/`registrar_compra_item`) - deliberadamente
separado de `colecao_inventario.quantidade` (que cai quando o item é
usado): o preço tem que continuar subindo mesmo depois do jogador gastar o
que comprou. Cada botão de item + os 2 Upgrades agora abrem
`_ViewEscolherAlvo` (mesma classe genérica que Treinamento Global/
Potencial da Coleção já usavam) pra comprar em lote, mostrando saldo +
preço total por opção antes de confirmar.

## Upgrade de Construção em lote + teto dinâmico da Cidade (2026-09-03)

**Unificação de área/construção primeiro, teto depois - a 2ª mudança
dependia da 1ª.** `itens.AREAS_CONSTRUCAO` (dict área->nome de construção,
"Militar"->"Quartel") e `cidade.FUNCOES_CIDADE` (tuple das mesmas 6 áreas)
eram 2 listas independentes descrevendo o MESMO domínio fechado - o pedido
do usuário ("vc tem distinguindo construção de area, mas é a msm coisa")
só foi possível resolver de verdade escolhendo ONDE a lista canônica devia
morar: `db.py`, porque o teto dinâmico (`teto_atual_construcao`) PRECISA
enxergar todas as 6 áreas pra calcular o mínimo entre elas, e `db.py` não
pode importar nem `itens.py` nem `cidade.py` (os dois já importam `db.py` -
ciclo). `AREAS_CONSTRUCAO = (...)` virou a fonte única em `db.py`;
`itens.AREAS_CONSTRUCAO`/`cidade.FUNCOES_CIDADE` viraram aliases (`=
db.AREAS_CONSTRUCAO`) - zero duplicação de string daqui pra frente.

**Teto dinâmico é sempre CALCULADO, nunca GRAVADO.** `db.teto_atual_
construcao(guild_id, user_id)` lê `niveis_construcoes` (já existia), pega
o MÍNIMO entre as 6 áreas (área nunca comprada conta como 0 - o pior caso)
e aplica `NIVEL_MAXIMO_CONSTRUCAO_BASE * (nivel_minimo // BASE + 1)`. Não
existe um "evento de destravar o teto" nem uma coluna nova pra isso - no
instante em que a última área atrasada bate o teto velho, a PRÓXIMA
leitura de `teto_atual_construcao` (a próxima vez que alguém tenta subir
QUALQUER área, ou abre o Inventário/Cidade) já devolve o teto novo
automaticamente. Isso também significa que o teto pode, em teoria,
DESCER se uma área nova aparecer no futuro com nível 0 enquanto as outras
já subiram - não é um cenário possível hoje (as 6 áreas são fixas, taxonomia
fechada), mas vale registrar que a função não tem estado próprio pra
proteger contra isso, é pura função do estado atual das 6 áreas.

**Uso em lote: `quantidade` clampada pro teto, mas NUNCA pra itens
faltando.** `itens.usar_upgrade_construcao(guild_id, user_id, area,
quantidade=1)` trata os 2 motivos de "não dá pra completar o pedido"
como coisas DIFERENTES: pedir mais do que cabe até o teto (`quantidade =
min(quantidade, teto - nivel_atual)`) é um limite ESTRUTURAL do jogo -
aplica o que cabe, sem erro, e a mensagem de sucesso já reflete o
`quantidade` real aplicado ("+10" em vez do "+15" pedido, no teste). Não
ter Upgrade de Construção suficiente (`db.quantidade_item` < `quantidade`
já clampada) é falta de RECURSO - falha explícita com os números exatos
("Você só tem X - precisa de Y"), mesma régua de "não tem WiShards
suficiente" usada em todo o resto da Loja. `db.subir_construcao` também
ganhou `quantidade` (era sempre +1) - grava o lote inteiro num único
`UPDATE ... SET nivel = nivel + excluded.nivel`, não um loop de N updates.

**UI reaproveita `_ViewEscolherAlvo` genérico** (mesma classe usada por
Treinamento Global/Potencial da Coleção/Upgrade de Rolls/Claims) em vez de
inventar um componente novo - só troca a "unidade" pra "Upgrade(s) de
Construção" em vez de WiShards, e o `custo_total_fn` vira uma subtração
simples (`alvo - nivel_atual`, 1 upgrade por nível) em vez de uma soma de
preços progressivos. O 1º passo (escolher a ÁREA) agora mostra "Nível
N/teto" em cada opção, então o jogador já vê quem está atrasado antes de
escolher onde investir.

**Cidade ganhou visibilidade do Nível de Construção** (pedido: "informa
na cidade o lv dessas construcoes") - `_embed_cidade` ganhou `guild_id`/
`user_id` (antes só recebia `resultado` de `cidade.coletar_producao_
pendente`) pra buscar `db.nivel_construcao`. 1ª versão acrescentava uma
linha própria "🏗️ Construção: Nível N/teto" no VALOR de cada card - o
usuário, vendo o resultado ao vivo, pediu formato mais compacto: "n
precisar colocar o campo construcao, é so por lv X na frente, Ex: ⚔️
Militar - Lv10" - o nível foi pro TÍTULO do card (`f"{icone} {funcao} -
Lv{nivel}"`), sem campo/linha extra, e sem mostrar o teto ali (só o
Inventário mostra "/teto" - exemplo do usuário não pedia isso na Cidade).

**Preços da Loja de Itens reduzidos ~30%** (pedido: "O preço desses
itens esta muito caro. Diminui um pouco") - `itens.PRECOS_LOJA_ITENS`
(Proteção/Revanche/Chave da Torre/Upgrade de Construção/Chamado) - eram
"primeiro palpite" documentados como "balanceável depois"; cortados de
forma consistente (mesmo fator pra todos) em vez de escolhidos um a um,
fácil de reajustar nesse mesmo lugar se ainda estiver caro/barato demais.

## 💖 Personagens Favoritas - Fortalecimento/Ascensão + remoção da Vitrine (2026-09-03)

Pedido do usuário veio como uma spec de 13 seções já fechada (patamares,
custos, exemplos numéricos de gap-filling) - o trabalho real de design foi
achar que os exemplos 4/5/6/7/10 do pedido são todos resolvidos por UM
algoritmo só (`personagens_favoritas._estado_fortalecimento`), não um caso
especial por exemplo.

**Por que bitmask, não lista.** 14 patamares fixos (300→1000, 50 em 50)
nunca mudam - um `INTEGER` com bit `i` = patamar `i` comprado NESSE slot
é literalmente mais simples que uma lista de strings/JSON, e a consulta
"esse patamar já foi comprado?" vira uma AND bit a bit em vez de parsing.
Ascensão (sem teto, sempre sequencial) já é um contador simples,
`nivel_ascensao` - não precisa de bitmask porque nunca tem lacuna (mesmo
padrão de todo outro "nível de upgrade" do projeto).

**O algoritmo central resolve gap-filling sem casos especiais:**
```python
def _estado_fortalecimento(popularidade, bitmask):
    atual = torre.power_base(popularidade)  # fórmula original, intocada
    for indice, (_lo, hi) in enumerate(PATAMARES_FORTALECIMENTO):
        if atual >= hi:
            continue  # natural já superou esse patamar - nunca precisa comprar
        if bitmask & (1 << indice):
            atual = hi  # patamar comprado NESSE slot - sobe
        else:
            return atual, indice  # lacuna - para aqui, é o próximo a comprar
    return atual, None  # 1000 atingido, só Ascensão daqui pra frente
```
Isso sozinho cobre: personagem de Power natural alto entrando num slot
zerado (pula os patamares abaixo do natural sem checar bit nenhum);
personagem de Power natural baixo entrando num slot com patamares ALTOS
já comprados (para na primeira lacuna, mesmo que 900→950/950→1000 já
estejam comprados - só alcança eles depois de preencher tudo abaixo);
Power natural desalinhado tipo 873 (o próximo patamar é sempre o GLOBAL
seguinte - 850→900 - custando o preço CHEIO daquele patamar, nunca uma
fração proporcional à distância real coberta).

**O hook no Power Base é a parte que precisava de mais cuidado pra não
violar a regra "não alterar a fórmula original".** `torre.power_final`
já fazia `(power_base(popularidade) + bônus_nível) × multiplicador`;
virou `power_final(..., power_base_override=None)` - quando presente,
SUBSTITUI só a chamada a `power_base(popularidade)`, o resto da fórmula
(bônus de nível fixo, multiplicador de Afinidade/Soulmate) roda
IDÊNTICO. `torre.power_personagem` ganhou `favoritas_ocupantes`
(opcional, dict pré-carregado) - mesmo padrão já estabelecido por
`bonus_series` (Série Favorita): calculado em lote 1x por
`_contexto_lote` (5º elemento da tupla agora), nunca consultado por
personagem individual no caminho quente. Isso obrigou atualizar TODO
call site que desempacota essa tupla (`torre.py` x2, `cidade.py`,
`worldboss.py`, `paineis._descricao_personagem_dropdown` - esse último
sozinho já cobre Merge/Party/Trocar de personagem, é o helper central
reaproveitado por todo select de personagem do pacote).

**Ciclo de import evitado com import local, não reestruturação.**
`personagens_favoritas.py` precisa de `torre.power_base` (a fórmula
natural); `torre.py` precisa de `personagens_favoritas.power_efetivo`/
`elegivel_ascensao` pro hook. Import nos 2 topos seria um ciclo -
resolvido com `from pandora import personagens_favoritas` DENTRO de
`power_personagem` (não no topo de `torre.py`), mesmo padrão já usado em
`itens.usar_chamado` (import local de `worldboss` pelo mesmo motivo,
achado nesta sessão ao revisar o precedente antes de decidir).

**Validado contra um banco temporário isolado** (não o real): favoritar
uma personagem nova sem nenhum Fortalecimento comprado mantém Power
natural exato; 3 Fortalecimentos sequenciais (300→350→400→450) custam
50/100/250 Soulstone, batendo com a tabela do pedido; `power_personagem`
com o slot aplicado via `favoritas_ocupantes` reflete exatamente +150 de
Power Base sobre o mesmo cálculo sem o hook (a soma dos 3 patamares) -
confirma que a substituição é puramente aditiva, o resto da fórmula
(bônus global/classe/série, que também estavam ativos no teste) não foi
tocado por engano.

**Vitrine removida** (mostruário público, `/vitrine` no ERIS - nunca
teve botão no hub `/pandora`, então a remoção não afeta nenhum fluxo já
em uso pelo hub) - substituída em espírito pelo sistema novo.
`colecao_equipe` (tabela compartilhada por Party/Vitrine via `tipo`)
continua genérica, sem migração - linhas antigas com `tipo="vitrine"`
(se existirem) ficam órfãs e inertes, mesmo padrão de "nunca migração
destrutiva" já usado no projeto inteiro.

## Falha de classificação silenciosa em "Comprar Tudo" (2026-09-05)

Achado do usuário: "quando estou dentro das coleções, e mando comprar tudo,
as personagens compradas estão vindo sem classe". Causa raiz já era
conhecida (ver "4 correções/melhorias de 2026-09-03" acima - cota diária de
tokens da Groq só aguenta ~23 classificações reais por dia), mas
`gacha.comprar_com_revelacao` não tinha como AVISAR quem chamou quando isso
acontecia: `revelar_classe` roda sobre uma cópia FRESCA do personagem
(`db.personagem_por_id`, não o dict que o chamador já tinha em mãos) e o
resultado nunca voltava pro chamador - a compra em si sempre reportava
sucesso (`ok=True`), então "Comprar Tudo" numa série grande (facilmente mais
de 23 personagens livres) estourava a cota no meio do lote e ninguém
percebia até auditar depois com `/pandora_admin validar_classes`.

Corrigido devolvendo um 3º valor, `tem_classe` (`None` se `ok=False`,
True/False se `ok=True`) - `_sufixo_aviso_sem_classe` (novo, `paineis.py`)
vira um aviso "⚠️ sem classe ainda... `/pandora_admin validar_classes`
tenta de novo depois" anexado à mensagem de resposta nos 4 pontos que
compram personagem (Loja "Comprar" da série/navegador, "Comprar Tudo",
Loja principal). Nenhuma mudança na causa raiz em si (cota da Groq) - o
comando de auditoria já existente continua sendo a retentativa real, isto
só torna o gap VISÍVEL na hora em vez de silencioso.

## "⚡ Fortalecer ao Máximo" nas Waifus (2026-09-06)

Pedido do usuário: "Na tela de waifus, permita fortalecer varios leveis".
`personagens_favoritas.fortalecer` (Seção do sistema de Personagens
Favoritas, ver seção própria mais abaixo/CHANGELOG de 2026-09-03) só
avançava 1 dos 14 patamares de Fortalecimento por chamada - o botão "💪
Fortalecer" (`_ViewDetalheFavorita`) exigia clicar (e esperar o Discord
responder) repetidamente pra subir vários patamares de uma vez, mesmo com
saldo de Soulstone suficiente pra todos de cara.

**`personagens_favoritas.fortalecer_em_massa`** (novo) reaproveita as
MESMAS constantes/regra de preço de `fortalecer`
(`CUSTOS_FORTALECIMENTO`/`PATAMARES_FORTALECIMENTO`/
`_estado_fortalecimento` - nunca duplicadas) num loop que gasta o saldo
ATUAL de Soulstone em quantos patamares couberem, em sequência, parando no
1º que não couber OU ao chegar no Fortalecimento máximo (1000). Não é uma
chamada em loop de `fortalecer()` em si (isso reconsultaria o banco a cada
patamar, até 14x à toa) - o loop lê `linha`/`personagem`/saldo UMA vez e
segue em memória, só gravando no banco (`db.creditar_soulstone`/
`db.marcar_patamar_fortalecimento`) por patamar comprado de verdade.
Devolve `(ok, mensagem)` - `ok=False` só quando NENHUM patamar coube (saldo
zerado ou já no máximo); sucesso PARCIAL (1+, mas não os 14) ainda conta
como sucesso, com a mensagem reportando quantos patamares/qual faixa final
(ex.: "Fortalecido 3 patamar(es)! 450→600...").

**UI:** novo botão "⚡ Fortalecer ao Máximo" ao lado do "💪 Fortalecer"
comum em `_ViewDetalheFavorita._montar_botoes` (mesma condição de
visibilidade - só aparece quando `item["proximo_fortalecimento"]` existe) -
"💪 Fortalecer" NÃO foi removido, continua servindo quem prefere controle
fino de 1 patamar por vez (ex.: pra não gastar Soulstone que quer guardar
pra outra coisa). Nenhuma mudança de schema/tabela - só uma função nova +
1 botão novo.

## Dropdowns de personagem padronizados (classe + CP base) + 3 bugs reais (2026-09-06)

Usuário mandou uma imagem do dropdown da Party (formato "🛡️ Nome #443
⭐⭐⭐⭐ Nv.10 · CP 142,8K · 💞10") como referência do padrão esperado em
QUALQUER select de personagem, com um pedido extra: mostrar também **CP
base** (`torre.power_base(popularidade)` - Power Base natural, 300-1000,
puramente da popularidade da personagem, sem Nível/Afinidade/Soulmate/
bônus nenhum) "relacionado à mecânica de waifu" - é esse número que decide
quantos patamares de Fortalecimento de um slot de Waifu a personagem já
cobre sozinha (`personagens_favoritas._estado_fortalecimento`), então é o
dado relevante na hora de escolher quem colocar num slot. Junto, pedido
pra mostrar a classe também (não só o ícone de categoria).

**`_descricao_personagem_dropdown`** (formatador único já usado por Party/
Merge/"🔍 Personagem" desde 2026-08-30) ganhou os 2 campos. Auditoria dos
OUTROS selects de personagem do pacote achou vários que nunca passavam
`descricao=` nenhum pro `_ModalBuscarPersonagem`/`_ViewSelecionarPersonagem`
(caíam no fallback simples, `#id · estrelas` ou só `#id`) - todos
corrigidos pra passar o formatador certo: "Trocar/Escolher personagem"
(Waifus), Batalha (escolher personagem alheia - usa o `contexto_lote` do
ALVO, não de quem desafia), Proteção, Prova de Soulmate.

**Novo `_descricao_personagem_livre_dropdown`** - 3 selects listam
personagens SEM um dono fixo consultável (Fusão - escolher quem RECEBER,
entre livres do servidor; Loja "Comprar"; Revanche - "perdidas", cada uma
com um dono ATUAL diferente, quem venceu aquela Batalha) - Nível/Afinidade
não fariam sentido nesses 3 (não tem 1 conta certa pra consultar), mas
classe + CP base + categoria (`torre.categoria_personagem`, função PURA -
só olha `personagem["classe"]`, funciona igual sem dono nenhum) continuam
fazendo sentido e agora aparecem lá também.

**Achado real no processo, "A lista dos personagens de troca, fusão esta
errado":** o select de "🔄 Trocas" (`_ViewEscolherPersonagensTroca`) NUNCA
usava `_descricao_personagem_dropdown` - montava `SelectOption` direto com
só nome+estrelas, o único select de personagem do pacote inteiro sem
NENHUM detalhe (CP/nível/afinidade/classe). Corrigido usando o dono certo
por etapa (proponente na etapa "oferece", alvo na etapa "pede" - cada uma
precisa do PRÓPRIO `contexto_lote`, calculado na hora certa em
`_ViewEscolherAlvoTroca._selecionou`/`_ViewEscolherPersonagensTroca.
_avancar`). Fusão, em contraste, já usava o formatador certo desde sempre -
só ficou mais completa com os 2 campos novos.

**"O botão Coleção dentro de Perfil nao responde":** `_ViewPerfil._colecao`
chamava `ViewColecaoHub.colecao_minha_ordenada` (documentado como caro -
ordena a coleção INTEIRA por CP) ANTES de `interaction.response.
send_message` - mesma classe de bug "GAIA não respondeu a tempo" corrigida
dezenas de vezes neste projeto em outros pontos, essa instância específica
nunca tinha sido reportada. `defer()` + `followup.send` resolvem, mesmo
padrão de sempre.

**"Pode remover... Slot de Serie Favorita na loja":** removido o botão +
`_upgrade_slot_serie_favorita` da `_ViewLoja` - era uma duplicata completa
do botão "Comprar slot" que já existe dentro de `_ViewSeriesFavoritas`
(mesmo `db.comprar_slot_serie_favorita`/tabela de preços por trás), sem
nenhuma vantagem por estar também na Loja. O slot de Waifu nunca teve
essa duplicata pra começar - agora os dois sistemas seguem o mesmo padrão
(slot comprado só de dentro da própria tela).

**"quero ver as imagens das personagens... com as classes e tudo":**
`_ViewDetalheFavorita.montar_embed` reconstruía um `discord.Embed` do zero
(só nome em texto, nenhuma imagem, nenhuma classe) - trocado por
`consulta.embed_carta_personagem(p)` (o MESMO card completo que "🔍
Personagem" usa - imagem via `set_image`, classe, série, vínculo de
Afinidade/Soulmate) como base, com os campos específicos do slot (Power
natural/atual, Fortalecimento/Ascensão) adicionados por cima via
`add_field`. **Atualização no mesmo dia** (ver seção seguinte): a lista de
slots em texto puro descrita aqui foi substituída por um navegador com
setas - o card completo agora é a ÚNICA tela, não mais algo que só aparece
ao abrir 1 slot por vez.

Nenhuma mudança de schema. Validado só por leitura de código (sem clique
real no Discord) - ver `docs/TODO.md`.

## Waifus: navegador com setas + Fortalecer virou dropdown (2026-09-06)

Mesmo dia da leva anterior, pedido novo do usuário depois de ver o card
completo funcionando: "quero q na propria tela de waifus, q lista os
slots, seja como a tela de personagens, q tem as setas p ver as imagens e
dados detalhados de cada uma" + "ao selecionar um slot, o botao de
fortalecer dentro dele tem de permitir fortalecer varios niveis por vez,
por um dropdown igual nos outros locais, mostrando custo e qnt tenho".

**Navegador único.** `_ViewPersonagensFavoritas` (lista em texto + Select
de slot, mensagem própria) e `_ViewDetalheFavorita` (card de detalhe,
OUTRA mensagem separada aberta ao escolher um slot) viraram uma única
classe, no mesmo espírito de `_ViewNivel` ("🔍 Personagem"): `self._indice`
guarda a posição atual dentro de `self._slots` (lista inteira, carregada
1x em `criar()` - diferente de "🔍 Personagem", nunca precisa paginar em
blocos de 25, porque o total de slots é sempre pequeno, `SLOTS_MAXIMO` no
máximo). ◀️/▶️ trocam `self._indice` e redesenham; `montar_embed()` sempre
devolve o card completo (via `consulta.embed_carta_personagem`, ver seção
anterior) do slot atual, com rodapé "posição/total". Todas as ações
(Fortalecer/Ascender/Trocar/Esvaziar/Comprar slot) passaram a operar sobre
`self._item` (property que resolve `self._slots[self._indice]`) em vez de
um `self._item` fixo recebido no construtor.

**Correção no mesmo dia:** a 1ª versão desta leva derrubou por completo o
Select "escolher um slot" da tela antiga, sobrando só as setas - achado do
usuário ("Ficou faltando o dropdown p ir rapido para os personagens na
tela de waifu"). `_montar_select_slots` devolveu o dropdown (row 0, acima
das setas na row 1) - agora, igual "🔍 Personagem", a tela tem os DOIS
jeitos de navegar ao mesmo tempo (setas pra 1 passo, dropdown pra pular
direto), nunca só um dos dois.

**2ª correção, mesmo dia:** a description desse dropdown novo começou com
um texto PRÓPRIO (só nome + "Power atual" do slot) - achado do usuário
("Nesse dropdown de slot era p ser igual dos outros personagens, mostrando
todas aquelas infos"). Trocado por `_descricao_personagem_dropdown`, o
MESMO formato padrão de Party/Merge/Trocas/"🔍 Personagem" (classe, CP
final, CP base, Nível, Afinidade, ícone de categoria) - `torre.
power_personagem` já detecta sozinho, via `favoritas_ocupantes` (parte do
`_contexto_lote`), que a personagem ocupa ESSE slot, e usa o Power Base
EFETIVO do slot (com Fortalecimento/Ascensão) em vez do natural pro CP
final; "CP base" continua sendo o natural, puro, útil justamente pra
comparar contra o CP final boostado pelo slot. `criar()`/`_atualizar()`
passaram a pré-carregar `torre._contexto_lote` 1x (guardado em
`self._contexto_lote`) - sem isso, descrever cada slot ocupado abriria sua
própria consulta, o mesmo tipo de custo que a correção da Party (seção
anterior) já eliminou noutro lugar.

**3ª correção, mesmo dia:** "Adiciona o Power Atual na frente do nome do
personagem" - o RÓTULO (`label`, a 1ª linha da opção, diferente da
`description` que já mostra o CP completo) ganhou o `power_atual` do
PRÓPRIO slot (não o CP de `_descricao_personagem_dropdown`). 1ª tentativa
pôs o número ANTES do nome (`f"Slot {slot}: {power_atual} {nome}"`) -
corrigida na hora ("valor era p ser igual antes Slot N: <Nome> (Power
<Power Atual>)") pro formato de sempre, número DEPOIS do nome entre
parênteses: `f"Slot {slot}: {prefixo_soulmate}{nome} (Power {power_atual})"`.

**Fortalecer virou dropdown, não mais 2 botões.** O par "💪 Fortalecer" (1
patamar por clique) + "⚡ Fortalecer ao Máximo" (gasta o saldo todo, da
leva anterior no mesmo dia) foi substituído por UM botão que abre um
dropdown "até qual patamar ir", com custo TOTAL acumulado por opção e
confirmação antes de gastar - exatamente o padrão já usado por "⬆️ Upar
Nível"/Loja/Construção (`_ViewEscolherAlvo`). A 1ª opção do dropdown É o
antigo comportamento de 1 clique; a ÚLTIMA é "gastar tudo que dá pra esse
slot" - um único fluxo cobre os 2 extremos antigos e tudo no meio, sem
precisar de 2 botões.

`_ViewEscolherAlvo` **generalizado, não duplicado.** Fortalecimento não é
um domínio de "incrementos de 1 unidade" como Nível/Afinidade/Upgrade de
Construção (que `_ViewEscolherAlvo` já assumia, com `range(valor_atual+1,
valor_maximo+1)` e rótulo fixo `f"{rotulo} {alvo}"`) - são 14 patamares
FIXOS, saltos de 50 em 50, cada um com custo próprio. Em vez de criar uma
classe paralela duplicando toda a lógica de custo acumulado/confirmação/
preservação do embed original durante o passo de confirmação (já testada
em produção pelos outros 4 usos), `_ViewEscolherAlvo` ganhou 2 parâmetros
NOVOS e opcionais:
- `rotulo_opcao_fn(alvo)` - troca o rótulo padrão da opção por um
  customizado (Fortalecimento usa `f"Fortalecer até {hi}"`, mostrando o
  Power-alvo em vez do índice cru do patamar).
- `unidade_degrau` (padrão `"nível"`) - troca a palavra usada pro "passo"
  na descrição/confirmação (Fortalecimento usa `"patamar"`).

Os 4 callers antigos (Upar Nível, Aumentar Afinidade, Loja - Treinamento
Global/Potencial da Coleção/Upgrade de rolls/claims/itens, Construção)
continuam passando só os parâmetros de sempre - o comportamento deles não
mudou uma linha, os 2 novos parâmetros são puramente aditivos.

`personagens_favoritas.fortalecer` (1 patamar) e `fortalecer_em_massa`
(gasta tudo, da leva anterior) foram REMOVIDOS - sem nenhum uso fora do
antigo par de botões que também foi removido. Substituídos por
`custo_fortalecer_ate(indice_proximo, indice_alvo)` (soma pura, sem tocar
no banco - usada pra montar as opções do dropdown) e `fortalecer_ate(
guild_id, user_id, slot, indice_alvo)` (compra tudo do próximo patamar até
`indice_alvo` inclusive, tudo-ou-nada: se o saldo não cobrir o custo TOTAL
escolhido, falha sem comprar nada - diferente do antigo "gasta o quanto
der", aqui o jogador já escolheu o alvo exato no dropdown antes de
confirmar, então não faz sentido parar no meio de uma compra que ele
mesmo pediu).

Nenhuma mudança de schema. Validado só por leitura de código (sem clique
real no Discord) - ver `docs/TODO.md`.

## Cidade (ordem de texto) + Party lenta ao filtrar por role (2026-09-06)

**Cidade** - troca pura de ordem em `_embed_cidade`, sem mudança de dado:
o texto "Desde sua última visita" mostrava WiShards/XP/Soulstone, virou
WiShards/Soulstone/XP de Progressão (pedido do usuário: "inverte soulstone
com xp no inicio").

**Party lenta ("apos colocar a role, demora um pouco p aparecer as
personagens daquela role, tem como melhorar?").** Achado em `_abrir_
adicionar`/`prosseguir`: filtrar as candidatas por categoria chamava
`torre.categoria_personagem(p)` (que por sua vez chama `db.categoria_
combate_da_classe(classe)`, uma consulta SQLite própria) **por
personagem candidata**, sem nenhum cache - uma coleção com muitas
personagens da MESMA classe repetia a consulta idêntica centenas de vezes.
É exatamente o mesmo padrão "44 Guerreiro = 44 conexões SQLite idênticas"
que `torre.power_personagem`/`db.info_classes_em_lote` já existem
especificamente pra evitar (achado originalmente em `cidade._workforce_
por_funcao`, 2026-09-01, "2,7s pra ~1.100 personagens") - só que aqui,
nessa função específica, ninguém tinha usado esse cache ainda. Por cima
disso, `ordenar_por_power` (chamada logo depois) e a montagem da descrição
do dropdown (`_descricao_personagem_dropdown`) cada uma abria sua PRÓPRIA
`torre._contexto_lote` de novo - 3 idas ao banco fazendo, na prática, o
trabalho de 1.

**Correção:** `torre.ordenar_por_power` ganhou um parâmetro opcional
`contexto_lote=None` - se não vier, continua buscando sozinha (nenhum dos
outros 5 callers no projeto precisou mudar); se vier, reaproveita o que já
foi carregado. `prosseguir` agora busca UM `_contexto_lote` no topo e
reaproveita nos 3 passos: filtra usando `contexto_lote[2]` (o cache de
classe -> categoria, já em lote) em vez de `categoria_personagem` por
personagem, passa o mesmo contexto pra `ordenar_por_power`, e pra
`_descricao_personagem_dropdown` na montagem final do select. Resultado:
1 consulta em lote no lugar de 3 (uma delas antes sendo, na real, N
consultas - N = quantidade de candidatas).

Nenhuma mudança de schema/comportamento visível além da velocidade (mesmo
filtro/ordenação/descrição de sempre, só bem mais rápido). Validado só por
leitura de código (sem medição real de tempo antes/depois) - ver
`docs/TODO.md`.

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
