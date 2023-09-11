#!/usr/bin/env python

import argparse
import json
import os
import re
import shutil

from bs4 import BeautifulSoup
from datetime import datetime

from build import HtmlBuilder
from scrapers.capitolio import Capitolio
from scrapers.cinebancarios import CineBancarios
from scrapers.paulo_amorim import CinematecaPauloAmorim
from scrapers.sala_redencao import SalaRedencao
from utils import dump_utf8_json


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="cinemaempoa",
        description="Grab the schedule for Porto Alegre's finest features",
    )

    allowed_rooms = ["capitolio", "sala-redencao", "cinebancarios", "paulo-amorim"]

    parser.add_argument(
        "-b",
        "--build",
        help="Builds the newest scrapped json as docs/index.html - saves the old index file in YYYY-MM-DD.html format",
        action="store_true",
    )

    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "-r",
        "--rooms",
        nargs="+",
        help=f"Filter specific rooms. Available: {', '.join(allowed_rooms)}",
        required=False,
    )
    group.add_argument(
        "-f", "--file", help="JSON filepath to build index.html from", required=False
    )

    args = parser.parse_args()

    if not args.rooms and not args.file:
        parser.error("Define build input with either --rooms or --file")

    if args.rooms:
        if not all(room in allowed_rooms for room in args.rooms):
            parser.error(
                f"Invalid selected rooms. Available: {', '.join(allowed_rooms)}"
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
            features.append(cineBancarios.get_daily_features_json())
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

    if args.file:
        if not os.path.exists(args.file):
            parser.error(f"File {args.file} not found.")
        with open(args.file, "r") as json_file:
            features = json.load(json_file)

    json_string = dump_utf8_json(features)

    if args.build:
        html_builder = HtmlBuilder(json_string)
        page_html = html_builder.create_page_from_json()

        os.makedirs("docs", exist_ok=True)
        with open("docs/index.html", "r") as index:
            index_soup = BeautifulSoup(index, "html.parser")
        time_tag = index_soup.find("time")
        datetime_match = re.match("\d{4}-\d{2}-\d{1,2}", time_tag["datetime"])
        if not datetime_match:
            parser.error(
                "Please check that your index.html has a <time> tag with a valid YYYY-MM-DD datetime attribute"
            )

        shutil.move("docs/index.html", f"docs/{datetime_match[0]}.html")
        with open("docs/index.html", "w") as new_index:
            new_index.write(page_html)
    else:
        print(json_string)
