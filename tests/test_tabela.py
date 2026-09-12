import unittest
from datetime import date

from agente_esportivo.modelos import Partida
from agente_esportivo.tabela import (
    classificacao,
    confrontos_diretos,
    forma,
    resumo_confrontos,
    vantagem_de_mando,
)

from .apoio import partidas_simples


class TestClassificacao(unittest.TestCase):
    def setUp(self):
        self.partidas = partidas_simples()

    def test_pontos_e_ordem(self):
        linhas = classificacao(self.partidas)
        self.assertEqual(linhas[0].time, "Alfa")
        self.assertEqual(linhas[0].pontos, 10)  # 3V, 1E
        self.assertEqual(linhas[0].jogos, 4)

    def test_saldo_e_gols(self):
        alfa = classificacao(self.partidas)[0]
        self.assertEqual(alfa.gols_pro, 8)
        self.assertEqual(alfa.gols_contra, 1)
        self.assertEqual(alfa.saldo, 7)

    def test_aproveitamento(self):
        alfa = classificacao(self.partidas)[0]
        self.assertAlmostEqual(alfa.aproveitamento, 10 / 12)

    def test_recorte_casa_e_fora(self):
        casa = {l.time: l for l in classificacao(self.partidas, mando="casa")}
        fora = {l.time: l for l in classificacao(self.partidas, mando="fora")}
        self.assertEqual(casa["Alfa"].jogos, 2)
        self.assertEqual(fora["Alfa"].jogos, 2)
        self.assertEqual(casa["Alfa"].vitorias, 1)

    def test_mando_invalido(self):
        with self.assertRaises(ValueError):
            classificacao(self.partidas, mando="neutro")

    def test_total_de_pontos_confere(self):
        """Cada jogo distribui 3 pontos (vitoria) ou 2 (empate)."""
        linhas = classificacao(self.partidas)
        esperado = sum(2 if p.resultado == "E" else 3 for p in self.partidas)
        self.assertEqual(sum(l.pontos for l in linhas), esperado)


class TestForma(unittest.TestCase):
    def setUp(self):
        self.partidas = partidas_simples()

    def test_sequencia_cronologica(self):
        resumo = forma(self.partidas, "Alfa", janela=4)
        self.assertEqual(resumo.sequencia, "VVEV")
        self.assertEqual(resumo.pontos, 10)

    def test_janela_limita(self):
        self.assertEqual(len(forma(self.partidas, "Alfa", janela=2).ultimas), 2)

    def test_invencibilidade(self):
        self.assertEqual(forma(self.partidas, "Alfa").invencibilidade, 4)

    def test_sem_vencer(self):
        resumo = forma(self.partidas, "Beta")
        self.assertGreaterEqual(resumo.sem_vencer, 1)

    def test_janela_invalida(self):
        with self.assertRaises(ValueError):
            forma(self.partidas, "Alfa", janela=0)


class TestConfrontosDiretos(unittest.TestCase):
    def test_historico_direto(self):
        partidas = partidas_simples()
        diretos = confrontos_diretos(partidas, "Alfa", "Beta")
        self.assertEqual(len(diretos), 2)

    def test_resumo(self):
        resumo = resumo_confrontos(partidas_simples(), "Alfa", "Beta")
        self.assertEqual(resumo["jogos"], 2)
        self.assertEqual(resumo["vitorias_a"], 2)
        self.assertEqual(resumo["gols_a"], 4)

    def test_resumo_e_espelhado(self):
        direto = resumo_confrontos(partidas_simples(), "Alfa", "Beta")
        inverso = resumo_confrontos(partidas_simples(), "Beta", "Alfa")
        self.assertEqual(direto["vitorias_a"], inverso["vitorias_b"])


class TestVantagemDeMando(unittest.TestCase):
    def test_proporcoes_somam_um(self):
        medida = vantagem_de_mando(partidas_simples())
        total = medida["vitorias_casa"] + medida["empates"] + medida["vitorias_fora"]
        self.assertAlmostEqual(total, 1.0)

    def test_lista_vazia(self):
        self.assertEqual(vantagem_de_mando([])["jogos"], 0)

    def test_mando_real_do_brasileirao(self):
        """Mandante vence mais que visitante - se isso quebrar, algo esta trocado."""
        partidas = [Partida(date(2024, 5, 1), "A", "B", 2, 0)] * 3 + [
            Partida(date(2024, 5, 2), "C", "D", 0, 1)
        ]
        medida = vantagem_de_mando(partidas)
        self.assertGreater(medida["vitorias_casa"], medida["vitorias_fora"])


if __name__ == "__main__":
    unittest.main()
