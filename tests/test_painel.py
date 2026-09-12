"""Testes do gerador do painel web.

O painel e uma pagina unica com os dados embutidos: se o gerador escrever um
JSON quebrado ou um id que nao existe no template, a pagina abre em silencio
mostrando tracos no lugar dos numeros. Estes testes pegam exatamente isso.
"""

from __future__ import annotations

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

from agente_esportivo.previsao import Agente

from .apoio import liga_sintetica

RAIZ = Path(__file__).resolve().parent.parent


def carrega_gerador():
    caminho = RAIZ / "ferramentas" / "gerar_painel.py"
    spec = importlib.util.spec_from_file_location("gerar_painel", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def base_temporaria() -> tuple[Path, list]:
    partidas, _ = liga_sintetica(times=10, turnos=2, semente=23)
    caminho = Path(tempfile.mkdtemp()) / "base.csv"
    linhas = ["data,mandante,visitante,gols_mandante,gols_visitante,competicao"]
    for p in partidas:
        linhas.append(
            f"{p.data.isoformat()},{p.mandante},{p.visitante},"
            f"{p.gols_mandante},{p.gols_visitante},Teste"
        )
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho, partidas


class TestMontaDados(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gerador = carrega_gerador()
        cls.base, cls.partidas = base_temporaria()
        cls.dados = cls.gerador.monta_dados(
            cls.base, None, com_backtest=False, aquecimento=100, fonte="Teste"
        )

    def test_todos_os_times_entram(self):
        self.assertEqual(len(self.dados["times"]), 10)

    def test_times_vem_ordenados_pela_classificacao(self):
        posicoes = [t["pos"] for t in self.dados["times"]]
        self.assertEqual(posicoes, list(range(1, 11)))
        pontos = [t["pts"] for t in self.dados["times"]]
        self.assertEqual(pontos, sorted(pontos, reverse=True))

    def test_parametros_batem_com_o_agente(self):
        """A pagina refaz a conta em JS - se os parametros divergirem, ela mente."""
        agente = Agente(self.partidas)
        modelo = self.dados["modelo"]
        self.assertAlmostEqual(modelo["mu"], agente.poisson.mu, places=4)
        self.assertAlmostEqual(modelo["mando"], agente.poisson.mando, places=4)
        self.assertEqual(modelo["peso_elo"], agente.peso_elo)
        self.assertEqual(modelo["elo_mando"], agente.elo.vantagem_mando)

    def test_forcas_por_time_batem_com_o_agente(self):
        agente = Agente(self.partidas)
        for time in self.dados["times"]:
            self.assertAlmostEqual(time["ataque"], agente.poisson.ataque[time["nome"]], places=3)
            self.assertAlmostEqual(time["defesa"], agente.poisson.defesa[time["nome"]], places=3)
            self.assertAlmostEqual(time["elo"], agente.elo.rating(time["nome"]), places=1)

    def test_sem_backtest_nao_inventa_numeros(self):
        self.assertNotIn("backtest", self.dados)

    def test_com_backtest_traz_metricas(self):
        dados = self.gerador.monta_dados(
            self.base, None, com_backtest=True, aquecimento=100, fonte="Teste"
        )
        backtest = dados["backtest"]
        self.assertGreater(backtest["n"], 0)
        self.assertGreater(backtest["rps"], 0)
        self.assertTrue(backtest["calibracao"])

    def test_temporada_inexistente_falha_claro(self):
        with self.assertRaises(SystemExit):
            self.gerador.monta_dados(
                self.base, 1998, com_backtest=False, aquecimento=100, fonte="Teste"
            )


class TestPaginaGerada(unittest.TestCase):
    """Valida o HTML pronto que vai para o navegador."""

    @classmethod
    def setUpClass(cls):
        cls.html = (RAIZ / "painel" / "painel.html").read_text(encoding="utf-8")

    def test_sem_marcador_de_template(self):
        self.assertNotIn("__DADOS__", self.html)

    def test_json_embutido_e_valido(self):
        bruto = re.search(r"const DADOS = (\{.*?\});\n/\* ===== fim dos dados", self.html, re.S)
        self.assertIsNotNone(bruto)
        dados = json.loads(bruto.group(1))
        self.assertIn("times", dados)
        self.assertIn("modelo", dados)

    def test_todo_id_consultado_existe_no_html(self):
        usados = set(re.findall(r"getElementById\('([^']+)'\)", self.html))
        definidos = set(re.findall(r'id="([^"]+)"', self.html))
        self.assertEqual(usados - definidos, set())

    def test_numeros_do_backtest_nao_estao_cravados(self):
        """Se estiverem no HTML, envelhecem calados quando a base for atualizada."""
        for cravado in ("0,2121", "1.246 partidas"):
            self.assertNotIn(cravado, self.html)

    def test_template_e_pagina_continuam_em_sincronia(self):
        modelo = (RAIZ / "painel" / "modelo.html").read_text(encoding="utf-8")
        self.assertIn("__DADOS__", modelo)
        # mesma estrutura dos dois lados: so o bloco de dados muda
        limpa = lambda t: re.sub(r"const DADOS = .*?;\n", "", t, flags=re.S)
        self.assertEqual(limpa(modelo), limpa(self.html))


if __name__ == "__main__":
    unittest.main()
