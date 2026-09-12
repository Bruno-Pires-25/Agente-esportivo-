import unittest

from agente_esportivo.aovivo import DURACAO, Estado, reprecifica
from agente_esportivo.modelos import CASA, EMPATE, FORA
from agente_esportivo.previsao import Agente

from .apoio import liga_sintetica


class TestEstado(unittest.TestCase):
    def test_minutos_restantes(self):
        self.assertEqual(Estado("A", "B", minuto=0).minutos_restantes, DURACAO)
        self.assertEqual(Estado("A", "B", minuto=70).minutos_restantes, 20)
        self.assertEqual(Estado("A", "B", minuto=90, acrescimos=4).minutos_restantes, 4)

    def test_nao_fica_negativo(self):
        self.assertEqual(Estado("A", "B", minuto=120).minutos_restantes, 0)
        self.assertTrue(Estado("A", "B", minuto=120).encerrado)

    def test_placar_formatado(self):
        self.assertEqual(Estado("A", "B", 2, 1, 60).placar, "2-1")

    def test_entradas_invalidas(self):
        with self.assertRaises(ValueError):
            Estado("A", "B", minuto=-1)
        with self.assertRaises(ValueError):
            Estado("A", "B", gols_mandante=-1)


class TestRepreciamento(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.partidas, _ = liga_sintetica(times=10, turnos=2, semente=53)
        cls.agente = Agente(cls.partidas)

    def reprecifica(self, **kwargs):
        return reprecifica(self.agente, Estado("Time A", "Time B", **kwargs))

    def test_probabilidades_somam_um(self):
        for kwargs in ({}, {"minuto": 45}, {"gols_mandante": 2, "minuto": 80}):
            analise = self.reprecifica(**kwargs)
            self.assertAlmostEqual(sum(analise.probabilidades.values()), 1.0, places=9)

    def test_no_minuto_zero_bate_com_o_poisson_pre_jogo(self):
        analise = self.reprecifica()
        do_modelo = self.agente.poisson.probabilidades("Time A", "Time B")
        # o pre-jogo do Poisson tem a correcao de Dixon-Coles; ao vivo nao,
        # entao a diferenca existe mas e pequena
        for chave in (CASA, EMPATE, FORA):
            self.assertAlmostEqual(analise.probabilidades[chave], do_modelo[chave], places=1)

    def test_gol_do_mandante_aumenta_a_chance_dele(self):
        antes = self.reprecifica(minuto=60).probabilidades[CASA]
        depois = self.reprecifica(gols_mandante=1, minuto=60).probabilidades[CASA]
        self.assertGreater(depois, antes)

    def test_tempo_passando_congela_o_placar(self):
        cedo = self.reprecifica(gols_mandante=1, minuto=20).probabilidades[CASA]
        tarde = self.reprecifica(gols_mandante=1, minuto=85).probabilidades[CASA]
        self.assertGreater(tarde, cedo)

    def test_jogo_encerrado_e_deterministico(self):
        analise = self.reprecifica(gols_mandante=2, gols_visitante=1, minuto=95)
        self.assertAlmostEqual(analise.probabilidades[CASA], 1.0, places=6)
        self.assertAlmostEqual(analise.probabilidades[FORA], 0.0, places=6)
        self.assertAlmostEqual(analise.mercados["over25"], 1.0, places=6)
        self.assertAlmostEqual(analise.mercados["btts_sim"], 1.0, places=6)

    def test_empate_no_fim_do_jogo(self):
        analise = self.reprecifica(gols_mandante=1, gols_visitante=1, minuto=95)
        self.assertAlmostEqual(analise.probabilidades[EMPATE], 1.0, places=6)

    def test_gols_restantes_caem_com_o_tempo(self):
        cedo = sum(self.reprecifica(minuto=10).gols_restantes)
        tarde = sum(self.reprecifica(minuto=80).gols_restantes)
        self.assertGreater(cedo, tarde)
        self.assertAlmostEqual(sum(self.reprecifica(minuto=95).gols_restantes), 0.0)

    def test_mercados_incluem_gols_ja_marcados(self):
        """Com 3-0 aos 50', 'mais de 2,5' ja esta ganho."""
        analise = self.reprecifica(gols_mandante=3, minuto=50)
        self.assertAlmostEqual(analise.mercados["over25"], 1.0, places=6)
        self.assertAlmostEqual(analise.mercados["btts_nao"], 1.0 - analise.mercados["btts_sim"], places=9)

    def test_ambas_marcam_depende_de_quem_ja_marcou(self):
        """Se o mandante ja marcou, so falta o visitante - fica mais provavel."""
        ninguem = self.reprecifica(minuto=60).mercados["btts_sim"]
        um_lado = self.reprecifica(gols_mandante=1, minuto=60).mercados["btts_sim"]
        self.assertGreater(um_lado, ninguem)

    def test_movimento_contra_o_pre_jogo(self):
        analise = self.reprecifica(gols_mandante=1, minuto=70)
        self.assertGreater(analise.movimento[CASA], 0)
        self.assertLess(analise.movimento[FORA], 0)

    def test_efeito_placar_ajuda_quem_perde(self):
        sem = reprecifica(self.agente, Estado("Time A", "Time B", 1, 0, 60))
        com = reprecifica(self.agente, Estado("Time A", "Time B", 1, 0, 60), efeito_placar=0.25)
        self.assertGreater(com.gols_restantes[1], sem.gols_restantes[1])
        self.assertLess(com.gols_restantes[0], sem.gols_restantes[0])

    def test_placares_finais_incluem_o_atual(self):
        analise = self.reprecifica(gols_mandante=2, gols_visitante=1, minuto=88)
        self.assertEqual(analise.placares[0][0], "2-1")

    def test_consultas_de_selecao(self):
        analise = self.reprecifica(gols_mandante=1, minuto=70)
        self.assertAlmostEqual(analise.probabilidade("C"), analise.probabilidades[CASA], places=9)
        conjunta = analise.probabilidade_conjunta(["C", "over15"])
        self.assertLessEqual(conjunta, analise.probabilidade("C") + 1e-12)

    def test_favorito(self):
        self.assertEqual(self.reprecifica(gols_mandante=3, minuto=80).favorito, "Time A")

    def test_time_desconhecido(self):
        with self.assertRaises(KeyError):
            reprecifica(self.agente, Estado("Barcelona", "Time B", minuto=10))


if __name__ == "__main__":
    unittest.main()
