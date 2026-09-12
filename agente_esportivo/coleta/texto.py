"""Extrai confrontos e odds de texto solto.

Este e o caminho que sempre funciona: voce abre a casa de apostas no seu
navegador, seleciona a lista de jogos, copia (Ctrl+C) e salva em um arquivo .txt
- ou salva a pagina inteira com Ctrl+S. Nenhuma automacao, nenhum login
programatico, nenhum termo de uso violado. O parser aqui reconhece os tres
layouts que as casas usam na pratica.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Sequence

from ..modelos import Confronto
from ..nomes import resolve

# 1.85 / 1,85 / 10.0 - mas nao 19:00, nem 12/05, nem 2-1
ODD = re.compile(r"^\d{1,3}[.,]\d{1,3}$")
SEPARADOR = re.compile(r"\s+(?:x|vs\.?|×|–|-|@)\s+", re.IGNORECASE)
LINHA_COMPLETA = re.compile(
    r"^(?P<casa>.+?)\s+(?:x|vs\.?|×|@)\s+(?P<fora>.+?)\s+"
    r"(?P<oc>\d{1,3}[.,]\d{1,3})\s+(?P<oe>\d{1,3}[.,]\d{1,3})\s+"
    r"(?P<of>\d{1,3}[.,]\d{1,3})\s*$",
    re.IGNORECASE,
)
MAIS_DE = re.compile(r"(?:mais de|over|\+)\s*(\d[.,]\d)\s*:?\s*(\d{1,3}[.,]\d{1,3})", re.I)
MENOS_DE = re.compile(r"(?:menos de|under|-)\s*(\d[.,]\d)\s*:?\s*(\d{1,3}[.,]\d{1,3})", re.I)
AMBAS_SIM = re.compile(r"ambas\s+marcam[^0-9]{0,20}sim[^0-9]{0,10}(\d{1,3}[.,]\d{1,3})", re.I)
AMBAS_NAO = re.compile(r"ambas\s+marcam[^0-9]{0,20}n[aã]o[^0-9]{0,10}(\d{1,3}[.,]\d{1,3})", re.I)

# linhas que aparecem entre os nomes dos times e nao sao times
IGNORAR = re.compile(
    r"^(?:\d{1,2}:\d{2}|hoje|amanh[aã]|ao vivo|empate|draw|x|1|2|\d{1,2}/\d{1,2}(?:/\d{2,4})?|"
    r"rodada\s*\d*|hor[aá]rio|mercados?|\+\d+|resultado final|1x2)$",
    re.IGNORECASE,
)


def _numero(texto: str) -> float:
    return float(texto.replace(",", "."))


def _e_odd(linha: str) -> bool:
    return bool(ODD.match(linha.strip())) and 1.0 < _numero(linha.strip()) <= 1000.0


class _RemoveTags(HTMLParser):
    """Converte HTML salvo em linhas de texto, descartando script/style."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.linhas: list[str] = []
        self._ignorando = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style", "noscript", "svg"):
            self._ignorando = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "svg"):
            self._ignorando = False

    def handle_data(self, data: str) -> None:
        if self._ignorando:
            return
        texto = data.strip()
        if texto:
            self.linhas.append(texto)


def html_para_texto(html: str) -> str:
    parser = _RemoveTags()
    parser.feed(html)
    return "\n".join(parser.linhas)


def _limpa(texto: str) -> list[str]:
    linhas = []
    for bruta in texto.splitlines():
        linha = re.sub(r"\s+", " ", bruta).strip()
        if linha:
            linhas.append(linha)
    return linhas


def _mercados_extras(bloco: str) -> dict[str, float]:
    """Procura over/under e ambas marcam no texto ao redor do confronto."""
    odds: dict[str, float] = {}
    for regex, prefixo in ((MAIS_DE, "over"), (MENOS_DE, "under")):
        for limite, odd in regex.findall(bloco):
            chave = f"{prefixo}{limite.replace(',', '').replace('.', '')}"
            if chave in ("over25", "under25", "over15", "under15", "over35", "under35"):
                odds.setdefault(chave, _numero(odd))
    for regex, chave in ((AMBAS_SIM, "btts_sim"), (AMBAS_NAO, "btts_nao")):
        achado = regex.search(bloco)
        if achado:
            odds.setdefault(chave, _numero(achado.group(1)))
    return odds


