"""Classificacao, recortes mandante/visitante e forma recente."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .modelos import CASA, EMPATE, FORA, Partida


@dataclass
class Linha:
    """Uma linha da classificacao."""

    time: str
    jogos: int = 0
    vitorias: int = 0
    empates: int = 0
    derrotas: int = 0
    gols_pro: int = 0
    gols_contra: int = 0

    @property
    def pontos(self) -> int:
        return self.vitorias * 3 + self.empates

    @property
    def saldo(self) -> int:
        return self.gols_pro - self.gols_contra

    @property
    def aproveitamento(self) -> float:
        """Percentual de pontos conquistados (0 a 1)."""
        return self.pontos / (3 * self.jogos) if self.jogos else 0.0

    @property
    def media_gols_pro(self) -> float:
        return self.gols_pro / self.jogos if self.jogos else 0.0

    @property
    def media_gols_contra(self) -> float:
        return self.gols_contra / self.jogos if self.jogos else 0.0

    def registra(self, marcados: int, sofridos: int) -> None:
        self.jogos += 1
        self.gols_pro += marcados
        self.gols_contra += sofridos
        if marcados > sofridos:
            self.vitorias += 1
        elif marcados == sofridos:
            self.empates += 1
        else:
            self.derrotas += 1

    @property
    def chave_ordenacao(self) -> tuple:
        # criterio padrao: pontos, vitorias, saldo, gols pro, nome
        return (-self.pontos, -self.vitorias, -self.saldo, -self.gols_pro, self.time)


def classificacao(
    partidas: Iterable[Partida], *, mando: str | None = None
) -> list[Linha]:
    """Monta a classificacao.

    `mando` restringe o recorte: "casa" conta apenas jogos como mandante,
    "fora" apenas como visitante, None conta tudo.
    """
    if mando not in (None, "casa", "fora"):
        raise ValueError("mando deve ser 'casa', 'fora' ou None")

    linhas: dict[str, Linha] = {}

    def linha(time: str) -> Linha:
        return linhas.setdefault(time, Linha(time=time))

    for partida in partidas:
        if mando in (None, "casa"):
            linha(partida.mandante).registra(partida.gols_mandante, partida.gols_visitante)
        if mando in (None, "fora"):
            linha(partida.visitante).registra(partida.gols_visitante, partida.gols_mandante)
    return sorted(linhas.values(), key=lambda l: l.chave_ordenacao)


@dataclass
class Forma:
    """Resumo da forma recente de um time."""

    time: str
    sequencia: str = ""  # ex.: "VVEDV", mais recente a direita
    pontos: int = 0
    jogos: int = 0
    gols_pro: int = 0
    gols_contra: int = 0
    invencibilidade: int = 0
    sem_vencer: int = 0
    ultimas: list[Partida] = field(default_factory=list)

    @property
    def pontos_por_jogo(self) -> float:
        return self.pontos / self.jogos if self.jogos else 0.0

    @property
    def saldo(self) -> int:
        return self.gols_pro - self.gols_contra


def forma(partidas: Sequence[Partida], time: str, janela: int = 5) -> Forma:
    """Forma do time nas ultimas `janela` partidas (ordem cronologica)."""
    if janela <= 0:
        raise ValueError("janela deve ser positiva")
    do_time = [p for p in partidas if p.envolve(time)]
    do_time.sort(key=lambda p: p.data)
    recentes = do_time[-janela:]

    resumo = Forma(time=time, ultimas=recentes)
    letras: list[str] = []
    for partida in recentes:
        marcados, sofridos = partida.gols_de(time), partida.gols_contra(time)
        resumo.jogos += 1
        resumo.gols_pro += marcados
        resumo.gols_contra += sofridos
        resumo.pontos += partida.pontos_de(time)
        letras.append("V" if marcados > sofridos else "E" if marcados == sofridos else "D")
    resumo.sequencia = "".join(letras)

    # sequencias correntes usam o historico completo, nao apenas a janela
    for partida in reversed(do_time):
        if partida.pontos_de(time) == 0:
            break
        resumo.invencibilidade += 1
    for partida in reversed(do_time):
        if partida.pontos_de(time) == 3:
            break
        resumo.sem_vencer += 1
    return resumo


def confrontos_diretos(
    partidas: Iterable[Partida], time_a: str, time_b: str
) -> list[Partida]:
    """Historico direto entre dois times, do mais antigo ao mais recente."""
    diretos = [
        p for p in partidas
        if {p.mandante, p.visitante} == {time_a, time_b}
    ]
    diretos.sort(key=lambda p: p.data)
    return diretos


def resumo_confrontos(
    partidas: Iterable[Partida], time_a: str, time_b: str
) -> dict[str, int]:
    """Placar do retrospecto direto do ponto de vista de `time_a`."""
    diretos = confrontos_diretos(partidas, time_a, time_b)
    resumo = {"jogos": 0, "vitorias_a": 0, "empates": 0, "vitorias_b": 0,
              "gols_a": 0, "gols_b": 0}
    for partida in diretos:
        resumo["jogos"] += 1
        gols_a, gols_b = partida.gols_de(time_a), partida.gols_de(time_b)
        resumo["gols_a"] += gols_a
        resumo["gols_b"] += gols_b
        if gols_a > gols_b:
            resumo["vitorias_a"] += 1
        elif gols_a == gols_b:
            resumo["empates"] += 1
        else:
            resumo["vitorias_b"] += 1
    return resumo


def vantagem_de_mando(partidas: Sequence[Partida]) -> dict[str, float]:
    """Mede o peso do mando de campo no conjunto de partidas."""
    total = len(partidas)
    if not total:
        return {"jogos": 0, "vitorias_casa": 0.0, "empates": 0.0, "vitorias_fora": 0.0,
                "gols_casa": 0.0, "gols_fora": 0.0}
    contagem = {CASA: 0, EMPATE: 0, FORA: 0}
    gols_casa = gols_fora = 0
    for partida in partidas:
        contagem[partida.resultado] += 1
        gols_casa += partida.gols_mandante
        gols_fora += partida.gols_visitante
    return {
        "jogos": total,
        "vitorias_casa": contagem[CASA] / total,
        "empates": contagem[EMPATE] / total,
        "vitorias_fora": contagem[FORA] / total,
        "gols_casa": gols_casa / total,
        "gols_fora": gols_fora / total,
    }
