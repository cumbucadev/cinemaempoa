from flask_backend.models import Movie


def create_movies(db_session):
    movies = [
        Movie(title="Lobo e Cão", slug="lobo-e-cao"),
        Movie(title="Terra de Deus", slug="terra-de-deus"),
        Movie(title="MARINHEIRO DAS MONTANHAS", slug="marinheiro-das-montanhas"),
        Movie(title="NARDJES A.", slug="nardjes-a"),
        Movie(title="ELIS & TOM – SÓ TINHA DE SER COM VOCÊ", slug="elis-tom-so-havia-de-ser-com-voce"),
        Movie(title="A CASA DOS PRAZERES", slug="a-casa-dos-prazeres"),
        Movie(title="OLDBOY", slug="oldboy"),
        Movie(title="NOSSO SONHO", slug="nosso-sonho"),
    ]
    db_session.add_all(movies)
    db_session.commit()
