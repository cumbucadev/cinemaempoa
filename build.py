#!/usr/bin/env python

import hashlib
import json
import requests
import math
import os
import sys

from datetime import datetime
from io import BytesIO
from PIL import Image


def generate_movie_grid(cinema):
    movies_list = ""
    for item in cinema["features"]:
        if "poster" in item and item["poster"] != "":
            # attempt to download file locally
            file_extension = item["poster"].split(".")[-1]
            file_name = (
                hashlib.md5(item["poster"].encode("utf-8")).hexdigest()
                + "."
                + file_extension
            )
            if os.path.exists(file_name):
                with open(file_name, "rb") as f:
                    img = Image.open(f)
            else:
                r = requests.get(item["poster"])
                with open(file_name, "wb") as f:
                    file_content = r.content
                    f.write(file_content)
                    img = Image.open(BytesIO(file_content))

            width = img.width
            height = img.height

            imgDisplayWidth = 325
            minHeight = math.ceil(imgDisplayWidth / width * height)
            movies_list += f"<li style='min-height: {minHeight}px;'>"
            movies_list += f"<img src=\"{file_name}\" width={imgDisplayWidth} loading=\"lazy\" alt=\"{item['title']}\">"
        else:
            movies_list += "<li>"
        movies_list += f"""
                <h3>{item['title']}</h3>
                <p>{item['general_info']}</p>
                <p>{item['time']}</p>
        """
        if "direction" in item and item["director"] is not False:
            movies_list += f"<p>{item['director']}</p>"

        movies_list += f"""
                <p>{item['excerpt']}</p>
                <a href="{item['read_more']}">Mais informações</a>
            </li>
        """
    warnings = ""
    if movies_list == "":
        warnings = "<strong style='color: red;'>Não há sessões hoje</strong><br/>"
    if "warning" in cinema and cinema["warning"]:
        warnings += f"<strong style='color: red;'>{cinema['warning']}</strong>"
    html = f"""
        <article>
            <header>
                <h2>
                    {cinema['cinema']}
                    <small class='cinema-url'>
                        <a href="{cinema['url']}">visitar</a>
                    </small>
                </h2>
                {warnings}
            </header>
            <main>
                <ul>
                    {movies_list}
                </ul>
            </main>
        </article>"""

    return html


def generate_html_structure(content):
    html = f"""
        <!DOCTYPE html>
        <html lang="pt-br">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>CINEMA EM POA</title>
            <meta name="description" content="Filmes em cartaz nas salas CineBancários, Cinemateca Paulo Amorim, Cinemateca Capitólio e Sala Redenção de Porto Alegre." />
            <style>
                body {{
                    max-width: 960px;
                }}
                img {{ float: left; max-width: 100%; object-fit: contain; margin-right: 15px; }}
                ul {{ list-style: none; }}
                li, p {{ font-size: 1.25rem; }}
                .cinema-url {{ font-weight: normal; font-size: 1rem; }}
            </style>
        </head>
        <body>
            <header>
                <h1>CINEMA EM POA</h1>
                <p>Este site mostra os filmes em cartaz em algumas das diversas salas de cinema de Porto Alegre.</p>
                <p>Mostrando filmes para <strong>{datetime.now().strftime("%d/%m/%Y")}</strong></p>
            </header>
            <main>
                {"".join(content)}
            </main>
            <footer>
                <p>Feito com ♥ por Porto Alegre | <a href="https://github.com/guites/cinemaempoa">Ver código fonte</a> | <a href="https://cinemaempoa.goatcounter.com/">Acessos: <span id="stats"></span></a></p>
            </footer>

            <script>
                var r = new XMLHttpRequest();
                r.addEventListener('load', function() {{
                    document.querySelector('#stats').innerText = JSON.parse(this.responseText).count
                }})
                r.open('GET', 'https://cinemaempoa.goatcounter.com/counter/' + encodeURIComponent(location.pathname.replace(/\/$/, '')) + '.json')
                r.send()
            </script>
            <script data-goatcounter="https://cinemaempoa.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
        </body>
        </html>"""
    return html


incoming_data = sys.stdin.read()
json_data = json.loads(incoming_data)


movie_grids = []
for cinema in json_data:
    movie_grid = generate_movie_grid(cinema)
    movie_grids.append(movie_grid)

page_html = generate_html_structure(movie_grids)
print(page_html)