def extrai_confrontos(
    texto: str,
    times_conhecidos: Sequence[str] | None = None,
    *,
    competicao: str = "Brasileirao",
    estrito: bool = False,
) -> list[Confronto]:
    """Le confrontos com odds 1X2 a partir de texto copiado de uma casa.

    Se `times_conhecidos` for informado, os nomes sao resolvidos contra o
    historico (via `nomes.resolve`), o que corrige grafias como "Atlético-MG" x
    "Atletico Mineiro". Com `estrito=True`, confrontos cujo time nao for
    reconhecido sao descartados em vez de entrarem com o nome bruto.
    """
    linhas = _limpa(texto)
    encontrados: list[Confronto] = []
    vistos: set[tuple[str, str]] = set()

    def adiciona(casa: str, fora: str, odds: dict[str, float], contexto: str) -> None:
        casa, fora = casa.strip(" -|"), fora.strip(" -|")
        if not casa or not fora or casa.lower() == fora.lower():
            return
        if times_conhecidos:
            achado_casa = resolve(casa, times_conhecidos)
            achado_fora = resolve(fora, times_conhecidos)
            if estrito and (achado_casa is None or achado_fora is None):
                return
            casa, fora = achado_casa or casa, achado_fora or fora
        chave = (casa.lower(), fora.lower())
        if chave in vistos:
            return
        vistos.add(chave)
        odds.update(
            {k: v for k, v in _mercados_extras(contexto).items() if k not in odds}
        )
        encontrados.append(
            Confronto(mandante=casa, visitante=fora, competicao=competicao, odds=odds)
        )

    # formato 1: tudo em uma linha
    for indice, linha in enumerate(linhas):
        achado = LINHA_COMPLETA.match(linha)
        if achado:
            contexto = "\n".join(linhas[indice : indice + 6])
            adiciona(
                achado.group("casa"),
                achado.group("fora"),
                {
                    "C": _numero(achado.group("oc")),
                    "E": _numero(achado.group("oe")),
                    "F": _numero(achado.group("of")),
                },
                contexto,
            )

    # formato 2: nomes e odds em linhas separadas (layout mais comum das casas)
    indice = 0
    while indice < len(linhas) - 2:
        trio = linhas[indice : indice + 3]
        if all(_e_odd(l) for l in trio):
            nomes: list[str] = []
            recuo = indice - 1
            while recuo >= 0 and len(nomes) < 2:
                candidata = linhas[recuo]
                if _e_odd(candidata) or IGNORAR.match(candidata):
                    recuo -= 1
                    continue
                partes = SEPARADOR.split(candidata)
                if len(partes) == 2:
                    nomes = [partes[0], partes[1]]
                    break
                nomes.insert(0, candidata)
                recuo -= 1
            if len(nomes) == 2:
                contexto = "\n".join(linhas[indice : indice + 8])
                adiciona(
                    nomes[0],
                    nomes[1],
                    {"C": _numero(trio[0]), "E": _numero(trio[1]), "F": _numero(trio[2])},
                    contexto,
                )
            indice += 3
            continue
        indice += 1

    return encontrados


def de_arquivo(
    caminho: str | Path,
    times_conhecidos: Sequence[str] | None = None,
    **kwargs,
) -> list[Confronto]:
    """Le .txt copiado da casa ou .html salvo com Ctrl+S."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"arquivo nao encontrado: {caminho}")
    bruto = caminho.read_text(encoding="utf-8", errors="replace")
    if caminho.suffix.lower() in (".html", ".htm") or "<html" in bruto[:2000].lower():
        bruto = html_para_texto(bruto)
    return extrai_confrontos(bruto, times_conhecidos, **kwargs)
