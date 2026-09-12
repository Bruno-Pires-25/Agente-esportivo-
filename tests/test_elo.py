import unittest
from datetime import date

from agente_esportivo.elo import Elo, multiplicador_de_margem, treina
from agente_esportivo.modelos import CASA, EMPATE, FORA, Partida

from .apoio import liga_sintetica, partidas_simples


class TestElo(unittest.TestCase):
    def test_rating_inicial(self):
        modelo = Elo()
        self.assertEqual(modelo.rating("Time novo"), 1500.0)

    def test_vitoria_sobe_e_derrota_desce(self):
        modelo = Elo()
        modelo.atualiza(Partida(date(2024, 5, 1), "A", "B", 2, 0))
        self.assertGreater(modelo.rating("A"), 1500)
        self.assertLess(modelo.rating("B"), 1500)

    def test_elo_e_soma_zero(self):
        modelo = Elo()
        modelo.atualiza(Partida(date(2024, 5, 1), "A", "B", 3, 1))
        self.assertAlmostEqual(modelo.rating("A") + modelo.rating("B"), 3000.0)

    def test_goleada_move_mais_que_vitoria_magra(self):
        magra, goleada = Elo(), Elo()
        magra.atualiza(Partida(date(2024, 5, 1), "A", "B", 1, 0))
        goleada.atualiza(Partida(date(2024, 5, 1), "A", "B", 4, 0))
        self.assertGreater(goleada.rating("A"), magra.rating("A"))

    def test_multiplicador_de_margem(self):
        self.assertEqual(multiplicador_de_margem(0), 1.0)
        self.assertEqual(multiplicador_de_margem(1), 1.0)
        self.assertEqual(multiplicador_de_margem(-2), 1.5)
        self.assertGreater(multiplicador_de_margem(4), 1.5)

    def test_mando_favorece_o_mandante(self):
        modelo = Elo()
        self.assertGreater(modelo.score_esperado("A", "B"), 0.5)

    def test_probabilidades_somam_um(self):
        modelo = Elo()
        modelo.ratings.update({"Forte": 1800, "Fraco": 1300})
        for casa, fora in (("Forte", "Fraco"), ("Fraco", "Forte"), ("Forte", "Forte2")):
            probabilidades = modelo.probabilidades(casa, fora)
            self.assertAlmostEqual(sum(probabilidades.values()), 1.0, places=9)
            self.assertTrue(all(0 < p < 1 for p in probabilidades.values()))

    def test_time_melhor_tem_mais_chance(self):
        modelo = Elo()
        modelo.ratings.update({"Forte": 1800, "Fraco": 1300})
        probabilidades = modelo.probabilidades("Forte", "Fraco")
        self.assertGreater(probabilidades[CASA], probabilidades[FORA])
        self.assertGreater(probabilidades[CASA], 0.6)

    def test_empate_mais_provavel_em_jogo_equilibrado(self):
        modelo = Elo()
        modelo.ratings.update({"A": 1500, "B": 1500, "Forte": 1900})
        equilibrado = modelo.probabilidades("A", "B")[EMPATE]
        desigual = modelo.probabilidades("Forte", "B")[EMPATE]
        self.assertGreater(equilibrado, desigual)

    def test_regressao_para_a_media(self):
        modelo = Elo()
        modelo.ratings["A"] = 1700.0
        modelo.regride_para_media(0.5)
        self.assertAlmostEqual(modelo.ratings["A"], 1600.0)

    def test_ranking_recupera_a_ordem_real(self):
        partidas, forcas = liga_sintetica(times=8, turnos=2)
        modelo = treina(partidas)
        melhor_real = max(forcas, key=forcas.get)
        self.assertIn(melhor_real, [time for time, _ in modelo.ranking()[:3]])

    def test_copia_e_independente(self):
        modelo = treina(partidas_simples())
        clone = modelo.copia()
        clone.ratings["Alfa"] = 9999.0
        self.assertNotEqual(modelo.ratings["Alfa"], 9999.0)


if __name__ == "__main__":
    unittest.main()
