"""Avaliacao de apostas multiplas (combinadas).

Duas verdades desconfortaveis que este modulo torna visiveis:

1. **Combinar nao cria valor, multiplica margem.** Cada perna carrega a margem
   da casa e elas compoem: cinco pernas a 6% viram ~34% de margem contra voce.
   Por isso a multipla e o produto mais lucrativo que a casa vende.

2. **Pernas do mesmo jogo nao sao independentes.** Multiplicar as
   probabilidades - que e o que quase todo mundo faz - pode errar por dezenas de
   pontos percentuais. "Mais de 2,5 gols" e "ambas marcam" andam juntos; "mandante
   vence" e "menos de 1,5 gols" brigam entre si. Aqui a probabilidade conjunta sai
   da soma das celulas da matriz de placares em que todas as pernas ganham, o que
   e exato, e nao de uma multiplicacao que supoe o que nao existe.

O que o modulo nao faz: escanteios, chutes, cartoes. O modelo so viu placares.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import selecoes as sel
from .apostas import kelly, valor_esperado

PERNA = re.compile(
    r"^\s*(?P<casa>.+?)\s+(?:x|vs\.?|×)\s+(?P<fora>.+?)\s*:\s*"
    r"(?P<selecao>[^@]+?)\s*(?:@\s*(?P<odd>[\d.,]+))?\s*$",
    re.IGNORECASE,
)


class ErroDeCombinada(ValueError):
    """Entrada malformada ou perna que o modelo nao sabe avaliar."""


@dataclass(frozen=True)
class Perna:
    """Uma selecao dentro da combinada."""

    mandante: str
    visitante: str
    selecao: str
    odd: float | None = None

    @property
    def jogo(self) -> tuple[str, str]:
        return (self.mandante, self.visitante)

    @property
    def rotulo(self) -> str:
        return f"{self.mandante} x {self.visitante}: {sel.nome(self.selecao)}"


def analisa_perna(texto: str) -> Perna:
    """Le uma perna no formato 'Mandante x Visitante: selecao @odd'."""
    achado = PERNA.match(texto)
    if not achado:
        raise ErroDeCombinada(
            f"nao entendi a perna {texto!r}.\n"
            "Formato: \"Palmeiras x Flamengo: over25 @1.85\""
        )
    bruto = achado.group("odd")
    odd = None
    if bruto:
        try:
            odd = float(bruto.replace(",", "."))
        except ValueError:
            raise ErroDeCombinada(f"odd invalida em {texto!r}") from None
        if odd <= 1.0:
            raise ErroDeCombinada(f"odd precisa ser > 1,0 em {texto!r}")
    return Perna(
        mandante=achado.group("casa").strip(),
        visitante=achado.group("fora").strip(),
        selecao=achado.group("selecao").strip(),
        odd=odd,
    )


@dataclass
class PernaAvaliada:
    perna: Perna
    probabilidade: float

    @property
    def odd_justa(self) -> float:
        return 1.0 / self.probabilidade if self.probabilidade > 0 else float("inf")


@dataclass
class Combinada:
    """Resultado da avaliacao de uma multipla."""

    pernas: list[PernaAvaliada]
    conjunta: float
    ingenua: float
    odd_oferecida: float | None
    por_jogo: dict[tuple[str, str], float] = field(default_factory=dict)
    preco_do_produto: bool = False
    """True quando a odd usada e o produto das pernas, e nao um preco real da casa."""
    sem_sinal: tuple[str, ...] = ()
    """Estatisticas cujo modelo nao bate a frequencia historica - leia com desconfianca."""

    @property
    def odd_justa(self) -> float:
        return 1.0 / self.conjunta if self.conjunta > 0 else float("inf")

    @property
    def odd_justa_ingenua(self) -> float:
        return 1.0 / self.ingenua if self.ingenua > 0 else float("inf")

    @property
    def correlacao(self) -> float:
        """Quanto a conta ingenua erra. 1,0 = pernas de fato independentes.

        Acima de 1: as pernas se ajudam e multiplicar subestima a multipla.
        Abaixo de 1: as pernas brigam entre si e multiplicar superestima.
        """
        return self.conjunta / self.ingenua if self.ingenua > 0 else float("inf")

    @property
    def ev(self) -> float | None:
        if self.odd_oferecida is None:
            return None
        return valor_esperado(self.conjunta, self.odd_oferecida)

    @property
    def stake_kelly(self) -> float:
        if self.odd_oferecida is None:
            return 0.0
        return kelly(self.conjunta, self.odd_oferecida, 0.25)

    @property
    def mesmo_jogo(self) -> bool:
        return len({p.perna.jogo for p in self.pernas}) == 1


def margem_composta(margem_por_perna: float, pernas: int) -> float:
    """Margem total de uma multipla com N pernas de mesma margem.

    E a conta que a casa faz e o apostador nao: 6% por perna em 4 pernas nao da
    6%, da 26%.
    """
    if margem_por_perna < 0 or pernas < 1:
        raise ValueError("margem nao negativa e ao menos uma perna")
    return (1.0 + margem_por_perna) ** pernas - 1.0


def avalia(agente, pernas, odd_total: float | None = None) -> Combinada:
    """Avalia a combinada com o modelo do agente.

    Dentro de um mesmo jogo a probabilidade conjunta e exata (soma das celulas da
    matriz). Entre jogos diferentes, as probabilidades sao multiplicadas - dois
    jogos distintos sao razoavelmente independentes.
    """
    pernas = list(pernas)
    if not pernas:
        raise ErroDeCombinada("informe ao menos uma perna")

    grupos: dict[tuple[str, str], list[Perna]] = {}
    avaliadas: list[PernaAvaliada] = []
    conjunta = 1.0
    ingenua = 1.0
    por_jogo: dict[tuple[str, str], float] = {}
    sem_sinal: set[str] = set()

    for perna in pernas:
        try:
            mandante = agente.valida_time(perna.mandante)
            visitante = agente.valida_time(perna.visitante)
        except KeyError as erro:
            raise ErroDeCombinada(str(erro)) from erro
        grupos.setdefault((mandante, visitante), []).append(
            Perna(mandante, visitante, perna.selecao, perna.odd)
        )

    for jogo, do_jogo in grupos.items():
        de_gols: list[Perna] = []
        de_contagem: dict[str, list[tuple[Perna, str, float]]] = {}
        for perna in do_jogo:
            leitura = sel.analisa_contagem(perna.selecao)
            if leitura is None:
                de_gols.append(perna)
            else:
                estatistica, tipo, linha = leitura
                if estatistica not in agente.estatisticas:
                    raise ErroDeCombinada(
                        f"'{perna.selecao}' precisa da base de estatisticas por partida. "
                        "Rode com --estatisticas dados/estatisticas_2015_2023.csv "
                        "(gere com ferramentas/baixar_brasileirao.py --estatisticas ...)."
                    )
                de_contagem.setdefault(estatistica, []).append((perna, tipo, linha))

        probabilidade_do_jogo = 1.0

        if de_gols:
            matriz = agente.poisson.matriz(*jogo)
            try:
                parcial = sel.probabilidade_conjunta(matriz, [p.selecao for p in de_gols])
            except sel.MercadoDesconhecido as erro:
                raise ErroDeCombinada(str(erro)) from erro
            probabilidade_do_jogo *= parcial
            for perna in de_gols:
                individual = sel.probabilidade(matriz, perna.selecao)
                ingenua *= individual
                avaliadas.append(PernaAvaliada(perna, individual))

        # Pernas de contagem: exato dentro da mesma estatistica; entre
        # estatisticas diferentes (e contra os gols) multiplicamos, o que os
        # dados sustentam - gols x escanteios tem correlacao -0,04 no
        # Brasileirao, conjunta/produto de 0,98.
        for estatistica, itens in de_contagem.items():
            modelo = agente.estatisticas[estatistica]
            if not modelo.tem_sinal_conhecido:
                sem_sinal.add(estatistica)
            distribuicao = modelo.distribuicao_total(*jogo)
            parcial = sum(
                p for valor, p in enumerate(distribuicao)
                if all(
                    valor > linha if tipo == "over" else valor < linha
                    for _, tipo, linha in itens
                )
            )
            probabilidade_do_jogo *= parcial
            for perna, tipo, linha in itens:
                acima = sum(p for valor, p in enumerate(distribuicao) if valor > linha)
                individual = acima if tipo == "over" else 1.0 - acima
                ingenua *= individual
                avaliadas.append(PernaAvaliada(perna, individual))

        por_jogo[jogo] = probabilidade_do_jogo
        conjunta *= probabilidade_do_jogo

    oferecida = odd_total
    preco_do_produto = False
    if oferecida is None:
        odds = [p.perna.odd for p in avaliadas]
        oferecida = None if any(o is None for o in odds) else _produto(odds)
        preco_do_produto = oferecida is not None

    return Combinada(
        pernas=avaliadas,
        conjunta=conjunta,
        ingenua=ingenua,
        odd_oferecida=oferecida,
        por_jogo=por_jogo,
        preco_do_produto=preco_do_produto,
        sem_sinal=tuple(sorted(sem_sinal)),
    )


def _produto(valores) -> float:
    total = 1.0
    for valor in valores:
        total *= valor
    return total


def sugere_combinadas(
    agente,
    confrontos,
    *,
    selecoes_candidatas=("C", "F", "1X", "X2", "over15", "over25", "under25", "btts_sim", "btts_nao"),
    minimo_por_perna: float = 0.55,
    pernas: int = 2,
    maximo: int = 10,
):
    """Monta combinadas de duas pernas com as selecoes mais provaveis da rodada.

    Deliberadamente conservador: so entra selecao com probabilidade individual
    acima de `minimo_por_perna`. Ainda assim, leia o resultado como "estas sao as
    menos improvaveis", nunca como "estas vao bater" - e lembre que cada perna
    adicionada multiplica a margem da casa contra voce.
    """
    if pernas < 1:
        raise ValueError("pernas deve ser >= 1")

    candidatas: list[tuple[float, Perna]] = []
    for confronto in confrontos:
        try:
            mandante = agente.valida_time(confronto.mandante)
            visitante = agente.valida_time(confronto.visitante)
        except KeyError:
            continue
        matriz = agente.poisson.matriz(mandante, visitante)
        for selecao in selecoes_candidatas:
            probabilidade = sel.probabilidade(matriz, selecao)
            if probabilidade >= minimo_por_perna:
                candidatas.append(
                    (probabilidade, Perna(mandante, visitante, selecao))
                )

    candidatas.sort(key=lambda item: -item[0])
    escolhidas = [perna for _, perna in candidatas[: maximo * pernas]]

    combinadas: list[Combinada] = []
    vistas: set[frozenset] = set()
    for i, primeira in enumerate(escolhidas):
        for segunda in escolhidas[i + 1:]:
            if pernas == 2 and primeira.jogo == segunda.jogo:
                continue  # combinada de mesmo jogo depende de preco especifico
            chave = frozenset([
                (primeira.jogo, primeira.selecao), (segunda.jogo, segunda.selecao)
            ])
            if chave in vistas:
                continue
            vistas.add(chave)
            combinadas.append(avalia(agente, [primeira, segunda]))
            if len(combinadas) >= maximo:
                return sorted(combinadas, key=lambda c: -c.conjunta)
    return sorted(combinadas, key=lambda c: -c.conjunta)
