"""Estruturas de dados centrais do agente.

Todo o restante do pacote (Elo, Poisson, apostas, relatorios) opera sobre
`Partida` e `Confronto`, entao estes objetos sao deliberadamente simples e
imutaveis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

CASA = "C"
EMPATE = "E"
FORA = "F"

RESULTADOS = (CASA, EMPATE, FORA)

NOME_RESULTADO = {
    CASA: "Vitoria do mandante",
    EMPATE: "Empate",
    FORA: "Vitoria do visitante",
}


@dataclass(frozen=True)
class Partida:
    """Uma partida ja encerrada, com placar conhecido."""

    data: date
    mandante: str
    visitante: str
    gols_mandante: int
    gols_visitante: int
    competicao: str = "desconhecida"
    rodada: Optional[int] = None

    def __post_init__(self) -> None:
        if self.gols_mandante < 0 or self.gols_visitante < 0:
            raise ValueError(
                f"placar negativo em {self.mandante} x {self.visitante}: "
                f"{self.gols_mandante}-{self.gols_visitante}"
            )
        if self.mandante == self.visitante:
            raise ValueError(f"time enfrentando a si mesmo: {self.mandante}")

    @property
    def resultado(self) -> str:
        if self.gols_mandante > self.gols_visitante:
            return CASA
        if self.gols_mandante < self.gols_visitante:
            return FORA
        return EMPATE

    @property
    def total_gols(self) -> int:
        return self.gols_mandante + self.gols_visitante

    @property
    def saldo(self) -> int:
        """Saldo de gols do ponto de vista do mandante."""
        return self.gols_mandante - self.gols_visitante

    @property
    def ambos_marcaram(self) -> bool:
        return self.gols_mandante > 0 and self.gols_visitante > 0

    @property
    def times(self) -> tuple[str, str]:
        return (self.mandante, self.visitante)

    def envolve(self, time: str) -> bool:
        return time in self.times

    def gols_de(self, time: str) -> int:
        if time == self.mandante:
            return self.gols_mandante
        if time == self.visitante:
            return self.gols_visitante
        raise KeyError(f"{time} nao participou de {self.mandante} x {self.visitante}")

    def gols_contra(self, time: str) -> int:
        return self.gols_de(self.adversario_de(time))

    def adversario_de(self, time: str) -> str:
        if time == self.mandante:
            return self.visitante
        if time == self.visitante:
            return self.mandante
        raise KeyError(f"{time} nao participou de {self.mandante} x {self.visitante}")

    def pontos_de(self, time: str) -> int:
        marcados, sofridos = self.gols_de(time), self.gols_contra(time)
        if marcados > sofridos:
            return 3
        if marcados == sofridos:
            return 1
        return 0

    def __str__(self) -> str:  # pragma: no cover - conveniencia de depuracao
        return (
            f"{self.data.isoformat()} {self.mandante} {self.gols_mandante}"
            f"-{self.gols_visitante} {self.visitante}"
        )


@dataclass(frozen=True)
class Confronto:
    """Um jogo futuro a ser analisado, opcionalmente com odds de mercado."""

    mandante: str
    visitante: str
    data: Optional[date] = None
    competicao: str = "desconhecida"
    rodada: Optional[int] = None
    odds: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mandante == self.visitante:
            raise ValueError(f"time enfrentando a si mesmo: {self.mandante}")
        for chave, valor in self.odds.items():
            if valor <= 1.0:
                raise ValueError(
                    f"odd decimal invalida para {chave}: {valor} (precisa ser > 1.0)"
                )

    @property
    def tem_odds(self) -> bool:
        return bool(self.odds)

    @property
    def rotulo(self) -> str:
        return f"{self.mandante} x {self.visitante}"


def times_de(partidas: Iterable[Partida]) -> list[str]:
    """Lista ordenada de todos os times presentes nas partidas."""
    nomes: set[str] = set()
    for partida in partidas:
        nomes.update(partida.times)
    return sorted(nomes)
