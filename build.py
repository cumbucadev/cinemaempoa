#!/usr/bin/env python

import json
import sys

from datetime import datetime


def generate_movie_grid(cinema):
    html = (
        "<div class='cinema'><h2>"
        + cinema["cinema"]
        + " <small><a href="
        + cinema["url"]
        + ">ver site</a></small></h2><ul>"
    )
    for item in cinema["features"]:
        if "poster" in item and item["poster"] != "":
            html += '<li style="min-height: 325px;">'
            html += f"<img src=\"{item['poster']}\" width=225 loading=\"lazy\" alt=\"{item['title']}\">"
        else:
            html += "<li>"
        html += f"""
                <h3>{item['title']}</h3>
                <p>{item['general_info']}</p>
                <p>{item['time']}</p>
        """
        if "direction" in item and item["director"] is not False:
            html += f"<p>{item['director']}</p>"

        html += f"""
                <p>{item['excerpt']}</p>
                <a href="{item['read_more']}">Read More</a>
            </li>
        """

    html += "</ul></div>"
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
            </style>
        </head>
        <body>
            <header>
                <h1>CINEMA EM POA</h1>
                <p>Este site mostra os filmes em cartaz em algumas das diversas salas de cinema de Porto Alegre.</p>
                <p>Mostrando filmes para <strong>{datetime.now().date()}</strong></p>
            </header>
            {"".join(content)}
        </body>
        </html>"""
    return html


incoming_data = sys.stdin.read()
json_data = json.loads(incoming_data)


movie_grids = []
for cinema in json_data:
    if len(cinema["features"]) == 0:
        continue
    movie_grid = generate_movie_grid(cinema)
    movie_grids.append(movie_grid)

page_html = generate_html_structure(movie_grids)
print(page_html)
