"""O agente propriamente dito: combina os modelos e produz a analise do jogo.

Nenhum modelo sozinho e bom em tudo. O Elo captura forca geral e sequencia de
resultados, mas nao sabe nada sobre gols; o Dixon-Coles descreve bem a
distribuicao de placares, mas reage devagar a mudancas bruscas de elenco. O
agente roda os dois e combina as probabilidades, dando mais peso ao Poisson no
1X2 e usando exclusivamente ele para os mercados de gols.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Sequence

from . import apostas as mod_apostas
from . import poisson as mod_poisson
from . import tabela as mod_tabela
from .elo import Elo
from .estatisticas import ModeloContagem, RegistroEstatistica, ajusta_todos
from .modelos import CASA, EMPATE, FORA, Confronto, Partida, times_de
from .poisson import ModeloPoisson

PESO_ELO_PADRAO = 0.40   # calibrado em 2023-2024 (ver README)
MEIA_VIDA_PADRAO = 730.0  # duas temporadas: o Brasileirao muda devagar


def _normaliza(probabilidades: dict[str, float]) -> dict[str, float]:
    total = sum(probabilidades.values())
    if total <= 0:
        return {chave: 1.0 / len(probabilidades) for chave in probabilidades}
    return {chave: valor / total for chave, valor in probabilidades.items()}


def combina(
    prob_elo: dict[str, float], prob_poisson: dict[str, float], peso_elo: float
) -> dict[str, float]:
    if not 0.0 <= peso_elo <= 1.0:
        raise ValueError("peso_elo deve estar entre 0 e 1")
    return _normaliza(
        {
            chave: peso_elo * prob_elo[chave] + (1.0 - peso_elo) * prob_poisson[chave]
            for chave in (CASA, EMPATE, FORA)
        }
    )


def divergencia(a: dict[str, float], b: dict[str, float]) -> float:
    """Distancia de variacao total entre duas distribuicoes (0 = identicas)."""
    return 0.5 * sum(abs(a[chave] - b[chave]) for chave in a)


@dataclass
class Analise:
    """Tudo que o agente sabe dizer sobre um confronto."""

    confronto: Confronto
    probabilidades: dict[str, float]
    prob_elo: dict[str, float]
    prob_poisson: dict[str, float]
    gols_esperados: tuple[float, float]
    mercados: dict[str, float]
    dupla_chance: dict[str, float]
    placares: list[tuple[str, float]]
    handicaps: dict[float, dict[str, float]]
    elo: dict[str, float]
    forma: dict[str, mod_tabela.Forma]
    retrospecto: dict[str, int]
    confianca: float
    amostra: dict[str, int]
    apostas: list[mod_apostas.Aposta] = field(default_factory=list)

    @property
    def favorito(self) -> str:
        chave = max(self.probabilidades, key=self.probabilidades.get)
        if chave == CASA:
            return self.confronto.mandante
        if chave == FORA:
            return self.confronto.visitante
        return "Empate"

    @property
    def resultado_mais_provavel(self) -> str:
        return max(self.probabilidades, key=self.probabilidades.get)

    @property
    def placar_provavel(self) -> str:
        return self.placares[0][0] if self.placares else "-"

    @property
    def nivel_confianca(self) -> str:
        if self.confianca >= 0.7:
            return "alta"
        if self.confianca >= 0.45:
            return "media"
        return "baixa"

    def todas_probabilidades(self) -> dict[str, float]:
        """Dicionario unico com todos os mercados, pronto para cruzar com odds."""
        combinadas: dict[str, float] = dict(self.probabilidades)
        combinadas.update(self.dupla_chance)
        for chave, valor in self.mercados.items():
            if chave != "gols_esperados":
                combinadas[chave] = valor
        return combinadas


@dataclass
class Agente:
    """Fachada de alto nivel: carrega partidas, treina e analisa."""

    partidas: list[Partida]
    peso_elo: float = PESO_ELO_PADRAO
    meia_vida_dias: float = MEIA_VIDA_PADRAO
    janela_forma: int = 5
    elo: Elo = field(default_factory=Elo)
    registros_estatisticas: list[RegistroEstatistica] | None = None
    poisson: ModeloPoisson = field(init=False, repr=False, default=None)  # type: ignore[assignment]
    estatisticas: dict[str, ModeloContagem] = field(default_factory=dict)
    referencia: date | None = None

    def __post_init__(self) -> None:
        if not self.partidas:
            raise ValueError("o agente precisa de pelo menos uma partida para treinar")
        self.partidas = sorted(self.partidas, key=lambda p: p.data)
        self.treina()

    # -------------------------------------------------------------- treino
    def treina(self) -> "Agente":
        self.referencia = self.partidas[-1].data
        self.elo = Elo(
            k=self.elo.k,
            vantagem_mando=self.elo.vantagem_mando,
            rating_inicial=self.elo.rating_inicial,
        )
        self.elo.processa(self.partidas)
        self.poisson = ModeloPoisson(meia_vida_dias=self.meia_vida_dias).ajusta(
            self.partidas, referencia=self.referencia
        )
        if self.registros_estatisticas:
            self.estatisticas = ajusta_todos(
                self.registros_estatisticas, meia_vida_dias=self.meia_vida_dias
            )
        return self

    # ------------------------------------------------------------ consultas
    @property
    def times(self) -> list[str]:
        return times_de(self.partidas)

    def valida_time(self, time: str) -> str:
        """Resolve o nome do time aceitando diferenca de caixa e prefixo."""
        conhecidos = self.times
        for nome in conhecidos:
            if nome.lower() == time.lower():
                return nome
        candidatos = [n for n in conhecidos if time.lower() in n.lower()]
        if len(candidatos) == 1:
            return candidatos[0]
        if candidatos:
            raise KeyError(
                f"'{time}' e ambiguo - pode ser: {', '.join(candidatos)}"
            )
        raise KeyError(
            f"time desconhecido: '{time}'. Times disponiveis: {', '.join(conhecidos)}"
        )

    def classificacao(self, mando: str | None = None) -> list[mod_tabela.Linha]:
        return mod_tabela.classificacao(self.partidas, mando=mando)

    def forma(self, time: str) -> mod_tabela.Forma:
        return mod_tabela.forma(self.partidas, self.valida_time(time), self.janela_forma)

    def jogos_de(self, time: str) -> int:
        time = self.valida_time(time)
        return sum(1 for p in self.partidas if p.envolve(time))

    # -------------------------------------------------------------- analise
    def analisa(
        self,
        confronto: Confronto | str,
        visitante: str | None = None,
        *,
        banca: float = 0.0,
        ev_minimo: float = 0.03,
        fracao_kelly: float = 0.25,
    ) -> Analise:
        """Analisa um confronto. Aceita `Confronto` ou dois nomes de time."""
        if isinstance(confronto, str):
            if visitante is None:
                raise ValueError("informe o visitante ou passe um objeto Confronto")
            confronto = Confronto(mandante=confronto, visitante=visitante)

        mandante = self.valida_time(confronto.mandante)
        fora = self.valida_time(confronto.visitante)
        if mandante != confronto.mandante or fora != confronto.visitante:
            confronto = Confronto(
                mandante=mandante,
                visitante=fora,
                data=confronto.data,
                competicao=confronto.competicao,
                rodada=confronto.rodada,
                odds=confronto.odds,
            )

        prob_elo = self.elo.probabilidades(mandante, fora)
        prob_poisson = self.poisson.probabilidades(mandante, fora)
        combinadas = combina(prob_elo, prob_poisson, self.peso_elo)

        matriz = self.poisson.matriz(mandante, fora)
        mercados = mod_poisson.mercados(matriz)
        handicaps = {
            linha: mod_poisson.handicap_asiatico(matriz, linha)
            for linha in (-1.5, -1.0, -0.5, 0.5, 1.0, 1.5)
        }

        amostra = {mandante: self.jogos_de(mandante), fora: self.jogos_de(fora)}
        confianca = self.confianca(prob_elo, prob_poisson, amostra)

        analise = Analise(
            confronto=confronto,
            probabilidades=combinadas,
            prob_elo=prob_elo,
            prob_poisson=prob_poisson,
            gols_esperados=self.poisson.expectativa(mandante, fora),
            mercados=mercados,
            dupla_chance=mod_poisson.dupla_chance(combinadas),
            placares=mod_poisson.placares_provaveis(matriz, 6),
            handicaps=handicaps,
            elo={mandante: self.elo.rating(mandante), fora: self.elo.rating(fora)},
            forma={
                mandante: mod_tabela.forma(self.partidas, mandante, self.janela_forma),
                fora: mod_tabela.forma(self.partidas, fora, self.janela_forma),
            },
            retrospecto=mod_tabela.resumo_confrontos(self.partidas, mandante, fora),
            confianca=confianca,
            amostra=amostra,
        )

        if confronto.tem_odds:
            analise.apostas = mod_apostas.encontra_valor(
                analise.todas_probabilidades(),
                confronto.odds,
                ev_minimo=ev_minimo,
                banca=banca,
                fracao_kelly=fracao_kelly,
            )
        return analise

    @staticmethod
    def confianca(
        prob_elo: dict[str, float],
        prob_poisson: dict[str, float],
        amostra: dict[str, int],
    ) -> float:
        """Quanta fe merece esta estimativa (nao e a chance de o favorito ganhar).

        Sobe quando os dois modelos chegam perto da mesma resposta e quando ha
        jogos suficientes dos dois times na base. Um jogo equilibrado pode ter
        confianca alta: significa "50-50 mesmo", nao "nao faco ideia".
        """
        acordo = 1.0 - divergencia(prob_elo, prob_poisson)
        # modelos discordando menos de 20 pontos ja e o normal; abaixo disso o
        # sinal e ruido, entao reescalamos a faixa util
        acordo_util = max(0.0, (acordo - 0.80) / 0.20)
        dados = min(min(amostra.values()) / 20.0, 1.0)
        return max(0.0, min(1.0, 0.6 * acordo_util + 0.4 * dados))

    def analisa_rodada(
        self, confrontos: Iterable[Confronto], **kwargs
    ) -> list[Analise]:
        return [self.analisa(confronto, **kwargs) for confronto in confrontos]

    def ranking(self) -> list[tuple[str, float, mod_poisson.Forca]]:
        """Ranking de forca: Elo + ataque/defesa do Poisson."""
        forcas = {f.time: f for f in self.poisson.forcas()}
        saida = [
            (time, self.elo.rating(time), forcas.get(time))
            for time in self.times
        ]
        saida.sort(key=lambda item: -item[1])
        return saida


def carrega(partidas: Sequence[Partida], **kwargs) -> Agente:
    return Agente(list(partidas), **kwargs)
