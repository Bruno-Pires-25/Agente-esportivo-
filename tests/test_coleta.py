import tempfile
import unittest
from pathlib import Path

from agente_esportivo.coleta.texto import (
    de_arquivo,
    extrai_confrontos,
    html_para_texto,
)

CONHECIDOS = ["Palmeiras", "Flamengo", "Atletico-MG", "Sao Paulo", "Vasco", "Fortaleza"]

# layout tipico: nomes em linhas separadas, tres odds abaixo
COPIADO_COLUNAS = """
Brasileirao Serie A
Hoje
19:00
Palmeiras
Flamengo
1.95
3.40
3.90
Mais de 2.5: 2.05
Menos de 2.5: 1.75
21:30
Atletico Mineiro
Sao Paulo
2.10
3.20
3.60
"""

# layout de casas que mostram o jogo em uma linha so
COPIADO_LINHA = """
Vasco x Fortaleza 2.30 3.10 3.30
Palmeiras vs Flamengo 1,95 3,40 3,90
"""


class TestExtracaoDeTexto(unittest.TestCase):
    def test_layout_em_colunas(self):
        confrontos = extrai_confrontos(COPIADO_COLUNAS, CONHECIDOS)
        self.assertEqual(len(confrontos), 2)
        primeiro = confrontos[0]
        self.assertEqual(primeiro.mandante, "Palmeiras")
        self.assertEqual(primeiro.visitante, "Flamengo")
        self.assertAlmostEqual(primeiro.odds["C"], 1.95)
        self.assertAlmostEqual(primeiro.odds["F"], 3.90)

    def test_mercados_extras(self):
        confronto = extrai_confrontos(COPIADO_COLUNAS, CONHECIDOS)[0]
        self.assertAlmostEqual(confronto.odds["over25"], 2.05)
        self.assertAlmostEqual(confronto.odds["under25"], 1.75)

    def test_nome_normalizado_contra_a_base(self):
        confronto = extrai_confrontos(COPIADO_COLUNAS, CONHECIDOS)[1]
        self.assertEqual(confronto.mandante, "Atletico-MG")

    def test_layout_em_uma_linha(self):
        confrontos = extrai_confrontos(COPIADO_LINHA, CONHECIDOS)
        rotulos = {c.rotulo for c in confrontos}
        self.assertIn("Vasco x Fortaleza", rotulos)

    def test_virgula_decimal(self):
        confrontos = extrai_confrontos("Vasco x Fortaleza 2,30 3,10 3,30", CONHECIDOS)
        self.assertAlmostEqual(confrontos[0].odds["C"], 2.30)

    def test_sem_duplicatas(self):
        confrontos = extrai_confrontos(COPIADO_COLUNAS + COPIADO_COLUNAS, CONHECIDOS)
        self.assertEqual(len(confrontos), 2)

    def test_modo_estrito_descarta_desconhecido(self):
        texto = "Barcelona\nReal Madrid\n2.10\n3.40\n3.20\n"
        self.assertEqual(extrai_confrontos(texto, CONHECIDOS, estrito=True), [])
        self.assertEqual(len(extrai_confrontos(texto, CONHECIDOS, estrito=False)), 1)

    def test_texto_sem_odds(self):
        self.assertEqual(extrai_confrontos("Nada de util aqui\nnem aqui", CONHECIDOS), [])

    def test_ignora_horario_e_rotulos(self):
        """Horarios e a palavra 'Empate' nao podem virar nome de time."""
        texto = "Empate\n20:00\nPalmeiras\nFlamengo\n1.95\n3.40\n3.90\n"
        confronto = extrai_confrontos(texto, CONHECIDOS)[0]
        self.assertEqual(confronto.mandante, "Palmeiras")

    def test_placar_nao_vira_odd(self):
        """'2-1' e placar, nao odd - nao pode ser lido como cotacao."""
        self.assertEqual(extrai_confrontos("Palmeiras\nFlamengo\n2-1\n1-0\n0-0\n"), [])


class TestHtml(unittest.TestCase):
    def test_remove_tags_e_scripts(self):
        html = (
            "<html><body><script>var x = 'Botafogo';</script>"
            "<div>Palmeiras</div><div>Flamengo</div>"
            "<span>1.95</span><span>3.40</span><span>3.90</span></body></html>"
        )
        texto = html_para_texto(html)
        self.assertNotIn("var x", texto)
        confrontos = extrai_confrontos(texto, CONHECIDOS)
        self.assertEqual(confrontos[0].rotulo, "Palmeiras x Flamengo")

    def test_de_arquivo_html(self):
        caminho = Path(tempfile.mkdtemp()) / "pagina.html"
        caminho.write_text(
            "<html><body><p>Palmeiras</p><p>Flamengo</p>"
            "<b>1.95</b><b>3.40</b><b>3.90</b></body></html>",
            encoding="utf-8",
        )
        self.assertEqual(len(de_arquivo(caminho, CONHECIDOS)), 1)

    def test_de_arquivo_txt(self):
        caminho = Path(tempfile.mkdtemp()) / "odds.txt"
        caminho.write_text(COPIADO_COLUNAS, encoding="utf-8")
        self.assertEqual(len(de_arquivo(caminho, CONHECIDOS)), 2)

    def test_arquivo_inexistente(self):
        with self.assertRaises(FileNotFoundError):
            de_arquivo("/nao/existe.txt")


class TestNavegador(unittest.TestCase):
    def test_exige_origem(self):
        from agente_esportivo.coleta.navegador import captura_texto

        with self.assertRaises(ValueError):
            captura_texto("https://exemplo.com")

    def test_instrucoes_mencionam_a_porta(self):
        from agente_esportivo.coleta.navegador import INSTRUCOES

        self.assertIn("9222", INSTRUCOES)


if __name__ == "__main__":
    unittest.main()
