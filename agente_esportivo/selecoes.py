"""Selecoes de aposta como predicados sobre o placar final.

Todo mercado derivado de gols e, no fundo, uma pergunta sobre a celula (i, j) da
matriz de placares: "o mandante venceu?", "passou de 2,5?", "os dois marcaram?".
Escrever cada mercado como um predicado permite duas coisas que o resto do
pacote usa: resolver apostas no backtest e - o ponto importante - somar as
celulas que satisfazem varias selecoes ao mesmo tempo, que e a probabilidade
conjunta exata de uma multipla no mesmo jogo.
"""

from __future__ import annotations

import re
from typing import Callable

CASA, EMPATE, FORA = "C", "E", "F"


class MercadoDesconhecido(KeyError):
    """Selecao que o modelo de gols nao sabe resolver."""


class MercadoDeContagem(MercadoDesconhecido):
    """Selecao de escanteio/chute/cartao: existe, mas nao sai da matriz de gols.

    Quem resolve e o modelo de contagem (`estatisticas.py`), que precisa da base
    de estatisticas por partida. Esta excecao carrega o que foi pedido para quem
    souber tratar.
    """

    def __init__(self, mensagem: str, estatistica: str, tipo: str, linha: float):
        super().__init__(mensagem)
        self.estatistica = estatistica
        self.tipo = tipo
        self.linha = linha


PLACAR_EXATO = re.compile(r"^placar:(\d+)-(\d+)$")
# ex.: escanteios_over95 -> mais de 9,5 escanteios (o ultimo digito e o decimal)
CONTAGEM = re.compile(
    r"^(escanteios|chutes_no_alvo|chutes|cartao_amarelo|faltas)_(over|under)(\d{2,})$"
)
LINHA_GOLS = re.compile(r"^(over|under)(\d)(\d)$")

BASICOS: dict[str, Callable[[int, int], bool]] = {
    CASA: lambda c, f: c > f,
    EMPATE: lambda c, f: c == f,
    FORA: lambda c, f: c < f,
    "1X": lambda c, f: c >= f,
    "12": lambda c, f: c != f,
    "X2": lambda c, f: c <= f,
    "btts_sim": lambda c, f: c > 0 and f > 0,
    "btts_nao": lambda c, f: c == 0 or f == 0,
    "mandante_marca": lambda c, f: c > 0,
    "visitante_marca": lambda c, f: f > 0,
    "mandante_sem_sofrer": lambda c, f: f == 0,
    "visitante_sem_sofrer": lambda c, f: c == 0,
    "mandante_vence_sem_sofrer": lambda c, f: c > f and f == 0,
    "visitante_vence_sem_sofrer": lambda c, f: f > c and c == 0,
    "gol_nos_dois_tempos": None,  # depende de tempo, nao de placar final
}

NOMES: dict[str, str] = {
    CASA: "Vitoria do mandante",
    EMPATE: "Empate",
    FORA: "Vitoria do visitante",
    "1X": "Dupla chance 1X",
    "12": "Dupla chance 12",
    "X2": "Dupla chance X2",
    "btts_sim": "Ambas marcam",
    "btts_nao": "Ambas nao marcam",
    "mandante_marca": "Mandante marca",
    "visitante_marca": "Visitante marca",
    "mandante_sem_sofrer": "Mandante nao sofre gol",
    "visitante_sem_sofrer": "Visitante nao sofre gol",
    "mandante_vence_sem_sofrer": "Mandante vence sem sofrer",
    "visitante_vence_sem_sofrer": "Visitante vence sem sofrer",
}

# mercados que o modelo NAO cobre - listados para dar erro util em vez de silencio
FORA_DO_MODELO = {
    "escanteios", "escanteio", "cantos", "corners",
    "chutes", "chutes_no_gol", "finalizacoes", "shots",
    "cartoes", "cartao", "faltas", "impedimentos", "posse",
}


