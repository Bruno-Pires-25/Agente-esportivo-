"""Leitura de arquivos CSV de partidas e confrontos.

O leitor aceita tanto o cabecalho nativo em portugues quanto os formatos mais
comuns em bases publicas (football-data.co.uk e derivados em ingles), porque na
pratica os CSVs chegam de fontes diferentes.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from .estatisticas import ESTATISTICAS, RegistroEstatistica
from .modelos import Confronto, Partida

# nome canonico -> apelidos aceitos no cabecalho
ALIASES: dict[str, tuple[str, ...]] = {
    "data": ("data", "date", "dia", "matchdate"),
    "mandante": ("mandante", "casa", "time_casa", "hometeam", "home_team", "home"),
    "visitante": ("visitante", "fora", "time_fora", "awayteam", "away_team", "away"),
    "gols_mandante": (
        "gols_mandante", "golsmandante", "gols_casa", "fthg", "home_goals",
        "homegoals", "hg", "placar_casa",
    ),
    "gols_visitante": (
        "gols_visitante", "golsvisitante", "gols_fora", "ftag", "away_goals",
        "awaygoals", "ag", "placar_fora",
    ),
    "competicao": ("competicao", "campeonato", "liga", "league", "div", "competition"),
    "rodada": ("rodada", "round", "matchweek", "mw"),
    "odd_casa": ("odd_casa", "odds_casa", "oddcasa", "b365h", "psh", "avgh", "home_odds"),
    "odd_empate": ("odd_empate", "odds_empate", "oddempate", "b365d", "psd", "avgd", "draw_odds"),
    "odd_fora": ("odd_fora", "odds_fora", "oddfora", "b365a", "psa", "avga", "away_odds"),
    "odd_over25": ("odd_over25", "odd_mais25", "b365>2.5", "over25", "odd_over"),
    "odd_under25": ("odd_under25", "odd_menos25", "b365<2.5", "under25", "odd_under"),
    "odd_btts_sim": ("odd_btts_sim", "odd_ambas_sim", "btts_sim", "btts_yes"),
    "odd_btts_nao": ("odd_btts_nao", "odd_ambas_nao", "btts_nao", "btts_no"),
}

CHAVES_ODDS = (
    "odd_casa", "odd_empate", "odd_fora",
    "odd_over25", "odd_under25",
    "odd_btts_sim", "odd_btts_nao",
)

MERCADO_POR_CHAVE = {
    "odd_casa": "C",
    "odd_empate": "E",
    "odd_fora": "F",
    "odd_over25": "over25",
    "odd_under25": "under25",
    "odd_btts_sim": "btts_sim",
    "odd_btts_nao": "btts_nao",
}

FORMATOS_DATA = ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y/%m/%d", "%d-%m-%Y")


class ErroDeDados(ValueError):
    """Arquivo de entrada malformado, com mensagem apontando a linha."""


def _normaliza(cabecalho: str) -> str:
    return cabecalho.strip().lower().replace(" ", "_").replace("-", "_").lstrip("﻿")


def _mapa_de_colunas(cabecalhos: Sequence[str]) -> dict[str, str]:
    """Mapeia nome canonico -> nome real da coluna no arquivo."""
    vistos = {_normaliza(c): c for c in cabecalhos if c}
    mapa: dict[str, str] = {}
    for canonico, apelidos in ALIASES.items():
        for apelido in apelidos:
            if apelido in vistos:
                mapa[canonico] = vistos[apelido]
                break
    return mapa


def analisa_data(texto: str) -> date:
    texto = texto.strip()
    for formato in FORMATOS_DATA:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ErroDeDados(f"data nao reconhecida: {texto!r}")


def _inteiro(texto: str, campo: str, linha: int) -> int:
    try:
        return int(float(texto.strip()))
    except (TypeError, ValueError):
        raise ErroDeDados(f"linha {linha}: {campo} invalido ({texto!r})") from None


def _odds_da_linha(linha: dict[str, str], mapa: dict[str, str]) -> dict[str, float]:
    odds: dict[str, float] = {}
    for chave in CHAVES_ODDS:
        coluna = mapa.get(chave)
        if not coluna:
            continue
        bruto = (linha.get(coluna) or "").strip()
        if not bruto:
            continue
        try:
            valor = float(bruto.replace(",", "."))
        except ValueError:
            continue
        if valor > 1.0:
            odds[MERCADO_POR_CHAVE[chave]] = valor
    return odds


def le_partidas(caminho: str | Path) -> list[Partida]:
    """Le um CSV de partidas encerradas, ordenado por data."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroDeDados(f"arquivo nao encontrado: {caminho}")

    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        if not leitor.fieldnames:
            raise ErroDeDados(f"{caminho}: arquivo sem cabecalho")
        mapa = _mapa_de_colunas(leitor.fieldnames)
        faltando = [
            c for c in ("data", "mandante", "visitante", "gols_mandante", "gols_visitante")
            if c not in mapa
        ]
        if faltando:
            raise ErroDeDados(
                f"{caminho}: colunas obrigatorias ausentes: {', '.join(faltando)}. "
                f"Cabecalho lido: {', '.join(leitor.fieldnames)}"
            )

        partidas: list[Partida] = []
        for numero, linha in enumerate(leitor, start=2):
            mandante = (linha.get(mapa["mandante"]) or "").strip()
            visitante = (linha.get(mapa["visitante"]) or "").strip()
            if not mandante or not visitante:
                continue  # linha em branco no fim do arquivo
            placar_casa = (linha.get(mapa["gols_mandante"]) or "").strip()
            placar_fora = (linha.get(mapa["gols_visitante"]) or "").strip()
            if not placar_casa or not placar_fora:
                continue  # jogo ainda nao disputado
            try:
                partida = Partida(
                    data=analisa_data(linha[mapa["data"]]),
                    mandante=mandante,
                    visitante=visitante,
                    gols_mandante=_inteiro(placar_casa, "gols_mandante", numero),
                    gols_visitante=_inteiro(placar_fora, "gols_visitante", numero),
                    competicao=(linha.get(mapa.get("competicao", ""), "") or "desconhecida").strip()
                    or "desconhecida",
                    rodada=(
                        _inteiro(linha[mapa["rodada"]], "rodada", numero)
                        if mapa.get("rodada") and (linha.get(mapa["rodada"]) or "").strip()
                        else None
                    ),
                )
            except ErroDeDados:
                raise
            except ValueError as erro:
                raise ErroDeDados(f"linha {numero}: {erro}") from erro
            partidas.append(partida)

    if not partidas:
        raise ErroDeDados(f"{caminho}: nenhuma partida valida encontrada")
    partidas.sort(key=lambda p: (p.data, p.mandante))
    return partidas


