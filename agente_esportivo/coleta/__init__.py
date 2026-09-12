"""Coleta de odds: do jeito manual (sempre funciona) ou pelo navegador logado."""

from .texto import de_arquivo, extrai_confrontos, html_para_texto
from .navegador import (
    INSTRUCOES,
    ColetaIndisponivel,
    captura_texto,
    coleta_odds,
)

__all__ = [
    "de_arquivo",
    "extrai_confrontos",
    "html_para_texto",
    "captura_texto",
    "coleta_odds",
    "ColetaIndisponivel",
    "INSTRUCOES",
]
