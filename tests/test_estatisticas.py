"""Testes do modelo de contagens (escanteios, chutes, cartoes)."""

import statistics
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from agente_esportivo.dados import ErroDeDados, le_estatisticas
from agente_esportivo.estatisticas import (
    ModeloContagem,
    RegistroEstatistica,
    ajusta_todos,
    binomial_negativa_pmf,
    valida,
)
from agente_esportivo.poisson import poisson_pmf


def registros_sinteticos(times=8, rodadas=12, semente=5, media=5.0):
    """Gera escanteios com forcas conhecidas e superdispersao real."""
    import random

    sorteio = random.Random(semente)
    nomes = [f"Time {chr(65 + i)}" for i in range(times)]
    forca = {n: 0.7 + 0.6 * i / (times - 1) for i, n in enumerate(nomes)}
    registros = []
    dia = date(2022, 1, 9)
    for _ in range(rodadas):
        sorteio.shuffle(nomes)
        for a in range(0, times, 2):
            casa, fora = nomes[a], nomes[a + 1]
            # gama-poisson = binomial negativa: a media varia de jogo para jogo
            mc = sorteio.gammavariate(8, media * forca[casa] / forca[fora] * 1.3 / 8)
            mf = sorteio.gammavariate(8, media * forca[fora] / forca[casa] / 8)
            registros.append(
                RegistroEstatistica(
                    data=dia, mandante=casa, visitante=fora,
                    valores={"escanteios": (_poisson(sorteio, mc), _poisson(sorteio, mf))},
                )
            )
            dia += timedelta(days=1)
    return registros, forca


def _poisson(sorteio, media):
    import math

    limite, k, produto = math.exp(-media), 0, 1.0
    while True:
        produto *= sorteio.random()
        if produto <= limite:
            return k
        k += 1


class TestDistribuicao(unittest.TestCase):
    def test_soma_um(self):
        total = sum(binomial_negativa_pmf(x, 5.0, 8.0) for x in range(200))
        self.assertAlmostEqual(total, 1.0, places=8)

    def test_k_infinito_vira_poisson(self):
        for x in range(8):
            self.assertAlmostEqual(
                binomial_negativa_pmf(x, 4.0, float("inf")), poisson_pmf(x, 4.0), places=9
            )

    def test_cauda_mais_gorda_que_poisson(self):
        """E exatamente por isso que a Binomial Negativa esta aqui."""
        nb = sum(binomial_negativa_pmf(x, 5.0, 8.0) for x in range(15, 60))
        po = sum(poisson_pmf(x, 5.0) for x in range(15, 60))
        self.assertGreater(nb, po * 2)

    def test_media_bate(self):
        media = sum(x * binomial_negativa_pmf(x, 5.0, 8.0) for x in range(200))
        self.assertAlmostEqual(media, 5.0, places=4)


class TestModeloContagem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registros, cls.forca = registros_sinteticos()
        cls.modelo = ModeloContagem("escanteios").ajusta(cls.registros)

    def test_mu_proximo_da_media_observada(self):
        valores = [v for r in self.registros for v in r.par("escanteios")]
        self.assertAlmostEqual(self.modelo.mu, statistics.mean(valores), delta=0.6)

    def test_mando_favorece_o_mandante(self):
        self.assertGreater(self.modelo.mando, 1.0)

    def test_detecta_superdispersao(self):
        self.assertTrue(self.modelo.superdisperso)
        self.assertGreater(self.modelo.razao_variancia, 1.0)

    def test_recupera_a_forca_real(self):
        melhor = max(self.forca, key=self.forca.get)
        topo = [t for t, _, _ in self.modelo.ranking()[:3]]
        self.assertIn(melhor, topo)

    def test_distribuicao_total_normalizada(self):
        distribuicao = self.modelo.distribuicao_total("Time A", "Time B")
        self.assertAlmostEqual(sum(distribuicao), 1.0, places=8)

    def test_over_decresce_com_a_linha(self):
        anterior = 1.0
        for linha in (7.5, 8.5, 9.5, 10.5, 11.5):
            atual = self.modelo.acima_de("Time A", "Time B", linha)
            self.assertLess(atual, anterior)
            anterior = atual

    def test_mercados_complementares(self):
        mercados = self.modelo.mercados("Time A", "Time B")
        self.assertAlmostEqual(mercados["over95"] + mercados["under95"], 1.0, places=9)
        self.assertAlmostEqual(
            mercados["esperado_total"],
            mercados["esperado_mandante"] + mercados["esperado_visitante"], places=9,
        )

    def test_time_desconhecido_vira_media(self):
        casa, fora = self.modelo.expectativa("Inexistente A", "Inexistente B")
        self.assertAlmostEqual(casa, self.modelo.mu * self.modelo.mando, places=6)

    def test_estatistica_ausente_da_erro_util(self):
        with self.assertRaises(ValueError) as contexto:
            ModeloContagem("posse_de_bola").ajusta(self.registros)
        self.assertIn("posse_de_bola", str(contexto.exception))

    def test_sem_validacao_nao_ha_sinal_conhecido(self):
        """Modelo nao medido nao ganha o beneficio da duvida."""
        self.assertFalse(self.modelo.tem_sinal_conhecido)

    def test_ajusta_todos_pula_o_que_falta(self):
        modelos = ajusta_todos(self.registros)
        self.assertIn("escanteios", modelos)
        self.assertNotIn("faltas", modelos)


