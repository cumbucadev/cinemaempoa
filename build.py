#!/usr/bin/env python

import hashlib
import json
import math
import os
from datetime import datetime
from io import BytesIO

import requests
from PIL import Image

from scrapers.imdb import IMDBScrapper


class HtmlBuilder:
    def __init__(self, json_string) -> None:
        self.json_data = json.loads(json_string)

    def _download_img_from_url(self, img_url):
        if img_url is None:
            return None, None
        file_extension = img_url.split(".")[-1]
        file_name = (
            hashlib.md5(img_url.encode("utf-8")).hexdigest() + "." + file_extension
        )
        file_path = os.path.join("images", file_name)
        docs_file_path = os.path.join("docs", file_path)
        os.makedirs("docs/images", exist_ok=True)
        if os.path.exists(docs_file_path):
            with open(docs_file_path, "rb") as f:
                return Image.open(f), file_path

        r = requests.get(img_url)
        with open(docs_file_path, "wb") as f:
            file_content = r.content
            f.write(file_content)
            return Image.open(BytesIO(file_content)), file_path

    def _generate_movie_grid(self, cinema):
        movies_list = ""
        for item in cinema["features"]:
            img = None
            if "poster" in item and item["poster"] != "":
                # attempt to download file locally
                img, file_path = self._download_img_from_url(item["poster"])
            else:
                imdb_scrapper = IMDBScrapper()
                poster_url = imdb_scrapper.get_image(item)
                img, file_path = self._download_img_from_url(poster_url)

            if img:
                width = img.width
                height = img.height

                imgDisplayWidth = 325
                minHeight = math.ceil(imgDisplayWidth / width * height)
                movies_list += f"<li class='mb-5' style='min-height: {minHeight}px;'>"
                movies_list += f"<img src=\"{file_path}\" width={imgDisplayWidth} loading=\"lazy\" alt=\"{item['title']}\" class='img fluid rounded float-sm-start mb-3 mb-sm-0'>"
            else:
                movies_list += "<li class='mb-5'>"

            movies_list += f"""
                    <h3>{item['title']}</h3>
                    <p>{item['general_info']}</p>
                    <p>{item['time']}</p>
            """
            if "director" in item and item["director"] is not False:
                movies_list += f"<p><strong>Direção</strong>: {item['director']}</p>"
            if "classification" in item and item["classification"] is not False:
                movies_list += f"<p>{item['classification']}</p>"
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
                    <h2 id="{cinema['slug']}">
                        {cinema['cinema']}
                    </h2>
                    <p>
                        <a href="{cinema['url']}">Visite o site</a> do cinema.
                    </p>
                    {warnings}
                </header>
                <main>
                    <ul class="list-unstyled">
                        {movies_list}
                    </ul>
                </main>
            </article>"""

        return html

    def _generate_html_structure(self, main_content, header_content):
        html = f"""
            <!DOCTYPE html>
            <html lang="pt-br" data-bs-theme="dark">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>CINEMA EM POA</title>
                <meta name="description" content="Filmes em cartaz nas salas CineBancários, Cinemateca Paulo Amorim, Cinemateca Capitólio e Sala Redenção de Porto Alegre." />
                <style>
                    img {{ max-width: 100%; object-fit: contain; margin-right: 15px; }}
                </style>
                <!-- Halfmoon CSS -->
                <link href="assets/halfmoon.min.css" rel="stylesheet">
            </head>
            <body>
                <header>
                    <nav class="navbar mb-5" style="background-color: var(--bs-content-bg); border-bottom: var(--bs-border-width) solid var(--bs-content-border-color);">
                        <div class="container-fluid">
                            <a class="navbar-brand" href="#">
                            <img id="logo-black" src="assets/cinema.png" alt="Logo" width="24" height="24" class="d-inline-block align-text-top">
                            <img id="logo-white" src="assets/cinema-white.png" alt="Logo" width="24" height="24" class="d-inline-block align-text-top">
                            Cinema em POA
                            </a>
                            <span class="navbar-text">
                            Filmes em cartaz <strong><time datetime="{datetime.now().strftime("%Y-%m-%d")}">{datetime.now().strftime("%d/%m/%Y")}</time></strong>
                            </span>
                        </div>
                    </nav>
                    <script>
                        const html = document.querySelector('html');
                        if (window.matchMedia('(prefers-color-scheme: dark)').matches) {{
                            html.setAttribute('data-bs-theme', 'dark')
                            document.getElementById('logo-black').remove()
                        }} else {{
                            html.setAttribute('data-bs-theme', 'light')
                            document.getElementById('logo-white').remove()
                        }}
                    </script>
                    <div class="container">
                        <p>Este site mostra os filmes em cartaz em algumas das diversas salas de cinema de Porto Alegre.</p>
                        <p>Mostrando filmes para <strong><time datetime="{datetime.now().strftime("%Y-%m-%d")}">{datetime.now().strftime("%d/%m/%Y")}</time></strong>.</p>
                        <aside>
                            <nav>
                                { "".join(header_content) }
                            </nav>
                        </aside>
                    </div>
                </header>
                <main class="container">
                    {"".join(main_content)}
                </main>
                <footer class="py-3 my-4">
                    <ul class="nav justify-content-center border-bottom pb-3 mb-3">
                    <li class="nav-item"><a href="https://github.com/guites/cinemaempoa" class="nav-link px-2 text-muted">código fonte</a></li>
                    <li class="nav-item"><a href="https://cinemaempoa.goatcounter.com/" class="nav-link px-2 text-muted">analytics</a></li>
                    </ul>
                    <p class="text-center text-muted">Feito com ♥ por Porto Alegre</p>
                </footer>
                <script data-goatcounter="https://cinemaempoa.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
            </body>
            </html>"""
        return html

    def create_page_from_json(self) -> str:
        movie_grids = []
        header_content = ["<aside><nav><ul>"]
        for cinema in self.json_data:
            movie_grid = self._generate_movie_grid(cinema)
            movie_grids.append(movie_grid)
            header_content.append(
                f"<li><a href='#{cinema['slug']}'>{cinema['cinema']}</a></li>"
            )
        header_content.append("</ul></nav></aside>")
        page_html = self._generate_html_structure(movie_grids, header_content)
        return page_html
