#!/usr/bin/env python3
"""Gera o painel web a partir da base de partidas.

O painel (`painel/painel.html`) e uma pagina unica, sem servidor: os parametros
do modelo e os dados dos times ficam embutidos nela, e o calculo das
probabilidades roda no navegador. Este script apenas treina o agente, mede o
backtest e injeta o resultado no template.

    python ferramentas/gerar_painel.py
    python ferramentas/gerar_painel.py --temporada 2025 --sem-backtest

Depois de gerar, publique a pagina como Artifact (ou abra o arquivo direto no
navegador - ela funciona offline).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente_esportivo.backtest import executa  # noqa: E402
from agente_esportivo.dados import le_partidas  # noqa: E402
from agente_esportivo.metricas import curva_de_calibracao  # noqa: E402
from agente_esportivo.previsao import Agente  # noqa: E402
from agente_esportivo.tabela import classificacao, forma, vantagem_de_mando  # noqa: E402

PLACEHOLDER = "__DADOS__"
FONTE_PADRAO = "Dados das súmulas da CBF (via adaoduque/Brasileirao_Dataset)"


def monta_dados(
    caminho_base: Path,
    temporada: int | None,
    com_backtest: bool,
    aquecimento: int,
    fonte: str,
) -> dict:
    partidas = le_partidas(caminho_base)
    agente = Agente(partidas)

    ultima = max(p.data for p in partidas)
    temporada = temporada or ultima.year
    recorte = [p for p in partidas if p.data.year == temporada]
    if not recorte:
        raise SystemExit(f"nenhuma partida de {temporada} em {caminho_base}")

    # O painel mostra o elenco de uma temporada; times que sairam da Serie A
    # ficariam com rating velho e so poluiriam a lista.
    casa = {l.time: l for l in classificacao(recorte, mando="casa")}
    fora = {l.time: l for l in classificacao(recorte, mando="fora")}
    forcas = {f.time: f for f in agente.poisson.forcas()}

    times = []
    for posicao, linha in enumerate(classificacao(recorte), start=1):
        nome = linha.time
        forca = forcas[nome]
        times.append({
            "nome": nome, "pos": posicao, "pts": linha.pontos, "j": linha.jogos,
            "v": linha.vitorias, "e": linha.empates, "d": linha.derrotas,
            "gp": linha.gols_pro, "gc": linha.gols_contra, "sg": linha.saldo,
            "elo": round(agente.elo.rating(nome), 1),
            "ataque": round(forca.ataque, 4), "defesa": round(forca.defesa, 4),
            "jogos_base": forca.jogos,
            "forma": forma(recorte, nome, 5).sequencia,
            "casa_pts": casa[nome].pontos, "casa_j": casa[nome].jogos,
            "fora_pts": fora[nome].pontos, "fora_j": fora[nome].jogos,
        })

    dados = {
        "meta": {
            "ultima_partida": ultima.isoformat(),
            "partidas_base": len(partidas),
            "temporada": temporada,
            "fonte": fonte,
        },
        "modelo": {
            "mu": round(agente.poisson.mu, 5),
            "mando": round(agente.poisson.mando, 5),
            "rho": round(agente.poisson.rho, 4),
            "peso_elo": agente.peso_elo,
            "meia_vida": agente.meia_vida_dias,
            "elo_mando": agente.elo.vantagem_mando,
            "elo_empate_base": agente.elo.empate_base,
            "elo_empate_escala": agente.elo.empate_escala,
        },
        "mando_liga": {
            chave: (round(valor, 4) if isinstance(valor, float) else valor)
            for chave, valor in vantagem_de_mando(recorte).items()
        },
        "times": times,
    }

    if com_backtest:
        avaliacao = executa(partidas, aquecimento=aquecimento, guarda_detalhes=False)
        dados["backtest"] = {
            "n": avaliacao.avaliadas,
            "rps": round(avaliacao.modelo.rps, 4),
            "rps_base": round(avaliacao.base.rps, 4),
            "acuracia": round(avaliacao.modelo.acuracia, 4),
            "log_loss": round(avaliacao.modelo.log_loss, 4),
            "ganho": round(avaliacao.ganho_sobre_base, 4),
            "calibracao": [
                [round(faixa["previsto"], 4), round(faixa["observado"], 4), faixa["n"]]
                for faixa in curva_de_calibracao(avaliacao.modelo.calibracao)
            ],
        }
    return dados


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dados", default="dados/brasileirao_2021_2024.csv")
    parser.add_argument("--modelo", default="painel/modelo.html", help="template HTML")
    parser.add_argument("--saida", default="painel/painel.html")
    parser.add_argument("--temporada", type=int, help="elenco a exibir (padrao: o mais recente)")
    parser.add_argument("--aquecimento", type=int, default=380,
                        help="partidas so para treinar no backtest (padrao: uma temporada)")
    parser.add_argument("--sem-backtest", action="store_true", dest="sem_backtest",
                        help="pula a validacao (a ficha do modelo fica sem numeros)")
    parser.add_argument("--fonte", default=FONTE_PADRAO)
    argumentos = parser.parse_args()

    def caminho(valor: str) -> Path:
        alvo = Path(valor)
        return alvo if alvo.is_absolute() or alvo.exists() else RAIZ / valor

    base, modelo = caminho(argumentos.dados), caminho(argumentos.modelo)
    if not modelo.exists():
        raise SystemExit(f"template nao encontrado: {modelo}")

    if not argumentos.sem_backtest:
        print("treinando e rodando o backtest (leva alguns segundos)...")
    dados = monta_dados(
        base, argumentos.temporada, not argumentos.sem_backtest,
        argumentos.aquecimento, argumentos.fonte,
    )

    html = modelo.read_text(encoding="utf-8")
    if PLACEHOLDER not in html:
        raise SystemExit(f"{modelo} nao tem o marcador {PLACEHOLDER}")
    html = html.replace(
        PLACEHOLDER, json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    )

    saida = Path(argumentos.saida)
    if not saida.is_absolute():
        saida = RAIZ / argumentos.saida
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(html, encoding="utf-8")

    backtest = dados.get("backtest")
    print(
        f"{len(dados['times'])} times da temporada {dados['meta']['temporada']}, "
        f"{dados['meta']['partidas_base']} partidas na base"
        + (f", RPS {backtest['rps']} (base {backtest['rps_base']})" if backtest else "")
    )
    print(f"painel gravado em {saida} ({len(html) // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
