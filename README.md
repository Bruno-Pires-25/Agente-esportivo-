# Agente de análise esportiva — Brasileirão Série A

Agente de linha de comando que estima probabilidades de jogos do Brasileirão,
compara com as odds da sua casa de apostas e aponta onde o mercado está pagando
mais do que deveria.

Roda com **Python 3.11+ e nada além da biblioteca padrão**. Nenhum `pip install`
é necessário para o funcionamento principal.

```bash
python -m agente_esportivo tabela --desde 2024
python -m agente_esportivo prever Palmeiras Flamengo
python -m agente_esportivo rodada --arquivo dados/proxima_rodada.csv --banca 500
python -m agente_esportivo backtest
```

---

## O que ele faz

```
$ python -m agente_esportivo prever Botafogo Palmeiras

Botafogo-RJ  x  Palmeiras
=========================
Gols esperados: Botafogo-RJ 1,19 x 1,07 Palmeiras   |   Placar mais provavel: 1-1

Probabilidades (modelo combinado)
  Vitoria Botafogo-RJ          #########...........  42,9%   odd justa 2,33
  Empate                       ######..............  27,9%   odd justa 3,59
  Vitoria Palmeiras            ######..............  29,3%   odd justa 3,42
```

Além do 1X2, o agente calcula a matriz completa de placares — e dela saem
over/under, ambas marcam, dupla chance, handicap asiático e placar exato.

| Comando | Para quê |
|---|---|
| `tabela` | Classificação, com recorte `--mando casa` / `--mando fora` |
| `ranking` | Força de cada time: Elo + índices de ataque e defesa |
| `time <nome>` | Dossiê: posição, forma, sequências, desempenho por mando, últimos jogos |
| `prever <casa> <fora>` | Análise completa de um confronto |
| `rodada --arquivo x.csv` | Vários jogos de uma vez, com resumo comparativo |
| `odds` | Lê odds da casa de apostas e procura valor |
| `backtest` | Validação walk-forward contra a temporada real |
| `exportar` | Reexporta a base no formato canônico |
| `aovivo` | Reprecifica um jogo em andamento pelo placar e pelo minuto |
| `combinar` | Avalia uma múltipla com correlação exata entre as pernas |
| `sugerir` | Monta combinadas com as seleções mais prováveis da rodada |
| `times` | Lista os times da base |

E `python ferramentas/gerar_painel.py` gera o painel web (veja abaixo).

Qualquer comando aceita `--json` para consumo por outro programa.

---

## Como o modelo funciona

Dois modelos rodam em paralelo, porque erram de maneiras diferentes:

**Elo adaptado a futebol** (`elo.py`) — rating incremental, com bônus para o
mandante, fator K amplificado pela margem de gols (goleada move mais que vitória
magra) e probabilidade de empate modelada explicitamente: `P(empate)` é uma
gaussiana centrada na diferença zero, distribuída de forma consistente com o
score esperado (`E = P(casa) + P(empate)/2`). O Elo puro devolve só o score
esperado, que sozinho não separa 1X2.

**Dixon-Coles** (`poisson.py`) — cada time tem força de ataque e de defesa
estimadas por máxima verossimilhança ponderada. Gols do mandante seguem
`Poisson(mu × ataque_casa × defesa_fora × mando)`, com:

- correção de Dixon-Coles para placares baixos (0-0, 1-0, 0-1, 1-1), que o
  Poisson puro subestima — o `rho` é ajustado por busca em grade na própria base;
- decaimento exponencial: uma partida de 730 dias atrás pesa metade de uma de
  hoje.

As probabilidades 1X2 dos dois são combinadas (peso 0,40 para o Elo); os
mercados de gols saem exclusivamente da matriz de placares do Dixon-Coles.

### Os parâmetros não foram chutados

`peso_elo = 0,40` e `meia_vida = 730 dias` saíram de uma varredura com validação
walk-forward, medida em duas temporadas separadas:

| peso_elo | meia-vida | ganho em 2023 | ganho em 2024 |
|---|---|---|---|
| 0,0 | 365 | 3,30% | 3,16% |
| 0,2 | 730 | 3,55% | 3,42% |
| **0,40** | **730** | **3,42%** | **3,80%** |
| 0,5 | 730 | 3,30% | 3,93% |

A superfície é plana, então a escolha foi pelo par mais estável nas duas
temporadas, não pelo máximo de uma delas.

---

## O que o backtest diz

`backtest` faz validação walk-forward: para prever o jogo do dia X, o modelo só
enxerga partidas anteriores a X. Treinar com a temporada inteira e depois
"prever" jogos dela produz números lindos e inúteis.

