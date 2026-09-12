"""Saida em texto para o terminal - tabelas, cartoes de analise e relatorios."""

from __future__ import annotations

from typing import Iterable, Sequence

from .apostas import Aposta
from .aovivo import AnaliseAoVivo
from .backtest import Avaliacao
from .combinadas import Combinada, margem_composta
from .metricas import curva_de_calibracao
from .modelos import CASA, EMPATE, FORA
from .previsao import Agente, Analise
from .tabela import Forma, Linha

LARGURA = 76


def pct(valor: float, casas: int = 1) -> str:
    return f"{valor * 100:.{casas}f}%".replace(".", ",")


def num(valor: float, casas: int = 2) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def titulo(texto: str, caractere: str = "=") -> str:
    return f"\n{texto}\n{caractere * min(max(len(texto), 20), LARGURA)}"


def barra(proporcao: float, largura: int = 20) -> str:
    cheios = int(round(max(proporcao, 0.0) * largura))
    return "#" * cheios + "." * (largura - cheios)


def tabela_texto(
    cabecalhos: Sequence[str],
    linhas: Sequence[Sequence[object]],
    alinhamentos: Sequence[str] | None = None,
) -> str:
    """Tabela ASCII com colunas dimensionadas pelo conteudo."""
    colunas = len(cabecalhos)
    alinhamentos = alinhamentos or ["<"] + [">"] * (colunas - 1)
    texto_linhas = [[str(celula) for celula in linha] for linha in linhas]
    larguras = [
        max(len(cabecalhos[i]), *(len(l[i]) for l in texto_linhas)) if texto_linhas
        else len(cabecalhos[i])
        for i in range(colunas)
    ]
    saida = [
        "  ".join(f"{cabecalhos[i]:{alinhamentos[i]}{larguras[i]}}" for i in range(colunas)),
        "  ".join("-" * larguras[i] for i in range(colunas)),
    ]
    for linha in texto_linhas:
        saida.append(
            "  ".join(f"{linha[i]:{alinhamentos[i]}{larguras[i]}}" for i in range(colunas))
        )
    return "\n".join(saida)


# ------------------------------------------------------------------ tabelas
def formata_classificacao(linhas: Sequence[Linha], mando: str | None = None) -> str:
    rotulo = {None: "Classificacao geral", "casa": "Classificacao como mandante",
              "fora": "Classificacao como visitante"}[mando]
    corpo = tabela_texto(
        ["#", "Time", "P", "J", "V", "E", "D", "GP", "GC", "SG", "Aprov."],
        [
            [
                posicao,
                linha.time,
                linha.pontos,
                linha.jogos,
                linha.vitorias,
                linha.empates,
                linha.derrotas,
                linha.gols_pro,
                linha.gols_contra,
                f"{linha.saldo:+d}",
                pct(linha.aproveitamento, 0),
            ]
            for posicao, linha in enumerate(linhas, start=1)
        ],
        ["<", "<", ">", ">", ">", ">", ">", ">", ">", ">", ">"],
    )
    return titulo(rotulo) + "\n" + corpo


def formata_ranking(agente: Agente) -> str:
    linhas = []
    for posicao, (time, rating, forca) in enumerate(agente.ranking(), start=1):
        linhas.append(
            [
                posicao,
                time,
                num(rating, 0),
                num(forca.ataque, 2) if forca else "-",
                num(forca.defesa, 2) if forca else "-",
                num(forca.nota, 2) if forca else "-",
                agente.forma(time).sequencia or "-",
            ]
        )
    corpo = tabela_texto(
        ["#", "Time", "Elo", "Ataque", "Defesa", "Indice", "Forma"],
        linhas,
        ["<", "<", ">", ">", ">", ">", "<"],
    )
    return (
        titulo("Ranking de forca (Elo + ataque/defesa)")
        + "\n"
        + corpo
        + "\n\nAtaque/Defesa: 1,00 = media da liga. Ataque alto e defesa baixa sao bons."
    )


def formata_forma(forma: Forma) -> str:
    return (
        f"{forma.sequencia or '-'}  ({forma.pontos}/{forma.jogos * 3} pts, "
        f"{forma.gols_pro}-{forma.gols_contra} gols)"
    )


