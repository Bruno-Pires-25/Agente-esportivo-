import unittest
from datetime import date, timedelta

from agente_esportivo.modelos import CASA, EMPATE, FORA, Partida
from agente_esportivo.poisson import (
    ModeloPoisson,
    dupla_chance,
    handicap_asiatico,
    mercados,
    placares_provaveis,
    poisson_pmf,
    tau_dixon_coles,
)

from .apoio import liga_sintetica


class TestDistribuicao(unittest.TestCase):
    def test_poisson_pmf_soma_um(self):
        total = sum(poisson_pmf(k, 1.5) for k in range(40))
        self.assertAlmostEqual(total, 1.0, places=9)

    def test_poisson_pmf_conhecido(self):
        self.assertAlmostEqual(poisson_pmf(0, 2.0), 0.1353352832, places=8)

    def test_tau_so_altera_placares_baixos(self):
        self.assertEqual(tau_dixon_coles(2, 2, 1.5, 1.2, -0.1), 1.0)
        self.assertNotEqual(tau_dixon_coles(0, 0, 1.5, 1.2, -0.1), 1.0)


class TestAjuste(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.partidas, cls.forcas = liga_sintetica(times=10, turnos=2, semente=11)
        cls.modelo = ModeloPoisson(meia_vida_dias=730).ajusta(cls.partidas)

    def test_ataque_medio_normalizado(self):
        media = sum(self.modelo.ataque.values()) / len(self.modelo.ataque)
        self.assertAlmostEqual(media, 1.0, places=6)

    def test_recupera_a_forca_real(self):
        """O time mais forte da simulacao tem que aparecer no topo do indice."""
        melhor_real = max(self.forcas, key=self.forcas.get)
        topo = [forca.time for forca in self.modelo.forcas()[:3]]
        self.assertIn(melhor_real, topo)

    def test_mando_positivo(self):
        self.assertGreater(self.modelo.mando, 1.0)

    def test_matriz_normalizada(self):
        matriz = self.modelo.matriz(*list(self.modelo.ataque)[:2])
        total = sum(sum(linha) for linha in matriz)
        self.assertAlmostEqual(total, 1.0, places=9)
        self.assertTrue(all(valor >= 0 for linha in matriz for valor in linha))

    def test_probabilidades_somam_um(self):
        casa, fora = list(self.modelo.ataque)[:2]
        probabilidades = self.modelo.probabilidades(casa, fora)
        self.assertAlmostEqual(sum(probabilidades.values()), 1.0, places=9)

    def test_time_desconhecido_vira_media_da_liga(self):
        lc, lf = self.modelo.expectativa("Time Inexistente", "Outro Inexistente")
        self.assertAlmostEqual(lc, self.modelo.mu * self.modelo.mando, places=6)
        self.assertAlmostEqual(lf, self.modelo.mu, places=6)

    def test_sem_partidas_da_erro(self):
        with self.assertRaises(ValueError):
            ModeloPoisson().ajusta([])

    def test_peso_decai_com_o_tempo(self):
        modelo = ModeloPoisson(meia_vida_dias=100)
        hoje = date(2024, 6, 1)
        partidas = [
            Partida(hoje - timedelta(days=200), "A", "B", 1, 0),
            Partida(hoje - timedelta(days=100), "A", "B", 1, 0),
            Partida(hoje, "A", "B", 1, 0),
        ]
        pesos = modelo.pesos(partidas, hoje)
        self.assertAlmostEqual(pesos[2], 1.0)
        self.assertAlmostEqual(pesos[1], 0.5, places=6)
        self.assertAlmostEqual(pesos[0], 0.25, places=6)
        self.assertLess(pesos[0], pesos[1])


class TestMercados(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        partidas, _ = liga_sintetica(times=8, turnos=2, semente=3)
        cls.modelo = ModeloPoisson().ajusta(partidas)
        cls.matriz = cls.modelo.matriz(*list(cls.modelo.ataque)[:2])

    def test_over_under_sao_complementares(self):
        saida = mercados(self.matriz)
        for limite in ("05", "15", "25", "35", "45"):
            self.assertAlmostEqual(
                saida[f"over{limite}"] + saida[f"under{limite}"], 1.0, places=9
            )

    def test_over_decresce_com_a_linha(self):
        saida = mercados(self.matriz)
        self.assertGreater(saida["over05"], saida["over15"])
        self.assertGreater(saida["over15"], saida["over25"])
        self.assertGreater(saida["over25"], saida["over35"])

    def test_ambas_marcam_complementar(self):
        saida = mercados(self.matriz)
        self.assertAlmostEqual(saida["btts_sim"] + saida["btts_nao"], 1.0, places=9)

    def test_gols_esperados_positivo(self):
        self.assertGreater(mercados(self.matriz)["gols_esperados"], 0.5)

    def test_dupla_chance_consistente(self):
        probabilidades = {CASA: 0.5, EMPATE: 0.3, FORA: 0.2}
        saida = dupla_chance(probabilidades)
        self.assertAlmostEqual(saida["1X"], 0.8)
        self.assertAlmostEqual(saida["12"], 0.7)
        self.assertAlmostEqual(saida["X2"], 0.5)

    def test_handicap_soma_um(self):
        for linha in (-1.5, -1.0, -0.5, 0.5, 1.0):
            saida = handicap_asiatico(self.matriz, linha)
            self.assertAlmostEqual(sum(saida.values()), 1.0, places=9)

    def test_handicap_de_meio_gol_nao_anula(self):
        self.assertAlmostEqual(handicap_asiatico(self.matriz, -0.5)["anulado"], 0.0)
        self.assertGreater(handicap_asiatico(self.matriz, -1.0)["anulado"], 0.0)

    def test_handicap_penaliza_o_favorecido(self):
        sem = handicap_asiatico(self.matriz, -0.5)["casa"]
        com = handicap_asiatico(self.matriz, -1.5)["casa"]
        self.assertGreater(sem, com)

    def test_placares_provaveis_ordenados(self):
        placares = placares_provaveis(self.matriz, 5)
        self.assertEqual(len(placares), 5)
        probabilidades = [p for _, p in placares]
        self.assertEqual(probabilidades, sorted(probabilidades, reverse=True))


if __name__ == "__main__":
    unittest.main()
