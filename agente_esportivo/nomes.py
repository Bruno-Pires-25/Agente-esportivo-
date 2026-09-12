"""Normalizacao de nomes de clubes.

O mesmo time aparece como "Atletico-MG", "Atlético Mineiro", "AtleticoMG" ou
"Galo" dependendo da fonte. Sem uma camada de nomes, cruzar odds de uma casa de
apostas com o historico de partidas vira um pesadelo silencioso: o time nao bate,
o agente diz "time desconhecido" e voce acha que o modelo esta quebrado.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Iterable, Sequence

# sufixos e prefixos que nao ajudam a identificar o clube
RUIDO = (
    "futebol clube", "clube de regatas", "clube atletico", "esporte clube",
    "associacao chapecoense de futebol", "sport club", "sociedade esportiva",
    "regatas", " fc", "fc ", " ec", "ec ", " sc", "sc ", " ac", " cf",
    " futebol", " clube", " esporte", "/", "(", ")",
)

# apelidos e grafias alternativas -> nome canonico
APELIDOS: dict[str, str] = {
    "galo": "Atletico-MG",
    "atletico mineiro": "Atletico-MG",
    "atletico mg": "Atletico-MG",
    "cam": "Atletico-MG",
    "furacao": "Athletico-PR",
    "athletico paranaense": "Athletico-PR",
    "atletico paranaense": "Athletico-PR",
    "cap": "Athletico-PR",
    "atletico goianiense": "Atletico-GO",
    "dragao": "Atletico-GO",
    "timao": "Corinthians",
    "corinthians paulista": "Corinthians",
    "verdao": "Palmeiras",
    "porco": "Palmeiras",
    "mengao": "Flamengo",
    "mengo": "Flamengo",
    "fla": "Flamengo",
    "flu": "Fluminense",
    "botafogo rj": "Botafogo",
    "fogao": "Botafogo",
    "glorioso": "Botafogo",
    "vasco": "Vasco da Gama",
    "gigante da colina": "Vasco da Gama",
    "peixe": "Santos",
    "santos fc": "Santos",
    "sao paulo fc": "Sao Paulo",
    "spfc": "Sao Paulo",
    "soberano": "Sao Paulo",
    "colorado": "Internacional",
    "inter": "Internacional",
    "internacional rs": "Internacional",
    "imortal": "Gremio",
    "tricolor gaucho": "Gremio",
    "raposa": "Cruzeiro",
    "cruzeiro ec": "Cruzeiro",
    "esquadrao": "Bahia",
    "leao do pici": "Fortaleza",
    "vozao": "Ceara",
    "ceara sc": "Ceara",
    "leao": "Sport",
    "sport recife": "Sport",
    "sport club do recife": "Sport",
    "rb bragantino": "Bragantino",
    "red bull bragantino": "Bragantino",
    "bragantino sp": "Bragantino",
    "massa bruta": "Bragantino",
    "dourado": "Cuiaba",
    "tigre": "Criciuma",
    "leao da barra": "Vitoria",
    "papo": "Juventude",
    "ec juventude": "Juventude",
    "leao caipira": "Mirassol",
    "coritiba fc": "Coritiba",
    "coxa": "Coritiba",
    "goias ec": "Goias",
    "esmeraldino": "Goias",
    "america mg": "America-MG",
    "coelho": "America-MG",
    "chape": "Chapecoense",
}


def normaliza(nome: str) -> str:
    """Forma canonica para comparacao: sem acento, sem ruido, sem caixa."""
    texto = unicodedata.normalize("NFKD", nome.strip().lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.replace("-", " ").replace(".", " ")
    for ruido in RUIDO:
        texto = texto.replace(ruido, " ")
    texto = re.sub(r"[^a-z0-9 ]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def canonico(nome: str) -> str:
    """Aplica a tabela de apelidos; devolve o proprio nome se nao conhecer."""
    chave = normaliza(nome)
    if chave in APELIDOS:
        return APELIDOS[chave]
    return nome.strip()


def resolve(
    nome: str, conhecidos: Sequence[str], *, corte: float = 0.82
) -> str | None:
    """Encontra, entre `conhecidos`, o time que corresponde a `nome`.

    Tenta, nesta ordem: igualdade normalizada, tabela de apelidos, prefixo unico
    e, por fim, similaridade de texto. Devolve None quando nada bate com
    seguranca - melhor ficar em duvida do que cruzar o time errado.
    """
    if not nome or not conhecidos:
        return None

    mapa = {normaliza(c): c for c in conhecidos}
    alvo = normaliza(nome)
    if alvo in mapa:
        return mapa[alvo]

    apelido = normaliza(canonico(nome))
    if apelido in mapa:
        return mapa[apelido]

    prefixos = [real for chave, real in mapa.items() if chave.startswith(alvo) or alvo.startswith(chave)]
    if len(set(prefixos)) == 1:
        return prefixos[0]

    proximos = difflib.get_close_matches(alvo, list(mapa), n=1, cutoff=corte)
    if proximos:
        return mapa[proximos[0]]
    return None


def resolve_varios(
    nomes: Iterable[str], conhecidos: Sequence[str]
) -> dict[str, str | None]:
    return {nome: resolve(nome, conhecidos) for nome in nomes}
