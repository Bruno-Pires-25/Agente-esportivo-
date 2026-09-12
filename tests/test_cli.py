import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agente_esportivo.cli import main

from .apoio import liga_sintetica


def base_temporaria() -> Path:
    """Grava uma liga sintetica em CSV para exercitar a CLI ponta a ponta."""
    partidas, _ = liga_sintetica(times=8, turnos=2, semente=17)
    caminho = Path(tempfile.mkdtemp()) / "base.csv"
    linhas = ["data,mandante,visitante,gols_mandante,gols_visitante,competicao"]
    for partida in partidas:
        linhas.append(
            f"{partida.data.isoformat()},{partida.mandante},{partida.visitante},"
            f"{partida.gols_mandante},{partida.gols_visitante},Teste"
        )
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


class TestCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = base_temporaria()

    def roda(self, *argumentos) -> tuple[int, str, str]:
        saida, erro = io.StringIO(), io.StringIO()
        with redirect_stdout(saida), redirect_stderr(erro):
            codigo = main(["--dados", str(self.base), *argumentos])
        return codigo, saida.getvalue(), erro.getvalue()

    def test_tabela(self):
        codigo, saida, _ = self.roda("tabela")
        self.assertEqual(codigo, 0)
        self.assertIn("Classificacao", saida)
        self.assertIn("Time A", saida)

    def test_tabela_por_mando(self):
        _, saida, _ = self.roda("tabela", "--mando", "casa")
        self.assertIn("mandante", saida)

    def test_tabela_json(self):
        _, saida, _ = self.roda("tabela", "--json")
        dados = json.loads(saida)
        self.assertEqual(dados[0]["posicao"], 1)
        self.assertIn("pontos", dados[0])

    def test_opcao_global_depois_do_subcomando(self):
        """'tabela --desde 2023' e como as pessoas digitam de verdade."""
        codigo, saida, _ = self.roda("tabela", "--desde", "2023")
        self.assertEqual(codigo, 0)
        self.assertIn("Classificacao", saida)

    def test_ranking(self):
        codigo, saida, _ = self.roda("ranking")
        self.assertEqual(codigo, 0)
        self.assertIn("Elo", saida)

    def test_times(self):
        _, saida, _ = self.roda("times")
        self.assertIn("Time A", saida)

    def test_dossie(self):
        codigo, saida, _ = self.roda("time", "Time A")
        self.assertEqual(codigo, 0)
        self.assertIn("Dossie", saida)
        self.assertIn("Desempenho por mando", saida)

    def test_prever(self):
        codigo, saida, _ = self.roda("prever", "Time A", "Time B")
        self.assertEqual(codigo, 0)
        self.assertIn("Gols esperados", saida)
        self.assertIn("Placares mais provaveis", saida)

    def test_prever_com_odds_mostra_valor(self):
        _, saida, _ = self.roda(
            "prever", "Time A", "Time B", "--odd-casa", "50", "--banca", "100"
        )
        self.assertIn("Apostas de valor", saida)

    def test_prever_json(self):
        _, saida, _ = self.roda("prever", "Time A", "Time B", "--json")
        dados = json.loads(saida)
        self.assertAlmostEqual(sum(dados["probabilidades"].values()), 1.0, places=6)

    def test_time_desconhecido_retorna_erro(self):
        codigo, _, erro = self.roda("prever", "Barcelona", "Time B")
        self.assertEqual(codigo, 1)
        self.assertIn("desconhecido", erro)

    def test_rodada(self):
        confrontos = Path(tempfile.mkdtemp()) / "rodada.csv"
        confrontos.write_text(
            "mandante,visitante,odd_casa,odd_empate,odd_fora\n"
            "Time A,Time B,2.10,3.40,3.60\n"
            "Time C,Time D,1.80,3.50,4.20\n",
            encoding="utf-8",
        )
        codigo, saida, _ = self.roda("rodada", "--arquivo", str(confrontos))
        self.assertEqual(codigo, 0)
        self.assertIn("Analise da rodada", saida)
        self.assertIn("Time A x Time B", saida)

    def test_odds_de_arquivo(self):
        odds = Path(tempfile.mkdtemp()) / "odds.txt"
        odds.write_text("Time A\nTime B\n1.95\n3.40\n3.90\n", encoding="utf-8")
        codigo, saida, _ = self.roda("odds", "--arquivo", str(odds))
        self.assertEqual(codigo, 0)
        self.assertIn("Time A x Time B", saida)

    def test_odds_salva_csv(self):
        odds = Path(tempfile.mkdtemp()) / "odds.txt"
        odds.write_text("Time A\nTime B\n1.95\n3.40\n3.90\n", encoding="utf-8")
        destino = Path(tempfile.mkdtemp()) / "coletadas.csv"
        self.roda("odds", "--arquivo", str(odds), "--salvar", str(destino))
        self.assertTrue(destino.exists())
        self.assertIn("odd_casa", destino.read_text(encoding="utf-8"))

    def test_odds_sem_origem_explica(self):
        codigo, _, erro = self.roda("odds")
        self.assertEqual(codigo, 2)
        self.assertIn("--arquivo", erro)

    def test_odds_instrucoes(self):
        codigo, saida, _ = self.roda("odds", "--instrucoes")
        self.assertEqual(codigo, 0)
        self.assertIn("9222", saida)

    def test_backtest(self):
        codigo, saida, _ = self.roda("backtest", "--aquecimento", "60", "--refit", "20")
        self.assertEqual(codigo, 0)
        self.assertIn("RPS", saida)

    def test_backtest_json(self):
        _, saida, _ = self.roda("backtest", "--aquecimento", "60", "--json")
        dados = json.loads(saida)
        self.assertIn("rps", dados["modelo"])

    def test_exportar(self):
        destino = Path(tempfile.mkdtemp()) / "export.csv"
        codigo, saida, _ = self.roda("exportar", "--saida", str(destino))
        self.assertEqual(codigo, 0)
        self.assertTrue(destino.exists())

    def test_base_inexistente_da_mensagem_util(self):
        saida, erro = io.StringIO(), io.StringIO()
        with redirect_stdout(saida), redirect_stderr(erro):
            codigo = main(["--dados", "/nao/existe.csv", "tabela"])
        self.assertEqual(codigo, 1)
        self.assertIn("nao encontrada", erro.getvalue())


if __name__ == "__main__":
    unittest.main()
