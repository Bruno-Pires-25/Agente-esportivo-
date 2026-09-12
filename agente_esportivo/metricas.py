"""Metricas para saber se o modelo presta.

Acertar o favorito nao diz quase nada - em 1X2 o favorito vence pouco mais de
40% das vezes. O que importa e a qualidade da probabilidade, medida por log loss,
Brier e RPS, sempre comparada a uma referencia (a base da liga ou o mercado).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from .modelos import CASA, EMPATE, FORA, RESULTADOS

ORDEM = (CASA, EMPATE, FORA)  # ordem natural para o RPS


def log_loss(probabilidade_do_ocorrido: float) -> float:
    """-ln(p) do resultado que de fato aconteceu. Menor e melhor."""
    return -math.log(max(probabilidade_do_ocorrido, 1e-15))


def brier(probabilidades: dict[str, float], resultado: str) -> float:
    """Erro quadratico multiclasse. 0 = perfeito, 2 = pior possivel."""
    return sum(
        (probabilidades.get(chave, 0.0) - (1.0 if chave == resultado else 0.0)) ** 2
        for chave in RESULTADOS
    )


def rps(probabilidades: dict[str, float], resultado: str) -> float:
    """Ranked Probability Score: penaliza menos o erro 'proximo'.

    Prever vitoria do mandante e dar empate custa menos do que prever vitoria do
    mandante e dar vitoria do visitante - o RPS enxerga essa ordem, o Brier nao.
    """
    acumulado_previsto = 0.0
    acumulado_real = 0.0
    total = 0.0
    for chave in ORDEM[:-1]:
        acumulado_previsto += probabilidades.get(chave, 0.0)
        acumulado_real += 1.0 if chave == resultado else 0.0
        total += (acumulado_previsto - acumulado_real) ** 2
    return total / (len(ORDEM) - 1)


@dataclass
class Placar:
    """Acumulador de metricas de uma avaliacao."""

    n: int = 0
    soma_log_loss: float = 0.0
    soma_brier: float = 0.0
    soma_rps: float = 0.0
    acertos: int = 0
    lucro: float = 0.0
    apostas: int = 0
    apostas_vencedoras: int = 0
    volume: float = 0.0
    calibracao: list[tuple[float, float]] = field(default_factory=list)

    def registra(self, probabilidades: dict[str, float], resultado: str) -> None:
        self.n += 1
        self.soma_log_loss += log_loss(probabilidades.get(resultado, 0.0))
        self.soma_brier += brier(probabilidades, resultado)
        self.soma_rps += rps(probabilidades, resultado)
        previsto = max(probabilidades, key=probabilidades.get)
        if previsto == resultado:
            self.acertos += 1
        self.calibracao.append(
            (probabilidades.get(previsto, 0.0), 1.0 if previsto == resultado else 0.0)
        )

    def registra_aposta(self, stake: float, retorno: float, venceu: bool) -> None:
        self.apostas += 1
        self.volume += stake
        self.lucro += retorno
        if venceu:
            self.apostas_vencedoras += 1

    @property
    def log_loss(self) -> float:
        return self.soma_log_loss / self.n if self.n else 0.0

    @property
    def brier(self) -> float:
        return self.soma_brier / self.n if self.n else 0.0

    @property
    def rps(self) -> float:
        return self.soma_rps / self.n if self.n else 0.0

    @property
    def acuracia(self) -> float:
        return self.acertos / self.n if self.n else 0.0

    @property
    def roi(self) -> float:
        return self.lucro / self.volume if self.volume else 0.0

    @property
    def taxa_acerto_apostas(self) -> float:
        return self.apostas_vencedoras / self.apostas if self.apostas else 0.0


def referencia_base(resultados: Sequence[str]) -> dict[str, float]:
    """Distribuicao base da amostra - o piso que qualquer modelo tem que bater."""
    if not resultados:
        return {chave: 1 / 3 for chave in RESULTADOS}
    return {
        chave: sum(1 for r in resultados if r == chave) / len(resultados)
        for chave in RESULTADOS
    }


def curva_de_calibracao(
    pares: Sequence[tuple[float, float]], faixas: int = 5
) -> list[dict[str, float]]:
    """Agrupa previsoes por faixa de probabilidade e compara com o observado.

    Um modelo calibrado acerta ~70% das vezes em que diz "70%".
    """
    if not pares:
        return []
    grupos: list[list[tuple[float, float]]] = [[] for _ in range(faixas)]
    for probabilidade, acerto in pares:
        indice = min(int(probabilidade * faixas), faixas - 1)
        grupos[indice].append((probabilidade, acerto))

    saida = []
    for indice, grupo in enumerate(grupos):
        if not grupo:
            continue
        saida.append(
            {
                "faixa_min": indice / faixas,
                "faixa_max": (indice + 1) / faixas,
                "n": len(grupo),
                "previsto": sum(p for p, _ in grupo) / len(grupo),
                "observado": sum(a for _, a in grupo) / len(grupo),
            }
        )
    return saida