def le_confrontos(caminho: str | Path) -> list[Confronto]:
    """Le um CSV de jogos futuros (com odds opcionais)."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroDeDados(f"arquivo nao encontrado: {caminho}")

    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        if not leitor.fieldnames:
            raise ErroDeDados(f"{caminho}: arquivo sem cabecalho")
        mapa = _mapa_de_colunas(leitor.fieldnames)
        faltando = [c for c in ("mandante", "visitante") if c not in mapa]
        if faltando:
            raise ErroDeDados(
                f"{caminho}: colunas obrigatorias ausentes: {', '.join(faltando)}"
            )

        confrontos: list[Confronto] = []
        for numero, linha in enumerate(leitor, start=2):
            mandante = (linha.get(mapa["mandante"]) or "").strip()
            visitante = (linha.get(mapa["visitante"]) or "").strip()
            if not mandante or not visitante:
                continue
            bruto_data = (linha.get(mapa.get("data", ""), "") or "").strip()
            try:
                confronto = Confronto(
                    mandante=mandante,
                    visitante=visitante,
                    data=analisa_data(bruto_data) if bruto_data else None,
                    competicao=(linha.get(mapa.get("competicao", ""), "") or "desconhecida").strip()
                    or "desconhecida",
                    rodada=(
                        _inteiro(linha[mapa["rodada"]], "rodada", numero)
                        if mapa.get("rodada") and (linha.get(mapa["rodada"]) or "").strip()
                        else None
                    ),
                    odds=_odds_da_linha(linha, mapa),
                )
            except ErroDeDados:
                raise
            except ValueError as erro:
                raise ErroDeDados(f"linha {numero}: {erro}") from erro
            confrontos.append(confronto)

    if not confrontos:
        raise ErroDeDados(f"{caminho}: nenhum confronto valido encontrado")
    return confrontos



def le_estatisticas(caminho: str | Path) -> list[RegistroEstatistica]:
    """Le o CSV de estatisticas por partida (escanteios, chutes, cartoes...).

    Colunas ausentes ou vazias sao simplesmente omitidas do registro, e nao
    viram zero: "nao coletado" e "aconteceu zero vez" sao coisas diferentes, e
    confundi-las treina o modelo em ficcao.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroDeDados(f"arquivo nao encontrado: {caminho}")

    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        if not leitor.fieldnames:
            raise ErroDeDados(f"{caminho}: arquivo sem cabecalho")
        mapa = _mapa_de_colunas(leitor.fieldnames)
        faltando = [c for c in ("data", "mandante", "visitante") if c not in mapa]
        if faltando:
            raise ErroDeDados(
                f"{caminho}: colunas obrigatorias ausentes: {', '.join(faltando)}"
            )

        registros: list[RegistroEstatistica] = []
        for numero, linha in enumerate(leitor, start=2):
            mandante = (linha.get(mapa["mandante"]) or "").strip()
            visitante = (linha.get(mapa["visitante"]) or "").strip()
            if not mandante or not visitante:
                continue
            valores: dict[str, tuple[int, int]] = {}
            for estatistica in ESTATISTICAS:
                casa = (linha.get(f"{estatistica}_mandante") or "").strip()
                fora = (linha.get(f"{estatistica}_visitante") or "").strip()
                if not casa or not fora:
                    continue
                try:
                    valores[estatistica] = (int(float(casa)), int(float(fora)))
                except ValueError:
                    continue
            if not valores:
                continue
            registros.append(
                RegistroEstatistica(
                    data=analisa_data(linha[mapa["data"]]),
                    mandante=mandante,
                    visitante=visitante,
                    valores=valores,
                    competicao=(linha.get(mapa.get("competicao", ""), "") or "desconhecida").strip()
                    or "desconhecida",
                )
            )

    if not registros:
        raise ErroDeDados(f"{caminho}: nenhuma estatistica valida encontrada")
    registros.sort(key=lambda r: (r.data, r.mandante))
    return registros


def escreve_partidas(caminho: str | Path, partidas: Iterable[Partida]) -> None:
    """Grava partidas no formato canonico (util para exportar simulacoes)."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(
            ["data", "rodada", "mandante", "visitante", "gols_mandante",
             "gols_visitante", "competicao"]
        )
        for partida in partidas:
            escritor.writerow([
                partida.data.isoformat(),
                partida.rodada if partida.rodada is not None else "",
                partida.mandante,
                partida.visitante,
                partida.gols_mandante,
                partida.gols_visitante,
                partida.competicao,
            ])


def filtra(
    partidas: Iterable[Partida],
    *,
    competicao: str | None = None,
    desde: date | None = None,
    ate: date | None = None,
    time: str | None = None,
) -> Iterator[Partida]:
    """Filtra partidas por competicao, janela de datas e/ou time."""
    for partida in partidas:
        if competicao and partida.competicao.lower() != competicao.lower():
            continue
        if desde and partida.data < desde:
            continue
        if ate and partida.data > ate:
            continue
        if time and not partida.envolve(time):
            continue
        yield partida
