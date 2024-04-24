#!/usr/bin/env python
import argparse
import json
import os
import re
import shutil
from datetime import datetime

from bs4 import BeautifulSoup

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
        help="Builds scrapped json as an html file",
        action="store_true",
    )

    parser.add_argument(
        "--deploy",
        help="Saves generated html at docs/index.html - saves the old index file in YYYY-MM-DD.html format",
        action="store_true",
    )

    parser.add_argument(
        "--date",
        help="Runs the scrapper as if the current date is the given YYYY-MM-DD value",
        required=False,
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
        "-j", "--json", help="JSON filepath to build index.html from", required=False
    )

    args = parser.parse_args()

    if args.date and not args.rooms:
        parser.error("Define rooms to scrape when using a custom date")

    if not args.rooms and not args.json:
        parser.error("Define program input with either --rooms or --json")

    if args.deploy and not args.build:
        parser.error("You need --build in order to deploy")

    if args.rooms:
        if not all(room in allowed_rooms for room in args.rooms):
            parser.error(f"Invalid selected rooms. Available: {', '.join(allowed_rooms)}")

        scrape_date = args.date
        if scrape_date:
            if args.rooms != ["sala-redencao"]:
                parser.error("Only sala-redencao implements custom date scraping.")
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
            redencao = SalaRedencao(date=scrape_date)
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

    if args.json:
        if not os.path.exists(args.json):
            parser.error(f"File {args.json} not found.")
        with open(args.json, "r") as json_file:
            features = json.load(json_file)

    json_string = dump_utf8_json(features)

    page_html = None
    if args.build:
        html_builder = HtmlBuilder(json_string)
        page_html = html_builder.create_page_from_json()
        if not args.deploy:
            print(page_html)
    else:
        print(json_string)

    if args.deploy:
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
