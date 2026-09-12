import unittest

from agente_esportivo.backtest import _resolve, executa
from agente_esportivo.metricas import (
    Placar,
    brier,
    curva_de_calibracao,
    log_loss,
    referencia_base,
    rps,
)
from agente_esportivo.modelos import CASA, EMPATE, FORA, Partida

from .apoio import liga_sintetica, partidas_simples


class TestMetricas(unittest.TestCase):
    def test_log_loss_da_certeza(self):
        self.assertAlmostEqual(log_loss(1.0), 0.0)
        self.assertGreater(log_loss(0.1), log_loss(0.5))

    def test_log_loss_nao_estoura_com_zero(self):
        self.assertLess(log_loss(0.0), 40.0)

    def test_brier_perfeito_e_pessimo(self):
        self.assertAlmostEqual(brier({CASA: 1, EMPATE: 0, FORA: 0}, CASA), 0.0)
        self.assertAlmostEqual(brier({CASA: 0, EMPATE: 0, FORA: 1}, CASA), 2.0)

    def test_rps_respeita_a_ordem_dos_resultados(self):
        """Errar para o empate tem que custar menos do que errar para o outro lado."""
        probabilidades = {CASA: 0.6, EMPATE: 0.25, FORA: 0.15}
        self.assertLess(rps(probabilidades, CASA), rps(probabilidades, EMPATE))
        self.assertLess(rps(probabilidades, EMPATE), rps(probabilidades, FORA))

    def test_rps_perfeito(self):
        self.assertAlmostEqual(rps({CASA: 1, EMPATE: 0, FORA: 0}, CASA), 0.0)

    def test_placar_acumula(self):
        placar = Placar()
        placar.registra({CASA: 0.6, EMPATE: 0.25, FORA: 0.15}, CASA)
        placar.registra({CASA: 0.6, EMPATE: 0.25, FORA: 0.15}, FORA)
        self.assertEqual(placar.n, 2)
        self.assertAlmostEqual(placar.acuracia, 0.5)
        self.assertGreater(placar.log_loss, 0)

    def test_placar_vazio_nao_divide_por_zero(self):
        placar = Placar()
        self.assertEqual(placar.acuracia, 0.0)
        self.assertEqual(placar.rps, 0.0)
        self.assertEqual(placar.roi, 0.0)

    def test_registro_de_apostas(self):
        placar = Placar()
        placar.registra_aposta(1.0, 1.5, True)
        placar.registra_aposta(1.0, -1.0, False)
        self.assertEqual(placar.apostas, 2)
        self.assertAlmostEqual(placar.lucro, 0.5)
        self.assertAlmostEqual(placar.roi, 0.25)

    def test_referencia_base(self):
        base = referencia_base([CASA, CASA, EMPATE, FORA])
        self.assertAlmostEqual(base[CASA], 0.5)
        self.assertAlmostEqual(sum(base.values()), 1.0)

    def test_referencia_base_vazia(self):
        self.assertAlmostEqual(referencia_base([])[CASA], 1 / 3)

    def test_curva_de_calibracao(self):
        curva = curva_de_calibracao([(0.9, 1.0), (0.85, 1.0), (0.3, 0.0)], faixas=5)
        self.assertEqual(len(curva), 2)
        self.assertEqual(sum(faixa["n"] for faixa in curva), 3)


class TestResolucaoDeMercado(unittest.TestCase):
    def setUp(self):
        self.partida = partidas_simples()[0]  # Alfa 2 x 0 Beta

    def test_1x2(self):
        self.assertTrue(_resolve("C", self.partida))
        self.assertFalse(_resolve("E", self.partida))
        self.assertFalse(_resolve("F", self.partida))

    def test_dupla_chance(self):
        self.assertTrue(_resolve("1X", self.partida))
        self.assertFalse(_resolve("X2", self.partida))

    def test_gols(self):
        self.assertTrue(_resolve("over15", self.partida))
        self.assertFalse(_resolve("over25", self.partida))
        self.assertTrue(_resolve("under25", self.partida))

    def test_ambas_marcam(self):
        self.assertFalse(_resolve("btts_sim", self.partida))
        self.assertTrue(_resolve("btts_nao", self.partida))

    def test_mercado_desconhecido(self):
        self.assertIsNone(_resolve("escanteios_over9", self.partida))


class TestBacktest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.partidas, _ = liga_sintetica(times=10, turnos=2, semente=13)

    def test_precisa_de_partidas_alem_do_aquecimento(self):
        with self.assertRaises(ValueError):
            executa(self.partidas[:10], aquecimento=60)

    def test_avalia_todas_as_partidas_restantes(self):
        avaliacao = executa(self.partidas, aquecimento=100, refit_a_cada=20)
        self.assertEqual(avaliacao.avaliadas, len(self.partidas) - 100)
        self.assertEqual(avaliacao.modelo.n, avaliacao.base.n)

    def test_modelo_bate_a_referencia_da_liga(self):
        """Numa liga simulada com forcas fixas, o modelo tem que ganhar da base."""
        avaliacao = executa(self.partidas, aquecimento=90, refit_a_cada=10)
        self.assertLess(avaliacao.modelo.rps, avaliacao.base.rps)
        self.assertGreater(avaliacao.ganho_sobre_base, 0.0)

    def test_apostas_com_odds(self):
        odds = {
            indice: {"C": 3.0, "E": 3.4, "F": 3.0}
            for indice in range(100, len(self.partidas))
        }
        avaliacao = executa(
            self.partidas, aquecimento=100, refit_a_cada=20,
            odds_por_partida=odds, ev_minimo=0.05,
        )
        self.assertGreater(avaliacao.modelo.apostas, 0)
        self.assertEqual(avaliacao.mercado.n, avaliacao.avaliadas)

    def test_detalhes_opcionais(self):
        sem = executa(self.partidas, aquecimento=150, guarda_detalhes=False)
        self.assertEqual(sem.detalhes, [])
        com = executa(self.partidas, aquecimento=150, guarda_detalhes=True)
        self.assertEqual(len(com.detalhes), com.avaliadas)

    def test_refit_nao_muda_demais_o_resultado(self):
        """Reajustar a cada jogo ou a cada 10 tem que dar resultados parecidos."""
        frequente = executa(self.partidas, aquecimento=120, refit_a_cada=1)
        esparso = executa(self.partidas, aquecimento=120, refit_a_cada=10)
        self.assertAlmostEqual(frequente.modelo.rps, esparso.modelo.rps, places=2)


if __name__ == "__main__":
    unittest.main()
