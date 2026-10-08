#!/usr/bin/env python
import argparse
import os
import sys
import traceback
from datetime import datetime

from scrapers.capitolio import Capitolio
from scrapers.cine_cinco import CineCinco
from scrapers.cinebancarios import CineBancarios
from scrapers.paulo_amorim import CinematecaPauloAmorim
from scrapers.sala_redencao import SalaRedencao
from utils import dump_utf8_json

# slug -> (url, cinema name, scraper class), in output order.
ROOMS = {
    "capitolio": ("http://www.capitolio.org.br", "Cinemateca Capitólio", Capitolio),
    "sala-redencao": (
        "https://www.ufrgs.br/difusaocultural/salaredencao/",
        "Sala Redenção",
        SalaRedencao,
    ),
    "cinebancarios": (
        "https://cinebancarios.blogspot.com",
        "CineBancários",
        CineBancarios,
    ),
    "paulo-amorim": (
        "https://www.cinematecapauloamorim.com.br",
        "Cinemateca Paulo Amorim",
        CinematecaPauloAmorim,
    ),
    "cine-cinco": (
        "https://www.pucrs.br/cultura/projetos/cine-cinco/",
        "Cine Cinco",
        CineCinco,
    ),
}


def scrape_room(slug):
    """Scrapes one room. A failing scraper must not take the other rooms of
    the same run down with it, so errors go to stderr and the room is still
    emitted with no features - import-json then records it as having
    scraped nothing, which `pipeline-health` flags."""
    url, name, scraper_class = ROOMS[slug]
    room = {"url": url, "cinema": name, "slug": slug}
    try:
        room["features"] = scraper_class().get_daily_features_json()
    except Exception:
        print(f"Erro ao extrair a sala {slug}:", file=sys.stderr)
        traceback.print_exc()
        room["features"] = []
    return room


def scrape_rooms(rooms):
    features = []
    for slug in ROOMS:
        if slug not in rooms:
            continue
        features.append(scrape_room(slug))
        if slug == "paulo-amorim":
            json_filename = os.path.join(
                "json", f"{datetime.now().strftime('%Y-%m-%d')}.json"
            )
            os.makedirs("json", exist_ok=True)

            with open(json_filename, "w") as json_file:
                json_file.write(dump_utf8_json(features))
    return features


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="cinemaempoa",
        description="Extrai os horários das salas de cinema de Porto Alegre em formato JSON utilizando webscrapping.",
    )

    allowed_rooms = list(ROOMS)

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
        parser.error(f"Sala de cinema inválida. Opções: {', '.join(allowed_rooms)}")

    print(dump_utf8_json(scrape_rooms(args.rooms)))
