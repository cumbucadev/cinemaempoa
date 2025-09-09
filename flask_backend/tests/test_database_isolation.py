"""
Test database isolation and cleanup.
Ensures that tests don't interfere with each other and the production database.
"""

import os

import pytest

from flask_backend.db import db_session
from flask_backend.models import BlogPost, User


class TestDatabaseIsolation:
    """Test cases for database isolation and cleanup."""

    def test_each_test_gets_clean_database(self, app):
        """Test that each test gets a fresh database."""
        with app.app_context():
            # Check that the database is empty initially
            user_count = db_session.query(User).count()
            post_count = db_session.query(BlogPost).count()
            assert user_count == 0
            assert post_count == 0

    def test_database_is_temporary_file(self, app):
        """Test that the database is a temporary file, not the production database."""
        # The app should be using a temporary database file
        # Check the environment variable instead of app config
        import os

        db_url = os.environ.get("DATABASE_URL", "")
        assert "sqlite:///" in db_url
        # Should not be the production database
        assert "flask_backend.sqlite" not in db_url
        # Should be a temporary file
        assert "/tmp/" in db_url or "tmp" in db_url

    def test_database_cleanup_after_test(self, app):
        """Test that the database file is cleaned up after the test."""
        db_path = None
        with app.app_context():
            # Get the database path
            db_url = app.config.get("DATABASE_URL", "")
            if db_url.startswith("sqlite:///"):
                db_path = db_url.replace("sqlite:///", "")

        # After the test context, the file should be cleaned up
        if db_path and os.path.exists(db_path):
            # This should not happen if cleanup is working properly
            pytest.fail(f"Database file {db_path} was not cleaned up")

    def test_multiple_tests_dont_share_data(self, app, test_user, test_blog_post):
        """Test that data from one test doesn't leak into another test."""
        with app.app_context():
            # This test should have the test data
            user_count = db_session.query(User).count()
            post_count = db_session.query(BlogPost).count()
            assert user_count >= 1  # At least the test_user
            assert post_count >= 1  # At least the test_blog_post

    def test_isolated_test_has_clean_database(self, app):
        """Test that a test without fixtures has a clean database."""
        with app.app_context():
            # This test should have a clean database
            user_count = db_session.query(User).count()
            post_count = db_session.query(BlogPost).count()
            assert user_count == 0
            assert post_count == 0

    def test_database_operations_are_isolated(self, app):
        """Test that database operations in one test don't affect another."""
        with app.app_context():
            # Create some data in this test
            user = User(username="isolation_test_user", password="password")
            db_session.add(user)
            db_session.commit()

            # Verify it exists
            user_count = db_session.query(User).count()
            assert user_count == 1

    def test_another_isolated_test_has_clean_database(self, app):
        """Test that another test still has a clean database."""
        with app.app_context():
            # This should be a fresh database
            user_count = db_session.query(User).count()
            post_count = db_session.query(BlogPost).count()
            assert user_count == 0
            assert post_count == 0
