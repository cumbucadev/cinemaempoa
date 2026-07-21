import json
from unittest.mock import patch

from flask_backend.db import db_session
from flask_backend.models import PipelineRun, Screening
from flask_backend.service.movie_metadata_pipeline import (
    PipelineResult as MetadataPipelineResult,
)
from flask_backend.service.poster_pipeline import PipelineResult as PosterPipelineResult


class TestImportJsonCommand:
    def test_invalid_json_shows_error(self, runner, tmp_path):
        json_path = tmp_path / "bad.json"
        json_path.write_text("not-valid-json{")

        result = runner.invoke(args=["import-json", str(json_path)])
        assert "Arquivo .json inválido ou não encontrado" in result.output

    def test_invalid_structure_shows_error(self, runner, tmp_path):
        json_path = tmp_path / "bad-structure.json"
        json_path.write_text(json.dumps([{"foo": "bar"}]))

        result = runner.invoke(args=["import-json", str(json_path)])
        assert "estrutura inválida" in result.output

    def test_unknown_cinema_shows_error(self, runner, tmp_path, setup_cinemas):
        payload = [
            {
                "url": "",
                "cinema": "Inexistente",
                "slug": "inexistente",
                "features": [],
            }
        ]
        json_path = tmp_path / "unknown-cinema.json"
        json_path.write_text(json.dumps(payload))

        result = runner.invoke(args=["import-json", str(json_path)])
        assert "não encontrada" in result.output

    def test_success_imports_screenings(self, runner, tmp_path, setup_cinemas):
        payload = [
            {
                "url": "",
                "cinema": "Cinemateca Capitólio",
                "slug": "capitolio",
                "features": [
                    {
                        "poster": "",
                        "time": ["2026-08-01T19:00"],
                        "title": "Filme via CLI",
                        "original_title": "",
                        "price": "",
                        "director": "",
                        "classification": "",
                        "general_info": "",
                        "excerpt": "um filme",
                        "read_more": "",
                    }
                ],
            }
        ]
        json_path = tmp_path / "valid.json"
        json_path.write_text(json.dumps(payload))

        result = runner.invoke(args=["import-json", str(json_path)])
        assert "sessões criadas com sucesso" in result.output

    def test_success_creates_pipeline_run_with_source_and_summary(
        self, app, runner, tmp_path, setup_cinemas
    ):
        payload = [
            {
                "url": "",
                "cinema": "Cinemateca Capitólio",
                "slug": "capitolio",
                "features": [
                    {
                        "poster": "",
                        "time": ["2026-08-01T19:00"],
                        "title": "Filme via CLI 2",
                        "original_title": "",
                        "price": "",
                        "director": "",
                        "classification": "",
                        "general_info": "",
                        "excerpt": "um filme",
                        "read_more": "",
                    }
                ],
            }
        ]
        json_path = tmp_path / "valid2.json"
        json_path.write_text(json.dumps(payload))

        runner.invoke(args=["import-json", str(json_path)])

        with app.app_context():
            run = (
                db_session.query(PipelineRun)
                .filter_by(pipeline_name="import-json")
                .one()
            )
            assert run.status == "success"
            assert run.source == "capitolio"
            assert run.finished_at is not None
            assert '"created": 1' in run.summary

            screening = (
                db_session.query(Screening).filter_by(pipeline_run_id=run.id).one()
            )
            assert screening.movie.title == "Filme via CLI 2"

    def test_zero_screenings_created_marks_run_as_warning(
        self, app, runner, tmp_path, setup_cinemas
    ):
        payload = [
            {
                "url": "",
                "cinema": "Cinemateca Capitólio",
                "slug": "capitolio",
                "features": [],
            }
        ]
        json_path = tmp_path / "empty.json"
        json_path.write_text(json.dumps(payload))

        runner.invoke(args=["import-json", str(json_path)])

        with app.app_context():
            run = (
                db_session.query(PipelineRun)
                .filter_by(pipeline_name="import-json")
                .one()
            )
            assert run.status == "warning"

    def test_invalid_json_marks_run_as_error(self, app, runner, tmp_path):
        json_path = tmp_path / "bad.json"
        json_path.write_text("not-valid-json{")

        runner.invoke(args=["import-json", str(json_path)])

        with app.app_context():
            run = (
                db_session.query(PipelineRun)
                .filter_by(pipeline_name="import-json")
                .one()
            )
            assert run.status == "error"
            assert run.source is None
            assert "inválido" in run.error_message

    def test_unknown_cinema_marks_run_as_error(self, app, runner, tmp_path):
        payload = [
            {
                "url": "",
                "cinema": "Inexistente",
                "slug": "inexistente",
                "features": [],
            }
        ]
        json_path = tmp_path / "unknown-cinema2.json"
        json_path.write_text(json.dumps(payload))

        runner.invoke(args=["import-json", str(json_path)])

        with app.app_context():
            run = (
                db_session.query(PipelineRun)
                .filter_by(pipeline_name="import-json")
                .one()
            )
            assert run.status == "error"
            assert "não encontrada" in run.error_message


