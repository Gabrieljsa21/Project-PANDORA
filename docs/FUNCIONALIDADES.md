# Funcionalidades - Project PANDORA

Referência de TUDO que existe hoje no Colecionador de Personagens: cada tela,
botão e comando de barra, o que faz e quanto custa. Documenta o ESTADO
ATUAL (não é um histórico - pra isso ver `CHANGELOG.md`; pra decisão técnica/
raciocínio de implementação, ver `ARQUITETURA.md`). Atualizar sempre que um
botão/comando for adicionado, removido ou mudar de comportamento visível
pro jogador (ver `CLAUDE.md`).

PANDORA é uma biblioteca importada pelo [Project-ERIS](../../Project-ERIS), que
registra os comandos de barra de verdade - por isso alguns comandos citados
aqui (`/wa`, `/pandora_admin`, etc.) vivem no código do ERIS, não neste repo.

## Índice

1. [Hub principal (`/pandora`)](#hub-principal-pandora)
2. [Rolls e Claims](#rolls-e-claims)
3. [Loja](#loja)
4. [Inventário](#inventário)
5. [Investir em Massa](#investir-em-massa)
6. [Perfil](#-perfil)
7. [🔍 Personagem (navegador de coleção)](#-personagem-navegador-de-coleção)
8. [💖 Waifus (Personagens Favoritas)](#-waifus-personagens-favoritas)
9. [❤️ Séries Favoritas](#️-séries-favoritas)
10. [👥 Party, Trocas e 🧬 Fusão](#-party-trocas-e--fusão)
11. [🗼 Torre](#-torre)
12. [🏙️ Cidade](#️-cidade)
13. [⚔️ Batalha 5x5 (PvP)](#️-batalha-5x5-pvp)
14. [🌍 World Boss](#-world-boss)
15. [Auto-colecionador / Auto-claim](#auto-colecionador--auto-claim)
16. [`/pandora_admin` (configuração do servidor)](#pandora_admin-configuração-do-servidor)
17. [Comandos avulsos](#comandos-avulsos)

---

## Hub principal (`/pandora`)

Painel central do Colecionador. Abre um embed com resumo do jogador
(WiShards, tamanho da coleção, Soulstone, posição no ranking do servidor e
Progressão/Nível da conta) e uma grade de botões. É um painel pessoal: só
quem digitou `/pandora` pode clicar nos próprios botões.

**Linha 1**
- **🎲 Rolar**: rola personagens de qualquer gênero (equivalente a `/ma`).
  Sempre puxa o máximo de rolls que sobrar no ciclo atual num clique só, não
  apenas 1.
- **🎯 Claim All**: reivindica de uma vez todas as personagens disponíveis
  nesse servidor (as que caíram em rolls recentes e ainda não têm dono), em
  ordem de popularidade, até os claims do ciclo acabarem ou a lista esgotar.
- **🎁 Diária**: resgata a Recompensa Diária (uma vez por dia de calendário).
  Dá WiShards (a quantidade escala com a Progressão da conta) e garante 1
  item raro (os mesmos itens que podem cair como drop do World Boss).

**Linha 2**
- **👥 Party**: abre a equipe (até 5 personagens) usada em Batalha/Torre.
- **🔄 Trocas**: inicia uma proposta de troca com outro membro do servidor.
- **⚔️ PvP**: abre o painel de Batalha 5x5 com aposta de personagem.
- **🧬 Fusão**: funde 5 personagens da mesma raridade em 1 personagem daquela
  raridade, à escolha, dentre as disponíveis no servidor.

**Linha 3**
- **🏙️ Cidade**: mostra o status da produção da Cidade (a alocação de
  personagens às funções é automática, por classe - aqui só se coleta o que
  já foi produzido) + botões pra comprar/usar Upgrade de Construção direto
  do painel.
- **🗼 Torre**: abre o andar atual da Torre de desafios.
- **🐉 World Boss**: abre o painel do chefão cooperativo do servidor (visível
  a qualquer jogador, não só a quem abriu o hub).

**Linha 4**
- **🛒 Loja**: abre a Loja.
- **🎒 Inventário**: mostra e permite usar os itens que o jogador tem
  guardados.
- **📈 Investir em Massa**: sobe Nível ou Afinidade de várias personagens de
  uma vez, gastando um orçamento definido pelo jogador.

**Linha 5**
- **📖 Perfil**: abre o perfil detalhado e dá acesso a Auto-claim, Ranking,
  Conquistas, Wishlist, Séries Favoritas, Coleção e Classes.
- **🔍 Personagem**: abre o navegador de card de uma personagem específica da
  coleção do jogador.
- **❤️ Séries**: gerencia os slots de Série Favorita.
- **💖 Waifus**: lista de Personagens Favoritas (slots por personagem
  individual, em vez de por série).

---

## Rolls e Claims

### Comandos de rolar
- **`/wa`**: rola personagem(ns) **feminina(s)**.
- **`/ha`**: rola personagem(ns) **masculina(s)**.
- **`/ma`**: rola personagem(ns) de **qualquer gênero** (o botão "Rolar" do
  hub usa esse mesmo caminho).

Todos aceitam um parâmetro opcional `quantidade`. Deixar vazio ou colocar
`0` rola **todos os rolls que sobrarem** no ciclo atual de uma vez.
Informar um número explícito respeita o teto de "máximo por puxada"
configurado no servidor (padrão: 10, ajustável em `/pandora_admin
max_puxada`).

Por padrão, cada jogador tem **50 rolls a cada 60 minutos** (configurável
por servidor). Uma parte dos rolls (20% de chance por padrão, também
configurável) pode vir direto da Wishlist de quem está rolando, em vez do
sorteio normal por raridade.

Raridade sorteada com pesos fixos: 1⭐ 50%, 2⭐ 30%, 3⭐ 15%, 4⭐ 4%, 5⭐ 1%.

### O que pode acontecer ao rolar uma personagem
- **Livre**: ninguém no servidor tem essa personagem ainda. Vira um card com
  botão/reação de Reivindicar.
- **Reencontro**: quem rolou já é dono dela. A Afinidade sobe e ela já paga
  WiShards na hora, sem precisar clicar em nada. Se a Afinidade já estiver
  no máximo (10), a personagem vira automaticamente **Soulmate** (na
  primeira vez) ou dá **Soulstone extra** (nas vezes seguintes).
- **Terceiro**: outra pessoa já é dona dela. Quem rolou não ganha nada; o
  dono de verdade recebe metade do valor da personagem em WiShards, como
  uma espécie de "royalty".

### O card e a reivindicação
Cada personagem rolada sai numa mensagem própria, com imagem, série e
raridade. Se estiver "livre":
- A mensagem ganha 2 reações: uma colorida por raridade (⚪1⭐/🟢2⭐/🔵3⭐/🟣4⭐/🟡5⭐)
  que reivindica normalmente, e ⭐ que reivindica e já favorita a
  personagem.
- Ao fim de uma puxada, chega também uma mensagem separada com um botão
  "💘 Reivindicar" por personagem livre ("Reivindicar uma das 10 primeiras",
  já que cada mensagem de botões cobre até 10 cartas por vez).
- O botão/reação fica ativo por um tempo limitado (1 hora por padrão,
  configurável por servidor); depois disso os botões se desativam
  sozinhos.

Reivindicar (claim) dá:
- A personagem entra na coleção, com Afinidade inicial 1.
- WiShards iguais ao valor base dela (20 × número de estrelas: 20 pra 1⭐,
  até 100 pra 5⭐).
- XP de Progressão da conta.
- Revelação da classe/categoria de combate da personagem (só na primeira
  vez que ela é reivindicada em qualquer servidor).

**Cooldown de claims**: por padrão 1 claim a cada 60 minutos por jogador
(configurável por servidor, e aumentável na Loja via "Upgrade de claims").

---

## Loja

Aberta pelo botão **🛒 Loja** do hub.

- **🛍️ Comprar**: 3 passos - (1) dropdown de raridade (1⭐ a 5⭐); (2) janela
  de texto (Modal) pra digitar parte do nome (pode deixar em branco pra ver
  uma amostra); (3) dropdown com até 25 personagens daquela raridade mais
  parecidas com o nome digitado, ainda livres no servidor, pra escolher a
  exata e comprar. Preços: 1⭐ 250, 2⭐ 500, 3⭐ 1.000, 4⭐ 2.500, 5⭐ 5.000
  WiShards.
- **🎯 Garantir raridade**: paga pra garantir que o próximo roll saia numa
  raridade mínima escolhida (3⭐, 4⭐ ou 5⭐), mas a personagem em si continua
  sendo sorteada aleatoriamente. Custa sempre metade do preço de "Comprar"
  da mesma raridade: 3⭐ 500, 4⭐ 1.250, 5⭐ 2.500 WiShards.
- **⬆️ Upgrade de rolls**: aumenta permanentemente quantos rolls o jogador
  ganha por ciclo (+5 rolls por nível, sem teto). Preços dos 5 primeiros
  níveis: 1.000 / 2.500 / 5.000 / 10.000 / 25.000 WiShards; a partir do
  nível 6 o preço dobra a cada nível.
- **🔺 Upgrade de claims**: mesma lógica, mas pra claims (+1 claim por ciclo
  por nível). Preços dos 5 primeiros níveis: 2.000 / 5.000 / 10.000 /
  20.000 / 40.000 WiShards; também dobra a partir do nível 6.
- **🏋️ Treinamento da Coleção**: sobe permanentemente um Nível de Treinamento
  que dá +25 de CP fixo pra TODAS as personagens da coleção, pra sempre.
  Sem teto de nível; custo por nível = nível² WiShards.
- **📊 Maestria da Coleção**: como o Treinamento da Coleção, mas o bônus é
  percentual (+2% de CP global por nível) em vez de fixo. Custo por nível =
  2 × nível² WiShards.

  **Como comprar vários níveis de uma vez** (Upgrade de rolls/claims,
  Treinamento da Coleção, Maestria da Coleção): mesmo dropdown com custo
  acumulado + confirmação do "⬆️ Upar Nível" da seção "🔍 Personagem" acima,
  mostrando também quanto você tem no momento no placeholder ("Você tem X
  WiShards - escolha o Nível alvo..."). Diferença aqui: como esses 4 não têm
  teto de nível fixo, o dropdown só lista até **25 níveis à frente** do
  atual por vez (limite de verdade de um menu do Discord) - pra subir mais
  que isso, é só abrir o botão de novo depois de comprar o primeiro lote.
- **Itens** (botões diretos, sem passar por menu): clicar abre o mesmo
  dropdown de "até quanto" das outras seções (custo TOTAL acumulado por
  opção + confirmação), deixando comprar de 1 até 25 unidades de uma vez
  só; preço sobe 15% por unidade já comprada (geométrico), então cada
  opção do dropdown mostra quanto custaria comprar aquela quantidade no
  preço já escalado.
  - 🛡️ **Proteção** (2.100 WiShards base): protege 1 personagem de ser
    perdida numa Batalha 5x5 enquanto ativa.
  - ⚔️ **Revanche** (2.800 WiShards base): desafia de novo por uma
    personagem perdida no PvP, ignorando cooldown/limite diário.
  - 🗝️ **Chave da Torre** (3.500 WiShards base): ignora a restrição de
    categoria na próxima tentativa de andar da Torre.
  - 📯 **Chamado** (5.600 WiShards base): escolhe qual World Boss aparece no
    próximo horário fixo desse servidor.

  (Roll Permanente e Claim Permanente, dois outros itens do catálogo, só
  vêm de drop raro do World Boss/Diária, não são comprados na Loja. "🏗️
  Upgrade de Construção" TAMBÉM saiu daqui, 2026-09-07 - "Vamos tirar esse
  item da loja e permitir o jogador upar diretamente a construção" - ver
  "💰 Upar Construção" na seção "🏙️ Cidade" abaixo; o item continua
  existindo, só não é mais comprável com WiShards.)

---

## Inventário

Aberto pelo botão **🎒 Inventário** do hub, é pessoal. Mostra quantos itens o
jogador tem guardados e cria um botão de "usar" só pros itens que ele
realmente possui:
- **Usar Proteção**
- **Usar Revanche**
- **Ativar Chave da Torre** (some da lista enquanto já estiver ativa)
- **Usar Upgrade de Construção**
- **Usar Chamado**

Também mostra, como status (sem botão, é automático): bônus permanente de
Roll/Claim vindo de drop do World Boss e de compra na Loja (cada um com
teto próprio de +5); se a Chave da Torre está ativa; quais personagens
estão atualmente protegidas contra perda no PvP.

Botão **🔄 Atualizar** recarrega o painel depois de usar algo.

---

## Investir em Massa

Aberto pelo botão **📈 Investir em Massa** do hub. Serve pra upar várias
personagens de uma vez sem escolher uma por uma: o jogador escolhe **Nível**
ou **Afinidade** e informa só o orçamento que quer gastar; o sistema
investe automaticamente, sempre priorizando as personagens de **maior CP
primeiro**, até o orçamento acabar ou não sobrar mais ninguém pra upar.

- **⬆️ Nível (WiShards)**: sobe o Nível das personagens (teto 10 por
  personagem) gastando WiShards.
- **💕 Afinidade (Soulstone)**: sobe a Afinidade das personagens gastando
  Soulstone.

O orçamento é digitado num campo de texto (aceita "50000", "50.000" ou
"50K"); o resultado mostra quanto foi realmente gasto e lista cada
personagem que subiu, com o nível/afinidade antes e depois.

Existe uma variante restrita a uma única Série Favorita, acessível pelo
navegador de séries (ver "❤️ Séries Favoritas" abaixo), que funciona igual
mas só investe nas personagens daquela série.

---

## 📖 Perfil

Botão do hub que abre a tela pessoal do jogador:
- Total de personagens na coleção, nível máximo, afinidade máxima e
  quantidade de Soulmates.
- Tabela de progressão por raridade (1 a 5 estrelas), com quantas
  personagens de cada uma estão no nível máximo, na afinidade máxima e
  quantas viraram Soulmate (contagem e porcentagem).
- Contagem de Conquistas desbloqueadas, andar atual da Torre e saldo de
  Soulstones.

Sub-botões:
- **🤖 Auto-claim (ON/OFF)**: liga/desliga a reivindicação automática (ver
  seção "Auto-colecionador / Auto-claim").
- **🏆 Ranking**: seletor de métrica (Coleção, Soulmates ou Torre), top 25
  do servidor naquela métrica.
- **🏆 Conquistas**: abre o painel de conquistas (ver seção própria). Ao
  abrir, confere na hora se algum marco novo foi cruzado.
- **⭐ Wishlist**: abre a lista de desejos em formato de card navegável.
- **📚 Séries**: abre a tela de Séries Favoritas com estatísticas detalhadas.
- **📚 Coleção**: abre a tela de coleção (ver seção própria).
- **⚔️ Classes**: abre a tela de bônus por classe.

### Coleção

Duas formas de ver: comando `/colecao` e a tela expandida do Perfil.

- **`/colecao [membro]`**: mostra a coleção de quem usou o comando ou de
  outro membro, paginada 10 por página (◀️/▶️). Cada linha mostra estrelas
  de raridade, nome, classe (se já revelada), série e afinidade (ou o selo
  de Soulmate).
- **Tela de Coleção do Perfil**: mesma paginação, mas com um seletor de
  modo:
  - **📚 Minha coleção**: coleção inteira ordenada por CP (maior primeiro),
    com ícone de categoria de combate e CP de cada uma.
  - **🔥 Populares do catálogo**: as 50 personagens mais populares de TODO o
    catálogo (não só as que o jogador possui), com posição no ranking
    global e curtidas da fonte.
  - **🎯 Disponíveis pra pegar**: quem está livre pra reivindicar no
    servidor agora, ordenado por popularidade, com botão de Reivindicar
    direto.
  - **🏷️ Marcadas pra troca**: personagens sinalizadas com a reação de troca
    (🔄), separadas do resto da coleção.

### Classes

Toda personagem tem uma **classe** (ex.: Guerreira, Maga, Ladina), revelada
só na primeira vez que é reivindicada em qualquer servidor. Cada classe
pertence a uma de três **categorias de combate**: ⚔️ DPS, 🛡️ Tank ou
✨ Support (decidida automaticamente pelo jogo).

A cada **N personagens da mesma classe** que o jogador possui, todas as
personagens daquela classe ganham **+50 de CP** de bônus, cumulativo (2N =
+100, 3N = +150...). O bônus é por classe individual. N é **5** pra
DPS/Support, mas **2** pra Tank (2026-09-06, achado do usuário: Tank é
estruturalmente ~11x mais raro no catálogo que Support - marco menor
compensa isso sem precisar reclassificar nenhuma personagem).

Tela **"⚔️ Classes"**: mostra, por categoria (DPS/Tank/Support/Sem
categoria), o total de bônus de CP somado e quantas personagens compõem
esse total, mais uma lista de cada classe possuída com o bônus atual e o
progresso até o próximo marco (ex.: "3/5 pro próximo marco", ou "1/2" pra
uma classe Tank). Botão "🔄 Atualizar" recalcula na hora.

### Ranking

- **`/ranking`**: top 10 do servidor por quantidade de personagens
  reivindicadas.
- **Botão "Ranking" do Perfil**: seletor com 3 métricas, cada uma mostrando
  o top 25: **📚 Coleção**, **💞 Soulmates**, **🗼 Torre**.

O hub `/pandora` também mostra, direto no resumo principal, a posição do
próprio jogador no ranking de Coleção.

### Conquistas

Painel **"🏆 Conquistas"**, duas famílias:

**World Boss (registro puro, sem recompensa)** - só troféu, não paga nada:
- 🏆 Primeiro Sangue (1ª vitória), 🏆 Caçador (10), 🏆 Veterano (100), 🏆
  Lenda da Caçada (1.000).
- 1 conquista por tipo de chefe: 🐉 Caçador de Dragões, 🩸 Caçador da Noite,
  🪞 Reflexo Partido, ☠️ Além da Morte, 🔥 Cinzas às Cinzas, 🗿 Queda do
  Colosso, 🌑 Contra o Abismo, 👑 Regicídio, 🐍 Sem Cabeças, 🌌 Contra o
  Caos.
- Desempenho na luta: 🏆 Por um Fio (vencer com <5% do HP do time
  restante), 🏆 Intocáveis (vencer com 100% do HP), 🏆 Último Segundo
  (derrotar no último turno), 🏆 Ataque Total (vencer com DPS >70% do CP
  enviado), 🏆 Fortaleza (Tank é a categoria de maior CP agregado do time
  vencedor), 🏆 Sustentação (idem, mas Support).

**Colecionador (progressiva, paga WiShards)** - 5 marcos (I a V) por
família: **25 / 50 / 100 / 250 / 500 WiShards** ao cruzar cada marco.

| Família | Limiares (I a V) |
|---|---|
| 📚 Colecionador (personagens totais) | 10 / 50 / 150 / 500 / 1.500 |
| ⚪ Colecionador Comum (1⭐) | 20 / 100 / 300 / 800 / 2.000 |
| 🟢 Colecionador Incomum (2⭐) | 15 / 75 / 200 / 500 / 1.200 |
| 🔵 Colecionador Raro (3⭐) | 10 / 50 / 150 / 400 / 1.000 |
| 🟣 Colecionador Épico (4⭐) | 5 / 25 / 75 / 200 / 500 |
| 🟡 Colecionador Lendário (5⭐) | 3 / 10 / 30 / 75 / 200 |
| 💘 Caçador de Waifus (claims) | 10 / 50 / 150 / 500 / 1.500 |
| 🎲 Rolador Compulsivo (rolls) | 50 / 250 / 750 / 2.000 / 5.000 |
| ⭐ Desejo Realizado (wishlist conquistada) | 3 / 10 / 25 / 50 / 100 |
| ❤️ Vínculo Profundo (Afinidade acumulada) | 50 / 250 / 750 / 2.000 / 5.000 |
| 💞 Alma Gêmea (Soulmates) | 1 / 5 / 15 / 30 / 50 |
| 🔄 Negociante (trocas aceitas) | 5 / 15 / 50 / 150 / 400 |
| 🔀 Fusão Arcana (merges) | 5 / 15 / 50 / 150 / 400 |
| 📖 Completista (séries completadas) | 1 / 3 / 10 / 25 / 50 |
| 💰 Coleção Valiosa (valor em WiShards) | 5.000 / 25.000 / 100.000 / 500.000 / 2.000.000 |
| 🏦 Economia Ativa (WiShards movimentados) | 5.000 / 25.000 / 100.000 / 500.000 / 2.000.000 |
| 🗼 Escalador (andares vencidos) | 10 / 25 / 50 / 100 / 200 |

A checagem de marcos novos só acontece ao abrir (ou atualizar) o painel de
Conquistas, nunca automaticamente a cada roll/claim.

### Wishlist

Absorveu o antigo sistema de "Favoritos" - hoje os dois nomes se referem à
mesma lista pessoal de personagens que o jogador quer priorizar, **podendo
incluir personagens que ele ainda nem possui**.

- **Efeito no roll**: cada roll tem uma chance (20% por padrão, configurável
  0-100% por servidor) de vir de uma personagem da wishlist do jogador que
  ainda não tem dono ali. Não garante o aparecimento, só aumenta a chance.
- **Tela da Wishlist**: mesmo formato de card do "🔍 Personagem", navegando
  só pela lista de favoritos. Cada card mostra um de 3 estados: **🛒
  Disponível** (botão Comprar pelo preço da Loja), **✅ Já é sua** (CP,
  Nível, Afinidade, Upar Nível/Aumentar Afinidade/Divorciar) ou **🔒
  Possuída por outro jogador** (só tirar da wishlist ou atualizar).
  "➕ Adicionar" abre um campo multi-linha (1 nome por linha, processa
  vários de uma vez).
- Nas telas de "🔍 Personagem" e do navegador de séries também tem botão
  Favoritar/Desfavoritar direto.
- Comandos legados: `/favoritar <#id> <true/false>` e o grupo `/wishlist
  adicionar`/`remover`/`listar`.

---

## 🔍 Personagem (navegador de coleção)

Botão "Personagem" do hub - card completo de uma personagem da própria
coleção (imagem, raridade, classe, série, CP, Nível, Afinidade e, se
aplicável, andares da Torre vencidos com ela). Abre sempre na posição 1.

**Navegação**: ◀️/▶️ (uma posição), ⏮️/⏭️ (um bloco de 25), 🔎 Buscar (nome
aproximado ou posição numérica exata), menu suspenso com as 25 do bloco
atual. Rodapé sempre mostra "posição atual/total" (ex.: "43/1200").

**Ações**:
- **⬆️ Upar Nível** / **💕 Aumentar Afinidade**: abre um dropdown nativo do
  Discord listando CADA nível/afinidade possível do atual+1 até o máximo (10),
  cada opção já mostrando o custo TOTAL acumulado pra chegar ali (ex.: "Nível
  8 - Custo total: 45.000 WiShards (3 níveis, ~15.000/nível)" se você estiver
  no 5). Escolher uma opção não gasta na hora: mostra uma 2ª tela só com
  "Ir até aqui custa X - confirma?" e botões **Confirmar**/**Cancelar**. Upar
  Nível gasta WiShards; Aumentar Afinidade gasta Soulstone e nunca compra o
  status de Soulmate sozinho (isso só vem de reencontro, ao rolar de novo
  uma personagem já na Afinidade 10).
- **⭐ Favoritar/Desfavoritar**: alterna na Wishlist.
- **💔 Divorciar**: libera a personagem, devolvendo WiShards e XP de
  Progressão (Afinidade continua guardada). Pede confirmação extra se
  estiver favoritada.
- **🔄 Atualizar**: recarrega os dados do card.

**Comandos relacionados**:
- **`/personagem <nome>`**: busca por nome em todo o catálogo do jogo.
- **`/populares <quantidade>`**: lista as mais populares do catálogo
  (padrão 50, até 200), com posição no ranking geral e curtidas.
- **`/carteira [membro]`**: saldo de WiShards (próprio ou de outra pessoa).
- **`/favoritar <#id> [favoritar]`**: marca/desmarca como favorita (só
  funciona em personagem que o jogador realmente possui).
- **`/divorciar <#id> [confirmar]`**: libera personagem da coleção; recusa e
  pede `confirmar:true` se ela estiver favoritada.

---

## 💖 Waifus (Personagens Favoritas)

Botão **💖 Waifus** do hub. Até algumas personagens da coleção recebem
progressão extra de Power (CP), separada do sistema normal de Nível/
Afinidade.

**Navegador com setas + dropdown** (2026-09-06, pedido do usuário: "quero q
na propria tela de waifus... seja como a tela de personagens, q tem as
setas p ver as imagens e dados detalhados de cada uma") - mesmo espírito
do "🔍 Personagem": ◀️/▶️ passam de slot em slot (vazio ou ocupado), sempre
mostrando o card COMPLETO da personagem atual (imagem, classe, série,
vínculo de Afinidade/Soulmate) com os campos de Power/Fortalecimento/
Ascensão do slot por cima, e o rodapé "X/Y" indicando a posição. Um
dropdown "💖 Ir direto pro slot..." lista TODOS os slots de uma vez
(sempre cabe numa página só, no máximo 25) pra pular direto sem precisar
clicar ◀️/▶️ várias vezes - cada slot ocupado mostra a MESMA descrição
padrão de qualquer outro dropdown de personagem do jogo (classe, CP final,
CP base, Nível, Afinidade, ícone de categoria; o CP final já reflete o
Power do próprio slot). Não existe mais uma lista em texto separada de
um card de detalhe à parte - é uma tela só, navegável.

**Slots**: 5 gratuitos, até 20 extras - botão "Comprar slot" dentro da
PRÓPRIA tela de Waifus (2026-09-06: não existe mais uma opção redundante na
Loja pra isso, só esse caminho), total 25. Os slots 6–25 custam de 5M a
100M WiShards em progressão linear:

| Slot nº | Custo (WiShards) | Slot nº | Custo (WiShards) |
|---|---|---|---|
| 6 | 5.000.000 | 16 | 55.000.000 |
| 7 | 10.000.000 | 17 | 60.000.000 |
| 8 | 15.000.000 | 18 | 65.000.000 |
| 9 | 20.000.000 | 19 | 70.000.000 |
| 10 | 25.000.000 | 20 | 75.000.000 |
| 11 | 30.000.000 | 21 | 80.000.000 |
| 12 | 35.000.000 | 22 | 85.000.000 |
| 13 | 40.000.000 | 23 | 90.000.000 |
| 14 | 45.000.000 | 24 | 95.000.000 |
| 15 | 50.000.000 | 25 | 100.000.000 |

**Regra central: a progressão é do SLOT, não da personagem.** Colocar uma
personagem no slot não dá Power de graça - o slot guarda um progresso
próprio (Fortalecimento/Ascensão), e a personagem só se beneficia do que já
foi comprado ali, preenchendo a diferença entre o Power natural dela e o
que o slot já desbloqueou. Trocar a personagem do slot **não reseta** o
progresso: a nova ocupante herda o que já estava desbloqueado (pode até
"pular" patamares baixos se o Power natural dela já for alto; se for baixo,
para na primeira lacuna real).

**Fortalecimento**: 14 patamares fixos de 50 em 50 (300→1000), custo em
Soulstone crescente por patamar (preço cheio do patamar, não proporcional à
distância que falta):

| Patamar | Custo | Patamar | Custo |
|---|---|---|---|
| 300→350 | 50 | 650→700 | 10.000 |
| 350→400 | 100 | 700→750 | 20.000 |
| 400→450 | 250 | 750→800 | 40.000 |
| 450→500 | 500 | 800→850 | 75.000 |
| 500→550 | 1.000 | 850→900 | 150.000 |
| 550→600 | 2.500 | 900→950 | 300.000 |
| 600→650 | 5.000 | 950→1000 | 500.000 |

- **💪 Fortalecer**: abre um dropdown (2026-09-06, pedido do usuário: "o
  botao de fortalecer... tem de permitir fortalecer varios niveis por vez,
  por um dropdown igual nos outros locais, mostrando custo e qnt tenho" -
  mesmo padrão do "⬆️ Upar Nível" da seção "🔍 Personagem") listando CADA
  patamar do próximo disponível até 1000, cada opção já mostrando o custo
  TOTAL acumulado até ali (ex.: "Fortalecer até 600 - Custo total: 8.750
  Soulstone (3 patamares, ~2.916/patamar)"). Escolher uma opção mostra uma
  2ª tela só com o custo e um botão Confirmar/Cancelar antes de gastar -
  escolher a 1ª opção da lista equivale ao antigo "avançar 1 patamar",
  escolher a ÚLTIMA equivale a "gastar tudo que der pra esse slot".

**Ascensão**: disponível só depois do Fortalecimento chegar a 1000 **e** a
personagem do slot estar em Nível máximo (10) + Afinidade máxima (10) +
Soulmate ao mesmo tempo. Cada Ascensão soma **+50 de Power**, sem limite de
compras - custo começa em 600.000 Soulstone e sobe +100.000 por Ascensão
(2ª = 700.000, 3ª = 800.000...). Se a personagem do slot deixar de cumprir
os requisitos (por troca), o Power fica limitado a 1000 até alguém no slot
cumprir de novo, mesmo com Ascensões já pagas ali.

**🔄 Trocar personagem** / **➕ Escolher personagem**: abre uma janela de
texto (Modal) pra digitar o nome de quem você quer colocar no slot (pode
deixar em branco); o jogo então mostra um dropdown com até 25 personagens
da sua coleção mais parecidas com o que foi digitado (ou as 25 primeiras,
se o campo ficar vazio) pra você escolher a exata. Não reseta o
Fortalecimento/Ascensão do slot.

**🗑️ Esvaziar slot**: remove a ocupante sem apagar o Fortalecimento/
Ascensão já comprados no slot.

---

## ❤️ Séries Favoritas

Botão **❤️ Séries** do hub (ou **📚 Séries** dentro do Perfil, mesma tela).
Em vez de espalhar atenção pelo catálogo inteiro, escolhe séries
específicas pra focar e ganha bônus percentual de CP que só vale pras
personagens **daquela série**.

**Slots**: 5 gratuitos, até 20 extras - botão "Comprar slot" dentro da
PRÓPRIA tela de Séries (mesma tabela de preços da seção "💖 Waifus" acima),
total 25. Escolher/trocar/limpar é instantâneo. Digitar um nome que não
bate exatamente busca séries parecidas pra escolher a certa.

**4 marcos, +5% de CP cada, teto de +20%** (só nas personagens da série):
- **📚 Coleção Completa**: 100% do catálogo daquela série.
- **⭐ Maestria Completa**: todas as que possui no Nível máximo.
- **❤️ Afinidade Completa**: todas na Afinidade máxima.
- **💕 Soulbond Completo**: todas viraram Soulmate.

Os 3 últimos SEMPRE exigem a Coleção Completa também - faltar 1 personagem
da série no catálogo zera esses 3 marcos, mesmo com tudo mais maximizado.

**Navegador de uma série favoritada** (mesmo card do "🔍 Personagem",
percorrendo só as personagens daquela série):
- **🛒 Comprar**: compra a personagem exibida no momento (se livre).
- **🛍️ Comprar Tudo**: mostra o preço total de todas as livres da série e
  pede confirmação antes de comprar todas de uma vez.
- **⭐ Favoritar**: adiciona à Wishlist, mesmo sem possuir ainda.
- **⬆️ Maximizar Nível** / **💕 Maximizar Afinidade**: Investir em Massa
  restrito só às personagens que já possui daquela série.

---

## 👥 Party, Trocas e 🧬 Fusão

> 📋 **Formato padrão de qualquer dropdown de personagem** (2026-09-06,
> pedido do usuário: "os de personagem tem q ser igual do party" +
> "no dropdown tbm tem q mostrar a classe") - toda lista de personagem que
> aparece num select (Party, Fusão, Trocas, "🔍 Personagem"/"Trocar
> personagem", Batalha, Proteção, Revanche, Loja "Comprar") mostra a MESMA
> informação: ícone de categoria (⚔️/🛡️/✨),
> classe, raridade, e **CP base** (Power Base natural, 300-1000, só a
> popularidade da personagem importa - o número que decide quanto do
> Fortalecimento de um slot de Waifu ela já cobre sozinha, ver seção
> "💖 Waifus" abaixo) ao lado do CP final (já com todos os bônus). Quando a
> personagem tem um dono certo (Party/Fusão/Trocar/etc.), também mostra
> Nível e Afinidade; quando não tem dono fixo (Fusão - quem RECEBER, Loja
> "Comprar", Revanche - quem já pertence a outra pessoa), só classe/CP
> base/raridade, sem Nível/Afinidade (não fariam sentido ali). Antes disso,
> Trocas mostrava só nome+estrelas (bem mais pobre que o resto) - corrigido
> pra bater com todo o resto.

### Party

Botão **👥 Party** do hub (sem comando de barra próprio) - equipe de até 5
personagens, usada pra Torre e como proteção contra Fusão.

- **➕ Adicionar**: 2 passos - (1) escolhe um filtro de role (Todas/DPS/
  Tank/Support); (2) um dropdown de multi-seleção nativo do Discord mostra
  até 25 personagens fora da Party que batem com o filtro, ordenadas por
  CP (as 25 de maior CP daquele filtro, não busca por nome), e você marca
  de uma vez quantas quiser até o número de vagas livres.
- **➖ Remover** / **🗑️ Limpar tudo**: tira uma ou esvazia tudo.
- **🤖 Auto-Party** (dentro do painel da Torre): monta automaticamente a
  composição de maior CP que respeita a restrição de role do andar atual,
  substituindo a Party inteira - reversível a qualquer momento.
- Personagem na Party fica **protegida contra Fusão** (não pode ser
  escolhida pra sacrifício enquanto estiver lá).

### Trocas

Botão **🔄 Trocas** do hub - proposta bilateral em etapas: escolher com quem
negociar, o que você oferece, o que você pede, e quanto WiShards entra de
cada lado (o sistema mostra o valor de loja de cada lado e seu saldo atual
como referência). O destinatário recebe **🤝 Aceitar** / **✖️ Recusar**; ao
aceitar, tudo é revalidado (posse, saldo), então uma proposta pode falhar
se algo mudou desde a criação. Trocar com uma conta de bot é resolvido na
hora: ela aceita automaticamente se o total oferecido for pelo menos 10x o
valor de loja do que está sendo pedido a ela.

### 🧬 Fusão (Merge)

Botão **🧬 Fusão** do hub - transforma 5 personagens da mesma raridade em 1
personagem à escolha, dentro da mesma faixa de raridade:

1. Escolhe a raridade das personagens que serão sacrificadas. Só aparecem
   raridades nas quais você possui pelo menos 5 personagens.
2. Escreve os nomes das 5 personagens em campos separados. A busca usa a
   coleção inteira daquela raridade, aceita nome completo, parcial ou um erro
   pequeno de digitação e nunca repete a mesma personagem. O corte de
   similaridade é conservador porque uma escolha errada teria consequência
   permanente.
3. Se alguma das 5 tiver vínculo (Afinidade > 1), pede confirmação extra
   antes de continuar.
4. A tela mostra os 5 nomes interpretados. Depois, escolhe em outro dropdown
   com até 25 opções entre as personagens **livres** daquela raridade no
   servidor. A escolha de quem receber é sua.
5. Ao confirmar, as 5 saem da coleção e a escolhida entra, mais XP de
   Progressão proporcional à raridade sacrificada.

Se a escolhida for reivindicada por outra pessoa no meio do processo, a
Fusão é cancelada com aviso, sem perder as 5 sacrificadas.

> ⚠️ O comando de barra `/merge` está com um bug de assinatura desatualizada
> e provavelmente quebra ao ser usado - o fluxo que funciona de verdade hoje
> é só pelo botão "🧬 Fusão" do hub. Ver `TODO.md`.

---

## 🗼 Torre

Modo de progressão PvE: sobe andares usando a Party (até 5 personagens).
Cada andar exige um Power mínimo pra ser vencido - sem RNG, se a Party for
forte o suficiente (e cumprir a eventual restrição do andar), vence sempre.
Perder não tem penalidade nem cooldown.

### Como o Power (CP) de uma personagem é calculado

Em camadas, nessa ordem:
1. **Power Base** (da popularidade): comprimido numa faixa de 300 a 1.000
   (escala logarítmica - o ganho por popularidade extra vai diminuindo).
2. **Bônus de Nível**: +50 de Power fixo por nível acima do 1º (teto Nível
   10 = até +450).
3. **Multiplicador de Afinidade/Soulmate**: Soulmate = sempre 2,0x. Sem
   Soulmate, a Afinidade (1-10) dá de 1,0x a 1,9x (10% por ponto).
4. **Bônus de Progressão Global da conta**: fixo + percentual, por cima do
   resultado acima (cresce com o progresso da CONTA, não da personagem).
   O Nível de Progressão também influencia, com efeito mais discreto e
   sempre com teto, **3 outros sistemas** fora do CP (2026-09-06): um
   desconto pequeno no custo de Treinamento Global/Potencial da Coleção
   (até 25% no teto), um empurrão pequeno na chance de drop raro do World
   Boss (até +5 pontos percentuais no teto) e um empurrão pequeno nas
   odds de 4⭐/5⭐ de qualquer roll (até 3x a chance base no teto).
5. **Bônus por Classe**: a cada N personagens da mesma classe possuídas,
   TODAS dessa classe ganham +50 de Power fixo (marco N=5 pra DPS/Support;
   N=2 pra Tank - 2026-09-06, compensa a raridade estrutural de Tank no
   catálogo, ~11x menos personagens que Support).
6. **Bônus de Série Favorita**: percentual só nas personagens daquela
   série (ver seção "Séries Favoritas").
7. **Personagem Favorita** (se ocupa um slot de Waifu): o Power Base
   natural (item 1) é substituído pelo Power Base do slot (Fortalecimento/
   Ascensão) - o resto da fórmula continua igual em cima desse novo valor.

Na tela **🔍 Personagem**, o botão **📊 Detalhes CP** abre uma conta item a
item: Base natural/efetiva, Fortalecimento, Ascensão, Nível, Afinidade ou
Soulmate, Progressão, Maestria da Coleção, Série Favorita, Treinamento da
Coleção e Classe. Arcano, Militar e composição ficam de fora porque são
bônus da Party, não da personagem individual.

### Power da Party

Soma o CP dos até 5 membros, **+10% se tiver as 3 categorias juntas**
(DPS + Tank + Support), aplica o percentual do Arcano e adiciona o CP fixo
do Militar: `(soma × composição) × (1 + Arcano) + Militar`. Administração
já está incluída no valor efetivo de Arcano e Militar.

### Andares

- **Power necessário**: segue uma curva de potência, partindo de 1.000 no
  Andar 1 e chegando a 150K no Andar 400, sem fim fixo. A referência de
  balanceamento é Progressão Lv200 → Construções Lv100 → Torre andar 400.
- **Restrição de categoria**, em ciclo de 6 andares: Andar 1/7/13... sem
  restrição; 2/8/14... precisa de 1+ Tank; 3/9/15... precisa de 1+ Support;
  4/10/16... no máximo 1 Tank; 5/11/17... precisa das 3 categorias juntas;
  6/12/18... só DPS permitido.

### Recompensas por andar vencido

WiShards = `50 × andar`. XP de Progressão = `10 × andar`, ×5 em andares
"checkpoint" (múltiplos de 50).

### Botões do painel

- **Subir**: tenta o andar atual com a Party de agora, sem custo por
  tentar.
- **Subir Max**: sobe automaticamente andar por andar até perder, trocando
  a Party sozinha a cada mudança de restrição. Mostra resumo final (andares
  vencidos, WiShards/XP totais, e o motivo de ter parado).
- **Auto-Party**: monta a melhor Party pro andar atual usando toda a
  coleção.
- **Atualizar**: recarrega o preview.
- **Detalhes da Party**: abre a soma dos CPs individuais, a composição, o
  Arcano, o Militar e a fórmula exata do Power exibido.
- **Estatísticas**: top 10 de personagens que mais venceram andares.

### Chave da Torre (item)

Ao ativar, a **próxima** tentativa de andar ignora a restrição de
categoria (não reduz o Power necessário nem garante vitória). Consumida na
tentativa, vença ou perca. Só uma ativa por vez; no "Subir Max" só vale
pro primeiro andar do loop.

---

## 🏙️ Cidade

Toda personagem que o jogador possui e que **não está na Party** trabalha
sozinha na Cidade, automaticamente - a alocação é decidida pela **classe**
(a mesma que decide a categoria de combate na Torre), sem configuração
manual. Cada classe está permanentemente ligada a uma de 6 funções:
⚔️ Militar, ⚕️ Saúde, 🎭 Cultura, 📜 Administração, 🏪 Comércio, 🔮 Arcano.
Personagem sem classe revelada ainda não conta pra nenhuma.

**Marcos por Construção** (2026-09-07, substituiu de vez o "Poder da
Área"/CP-ponderado e o marco com retorno decrescente que as 3 áreas de
CP tinham desde o dia anterior) - fórmula ÚNICA pras 6 áreas, especificada
pelo usuário com exemplo numérico próprio validado 1 a 1 pra cada área:

```
marcos      = floor(personagens_na_área / 5)
bônus_marco = bônus_base_da_área × nível_da_construção
bônus_total = marcos × bônus_marco
```

Cada 5 personagens trabalhando na área vira 1 marco - **sem bônus
parcial** entre marcos e **sem retorno decrescente** (a única diminuição
de retorno do jogo continua sendo o Bônus por Classe, não a Cidade). O
Nível da Construção MULTIPLICA DIRETO o valor de cada marco (Lv10 = 10x
o valor do Lv1), exceto em **Militar e Arcano**, que usam `Lv × 0,05`
(Lv10 = 0,5x) - **o bônus já começa no Lv1** mesmo numa área sem NENHUM
Upgrade de Construção comprado ainda (2026-09-07, "tem q começar ja no
lv1" - o Lv0 zerando tudo, do palpite inicial, foi corrigido no mesmo
dia). Bônus-base por marco, no Lv1, de cada área:
⚔️ Militar +10 CP fixo · ⚕️ Saúde +0,5 Soulstone/h · 🎭 Cultura +25 XP/h ·
📜 Administração +0,005% de eficiência das outras áreas · 🏪 Comércio
+50 WiShards/h (reduzido de 250, 2026-09-07 - "a partir da decisão de
reduzir o Comércio para base 50", rendia rápido demais perto do novo
custo de Upar Construção) · 🔮 Arcano +0,01% de CP. Nunca depende de CP, só de
QUANTIDADE de trabalhadores - imune a qualquer inflação futura de fórmula
individual.

**Recursos que acumulam com o tempo** (creditados só quando o painel é
aberto, teto de acúmulo de 7 dias):
- ⚕️ Saúde → Soulstone/hora.
- 🎭 Cultura → XP de Progressão/hora.
- 🏪 Comércio → WiShards/hora.

**Bônus de CP ao vivo pra Party** (sempre ativos, aplicados direto no
Power da Party na Torre):
- ⚔️ Militar → CP fixo extra.
- 🔮 Arcano → % de CP extra.
- 📜 Administração → não afeta a Party direto, multiplica a EFICIÊNCIA das
  outras 5 áreas (mais Soulstone/XP/WiShards por hora, mais CP de
  Militar/Arcano). Não afeta o Bônus da Coleção.

**👑 Bônus da Coleção**: multiplicador global de loot, baseado no **CP
total da coleção inteira** (inclusive quem está na Party), sem teto.
`Bônus de Loot = CP da Coleção ÷ 1M`: 308M CP gera +308%, logo as
recompensas são multiplicadas por 4,08. Afeta WiShards e XP da Torre e
dos claims, além de WiShards, XP e Soulstone do World Boss. Não afeta
produção da Cidade, raridade de drops nem o Power da Party.

**Nível de Construção**: sobe o bônus de UMA área à escolha (multiplica o
bônus de cada marco daquela área, ver fórmula acima). Teto dinâmico:
começa em 50 pra todas (2026-09-07, era 10 - "P subir p 51, todas tem de
ta 50. P subir p 101, todas tem de ta em 100"), só sobe pra 100/150/...
quando TODAS as 6 áreas já bateram o teto anterior (a mais atrasada trava
as outras, incentivando desenvolvimento equilibrado). 2 caminhos pra
subir, os dois direto no painel da Cidade:
- **💰 Upar Construção** (2026-09-07, "Vamos tirar esse item da loja e
  permitir o jogador upar diretamente a construção... vamos pular essa
  parte de item do fluxo"): paga WiShards DIRETO, sem item nenhum - preço
  FIXO por faixa de 10 níveis, IGUAL pras 6 áreas, olhando o nível ALVO
  daquela área especificamente (Lv1-10 = 100K, Lv11-20 = 250K, ...,
  Lv191-200 = 5M; além do Nível 200, +500.000 por faixa nova, mesmo
  incremento das 2 últimas faixas da tabela - "eu manteria esse padrão
  para sempre").
- **🏗️ Usar Upgrade de Construção (x`N`)** (item, de graça): sobe usando o
  item "🏗️ Upgrade de Construção" - só vem de drop raro do World Boss/
  prêmio da Diária agora (2026-09-07, saiu da Loja - não é mais comprável
  com WiShards). **Só aparece se o jogador tiver pelo menos 1 guardado**
  (2026-09-07, "Podia informar quantos upgrades de construção tenho. E
  se nao tiver nenhum ja avisar de inicio, ou sequer aparecer o botão de
  usar eles" - mesmo padrão do 🎒 Inventário) - o rótulo já mostra quantos
  tem (`(x3)`), sem precisar clicar em nada.

Os 2 fluxos de uso são iguais em 2 passos: (1) um dropdown pra escolher A
ÁREA, já mostrando o nível atual de cada uma contra o teto (ex.: "⚔️
Militar (Nível 7/10)"); (2) depois de escolher, outro dropdown - mesmo
padrão do "⬆️ Upar Nível" - listando até onde subir de uma vez (custo
total acumulado ou quantos Upgrades de Construção você tem guardados,
conforme o caminho), com confirmação antes de gastar.

O painel mostra, por área: quantas personagens trabalhando e CP total
(informativo - a fórmula acima não usa CP), Nível de Construção atual (com
pips ◆/◇ além do número, 2026-09-06), bônus atual "ao vivo". 1ª fileira:
"💰 Upar Construção", "🏗️ Usar Upgrade de Construção (x`N`)" (se tiver
algum), "📈 Progressão" e "🔄 Atualizar" (nessa ordem, 2026-09-07 -
"Coloca o progressao antes do botao atualizar, na primeira fileira").
Qualquer mudança na Party/CP (montar Party, Auto-Party, upar Nível/
Afinidade, Divorciar, Fusão...) atualiza o bônus de CP da Cidade na hora,
sem precisar reabrir o painel.

**Botão de detalhe por área** (2026-09-06/07, mockup + especificação do
usuário em `PANDORA_marcos_cidade.md`): 6 botões novos no painel
principal (1 por área), cada um abre uma tela EPHEMERAL (só quem clicou
vê, o painel principal continua aberto por trás) - mesma tela pras 6
áreas, já que todas usam a mesma fórmula:
- **Trabalhando aqui**: quantos personagens trabalham na área. O CP da
  coleção aparece apenas no Bônus da Coleção, pois não participa do cálculo
  individual das estruturas.
- **Bônus atual**: o valor REAL vigente pra Party/produção.
- **Marcos**: quantos marcos concluídos + o valor de CADA marco individual
  (não o total) no Nível de Construção atual.
- **Próximo marco**: progresso atual/próximo (sempre +5 personagens) +
  quantos faltam.
- **📊 Detalhes do cálculo** (2026-09-07, "quero q as areas tenham as infos
  do calculo mais detalhadas"): 3 blocos - **Fórmula** (`B_final = M ×
  B_base × Lv × (1 + A)`; Militar e Arcano usam `B_final = M × B_base ×
  (Lv × 0,05) × (1 + A)` - Administração sai sem o termo `(1 + A)`, nunca
  cruza sobre si mesma), **Variáveis** (M/B_base/Lv/A/B_final nomeados,
  cada um com o valor atual), **Cálculo** (a conta numérica por extenso,
  ex.: "595 × 10 × 10 × (1 + 0,179) = 70,2K CP") - sem listar marcos
  individualmente, por pedido explícito do documento de especificação.

**📈 Progressão** (2026-09-07, "depois na tela de cidade vc traz um botao
de progressao, mostrando as fontes de xp acumaladas ate entao"): botão na
1ª fileira, antes do "🔄 Atualizar" (2026-09-07, "Coloca o progressao
antes do botao atualizar, na primeira fileira"), abre tela EPHEMERAL com
Nível/XP atual + quanto falta pro próximo nível, e a soma de XP creditado
por
ORIGEM (Cidade/produção, Torre/andar, Claims, Divórcio, Upar Nível,
Fusão, Marcos de coleção) desde que o ledger de XP passou a existir
(2026-09-07) - XP creditado antes disso não tem fonte discriminada, só
conta no Nível/XP totais.

---

## ⚔️ Batalha 5x5 (PvP)

Duelo 1x1 entre jogadores (ou contra conta de bot) disputado por uma
personagem específica. Quem desafia arrisca WiShards; quem defende arrisca
a própria personagem. O resultado NUNCA depende de CP/Nível/Afinidade - é
decidido por Jokenpô de categoria.

### Como desafiar

Abrir "⚔️ PvP" → Desafiar → escolher o jogador → escolher qual personagem
da coleção dele reivindicar → montar a formação (categoria de cada uma das
5 posições, livre, não depende de possuir personagens dessas categorias) →
confirmar (mostra o valor da aposta, mas ainda não desconta nada). Não dá
pra desafiar a si mesmo nem abrir novo desafio com alguém já em duelo.

### Jokenpô de categoria

DPS vence Support; Support vence Tank; Tank vence DPS; mesma categoria
contra mesma categoria sempre empata. CP/Nível/Afinidade nunca entram.

### Aposta de personagem

Preço de loja da raridade × 2: 1⭐ 500, 2⭐ 1.000, 3⭐ 2.000, 4⭐ 5.000, 5⭐
10.000 WiShards. Só é DESCONTADO se o desafiante perder (pra ele: vencer
não custa nada, a personagem é transferida na hora; pra ele perder: paga o
valor total ao defensor, que mantém a personagem). Soulmate é sempre
protegida contra desafio; item Proteção também protege enquanto ativo.

### Defesa

O defensor vê só quantos DPS/Tank/Support o desafiante usou (não a ordem
nem quem é quem) e escolhe:
- **Montar Defesa**: escolhe a categoria das próprias 5 posições; resolve
  assim que a 5ª é escolhida.
- **Recusar**: cancela (nada foi cobrado ainda, então nada é devolvido).

### Resolução (5 rodadas, melhor de 3)

Posições reveladas uma a uma; termina assim que um lado fecha 3 vitórias.
Se ninguém fechar 3 depois das 5: vence quem tiver mais vitórias; empate
de verdade (ex.: 2x2) o **desafiante vence automaticamente** (compensação
por o defensor ver a composição dele antes de montar a própria).

### Auto-Defesa

Toggle no painel PvP (desligado por padrão) - resolve desafios recebidos
na hora, escolhendo automaticamente a categoria que vence cada categoria
do desafiante (ordem embaralhada entre as 5 posições). Sem resposta manual
nem Auto-Defesa em 10 minutos, o sistema aplica a mesma lógica sozinho.
Desafiar uma conta de bot funciona igual, resolvido na hora.

### Itens e limites

- **Revanche**: desafia de novo por uma personagem perdida, ignorando
  cooldown e limite diário de defesas do dono.
- **Proteção**: protege 1 personagem contra qualquer desafio enquanto
  ativa.
- **Cooldown de 24h entre o mesmo par** desafiante/defensor: desligado por
  padrão (config de servidor, `/pandora_admin cooldown_batalha`).
- **Limite diário de defesas**: sempre ativo, 3 desafios recebidos por dia
  por jogador (não configurável).

---

## 🌍 World Boss

Evento cooperativo de servidor: todos que entrarem formam UM time contra
um chefe gigante. CP importa aqui, sempre agregado por categoria (soma de
CP de todos os DPS do time, todos os Tanks, todos os Supports).

### Quando acontece

4 vezes por dia, horários fixos de Brasília: **10h, 14h, 18h, 22h**. Ao
aparecer, abre janela de inscrição de **10 minutos**.

### Como entrar

No painel "🐉 World Boss", clicar numa categoria (DPS/Tank/Support)
adiciona ela ao conjunto permitido; clicar de novo remove (alternador). O
sistema escolhe automaticamente sua personagem de **maior CP** entre as
categorias permitidas. **Entrada Automática**: preferência configurável
pra entrar em todo evento futuro sem abrir o painel na hora (só aplicada
se ainda não entrou manualmente naquele evento).

### Fechamento das inscrições

Ao fechar os 10 minutos: jogadores com Entrada Automática entram; se
nenhum humano participou, o evento é cancelado; senão, **2 bots** sempre
entram pra completar o time (priorizam categoria sem nenhum humano, ou a
de menor CP agregado; CP do bot = média do CP dos humanos; bots não
recebem recompensa). CP de DPS vira dano/turno do time, CP de Tank vira HP
máximo, CP de Support vira cura/turno (crescimento desacelerado).

### Dificuldade

Sorteada entre 5 níveis (multiplicam HP/ATK do chefe): 🟢 Fácil, 🔵 Normal,
🟠 Difícil (referência), 🔴 Elite, 🟣 Pesadelo. O painel mostra o "CP
recomendado por categoria" pra aquele chefe/dificuldade.

### Combate

Turnos automáticos, 1 por minuto, até 60 turnos (1 hora), com ~±10% de
variação aleatória no dano/cura/ataque por turno. Termina em vitória (HP
do chefe = 0), derrota (HP do time = 0) ou expira (60 turnos sem decisão).

### Os 10 chefes

- 🐉 **Dragão Ancião**: ataque cresce 10%/turno, composto.
- 🩸 **Rei Vampiro**: recupera 30% do próprio dano causado como cura.
- 🪞 **Doppelgänger**: copia a categoria dominante do time e ganha
  vantagem contra ela.
- ☠️ **Senhor da Morte**: a cada 3 turnos, tira 30% do HP máximo do time
  direto.
- 🔥 **Fênix Eterna**: pode renascer até 2x (70% HP na 1ª, 40% na 2ª, ATK
  maior a cada vez).
- 🗿 **Colosso de Pedra**: barreira de HP separada; ATK reduzido enquanto
  ela existir, maior depois que cair.
- 🌑 **Devorador do Abismo**: reduz dano e cura do time de forma acumulada
  a cada turno.
- 👑 **Rei Demônio**: alterna 3 posturas por turno (reduz dano do time /
  aumenta o próprio ATK / reduz cura do time).
- 🐍 **Hidra**: 3 cabeças destruídas em 75%/50%/25% de HP, cada uma viva
  dá um efeito (ATK, regeneração, ou redução de cura do time).
- 🌌 **Deus do Caos**: sorteia um efeito aleatório por turno (dano/cura/HP
  do time, ATK do chefe, cura do chefe, ataque duplo de qualquer lado).

### Recompensas por vitória (só humanos)

Por jogador: 500 WiShards, 200 XP, 20 Soulstone, chance de 5⭐ garantida
(sorteada só entre 5⭐ que ninguém possui no servidor ou que já são suas) e
15% de chance de item raro extra (Proteção/Revanche mais comuns, depois
Chave da Torre/Upgrade de Construção, depois Chamado, e por último Roll
Permanente/Claim Permanente).

### Itens ligados

**📯 Chamado**: escolhe qual chefe aparece no próximo horário fixo do
servidor (dificuldade continua sorteada normalmente).

---

## Auto-colecionador / Auto-claim

### Auto-colecionador (contas de bot)

As contas de bot do ecossistema (**GAIA**, papel "principal", e **ERIS**,
papel "música") jogam sozinhas, como mais um jogador:
- GAIA rola no minuto **:05** de cada hora, decide o que reivindicar no
  **:10**.
- ERIS rola no **:30**, decide no **:35**.
- Rolls = `rolls_por_ciclo` configurado no servidor (padrão 50), sem
  nenhum bônus/upgrade pessoal.
- Aparecem como um roll normal (mesmos cards/botões) - qualquer jogador
  humano pode reivindicar antes.
- Só depois de 5 minutos a conta reivindica, entre as que sobraram sem
  dono, priorizando as MAIS POPULARES (não a maior raridade), até o limite
  de claims do servidor.

### Auto-claim (toggle de jogador humano)

Ligado/desligado no Perfil ("🤖 Auto-claim"). Ativo:
- Todo dia, no minuto **:50**, rola automaticamente usando a cota real do
  jogador, só se ele ainda não tiver mexido no próprio ciclo de rolls
  naquele período.
- No **:55**, reivindica automaticamente gastando os claims reais dele,
  sempre a mais popular entre as disponíveis, até acabar.
- É a mesma cota/cooldown normal sendo usada automaticamente, não um bônus
  à parte.

---

## `/pandora_admin` (configuração do servidor)

Grupo restrito a administradores do servidor. Cada subcomando ajusta uma
regra naquele servidor:

- **`nsfw`**: liga/desliga personagens NSFW nos rolls.
- **`rolls`**: quantos rolls por jogador, a cada quantos minutos.
- **`claims`**: quantos claims por jogador, a cada quantos minutos.
- **`duracao_card`**: por quantos segundos o botão/reação de Reivindicar
  fica ativo.
- **`max_puxada`**: máximo por comando de roll com quantidade explícita
  (não afeta quantidade:0 = máximo).
- **`wishlist_chance`**: chance (%) de um roll vir da wishlist de quem
  rolou.
- **`cooldown_batalha`**: liga/desliga cooldown de 24h entre desafios ao
  mesmo alvo (desligado por padrão).
- **`canal`**: canal onde o auto-colecionador (GAIA/ERIS) posta os
  próprios rolls.
- **`ver`**: mostra a configuração atual inteira do servidor.
- **`bloquear_serie`** / **`desbloquear_serie`**: impede/libera personagens
  de uma série/obra específica nos rolls desse servidor.
- **`resetar_rolls`** / **`resetar_claims`**: força o ciclo de alguém a
  recarregar na hora, sem esperar o horário fixo.
- **`dar_personagem`**: dá uma personagem LIVRE pra alguém direto (sem
  gastar roll/claim).
- **`validar_classes`**: revisa personagens já reivindicadas ainda sem
  classe/categoria de combate e tenta classificar agora (até 100 por
  chamada; tem opção pra revisar só as que já falharam antes numa fila
  separada).
- **`definir_afinidade`**: define manualmente a Afinidade (0-10) de
  alguém com uma personagem, sem esperar reencontros.

---

## Comandos avulsos

- **`/colecao_disponiveis [raridade]`**: lista até 10 personagens que
  apareceram em rolls recentes, ainda sem dono, ordenadas por popularidade
  (opcionalmente filtrando por raridade), com botão de Reivindicar direto
  pra cada uma.
- **`/carteira [membro]`**: saldo de WiShards (próprio ou de outra
  pessoa).
- **`/merge`**: ver aviso na seção "🧬 Fusão" acima (comando com bug
  conhecido - usar o botão do hub em vez disso).
