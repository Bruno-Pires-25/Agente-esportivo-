"""Leitura de odds a partir de um navegador que VOCE ja deixou logado.

Desenho deliberado: o script nunca digita usuario e senha em lugar nenhum. Voce
abre o Chrome, faz login (com 2FA, captcha, o que for) e o coletor apenas se
conecta aquela janela e le o texto da pagina. Isso evita guardar credencial em
arquivo, sobrevive a mudanca de tela de login e reduz a chance de o site tratar
a sessao como robo.

Vale lembrar do outro lado: a maioria das casas de apostas proibe automacao nos
termos de uso e pode bloquear a conta. Use em conta propria, sem paralelismo e
sem repetir a coleta em loop - ou fique no modo copiar/colar de `coleta.texto`,
que nao automatiza nada.

Requer o Playwright (opcional):

    pip install playwright && playwright install chromium
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

from ..modelos import Confronto
from .texto import extrai_confrontos, html_para_texto

PORTA_PADRAO = 9222

INSTRUCOES = f"""
Como deixar o navegador pronto para a coleta:

1. Feche o Chrome/Chromium e abra de novo com a porta de depuracao ligada:

   Linux:   google-chrome --remote-debugging-port={PORTA_PADRAO} --user-data-dir=~/.perfil-odds
   macOS:   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \\
                --remote-debugging-port={PORTA_PADRAO} --user-data-dir=~/.perfil-odds
   Windows: chrome.exe --remote-debugging-port={PORTA_PADRAO} --user-data-dir=%TEMP%\\perfil-odds

2. Faca login na casa de apostas normalmente, nessa janela.
3. Deixe aberta a pagina com a lista de jogos do Brasileirao.
4. Rode:  python -m agente_esportivo odds --cdp http://localhost:{PORTA_PADRAO}
""".strip()


class ColetaIndisponivel(RuntimeError):
    """Playwright ausente ou navegador inacessivel."""


def _carrega_playwright():
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as erro:  # pragma: no cover - depende do ambiente
        raise ColetaIndisponivel(
            "Playwright nao instalado. Rode:\n"
            "    pip install playwright && playwright install chromium\n"
            "Ou use o modo sem automacao: copie a pagina e rode "
            "`python -m agente_esportivo odds --arquivo odds.txt`"
        ) from erro
    return sync_playwright


def captura_texto(
    url: str | None = None,
    *,
    cdp: str | None = None,
    perfil: str | Path | None = None,
    seletor: str | None = None,
    espera_ms: int = 4000,
    esperar_enter: bool = False,
    salvar_html: str | Path | None = None,
) -> str:
    """Devolve o texto visivel da pagina de odds.

    `cdp`    - conecta a um Chrome ja aberto e logado (recomendado).
    `perfil` - abre um Chrome proprio com perfil persistente; da para logar na
               primeira vez e reaproveitar a sessao depois.
    """
    if not cdp and not perfil:
        raise ValueError(
            "informe --cdp (navegador ja logado) ou --perfil (perfil persistente).\n"
            + INSTRUCOES
        )

    sync_playwright = _carrega_playwright()
    with sync_playwright() as playwright:
        if cdp:
            try:
                navegador = playwright.chromium.connect_over_cdp(cdp)
            except Exception as erro:  # pragma: no cover - depende do ambiente
                raise ColetaIndisponivel(
                    f"nao consegui conectar em {cdp}: {erro}\n\n{INSTRUCOES}"
                ) from erro
            contexto = navegador.contexts[0] if navegador.contexts else navegador.new_context()
            pagina = _pagina_alvo(contexto, url)
        else:
            contexto = playwright.chromium.launch_persistent_context(
                str(Path(perfil).expanduser()), headless=False
            )
            pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
            if url:
                pagina.goto(url, wait_until="domcontentloaded")

        if esperar_enter:
            print(
                "\nFaca login e deixe a pagina de jogos aberta.\n"
                "Quando estiver pronta, volte aqui e tecle ENTER..."
            )
            input()

        try:
            pagina.wait_for_load_state("networkidle", timeout=espera_ms)
        except Exception:
            pass  # paginas de odds atualizam odd em tempo real e nunca ficam ociosas
        if seletor:
            pagina.wait_for_selector(seletor, timeout=espera_ms)

        alvo = pagina.locator(seletor) if seletor else pagina.locator("body")
        texto = alvo.first.inner_text()
        if salvar_html:
            caminho = Path(salvar_html)
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_text(pagina.content(), encoding="utf-8")

        if perfil:
            contexto.close()
        return texto


def _pagina_alvo(contexto, url: str | None):
    """Reaproveita a aba certa em vez de abrir outra (mantem a sessao logada)."""
    paginas = [p for p in contexto.pages if not p.is_closed()]
    if url:
        for pagina in paginas:
            if url.split("://")[-1].split("/")[0] in pagina.url:
                pagina.bring_to_front()
                if pagina.url.rstrip("/") != url.rstrip("/"):
                    pagina.goto(url, wait_until="domcontentloaded")
                return pagina
        pagina = contexto.new_page()
        pagina.goto(url, wait_until="domcontentloaded")
        return pagina
    if not paginas:
        raise ColetaIndisponivel(
            "o navegador conectado nao tem nenhuma aba aberta - abra a pagina de jogos"
        )
    return paginas[0]


def coleta_odds(
    url: str | None = None,
    *,
    times_conhecidos: Sequence[str] | None = None,
    competicao: str = "Brasileirao",
    estrito: bool = False,
    **kwargs,
) -> list[Confronto]:
    """Captura a pagina e ja devolve os confrontos com odds."""
    texto = captura_texto(url, **kwargs)
    if "<html" in texto[:2000].lower():
        texto = html_para_texto(texto)
    return extrai_confrontos(
        texto, times_conhecidos, competicao=competicao, estrito=estrito
    )


def abre_chrome_com_depuracao(
    porta: int = PORTA_PADRAO, perfil: str = "~/.perfil-odds"
) -> subprocess.Popen | None:  # pragma: no cover - depende da maquina do usuario
    """Tenta abrir o Chrome local ja com a porta de depuracao ligada."""
    caminho_perfil = str(Path(perfil).expanduser())
    candidatos = (
        "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    )
    for executavel in candidatos:
        try:
            return subprocess.Popen(
                [
                    executavel,
                    f"--remote-debugging-port={porta}",
                    f"--user-data-dir={caminho_perfil}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            continue
    return None