```
$ python -m agente_esportivo backtest

Partidas avaliadas: 1246  (aquecimento de 380 jogos)

Previsor         RPS  Log loss   Brier  Acertos
------------  ------  --------  ------  -------
Modelo        0,2121    1,0293  0,6166    48,5%
Base da liga  0,2217    1,0585  0,6385    47,6%

  Ganho sobre a base da liga: 4,3%

Calibracao (o modelo cumpre o que promete?)
Faixa       n  Previsto  Observado
--------  ---  --------  ---------
20%-40%   279     37,6%      37,3%
40%-60%   762     48,5%      48,4%
60%-80%   201     65,6%      64,2%
```

Duas leituras honestas desses números:

- **A calibração é boa.** Quando o agente diz 48,5%, acontece 48,4%. É o que mais
  importa para apostar: probabilidade que corresponde à realidade.
- **O ganho sobre a base é modesto** — 4,3% de RPS. É o que um modelo honesto,
  alimentado só com placares públicos, consegue no Brasileirão. Quem promete
  muito mais que isso está com vazamento de dados no backtest ou mentindo.

O RPS (Ranked Probability Score) é a métrica certa aqui porque entende a ordem
dos resultados: prever vitória do mandante e dar empate erra menos do que dar
vitória do visitante. Acurácia sozinha não diz nada — o favorito vence pouco
mais de 45% das vezes no Brasileirão.

---

## Dados

