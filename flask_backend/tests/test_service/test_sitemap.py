from datetime import date

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.scripts.sitemap import sitemap


class TestSitemap:
    def test_prints_urls_for_movies_and_blog_posts(
        self, app, setup_cinemas, test_blog_post, capsys
    ):
        with app.app_context():
            movie = Movie(title="Filme no Sitemap", slug="filme-no-sitemap")
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

        sitemap()

        output = capsys.readouterr().out
        urls = output.strip().split("\n")

        assert any("/filme-no-sitemap" in url for url in urls)
        assert any(f"/{test_blog_post['slug']}" in url for url in urls)
        assert any(url.endswith("cinemaempoa.com.br/") for url in urls)

    def test_excludes_draft_only_movies_and_unpublished_posts(
        self, app, setup_cinemas, capsys
    ):
        with app.app_context():
            movie = Movie(title="Filme Rascunho", slug="filme-rascunho")
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=True,
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

        sitemap()

        output = capsys.readouterr().out
        assert "/filme-rascunho" not in output
