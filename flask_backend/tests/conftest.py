import os
import tempfile
from datetime import datetime

import pytest

from flask_backend import create_app
from flask_backend.db import db_session
from flask_backend.models import BlogPost, User


@pytest.fixture()
def app():
    """Create and configure a new app instance for each test."""
    # Create a temporary file to serve as the database
    db_fd, db_path = tempfile.mkstemp()

    # Override the DATABASE_URL environment variable for testing
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    try:
        app = create_app({"TESTING": True})

        # Create the database and tables
        with app.app_context():
            from flask_backend.db import init_db

            init_db()

        yield app

    finally:
        # Clean up
        os.close(db_fd)
        if os.path.exists(db_path):
            os.unlink(db_path)
        # Restore original DATABASE_URL
        if original_db_url is not None:
            os.environ["DATABASE_URL"] = original_db_url
        elif "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]


@pytest.fixture(autouse=True)
def clean_db(app):
    """Clean the database before each test."""
    with app.app_context():
        # Clear all data from tables
        from flask_backend.models import (
            BlogPost,
            Cinema,
            Movie,
            Screening,
            ScreeningDate,
            User,
        )

        db_session.query(BlogPost).delete()
        db_session.query(User).delete()
        db_session.query(ScreeningDate).delete()
        db_session.query(Screening).delete()
        db_session.query(Movie).delete()
        db_session.query(Cinema).delete()
        db_session.commit()


@pytest.fixture()
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture()
def runner(app):
    """A test CLI runner for the app."""
    return app.test_cli_runner()


@pytest.fixture()
def test_user(app):
    """Create a test user for authentication tests."""
    with app.app_context():
        user = User(username="testuser", password="testpassword")
        db_session.add(user)
        db_session.commit()
        # Return the user ID instead of the user object to avoid detachment issues
        return user.id


@pytest.fixture()
def test_blog_post(app, test_user):
    """Create a test blog post."""
    with app.app_context():
        post = BlogPost(
            title="Test Blog Post",
            slug="test-blog-post",
            content="This is a test blog post content.",
            excerpt="This is a test excerpt.",
            author_id=test_user,  # test_user is now the user ID
            created_at=datetime.now(),
            published=True,
            featured_image="https://example.com/image.jpg",
            featured_image_alt="Test image",
        )
        db_session.add(post)
        db_session.commit()
        # Return a dict with the post data to avoid detachment issues
        return {
            "id": post.id,
            "slug": post.slug,
            "title": post.title,
            "content": post.content,
            "published": post.published,
        }


@pytest.fixture()
def test_draft_blog_post(app, test_user):
    """Create a test draft blog post."""
    with app.app_context():
        post = BlogPost(
            title="Draft Blog Post",
            slug="draft-blog-post",
            content="This is a draft blog post content.",
            excerpt="This is a draft excerpt.",
            author_id=test_user,  # test_user is now the user ID
            created_at=datetime.now(),
            published=False,
        )
        db_session.add(post)
        db_session.commit()
        # Return a dict with the post data to avoid detachment issues
        return {
            "id": post.id,
            "slug": post.slug,
            "title": post.title,
            "content": post.content,
            "published": post.published,
        }


@pytest.fixture()
def auth_headers(client, test_user):
    """Get authentication headers for admin routes."""
    with client.session_transaction() as sess:
        # Set the user_id in the session to simulate login
        sess["user_id"] = test_user  # test_user is now the user ID

    # Return the client with session
    return client
