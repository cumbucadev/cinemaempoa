"""
Test database isolation and cleanup.
Ensures that tests don't interfere with each other and the production database.
"""

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

    def test_multiple_tests_dont_share_data(self, app, test_user, test_blog_post):
        """Test that data from one test doesn't leak into another test."""
        with app.app_context():
            # This test should have the test data
            user_count = db_session.query(User).count()
            post_count = db_session.query(BlogPost).count()
            assert user_count == 1  # At least the test_user
            assert post_count == 1  # At least the test_blog_post

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