class TestThinWrapperCommands:
    def test_dupe_check_calls_dupe_checker(self, runner):
        with patch("flask_backend.commands.dupe_checker") as mock_fn:
            runner.invoke(args=["dupe-check"])
        mock_fn.assert_called_once()

    def test_run_dedupper_calls_dedupper(self, runner):
        with patch("flask_backend.commands.dedupper") as mock_fn:
            runner.invoke(args=["run-dedupper"])
        mock_fn.assert_called_once()

    def test_generate_sitemap_calls_sitemap(self, runner):
        with patch("flask_backend.commands.sitemap") as mock_fn:
            runner.invoke(args=["generate-sitemap"])
        mock_fn.assert_called_once()

    def test_title_cleaning_report_calls_underlying_function(self, runner):
        with patch("flask_backend.commands.run_title_cleaning_report") as mock_fn:
            runner.invoke(args=["title-cleaning-report"])
        mock_fn.assert_called_once()

    def test_title_cleaning_backfill_dry_run_by_default(self, runner):
        with patch("flask_backend.commands.run_title_cleaning_backfill") as mock_fn:
            runner.invoke(args=["title-cleaning-backfill"])
        mock_fn.assert_called_once_with(apply=False)

    def test_title_cleaning_backfill_apply_flag(self, runner):
        with patch("flask_backend.commands.run_title_cleaning_backfill") as mock_fn:
            runner.invoke(args=["title-cleaning-backfill", "--apply"])
        mock_fn.assert_called_once_with(apply=True)

    def test_delete_movie_forwards_id_and_yes_flag(self, runner):
        with patch("flask_backend.commands.run_delete_movie") as mock_fn:
            runner.invoke(args=["delete-movie", "42", "--yes"])
        mock_fn.assert_called_once_with(42, skip_confirmation=True)

    def test_delete_movie_without_yes_flag(self, runner):
        with patch("flask_backend.commands.run_delete_movie") as mock_fn:
            runner.invoke(args=["delete-movie", "42"])
        mock_fn.assert_called_once_with(42, skip_confirmation=False)


