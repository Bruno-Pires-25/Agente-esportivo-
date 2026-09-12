"""Interface de linha de comando do agente.

    python -m agente_esportivo tabela
    python -m agente_esportivo prever Palmeiras Flamengo
    python -m agente_esportivo odds --arquivo odds_copiadas.txt --banca 500
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

from . import relatorio
from .aovivo import Estado, reprecifica
from .backtest import executa
from .combinadas import ErroDeCombinada, analisa_perna, avalia, sugere_combinadas
from .coleta import ColetaIndisponivel, de_arquivo
from .coleta.navegador import INSTRUCOES, coleta_odds
from .dados import ErroDeDados, escreve_partidas, filtra, le_confrontos, le_partidas
from .modelos import Confronto, Partida
from .previsao import Agente, Analise

BASE_PADRAO = "dados/brasileirao_2021_2024.csv"


# ------------------------------------------------------------------ apoio
def _resolve_base(caminho: str) -> Path:
    """Aceita caminho relativo ao diretorio atual ou a raiz do projeto."""
    alvo = Path(caminho)
    if alvo.exists():
        return alvo
    raiz = Path(__file__).resolve().parent.parent / caminho
    if raiz.exists():
        return raiz
    raise ErroDeDados(
        f"base de partidas nao encontrada: {caminho}\n"
        "Baixe o historico com: python ferramentas/baixar_brasileirao.py"
    )


def carrega_agente(argumentos: argparse.Namespace) -> Agente:
    partidas = le_partidas(_resolve_base(argumentos.dados))
    desde = date(argumentos.desde, 1, 1) if argumentos.desde else None
    ate = date(argumentos.ate, 12, 31) if argumentos.ate else None
    if desde or ate:
        partidas = list(filtra(partidas, desde=desde, ate=ate))
        if not partidas:
            raise ErroDeDados("nenhuma partida no periodo pedido")
    return Agente(
        partidas,
        peso_elo=argumentos.peso_elo,
        meia_vida_dias=argumentos.meia_vida,
        janela_forma=argumentos.janela_forma,
    )


def _odds_dos_argumentos(argumentos: argparse.Namespace) -> dict[str, float]:
    mapa = {
        "C": argumentos.odd_casa,
        "E": argumentos.odd_empate,
        "F": argumentos.odd_fora,
        "over25": argumentos.odd_over25,
        "under25": argumentos.odd_under25,
    }
    return {chave: valor for chave, valor in mapa.items() if valor}


def _analise_para_dicionario(analise: Analise) -> dict:
    return {
        "mandante": analise.confronto.mandante,
        "visitante": analise.confronto.visitante,
        "probabilidades": analise.probabilidades,
        "prob_elo": analise.prob_elo,
        "prob_poisson": analise.prob_poisson,
        "gols_esperados": list(analise.gols_esperados),
        "mercados": analise.mercados,
        "dupla_chance": analise.dupla_chance,
        "placares": analise.placares,
        "confianca": analise.confianca,
        "elo": analise.elo,
        "forma": {
            time: forma.sequencia for time, forma in analise.forma.items()
        },
        "apostas": [
            {
                "mercado": aposta.mercado,
                "nome": aposta.nome,
                "odd": aposta.odd,
                "odd_justa": round(aposta.odd_justa, 3),
                "prob_modelo": aposta.prob_modelo,
                "prob_mercado": aposta.prob_mercado,
                "ev": aposta.ev,
                "kelly": aposta.kelly,
                "stake": aposta.stake,
            }
            for aposta in analise.apostas
        ],
    }


def _saida_json(dados: object) -> None:
    print(json.dumps(dados, ensure_ascii=False, indent=2, default=str))


# --------------------------------------------------------------- comandos
def comando_tabela(argumentos: argparse.Namespace) -> int:
    agente = carrega_agente(argumentos)
    linhas = agente.classificacao(mando=argumentos.mando)
    if argumentos.json:
        _saida_json(
            [
                {
                    "posicao": posicao,
                    "time": linha.time,
                    "pontos": linha.pontos,
                    "jogos": linha.jogos,
                    "vitorias": linha.vitorias,
                    "empates": linha.empates,
                    "derrotas": linha.derrotas,
                    "gols_pro": linha.gols_pro,
                    "gols_contra": linha.gols_contra,
                    "saldo": linha.saldo,
                    "aproveitamento": round(linha.aproveitamento, 4),
                }
                for posicao, linha in enumerate(linhas, start=1)
            ]
        )
    else:
        print(relatorio.formata_classificacao(linhas, argumentos.mando))
    return 0


def comando_ranking(argumentos: argparse.Namespace) -> int:
    agente = carrega_agente(argumentos)
    if argumentos.json:
        _saida_json(
            [
                {
                    "time": time,
                    "elo": round(rating, 1),
                    "ataque": round(forca.ataque, 3) if forca else None,
                    "defesa": round(forca.defesa, 3) if forca else None,
                    "indice": round(forca.nota, 3) if forca else None,
                }
                for time, rating, forca in agente.ranking()
            ]
        )
    else:
        print(relatorio.formata_ranking(agente))
    return 0


def comando_times(argumentos: argparse.Namespace) -> int:
    agente = carrega_agente(argumentos)
    if argumentos.json:
        _saida_json(agente.times)
    else:
        print(relatorio.formata_lista_times(agente.times))
    return 0


def comando_time(argumentos: argparse.Namespace) -> int:
    agente = carrega_agente(argumentos)
    print(relatorio.formata_dossie(agente, argumentos.time))
    return 0


def comando_prever(argumentos: argparse.Namespace) -> int:
    agente = carrega_agente(argumentos)
    confronto = Confronto(
        mandante=argumentos.mandante,
        visitante=argumentos.visitante,
        odds=_odds_dos_argumentos(argumentos),
    )
    analise = agente.analisa(
        confronto,
        banca=argumentos.banca,
        ev_minimo=argumentos.ev_minimo,
        fracao_kelly=argumentos.kelly,
    )
    if argumentos.json:
        _saida_json(_analise_para_dicionario(analise))
    else:
        print(relatorio.formata_analise(analise, detalhado=not argumentos.resumido))
    return 0


def comando_rodada(argumentos: argparse.Namespace) -> int:
    agente = carrega_agente(argumentos)
    confrontos = le_confrontos(_resolve_base(argumentos.arquivo))
    analises = agente.analisa_rodada(
        confrontos,
        banca=argumentos.banca,
        ev_minimo=argumentos.ev_minimo,
        fracao_kelly=argumentos.kelly,
    )
    if argumentos.json:
        _saida_json([_analise_para_dicionario(a) for a in analises])
        return 0

    print(relatorio.formata_rodada(analises))
    if argumentos.detalhado:
        for analise in analises:
            print(relatorio.formata_analise(analise))
    else:
        oportunidades = [a for a in analises if a.apostas]
        if oportunidades:
            print(relatorio.titulo("Onde o modelo discorda do mercado", "-"))
            for analise in oportunidades:
                for aposta in analise.apostas:
                    print(
                        f"  {analise.confronto.rotulo:<32} {aposta.nome:<26} "
                        f"@{relatorio.num(aposta.odd)}  EV +{relatorio.pct(aposta.ev)}"
                        + (f"  stake {relatorio.num(aposta.stake)}" if aposta.stake else "")
                    )
    return 0


def comando_odds(argumentos: argparse.Namespace) -> int:
    agente = carrega_agente(argumentos)
    conhecidos = agente.times

    if argumentos.instrucoes:
        print(INSTRUCOES)
        return 0

    try:
        if argumentos.arquivo:
            confrontos = de_arquivo(
                argumentos.arquivo, conhecidos, estrito=argumentos.estrito
            )
        elif argumentos.cdp or argumentos.perfil:
            confrontos = coleta_odds(
                argumentos.url,
                times_conhecidos=conhecidos,
                estrito=argumentos.estrito,
                cdp=argumentos.cdp,
                perfil=argumentos.perfil,
                seletor=argumentos.seletor,
                esperar_enter=argumentos.esperar,
                salvar_html=argumentos.salvar_html,
            )
        else:
            print(
                "Informe uma origem das odds:\n"
                "  --arquivo odds.txt     texto copiado da casa ou pagina salva (.html)\n"
                "  --cdp http://localhost:9222   navegador seu, ja logado\n"
                "  --perfil ~/.perfil-odds       perfil persistente do Chrome\n"
                "  --instrucoes                  como preparar o navegador",
                file=sys.stderr,
            )
            return 2
    except ColetaIndisponivel as erro:
        print(f"erro na coleta: {erro}", file=sys.stderr)
        return 3

    if not confrontos:
        print(
            "nenhum confronto reconhecido no material coletado.\n"
            "Dica: copie a lista de jogos com as tres odds (casa, empate, fora) "
            "visiveis e tente de novo.",
            file=sys.stderr,
        )
        return 1

    if argumentos.salvar:
        destino = Path(argumentos.salvar)
        destino.parent.mkdir(parents=True, exist_ok=True)
        import csv as _csv

        with destino.open("w", encoding="utf-8", newline="") as arquivo:
            escritor = _csv.writer(arquivo)
            escritor.writerow(
                ["mandante", "visitante", "odd_casa", "odd_empate", "odd_fora",
                 "odd_over25", "odd_under25", "odd_btts_sim", "odd_btts_nao"]
            )
            for confronto in confrontos:
                odds = confronto.odds
                escritor.writerow([
                    confronto.mandante, confronto.visitante,
                    odds.get("C", ""), odds.get("E", ""), odds.get("F", ""),
                    odds.get("over25", ""), odds.get("under25", ""),
                    odds.get("btts_sim", ""), odds.get("btts_nao", ""),
                ])
        print(f"{len(confrontos)} confrontos salvos em {destino}")

    analises = []
    for confronto in confrontos:
        try:
            analises.append(
                agente.analisa(
                    confronto,
                    banca=argumentos.banca,
                    ev_minimo=argumentos.ev_minimo,
                    fracao_kelly=argumentos.kelly,
                )
            )
        except KeyError as erro:
            print(f"ignorando {confronto.rotulo}: {erro}", file=sys.stderr)

    if not analises:
        return 1
    if argumentos.json:
        _saida_json([_analise_para_dicionario(a) for a in analises])
        return 0

    print(relatorio.formata_rodada(analises))
    for analise in analises:
        if analise.apostas:
            print(relatorio.formata_analise(analise, detalhado=argumentos.detalhado))
    return 0



def comando_aovivo(argumentos: argparse.Namespace) -> int:
    agente = carrega_agente(argumentos)
    try:
        gols_casa, gols_fora = (int(x) for x in argumentos.placar.replace(":", "-").split("-"))
    except ValueError:
        print(f"erro: placar invalido '{argumentos.placar}' (use 1-0)", file=sys.stderr)
        return 1

    analise = reprecifica(
        agente,
        Estado(
            mandante=argumentos.mandante,
            visitante=argumentos.visitante,
            gols_mandante=gols_casa,
            gols_visitante=gols_fora,
            minuto=argumentos.minuto,
            acrescimos=argumentos.acrescimos,
        ),
        efeito_placar=argumentos.efeito_placar,
    )

    odds = _odds_dos_argumentos(argumentos)
    apostas = []
    if odds:
        from .apostas import encontra_valor

        probabilidades = dict(analise.probabilidades)
        probabilidades.update(
            {k: v for k, v in analise.mercados.items()
             if k not in ("gols_esperados", "gols_restantes_esperados", "minutos_restantes")}
        )
        apostas = encontra_valor(
            probabilidades, odds, ev_minimo=argumentos.ev_minimo,
            banca=argumentos.banca, fracao_kelly=argumentos.kelly,
        )

    if argumentos.json:
        _saida_json({
            "estado": {
                "mandante": analise.estado.mandante,
                "visitante": analise.estado.visitante,
                "placar": analise.estado.placar,
                "minuto": analise.estado.minuto,
                "minutos_restantes": analise.estado.minutos_restantes,
            },
            "probabilidades": analise.probabilidades,
            "movimento": analise.movimento,
            "gols_restantes": list(analise.gols_restantes),
            "mercados": analise.mercados,
            "placares": analise.placares,
        })
        return 0

    print(relatorio.formata_aovivo(analise))
    if odds:
        print(relatorio.formata_apostas(apostas))
    return 0


def comando_combinar(argumentos: argparse.Namespace) -> int:
    agente = carrega_agente(argumentos)
    try:
        pernas = [analisa_perna(texto) for texto in argumentos.pernas]
        combinada = avalia(agente, pernas, odd_total=argumentos.odd_total)
    except ErroDeCombinada as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1

    if argumentos.json:
        _saida_json({
            "pernas": [
                {"jogo": list(a.perna.jogo), "selecao": a.perna.selecao,
                 "probabilidade": a.probabilidade, "odd": a.perna.odd}
                for a in combinada.pernas
            ],
            "conjunta": combinada.conjunta,
            "ingenua": combinada.ingenua,
            "correlacao": combinada.correlacao,
            "odd_justa": combinada.odd_justa,
            "odd_oferecida": combinada.odd_oferecida,
            "ev": combinada.ev,
        })
        return 0

    print(relatorio.formata_combinada(combinada, banca=argumentos.banca))
    return 0


def comando_sugerir(argumentos: argparse.Namespace) -> int:
    agente = carrega_agente(argumentos)
    confrontos = le_confrontos(_resolve_base(argumentos.arquivo))
    sugestoes = sugere_combinadas(
        agente, confrontos,
        minimo_por_perna=argumentos.minimo,
        maximo=argumentos.maximo,
    )
    if argumentos.json:
        _saida_json([
            {
                "pernas": [
                    {"jogo": list(a.perna.jogo), "selecao": a.perna.selecao,
                     "probabilidade": a.probabilidade}
                    for a in c.pernas
                ],
                "conjunta": c.conjunta,
                "odd_justa": c.odd_justa,
            }
            for c in sugestoes
        ])
        return 0
    print(relatorio.formata_sugestoes(sugestoes, argumentos.maximo))
    return 0


def comando_backtest(argumentos: argparse.Namespace) -> int:
    partidas = le_partidas(_resolve_base(argumentos.dados))
    desde = date(argumentos.desde, 1, 1) if argumentos.desde else None
    ate = date(argumentos.ate, 12, 31) if argumentos.ate else None
    if desde or ate:
        partidas = list(filtra(partidas, desde=desde, ate=ate))

    avaliacao = executa(
        partidas,
        aquecimento=argumentos.aquecimento,
        refit_a_cada=argumentos.refit,
        peso_elo=argumentos.peso_elo,
        meia_vida_dias=argumentos.meia_vida,
        ev_minimo=argumentos.ev_minimo,
        fracao_kelly=argumentos.kelly,
    )
    if argumentos.json:
        _saida_json(
            {
                "avaliadas": avaliacao.avaliadas,
                "modelo": {
                    "rps": avaliacao.modelo.rps,
                    "log_loss": avaliacao.modelo.log_loss,
                    "brier": avaliacao.modelo.brier,
                    "acuracia": avaliacao.modelo.acuracia,
                },
                "base": {
                    "rps": avaliacao.base.rps,
                    "log_loss": avaliacao.base.log_loss,
                    "acuracia": avaliacao.base.acuracia,
                },
                "ganho_sobre_base": avaliacao.ganho_sobre_base,
            }
        )
    else:
        print(relatorio.formata_backtest(avaliacao))
    return 0


def comando_exportar(argumentos: argparse.Namespace) -> int:
    partidas: Sequence[Partida] = le_partidas(_resolve_base(argumentos.dados))
    desde = date(argumentos.desde, 1, 1) if argumentos.desde else None
    ate = date(argumentos.ate, 12, 31) if argumentos.ate else None
    if desde or ate:
        partidas = list(filtra(partidas, desde=desde, ate=ate))
    escreve_partidas(argumentos.saida, partidas)
    print(f"{len(partidas)} partidas gravadas em {argumentos.saida}")
    return 0


# ------------------------------------------------------------------ parser
def _opcoes_comuns(parser: argparse.ArgumentParser, *, com_padroes: bool) -> None:
    """Opcoes aceitas antes e depois do subcomando."""
    def padrao(valor):
        return valor if com_padroes else argparse.SUPPRESS

    parser.add_argument("--dados", default=padrao(BASE_PADRAO), help="CSV de partidas")
    parser.add_argument("--desde", type=int, default=padrao(None),
                        help="considerar apenas a partir deste ano")
    parser.add_argument("--ate", type=int, default=padrao(None),
                        help="considerar apenas ate este ano")
    parser.add_argument("--peso-elo", type=float, default=padrao(0.40), dest="peso_elo",
                        help="peso do Elo na combinacao 1X2 (0 a 1, padrao 0,40)")
    parser.add_argument("--meia-vida", type=float, default=padrao(730.0), dest="meia_vida",
                        help="meia-vida em dias do peso das partidas antigas (padrao 730)")
    parser.add_argument("--janela-forma", type=int, default=padrao(5), dest="janela_forma",
                        help="quantos jogos contam como forma recente (padrao 5)")
    parser.add_argument("--banca", type=float, default=padrao(0.0),
                        help="banca para calcular stake")
    parser.add_argument("--ev-minimo", type=float, default=padrao(0.03), dest="ev_minimo",
                        help="EV minimo para considerar valor (padrao 0,03 = 3%%)")
    parser.add_argument("--kelly", type=float, default=padrao(0.25),
                        help="fracao de Kelly usada no stake (padrao 0,25)")
    parser.add_argument("--json", action="store_true",
                        default=padrao(False), help="saida em JSON")


def constroi_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agente_esportivo",
        description="Agente de analise esportiva - Brasileirao Serie A",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "exemplos:\n"
            "  python -m agente_esportivo tabela --desde 2024\n"
            "  python -m agente_esportivo ranking\n"
            "  python -m agente_esportivo time Palmeiras\n"
            "  python -m agente_esportivo prever Palmeiras Flamengo --odd-casa 2.10\n"
            "  python -m agente_esportivo rodada --arquivo dados/proxima_rodada.csv --banca 500\n"
            "  python -m agente_esportivo odds --arquivo odds.txt --banca 500\n"
            "  python -m agente_esportivo aovivo Botafogo Palmeiras --placar 1-0 --minuto 70\n"
            "  python -m agente_esportivo combinar \"Botafogo x Palmeiras: over25 @2.05\" \\\n"
            "      \"Botafogo x Palmeiras: btts_sim @2.10\" --odd-total 3.40\n"
            "  python -m agente_esportivo backtest --desde 2023\n"
        ),
    )
    _opcoes_comuns(parser, com_padroes=True)

    # as mesmas opcoes aceitas DEPOIS do subcomando ("tabela --desde 2024"),
    # que e como todo mundo digita. SUPPRESS evita que o subparser sobrescreva
    # com o padrao o valor que veio antes do subcomando.
    comuns = argparse.ArgumentParser(add_help=False)
    _opcoes_comuns(comuns, com_padroes=False)

    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("tabela", help="classificacao do campeonato", parents=[comuns])
    p.add_argument("--mando", choices=("casa", "fora"), help="recorte por mando")
    p.set_defaults(funcao=comando_tabela)

    p = sub.add_parser("ranking", help="ranking de forca (Elo + ataque/defesa)", parents=[comuns])
    p.set_defaults(funcao=comando_ranking)

    p = sub.add_parser("times", help="lista os times da base", parents=[comuns])
    p.set_defaults(funcao=comando_times)

    p = sub.add_parser("time", help="dossie completo de um time", parents=[comuns])
    p.add_argument("time")
    p.set_defaults(funcao=comando_time)

    p = sub.add_parser("prever", help="analisa um confronto", parents=[comuns])
    p.add_argument("mandante")
    p.add_argument("visitante")
    p.add_argument("--odd-casa", type=float, dest="odd_casa")
    p.add_argument("--odd-empate", type=float, dest="odd_empate")
    p.add_argument("--odd-fora", type=float, dest="odd_fora")
    p.add_argument("--odd-over25", type=float, dest="odd_over25")
    p.add_argument("--odd-under25", type=float, dest="odd_under25")
    p.add_argument("--resumido", action="store_true", help="so as probabilidades 1X2")
    p.set_defaults(funcao=comando_prever)

    p = sub.add_parser("rodada", help="analisa varios jogos de um CSV", parents=[comuns])
    p.add_argument("--arquivo", default="dados/proxima_rodada.csv")
    p.add_argument("--detalhado", action="store_true", help="cartao completo de cada jogo")
    p.set_defaults(funcao=comando_rodada)

    p = sub.add_parser("odds", help="coleta odds e procura valor", parents=[comuns])
    p.add_argument("--arquivo", help="texto copiado da casa (.txt) ou pagina salva (.html)")
    p.add_argument("--cdp", help="endereco do Chrome ja logado, ex.: http://localhost:9222")
    p.add_argument("--perfil", help="pasta de perfil persistente do Chrome")
    p.add_argument("--url", help="pagina de jogos a abrir no navegador conectado")
    p.add_argument("--seletor", help="seletor CSS da lista de jogos (opcional)")
    p.add_argument("--esperar", action="store_true", help="pausa para voce logar antes de ler")
    p.add_argument("--salvar", help="grava as odds coletadas em CSV")
    p.add_argument("--salvar-html", dest="salvar_html", help="guarda o HTML da pagina lida")
    p.add_argument("--estrito", action="store_true", help="descarta times nao reconhecidos")
    p.add_argument("--detalhado", action="store_true")
    p.add_argument("--instrucoes", action="store_true", help="como preparar o navegador")
    p.set_defaults(funcao=comando_odds)

    p = sub.add_parser("aovivo", help="reprecifica um jogo em andamento", parents=[comuns])
    p.add_argument("mandante")
    p.add_argument("visitante")
    p.add_argument("--placar", default="0-0", help="placar atual, ex.: 1-0")
    p.add_argument("--minuto", type=int, default=0, help="minutos ja jogados")
    p.add_argument("--acrescimos", type=int, default=0)
    p.add_argument("--efeito-placar", type=float, default=0.0, dest="efeito_placar",
                   help="0 a 0,3: quanto quem perde ataca mais (padrao 0 = desligado)")
    p.add_argument("--odd-casa", type=float, dest="odd_casa")
    p.add_argument("--odd-empate", type=float, dest="odd_empate")
    p.add_argument("--odd-fora", type=float, dest="odd_fora")
    p.add_argument("--odd-over25", type=float, dest="odd_over25")
    p.add_argument("--odd-under25", type=float, dest="odd_under25")
    p.set_defaults(funcao=comando_aovivo)

    p = sub.add_parser("combinar", help="avalia uma multipla com correlacao exata", parents=[comuns])
    p.add_argument("pernas", nargs="+",
                   metavar="PERNA", help='ex.: "Palmeiras x Flamengo: over25 @1.85"')
    p.add_argument("--odd-total", type=float, dest="odd_total",
                   help="odd que a casa ofereceu para a multipla inteira")
    p.set_defaults(funcao=comando_combinar)

    p = sub.add_parser("sugerir", help="monta combinadas com as selecoes mais provaveis", parents=[comuns])
    p.add_argument("--arquivo", default="dados/proxima_rodada.csv")
    p.add_argument("--minimo", type=float, default=0.55, help="probabilidade minima por perna")
    p.add_argument("--maximo", type=int, default=10)
    p.set_defaults(funcao=comando_sugerir)

    p = sub.add_parser("backtest", help="validacao walk-forward do modelo", parents=[comuns])
    p.add_argument("--aquecimento", type=int, default=380,
                   help="jogos usados so para treinar (padrao: uma temporada)")
    p.add_argument("--refit", type=int, default=10, help="reajustar o Poisson a cada N jogos")
    p.set_defaults(funcao=comando_backtest)

    p = sub.add_parser("exportar", help="reexporta a base no formato canonico", parents=[comuns])
    p.add_argument("--saida", required=True)
    p.set_defaults(funcao=comando_exportar)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = constroi_parser()
    argumentos = parser.parse_args(argv)
    try:
        return argumentos.funcao(argumentos)
    except (ErroDeDados, KeyError, ValueError) as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    except BrokenPipeError:  # pragma: no cover - `| head` no terminal
        return 0
    except KeyboardInterrupt:  # pragma: no cover
        print("\ninterrompido", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
