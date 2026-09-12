"""Rating Elo adaptado a futebol.

Diferencas em relacao ao Elo classico de xadrez:

* bonus fixo de pontos para o mandante (`vantagem_mando`);
* fator K amplificado pela margem de gols, para que uma goleada mova mais o
  rating do que uma vitoria magra;
* probabilidade de empate modelada explicitamente - o Elo puro so devolve o
  "score esperado" (vitoria = 1, empate = 0,5), que sozinho nao separa 1X2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .modelos import CASA, EMPATE, FORA, Partida

RATING_INICIAL = 1500.0


def multiplicador_de_margem(saldo: int) -> float:
    """Amplifica o K conforme a margem de gols (padrao World Football Elo)."""
    margem = abs(saldo)
    if margem <= 1:
        return 1.0
    if margem == 2:
        return 1.5
    return (11 + margem) / 8.0


@dataclass
class Elo:
    """Mantem o rating de cada time e o atualiza partida a partida."""

    k: float = 20.0
    vantagem_mando: float = 65.0
    rating_inicial: float = RATING_INICIAL
    empate_base: float = 0.29
    empate_escala: float = 320.0
    ratings: dict[str, float] = field(default_factory=dict)
    historico: dict[str, list[tuple[object, float]]] = field(default_factory=dict)
    jogos: dict[str, int] = field(default_factory=dict)

    def rating(self, time: str) -> float:
        return self.ratings.get(time, self.rating_inicial)

    def diferenca(self, mandante: str, visitante: str) -> float:
        """Diferenca efetiva de rating, ja com o mando embutido."""
        return self.rating(mandante) + self.vantagem_mando - self.rating(visitante)

    def score_esperado(self, mandante: str, visitante: str) -> float:
        """Score esperado do mandante (vitoria = 1, empate = 0,5)."""
        return 1.0 / (1.0 + 10 ** (-self.diferenca(mandante, visitante) / 400.0))

    def probabilidades(self, mandante: str, visitante: str) -> dict[str, float]:
        """Probabilidades 1X2 derivadas do rating.

        O empate e mais provavel em jogos equilibrados, entao modelamos
        P(empate) como uma gaussiana centrada na diferenca zero e distribuimos o
        restante de forma consistente com o score esperado:
        E = P(casa) + P(empate)/2.
        """
        esperado = self.score_esperado(mandante, visitante)
        dif = self.diferenca(mandante, visitante)
        p_empate = self.empate_base * math.exp(-((dif / self.empate_escala) ** 2))
        p_casa = esperado - p_empate / 2.0
        p_fora = 1.0 - esperado - p_empate / 2.0

        # times muito desiguais poderiam gerar probabilidade negativa
        piso = 1e-4
        p_casa, p_fora = max(p_casa, piso), max(p_fora, piso)
        total = p_casa + p_empate + p_fora
        return {CASA: p_casa / total, EMPATE: p_empate / total, FORA: p_fora / total}

    def atualiza(self, partida: Partida) -> tuple[float, float]:
        """Processa uma partida e devolve a variacao de rating (mandante, visitante)."""
        esperado = self.score_esperado(partida.mandante, partida.visitante)
        obtido = {CASA: 1.0, EMPATE: 0.5, FORA: 0.0}[partida.resultado]
        ajuste = self.k * multiplicador_de_margem(partida.saldo) * (obtido - esperado)

        antes_mandante = self.rating(partida.mandante)
        antes_visitante = self.rating(partida.visitante)
        self.ratings[partida.mandante] = antes_mandante + ajuste
        self.ratings[partida.visitante] = antes_visitante - ajuste

        for time in partida.times:
            self.jogos[time] = self.jogos.get(time, 0) + 1
            self.historico.setdefault(time, []).append((partida.data, self.ratings[time]))
        return ajuste, -ajuste

    def processa(self, partidas) -> "Elo":
        for partida in partidas:
            self.atualiza(partida)
        return self

    def regride_para_media(self, peso: float = 0.25) -> None:
        """Puxa os ratings de volta para a media (uso tipico: virada de temporada)."""
        if not 0.0 <= peso <= 1.0:
            raise ValueError("peso deve estar entre 0 e 1")
        for time, valor in self.ratings.items():
            self.ratings[time] = valor + peso * (self.rating_inicial - valor)

    def ranking(self) -> list[tuple[str, float]]:
        return sorted(self.ratings.items(), key=lambda item: -item[1])

    def copia(self) -> "Elo":
        clone = Elo(
            k=self.k,
            vantagem_mando=self.vantagem_mando,
            rating_inicial=self.rating_inicial,
            empate_base=self.empate_base,
            empate_escala=self.empate_escala,
        )
        clone.ratings = dict(self.ratings)
        clone.jogos = dict(self.jogos)
        clone.historico = {t: list(h) for t, h in self.historico.items()}
        return clone


def treina(partidas, **parametros) -> Elo:
    """Atalho: cria um Elo, processa as partidas em ordem e devolve o modelo."""
    modelo = Elo(**parametros)
    modelo.processa(sorted(partidas, key=lambda p: p.data))
    return modelo
