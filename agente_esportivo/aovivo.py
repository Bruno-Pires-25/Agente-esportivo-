"""Repreciamento de jogo em andamento.

Um jogo 1-0 aos 70 minutos nao e o mesmo jogo que estava 0-0 no apito inicial: o
que resta e uma partida de 20 minutos, com o placar ja no bolso de alguem. Este
modulo reprecifica os mercados condicionando no estado atual.

Como funciona: os gols esperados da partida inteira sao escalados pelo tempo que
falta, a matriz de placares e recalculada sobre os gols QUE AINDA VAO SAIR, e o
placar atual e somado por cima. Todos os mercados saem dessa distribuicao final.

Limites honestos, porque ao vivo o erro custa caro:

* o modelo nao ve expulsao, lesao, substituicao nem quem esta pressionando;
* nao modela o efeito de placar (time atras se expoe mais) - existe o parametro
  `efeito_placar`, desligado por padrao, porque nao ha dado aqui para calibra-lo;
* o mercado ao vivo se move em segundos e com margem maior que o pre-jogo. Ler a
  tela e digitar aqui ja e tarde para linhas liquidas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import selecoes as sel
from .modelos import CASA, EMPATE, FORA
from .poisson import poisson_pmf

DURACAO = 90


@dataclass(frozen=True)
class Estado:
    """Situacao do jogo neste instante."""

    mandante: str
    visitante: str
    gols_mandante: int = 0
    gols_visitante: int = 0
    minuto: int = 0
    acrescimos: int = 0

    def __post_init__(self) -> None:
        if self.minuto < 0:
            raise ValueError("minuto nao pode ser negativo")
        if self.gols_mandante < 0 or self.gols_visitante < 0:
            raise ValueError("placar nao pode ser negativo")

    @property
    def placar(self) -> str:
        return f"{self.gols_mandante}-{self.gols_visitante}"

    @property
    def minutos_restantes(self) -> int:
        return max(DURACAO + self.acrescimos - self.minuto, 0)

    @property
    def fracao_restante(self) -> float:
        return self.minutos_restantes / DURACAO

    @property
    def encerrado(self) -> bool:
        return self.minutos_restantes == 0


@dataclass
class AnaliseAoVivo:
    """Mercados reprecificados para o estado atual."""

    estado: Estado
    probabilidades: dict[str, float]
    probabilidades_pre: dict[str, float]
    gols_restantes: tuple[float, float]
    matriz_final: list[list[float]]
    mercados: dict[str, float]
    placares: list[tuple[str, float]]

    @property
    def movimento(self) -> dict[str, float]:
        """Quanto cada resultado mudou desde o apito inicial."""
        return {
            chave: self.probabilidades[chave] - self.probabilidades_pre[chave]
            for chave in (CASA, EMPATE, FORA)
        }

    @property
    def favorito(self) -> str:
        chave = max(self.probabilidades, key=self.probabilidades.get)
        if chave == CASA:
            return self.estado.mandante
        if chave == FORA:
            return self.estado.visitante
        return "Empate"

    def probabilidade(self, selecao: str) -> float:
        return sel.probabilidade(self.matriz_final, selecao)

    def probabilidade_conjunta(self, selecoes) -> float:
        return sel.probabilidade_conjunta(self.matriz_final, selecoes)


def reprecifica(
    agente,
    estado: Estado,
    *,
    efeito_placar: float = 0.0,
    max_gols_extras: int = 8,
) -> AnaliseAoVivo:
    """Recalcula os mercados considerando placar e minuto atuais.

    `efeito_placar` (0 = desligado) aumenta em ate essa fracao o ataque de quem
    esta perdendo e reduz o de quem esta ganhando. Deixe em 0 a menos que voce
    tenha calibrado o valor com dados proprios: e um efeito real, mas chutar a
    intensidade so adiciona erro com cara de precisao.
    """
    mandante = agente.valida_time(estado.mandante)
    visitante = agente.valida_time(estado.visitante)
    if mandante != estado.mandante or visitante != estado.visitante:
        estado = Estado(
            mandante, visitante, estado.gols_mandante, estado.gols_visitante,
            estado.minuto, estado.acrescimos,
        )

    lambda_casa, lambda_fora = agente.poisson.expectativa(mandante, visitante)
    restante = estado.fracao_restante
    resto_casa = lambda_casa * restante
    resto_fora = lambda_fora * restante

    if efeito_placar:
        diferenca = estado.gols_mandante - estado.gols_visitante
        if diferenca > 0:
            resto_casa *= 1.0 - efeito_placar
            resto_fora *= 1.0 + efeito_placar
        elif diferenca < 0:
            resto_casa *= 1.0 + efeito_placar
            resto_fora *= 1.0 - efeito_placar

    # matriz dos gols que ainda vao sair; sem a correcao de Dixon-Coles, que foi
    # estimada para placar de jogo inteiro e nao para um trecho dele
    n = max_gols_extras + 1
    pc = [poisson_pmf(k, resto_casa) for k in range(n)]
    pf = [poisson_pmf(k, resto_fora) for k in range(n)]
    total = sum(a * b for a in pc for b in pf)

    tamanho = estado.gols_mandante + estado.gols_visitante + 2 * max_gols_extras + 1
    matriz = [[0.0] * tamanho for _ in range(tamanho)]
    for extras_casa in range(n):
        for extras_fora in range(n):
            i = estado.gols_mandante + extras_casa
            j = estado.gols_visitante + extras_fora
            matriz[i][j] = pc[extras_casa] * pf[extras_fora] / total

    casa = empate = fora = 0.0
    for i, linha in enumerate(matriz):
        for j, valor in enumerate(linha):
            if i > j:
                casa += valor
            elif i == j:
                empate += valor
            else:
                fora += valor

    pre = agente.analisa(mandante, visitante)
    mercados = _mercados(matriz)
    mercados["gols_restantes_esperados"] = resto_casa + resto_fora
    mercados["minutos_restantes"] = float(estado.minutos_restantes)

    placares = sorted(
        (
            (f"{i}-{j}", valor)
            for i, linha in enumerate(matriz)
            for j, valor in enumerate(linha)
            if valor > 0
        ),
        key=lambda item: -item[1],
    )[:6]

    return AnaliseAoVivo(
        estado=estado,
        probabilidades={CASA: casa, EMPATE: empate, FORA: fora},
        probabilidades_pre=pre.probabilidades,
        gols_restantes=(resto_casa, resto_fora),
        matriz_final=matriz,
        mercados=mercados,
        placares=placares,
    )


def _mercados(matriz) -> dict[str, float]:
    """Mercados de gols sobre o placar FINAL (inclui o que ja foi marcado)."""
    saida: dict[str, float] = {}
    for selecao in (
        "over05", "under05", "over15", "under15", "over25", "under25",
        "over35", "under35", "btts_sim", "btts_nao",
    ):
        saida[selecao] = sel.probabilidade(matriz, selecao)
    saida["gols_esperados"] = sum(
        (i + j) * valor for i, linha in enumerate(matriz) for j, valor in enumerate(linha)
    )
    return saida
