# Fórmulas e proporções de balanceamento

Documento de referência das fórmulas **ativas** que afetam progressão, CP, Cidade, Torre e loot. Percentuais abaixo são escritos de forma humana: `+10% = 0,10` no código.

## Régua de progressão esperada

Esta é a proporção de referência para uma conta em progresso equilibrado:

| Progressão da conta | Construções esperadas | Andar da Torre esperado |
| ---: | ---: | ---: |
| 25 | 12–13 | 50 |
| 50 | 25 | 100 |
| 100 | 50 | 200 |
| 150 | 75 | 300 |
| 200 | 100 | 400 |

Em forma de fórmula:

```text
nível esperado de Construção = Progressão ÷ 2
andar esperado da Torre      = Progressão × 2
```

É uma régua de balanceamento, não um bloqueio: uma conta pode estar acima ou abaixo dela. Todas as seis construções devem acompanhar níveis próximos; para atravessar cada novo bloco de 50, todas precisam ter completado o bloco anterior.

## CP individual da personagem

### 1. Base e desenvolvimento próprio

```text
Base natural = 300 + 700 × log(1 + Popularidade) / log(1 + MaiorPopularidadeDoCatálogo)
Bônus de nível = (Nível - 1) × 50
Base desenvolvida = Base efetiva + Bônus de nível
```

A Base natural fica sempre entre 300 e 1.000. Caso a personagem ocupe um slot de Personagem Favorita, a **Base efetiva** substitui a Base natural:

```text
Base efetiva = Base após Fortalecimento + (Ascensão × 50)
```

Fortalecimento compra os 14 degraus do slot, de 300 até 1.000, sempre em ordem. A Base natural não pula degraus: uma personagem com Base 951 ainda precisa comprar do primeiro patamar até 1.000, embora os patamares até 950 não alterem seu CP. Ascensão só entra depois do slot chegar a 1.000 e exige Nível 10, Afinidade 10 e Soulmate. Nível, Afinidade e Soulmate continuam sendo aplicados normalmente depois disso. Tanto Fortalecimento quanto Ascensão permitem escolher um alvo no dropdown: o jogo soma todos os degraus intermediários e confirma uma compra única. Para Ascensão, o custo do nível `n` é `600.000 + (n - 1) × 100.000 Soulstone`.

### 2. Vínculo

```text
Multiplicador de vínculo = 2,0                          se Soulmate
                           1,0 + (Afinidade - 1) × 0,10  caso contrário

CP vinculado = Base desenvolvida × Multiplicador de vínculo
```

Soulmate **substitui** o multiplicador de Afinidade; os dois não se somam. Afinidade 1 é `×1,0`, Afinidade 10 é `×1,9`.

### 3. Conta, Série e Classe

```text
Fixo da conta = (Progressão × 10) + (Treinamento da Coleção × 25)

% da conta = (floor(Progressão / 5) × 1%)
              + (Maestria da Coleção × 2%)

CP individual = (CP vinculado × (1 + % da conta) × (1 + % da Série))
                + Fixo da conta
                + Bônus da Classe
```

Os percentuais só multiplicam a parte desenvolvida da personagem. Os bônus fixos de conta e de Classe são adicionados no final para preservar a Base como um fator importante de CP.

Uma Série Favorita concede `+5%` por marco, até `+20%` naquela série:

| Marco da série | Bônus |
| --- | ---: |
| Coleção completa | +5% |
| Todas no Nível máximo | +5% |
| Todas na Afinidade máxima | +5% |
| Todas Soulmate | +5% |

Os três últimos só contam se a coleção completa da série também foi obtida.

O Bônus de Classe é fixo por personagem da mesma classe. A cada cinco personagens, o valor de cada marco diminui por faixa: 1–100 personagens = `+5 CP/marco`; 101–250 = `+4`; 251–500 = `+3`; 501–1.000 = `+2`; acima de 1.000 = `+1`. As faixas são cumulativas: um marco antigo não perde valor.

### Exemplo de Megumin

Com Base 1.000, Nível 10, Soulmate, Progressão 200, Treinamento 200, Maestria 200, Série Favorita +15% e Classe +343:

```text
Base desenvolvida = 1.000 + 450 = 1.450
CP vinculado      = 1.450 × 2,0 = 2.900
% da conta        = 40% + 400% = 440% = ×5,4
CP multiplicável  = 2.900 × 5,4 × 1,15 = 18.009
Fixos             = (200 × 10) + (200 × 25) + 343 = 7.343
CP individual     = 18.009 + 7.343 = 25.352
```

O valor real pode variar quando a Base natural, Série, Classe, Favorita ou níveis forem diferentes. A tela `📊 Detalhes CP` usa os números reais da personagem selecionada.

