import unittest
from datetime import date

from agente_esportivo.modelos import CASA, EMPATE, FORA, Confronto, Partida, times_de


class TestPartida(unittest.TestCase):
    def setUp(self):
        self.partida = Partida(date(2024, 5, 1), "Palmeiras", "Flamengo", 2, 1)

    def test_resultado(self):
        self.assertEqual(self.partida.resultado, CASA)
        self.assertEqual(Partida(date(2024, 5, 1), "A", "B", 1, 1).resultado, EMPATE)
        self.assertEqual(Partida(date(2024, 5, 1), "A", "B", 0, 2).resultado, FORA)

    def test_agregados(self):
        self.assertEqual(self.partida.total_gols, 3)
        self.assertEqual(self.partida.saldo, 1)
        self.assertTrue(self.partida.ambos_marcaram)

    def test_consultas_por_time(self):
        self.assertEqual(self.partida.gols_de("Flamengo"), 1)
        self.assertEqual(self.partida.gols_contra("Flamengo"), 2)
        self.assertEqual(self.partida.adversario_de("Flamengo"), "Palmeiras")
        self.assertEqual(self.partida.pontos_de("Palmeiras"), 3)
        self.assertEqual(self.partida.pontos_de("Flamengo"), 0)

    def test_time_de_fora_do_jogo_da_erro(self):
        with self.assertRaises(KeyError):
            self.partida.gols_de("Santos")

    def test_placar_negativo_rejeitado(self):
        with self.assertRaises(ValueError):
            Partida(date(2024, 5, 1), "A", "B", -1, 0)

    def test_time_contra_si_mesmo_rejeitado(self):
        with self.assertRaises(ValueError):
            Partida(date(2024, 5, 1), "A", "A", 1, 0)


class TestConfronto(unittest.TestCase):
    def test_odds_invalida_rejeitada(self):
        with self.assertRaises(ValueError):
            Confronto("A", "B", odds={"C": 0.9})

    def test_rotulo_e_odds(self):
        confronto = Confronto("A", "B", odds={"C": 2.0})
        self.assertEqual(confronto.rotulo, "A x B")
        self.assertTrue(confronto.tem_odds)
        self.assertFalse(Confronto("A", "B").tem_odds)


class TestAuxiliares(unittest.TestCase):
    def test_times_de(self):
        partidas = [
            Partida(date(2024, 5, 1), "B", "A", 1, 0),
            Partida(date(2024, 5, 2), "C", "A", 0, 0),
        ]
        self.assertEqual(times_de(partidas), ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()