class TestValidacao(unittest.TestCase):
    def test_amostra_pequena_recusa(self):
        registros, _ = registros_sinteticos(rodadas=2)
        with self.assertRaises(ValueError):
            valida(registros, "escanteios")

    def test_estatistica_inexistente(self):
        registros, _ = registros_sinteticos()
        with self.assertRaises(ValueError):
            valida(registros, "escanteios_fantasma")


class TestLeitura(unittest.TestCase):
    def escreve(self, conteudo: str) -> Path:
        caminho = Path(tempfile.mkdtemp()) / "stats.csv"
        caminho.write_text(conteudo, encoding="utf-8")
        return caminho

    def test_le_estatisticas(self):
        caminho = self.escreve(
            "data,mandante,visitante,escanteios_mandante,escanteios_visitante\n"
            "2023-05-01,Alfa,Beta,7,3\n"
        )
        registro = le_estatisticas(caminho)[0]
        self.assertEqual(registro.par("escanteios"), (7, 3))
        self.assertTrue(registro.tem("escanteios"))

    def test_coluna_vazia_nao_vira_zero(self):
        """'Nao coletado' e 'aconteceu zero vez' sao coisas diferentes."""
        caminho = self.escreve(
            "data,mandante,visitante,escanteios_mandante,escanteios_visitante,"
            "chutes_mandante,chutes_visitante\n"
            "2023-05-01,Alfa,Beta,7,3,,\n"
        )
        registro = le_estatisticas(caminho)[0]
        self.assertTrue(registro.tem("escanteios"))
        self.assertFalse(registro.tem("chutes"))

    def test_linha_sem_nenhuma_estatistica_e_descartada(self):
        caminho = self.escreve(
            "data,mandante,visitante,escanteios_mandante,escanteios_visitante\n"
            "2023-05-01,Alfa,Beta,7,3\n2023-05-08,Gama,Delta,,\n"
        )
        self.assertEqual(len(le_estatisticas(caminho)), 1)

    def test_arquivo_sem_nada_util(self):
        caminho = self.escreve(
            "data,mandante,visitante,escanteios_mandante,escanteios_visitante\n"
            "2023-05-01,Alfa,Beta,,\n"
        )
        with self.assertRaises(ErroDeDados):
            le_estatisticas(caminho)


class TestBaseReal(unittest.TestCase):
    """Fixa o que a base publica realmente tem - e o que ela nao tem."""

    @classmethod
    def setUpClass(cls):
        caminho = Path(__file__).resolve().parent.parent / "dados" / "estatisticas_2015_2023.csv"
        if not caminho.exists():
            raise unittest.SkipTest("base de estatisticas nao gerada")
        cls.registros = le_estatisticas(caminho)

    def test_periodo_coberto(self):
        anos = {r.data.year for r in self.registros}
        self.assertEqual(min(anos), 2015)
        self.assertEqual(max(anos), 2023)
        self.assertNotIn(2024, anos)  # a fonte parou de publicar estatisticas

    def test_chutes_no_alvo_so_de_2017(self):
        com_alvo = {r.data.year for r in self.registros if r.tem("chutes_no_alvo")}
        self.assertEqual(min(com_alvo), 2017)

    def test_escanteios_realistas(self):
        valores = [v for r in self.registros if r.tem("escanteios") for v in r.par("escanteios")]
        self.assertAlmostEqual(statistics.mean(valores), 5.2, delta=0.5)

    def test_escanteios_nao_batem_a_frequencia_historica(self):
        """Resultado medido, fixado para nao ser esquecido: escanteio nao tem sinal."""
        resultado = valida(self.registros, "escanteios")
        self.assertLess(resultado.ganho, 0.005)
        self.assertFalse(resultado.tem_sinal)

    def test_chutes_no_alvo_tem_algum_sinal(self):
        resultado = valida(self.registros, "chutes_no_alvo")
        self.assertGreater(resultado.ganho, 0.005)


if __name__ == "__main__":
    unittest.main()
