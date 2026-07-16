from flask_backend.db import db_session
from flask_backend.models import Movie
from flask_backend.scripts.title_cleaning_report import title_cleaning_report


class TestTitleCleaningReport:
    def test_reports_junk_suspects_and_cleaned_titles(self, app, capsys):
        with app.app_context():
            db_session.add_all(
                [
                    Movie(title="Cinema | Oldboy", slug="oldboy"),
                    Movie(title="O AGENTE SECRETO", slug="o-agente-secreto"),
                    Movie(title="Direção: Antonio Pitanga", slug="direcao-antonio"),
                ]
            )
            db_session.commit()

        title_cleaning_report()

        output = capsys.readouterr().out
        assert "Total de filmes analisados: 3" in output
        assert "Títulos que seriam alterados: 1" in output
        assert "Títulos suspeitos (revisão manual, não tratados): 1" in output
        assert '"Cinema | Oldboy" → "Oldboy"' in output
        assert "Direção: Antonio Pitanga" in output

    def test_reports_zero_when_nothing_to_clean(self, app, capsys):
        with app.app_context():
            db_session.add(Movie(title="Oldboy", slug="oldboy"))
            db_session.commit()

        title_cleaning_report()

        output = capsys.readouterr().out
        assert "Total de filmes analisados: 1" in output
        assert "Títulos que seriam alterados: 0" in output
        assert "Títulos suspeitos (revisão manual, não tratados): 0" in output