def nome(selecao: str) -> str:
    achado = PLACAR_EXATO.match(selecao)
    if achado:
        return f"Placar exato {achado.group(1)}-{achado.group(2)}"
    achado = LINHA_GOLS.match(selecao)
    if achado:
        lado = "Mais de" if achado.group(1) == "over" else "Menos de"
        return f"{lado} {achado.group(2)},{achado.group(3)} gols"
    contagem = analisa_contagem(selecao)
    if contagem:
        estatistica, tipo, linha = contagem
        from .estatisticas import NOMES as NOMES_CONTAGEM

        lado = "Mais de" if tipo == "over" else "Menos de"
        rotulo = NOMES_CONTAGEM.get(estatistica, estatistica).lower()
        return f"{lado} {str(linha).replace('.', ',')} {rotulo}"
    return NOMES.get(selecao, selecao)


def analisa_contagem(selecao: str) -> tuple[str, str, float] | None:
    """Le uma selecao de contagem: (estatistica, 'over'|'under', linha)."""
    achado = CONTAGEM.match(selecao.strip())
    if not achado:
        return None
    digitos = achado.group(3)
    return achado.group(1), achado.group(2), float(f"{digitos[:-1]}.{digitos[-1]}")


def satisfaz(selecao: str, gols_casa: int, gols_fora: int) -> bool:
    """Diz se o placar (gols_casa, gols_fora) faz a selecao ganhar."""
    chave = selecao.strip()

    contagem = analisa_contagem(chave)
    if contagem:
        estatistica, tipo, linha = contagem
        raise MercadoDeContagem(
            f"'{selecao}' e mercado de {estatistica}, que nao sai do placar. "
            "Carregue a base de estatisticas (--estatisticas) para avalia-lo.",
            estatistica, tipo, linha,
        )

    for termo in FORA_DO_MODELO:
        if termo in chave.lower():
            raise MercadoDesconhecido(
                f"'{selecao}' depende de dados que este modelo nao tem. "
                "Ele foi treinado so com placares - nao sabe estimar escanteios, "
                "chutes, cartoes nem posse de bola."
            )

    if chave in BASICOS and BASICOS[chave] is not None:
        return BASICOS[chave](gols_casa, gols_fora)

    achado = PLACAR_EXATO.match(chave)
    if achado:
        return (gols_casa, gols_fora) == (int(achado.group(1)), int(achado.group(2)))

    achado = LINHA_GOLS.match(chave)
    if achado:
        limite = float(f"{achado.group(2)}.{achado.group(3)}")
        total = gols_casa + gols_fora
        return total > limite if achado.group(1) == "over" else total < limite

    raise MercadoDesconhecido(
        f"selecao desconhecida: '{selecao}'. Disponiveis: "
        + ", ".join(sorted(NOMES)) + ", overXY/underXY (ex.: over25), placar:2-1"
    )


def probabilidade(matriz, selecao: str) -> float:
    """Soma as celulas da matriz em que a selecao ganha."""
    total = 0.0
    for i, linha in enumerate(matriz):
        for j, valor in enumerate(linha):
            if satisfaz(selecao, i, j):
                total += valor
    return total


def probabilidade_conjunta(matriz, selecoes) -> float:
    """Probabilidade EXATA de todas as selecoes do mesmo jogo darem certo.

    Nao multiplica probabilidades: soma as celulas em que todas as selecoes
    ganham ao mesmo tempo. E ai que mora a diferenca - "mais de 2,5 gols" e
    "ambas marcam" nao sao eventos independentes, e tratar como se fossem
    superestima ou subestima a multipla dependendo do par.
    """
    selecoes = list(selecoes)
    if not selecoes:
        raise ValueError("informe ao menos uma selecao")
    total = 0.0
    for i, linha in enumerate(matriz):
        for j, valor in enumerate(linha):
            if all(satisfaz(s, i, j) for s in selecoes):
                total += valor
    return total