# ------------------------------------------------------------------ analise
def formata_analise(analise: Analise, detalhado: bool = True) -> str:
    confronto = analise.confronto
    mandante, visitante = confronto.mandante, confronto.visitante
    partes: list[str] = []

    cabecalho = f"{mandante}  x  {visitante}"
    if confronto.data:
        cabecalho += f"   ({confronto.data.strftime('%d/%m/%Y')})"
    partes.append(titulo(cabecalho))

    lc, lf = analise.gols_esperados
    partes.append(
        f"Gols esperados: {mandante} {num(lc)} x {num(lf)} {visitante}   |   "
        f"Placar mais provavel: {analise.placar_provavel}   |   "
        f"Confianca na estimativa: {analise.nivel_confianca} "
        f"({pct(analise.confianca, 0)})"
    )

    partes.append("\nProbabilidades (modelo combinado)")
    for chave, rotulo in (
        (CASA, f"Vitoria {mandante}"),
        (EMPATE, "Empate"),
        (FORA, f"Vitoria {visitante}"),
    ):
        prob = analise.probabilidades[chave]
        justa = 1 / prob if prob else float("inf")
        partes.append(
            f"  {rotulo:<28} {barra(prob)} {pct(prob):>6}   odd justa {num(justa)}"
        )

    if detalhado:
        partes.append("\nComparacao entre modelos")
        partes.append(
            tabela_texto(
                ["Modelo", "Casa", "Empate", "Fora"],
                [
                    ["Elo", pct(analise.prob_elo[CASA]), pct(analise.prob_elo[EMPATE]),
                     pct(analise.prob_elo[FORA])],
                    ["Poisson", pct(analise.prob_poisson[CASA]),
                     pct(analise.prob_poisson[EMPATE]), pct(analise.prob_poisson[FORA])],
                    ["Combinado", pct(analise.probabilidades[CASA]),
                     pct(analise.probabilidades[EMPATE]), pct(analise.probabilidades[FORA])],
                ],
            )
        )

        partes.append("\nMercados de gols")
        mercados = analise.mercados
        partes.append(
            tabela_texto(
                ["Mercado", "Prob.", "Odd justa"],
                [
                    [rotulo, pct(mercados[chave]), num(1 / mercados[chave])
                     if mercados[chave] > 0 else "-"]
                    for chave, rotulo in (
                        ("over15", "Mais de 1,5 gols"),
                        ("over25", "Mais de 2,5 gols"),
                        ("under25", "Menos de 2,5 gols"),
                        ("over35", "Mais de 3,5 gols"),
                        ("btts_sim", "Ambas marcam"),
                        ("btts_nao", "Ambas nao marcam"),
                    )
                ],
            )
        )

        partes.append("\nDupla chance")
        partes.append(
            "  "
            + "   ".join(
                f"{chave}: {pct(valor)}" for chave, valor in analise.dupla_chance.items()
            )
        )

        partes.append("\nPlacares mais provaveis")
        partes.append(
            "  "
            + "   ".join(f"{placar} ({pct(prob)})" for placar, prob in analise.placares[:5])
        )

        partes.append("\nContexto")
        elo_casa = analise.elo[mandante]
        elo_fora = analise.elo[visitante]
        partes.append(
            f"  Elo: {mandante} {num(elo_casa, 0)}  x  {num(elo_fora, 0)} {visitante} "
            f"(diferenca {num(elo_casa - elo_fora, 0)})"
        )
        partes.append(f"  Forma {mandante}: {formata_forma(analise.forma[mandante])}")
        partes.append(f"  Forma {visitante}: {formata_forma(analise.forma[visitante])}")
        retrospecto = analise.retrospecto
        if retrospecto["jogos"]:
            partes.append(
                f"  Retrospecto direto ({retrospecto['jogos']} jogos): "
                f"{retrospecto['vitorias_a']}V {retrospecto['empates']}E "
                f"{retrospecto['vitorias_b']}D para o {mandante} "
                f"({retrospecto['gols_a']}-{retrospecto['gols_b']} em gols)"
            )
        else:
            partes.append("  Retrospecto direto: sem jogos na base")
        partes.append(
            f"  Amostra: {analise.amostra[mandante]} jogos do {mandante}, "
            f"{analise.amostra[visitante]} do {visitante}"
        )

    if analise.confronto.tem_odds:
        partes.append(formata_apostas(analise.apostas))
    return "\n".join(partes)


