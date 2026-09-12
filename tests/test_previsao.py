import unittest
from datetime import date

from agente_esportivo.modelos import CASA, EMPATE, FORA, Confronto, Partida
from agente_esportivo.previsao import Agente, combina, divergencia

from .apoio import liga_sintetica, partidas_simples


class TestCombinacao(unittest.TestCase):
    def test_media_ponderada(self):
        elo = {CASA: 0.6, EMPATE: 0.2, FORA: 0.2}
        poisson = {CASA: 0.4, EMPATE: 0.3, FORA: 0.3}
        combinado = combina(elo, poisson, 0.5)
        self.assertAlmostEqual(combinado[CASA], 0.5)
        self.assertAlmostEqual(sum(combinado.values()), 1.0)

    def test_pesos_extremos(self):
        elo = {CASA: 0.6, EMPATE: 0.2, FORA: 0.2}
        poisson = {CASA: 0.4, EMPATE: 0.3, FORA: 0.3}
        self.assertAlmostEqual(combina(elo, poisson, 1.0)[CASA], 0.6)
        self.assertAlmostEqual(combina(elo, poisson, 0.0)[CASA], 0.4)

    def test_peso_invalido(self):
        with self.assertRaises(ValueError):
            combina({CASA: 1, EMPATE: 0, FORA: 0}, {CASA: 1, EMPATE: 0, FORA: 0}, 1.5)

    def test_divergencia(self):
        igual = {CASA: 0.5, EMPATE: 0.3, FORA: 0.2}
        self.assertAlmostEqual(divergencia(igual, igual), 0.0)
        self.assertGreater(divergencia(igual, {CASA: 0.2, EMPATE: 0.3, FORA: 0.5}), 0.2)


class TestAgente(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.partidas, cls.forcas = liga_sintetica(times=10, turnos=2, semente=5)
        cls.agente = Agente(cls.partidas)

    def test_precisa_de_partidas(self):
        with self.assertRaises(ValueError):
            Agente([])

    def test_probabilidades_validas(self):
        analise = self.agente.analisa("Time A", "Time B")
        self.assertAlmostEqual(sum(analise.probabilidades.values()), 1.0, places=9)
        self.assertTrue(all(0 < p < 1 for p in analise.probabilidades.values()))

    def test_favorito_bate_com_a_forca_real(self):
        forte = max(self.forcas, key=self.forcas.get)
        fraco = min(self.forcas, key=self.forcas.get)
        analise = self.agente.analisa(forte, fraco)
        self.assertEqual(analise.resultado_mais_provavel, CASA)
        self.assertGreater(analise.probabilidades[CASA], analise.probabilidades[FORA])

    def test_mando_importa(self):
        forte = max(self.forcas, key=self.forcas.get)
        fraco = min(self.forcas, key=self.forcas.get)
        em_casa = self.agente.analisa(forte, fraco).probabilidades[CASA]
        visitante = self.agente.analisa(fraco, forte).probabilidades[FORA]
        self.assertGreater(em_casa, visitante)

    def test_gols_esperados_coerentes(self):
        forte = max(self.forcas, key=self.forcas.get)
        fraco = min(self.forcas, key=self.forcas.get)
        lc, lf = self.agente.analisa(forte, fraco).gols_esperados
        self.assertGreater(lc, lf)

    def test_nome_de_time_tolerante(self):
        self.assertEqual(self.agente.valida_time("time a"), "Time A")
        self.assertEqual(self.agente.valida_time("Time A"), "Time A")

    def test_time_desconhecido_lista_opcoes(self):
        with self.assertRaises(KeyError) as contexto:
            self.agente.analisa("Barcelona", "Time A")
        self.assertIn("Time A", str(contexto.exception))

    def test_analise_com_odds_gera_apostas(self):
        confronto = Confronto("Time A", "Time B", odds={"C": 50.0, "E": 3.4, "F": 3.6})
        analise = self.agente.analisa(confronto, banca=100)
        self.assertTrue(analise.apostas)
        self.assertEqual(analise.apostas[0].mercado, "C")
        self.assertGreater(analise.apostas[0].stake, 0)

    def test_odd_ruim_nao_gera_aposta(self):
        confronto = Confronto("Time A", "Time B", odds={"C": 1.01, "E": 1.01, "F": 1.01})
        self.assertEqual(self.agente.analisa(confronto).apostas, [])

    def test_todas_probabilidades_inclui_mercados(self):
        tudo = self.agente.analisa("Time A", "Time B").todas_probabilidades()
        for chave in (CASA, EMPATE, FORA, "over25", "btts_sim", "1X"):
            self.assertIn(chave, tudo)

    def test_confianca_entre_zero_e_um(self):
        analise = self.agente.analisa("Time A", "Time B")
        self.assertGreaterEqual(analise.confianca, 0.0)
        self.assertLessEqual(analise.confianca, 1.0)
        self.assertIn(analise.nivel_confianca, ("alta", "media", "baixa"))

    def test_confianca_cai_com_amostra_pequena(self):
        muitos = self.agente.confianca(
            {CASA: 0.5, EMPATE: 0.3, FORA: 0.2}, {CASA: 0.5, EMPATE: 0.3, FORA: 0.2},
            {"A": 40, "B": 40},
        )
        poucos = self.agente.confianca(
            {CASA: 0.5, EMPATE: 0.3, FORA: 0.2}, {CASA: 0.5, EMPATE: 0.3, FORA: 0.2},
            {"A": 2, "B": 2},
        )
        self.assertGreater(muitos, poucos)

    def test_analisa_rodada(self):
        confrontos = [Confronto("Time A", "Time B"), Confronto("Time C", "Time D")]
        self.assertEqual(len(self.agente.analisa_rodada(confrontos)), 2)

    def test_ranking_ordenado_por_elo(self):
        ranking = self.agente.ranking()
        self.assertEqual([r[1] for r in ranking], sorted([r[1] for r in ranking], reverse=True))

    def test_visitante_obrigatorio(self):
        with self.assertRaises(ValueError):
            self.agente.analisa("Time A")


class TestAgenteMinimo(unittest.TestCase):
    """O agente tem que funcionar mesmo com pouquissimo historico."""

    def test_base_de_seis_jogos(self):
        agente = Agente(partidas_simples())
        analise = agente.analisa("Alfa", "Beta")
        self.assertAlmostEqual(sum(analise.probabilidades.values()), 1.0, places=9)
        self.assertLess(analise.confianca, 0.9)

    def test_uma_unica_partida(self):
        agente = Agente([Partida(date(2024, 5, 1), "A", "B", 1, 0)])
        self.assertAlmostEqual(
            sum(agente.analisa("A", "B").probabilidades.values()), 1.0, places=9
        )


if __name__ == "__main__":
    unittest.main()
