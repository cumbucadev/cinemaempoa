# CINEMA EM POA

CINEMA EM POA é um portal agregador de filmes das casas de cinema de Porto Alegre.

Está rodando em <https://cinemaempoa.com.br>.

![Home page do site - b4252b9c824a4ba5d068e40144ea8d7d6c79a74f](README/b4252b9c824a4ba5d068e40144ea8d7d6c79a74f.png)

O conteúdo é agregado realizando _web scrapping_ em quatro diferentes sites:

- [CineBancários](http://cinebancarios.blogspot.com/?view=classic)
- [Cinemateca Paulo Amorim](https://www.cinematecapauloamorim.com.br)
- [Cinemateca Capitólio](http://www.capitolio.org.br)
- [Sala Redenção](https://www.ufrgs.br/difusaocultural/salaredencao/)

O projeto encoraja contribuições (veja [Contribuições](#contribuicoes)).

## Desenvolvimento

O projeto é composto de dois módulos: `scrapers/`, que contém a lógica para coleção de dados e `flask_backend/`, onde fica o código do portal.

Este projeto requer Python 3.10.x ou 3.11.x. Versões superiores não são suportadas no momento. Recomendamos utilizar a série 3.10 (por exemplo, 3.10.19).

O banco de dados utilizado é o [sqlite3](https://www.sqlite.org/).

### Instalando o projeto localmente

A instalação recomendada é usando um [ambiente virtual (venv)](https://docs.python.org/3/library/venv.html).

    python3 -m venv .venv
    source .venv/bin/activate
    pip3 install -r requirements.txt

### Instalando o projeto usando Docker

Você pode usar o arquivo `docker-compose.dev.yml` para iniciar um container com todas as dependências necessárias.

    docker compose -f docker-compose.dev.yml up -d

Ao utilizar o docker, os comandos mencionados na seção seguinte devem ser rodados de dentro do container.

    # utilize o `docker exec` para abrir um terminal dentro do container
    docker exec -it cinemaempoa_flask_dev bash

Antes de abrir um Pull Request, rode os comandos abaixo no seu terminal para validar e formatar o código:

```bash
ruff check --fix # roda o linter para código python
ruff format # roda o formatter para código python
djlint flask_backend/templates --lint --profile=jinja # roda o linter para os arquivos .html
djlint --reformat flask_backend/templates --format-css --format-js # roda o formatter para os arquivos .html
```

Opcionalmente, o [pre-commit](https://pre-commit.com/) pode automatizar a formatação do código quando você rodar um `git commit`.

Para utilizá-lo, instale com:

    pre-commit install

### Rodando o projeto

Para rodar o portal, você vai precisar de três comandos (todos rodados a partir da raíz do projeto):

    flask --app flask_backend init-db # inicializa as tabelas no banco de dados
    flask --app flask_backend seed-db # optional: popula o banco com dados iniciais
    flask --app flask_backend run --debug # inicia o projeto em modo desenvolvimento

Lembre-se de utilizar a flag `--host=0.0.0.0` caso esteja rodando o projeto através do docker de desenvolvimento (docker-compose.dev.yml).

O projeto vai rodar em <http://localhost:5000>.

**Nota para usuários macOS:** Se você estiver usando macOS e encontrar um erro 403 ao reiniciar a aplicação, a porta 5000 pode estar sendo usada pelo AirPlay Receiver. Nesse caso, use uma porta alternativa:

    flask --app flask_backend run --debug --port=5001

Se você rodou o comando para popular o banco de dados, vai ter um usuário admin criado com login: cinemaempoa e senha: 123123.

Você pode fazer login via <http://localhost:5000/auth/login>.

### Utilizando os scrappers

Os scrappers podem ser disparados através da interface web na URL <http://127.0.0.1:5000/screening/import>, clicando no botão "Fazer Scrapping dos cinemas selecionados".

Alternativamente, os scrappers também podem ser rodados via linha de comandos, com o script

    ./cinemaempoa.py -h

    usage: cinemaempoa [-h] [-b] [--deploy] [--date DATE] [-r ROOMS [ROOMS ...] | -j JSON]

    Grab the schedule for Porto Alegre's finest features

    options:
    -h, --help            show this help message and exit
    -b, --build           Builds scrapped json as an html file
    --deploy              Saves generated html at docs/index.html - saves the old index file in YYYY-MM-DD.html format
    --date DATE           Runs the scrapper as if the current date is the given YYYY-MM-DD value
    -r ROOMS [ROOMS ...], --rooms ROOMS [ROOMS ...]
                            Filter specific rooms. Available: capitolio, sala-redencao, cinebancarios, paulo-amorim
    -j JSON, --json JSON  JSON filepath to build index.html from

Para disparar os scrappers e conseguir os filmes em cartaz em formato json (que pode ser importado no portal), rode o comando com a flag `r`, listando as salas de cinema desejadas, e direcione a saída para um arquivo.

    ./cinemaempoa.py -r capitolio sala-redencao cinebancarios paulo-amorim > import.json

Você pode inspecionar o arquivo `import.json` resultante para entender melhor a estrutura de saída dos scrappers.

### Importando dados no portal

Caso você tenha rodado os scrappers via linha de comando, você vai precisar importar o arquivo .json resultante no portal.

Após logar, vá para a página <http://localhost:5000/screening/import>.

Lá, selecione o arquivo gerado na etapa anterior e clique em **Enviar**.

As sessões importadas vão estar disponíveis na home.

### Importando dados pela linha de comandos

Uma alternativa a importação via portal é utilizando a linha de comando.

Dentro do seu ambiente, rode o seguinte comando:

```
flask --app flask_backend import-json /caminho/ate/o/arquivo.json
```

### Testes automatizados

O projeto possui alguns (poucos) testes automatizados. Certifique-se de que eles estão atualizados e passando sempre que você fizer alguma modificação no código.

#### Testes do portal

Veja o [README dos testes](./flask_backend/tests/README.md) do portal.

#### Testes dos scrappers

Veja os testes em [./tests](./tests/).

<h2 id="contribuicoes">Contribuições</h2>

Veja nossos [issues](https://github.com/guites/cinemaempoa/issues) pra entender o que está sendo feito no projeto.

Implementações mais simples estão marcadas com [good first issue](https://github.com/guites/cinemaempoa/issues?q=is%3Aopen+is%3Aissue+label%3A%22good+first+issue%22).

## Deploy (produção)

Atualmente o projeto (em <https://cinemaempoa.com.br>) está hospedado em uma máquina virtual.

Os arquivos usados para o deployment são:

- .env (deve ser criado a partir do example.env).
- docker-compose.production.yml
- Dockerfile.prod

A cada novo merge no branch principal, o workflow em `.github/workflows/deploy-server.yml` faz o processo de atualização do servidor.

## Backups do banco de dados

Diariamente uma cópia do banco de dados é enviada para o google drive em <https://drive.google.com/drive/u/0/folders/1f9qFHb2Fxdg_EGg3Vq4W-leDaGed9kXk>.

O processo é automatizado pelo script `backup-db.sh` em um _cronjob_ na máquina virtual.

```
$ crontab -l
55 23 * * * cd /home/ubuntu/cinemaempoa && ./backup-db.sh
```
