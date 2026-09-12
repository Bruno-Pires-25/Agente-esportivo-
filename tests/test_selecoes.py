import unittest

from agente_esportivo.poisson import ModeloPoisson
from agente_esportivo.selecoes import (
    MercadoDesconhecido,
    nome,
    probabilidade,
    probabilidade_conjunta,
    satisfaz,
)

from .apoio import liga_sintetica


class TestPredicados(unittest.TestCase):
    def test_1x2(self):
        self.assertTrue(satisfaz("C", 2, 0))
        self.assertTrue(satisfaz("E", 1, 1))
        self.assertTrue(satisfaz("F", 0, 3))
        self.assertFalse(satisfaz("C", 1, 1))

    def test_dupla_chance(self):
        self.assertTrue(satisfaz("1X", 1, 1))
        self.assertTrue(satisfaz("1X", 2, 0))
        self.assertFalse(satisfaz("1X", 0, 1))
        self.assertFalse(satisfaz("12", 1, 1))

    def test_linhas_de_gols(self):
        self.assertTrue(satisfaz("over25", 2, 1))
        self.assertFalse(satisfaz("over25", 1, 1))
        self.assertTrue(satisfaz("under25", 1, 1))
        self.assertTrue(satisfaz("over05", 1, 0))
        self.assertTrue(satisfaz("under15", 1, 0))

    def test_ambas_marcam(self):
        self.assertTrue(satisfaz("btts_sim", 1, 1))
        self.assertFalse(satisfaz("btts_sim", 3, 0))
        self.assertTrue(satisfaz("btts_nao", 3, 0))

    def test_placar_exato(self):
        self.assertTrue(satisfaz("placar:2-1", 2, 1))
        self.assertFalse(satisfaz("placar:2-1", 1, 2))

    def test_sem_sofrer(self):
        self.assertTrue(satisfaz("mandante_sem_sofrer", 2, 0))
        self.assertTrue(satisfaz("mandante_vence_sem_sofrer", 2, 0))
        self.assertFalse(satisfaz("mandante_vence_sem_sofrer", 0, 0))

    def test_mercado_fora_do_modelo_explica(self):
        """Escanteio e chute nao estao no modelo - o erro precisa dizer isso."""
        for selecao in ("escanteios_over9", "chutes_no_gol_over4", "cartoes_over3"):
            with self.assertRaises(MercadoDesconhecido) as contexto:
                satisfaz(selecao, 1, 0)
            self.assertIn("nao tem", str(contexto.exception))

    def test_selecao_desconhecida_lista_opcoes(self):
        with self.assertRaises(MercadoDesconhecido) as contexto:
            satisfaz("qualquer_coisa", 1, 0)
        self.assertIn("over25", str(contexto.exception))

    def test_nomes_legiveis(self):
        self.assertEqual(nome("over25"), "Mais de 2,5 gols")
        self.assertEqual(nome("placar:2-1"), "Placar exato 2-1")
        self.assertEqual(nome("btts_sim"), "Ambas marcam")


class TestProbabilidades(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        partidas, _ = liga_sintetica(times=8, turnos=2, semente=31)
        cls.modelo = ModeloPoisson().ajusta(partidas)
        cls.matriz = cls.modelo.matriz("Time A", "Time B")

    def test_probabilidade_bate_com_o_modelo(self):
        do_modelo = self.modelo.probabilidades("Time A", "Time B")
        self.assertAlmostEqual(probabilidade(self.matriz, "C"), do_modelo["C"], places=9)

    def test_complementares_somam_um(self):
        self.assertAlmostEqual(
            probabilidade(self.matriz, "over25") + probabilidade(self.matriz, "under25"),
            1.0, places=9,
        )

    def test_conjunta_de_uma_selecao_e_ela_mesma(self):
        self.assertAlmostEqual(
            probabilidade_conjunta(self.matriz, ["over25"]),
            probabilidade(self.matriz, "over25"), places=12,
        )

    def test_conjunta_nunca_passa_da_menor_perna(self):
        conjunta = probabilidade_conjunta(self.matriz, ["C", "over25"])
        self.assertLessEqual(conjunta, probabilidade(self.matriz, "C") + 1e-12)
        self.assertLessEqual(conjunta, probabilidade(self.matriz, "over25") + 1e-12)

    def test_selecoes_incompativeis_dao_zero(self):
        """Vitoria do mandante e menos de 0,5 gol nao acontecem juntas."""
        self.assertAlmostEqual(probabilidade_conjunta(self.matriz, ["C", "under05"]), 0.0)

    def test_correlacao_positiva_entre_gols_e_ambas_marcam(self):
        """Mais gols e 'ambas marcam' andam juntos - multiplicar subestima."""
        conjunta = probabilidade_conjunta(self.matriz, ["over25", "btts_sim"])
        ingenua = probabilidade(self.matriz, "over25") * probabilidade(self.matriz, "btts_sim")
        self.assertGreater(conjunta, ingenua)

    def test_correlacao_negativa_entre_muitos_gols_e_zero_a_zero_de_um_lado(self):
        """Goleada e 'ambas nao marcam' brigam: multiplicar superestima em 3x."""
        conjunta = probabilidade_conjunta(self.matriz, ["over35", "btts_nao"])
        ingenua = probabilidade(self.matriz, "over35") * probabilidade(self.matriz, "btts_nao")
        self.assertLess(conjunta, ingenua * 0.5)

    def test_vitoria_com_poucos_gols_nao_e_negativamente_correlacionada(self):
        """Contraintuitivo e vale fixar: em jogo truncado, 1-0 do favorito domina,
        entao 'mandante vence' + 'menos de 1,5' se ajudam em vez de brigar."""
        conjunta = probabilidade_conjunta(self.matriz, ["C", "under15"])
        ingenua = probabilidade(self.matriz, "C") * probabilidade(self.matriz, "under15")
        self.assertGreater(conjunta, ingenua)

    def test_selecoes_vazias(self):
        with self.assertRaises(ValueError):
            probabilidade_conjunta(self.matriz, [])


if __name__ == "__main__":
    unittest.main()
