# CINEMA EM POA

CINEMA EM POA é um portal agregador de filmes das casas de cinema de Porto Alegre.

Está rodando em <https://cinemaempoa.com.br>.

O conteúdo é agregado realizando _web scrapping_ em quatro diferentes sites:

- [CineBancários](http://cinebancarios.blogspot.com/?view=classic)
- [Cinemateca Paulo Amorim](https://www.cinematecapauloamorim.com.br)
- [Cinemateca Capitólio](http://www.capitolio.org.br)
- [Sala Redenção](https://www.ufrgs.br/difusaocultural/salaredencao/)

## Desenvolvimento

O projeto é composto de dois módulos: `scrapers/`, que contém a lógica para
coleção de dados e `flask_backend/`, onde fica o código do portal.

Este projeto requer Python 3.10.x ou 3.11.x. Versões superiores não são suportadas
no momento. Recomendamos utilizar a série 3.10 (por exemplo, 3.10.19).

O banco de dados utilizado é o [sqlite3](https://www.sqlite.org/).

### Instalando o projeto localmente

A instalação é feita usando o [uv](https://docs.astral.sh/uv/), que instala as
dependências a partir do `uv.lock`.

    uv sync

### Configurando as variáveis de ambiente

Copie o arquivo `example.env` para `.env` e preencha os valores necessários:

    cp example.env .env

Algumas funcionalidades (posters, metadados de filmes) dependem de chaves de API de terceiros (`TMDB_API_TOKEN`, `IMGBB_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`). Elas só são necessárias se você for usar essas features específicas.

### Instalando o projeto usando Docker

Você pode usar o arquivo `docker-compose.dev.yml` para iniciar um container com
todas as dependências necessárias.

    docker compose -f docker-compose.dev.yml up -d

Ao utilizar o docker, os comandos mencionados nas seções seguintes devem ser
rodados de dentro do container.

    # utilize o `docker exec` para abrir um terminal dentro do container
    docker exec -it cinemaempoa_flask_dev bash

### Rodando o projeto

Para rodar o portal, você vai precisar de três comandos (todos rodados a partir da raíz do projeto):

    uv run flask --app flask_backend init-db # inicializa as tabelas no banco de dados
    uv run flask --app flask_backend seed-db # optional: popula o banco com dados iniciais
    uv run flask --app flask_backend run --debug # inicia o projeto em modo desenvolvimento

Lembre-se de utilizar a flag `--host=0.0.0.0` caso esteja rodando o projeto através do docker de desenvolvimento (docker-compose.dev.yml).

O projeto vai rodar em <http://localhost:5000>.

**Nota para usuários macOS:** Se você estiver usando macOS e encontrar um erro 403 ao reiniciar a aplicação, a porta 5000 pode estar sendo usada pelo AirPlay Receiver. Nesse caso, use uma porta alternativa:

    uv run flask --app flask_backend run --debug --port=5001

Se você rodou o comando para popular o banco de dados, vai ter um usuário admin criado com login: cinemaempoa e senha: 123123.

Você pode fazer login via <http://localhost:5000/auth/login>.

### Migrações do Banco de Dados

O projeto utiliza [Alembic](https://alembic.sqlalchemy.org/) para gerenciar
migrações do banco de dados. Isso permite que alterações no schema sejam
versionadas e aplicadas de forma controlada.

#### Comandos disponíveis

- `uv run flask --app flask_backend init-db` - Aplica todas as migrações pendentes
(inicializa ou atualiza o banco)
- `uv run flask --app flask_backend db-upgrade [revision]` - Aplica migrações até
uma revisão específica (padrão: head)
- `uv run flask --app flask_backend db-downgrade [revision]` - Reverte migrações até uma revisão específica
- `uv run flask --app flask_backend db-revision --autogenerate -m "mensagem"` - Cria uma nova migração automaticamente baseada nas mudanças nos modelos
- `uv run flask --app flask_backend db-current` - Mostra a revisão atual do banco de dados
- `uv run flask --app flask_backend db-history` - Mostra o histórico de migrações

#### Criando uma nova migração

Quando você modificar os modelos em `flask_backend/models.py`, crie uma nova migração:

    uv run flask --app flask_backend db-revision --autogenerate -m "Descrição da mudança"

### Lint e formatação

Antes de abrir um Pull Request, rode os comandos abaixo no seu terminal para validar e formatar o código:

```bash
uv run ruff check --fix # roda o linter para código python
uv run ruff format # roda o formatter para código python
uv run djlint flask_backend/templates --lint --profile=jinja # roda o linter para os arquivos .html
uv run djlint --reformat flask_backend/templates --format-css --format-js # roda o formatter para os arquivos .html
```

Opcionalmente, o [pre-commit](https://pre-commit.com/) pode automatizar a formatação do código quando você rodar um `git commit`.

Para utilizá-lo, instale com:

    pre-commit install


### Utilizando os scrappers

Os scrappers podem ser disparados através da interface web na URL <http://127.0.0.1:5000/screening/import>, clicando no botão "Fazer Scrapping dos cinemas selecionados".

Alternativamente, os scrappers também podem ser rodados via linha de comandos, com o script

    uv run ./cinemaempoa.py -h

    usage: cinemaempoa [-h] -r ROOMS [ROOMS ...]

    Extrai os horários das salas de cinema de Porto Alegre em formato JSON utilizando webscrapping.

    options:
    -h, --help            show this help message and exit
    -r ROOMS [ROOMS ...], --rooms ROOMS [ROOMS ...]
                            Define as salas de cinemas para extração dos horários de exibição. Opções: capitolio, sala-redencao, cinebancarios, paulo-amorim

Para disparar os scrappers e conseguir os filmes em cartaz em formato json (que pode ser importado no portal), rode o comando com a flag `r`, listando as salas de cinema desejadas, e direcione a saída para um arquivo.

    uv run ./cinemaempoa.py -r capitolio sala-redencao cinebancarios paulo-amorim > import.json

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
uv run flask --app flask_backend import-json /caminho/ate/o/arquivo.json
```

### Outros comandos úteis

Além dos comandos já citados, o projeto conta com outros comandos `flask`
para manutenção do catálogo.

Utilize `uv run flask --app flask_backend --help` para uma listagem completa dos
comandos disponíveis.

### Testes automatizados

O projeto possui testes automatizados. Certifique-se de que eles estão atualizados
e passando sempre que você fizer alguma modificação no código.

    uv run pytest

#### Testes do portal

Veja o [README dos testes](./flask_backend/tests/README.md) do portal.

#### Testes dos scrappers

Veja os testes em [./tests](./tests/).

## Contribuições

Veja o [guia de contribuição](./CONTRIBUTING.md) para o passo a passo completo
(fork, branch, PR) e o nosso [código de conduta](./CODE_OF_CONDUCT.md).

## Deploy (produção)

Atualmente o projeto (em <https://cinemaempoa.com.br>) está hospedado em uma máquina virtual.

Os arquivos usados para o deployment são:

- .env (deve ser criado a partir do example.env).
- docker-compose.production.yml
- Dockerfile.prod

A cada novo merge no branch principal, o workflow em `.github/workflows/deploy-server.yml`
faz o processo de atualização do servidor.

## Backups do banco de dados

Diariamente uma cópia do banco de dados é enviada para o google drive em <https://drive.google.com/drive/u/0/folders/1f9qFHb2Fxdg_EGg3Vq4W-leDaGed9kXk>.

O processo é automatizado pelo script `backup-db.sh` em um _cronjob_ na máquina virtual.

```
$ crontab -l
55 23 * * * cd /home/ubuntu/cinemaempoa && ./backup-db.sh
```

## Licença

Este projeto é distribuído sob a licença [GPLv3](./LICENSE).
