from flask_backend.models import Movie


def create_movies(db_session):
    movies = [
        Movie(title="Lobo e Cão"),
        Movie(title="Terra de Deus"),
        Movie(title="MARINHEIRO DAS MONTANHAS"),
        Movie(title="NARDJES A."),
        Movie(title="ELIS & TOM – SÓ TINHA DE SER COM VOCÊ"),
        Movie(title="A CASA DOS PRAZERES"),
        Movie(title="OLDBOY"),
        Movie(title="NOSSO SONHO"),
    ]
    db_session.add_all(movies)
    db_session.commit()
