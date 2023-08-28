# CINEMA EM POA

This project scrapes a few movie theater websites and compiles the results into a webpage showing, each day, the movies on display.

Featured movie theaters:
- [CineBancários](http://cinebancarios.blogspot.com/?view=classic)
- [Cinemateca Paulo Amorim](https://www.cinematecapauloamorim.com.br) \(WIP\)
- [Cinemateca Capitólio](http://www.capitolio.org.br)
- [Sala Redenção](https://www.ufrgs.br/difusaocultural/salaredencao/)

The resulting page is updated every day at <https://guites.github.io/cinemaempoa/>.

## Development

The project is currently composed of two main files, `scrape.py` and `build.py`.

`scrape.py` implements the scrapping logic: accessing each website, parsing the html or xml and formatting the values into a json string.

`build.py` receives the json string from stdin and generates the HTML.

The generated files are then moved into the docs/ directory in the gh_pages repository, which deploys the website on every push.

## Installation

This was developed on Python 3.10.9

    python3 -m venv .venv
    source .venv/bin/activate
    pip3 install -r requirements.txt

Dependencies:

    - [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
    - [Requests](https://requests.readthedocs.io/en/latest/)

## Running the project

An example on how to trigger the scrapper and pipe the output to the buid script, while saving the resulting JSON and HTML files is

    TODAY=$(date +%F); ./scrape.py -r capitolio sala-redencao cinebancarios | tee "$TODAY.json" | ./build.py > "$TODAY.html"

You can then inspect the resulting json and open the html file on your browser ♥‿♥

