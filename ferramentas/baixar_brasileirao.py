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

FONTE = (
    "https://raw.githubusercontent.com/adaoduque/Brasileirao_Dataset/"
    "master/campeonato-brasileiro-full.csv"
)


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desde", type=int, default=2021, help="primeiro ano (padrao: 2021)")
    parser.add_argument("--ate", type=int, default=2100, help="ultimo ano")
    parser.add_argument(
        "--saida", default="dados/brasileirao.csv", help="arquivo CSV de destino"
    )
    parser.add_argument("--fonte", default=FONTE, help="URL do CSV original")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
