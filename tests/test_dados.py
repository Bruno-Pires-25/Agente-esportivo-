import tempfile
import unittest
from datetime import date
from pathlib import Path

from agente_esportivo.dados import (
    ErroDeDados,
    analisa_data,
    escreve_partidas,
    filtra,
    le_confrontos,
    le_partidas,
)


def escreve(conteudo: str, sufixo: str = ".csv") -> Path:
    arquivo = tempfile.NamedTemporaryFile("w", suffix=sufixo, delete=False, encoding="utf-8")
    arquivo.write(conteudo)
    arquivo.close()
    return Path(arquivo.name)


class TestLeituraDePartidas(unittest.TestCase):
    def test_cabecalho_em_portugues(self):
        caminho = escreve(
            "data,mandante,visitante,gols_mandante,gols_visitante\n"
            "2024-05-01,Palmeiras,Flamengo,2,1\n"
        )
        partidas = le_partidas(caminho)
        self.assertEqual(len(partidas), 1)
        self.assertEqual(partidas[0].mandante, "Palmeiras")
        self.assertEqual(partidas[0].gols_visitante, 1)

    def test_cabecalho_football_data(self):
        """O formato mais comum de base publica tem que funcionar sem conversao."""
        caminho = escreve(
            "Date,HomeTeam,AwayTeam,FTHG,FTAG,Div\n"
            "01/05/2024,Palmeiras,Flamengo,2,1,BRA\n"
        )
        partidas = le_partidas(caminho)
        self.assertEqual(partidas[0].data, date(2024, 5, 1))
        self.assertEqual(partidas[0].competicao, "BRA")

    def test_ordena_por_data(self):
        caminho = escreve(
            "data,mandante,visitante,gols_mandante,gols_visitante\n"
            "2024-06-01,C,D,0,0\n"
            "2024-05-01,A,B,1,0\n"
        )
        partidas = le_partidas(caminho)
        self.assertEqual([p.data.month for p in partidas], [5, 6])

    def test_jogo_sem_placar_e_ignorado(self):
        caminho = escreve(
            "data,mandante,visitante,gols_mandante,gols_visitante\n"
            "2024-05-01,A,B,1,0\n"
            "2024-05-08,C,D,,\n"
        )
        self.assertEqual(len(le_partidas(caminho)), 1)

    def test_coluna_faltando_aponta_o_problema(self):
        caminho = escreve("data,mandante,visitante\n2024-05-01,A,B\n")
        with self.assertRaises(ErroDeDados) as contexto:
            le_partidas(caminho)
        self.assertIn("gols_mandante", str(contexto.exception))

    def test_arquivo_inexistente(self):
        with self.assertRaises(ErroDeDados):
            le_partidas("/caminho/que/nao/existe.csv")

    def test_placar_invalido_aponta_a_linha(self):
        caminho = escreve(
            "data,mandante,visitante,gols_mandante,gols_visitante\n2024-05-01,A,B,x,0\n"
        )
        with self.assertRaises(ErroDeDados) as contexto:
            le_partidas(caminho)
        self.assertIn("linha 2", str(contexto.exception))


class TestLeituraDeConfrontos(unittest.TestCase):
    def test_le_odds(self):
        caminho = escreve(
            "mandante,visitante,odd_casa,odd_empate,odd_fora,odd_over25\n"
            "Palmeiras,Flamengo,2.10,3.40,3.60,1.85\n"
        )
        confronto = le_confrontos(caminho)[0]
        self.assertEqual(confronto.odds["C"], 2.10)
        self.assertEqual(confronto.odds["over25"], 1.85)

    def test_odds_vazias_ou_invalidas_sao_descartadas(self):
        caminho = escreve(
            "mandante,visitante,odd_casa,odd_empate,odd_fora\nA,B,,0.5,3.60\n"
        )
        confronto = le_confrontos(caminho)[0]
        self.assertNotIn("C", confronto.odds)
        self.assertNotIn("E", confronto.odds)
        self.assertEqual(confronto.odds["F"], 3.60)

    def test_odds_com_virgula_decimal(self):
        caminho = escreve("mandante,visitante,odd_casa\nA;B,C,\"2,10\"\n")
        confronto = le_confrontos(caminho)[0]
        self.assertEqual(confronto.odds["C"], 2.10)


class TestUtilidades(unittest.TestCase):
    def test_formatos_de_data(self):
        self.assertEqual(analisa_data("2024-05-01"), date(2024, 5, 1))
        self.assertEqual(analisa_data("01/05/2024"), date(2024, 5, 1))
        with self.assertRaises(ErroDeDados):
            analisa_data("primeiro de maio")

    def test_filtro_por_periodo_e_time(self):
        caminho = escreve(
            "data,mandante,visitante,gols_mandante,gols_visitante\n"
            "2023-05-01,A,B,1,0\n"
            "2024-05-01,B,C,2,2\n"
        )
        partidas = le_partidas(caminho)
        self.assertEqual(len(list(filtra(partidas, desde=date(2024, 1, 1)))), 1)
        self.assertEqual(len(list(filtra(partidas, time="B"))), 2)

    def test_ida_e_volta_do_arquivo(self):
        caminho = escreve(
            "data,mandante,visitante,gols_mandante,gols_visitante\n2024-05-01,A,B,3,1\n"
        )
        partidas = le_partidas(caminho)
        destino = Path(tempfile.mkdtemp()) / "saida.csv"
        escreve_partidas(destino, partidas)
        self.assertEqual(le_partidas(destino), partidas)


if __name__ == "__main__":
    unittest.main()