def formata_apostas(apostas: Sequence[Aposta]) -> str:
    if not apostas:
        return (
            "\nApostas de valor: nenhuma. As odds oferecidas estao iguais ou piores "
            "que a probabilidade do modelo - o certo aqui e nao apostar."
        )
    corpo = tabela_texto(
        ["Mercado", "Odd", "Odd justa", "Modelo", "Mercado", "EV", "Stake"],
        [
            [
                aposta.nome,
                num(aposta.odd),
                num(aposta.odd_justa),
                pct(aposta.prob_modelo),
                pct(aposta.prob_mercado),
                f"+{pct(aposta.ev)}",
                f"{pct(aposta.kelly)} da banca"
                + (f" = {num(aposta.stake)}" if aposta.stake else ""),
            ]
            for aposta in apostas
        ],
        ["<", ">", ">", ">", ">", ">", ">"],
    )
    return (
        titulo("Apostas de valor (modelo acima do mercado)", "-")
        + "\n"
        + corpo
        + "\n\nStake por Kelly fracionado. EV positivo e estimativa, nao promessa:"
        "\no modelo pode estar errado e variancia de curto prazo engole qualquer borda."
    )


def formata_rodada(analises: Sequence[Analise]) -> str:
    linhas = []
    for analise in analises:
        confronto = analise.confronto
        lc, lf = analise.gols_esperados
        melhor = analise.apostas[0] if analise.apostas else None
        linhas.append(
            [
                confronto.rotulo,
                pct(analise.probabilidades[CASA], 0),
                pct(analise.probabilidades[EMPATE], 0),
                pct(analise.probabilidades[FORA], 0),
                f"{num(lc, 1)}-{num(lf, 1)}",
                analise.placar_provavel,
                analise.nivel_confianca,
                f"{melhor.nome} @{num(melhor.odd)} (+{pct(melhor.ev, 0)})" if melhor else "-",
            ]
        )
    corpo = tabela_texto(
        ["Jogo", "Casa", "Emp.", "Fora", "xG", "Placar", "Conf.", "Valor"],
        linhas,
        ["<", ">", ">", ">", ">", ">", "<", "<"],
    )
    return titulo("Analise da rodada") + "\n" + corpo


def formata_dossie(agente: Agente, time: str) -> str:
    time = agente.valida_time(time)
    geral = {l.time: l for l in agente.classificacao()}
    casa = {l.time: l for l in agente.classificacao(mando="casa")}
    fora = {l.time: l for l in agente.classificacao(mando="fora")}
    posicao = [l.time for l in agente.classificacao()].index(time) + 1
    forca = {f.time: f for f in agente.poisson.forcas()}.get(time)
    forma = agente.forma(time)

    partes = [titulo(f"Dossie: {time}")]
    linha = geral[time]
    partes.append(
        f"Posicao {posicao}o  |  {linha.pontos} pts em {linha.jogos} jogos  |  "
        f"aproveitamento {pct(linha.aproveitamento, 0)}  |  Elo {num(agente.elo.rating(time), 0)}"
    )
    if forca:
        partes.append(
            f"Ataque {num(forca.ataque)} / Defesa {num(forca.defesa)} "
            f"(1,00 = media da liga) - indice {num(forca.nota)}"
        )
    partes.append(f"Forma ({forma.jogos} jogos): {formata_forma(forma)}")
    partes.append(
        f"Sequencia: {forma.invencibilidade} jogo(s) sem perder, "
        f"{forma.sem_vencer} sem vencer"
    )

    partes.append("\nDesempenho por mando")
    partes.append(
        tabela_texto(
            ["Recorte", "J", "V", "E", "D", "GP", "GC", "Pts/jogo"],
            [
                [
                    rotulo,
                    dados[time].jogos,
                    dados[time].vitorias,
                    dados[time].empates,
                    dados[time].derrotas,
                    dados[time].gols_pro,
                    dados[time].gols_contra,
                    num(dados[time].pontos / dados[time].jogos) if dados[time].jogos else "-",
                ]
                for rotulo, dados in (("Casa", casa), ("Fora", fora), ("Geral", geral))
                if time in dados
            ],
        )
    )

    partes.append("\nUltimos jogos")
    for partida in reversed(forma.ultimas):
        adversario = partida.adversario_de(time)
        mando = "casa" if partida.mandante == time else "fora"
        resultado = "V" if partida.pontos_de(time) == 3 else "E" if partida.pontos_de(time) == 1 else "D"
        partes.append(
            f"  {partida.data.strftime('%d/%m')}  {resultado}  "
            f"{partida.gols_de(time)}-{partida.gols_contra(time)}  vs {adversario} ({mando})"
        )
    return "\n".join(partes)