## Power da Party e Torre

```text
Bônus de composição = +10% se houver DPS + Tank + Support

Power da Party = (Soma dos CPs individuais × (1 + composição))
                  × (1 + Arcano)
                  + Militar
```

Administração já está incorporada nos valores finais de Arcano e Militar. O Bônus da Coleção **não** entra mais no Power da Party.

```text
Power necessário do andar = arredondar_para_dez(1.000 × (1 + (Andar - 1) / 13,31847455)^1,45970145)
WiShards da Torre          = arredondar(50 × Andar × (1 + Bônus de Loot))
XP da Torre                = 30 × Andar × (1 + Bônus de Loot)
```

O XP da Torre é multiplicado por 5 nos andares checkpoint (múltiplos de 50). O bônus de loot também afeta esse XP. A vitória é determinística: precisa atingir o Power e cumprir a restrição de categoria do andar. A curva de CP foi calibrada para `100K` no andar 300 e `150K` no 400: andar 50 pede 9,51K, 100 pede 22,47K e 200 pede 56,93K.

## Cidade

Personagens fora da Party trabalham automaticamente em sua área conforme a Classe. Em qualquer área, cinco trabalhadores formam um marco:

```text
M = floor(Personagens na área / 5)
```

Administração não recebe seu próprio bônus. Todas as demais áreas recebem Administração depois de seu cálculo-base:

```text
Bônus final da área = Bônus-base da área × (1 + Administração)
```

### Fórmulas-base por área

| Área | Fórmula antes da Administração | Resultado |
| --- | --- | --- |
| Administração | `M × 0,005% × Lv` | eficiência das outras áreas |
| Militar | `M × 10 CP × (Lv × 0,05)` | CP fixo da Party |
| Arcano | `M × 0,01% × (Lv × 0,05)` | % de CP da Party |
| Comércio | `M × 50 × Lv` | WiShards/h |
| Saúde | `M × 0,5 × Lv` | Soulstone/h |
| Cultura | `M × 25 × Lv` | XP de Progressão/h |

Portanto, para Militar e Arcano a fórmula completa é:

```text
B_final = M × B_base × (Lv × 0,05) × (1 + A)
```

Para Comércio, Saúde e Cultura é:

```text
B_final = M × B_base × Lv × (1 + A)
```

Para Administração é:

```text
A = M × 0,005% × Lv
```

O nível efetivo mínimo é 1 mesmo antes de comprar um upgrade. Recursos por hora acumulam quando a Cidade é aberta, até no máximo 168 horas (sete dias) desde a última coleta.

### Proporção entre as seis áreas

Com o mesmo número de marcos e o mesmo nível de Construção, esta é a proporção por **um marco** antes de Administração:

| Área | Lv1 | Lv100 | Curva de nível |
| --- | ---: | ---: | --- |
| Administração | +0,005% | +0,5% | `Lv` |
| Militar | +0,5 CP | +50 CP | `Lv × 0,05` |
| Arcano | +0,0005% | +0,05% | `Lv × 0,05` |
| Comércio | +50 WiShards/h | +5.000 WiShards/h | `Lv` |
| Saúde | +0,5 Soulstone/h | +50 Soulstone/h | `Lv` |
| Cultura | +25 XP/h | +2.500 XP/h | `Lv` |

As unidades são diferentes e não devem ser comparadas como se fossem o mesmo recurso. A proporção intencional é:

- Comércio é a principal fonte de WiShards e vale 100 vezes Saúde em
quantidade numérica por marco, pois WiShards sustentam custos altos.
- Cultura vale 50 vezes Saúde em quantidade numérica por marco, porque XP
alimenta a Progressão contínua da conta.
- Militar e Arcano têm a curva de nível reduzida a 5% para serem reforços
relevantes de Party sem ultrapassarem o investimento individual.
- Administração é multiplicador transversal: quanto mais áreas produtivas,
maior o valor relativo dela. Ela não se multiplica a si própria, evitando crescimento exponencial interno.

## Bônus da Coleção e loot

O CP total de **toda** a coleção (inclusive Party) vira bônus de loot, linear e sem teto:

```text
Bônus de Loot = CP total da coleção ÷ 1.000.000
Loot final    = Loot base × (1 + Bônus de Loot)
```

Exemplo: `308M CP = +308% = ×4,08`. O multiplicador vale para WiShards e XP da Torre/claims e para WiShards, XP e Soulstones do World Boss. Não altera CP, produção por hora, chance de item ou raridade.

## Favoritos, Wishlist e recompensas da Torre

