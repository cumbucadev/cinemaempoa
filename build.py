#!/usr/bin/env python

import hashlib
import json
import requests
import math
import os

from datetime import datetime
from io import BytesIO
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
                movies_list += f"<li style='min-height: {minHeight}px;'>"
                movies_list += f"<img src=\"{file_path}\" width={imgDisplayWidth} loading=\"lazy\" alt=\"{item['title']}\">"
            else:
                movies_list += "<li>"

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

    def _generate_html_structure(self, main_content, header_content):
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
                        line-height: 1.5;
                    }}
                    img {{ float: left; max-width: 100%; object-fit: contain; margin-right: 15px; }}
                    ul {{ list-style: none; }}
                    li, p {{ font-size: 1.05rem; }}
                    .cinema-url {{ font-weight: normal; font-size: 1rem; }}
                </style>
            </head>
            <body>
                <header>
                    <h1>CINEMA EM POA</h1>
                    <p>Este site mostra os filmes em cartaz em algumas das diversas salas de cinema de Porto Alegre.</p>
                    <p>Mostrando filmes para <strong><time datetime="{datetime.now().strftime("%Y-%m-%d")}">{datetime.now().strftime("%d/%m/%Y")}</time></strong></p>
                    { "".join(header_content) }
                </header>
                <main>
                    {"".join(main_content)}
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
