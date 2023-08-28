#!/usr/bin/env python

import json
import sys

from datetime import datetime


def generate_movie_grid(cinema):
    movies_list = ""
    for item in cinema["features"]:
        if "poster" in item and item["poster"] != "":
            movies_list += '<li style="min-height: 325px;">'
            movies_list += f"<img src=\"{item['poster']}\" width=225 loading=\"lazy\" alt=\"{item['title']}\">"
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
            <style>
                img {{ float: left; max-height: 325px; object-fit: contain; margin-right: 15px; }}
                ul {{ list-style: none; }}
                .cinema-url {{ font-weight: normal; font-size: 1rem; }}
            </style>
        </head>
        <body>
            <header>
                <h1>CINEMA EM POA</h1>
                <p>Este site mostra os filmes em cartaz em algumas das diversas salas de cinema de Porto Alegre.</p>
                <p>Mostrando filmes para <strong>{datetime.now().strftime("%d/%m/%Y")}</strong></p>
            </header>
            {"".join(content)}
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
