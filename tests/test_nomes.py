import unittest

from agente_esportivo.nomes import canonico, normaliza, resolve, resolve_varios

CONHECIDOS = [
    "Atletico-MG", "Athletico-PR", "Flamengo", "Sao Paulo", "Bragantino",
    "Vasco", "Internacional", "Botafogo-RJ", "Gremio",
]


class TestNormalizacao(unittest.TestCase):
    def test_remove_acento_e_caixa(self):
        self.assertEqual(normaliza("São Paulo"), "sao paulo")
        self.assertEqual(normaliza("ATLÉTICO-MG"), "atletico mg")

    def test_apelido_vira_nome_canonico(self):
        self.assertEqual(canonico("Galo"), "Atletico-MG")
        self.assertEqual(canonico("Timao"), "Corinthians")

    def test_nome_desconhecido_passa_intacto(self):
        self.assertEqual(canonico("Clube Qualquer"), "Clube Qualquer")


class TestResolucao(unittest.TestCase):
    def test_igualdade_exata(self):
        self.assertEqual(resolve("Flamengo", CONHECIDOS), "Flamengo")

    def test_acento_e_caixa(self):
        self.assertEqual(resolve("São Paulo", CONHECIDOS), "Sao Paulo")
        self.assertEqual(resolve("FLAMENGO", CONHECIDOS), "Flamengo")

    def test_nome_longo_da_casa_de_apostas(self):
        self.assertEqual(resolve("Atlético Mineiro", CONHECIDOS), "Atletico-MG")
        self.assertEqual(resolve("Red Bull Bragantino", CONHECIDOS), "Bragantino")
        self.assertEqual(resolve("Vasco da Gama", CONHECIDOS), "Vasco")

    def test_apelido(self):
        self.assertEqual(resolve("Galo", CONHECIDOS), "Atletico-MG")

    def test_nao_confunde_atletico_com_athletico(self):
        """O erro mais caro dessa base: dois clubes quase homonimos."""
        self.assertEqual(resolve("Athletico Paranaense", CONHECIDOS), "Athletico-PR")
        self.assertEqual(resolve("Atletico Mineiro", CONHECIDOS), "Atletico-MG")

    def test_desconhecido_vira_none(self):
        self.assertIsNone(resolve("Manchester United", CONHECIDOS))

    def test_entrada_vazia(self):
        self.assertIsNone(resolve("", CONHECIDOS))
        self.assertIsNone(resolve("Flamengo", []))

    def test_resolve_varios(self):
        saida = resolve_varios(["Flamengo", "Inexistente"], CONHECIDOS)
        self.assertEqual(saida["Flamengo"], "Flamengo")
        self.assertIsNone(saida["Inexistente"])


if __name__ == "__main__":
    unittest.main()