def formata_backtest(avaliacao: Avaliacao) -> str:
    modelo = avaliacao.modelo
    partes = [titulo("Backtest walk-forward")]
    partes.append(
        f"Partidas avaliadas: {avaliacao.avaliadas}  "
        f"(aquecimento de {avaliacao.aquecimento} jogos)"
    )

    linhas = [
        ["Modelo", num(modelo.rps, 4), num(modelo.log_loss, 4), num(modelo.brier, 4),
         pct(modelo.acuracia, 1)],
        ["Base da liga", num(avaliacao.base.rps, 4), num(avaliacao.base.log_loss, 4),
         num(avaliacao.base.brier, 4), pct(avaliacao.base.acuracia, 1)],
    ]
    if avaliacao.mercado.n:
        linhas.append(
            ["Mercado (sem margem)", num(avaliacao.mercado.rps, 4),
             num(avaliacao.mercado.log_loss, 4), num(avaliacao.mercado.brier, 4),
             pct(avaliacao.mercado.acuracia, 1)]
        )
    partes.append(
        "\n" + tabela_texto(["Previsor", "RPS", "Log loss", "Brier", "Acertos"], linhas)
    )
    partes.append("\nRPS menor e melhor. O numero sozinho nao diz nada - o que importa")
    partes.append("e a comparacao com a base da liga e com o mercado.")
    partes.append(f"  Ganho sobre a base da liga: {pct(avaliacao.ganho_sobre_base)}")
    if avaliacao.mercado.n:
        partes.append(f"  Ganho sobre o mercado:      {pct(avaliacao.ganho_sobre_mercado)}")

    calibracao = curva_de_calibracao(modelo.calibracao)
    if calibracao:
        partes.append("\nCalibracao (o modelo cumpre o que promete?)")
        partes.append(
            tabela_texto(
                ["Faixa", "n", "Previsto", "Observado"],
                [
                    [
                        f"{pct(faixa['faixa_min'], 0)}-{pct(faixa['faixa_max'], 0)}",
                        faixa["n"],
                        pct(faixa["previsto"]),
                        pct(faixa["observado"]),
                    ]
                    for faixa in calibracao
                ],
            )
        )

    if modelo.apostas:
        partes.append("\nSimulacao de apostas (1 unidade na melhor entrada por jogo)")
        partes.append(
            f"  Entradas: {modelo.apostas}  |  acertos: {pct(modelo.taxa_acerto_apostas)}  |  "
            f"lucro: {num(modelo.lucro)} u  |  ROI: {pct(modelo.roi)}"
        )
        if modelo.apostas < 50:
            partes.append(
                "  Amostra pequena demais para concluir qualquer coisa sobre o ROI."
            )
    return "\n".join(partes)


# ------------------------------------------------------------------ ao vivo
def formata_aovivo(analise: AnaliseAoVivo) -> str:
    estado = analise.estado
    partes = [titulo(f"AO VIVO  {estado.mandante} {estado.placar} {estado.visitante}")]
    partes.append(
        f"{estado.minuto}' jogados  |  {estado.minutos_restantes}' restantes  |  "
        f"gols ainda esperados: {num(sum(analise.gols_restantes))}"
    )

    partes.append("\nResultado final (reprecificado agora)")
    for chave, rotulo in (
        (CASA, f"Vitoria {estado.mandante}"),
        (EMPATE, "Empate"),
        (FORA, f"Vitoria {estado.visitante}"),
    ):
        prob = analise.probabilidades[chave]
        movimento = analise.movimento[chave]
        seta = "^" if movimento > 0.005 else "v" if movimento < -0.005 else "="
        partes.append(
            f"  {rotulo:<28} {barra(prob)} {pct(prob):>6}   odd justa {num(1 / prob) if prob > 0 else '-':>6}"
            f"   {seta} {pct(movimento, 0):>6} vs pre-jogo"
        )

    partes.append("\nMercados sobre o placar FINAL")
    mercados = analise.mercados
    partes.append(
        tabela_texto(
            ["Mercado", "Prob.", "Odd justa"],
            [
                [rotulo, pct(mercados[chave]),
                 num(1 / mercados[chave]) if mercados[chave] > 0 else "-"]
                for chave, rotulo in (
                    ("over15", "Mais de 1,5 gols"),
                    ("over25", "Mais de 2,5 gols"),
                    ("under25", "Menos de 2,5 gols"),
                    ("over35", "Mais de 3,5 gols"),
                    ("btts_sim", "Ambas marcam"),
                    ("btts_nao", "Ambas nao marcam"),
                )
            ],
        )
    )

    partes.append("\nPlacares finais mais provaveis")
    partes.append(
        "  " + "   ".join(f"{placar} ({pct(prob)})" for placar, prob in analise.placares[:5])
    )
    partes.append(
        "\nAo vivo o agente usa so o modelo de gols: o Elo nao sabe condicionar em"
        "\nplacar e minuto, entao entrar com ele aqui pioraria a conta. E o modelo nao"
        "\nve expulsao, lesao nem quem esta pressionando - olhe o jogo, nao so a tela."
    )
    return "\n".join(partes)


