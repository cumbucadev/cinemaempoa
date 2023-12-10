import os

from scrapers.sala_redencao import SalaRedencao


class TestSalaRedencao:
    def test_get_events_blog_post_url(self):
        salaRedencao = SalaRedencao(date="2023-09-13")
        salaRedencao.dir = os.path.join("tests/files/files_sala-redencao/2023-09-13")
        salaRedencao._get_events_blog_post_url()
        assert salaRedencao.events == [
            "https://www.ufrgs.br/difusaocultural/sala-redencao-apresenta-programacao-de-cinema-japones/",
            "https://www.ufrgs.br/difusaocultural/programacao-da-sala-redencao-explora-vanguardas-no-cinema/",
            "https://www.ufrgs.br/difusaocultural/ciclo-cineciess-exibe-5-casas-na-sala-redencao/",
        ]

    def test_get_events_blog_post_html(self):
        salaRedencao = SalaRedencao(date="2023-09-13")
        salaRedencao.dir = os.path.join("tests/files/files_sala-redencao/2023-09-13")
        salaRedencao.events = [
            "https://www.ufrgs.br/difusaocultural/sala-redencao-apresenta-programacao-de-cinema-japones/",
            "https://www.ufrgs.br/difusaocultural/programacao-da-sala-redencao-explora-vanguardas-no-cinema/",
            "https://www.ufrgs.br/difusaocultural/ciclo-cineciess-exibe-5-casas-na-sala-redencao/",
        ]
