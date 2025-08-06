from flask_backend.import_json import ScrappedResult
from flask_backend.service.screening import import_scrapped_results
from scrapers.capitolio import Capitolio
from scrapers.cinebancarios import CineBancarios
from scrapers.paulo_amorim import CinematecaPauloAmorim
from scrapers.sala_redencao import SalaRedencao


class Runner:
    def __init__(self, cinemas=[]):
        features = []
        if "capitolio" in cinemas:
            feature = {
                "cls": Capitolio(),
                "url": "https://www.capitolio.org.br",
                "cinema": "Cinemateca Capitólio",
                "slug": "capitolio",
            }
            features.append(feature)

        if "redencao" in cinemas:
            feature = {
                "cls": SalaRedencao(),
                "url": "https://www.ufrgs.br/difusaocultural/salaredencao/",
                "cinema": "Sala Redenção",
                "slug": "sala-redencao",
            }
            features.append(feature)

        if "cinebancarios" in cinemas:
            feature = {
                "cls": CineBancarios(),
                "url": "http://cinebancarios.blogspot.com",
                "cinema": "CineBancários",
                "slug": "cinebancarios",
            }
            features.append(feature)

        if "pauloAmorim" in cinemas:
            feature = {
                "cls": CinematecaPauloAmorim(),
                "url": "https://www.cinematecapauloamorim.com.br",
                "cinema": "Cinemateca Paulo Amorim",
                "slug": "paulo-amorim",
            }
            features.append(feature)

        self.features = features

    def scrap(self):
        for cinema in self.features:
            cinema["features"] = cinema["cls"].get_daily_features_json()

    def parse_scrapped_json(self, features=None):
        self.scrapped_results: ScrappedResult = ScrappedResult.from_jsonable(
            self.features if features is None else features
        )

    def import_scrapped_results(self, current_app):
        return import_scrapped_results(self.scrapped_results, current_app)
