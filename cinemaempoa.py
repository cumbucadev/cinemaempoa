#!/usr/bin/env python
import argparse
import os
from datetime import datetime

from scrapers.capitolio import Capitolio
from scrapers.cinebancarios import CineBancarios
from scrapers.paulo_amorim import CinematecaPauloAmorim
from scrapers.sala_redencao import SalaRedencao
from utils import dump_utf8_json

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="cinemaempoa",
        description="Extrai os horários das salas de cinema de Porto Alegre em formato JSON utilizando webscrapping.",
    )

    allowed_rooms = ["capitolio", "sala-redencao", "cinebancarios", "paulo-amorim"]

    parser.add_argument(
        "-r",
        "--rooms",
        nargs="+",
        help=f"Define as salas de cinemas para extração dos horários de exibição. Opções: {', '.join(allowed_rooms)}",
        required=True,
    )

    args = parser.parse_args()

    if not args.rooms:
        parser.error("Defina as salas de cinema desejadas com o argumento --rooms")

    if not all(room in allowed_rooms for room in args.rooms):
        parser.error(
            f"Sala de cinema inválida. Opções: {', '.join(allowed_rooms)}"
        )

    features = []
    if "capitolio" in args.rooms:
        feature = {
            "url": "http://www.capitolio.org.br",
            "cinema": "Cinemateca Capitólio",
            "slug": "capitolio",
        }
        cap = Capitolio()
        feature["features"] = cap.get_daily_features_json()
        features.append(feature)
    if "sala-redencao" in args.rooms:
        feature = {
            "url": "https://www.ufrgs.br/difusaocultural/salaredencao/",
            "cinema": "Sala Redenção",
            "slug": "sala-redencao",
        }
        redencao = SalaRedencao()
        feature["features"] = redencao.get_daily_features_json()
        features.append(feature)
    if "cinebancarios" in args.rooms:
        cineBancarios = CineBancarios()
        feature = {
            "url": "https://cinebancarios.blogspot.com",
            "cinema": "CineBancários",
            "slug": "cinebancarios",
        }
        feature["features"] = cineBancarios.get_daily_features_json()
        features.append(feature)
    if "paulo-amorim" in args.rooms:
        feature = {
            "url": "https://www.cinematecapauloamorim.com.br",
            "cinema": "Cinemateca Paulo Amorim",
            "slug": "paulo-amorim",
        }
        pauloAmorim = CinematecaPauloAmorim()
        feature["features"] = pauloAmorim.get_daily_features_json()
        features.append(feature)

        json_filename = os.path.join(
            "json", f"{datetime.now().strftime('%Y-%m-%d')}.json"
        )
        os.makedirs("json", exist_ok=True)

        with open(json_filename, "w") as json_file:
            json_file.write(dump_utf8_json(features))

    json_string = dump_utf8_json(features)

    print(json_string)
