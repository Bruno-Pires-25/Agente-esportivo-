"""Fabricas de dados usadas pelos testes."""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

from agente_esportivo.modelos import Partida


def liga_sintetica(
    times: int = 8, turnos: int = 2, semente: int = 7
) -> tuple[list[Partida], dict[str, float]]:
    """Gera um campeonato de pontos corridos com forcas conhecidas.

    Devolve as partidas e a forca real de cada time, para que os testes possam
    checar se o modelo recupera a ordem correta.
    """
    sorteio = random.Random(semente)
    nomes = [f"Time {chr(65 + i)}" for i in range(times)]
    forcas = {nome: 0.6 + 0.9 * indice / (times - 1) for indice, nome in enumerate(nomes)}

    def gols(media: float) -> int:
        limite, contagem, produto = math.exp(-media), 0, 1.0
        while True:
            produto *= sorteio.random()
            if produto <= limite:
                return contagem
            contagem += 1

    partidas: list[Partida] = []
    dia = date(2023, 1, 8)
    for turno in range(turnos):
        for casa in nomes:
            for fora in nomes:
                if casa == fora:
                    continue
                if turno % 2 == 1:
                    casa, fora = fora, casa
                media_casa = 1.35 * (forcas[casa] / forcas[fora]) * 1.25
                media_fora = 1.35 * (forcas[fora] / forcas[casa])
                partidas.append(
                    Partida(
                        data=dia,
                        mandante=casa,
                        visitante=fora,
                        gols_mandante=gols(media_casa),
                        gols_visitante=gols(media_fora),
                        competicao="Teste",
                    )
                )
                dia += timedelta(days=1)
                if turno % 2 == 1:
                    casa, fora = fora, casa
    return partidas, forcas


def partidas_simples() -> list[Partida]:
    return [
        Partida(date(2024, 4, 1), "Alfa", "Beta", 2, 0),
        Partida(date(2024, 4, 8), "Beta", "Gama", 1, 1),
        Partida(date(2024, 4, 15), "Gama", "Alfa", 0, 3),
        Partida(date(2024, 4, 22), "Alfa", "Gama", 1, 1),
        Partida(date(2024, 4, 29), "Beta", "Alfa", 0, 2),
        Partida(date(2024, 5, 6), "Gama", "Beta", 2, 1),
    ]
