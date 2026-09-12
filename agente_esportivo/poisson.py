"""Modelo de gols Dixon-Coles (Poisson bivariado) com decaimento temporal.

Ideia: cada time tem uma forca de ataque e uma de defesa; o numero de gols do
mandante segue Poisson(mu * ataque_mandante * defesa_visitante * mando) e o do
visitante Poisson(mu * ataque_visitante * defesa_mandante). Sobre isso aplicamos
a correcao de Dixon-Coles para placares baixos (0-0, 1-0, 0-1, 1-1), que o
Poisson puro subestima, e um peso exponencial que faz jogos antigos importarem
menos.

Diferente do Elo, este modelo devolve a distribuicao completa de placares - e e
dela que saem over/under, ambas marcam, handicap e placar exato.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Sequence

from .ajuste import Observacao, ajusta_forcas
from .modelos import CASA, EMPATE, FORA, Partida

MAX_GOLS = 10


def _log_fatorial(n: int) -> float:
    return math.lgamma(n + 1)


def poisson_pmf(k: int, media: float) -> float:
    if media <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-media + k * math.log(media) - _log_fatorial(k))


def tau_dixon_coles(
    gols_casa: int, gols_fora: int, lambda_casa: float, lambda_fora: float, rho: float
) -> float:
    """Correcao de dependencia para placares baixos."""
    if gols_casa == 0 and gols_fora == 0:
        return 1.0 - lambda_casa * lambda_fora * rho
    if gols_casa == 0 and gols_fora == 1:
        return 1.0 + lambda_casa * rho
    if gols_casa == 1 and gols_fora == 0:
        return 1.0 + lambda_fora * rho
    if gols_casa == 1 and gols_fora == 1:
        return 1.0 - rho
    return 1.0


@dataclass
class Forca:
    """Forcas estimadas de um time (1,0 = media da liga)."""

    time: str
    ataque: float
    defesa: float
    jogos: int

    @property
    def nota(self) -> float:
        """Indice unico de qualidade: ataque alto e defesa baixa sobem a nota."""
        return self.ataque / self.defesa if self.defesa > 0 else self.ataque


@dataclass
class ModeloPoisson:
    """Ajusta ataque/defesa por maxima verossimilhanca ponderada."""

    meia_vida_dias: float = 730.0
    iteracoes: int = 60
    tolerancia: float = 1e-8
    max_gols: int = MAX_GOLS
    ajusta_rho: bool = True

    mu: float = 1.35
    mando: float = 1.30
    rho: float = -0.05
    ataque: dict[str, float] = field(default_factory=dict)
    defesa: dict[str, float] = field(default_factory=dict)
    jogos: dict[str, int] = field(default_factory=dict)
    referencia: date | None = None

    # ------------------------------------------------------------------ ajuste
    def pesos(self, partidas: Sequence[Partida], referencia: date) -> list[float]:
        """Peso exponencial: um jogo de `meia_vida_dias` atras vale metade."""
        if self.meia_vida_dias <= 0:
            return [1.0] * len(partidas)
        decaimento = math.log(2) / self.meia_vida_dias
        return [
            math.exp(-decaimento * max((referencia - p.data).days, 0)) for p in partidas
        ]

    def ajusta(
        self, partidas: Iterable[Partida], referencia: date | None = None
    ) -> "ModeloPoisson":
        partidas = sorted(partidas, key=lambda p: p.data)
        if not partidas:
            raise ValueError("sem partidas para ajustar o modelo")
        self.referencia = referencia or partidas[-1].data
        pesos = self.pesos(partidas, self.referencia)

        times = sorted({t for p in partidas for t in p.times})
        self.jogos = {t: 0 for t in times}
        for partida in partidas:
            for time in partida.times:
                self.jogos[time] += 1

        forcas = ajusta_forcas(
            [
                Observacao(p.mandante, p.visitante, p.gols_mandante, p.gols_visitante)
                for p in partidas
            ],
            pesos,
            iteracoes=self.iteracoes,
            tolerancia=self.tolerancia,
            mando_inicial=self.mando,
        )
        self.mu, self.mando = forcas.mu, forcas.mando
        self.ataque, self.defesa = forcas.ataque, forcas.defesa

        if self.ajusta_rho:
            self.rho = self._melhor_rho(partidas, pesos)
        return self

    def _melhor_rho(self, partidas: Sequence[Partida], pesos: Sequence[float]) -> float:
        """Busca em grade o rho que maximiza a verossimilhanca ponderada."""
        candidatos = [x / 100.0 for x in range(-25, 11)]
        melhor, melhor_ll = 0.0, -math.inf
        for rho in candidatos:
            total = 0.0
            valido = True
            for peso, partida in zip(pesos, partidas):
                lc, lf = self.expectativa(partida.mandante, partida.visitante)
                ajuste = tau_dixon_coles(
                    partida.gols_mandante, partida.gols_visitante, lc, lf, rho
                )
                if ajuste <= 0:
                    valido = False
                    break
                total += peso * (
                    math.log(ajuste)
                    + math.log(max(poisson_pmf(partida.gols_mandante, lc), 1e-300))
                    + math.log(max(poisson_pmf(partida.gols_visitante, lf), 1e-300))
                )
            if valido and total > melhor_ll:
                melhor, melhor_ll = rho, total
        return melhor

    # ------------------------------------------------------------- consultas
    def expectativa(self, mandante: str, visitante: str) -> tuple[float, float]:
        """Gols esperados (lambda) de mandante e visitante."""
        ataque_casa = self.ataque.get(mandante, 1.0)
        defesa_casa = self.defesa.get(mandante, 1.0)
        ataque_fora = self.ataque.get(visitante, 1.0)
        defesa_fora = self.defesa.get(visitante, 1.0)
        lambda_casa = self.mu * ataque_casa * defesa_fora * self.mando
        lambda_fora = self.mu * ataque_fora * defesa_casa
        return max(lambda_casa, 1e-4), max(lambda_fora, 1e-4)

    def matriz(self, mandante: str, visitante: str) -> list[list[float]]:
        """Matriz de probabilidade de cada placar exato, ja normalizada."""
        lambda_casa, lambda_fora = self.expectativa(mandante, visitante)
        n = self.max_gols + 1
        pc = [poisson_pmf(g, lambda_casa) for g in range(n)]
        pf = [poisson_pmf(g, lambda_fora) for g in range(n)]
        matriz = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                ajuste = tau_dixon_coles(i, j, lambda_casa, lambda_fora, self.rho)
                matriz[i][j] = max(pc[i] * pf[j] * ajuste, 0.0)
        total = sum(sum(linha) for linha in matriz)
        if total > 0:
            matriz = [[v / total for v in linha] for linha in matriz]
        return matriz

    def probabilidades(self, mandante: str, visitante: str) -> dict[str, float]:
        """Probabilidades 1X2 a partir da matriz de placares."""
        matriz = self.matriz(mandante, visitante)
        casa = empate = fora = 0.0
        for i, linha in enumerate(matriz):
            for j, valor in enumerate(linha):
                if i > j:
                    casa += valor
                elif i == j:
                    empate += valor
                else:
                    fora += valor
        return {CASA: casa, EMPATE: empate, FORA: fora}

    def forcas(self) -> list[Forca]:
        return sorted(
            (
                Forca(time, self.ataque[time], self.defesa[time], self.jogos.get(time, 0))
                for time in self.ataque
            ),
            key=lambda f: -f.nota,
        )


# --------------------------------------------------------------- mercados
def mercados(matriz: Sequence[Sequence[float]]) -> dict[str, float]:
    """Extrai os mercados usuais de uma matriz de placares."""
    total_gols: dict[int, float] = {}
    ambas = 0.0
    for i, linha in enumerate(matriz):
        for j, valor in enumerate(linha):
            total_gols[i + j] = total_gols.get(i + j, 0.0) + valor
            if i > 0 and j > 0:
                ambas += valor

    saida: dict[str, float] = {"btts_sim": ambas, "btts_nao": 1.0 - ambas}
    for limite in (0.5, 1.5, 2.5, 3.5, 4.5):
        acima = sum(p for gols, p in total_gols.items() if gols > limite)
        chave = str(limite).replace(".", "")
        saida[f"over{chave}"] = acima
        saida[f"under{chave}"] = 1.0 - acima
    saida["gols_esperados"] = sum(gols * p for gols, p in total_gols.items())
    return saida


def dupla_chance(probabilidades: dict[str, float]) -> dict[str, float]:
    return {
        "1X": probabilidades[CASA] + probabilidades[EMPATE],
        "12": probabilidades[CASA] + probabilidades[FORA],
        "X2": probabilidades[EMPATE] + probabilidades[FORA],
    }


def handicap_asiatico(
    matriz: Sequence[Sequence[float]], linha: float
) -> dict[str, float]:
    """Handicap simples (linha inteira ou de meio gol) para o mandante."""
    casa = fora = anulado = 0.0
    for i, valores in enumerate(matriz):
        for j, valor in enumerate(valores):
            diferenca = (i + linha) - j
            if abs(diferenca) < 1e-9:
                anulado += valor
            elif diferenca > 0:
                casa += valor
            else:
                fora += valor
    return {"casa": casa, "anulado": anulado, "fora": fora}


def placares_provaveis(
    matriz: Sequence[Sequence[float]], quantidade: int = 5
) -> list[tuple[str, float]]:
    todos = [
        (f"{i}-{j}", valor)
        for i, linha in enumerate(matriz)
        for j, valor in enumerate(linha)
    ]
    todos.sort(key=lambda item: -item[1])
    return todos[:quantidade]