**Favoritos** é a lista pessoal ilimitada de personagens de que o jogador gosta. Ela não altera rolls e não consome slots. A **Wishlist** é o sistema de slots que antes se chamava Waifus: cada slot pode apontar para qualquer personagem do catálogo, inclusive uma ainda não adquirida. Enquanto estiver livre, ela é um alvo dos rolls; depois de adquirida, o mesmo slot fica marcado com 🎴 e libera Fortalecimento e Ascensão. A progressão continua pertencendo ao slot, não à personagem.

Wishlist e Séries Favoritas começam com cinco slots gratuitos. A Torre libera um slot adicional a cada 25 andares vencidos, até o teto de 25 slots no andar 500. O andar mostrado no painel é o próximo desafio; por isso, a recompensa de um marco é recebida após vencer aquele andar. Slots pagos antes desta mudança são preservados até a Torre alcançar a mesma quantidade; não há novas compras de slots.

```text
Slots da Wishlist = min(25, 5 + floor(Andares vencidos / 25))
```

A chance de um roll substituir a personagem sorteada por uma personagem elegível da Wishlist é a chance configurada pelo servidor mais o bônus da Torre. A cada cinco andares vencidos que não seja múltiplo de 25, o bônus recebe `+0,25 ponto percentual`; ele para em `+20 pontos percentuais` no andar 500.

```text
Bônus da Torre = (floor(min(Andares vencidos, 500) / 5)
                  - floor(min(Andares vencidos, 500) / 25)) × 0,25%

Chance final de Wishlist = min(100%, Chance base do servidor + Bônus da Torre)
```

Com chance-base de 1%, o andar 500 chega a `1% + 20% = 21%`. A Torre não aumenta a chance de obter 5★: primeiro o jogo sorteia a raridade normal; só então, se o efeito da Wishlist ativar, ele seleciona aleatoriamente uma personagem dos slots de Wishlist **da mesma raridade**. Personagens já adquiridas continuam elegíveis: o resultado é um reencontro, que aumenta Afinidade e, ao chegar nela novamente com Afinidade 10, a torna Soulmate. Uma personagem não pode ocupar dois slots ao mesmo tempo.

## Ritmo de Progressão por XP

O XP necessário para o próximo nível é recalculado para cada conta a partir da produção atual de Cultura da Cidade:

```text
XP para o próximo nível = XP de Progressão/h da Cultura × 6
```

Assim, mantendo a produção da Cidade constante, cada nível leva aproximadamente seis horas. Outras fontes de XP continuam acelerando o progresso, mas não aumentam o requisito do próximo nível.

## Custos de Construção

Cada nível custa o preço da faixa de dez do seu nível-alvo. De Lv1–10, o custo é 100K por nível; Lv11–20 custa 250K; a tabela segue até Lv200 (5M por nível em Lv191–200). Depois disso, cada faixa de dez acrescenta 500K ao custo unitário da faixa anterior.

Esta curva existe para que Construções acompanhem a régua `Progressão ÷ 2`, sem tornar uma área isolada a fonte dominante de evolução.

## Onde conferir no jogo

- `📊 Detalhes CP`, no card de uma personagem: fórmula individual real.
- `📊 Detalhes da Party`, na Torre: fórmula real da Party.
- Botões das áreas da Cidade: trabalhadores, marcos, bônus atual e cálculo
específico da área.

## Simulador local de Progressão

`scripts/simular_balanceamento_progressao.py` usa a distribuição atual de trabalhadores como referência e preserva as proporções de Construção (`Progressão ÷ 2`) e Torre (`Progressão × 2`). Sem `--aplicar`, ele só simula e não altera o banco.

```powershell
python scripts/simular_balanceamento_progressao.py --nivel 200
python scripts/simular_balanceamento_progressao.py --niveis 25,50,100,150,200
python scripts/simular_balanceamento_progressao.py --nivel 150 --colecao 6000 --cp-colecao 90000000
python scripts/simular_balanceamento_progressao.py --nivel 150 --aplicar --guild-id 1388541192806989834 --user-id 304469035607916545
python scripts/simular_balanceamento_progressao.py --tabela-real --guild-id 1388541192806989834 --user-id 304469035607916545 --niveis 10,25,50,100,150,200
```

Com `--aplicar`, o script cria uma cópia consistente do banco antes de ajustar somente Progressão, Treinamento da Coleção, Maestria da Coleção, seis Construções e Torre. Personagens, coleção, Party, afinidade, Soulmate, favoritas, moedas e itens não são modificados. Por padrão, ele assume um claim por hora e projeta coleção/CP de forma linear a partir do perfil de referência. Esses parâmetros e a Party podem ser sobrescritos para testar cenários reais ou hipóteses mais conservadoras.

`--tabela-real` é estritamente de leitura: preserva a Party, a coleção e os trabalhadores reais da conta e entrega as colunas de CP e produção para os níveis escolhidos.
