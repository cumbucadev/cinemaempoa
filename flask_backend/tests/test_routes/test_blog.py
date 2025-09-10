"""
Tests the basic functionality of /blog and /blog/<slug> endpoints.
"""


class TestBlogIndex:
    """Test cases for public blog index."""

    def test_blog_index_returns_200(self, client):
        """Test that the blog index page returns 200 OK."""
        response = client.get("/blog")
        assert response.status_code == 200

    def test_blog_index_with_pagination(self, client):
        """Test blog index with pagination parameters."""
        response = client.get("/blog?page=1&limit=5")
        assert response.status_code == 200

    def test_blog_index_invalid_pagination_returns_400(self, client):
        """Test that invalid pagination parameters return 400."""
        response = client.get("/blog?page=invalid&limit=5")
        assert response.status_code == 400

    def test_blog_index_shows_published_posts(self, client, test_blog_post):
        """Test that published blog posts are shown on the index."""
        response = client.get("/blog")
        assert response.status_code == 200
        assert b"Test Blog Post" in response.data

    def test_blog_index_hides_draft_posts_when_not_logged_in(
        self, client, test_draft_blog_post
    ):
        """Test that draft posts are hidden when user is not logged in."""
        response = client.get("/blog")
        assert response.status_code == 200
        assert b"Draft Blog Post" not in response.data


class TestBlogShow:
    """Test cases for public blog show."""

    def test_blog_show_published_post_returns_200(self, client, test_blog_post):
        """Test that a published blog post can be viewed."""
        response = client.get(f'/blog/{test_blog_post["slug"]}')
        assert response.status_code == 200
        assert b"Test Blog Post" in response.data
        assert b"This is a test blog post content." in response.data

    def test_blog_show_draft_post_returns_404_when_not_logged_in(
        self, client, test_draft_blog_post
    ):
        """Test that draft posts return 404 when user is not logged in."""
        response = client.get(f'/blog/{test_draft_blog_post["slug"]}')
        assert response.status_code == 404

    def test_blog_show_nonexistent_post_returns_404(self, client):
        """Test that a non-existent blog post returns 404."""
        response = client.get("/blog/nonexistent-post")
        assert response.status_code == 404

    def test_blog_show_includes_markdown_content(self, client, test_blog_post):
        """Test that markdown content is properly rendered."""
        # Update the test post to include markdown
        with client.application.app_context():
            from flask_backend.db import db_session
            from flask_backend.models import BlogPost

            post = (
                db_session.query(BlogPost)
                .filter_by(slug=test_blog_post["slug"])
                .first()
            )
            post.content = "# Test Header\n\nThis is **bold** text."
            db_session.commit()

        response = client.get(f'/blog/{test_blog_post["slug"]}')
        # Check that markdown is rendered to HTML
        assert b"<h1>Test Header</h1>" in response.data
        assert b"<strong>bold</strong>" in response.data

    def test_blog_show_includes_updated_at_when_different_from_created_at(
        self, client, test_blog_post
    ):
        """Test that updated_at is shown when different from created_at."""
        from datetime import timedelta

        with client.application.app_context():
            from flask_backend.db import db_session
            from flask_backend.models import BlogPost

            post = (
                db_session.query(BlogPost)
                .filter_by(slug=test_blog_post["slug"])
                .first()
            )
            post.updated_at = post.created_at + timedelta(days=1)
            db_session.commit()

        response = client.get(f'/blog/{test_blog_post["slug"]}')
        # The template should show updated_at information
        assert b"Atualizado em" in response.data

    def test_blog_doesnt_show_updated_at_when_not_set(self, client, test_blog_post):
        """Test that updated_at is not shown when not set."""

        with client.application.app_context():
            from flask_backend.db import db_session
            from flask_backend.models import BlogPost

            post = (
                db_session.query(BlogPost)
                .filter_by(slug=test_blog_post["slug"])
                .first()
            )
            post.updated_at = None
            db_session.commit()

        response = client.get(f'/blog/{test_blog_post["slug"]}')
        assert response.status_code == 200
        assert b"Atualizado em" not in response.data

    def test_blog_doesn_t_show_updated_at_when_same_as_created_at(
        self, client, test_blog_post
    ):
        """Test that updated_at is not shown when same as created_at."""

        with client.application.app_context():
            from flask_backend.db import db_session
            from flask_backend.models import BlogPost

            post = (
                db_session.query(BlogPost)
                .filter_by(slug=test_blog_post["slug"])
                .first()
            )
            post.updated_at = post.created_at
            db_session.commit()

        response = client.get(f'/blog/{test_blog_post["slug"]}')
        assert response.status_code == 200
        assert b"Atualizado em" not in response.data

    def test_blog_show_includes_featured_image(self, client, test_blog_post):
        """Test that featured image is included in the post view."""
        response = client.get(f'/blog/{test_blog_post["slug"]}')
        assert response.status_code == 200
        assert b"https://example.com/image.jpg" in response.data
        assert b"Test image" in response.data  # alt text
