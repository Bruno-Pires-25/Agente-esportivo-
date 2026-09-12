"""Ajuste de forcas de ataque e defesa por maxima verossimilhanca ponderada.

O mesmo procedimento serve para qualquer contagem produzida por um time contra
outro: gols, escanteios, chutes, cartoes. A ideia e sempre a mesma - a contagem
esperada do mandante e `mu * ataque_mandante * defesa_visitante * mando`, e as
forcas saem de um ponto fixo que alterna entre atualizar ataques, defesas e o
fator mando ate parar de mudar.

Ficar em um lugar so evita a armadilha de duas copias do mesmo algoritmo
divergindo em silencio quando uma delas e corrigida.
"""

from __future__ import annotations

from typing import Iterable, NamedTuple, Sequence


class Observacao(NamedTuple):
    """Uma partida vista como duas contagens."""

    mandante: str
    visitante: str
    valor_mandante: float
    valor_visitante: float


class Forcas(NamedTuple):
    mu: float
    mando: float
    ataque: dict[str, float]
    defesa: dict[str, float]


def ajusta_forcas(
    observacoes: Sequence[Observacao],
    pesos: Sequence[float] | None = None,
    *,
    iteracoes: int = 60,
    tolerancia: float = 1e-8,
    mando_inicial: float = 1.3,
) -> Forcas:
    """Estima mu, fator mando e as forcas de cada time.

    `pesos` permite dar menos importancia a partidas antigas. Sem pesos, todas
    valem igual.
    """
    if not observacoes:
        raise ValueError("sem observacoes para ajustar")
    pesos = list(pesos) if pesos is not None else [1.0] * len(observacoes)
    if len(pesos) != len(observacoes):
        raise ValueError("pesos e observacoes precisam ter o mesmo tamanho")

    times = sorted({t for o in observacoes for t in (o.mandante, o.visitante)})
    ataque = {t: 1.0 for t in times}
    defesa = {t: 1.0 for t in times}
    mando = mando_inicial

    peso_total = sum(pesos)
    total = sum(w * (o.valor_mandante + o.valor_visitante) for w, o in zip(pesos, observacoes))
    mu = total / (2.0 * peso_total) if peso_total else 1.0
    if mu <= 0:
        raise ValueError("a media das contagens e zero - nao ha o que ajustar")

    produzido = {t: 0.0 for t in times}
    concedido = {t: 0.0 for t in times}
    casa_ponderado = 0.0
    for peso, o in zip(pesos, observacoes):
        produzido[o.mandante] += peso * o.valor_mandante
        produzido[o.visitante] += peso * o.valor_visitante
        concedido[o.mandante] += peso * o.valor_visitante
        concedido[o.visitante] += peso * o.valor_mandante
        casa_ponderado += peso * o.valor_mandante

    for _ in range(iteracoes):
        anterior = (dict(ataque), dict(defesa), mando)

        denominador = {t: 0.0 for t in times}
        for peso, o in zip(pesos, observacoes):
            denominador[o.mandante] += peso * mu * defesa[o.visitante] * mando
            denominador[o.visitante] += peso * mu * defesa[o.mandante]
        for time in times:
            if denominador[time] > 0:
                ataque[time] = max(produzido[time] / denominador[time], 1e-3)

        denominador = {t: 0.0 for t in times}
        for peso, o in zip(pesos, observacoes):
            denominador[o.mandante] += peso * mu * ataque[o.visitante]
            denominador[o.visitante] += peso * mu * ataque[o.mandante] * mando
        for time in times:
            if denominador[time] > 0:
                defesa[time] = max(concedido[time] / denominador[time], 1e-3)

        base = sum(
            peso * mu * ataque[o.mandante] * defesa[o.visitante]
            for peso, o in zip(pesos, observacoes)
        )
        if base > 0:
            mando = max(min(casa_ponderado / base, 3.0), 0.5)

        # ataque medio = 1; o produto ataque*defesa nao muda com essa normalizacao
        media = sum(ataque.values()) / len(times)
        if media > 0:
            for time in times:
                ataque[time] /= media
                defesa[time] *= media

        delta = max(
            max(abs(ataque[t] - anterior[0][t]) for t in times),
            max(abs(defesa[t] - anterior[1][t]) for t in times),
            abs(mando - anterior[2]),
        )
        if delta < tolerancia:
            break

    return Forcas(mu=mu, mando=mando, ataque=ataque, defesa=defesa)


def dispersao(
    observados: Iterable[float], esperados: Iterable[float]
) -> float:
    """Estima o parametro k da Binomial Negativa por momentos.

    Var(y) = mu + mu^2/k. Um k grande significa "quase Poisson"; k pequeno,
    contagem muito dispersa. Devolve infinito quando nao ha superdispersao
    detectavel - ai a Binomial Negativa vira Poisson, que e o comportamento certo.
    """
    numerador = 0.0
    denominador = 0.0
    for y, mu in zip(observados, esperados):
        if mu <= 0:
            continue
        numerador += (y - mu) ** 2 - mu
        denominador += mu ** 2
    if denominador <= 0 or numerador <= 0:
        return float("inf")
    return denominador / numerador
