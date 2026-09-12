"""Saida em texto para o terminal - tabelas, cartoes de analise e relatorios."""

from __future__ import annotations

from typing import Iterable, Sequence

from .apostas import Aposta
from .backtest import Avaliacao
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


def formata_lista_times(times: Iterable[str]) -> str:
    times = list(times)
    return titulo(f"Times na base ({len(times)})") + "\n  " + "\n  ".join(times)
