"""Leitura de odds, remocao da margem da casa e dimensionamento de aposta.

A odd de uma casa nao e uma probabilidade: ela ja embute a margem (o "juice").
Comparar a probabilidade do modelo com 1/odd sem tirar a margem faz todo mercado
parecer ruim. Aqui a margem e removida antes de qualquer comparacao.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

NOME_MERCADO = {
    "C": "Vitoria do mandante",
    "E": "Empate",
    "F": "Vitoria do visitante",
    "over25": "Mais de 2,5 gols",
    "under25": "Menos de 2,5 gols",
    "over15": "Mais de 1,5 gols",
    "under15": "Menos de 1,5 gols",
    "over35": "Mais de 3,5 gols",
    "under35": "Menos de 3,5 gols",
    "btts_sim": "Ambas marcam: sim",
    "btts_nao": "Ambas marcam: nao",
    "1X": "Dupla chance 1X",
    "12": "Dupla chance 12",
    "X2": "Dupla chance X2",
}

# grupos que somam 100% e por isso permitem remover a margem
GRUPOS: tuple[tuple[str, ...], ...] = (
    ("C", "E", "F"),
    ("over15", "under15"),
    ("over25", "under25"),
    ("over35", "under35"),
    ("btts_sim", "btts_nao"),
)


def prob_implicita(odd: float) -> float:
    if odd <= 1.0:
        raise ValueError(f"odd decimal precisa ser > 1.0 (recebido {odd})")
    return 1.0 / odd


def margem(odds: Iterable[float]) -> float:
    """Overround da casa: 0,05 = 5% de margem."""
    return sum(prob_implicita(o) for o in odds) - 1.0


def _proporcional(brutas: Sequence[float]) -> list[float]:
    total = sum(brutas)
    return [p / total for p in brutas]


def _potencia(brutas: Sequence[float]) -> list[float]:
    """Metodo da potencia: acha k tal que sum(p_i^k) = 1.

    Corrige melhor o favorite-longshot bias do que o metodo proporcional, que
    tira margem demais dos azaroes.
    """
    baixo, alto = 0.2, 3.0
    for _ in range(100):
        k = (baixo + alto) / 2.0
        soma = sum(p ** k for p in brutas)
        if soma > 1.0:
            baixo = k
        else:
            alto = k
    k = (baixo + alto) / 2.0
    ajustadas = [p ** k for p in brutas]
    return _proporcional(ajustadas)


def _shin(brutas: Sequence[float]) -> list[float]:
    """Metodo de Shin: modela a fatia de apostadores informados."""
    total = sum(brutas)
    baixo, alto = 0.0, 0.3

    def probabilidades(z: float) -> list[float]:
        if z <= 0:
            return _proporcional(brutas)
        saida = []
        for p in brutas:
            raiz = max(z * z + 4.0 * (1.0 - z) * p * p / total, 0.0)
            saida.append((raiz ** 0.5 - z) / (2.0 * (1.0 - z)))
        return saida

    for _ in range(100):
        z = (baixo + alto) / 2.0
        if sum(probabilidades(z)) > 1.0:
            baixo = z
        else:
            alto = z
    return _proporcional(probabilidades((baixo + alto) / 2.0))


METODOS = {"proporcional": _proporcional, "potencia": _potencia, "shin": _shin}


def remove_margem(
    odds: Mapping[str, float], metodo: str = "potencia"
) -> dict[str, float]:
    """Converte odds em probabilidades reais, grupo a grupo."""
    if metodo not in METODOS:
        raise ValueError(f"metodo desconhecido: {metodo} (use {', '.join(METODOS)})")
    funcao = METODOS[metodo]
    saida: dict[str, float] = {}
    usadas: set[str] = set()

    for grupo in GRUPOS:
        presentes = [chave for chave in grupo if chave in odds]
        if len(presentes) < 2:
            continue
        brutas = [prob_implicita(odds[chave]) for chave in presentes]
        for chave, prob in zip(presentes, funcao(brutas)):
            saida[chave] = prob
        usadas.update(presentes)

    # odds avulsas: sem par nao da para separar margem de probabilidade
    for chave, odd in odds.items():
        if chave not in usadas:
            saida[chave] = prob_implicita(odd)
    return saida


def valor_esperado(probabilidade: float, odd: float) -> float:
    """EV por unidade apostada: 0,07 = +7% de retorno esperado."""
    return probabilidade * odd - 1.0


def kelly(probabilidade: float, odd: float, fracao: float = 1.0) -> float:
    """Fracao da banca segundo o criterio de Kelly (0 se nao ha valor)."""
    ganho = odd - 1.0
    if ganho <= 0:
        return 0.0
    aposta = (probabilidade * odd - 1.0) / ganho
    return max(aposta, 0.0) * fracao


@dataclass
class Aposta:
    """Uma oportunidade identificada pelo modelo."""

    mercado: str
    odd: float
    prob_modelo: float
    prob_mercado: float
    ev: float
    kelly: float
    stake: float = 0.0

    @property
    def nome(self) -> str:
        return NOME_MERCADO.get(self.mercado, self.mercado)

    @property
    def odd_justa(self) -> float:
        return 1.0 / self.prob_modelo if self.prob_modelo > 0 else float("inf")

    @property
    def vantagem(self) -> float:
        """Diferenca de probabilidade entre modelo e mercado."""
        return self.prob_modelo - self.prob_mercado


def encontra_valor(
    probabilidades: Mapping[str, float],
    odds: Mapping[str, float],
    *,
    ev_minimo: float = 0.03,
    banca: float = 0.0,
    fracao_kelly: float = 0.25,
    stake_maxima: float = 0.05,
    metodo: str = "potencia",
) -> list[Aposta]:
    """Compara modelo x mercado e devolve as apostas com valor, da melhor a pior.

    `fracao_kelly` menor que 1 e o padrao consciente: Kelly cheio maximiza o
    crescimento teorico, mas so se a probabilidade estimada estiver certa - e ela
    nunca esta. `stake_maxima` limita a fracao da banca em uma unica entrada.
    """
    if not odds:
        return []
    sem_margem = remove_margem(odds, metodo=metodo)
    achados: list[Aposta] = []
    for mercado, odd in odds.items():
        prob_modelo = probabilidades.get(mercado)
        if prob_modelo is None:
            continue
        ev = valor_esperado(prob_modelo, odd)
        if ev < ev_minimo:
            continue
        fracao = min(kelly(prob_modelo, odd, fracao_kelly), stake_maxima)
        achados.append(
            Aposta(
                mercado=mercado,
                odd=odd,
                prob_modelo=prob_modelo,
                prob_mercado=sem_margem.get(mercado, prob_implicita(odd)),
                ev=ev,
                kelly=fracao,
                stake=round(banca * fracao, 2) if banca else 0.0,
            )
        )
    achados.sort(key=lambda a: -a.ev)
    return achados


def resultado_de_aposta(aposta: Aposta, acertou: bool, stake: float = 1.0) -> float:
    """Lucro/prejuizo de uma entrada resolvida."""
    return stake * (aposta.odd - 1.0) if acertou else -stake
