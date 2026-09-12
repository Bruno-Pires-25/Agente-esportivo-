import unittest

from agente_esportivo.combinadas import (
    ErroDeCombinada,
    analisa_perna,
    avalia,
    margem_composta,
    sugere_combinadas,
)
from agente_esportivo.modelos import Confronto
from agente_esportivo.previsao import Agente

from .apoio import liga_sintetica


class TestLeituraDePerna(unittest.TestCase):
    def test_formato_completo(self):
        perna = analisa_perna("Palmeiras x Flamengo: over25 @1.85")
        self.assertEqual(perna.mandante, "Palmeiras")
        self.assertEqual(perna.visitante, "Flamengo")
        self.assertEqual(perna.selecao, "over25")
        self.assertEqual(perna.odd, 1.85)

    def test_sem_odd(self):
        self.assertIsNone(analisa_perna("Palmeiras x Flamengo: C").odd)

    def test_virgula_decimal_e_vs(self):
        perna = analisa_perna("Palmeiras vs Flamengo: btts_sim @2,05")
        self.assertEqual(perna.odd, 2.05)

    def test_formato_invalido_explica(self):
        with self.assertRaises(ErroDeCombinada) as contexto:
            analisa_perna("qualquer coisa")
        self.assertIn("Formato", str(contexto.exception))

    def test_odd_menor_que_um(self):
        with self.assertRaises(ErroDeCombinada):
            analisa_perna("A x B: C @0.80")


class TestAvaliacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.partidas, _ = liga_sintetica(times=10, turnos=2, semente=41)
        cls.agente = Agente(cls.partidas)

    def perna(self, texto):
        return analisa_perna(texto)

    def test_uma_perna_bate_com_a_analise_simples(self):
        combinada = avalia(self.agente, [self.perna("Time A x Time B: C @2.00")])
        do_modelo = self.agente.poisson.probabilidades("Time A", "Time B")["C"]
        self.assertAlmostEqual(combinada.conjunta, do_modelo, places=9)

    def test_mesmo_jogo_usa_conjunta_exata(self):
        """Nao pode ser o produto: as pernas do mesmo jogo sao correlacionadas."""
        combinada = avalia(self.agente, [
            self.perna("Time A x Time B: over25 @2.00"),
            self.perna("Time A x Time B: btts_sim @2.00"),
        ])
        self.assertNotAlmostEqual(combinada.conjunta, combinada.ingenua, places=3)
        self.assertGreater(combinada.correlacao, 1.0)
        self.assertTrue(combinada.mesmo_jogo)

    def test_jogos_diferentes_multiplicam(self):
        combinada = avalia(self.agente, [
            self.perna("Time A x Time B: C @2.00"),
            self.perna("Time C x Time D: C @2.00"),
        ])
        self.assertAlmostEqual(combinada.conjunta, combinada.ingenua, places=9)
        self.assertFalse(combinada.mesmo_jogo)

    def test_pernas_incompativeis_zeram(self):
        combinada = avalia(self.agente, [
            self.perna("Time A x Time B: C @2.00"),
            self.perna("Time A x Time B: F @3.00"),
        ])
        self.assertAlmostEqual(combinada.conjunta, 0.0)

    def test_odd_oferecida_e_o_produto_por_padrao(self):
        combinada = avalia(self.agente, [
            self.perna("Time A x Time B: C @2.00"),
            self.perna("Time C x Time D: C @3.00"),
        ])
        self.assertAlmostEqual(combinada.odd_oferecida, 6.0)
        self.assertTrue(combinada.preco_do_produto)

    def test_odd_total_substitui_o_produto(self):
        combinada = avalia(self.agente, [
            self.perna("Time A x Time B: over25 @2.00"),
            self.perna("Time A x Time B: btts_sim @2.00"),
        ], odd_total=2.75)
        self.assertEqual(combinada.odd_oferecida, 2.75)
        self.assertFalse(combinada.preco_do_produto)
        self.assertAlmostEqual(combinada.ev, combinada.conjunta * 2.75 - 1)

    def test_sem_odd_nao_ha_ev(self):
        combinada = avalia(self.agente, [self.perna("Time A x Time B: C")])
        self.assertIsNone(combinada.odd_oferecida)
        self.assertIsNone(combinada.ev)
        self.assertEqual(combinada.stake_kelly, 0.0)

    def test_mercado_fora_do_modelo(self):
        with self.assertRaises(ErroDeCombinada) as contexto:
            avalia(self.agente, [self.perna("Time A x Time B: escanteios_over9 @1.90")])
        self.assertIn("escanteios", str(contexto.exception).lower())

    def test_time_desconhecido(self):
        with self.assertRaises(ErroDeCombinada):
            avalia(self.agente, [self.perna("Barcelona x Time B: C @2.00")])

    def test_sem_pernas(self):
        with self.assertRaises(ErroDeCombinada):
            avalia(self.agente, [])

    def test_conjunta_cai_a_cada_perna(self):
        uma = avalia(self.agente, [self.perna("Time A x Time B: C")]).conjunta
        duas = avalia(self.agente, [
            self.perna("Time A x Time B: C"), self.perna("Time C x Time D: C")
        ]).conjunta
        self.assertLess(duas, uma)


class TestMargemComposta(unittest.TestCase):
    def test_uma_perna_e_a_propria_margem(self):
        self.assertAlmostEqual(margem_composta(0.06, 1), 0.06)

    def test_margem_cresce_com_as_pernas(self):
        valores = [margem_composta(0.06, n) for n in range(1, 6)]
        self.assertEqual(valores, sorted(valores))
        self.assertGreater(valores[-1], 0.33)  # 5 pernas a 6% passam de 33%

    def test_entradas_invalidas(self):
        with self.assertRaises(ValueError):
            margem_composta(-0.1, 2)
        with self.assertRaises(ValueError):
            margem_composta(0.06, 0)


class TestSugestoes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        partidas, _ = liga_sintetica(times=10, turnos=2, semente=43)
        cls.agente = Agente(partidas)
        cls.confrontos = [
            Confronto("Time A", "Time B"), Confronto("Time C", "Time D"),
            Confronto("Time E", "Time F"),
        ]

    def test_respeita_o_maximo(self):
        sugestoes = sugere_combinadas(self.agente, self.confrontos, maximo=4)
        self.assertLessEqual(len(sugestoes), 4)

    def test_ordenadas_pela_probabilidade(self):
        sugestoes = sugere_combinadas(self.agente, self.confrontos, maximo=6)
        valores = [c.conjunta for c in sugestoes]
        self.assertEqual(valores, sorted(valores, reverse=True))

    def test_nao_mistura_pernas_do_mesmo_jogo(self):
        for combinada in sugere_combinadas(self.agente, self.confrontos, maximo=8):
            jogos = [a.perna.jogo for a in combinada.pernas]
            self.assertEqual(len(set(jogos)), len(jogos))

    def test_corte_alto_nao_sugere_nada(self):
        self.assertEqual(sugere_combinadas(self.agente, self.confrontos, minimo_por_perna=0.999), [])

    def test_time_desconhecido_e_ignorado(self):
        confrontos = self.confrontos + [Confronto("Barcelona", "Real Madrid")]
        self.assertTrue(sugere_combinadas(self.agente, confrontos, maximo=3))


if __name__ == "__main__":
    unittest.main()
