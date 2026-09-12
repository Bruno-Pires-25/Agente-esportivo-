"""Agente de analise esportiva - Brasileirao Serie A.

Uso rapido:

    from agente_esportivo import Agente, le_partidas

    agente = Agente(le_partidas("dados/brasileirao_2021_2024.csv"))
    analise = agente.analisa("Palmeiras", "Flamengo")
    print(analise.probabilidades, analise.placar_provavel)
"""

from .apostas import Aposta, encontra_valor, kelly, remove_margem, valor_esperado
from .backtest import executa as backtest
from .dados import ErroDeDados, le_confrontos, le_partidas
from .elo import Elo
from .modelos import CASA, EMPATE, FORA, Confronto, Partida
from .poisson import ModeloPoisson
from .previsao import Agente, Analise
from .tabela import classificacao, forma

__version__ = "1.0.0"

__all__ = [
    "Agente",
    "Analise",
    "Aposta",
    "CASA",
    "EMPATE",
    "FORA",
    "Confronto",
    "Elo",
    "ErroDeDados",
    "ModeloPoisson",
    "Partida",
    "backtest",
    "classificacao",
    "encontra_valor",
    "forma",
    "kelly",
    "le_confrontos",
    "le_partidas",
    "remove_margem",
    "valor_esperado",
    "__version__",
]
