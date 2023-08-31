# CINEMA EM POA

This project scrapes a few movie theater websites and compiles the results into a webpage showing, each day, the movies on display.

Featured movie theaters:
- [CineBancários](http://cinebancarios.blogspot.com/?view=classic)
- [Cinemateca Paulo Amorim](https://www.cinematecapauloamorim.com.br)
- [Cinemateca Capitólio](http://www.capitolio.org.br)
- [Sala Redenção](https://www.ufrgs.br/difusaocultural/salaredencao/)

The resulting page is updated every day at <https://guites.github.io/cinemaempoa/>.

## Development

The project is composed of a main file, `cinemaempoa.py`.

The `scrapers` directory holds implementations that access each of the tracked websites, parses their html or xml and formats the values into a json string.

The cli program accepts a `--build` flag which prompts it into turning that json string into valid html and moving it into the docs/ directory, which can trigger deployment of the website when pushed to the `gh_pages` branch.

## Installation

This was developed on Python 3.10.9

    python3 -m venv .venv
    source .venv/bin/activate
    pip3 install -r requirements.txt

## Running the project

An example on how to trigger the scrapper and save the resulting JSON and HTML files is

    ./cinemaempoa.py -r capitolio sala-redencao cinebancarios paulo-amorim -b

You can then inspect the resulting json and open the html file on your browser ♥‿♥

