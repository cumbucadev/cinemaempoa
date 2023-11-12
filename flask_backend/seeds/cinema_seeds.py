from flask_backend.models import Cinema


def create_cinemas(db_session):
    capitolio = Cinema(
        name="Cinemateca Capitólio",
        slug="capitolio",
        url="http://www.capitolio.org.br/",
    )
    sala_redencao = Cinema(
        name="Sala Redenção",
        slug="sala-redencao",
        url="https://www.ufrgs.br/difusaocultural/salaredencao/",
    )
    cinebancarios = Cinema(
        name="CineBancários",
        slug="cinebancarios",
        url="http://cinebancarios.blogspot.com/",
    )
    paulo_amorim = Cinema(
        name="Cinemateca Paulo Amorim",
        slug="paulo-amorim",
        url="https://www.cinematecapauloamorim.com.br/",
    )
    db_session.add_all([capitolio, sala_redencao, cinebancarios, paulo_amorim])
    db_session.commit()