`dados/brasileirao_2021_2024.csv` traz **1.632 partidas reais** da Série A
(2021–2024, 28 clubes), derivadas das súmulas da CBF via o dataset público
[adaoduque/Brasileirao_Dataset](https://github.com/adaoduque/Brasileirao_Dataset).

Para atualizar ou buscar mais temporadas:

```bash
python ferramentas/baixar_brasileirao.py --desde 2019 --saida dados/brasileirao.csv
python -m agente_esportivo --dados dados/brasileirao.csv tabela
```

O leitor de CSV aceita tanto o cabeçalho em português quanto o formato
football-data.co.uk (`Date,HomeTeam,AwayTeam,FTHG,FTAG`), então dá para apontar
para outra base sem converter nada. A coluna `competicao` é rotulada pelo ano do
calendário — jogos de janeiro/fevereiro de 2021 são, na verdade, o fim da
temporada 2020.

---

## Odds da casa de apostas

O agente lê odds de três jeitos. **A maioria das casas proíbe automação nos
termos de uso e bloqueia contas que detecta como robô** — por isso o desenho
aqui nunca digita sua senha em lugar nenhum, e o modo recomendado é o que não
automatiza nada.

### 1. Copiar e colar (sem automação, sempre funciona)

Abra a casa no navegador, selecione a lista de jogos com as três odds visíveis,
copie e salve em um `.txt` (ou salve a página com Ctrl+S):

```bash
python -m agente_esportivo odds --arquivo odds.txt --banca 500
```

O parser entende os dois layouts usados na prática (nomes e odds em linhas
separadas, ou o jogo inteiro em uma linha) e reconhece `Mais de 2.5`,
`Menos de 2.5` e `Ambas marcam` quando aparecem por perto.

### 2. Navegador que você já deixou logado

Você faz o login manualmente — com 2FA, captcha, o que for — e o coletor apenas
lê o texto da aba aberta:

```bash
# 1. abra o Chrome com a porta de depuracao ligada e faca login normalmente
google-chrome --remote-debugging-port=9222 --user-data-dir=~/.perfil-odds

# 2. com a pagina de jogos aberta:
pip install playwright && playwright install chromium
python -m agente_esportivo odds --cdp http://localhost:9222 --banca 500
```

`python -m agente_esportivo odds --instrucoes` imprime o passo a passo para
Linux, macOS e Windows. O Playwright é a **única** dependência opcional do
projeto, usada só por este modo.

### 3. Perfil persistente

`--perfil ~/.perfil-odds` abre um Chrome próprio, com sessão que sobrevive entre
execuções. Use `--esperar` para o script pausar enquanto você faz login.

Em todos os modos, nomes de clube são reconciliados contra a base
(`nomes.py`): "Atlético Mineiro", "Galo" e "Atletico-MG" viram o mesmo time — e
"Athletico Paranaense" **não** é confundido com o Galo. Use `--salvar odds.csv`
para guardar o que foi coletado e `--estrito` para descartar times não
reconhecidos.

---

## Jogo em andamento

Um jogo 1-0 aos 70 minutos não é o jogo que começou 0-0: o que resta é uma
partida de 20 minutos com o placar já no bolso de alguém. O comando `aovivo`
reprecifica tudo condicionando no estado atual.

```bash
python -m agente_esportivo aovivo Botafogo Palmeiras --placar 1-0 --minuto 70 \
    --odd-casa 1.35 --banca 300
```

```
AO VIVO  Botafogo-RJ 1-0 Palmeiras
70' jogados  |  20' restantes  |  gols ainda esperados: 0,50

  Vitoria Botafogo-RJ   #################...  83,2%   odd justa 1,20   ^ 40% vs pre-jogo
  Empate                ###.................  14,9%   odd justa 6,72   v -13% vs pre-jogo
  Vitoria Palmeiras     ....................   1,9%   odd justa 52,44  v -27% vs pre-jogo
```

Os gols esperados são escalados pelo tempo restante, a matriz é recalculada
sobre os gols **que ainda vão sair**, e o placar atual entra por cima — então
"mais de 2,5 gols" com 3-0 aos 50' aparece corretamente como 100%, e "ambas
marcam" sobe quando só falta um lado marcar.

Ao vivo o agente usa **só o modelo de gols**: o Elo não sabe condicionar em
placar e minuto, então incluí-lo pioraria a conta. E ele não vê expulsão, lesão
nem quem está pressionando. O mercado ao vivo se move em segundos e com margem
maior que o pré-jogo — ler a tela e digitar aqui já é tarde para linhas líquidas.

---

## Combinadas: a conta que quase todo mundo erra

Todos os mercados de gols saem da mesma matriz de placares. Isso permite calcular
a probabilidade conjunta **exata** de pernas do mesmo jogo — somando as células em
que todas ganham — em vez de multiplicar probabilidades como se fossem
independentes, que é o erro padrão.

A diferença não é pequena:

```bash
python -m agente_esportivo combinar "Botafogo x Palmeiras: over25 @2.05" \
                                    "Botafogo x Palmeiras: btts_sim @2.10"
```

| | |
|---|---|
| Multiplicando as pernas (ingênuo) | 18,1% → odd justa 5,52 |
| **Probabilidade conjunta real** | **32,6% → odd justa 3,07** |

"Mais de 2,5 gols" e "ambas marcam" andam juntos: a conjunta real é **1,80×** o
produto. Multiplicar subestimaria a múltipla em 44%. O inverso também acontece —
"goleada" e "ambas não marcam" brigam entre si, e ali multiplicar *superestima*
em três vezes, que é o erro caro.

Por isso nenhuma casa deixa combinar pernas correlacionadas pelo produto das
odds. Pegue o preço que ela realmente ofereceu e rode com `--odd-total`:

```bash
python -m agente_esportivo combinar "Botafogo x Palmeiras: over25 @2.05" \
    "Botafogo x Palmeiras: btts_sim @2.10" --odd-total 2.75
#   Valor esperado    -10,4%
```

### Combinar não cria valor — multiplica margem

Cada perna carrega a margem da casa, e elas compõem:

| Pernas | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Margem acumulada (6% por perna) | 6,0% | 12,4% | 19,1% | 26,2% | 33,8% |

É por isso que a múltipla é o produto que a casa mais empurra. Se uma perna
sozinha já não tem valor, juntar outras não conserta — piora.

### Seleções disponíveis

`C` `E` `F` · `1X` `12` `X2` · `over05`…`over45` e `under05`…`under45` ·
`btts_sim` `btts_nao` · `mandante_marca` `visitante_marca` ·
`mandante_sem_sofrer` `mandante_vence_sem_sofrer` · `placar:2-1`

**Escanteios, chutes no gol, cartões e posse não estão na lista** — o modelo foi
treinado só com placares finais. Pedir esses mercados devolve um erro explicando
isso, em vez de um número inventado com cara de precisão. Para cobri-los seria
preciso uma base com estatísticas por partida (escanteios e finalizações de cada
jogo), e aí sim modelá-los com o mesmo método.

---

## Painel web

Além do terminal, o agente gera um painel de página única — sem servidor, sem
dependências, funciona até offline:

```bash
python ferramentas/gerar_painel.py          # grava painel/painel.html
```

Abra o arquivo no navegador (ou publique onde quiser). Nele dá para escolher
qualquer confronto entre os times da temporada, inverter o mando, ver a matriz de
placares inteira, digitar as odds da sua casa e receber EV e stake na hora.

O truque é que **a página não traz previsões prontas**: ela embute só os
parâmetros do modelo — μ, fator mando, ρ, ataque/defesa e Elo de cada time, cerca
de 5 KB — e refaz a conta em JavaScript. São 380 confrontos possíveis; guardar
todos seria pesado e engessado.

Como o mesmo cálculo existe em dois lugares, `tests/test_painel.py` compara os
parâmetros embutidos com os do agente treinado e checa que todo `id` consultado
pelo script existe no HTML — o jeito clássico de uma página dessas quebrar em
silêncio e mostrar traços no lugar dos números.

- `painel/modelo.html` — o template (contém o marcador `__DADOS__`)
- `painel/painel.html` — a página gerada, pronta para abrir

Os números da ficha do modelo (RPS, calibração, tamanho da amostra) também saem
do backtest na hora da geração, então não envelhecem quando você atualizar a base.

---

## Apostas de valor

Odd não é probabilidade: ela embute a margem da casa. Comparar a probabilidade
do modelo com `1/odd` sem tirar a margem faz todo mercado parecer ruim. O agente
remove a margem por grupo de mercado (método da potência por padrão, com
proporcional e Shin disponíveis), calcula o EV e dimensiona a entrada por Kelly
fracionado — 25% do Kelly cheio, limitado a 5% da banca por entrada.

```
Apostas de valor (modelo acima do mercado)
------------------------------------------
Mercado               Odd  Odd justa  Modelo  Mercado     EV                 Stake
-------------------  ----  ---------  ------  -------  -----  --------------------
Vitoria do mandante  2,10       1,97   50,9%    46,0%  +6,8%  1,5% da banca = 7,73
```

Kelly cheio maximiza o crescimento teórico da banca, mas só se a probabilidade
estimada estiver certa — e ela nunca está. Daí o padrão fracionado.

> **Aviso.** Um ganho de 4,3% de RPS sobre a base não é licença para apostar: as
> casas trabalham com margem de 5% a 8%, e é dela que sai o lucro delas. EV
> positivo é estimativa, não promessa. Aposte só o que puder perder — e se
> apostar deixou de ser diversão, ligue 0800 000 0121 (CVV) ou procure os
> Jogadores Anônimos.

---

## Usando como biblioteca

```python
from agente_esportivo import Agente, Confronto, le_partidas

agente = Agente(le_partidas("dados/brasileirao_2021_2024.csv"))

analise = agente.analisa(Confronto("Palmeiras", "Flamengo",
                                   odds={"C": 2.10, "E": 3.40, "F": 3.60}),
                         banca=500)

print(analise.probabilidades)       # {'C': 0.509, 'E': 0.255, 'F': 0.236}
print(analise.gols_esperados)       # (1.66, 1.00)
print(analise.placares[:3])         # [('1-1', 0.116), ('1-0', 0.116), ('2-1', 0.096)]
for aposta in analise.apostas:
    print(aposta.nome, aposta.odd, f"EV {aposta.ev:+.1%}", aposta.stake)
```

## Estrutura

```
agente_esportivo/
  modelos.py     Partida e Confronto - as estruturas que todo o resto usa
  dados.py       Leitura de CSV (cabecalho PT ou football-data.co.uk)
  nomes.py       Reconciliacao de nomes de clube e apelidos
  tabela.py      Classificacao, recortes por mando, forma, confrontos diretos
  elo.py         Rating Elo adaptado a futebol
  poisson.py     Dixon-Coles: forcas, matriz de placares, mercados
  previsao.py    Agente: combina os modelos e monta a analise
  apostas.py     Margem, EV, Kelly, busca de valor
  metricas.py    RPS, log loss, Brier, calibracao
  backtest.py    Validacao walk-forward
  relatorio.py   Saida em texto para o terminal
  selecoes.py    Mercados como predicados sobre o placar (base das combinadas)
  aovivo.py      Repreciamento de jogo em andamento
  combinadas.py  Multiplas com probabilidade conjunta exata
  cli.py         Interface de linha de comando
  coleta/        Odds: texto copiado, HTML salvo ou navegador logado
painel/          Painel web de pagina unica (template + pagina gerada)
ferramentas/     Scripts de download da base e de geracao do painel
dados/           Base do Brasileirao e exemplo de rodada
tests/           265 testes (unittest, sem dependencias)
```

## Testes

```bash
python -m unittest discover -s tests -t .
```

## Limites honestos

- **Só usa placares.** Sem escalações, lesões, suspensões, calendário de
  Libertadores ou time misto na antepenúltima rodada. Um desfalque decisivo
  passa despercebido — olhe as notícias antes de confiar cegamente.
- **Time recém-promovido é um chute.** Sem histórico na Série A, o modelo o trata
  como média da liga. A confiança reportada cai, mas a estimativa é fraca mesmo.
- **Sem gols esperados (xG).** Placar é sinal ruidoso; xG melhoraria a estimativa,
  mas não há fonte pública confiável e gratuita para o Brasileirão.
- **A base vai até dezembro de 2024.** Rode o script de download para atualizar
  antes de usar em jogos atuais.
- **Ao vivo é o modo mais arriscado.** O modelo não enxerga expulsão, lesão nem
  pressão, o mercado se move em segundos e a margem é maior que no pré-jogo.
  Trate o repreciamento como uma segunda opinião, não como sinal de entrada.
