<p align="center">
  <img src="assets/icone_pandora.png" alt="Project PANDORA" width="180">
</p>

# Project PANDORA

Jogo de coleção e progressão de personagens com rolls, claims, afinidade, economia, party, batalhas e eventos.

## Recursos principais

- catálogo, coleção, rolls, claims, raridades e pity;
- personagens duplicadas, afinidade, favoritas e Soulmate;
- classes de combate, CP e progressão individual;
- WiShards, Soulstones, XP, loja, itens, fusão e trocas;
- Party de cinco personagens, Torre e Cidade;
- batalha 5x5 com aposta e World Boss cooperativo;
- conquistas e marcos de coleção e progressão.

O PANDORA é um pacote Python usado dentro de um bot. Ele não abre um processo ou uma porta própria, o que mantém as ações do Discord dentro do limite de resposta.

## Origem do nome

PANDORA vem de Pandora (Πανδώρα), personagem da mitologia grega ligada ao mito da Caixa de Pandora. Ela recebeu dos deuses um recipiente fechado e, ao abri-lo, libertou o que estava guardado. No fundo permaneceu Elpis, geralmente entendida como a esperança.

Cada roll segue a mesma ideia: abrir algo sem saber qual personagem será revelada. A relação central é **Pandora → recipiente fechado → abertura → surpresa → gacha**.

A ligação continua depois do roll. A personagem entra na coleção, aumenta o CP, recebe uma classe e pode fortalecer a Party, a Cidade, a Torre, as batalhas e outros sistemas. O ciclo pode ser resumido como **abrir → descobrir → colecionar → desenvolver → usar**. A própria coleção também representa a caixa, pois tudo o que existe dentro dela alimenta o restante do jogo.

### Identidade visual

A logo mostra três cartas com silhuetas de personagens. A carta central recebe destaque com uma personagem coroada, enquanto as silhuetas representam o conteúdo ainda oculto antes da revelação.

As cartas reúnem personagens, raridade, gacha e coleção. O dourado sugere recompensa e raridade; o roxo e o preto dão ao PANDORA uma identidade própria de jogo. A Caixa de Pandora aparece no ato de revelar o conteúdo: **fechado → abrir → descobrir**.

Em uma frase: **PANDORA transforma a curiosidade sobre a próxima abertura em um mundo construído a partir da coleção.**

## Requisitos

- Python 3.11 ou mais recente;
- um cliente que conecte o pacote ao Discord.

## Instalação e uso

Instale o pacote como dependência local e importe os módulos necessários:

```python
from pandora import db, gacha, paineis

db.inicializar()
```

## Integrações com outros projetos

- **ERIS:** oferece os comandos, botões e mensagens do Discord usados para jogar.
- **GAIA:** classifica personagens e cria textos especiais com IA. Quando ela está desligada, o sistema usa respostas simples e mantém as regras do jogo ativas.

Para copiar dados de uma instalação antiga do ERIS:

```powershell
python scripts/migrar_de_eris.py
```

O script só lê o banco de origem e pode ser executado mais de uma vez.

## Documentação

- [Funcionalidades](docs/FUNCIONALIDADES.md)
- [Arquitetura](docs/ARQUITETURA.md)
- [Pendências](docs/TODO.md)
- [Especificações](docs/specs/)
- [Histórico de versões](CHANGELOG.md)
- [Padrão de documentação](docs/PADRAO_DOCUMENTACAO.md)

## Situação atual

O pacote está em uso pelo ERIS. As validações pendentes e os próximos ajustes ficam em `docs/TODO.md`.