# ---------------------------------------------------------------- combinadas
def formata_combinada(combinada: Combinada, banca: float = 0.0) -> str:
    partes = [titulo(f"Combinada de {len(combinada.pernas)} perna(s)")]

    partes.append(
        tabela_texto(
            ["Perna", "Prob.", "Odd justa", "Odd oferecida"],
            [
                [
                    avaliada.perna.rotulo,
                    pct(avaliada.probabilidade),
                    num(avaliada.odd_justa),
                    num(avaliada.perna.odd) if avaliada.perna.odd else "-",
                ]
                for avaliada in combinada.pernas
            ],
            ["<", ">", ">", ">"],
        )
    )

    partes.append("\nA combinada inteira")
    linhas = [
        ["Probabilidade conjunta (exata)", pct(combinada.conjunta)],
        ["Odd justa", num(combinada.odd_justa)],
        ["Multiplicando as pernas (ingenuo)", pct(combinada.ingenua)],
        ["Odd justa pela conta ingenua", num(combinada.odd_justa_ingenua)],
    ]
    # so e "hipotetico" quando as pernas de fato se correlacionam; pernas
    # praticamente independentes (gol x escanteio, medido em 0,98) tornam o
    # produto uma referencia razoavel - o preco real ainda manda
    correlacionadas = abs(combinada.correlacao - 1.0) > 0.02
    hipotetico = (
        combinada.preco_do_produto and combinada.mesmo_jogo
        and len(combinada.pernas) > 1 and correlacionadas
    )
    if combinada.odd_oferecida is not None:
        linhas.append([
            "Odd pelo produto das pernas" if combinada.preco_do_produto else "Odd oferecida pela casa",
            num(combinada.odd_oferecida),
        ])
        ev = combinada.ev
        linhas.append([
            "Valor esperado" + (" (preco hipotetico)" if hipotetico else ""),
            ("+" if ev >= 0 else "") + pct(ev),
        ])
        if ev > 0 and banca and not hipotetico:
            linhas.append(
                ["Stake por Kelly fracionado",
                 f"{pct(combinada.stake_kelly)} = {num(banca * combinada.stake_kelly)}"]
            )
    partes.append(tabela_texto(["Item", "Valor"], linhas, ["<", ">"]))
    if hipotetico:
        partes.append(
            "\nO valor esperado acima NAO e real: ele usa o produto das odds das pernas,"
            "\nque nenhuma casa paga em multipla de mesmo jogo justamente porque as pernas"
            "\nsao correlacionadas. Pegue o preco que ela ofereceu e rode de novo com"
            "\n--odd-total - so esse numero vale alguma coisa."
        )

    if combinada.sem_sinal:
        nomes = ", ".join(combinada.sem_sinal)
        partes.append(
            f"\n>> ATENCAO: {nomes} - o modelo dessa estatistica e PIOR que a simples"
            "\n   frequencia historica da liga (rode `estatisticas --validar`). A"
            "\n   probabilidade acima esta bem calibrada na distribuicao, mas a parte"
            "\n   que depende dos times nao acrescenta nada. Apostar nisso e pagar"
            "\n   margem para jogar a media da liga."
        )

    if combinada.mesmo_jogo and len(combinada.pernas) > 1:
        fator = combinada.correlacao
        if fator > 1.02:
            leitura = (
                f"As pernas se ajudam: a conjunta real e {num(fator, 2)}x maior que o produto."
                "\nMultiplicar as probabilidades subestimaria a multipla."
            )
        elif fator < 0.98:
            leitura = (
                f"As pernas brigam entre si: a conjunta real e so {num(fator, 2)}x o produto."
                "\nMultiplicar as probabilidades superestimaria a multipla - e o erro caro."
            )
        else:
            leitura = (
                "As pernas sao praticamente independentes neste jogo, entao o produto"
                "\ndas probabilidades serve como referencia - confirme o preco real da"
                "\nmultipla mesmo assim."
            )
        partes.append("\nCorrelacao (mesmo jogo)")
        partes.append("  " + leitura.replace("\n", "\n  "))
        if correlacionadas:
            partes.append(
                "  Nenhuma casa deixa combinar pernas correlacionadas pelo produto das odds."
            )
            partes.append(
                "  Use --odd-total com o preco que ela realmente ofereceu na multipla."
            )

    partes.append("\nO que combinar custa")
    partes.append(
        tabela_texto(
            ["Pernas", "Margem da casa acumulada (6% por perna)"],
            [[n, pct(margem_composta(0.06, n))] for n in range(1, len(combinada.pernas) + 2)],
            ["<", ">"],
        )
    )
    partes.append(
        "Cada perna multiplica a margem contra voce. Combinada nao cria valor -"
        "\ne o produto de maior margem da casa. Se uma perna sozinha ja nao tem valor,"
        "\njuntar outras nao conserta: piora."
    )
    return "\n".join(partes)


