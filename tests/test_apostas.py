import unittest

from agente_esportivo.apostas import (
    Aposta,
    encontra_valor,
    kelly,
    margem,
    prob_implicita,
    remove_margem,
    resultado_de_aposta,
    valor_esperado,
)


class TestConversaoDeOdds(unittest.TestCase):
    def test_prob_implicita(self):
        self.assertAlmostEqual(prob_implicita(2.0), 0.5)
        self.assertAlmostEqual(prob_implicita(4.0), 0.25)

    def test_odd_invalida(self):
        with self.assertRaises(ValueError):
            prob_implicita(1.0)

    def test_margem(self):
        self.assertAlmostEqual(margem([2.0, 2.0]), 0.0, places=9)
        self.assertGreater(margem([1.90, 1.90]), 0.05)

    def test_remocao_de_margem_soma_um(self):
        odds = {"C": 2.10, "E": 3.40, "F": 3.60}
        for metodo in ("proporcional", "potencia", "shin"):
            probabilidades = remove_margem(odds, metodo=metodo)
            self.assertAlmostEqual(sum(probabilidades.values()), 1.0, places=6)

    def test_remocao_de_margem_reduz_probabilidade_bruta(self):
        odds = {"C": 2.10, "E": 3.40, "F": 3.60}
        probabilidades = remove_margem(odds)
        for mercado, odd in odds.items():
            self.assertLess(probabilidades[mercado], prob_implicita(odd))

    def test_grupos_sao_normalizados_separadamente(self):
        odds = {"C": 2.10, "E": 3.40, "F": 3.60, "over25": 1.85, "under25": 1.95}
        probabilidades = remove_margem(odds)
        self.assertAlmostEqual(
            sum(probabilidades[c] for c in ("C", "E", "F")), 1.0, places=6
        )
        self.assertAlmostEqual(
            probabilidades["over25"] + probabilidades["under25"], 1.0, places=6
        )

    def test_mercado_avulso_fica_com_a_probabilidade_bruta(self):
        probabilidades = remove_margem({"btts_sim": 2.00})
        self.assertAlmostEqual(probabilidades["btts_sim"], 0.5)

    def test_metodo_desconhecido(self):
        with self.assertRaises(ValueError):
            remove_margem({"C": 2.0, "E": 3.0, "F": 4.0}, metodo="chute")


class TestValorEKelly(unittest.TestCase):
    def test_valor_esperado(self):
        self.assertAlmostEqual(valor_esperado(0.5, 2.10), 0.05)
        self.assertAlmostEqual(valor_esperado(0.5, 2.00), 0.0)
        self.assertLess(valor_esperado(0.4, 2.00), 0.0)

    def test_kelly_sem_valor_e_zero(self):
        self.assertEqual(kelly(0.4, 2.0), 0.0)
        self.assertEqual(kelly(0.5, 2.0), 0.0)

    def test_kelly_conhecido(self):
        # p=0,6 em odd 2,0: fracao = (0,6*2 - 1)/1 = 0,2
        self.assertAlmostEqual(kelly(0.6, 2.0), 0.2)
        self.assertAlmostEqual(kelly(0.6, 2.0, fracao=0.25), 0.05)

    def test_kelly_cresce_com_a_vantagem(self):
        self.assertGreater(kelly(0.7, 2.0), kelly(0.6, 2.0))


class TestBuscaDeValor(unittest.TestCase):
    def setUp(self):
        self.odds = {"C": 2.10, "E": 3.40, "F": 3.60}

    def test_encontra_aposta_com_valor(self):
        achados = encontra_valor({"C": 0.55, "E": 0.25, "F": 0.20}, self.odds)
        self.assertEqual(achados[0].mercado, "C")
        self.assertGreater(achados[0].ev, 0.1)

    def test_ignora_mercado_sem_valor(self):
        self.assertEqual(encontra_valor({"C": 0.40, "E": 0.25, "F": 0.20}, self.odds), [])

    def test_respeita_ev_minimo(self):
        probabilidades = {"C": 0.50, "E": 0.25, "F": 0.20}
        self.assertTrue(encontra_valor(probabilidades, self.odds, ev_minimo=0.01))
        self.assertFalse(encontra_valor(probabilidades, self.odds, ev_minimo=0.20))

    def test_ordenado_por_ev(self):
        achados = encontra_valor(
            {"C": 0.55, "E": 0.32, "F": 0.20}, self.odds, ev_minimo=0.0
        )
        evs = [a.ev for a in achados]
        self.assertEqual(evs, sorted(evs, reverse=True))

    def test_stake_limitada(self):
        achados = encontra_valor(
            {"C": 0.95, "E": 0.03, "F": 0.02}, self.odds, banca=1000, stake_maxima=0.05
        )
        self.assertLessEqual(achados[0].kelly, 0.05)
        self.assertLessEqual(achados[0].stake, 50.0)

    def test_sem_odds_nao_ha_apostas(self):
        self.assertEqual(encontra_valor({"C": 0.9}, {}), [])

    def test_campos_derivados(self):
        aposta = encontra_valor({"C": 0.55, "E": 0.25, "F": 0.20}, self.odds)[0]
        self.assertAlmostEqual(aposta.odd_justa, 1 / 0.55, places=6)
        self.assertGreater(aposta.vantagem, 0)
        self.assertEqual(aposta.nome, "Vitoria do mandante")

    def test_resolucao_de_aposta(self):
        aposta = Aposta("C", 2.5, 0.5, 0.42, 0.25, 0.1)
        self.assertAlmostEqual(resultado_de_aposta(aposta, True), 1.5)
        self.assertAlmostEqual(resultado_de_aposta(aposta, False), -1.0)


if __name__ == "__main__":
    unittest.main()
