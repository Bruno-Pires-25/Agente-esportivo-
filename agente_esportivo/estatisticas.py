"""Modelo de contagens: escanteios, chutes, chutes no alvo, cartoes, faltas.

Mesma estrutura do modelo de gols - cada time tem uma forca de produzir e uma de
conceder - com uma diferenca que importa muito na hora de apostar:

**Escanteio nao segue Poisson.** No Brasileirao a variancia dos escanteios e 1,7x
a media (chutes, 1,95x). Uma Poisson pura, que assume variancia igual a media,
subestima sistematicamente as pontas - exatamente onde vivem os mercados de over.
Por isso a media sai por quasi-Poisson (consistente mesmo com superdispersao) e a
distribuicao e Binomial Negativa, com a dispersao estimada dos residuos.

Quando nao ha superdispersao detectavel, a Binomial Negativa converge para a
Poisson sozinha - nao e preciso escolher a mao.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Sequence

from .ajuste import Observacao, ajusta_forcas, dispersao

ESTATISTICAS = (
    "escanteios", "chutes", "chutes_no_alvo", "cartao_amarelo", "faltas",
)

NOMES = {
    "escanteios": "Escanteios",
    "chutes": "Chutes",
    "chutes_no_alvo": "Chutes no alvo",
    "cartao_amarelo": "Cartoes amarelos",
    "faltas": "Faltas",
}

# linhas que as casas costumam oferecer, por estatistica
LINHAS = {
    "escanteios": (7.5, 8.5, 9.5, 10.5, 11.5, 12.5),
    "chutes": (20.5, 22.5, 24.5, 26.5, 28.5),
    "chutes_no_alvo": (6.5, 7.5, 8.5, 9.5, 10.5),
    "cartao_amarelo": (2.5, 3.5, 4.5, 5.5, 6.5),
    "faltas": (24.5, 26.5, 28.5, 30.5),
}


@dataclass(frozen=True)
class RegistroEstatistica:
    """Estatisticas de uma partida, por lado."""

    data: date
    mandante: str
    visitante: str
    valores: dict[str, tuple[int, int]] = field(default_factory=dict)
    competicao: str = "desconhecida"

    def tem(self, estatistica: str) -> bool:
        return estatistica in self.valores

    def par(self, estatistica: str) -> tuple[int, int]:
        return self.valores[estatistica]


def binomial_negativa_pmf(x: int, media: float, k: float) -> float:
    """P(X = x) com media `media` e dispersao `k` (k -> infinito vira Poisson)."""
    if media <= 0:
        return 1.0 if x == 0 else 0.0
    if not math.isfinite(k) or k > 1e6:
        return math.exp(-media + x * math.log(media) - math.lgamma(x + 1))
    p = k / (k + media)
    return math.exp(
        math.lgamma(x + k) - math.lgamma(k) - math.lgamma(x + 1)
        + k * math.log(p) + x * math.log(1 - p)
    )


@dataclass
class ModeloContagem:
    """Forcas de produzir e conceder uma estatistica de contagem."""

    estatistica: str
    meia_vida_dias: float = 730.0
    iteracoes: int = 60
    tolerancia: float = 1e-8

    mu: float = 0.0
    mando: float = 1.0
    k: float = float("inf")
    ataque: dict[str, float] = field(default_factory=dict)
    defesa: dict[str, float] = field(default_factory=dict)
    jogos: dict[str, int] = field(default_factory=dict)
    amostra: int = 0
    referencia: date | None = None
    validacao: "Validacao | None" = None

    @property
    def tem_sinal_conhecido(self) -> bool:
        """So e True quando a validacao rodou E deu sinal positivo.

        Sem validacao o padrao e desconfiar: um numero bonito de um modelo que
        ninguem mediu nao vale mais que um palpite.
        """
        return self.validacao is not None and self.validacao.tem_sinal

    @property
    def nome(self) -> str:
        return NOMES.get(self.estatistica, self.estatistica)

    @property
    def superdisperso(self) -> bool:
        return math.isfinite(self.k)

    @property
    def razao_variancia(self) -> float:
        """Var/media implicada pelo modelo. 1,0 = Poisson."""
        if not self.superdisperso:
            return 1.0
        return 1.0 + self.mu / self.k

    # ------------------------------------------------------------------ ajuste
    def ajusta(
        self, registros: Iterable[RegistroEstatistica], referencia: date | None = None
    ) -> "ModeloContagem":
        usaveis = [r for r in registros if r.tem(self.estatistica)]
        usaveis.sort(key=lambda r: r.data)
        if not usaveis:
            raise ValueError(
                f"nenhuma partida com '{self.estatistica}' na base. "
                "Verifique se o periodo tem essa estatistica coletada."
            )
        self.referencia = referencia or usaveis[-1].data
        self.amostra = len(usaveis)

        if self.meia_vida_dias > 0:
            decaimento = math.log(2) / self.meia_vida_dias
            pesos = [
                math.exp(-decaimento * max((self.referencia - r.data).days, 0))
                for r in usaveis
            ]
        else:
            pesos = [1.0] * len(usaveis)

        observacoes = [
            Observacao(r.mandante, r.visitante, *r.par(self.estatistica)) for r in usaveis
        ]
        forcas = ajusta_forcas(
            observacoes, pesos, iteracoes=self.iteracoes, tolerancia=self.tolerancia
        )
        self.mu, self.mando = forcas.mu, forcas.mando
        self.ataque, self.defesa = forcas.ataque, forcas.defesa

        self.jogos = {}
        for registro in usaveis:
            for time in (registro.mandante, registro.visitante):
                self.jogos[time] = self.jogos.get(time, 0) + 1

        observados: list[float] = []
        esperados: list[float] = []
        for observacao in observacoes:
            casa, fora = self.expectativa(observacao.mandante, observacao.visitante)
            observados.extend([observacao.valor_mandante, observacao.valor_visitante])
            esperados.extend([casa, fora])
        self.k = dispersao(observados, esperados)
        return self

    # ---------------------------------------------------------------- consulta
    def expectativa(self, mandante: str, visitante: str) -> tuple[float, float]:
        casa = self.mu * self.ataque.get(mandante, 1.0) * self.defesa.get(visitante, 1.0) * self.mando
        fora = self.mu * self.ataque.get(visitante, 1.0) * self.defesa.get(mandante, 1.0)
        return max(casa, 1e-6), max(fora, 1e-6)

    def _maximo(self) -> int:
        return max(int(self.mu * 5) + 12, 20)

    def distribuicao_time(self, media: float) -> list[float]:
        return [binomial_negativa_pmf(x, media, self.k) for x in range(self._maximo() + 1)]

    def distribuicao_total(self, mandante: str, visitante: str) -> list[float]:
        """Distribuicao do total da partida (soma dos dois lados).

        Os dois lados entram como independentes dadas as forcas. Nao e exato - um
        jogo aberto rende escanteio para os dois - mas o erro e pequeno perto da
        superdispersao, que ja esta modelada.
        """
        casa, fora = self.expectativa(mandante, visitante)
        pc, pf = self.distribuicao_time(casa), self.distribuicao_time(fora)
        total = [0.0] * (len(pc) + len(pf) - 1)
        for i, a in enumerate(pc):
            if a < 1e-12:
                continue
            for j, b in enumerate(pf):
                total[i + j] += a * b
        soma = sum(total)
        return [v / soma for v in total] if soma > 0 else total

    def acima_de(self, mandante: str, visitante: str, linha: float) -> float:
        """P(total > linha)."""
        distribuicao = self.distribuicao_total(mandante, visitante)
        return sum(p for valor, p in enumerate(distribuicao) if valor > linha)

    def acima_de_time(self, media: float, linha: float) -> float:
        distribuicao = self.distribuicao_time(media)
        soma = sum(distribuicao)
        acima = sum(p for valor, p in enumerate(distribuicao) if valor > linha)
        return acima / soma if soma > 0 else 0.0

    def mercados(self, mandante: str, visitante: str) -> dict[str, float]:
        """Over/under nas linhas usuais, mais os totais esperados."""
        casa, fora = self.expectativa(mandante, visitante)
        saida: dict[str, float] = {
            "esperado_mandante": casa,
            "esperado_visitante": fora,
            "esperado_total": casa + fora,
        }
        for linha in LINHAS.get(self.estatistica, (casa + fora,)):
            acima = self.acima_de(mandante, visitante, linha)
            chave = str(linha).replace(".", "")
            saida[f"over{chave}"] = acima
            saida[f"under{chave}"] = 1.0 - acima
        return saida

    def ranking(self) -> list[tuple[str, float, float]]:
        return sorted(
            ((t, self.ataque[t], self.defesa[t]) for t in self.ataque),
            key=lambda item: -item[1],
        )



@dataclass
class Validacao:
    """Quanto o modelo de uma contagem bate a simples frequencia historica."""

    estatistica: str
    brier_modelo: float
    brier_base: float
    n_treino: int
    n_teste: int
    ano_teste: int

    @property
    def ganho(self) -> float:
        if self.brier_base <= 0:
            return 0.0
        return (self.brier_base - self.brier_modelo) / self.brier_base

    @property
    def tem_sinal(self) -> bool:
        """False quando o modelo perde para o chute mais burro possivel."""
        return self.ganho > 0.005

    @property
    def veredito(self) -> str:
        if self.ganho <= 0:
            return (
                f"SEM SINAL: o modelo de {self.estatistica} e PIOR que a frequencia "
                f"historica da liga ({self.ganho:+.1%}). Nao use para apostar."
            )
        if not self.tem_sinal:
            return (
                f"sinal nulo na pratica ({self.ganho:+.1%} sobre a frequencia "
                "historica): nao cobre a margem de nenhuma casa."
            )
        return (
            f"sinal fraco ({self.ganho:+.1%} sobre a frequencia historica) - "
            "bem abaixo da margem tipica de 5% a 8% de uma casa."
        )


def valida(
    registros: Sequence[RegistroEstatistica],
    estatistica: str,
    ano_teste: int | None = None,
    **kwargs,
) -> Validacao:
    """Treina ate o ano anterior e mede o Brier no ano de teste.

    A referencia nao e zero nem "acertou/errou": e a frequencia historica da
    linha. Um modelo de contagem que nao bate essa frequencia nao tem nada a
    dizer - e vale muito mais descobrir isso aqui do que no extrato.
    """
    disponiveis = [r for r in registros if r.tem(estatistica)]
    if not disponiveis:
        raise ValueError(f"nenhuma partida com '{estatistica}'")
    ano_teste = ano_teste or max(r.data.year for r in disponiveis)

    treino = [r for r in disponiveis if r.data.year < ano_teste]
    teste = [r for r in disponiveis if r.data.year == ano_teste]
    if len(treino) < 100 or len(teste) < 30:
        raise ValueError(
            f"amostra insuficiente para validar '{estatistica}': "
            f"{len(treino)} de treino, {len(teste)} de teste"
        )

    modelo = ModeloContagem(estatistica, **kwargs).ajusta(treino)
    totais_treino = [sum(r.par(estatistica)) for r in treino]

    soma_modelo = soma_base = 0.0
    n = 0
    for linha in LINHAS.get(estatistica, (float(sum(totais_treino)) / len(totais_treino),)):
        base = sum(1 for t in totais_treino if t > linha) / len(totais_treino)
        for registro in teste:
            real = 1.0 if sum(registro.par(estatistica)) > linha else 0.0
            previsto = modelo.acima_de(registro.mandante, registro.visitante, linha)
            soma_modelo += (previsto - real) ** 2
            soma_base += (base - real) ** 2
            n += 1

    return Validacao(
        estatistica=estatistica,
        brier_modelo=soma_modelo / n,
        brier_base=soma_base / n,
        n_treino=len(treino),
        n_teste=len(teste),
        ano_teste=ano_teste,
    )


def ajusta_todos(
    registros: Sequence[RegistroEstatistica],
    estatisticas: Sequence[str] = ESTATISTICAS,
    **kwargs,
) -> dict[str, ModeloContagem]:
    """Ajusta um modelo por estatistica, pulando as que a base nao tem."""
    modelos: dict[str, ModeloContagem] = {}
    for estatistica in estatisticas:
        try:
            modelos[estatistica] = ModeloContagem(estatistica, **kwargs).ajusta(registros)
        except ValueError:
            continue
    return modelos
