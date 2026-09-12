"""Validacao walk-forward: o unico teste honesto de um modelo esportivo.

A regra e simples e inegociavel: para prever a partida do dia X, o modelo so
pode ter visto partidas anteriores a X. Treinar com a temporada inteira e depois
"prever" jogos dela produz numeros lindos e inuteis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from . import apostas as mod_apostas
from .metricas import Placar, referencia_base
from .modelos import Partida
from .previsao import Agente


@dataclass
class Avaliacao:
    """Resultado de um backtest."""

    modelo: Placar = field(default_factory=Placar)
    mercado: Placar = field(default_factory=Placar)
    base: Placar = field(default_factory=Placar)
    aquecimento: int = 0
    avaliadas: int = 0
    detalhes: list[dict] = field(default_factory=list)

    @property
    def ganho_sobre_base(self) -> float:
        """Reducao percentual de RPS em relacao a distribuicao base da liga."""
        if not self.base.n or self.base.rps == 0:
            return 0.0
        return (self.base.rps - self.modelo.rps) / self.base.rps

    @property
    def ganho_sobre_mercado(self) -> float:
        if not self.mercado.n or self.mercado.rps == 0:
            return 0.0
        return (self.mercado.rps - self.modelo.rps) / self.mercado.rps


def executa(
    partidas: Sequence[Partida],
    *,
    aquecimento: int = 60,
    refit_a_cada: int = 10,
    peso_elo: float = 0.40,
    meia_vida_dias: float = 730.0,
    ev_minimo: float = 0.05,
    fracao_kelly: float = 0.25,
    odds_por_partida: dict[int, dict[str, float]] | None = None,
    guarda_detalhes: bool = True,
) -> Avaliacao:
    """Roda o backtest cronologico.

    `refit_a_cada` controla de quanto em quanto tempo o Poisson e reajustado
    (o Elo e sempre atualizado partida a partida, por ser incremental).
    Reajustar a cada rodada em vez de a cada jogo muda pouco o resultado e deixa
    o backtest varias vezes mais rapido.
    """
    ordenadas = sorted(partidas, key=lambda p: p.data)
    if len(ordenadas) <= aquecimento:
        raise ValueError(
            f"partidas insuficientes: {len(ordenadas)} para aquecimento de {aquecimento}"
        )

    avaliacao = Avaliacao(aquecimento=aquecimento)
    odds_por_partida = odds_por_partida or {}

    agente: Agente | None = None
    processadas = 0          # quantas partidas o Elo do agente ja viu
    desde_ultimo_ajuste = 0  # quantas partidas desde o ultimo ajuste do Poisson

    for indice in range(aquecimento, len(ordenadas)):
        historico = ordenadas[:indice]
        partida = ordenadas[indice]

        precisa_ajustar = (
            agente is None
            or desde_ultimo_ajuste >= refit_a_cada
            or partida.mandante not in agente.elo.ratings
            or partida.visitante not in agente.elo.ratings
        )
        if precisa_ajustar:
            agente = Agente(
                list(historico), peso_elo=peso_elo, meia_vida_dias=meia_vida_dias
            )
            processadas = indice
            desde_ultimo_ajuste = 0
        else:
            # entre ajustes do Poisson o Elo continua andando, partida a partida
            for anterior in ordenadas[processadas:indice]:
                agente.elo.atualiza(anterior)
            processadas = indice
        desde_ultimo_ajuste += 1
        odds = odds_por_partida.get(indice, {})
        assert agente is not None
        try:
            analise = agente.analisa(
                partida.mandante,
                partida.visitante,
                ev_minimo=ev_minimo,
                fracao_kelly=fracao_kelly,
            )
        except KeyError:
            continue  # time estreando no historico

        resultado = partida.resultado
        avaliacao.modelo.registra(analise.probabilidades, resultado)
        avaliacao.base.registra(
            referencia_base([p.resultado for p in historico]), resultado
        )
        avaliacao.avaliadas += 1

        aposta_registrada = None
        if odds:
            prob_mercado = mod_apostas.remove_margem(odds)
            mercado_1x2 = {
                chave: prob_mercado[chave]
                for chave in ("C", "E", "F")
                if chave in prob_mercado
            }
            if len(mercado_1x2) == 3:
                avaliacao.mercado.registra(mercado_1x2, resultado)

            oportunidades = mod_apostas.encontra_valor(
                analise.todas_probabilidades(),
                odds,
                ev_minimo=ev_minimo,
                fracao_kelly=fracao_kelly,
            )
            for aposta in oportunidades[:1]:  # so a melhor entrada por jogo
                venceu = _resolve(aposta.mercado, partida)
                if venceu is None:
                    continue
                retorno = mod_apostas.resultado_de_aposta(aposta, venceu)
                avaliacao.modelo.registra_aposta(1.0, retorno, venceu)
                aposta_registrada = {
                    "mercado": aposta.mercado,
                    "odd": aposta.odd,
                    "ev": aposta.ev,
                    "venceu": venceu,
                    "retorno": retorno,
                }

        if guarda_detalhes:
            avaliacao.detalhes.append(
                {
                    "data": partida.data,
                    "jogo": f"{partida.mandante} x {partida.visitante}",
                    "placar": f"{partida.gols_mandante}-{partida.gols_visitante}",
                    "resultado": resultado,
                    "probabilidades": dict(analise.probabilidades),
                    "previsto": analise.resultado_mais_provavel,
                    "aposta": aposta_registrada,
                }
            )

    return avaliacao


def _resolve(mercado: str, partida: Partida) -> bool | None:
    """Diz se a selecao venceu, dado o placar final."""
    total = partida.total_gols
    tabela = {
        "C": partida.resultado == "C",
        "E": partida.resultado == "E",
        "F": partida.resultado == "F",
        "1X": partida.resultado in ("C", "E"),
        "12": partida.resultado in ("C", "F"),
        "X2": partida.resultado in ("E", "F"),
        "btts_sim": partida.ambos_marcaram,
        "btts_nao": not partida.ambos_marcaram,
    }
    if mercado in tabela:
        return tabela[mercado]
    if mercado.startswith("over") or mercado.startswith("under"):
        digitos = mercado.replace("over", "").replace("under", "")
        try:
            limite = float(f"{digitos[:-1]}.{digitos[-1]}")
        except (ValueError, IndexError):
            return None
        return total > limite if mercado.startswith("over") else total < limite
    return None
