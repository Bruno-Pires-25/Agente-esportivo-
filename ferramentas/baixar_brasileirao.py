#!/usr/bin/env python3
"""Baixa e converte o historico do Brasileirao para o formato do agente.

Fonte: https://github.com/adaoduque/Brasileirao_Dataset (Serie A, 2003 em
diante, alimentado a partir das sumulas da CBF). O arquivo original tem colunas
extras (arena, tecnico, formacao) que o agente nao usa; aqui ficamos apenas com
data, rodada, times e placar.

    python ferramentas/baixar_brasileirao.py --desde 2021 --saida dados/brasileirao_2021_2024.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agente_esportivo.dados import analisa_data  # noqa: E402

BASE = "https://raw.githubusercontent.com/adaoduque/Brasileirao_Dataset/master/"
FONTE = BASE + "campeonato-brasileiro-full.csv"
FONTE_ESTATISTICAS = BASE + "campeonato-brasileiro-estatisticas-full.csv"

# Colunas do arquivo de estatisticas e o primeiro ano em que cada uma foi de fato
# coletada. Antes disso o arquivo traz zeros, que treinariam um modelo de nada:
# um time com "0 escanteios" em 2010 nao fez zero escanteio, ninguem anotou.
PRIMEIRO_ANO = {
    "escanteios": 2015,
    "chutes": 2015,
    "chutes_no_alvo": 2017,
    "cartao_amarelo": 2015,
    "faltas": 2015,
}
COLUNAS_ESTATISTICAS = tuple(PRIMEIRO_ANO)


def baixa(url: str) -> str:
    with urllib.request.urlopen(url, timeout=120) as resposta:
        return resposta.read().decode("utf-8-sig")


def converte(bruto: str, desde: int, ate: int) -> list[dict[str, object]]:
    leitor = csv.DictReader(io.StringIO(bruto))
    linhas: list[dict[str, object]] = []
    for linha in leitor:
        try:
            data = analisa_data(linha["data"])
        except Exception:
            continue
        if not desde <= data.year <= ate:
            continue
        placar_casa = (linha.get("mandante_Placar") or "").strip()
        placar_fora = (linha.get("visitante_Placar") or "").strip()
        if not placar_casa or not placar_fora:
            continue
        linhas.append(
            {
                "data": data.isoformat(),
                "rodada": (linha.get("rodata") or "").strip(),
                "mandante": linha["mandante"].strip(),
                "visitante": linha["visitante"].strip(),
                "gols_mandante": int(placar_casa),
                "gols_visitante": int(placar_fora),
                "competicao": f"Brasileirao Serie A {data.year}",
            }
        )
    linhas.sort(key=lambda item: (item["data"], item["mandante"]))
    return linhas



def converte_estatisticas(
    bruto_jogos: str, bruto_stats: str, desde: int, ate: int
) -> tuple[list[dict[str, object]], dict[str, int]]:
    """Cruza as estatisticas por time com a tabela de partidas.

    Devolve tambem um diagnostico do que foi descartado - o arquivo de origem
    tem temporadas inteiras zeradas, e entregar isso como dado seria pior do que
    nao ter dado nenhum.
    """
    partidas = {}
    for linha in csv.DictReader(io.StringIO(bruto_jogos)):
        try:
            data = analisa_data(linha["data"])
        except Exception:
            continue
        partidas[linha["ID"]] = (data, linha["mandante"].strip(),
                                 linha["visitante"].strip(), (linha.get("rodata") or "").strip())

    por_partida: dict[str, dict[str, dict[str, str]]] = {}
    for linha in csv.DictReader(io.StringIO(bruto_stats)):
        por_partida.setdefault(linha["partida_id"], {})[linha["clube"].strip()] = linha

    def numero(linha: dict[str, str], campo: str) -> int | None:
        try:
            return int(float((linha.get(campo) or "").strip()))
        except (TypeError, ValueError):
            return None

    saida: list[dict[str, object]] = []
    diagnostico = {"sem_partida": 0, "sem_os_dois_times": 0, "zerado": 0, "fora_do_periodo": 0}

    for partida_id, times in por_partida.items():
        if partida_id not in partidas:
            diagnostico["sem_partida"] += 1
            continue
        data, mandante, visitante, rodada = partidas[partida_id]
        if not desde <= data.year <= ate:
            diagnostico["fora_do_periodo"] += 1
            continue
        if mandante not in times or visitante not in times:
            diagnostico["sem_os_dois_times"] += 1
            continue

        registro: dict[str, object] = {
            "data": data.isoformat(), "rodada": rodada,
            "mandante": mandante, "visitante": visitante,
            "competicao": f"Brasileirao Serie A {data.year}",
        }
        aproveitou = False
        for campo in COLUNAS_ESTATISTICAS:
            casa = numero(times[mandante], campo)
            fora = numero(times[visitante], campo)
            coletado = data.year >= PRIMEIRO_ANO[campo]
            # zero dos dois lados em estatistica de volume e ausencia, nao valor
            ausente = casa in (None, 0) and fora in (None, 0)
            if not coletado or ausente:
                registro[f"{campo}_mandante"] = ""
                registro[f"{campo}_visitante"] = ""
            else:
                registro[f"{campo}_mandante"] = casa
                registro[f"{campo}_visitante"] = fora
                aproveitou = True
        if not aproveitou:
            diagnostico["zerado"] += 1
            continue
        saida.append(registro)

    saida.sort(key=lambda item: (item["data"], item["mandante"]))
    return saida, diagnostico


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desde", type=int, default=2021, help="primeiro ano (padrao: 2021)")
    parser.add_argument("--ate", type=int, default=2100, help="ultimo ano")
    parser.add_argument(
        "--saida", default="dados/brasileirao.csv", help="arquivo CSV de destino"
    )
    parser.add_argument("--fonte", default=FONTE, help="URL do CSV original")
    parser.add_argument("--estatisticas", metavar="ARQUIVO",
                        help="tambem baixa escanteios/chutes/cartoes para este CSV")
    argumentos = parser.parse_args()

    print(f"baixando {argumentos.fonte} ...")
    bruto = baixa(argumentos.fonte)
    linhas = converte(bruto, argumentos.desde, argumentos.ate)
    if not linhas:
        print("nenhuma partida no periodo pedido", file=sys.stderr)
        return 1

    saida = Path(argumentos.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0]))
        escritor.writeheader()
        escritor.writerows(linhas)

    times = {l["mandante"] for l in linhas} | {l["visitante"] for l in linhas}
    print(
        f"{len(linhas)} partidas de {linhas[0]['data']} a {linhas[-1]['data']} "
        f"({len(times)} times) -> {saida}"
    )

    if argumentos.estatisticas:
        print(f"baixando {FONTE_ESTATISTICAS} ...")
        bruto_stats = baixa(FONTE_ESTATISTICAS)
        registros, diagnostico = converte_estatisticas(
            bruto, bruto_stats, argumentos.desde, argumentos.ate
        )
        if not registros:
            print("nenhuma estatistica aproveitavel no periodo", file=sys.stderr)
            return 1
        destino = Path(argumentos.estatisticas)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("w", encoding="utf-8", newline="") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=list(registros[0]))
            escritor.writeheader()
            escritor.writerows(registros)
        print(
            f"{len(registros)} partidas com estatisticas de {registros[0]['data']} "
            f"a {registros[-1]['data']} -> {destino}"
        )
        descartes = ", ".join(f"{k}: {v}" for k, v in diagnostico.items() if v)
        if descartes:
            print(f"  descartadas -> {descartes}")
        for campo in COLUNAS_ESTATISTICAS:
            tem = sum(1 for r in registros if r[f"{campo}_mandante"] != "")
            print(f"  {campo:<16} {tem:>5} partidas ({PRIMEIRO_ANO[campo]} em diante)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