def formata_sugestoes(combinadas, maximo: int = 10) -> str:
    if not combinadas:
        return titulo("Combinadas sugeridas") + "\n  Nenhuma selecao passou do corte de probabilidade."
    linhas = []
    for combinada in combinadas[:maximo]:
        linhas.append([
            " + ".join(a.perna.rotulo for a in combinada.pernas),
            pct(combinada.conjunta),
            num(combinada.odd_justa),
        ])
    return (
        titulo("Combinadas sugeridas (as menos improvaveis da rodada)")
        + "\n"
        + tabela_texto(["Pernas", "Prob. conjunta", "Odd justa"], linhas, ["<", ">", ">"])
        + "\n\nSao as selecoes de maior probabilidade, nao as de maior valor: so vale a pena"
        "\nse a casa pagar ACIMA da odd justa da coluna - o que raramente acontece."
    )



def formata_estatisticas(agente, mandante: str, visitante: str) -> str:
    """Escanteios, chutes e cartoes esperados - cada um com seu veredito."""
    from .estatisticas import LINHAS

    partes = [titulo(f"Estatisticas esperadas: {mandante} x {visitante}")]

    resumo = []
    for estatistica, modelo in agente.estatisticas.items():
        casa, fora = modelo.expectativa(mandante, visitante)
        resumo.append([
            modelo.nome, num(casa), num(fora), num(casa + fora),
            num(modelo.razao_variancia, 2),
            ("+" if modelo.validacao and modelo.validacao.ganho >= 0 else "")
            + (pct(modelo.validacao.ganho) if modelo.validacao else "-"),
        ])
    partes.append(
        tabela_texto(
            ["Estatistica", "Mandante", "Visitante", "Total", "Var/media", "Ganho s/ base"],
            resumo, ["<", ">", ">", ">", ">", ">"],
        )
    )
    partes.append(
        "Var/media acima de 1 significa contagem mais espalhada que uma Poisson -"
        "\npor isso a distribuicao usada e Binomial Negativa, que acerta as pontas."
    )

    for estatistica, modelo in agente.estatisticas.items():
        mercados = modelo.mercados(mandante, visitante)
        linhas = []
        for linha in LINHAS.get(estatistica, ()):
            chave = str(linha).replace(".", "")
            if f"over{chave}" not in mercados:
                continue
            acima = mercados[f"over{chave}"]
            linhas.append([
                f"Mais de {str(linha).replace('.', ',')}",
                pct(acima), num(1 / acima) if acima > 0 else "-",
                pct(1 - acima), num(1 / (1 - acima)) if acima < 1 else "-",
            ])
        if not linhas:
            continue
        partes.append(titulo(modelo.nome, "-"))
        partes.append(
            tabela_texto(
                ["Linha", "Over", "Odd justa", "Under", "Odd justa"],
                linhas, ["<", ">", ">", ">", ">"],
            )
        )
        if modelo.validacao:
            marca = "  " if modelo.validacao.tem_sinal else "  >> "
            partes.append(marca + modelo.validacao.veredito)
    return "\n".join(partes)


def formata_lista_times(times: Iterable[str]) -> str:
    times = list(times)
    return titulo(f"Times na base ({len(times)})") + "\n  " + "\n  ".join(times)
