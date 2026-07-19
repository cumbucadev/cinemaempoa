from unittest.mock import patch

from sqlalchemy.exc import IntegrityError

from flask_backend.db import db_session
from flask_backend.models import Cinema, User


class TestInitDbCommand:
    def test_init_db_command_runs_migrations(self, runner):
        # the `app` fixture already ran init_db() once; running it again
        # via the CLI command should be a safe, idempotent no-op.
        result = runner.invoke(args=["init-db"])
        assert result.exit_code == 0
        assert "Initialized the database." in result.output


class TestInitDbProdCommand:
    def test_seeds_admin_user_and_cinemas(self, app, runner):
        result = runner.invoke(args=["init-db-prod"])
        assert result.exit_code == 0
        assert "Seeded the database - production." in result.output

        with app.app_context():
            assert db_session.query(User).count() == 1
            assert db_session.query(Cinema).count() == 5

    def test_running_twice_skips_existing_records(self, app, runner):
        runner.invoke(args=["init-db-prod"])
        result = runner.invoke(args=["init-db-prod"])

        assert result.exit_code == 0
        with app.app_context():
            assert db_session.query(User).count() == 1
            assert db_session.query(Cinema).count() == 5


class TestSeedDbCommand:
    def test_seeds_database(self, runner):
        result = runner.invoke(args=["seed-db"])
        assert result.exit_code == 0
        assert "Seeded the database." in result.output

    def test_running_twice_skips_existing_records(self, app, runner):
        runner.invoke(args=["seed-db"])
        result = runner.invoke(args=["seed-db"])

        assert result.exit_code == 0
        with app.app_context():
            assert db_session.query(Cinema).count() == 5
            assert db_session.query(User).count() == 1

    def test_skips_when_screenings_already_registered(self, runner):
        # Screening/Movie have no unique constraint that a natural
        # double-run would violate, so force the IntegrityError directly
        # to cover the "already registered" skip branches.
        with patch(
            "flask_backend.seeds.screening_seeds.create_screenings",
            side_effect=IntegrityError("stmt", {}, Exception()),
        ):
            result = runner.invoke(args=["seed-db"])
        assert result.exit_code == 0
        assert "Screenings already registered. Skipping..." in result.output

    def test_skips_when_movies_already_registered(self, runner):
        with patch(
            "flask_backend.seeds.movie_seeds.create_movies",
            side_effect=IntegrityError("stmt", {}, Exception()),
        ):
            result = runner.invoke(args=["seed-db"])
        assert result.exit_code == 0
        assert "Movies already registered. Skipping..." in result.output


class TestDbUpgradeCommand:
    def test_upgrades_to_given_revision(self, runner):
        with patch("alembic.command.upgrade") as mock_upgrade:
            result = runner.invoke(args=["db-upgrade", "head"])
        assert result.exit_code == 0
        mock_upgrade.assert_called_once()
        assert mock_upgrade.call_args[0][1] == "head"
        assert "Database upgraded to revision: head" in result.output


class TestDbDowngradeCommand:
    def test_downgrades_to_given_revision(self, runner):
        # "-1" is the default revision; passing it positionally would be
        # parsed by click as an option flag, so we rely on the default.
        with patch("alembic.command.downgrade") as mock_downgrade:
            result = runner.invoke(args=["db-downgrade"])
        assert result.exit_code == 0
        mock_downgrade.assert_called_once()
        assert mock_downgrade.call_args[0][1] == "-1"
        assert "Database downgraded to revision: -1" in result.output


class TestDbRevisionCommand:
    def test_autogenerate_flag_creates_auto_revision(self, runner):
        with patch("alembic.command.revision") as mock_revision:
            result = runner.invoke(
                args=["db-revision", "--autogenerate", "-m", "add table"]
            )
        assert result.exit_code == 0
        mock_revision.assert_called_once()
        assert mock_revision.call_args.kwargs["autogenerate"] is True
        assert mock_revision.call_args.kwargs["message"] == "add table"
        assert "Migração auto-gerada criada." in result.output

    def test_without_autogenerate_creates_empty_revision(self, runner):
        with patch("alembic.command.revision") as mock_revision:
            result = runner.invoke(args=["db-revision"])
        assert result.exit_code == 0
        mock_revision.assert_called_once()
        assert "autogenerate" not in mock_revision.call_args.kwargs
        assert "Migração vazia criada." in result.output


class TestDbCurrentCommand:
    def test_shows_current_revision(self, runner):
        with patch("alembic.command.current") as mock_current:
            result = runner.invoke(args=["db-current"])
        assert result.exit_code == 0
        mock_current.assert_called_once()


class TestDbHistoryCommand:
    def test_shows_history_verbose(self, runner):
        with patch("alembic.command.history") as mock_history:
            result = runner.invoke(args=["db-history", "--verbose"])
        assert result.exit_code == 0
        mock_history.assert_called_once()
        assert mock_history.call_args.kwargs["verbose"] is True

    def test_shows_history_non_verbose(self, runner):
        with patch("alembic.command.history") as mock_history:
            result = runner.invoke(args=["db-history"])
        assert result.exit_code == 0
        mock_history.assert_called_once()
        assert mock_history.call_args.kwargs["verbose"] is False