class TestFetchPostersCommand:
    def test_prints_summary(self, runner):
        result_obj = PosterPipelineResult(
            processed=3, posters_found=2, posters_not_found=1, errors=0
        )
        with patch(
            "flask_backend.service.poster_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            result = runner.invoke(args=["fetch-posters"])
        assert "Processadas:          3" in result.output
        assert "Posters encontrados:  2" in result.output

    def test_dry_run_prints_notice(self, runner):
        result_obj = PosterPipelineResult()
        with patch(
            "flask_backend.service.poster_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            result = runner.invoke(args=["fetch-posters", "--dry-run"])
        assert "Modo dry-run" in result.output

    def test_skipped_all_sources_shows_hint(self, runner):
        result_obj = PosterPipelineResult(skipped_all_sources_tried=2)
        with patch(
            "flask_backend.service.poster_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            result = runner.invoke(args=["fetch-posters", "--verbose"])
        assert "poster-review" in result.output

    def test_creates_pipeline_run_with_success_status(self, app, runner):
        result_obj = PosterPipelineResult(processed=3, posters_found=3, errors=0)
        with patch(
            "flask_backend.service.poster_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            runner.invoke(args=["fetch-posters"])

        with app.app_context():
            run = (
                db_session.query(PipelineRun)
                .filter_by(pipeline_name="fetch-posters")
                .one()
            )
            assert run.status == "success"

    def test_creates_pipeline_run_with_warning_status_on_errors(self, app, runner):
        result_obj = PosterPipelineResult(processed=3, posters_found=1, errors=2)
        with patch(
            "flask_backend.service.poster_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            runner.invoke(args=["fetch-posters"])

        with app.app_context():
            run = (
                db_session.query(PipelineRun)
                .filter_by(pipeline_name="fetch-posters")
                .one()
            )
            assert run.status == "warning"


class TestPosterReviewCommand:
    def test_no_pending_reviews(self, runner):
        with patch(
            "flask_backend.service.poster_pipeline.get_manual_review_summary",
            return_value=[],
        ):
            result = runner.invoke(args=["poster-review"])
        assert "Nenhuma sessão pendente" in result.output

    def test_lists_pending_reviews(self, runner):
        summary = [
            {
                "screening_id": 7,
                "movie_title": "Um Filme",
                "sources_attempted": ["tmdb", "imdb"],
            }
        ]
        with patch(
            "flask_backend.service.poster_pipeline.get_manual_review_summary",
            return_value=summary,
        ):
            result = runner.invoke(args=["poster-review"])
        assert "Um Filme" in result.output
        assert "tmdb, imdb" in result.output


class TestFetchMovieMetadataCommand:
    def test_prints_summary(self, runner):
        result_obj = MetadataPipelineResult(
            processed=5, metadata_found=4, metadata_not_found=1
        )
        with patch(
            "flask_backend.service.movie_metadata_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            result = runner.invoke(args=["fetch-movie-metadata"])
        assert "Processados:          5" in result.output

    def test_skipped_all_sources_shows_hint(self, runner):
        result_obj = MetadataPipelineResult(skipped_all_sources_tried=3)
        with patch(
            "flask_backend.service.movie_metadata_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            result = runner.invoke(args=["fetch-movie-metadata", "--dry-run"])
        assert "movie-metadata-review" in result.output

    def test_creates_pipeline_run_with_success_status(self, app, runner):
        result_obj = MetadataPipelineResult(processed=5, metadata_found=5, errors=0)
        with patch(
            "flask_backend.service.movie_metadata_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            runner.invoke(args=["fetch-movie-metadata"])

        with app.app_context():
            run = (
                db_session.query(PipelineRun)
                .filter_by(pipeline_name="fetch-movie-metadata")
                .one()
            )
            assert run.status == "success"
            assert '"processed": 5' in run.summary

    def test_creates_pipeline_run_with_warning_status_on_errors(self, app, runner):
        result_obj = MetadataPipelineResult(processed=5, metadata_found=3, errors=2)
        with patch(
            "flask_backend.service.movie_metadata_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            runner.invoke(args=["fetch-movie-metadata"])

        with app.app_context():
            run = (
                db_session.query(PipelineRun)
                .filter_by(pipeline_name="fetch-movie-metadata")
                .one()
            )
            assert run.status == "warning"


class TestMovieMetadataReviewCommand:
    def test_no_pending_reviews(self, runner):
        with patch(
            "flask_backend.service.movie_metadata_pipeline.get_manual_review_summary",
            return_value=[],
        ):
            result = runner.invoke(args=["movie-metadata-review"])
        assert "Nenhum filme pendente" in result.output

    def test_lists_pending_reviews(self, runner):
        summary = [
            {
                "movie_id": 9,
                "movie_title": "Outro Filme",
                "sources_attempted": ["tmdb"],
            }
        ]
        with patch(
            "flask_backend.service.movie_metadata_pipeline.get_manual_review_summary",
            return_value=summary,
        ):
            result = runner.invoke(args=["movie-metadata-review"])
        assert "Outro Filme" in result.output
