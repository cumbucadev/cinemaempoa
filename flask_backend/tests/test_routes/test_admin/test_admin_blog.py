"""
Tests the basic functionality of /admin/blog/* endpoints.
"""


class TestAdminBlogRoutes:
    """Test cases for admin blog routes."""

    def test_admin_blog_toggle_publish_nonexistent_post_returns_404(self, auth_headers):
        """Test that toggling publish on a non-existent post returns 404."""
        response = auth_headers.post("/admin/blog/99999/toggle-publish")
        assert response.status_code == 404


class TestAdminBlogIndex:
    """Test cases for admin blog index."""

    def test_admin_blog_index_requires_login(self, client):
        """Test that admin blog index requires authentication."""
        response = client.get("/admin/blog")
        # Should redirect to login page
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_admin_blog_index_with_auth_returns_200(self, auth_headers):
        """Test that admin blog index returns 200 when authenticated."""
        response = auth_headers.get("/admin/blog")
        assert response.status_code == 200

    def test_admin_blog_index_invalid_pagination_returns_400(self, auth_headers):
        """Test that invalid pagination parameters return 400."""
        response = auth_headers.get("/admin/blog?page=invalid&limit=10")
        assert response.status_code == 400

    def test_admin_blog_index_shows_all_posts_including_drafts(
        self, auth_headers, test_blog_post, test_draft_blog_post
    ):
        """Test that admin index shows both published and draft posts."""
        response = auth_headers.get("/admin/blog")
        assert response.status_code == 200
        assert b"Test Blog Post" in response.data
        assert b"Draft Blog Post" in response.data


class TestAdminBlogNew:
    """Test cases for admin blog new."""

    def test_admin_blog_new_requires_login(self, client):
        """Test that admin blog new requires authentication."""
        response = client.get("/admin/blog/new")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_admin_blog_new_get_with_auth_returns_200(self, auth_headers):
        """Test that admin blog new GET returns 200 when authenticated."""
        response = auth_headers.get("/admin/blog/new")
        assert response.status_code == 200


class TestAdmingBlogPost:
    def test_admin_blog_new_post_requires_login(self, client):
        """Test that admin blog new POST requires authentication."""
        response = client.post(
            "/admin/blog/new", data={"title": "New Test Post", "content": "New content"}
        )
        assert response.status_code == 302
        assert b"/auth/login" in response.data

        with client.application.app_context():
            from flask_backend.db import db_session
            from flask_backend.models import BlogPost

            post = (
                db_session.query(BlogPost).filter_by(title="New Post via Test").first()
            )
            assert post is None

    def test_admin_blog_new_post_with_auth_creates_post(self, client, auth_headers):
        """Test that admin blog new POST creates a new post when authenticated."""
        response = auth_headers.post(
            "/admin/blog/new",
            data={
                "title": "New Test Post",
                "content": "This is new test content.",
                "excerpt": "New test excerpt",
                "slug": "new-test-post",
                "published": "on",
                "featured_image": "https://example.com/new-image.jpg",
                "featured_image_alt": "New test image",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        # Should redirect to edit page after creation
        assert b"New Test Post" in response.data
        with client.application.app_context():
            from flask_backend.db import db_session
            from flask_backend.models import BlogPost

            post = db_session.query(BlogPost).filter_by(title="New Test Post").first()
            assert post is not None

    def test_admin_blog_new_post_validation_errors(self, client, auth_headers):
        """Test that admin blog new POST shows validation errors."""
        response = auth_headers.post(
            "/admin/blog/new",
            data={
                "title": "",  # Empty title should cause error
                "content": "Some validation test content",
            },
        )
        assert response.status_code == 200
        assert b"T\xc3\xadtulo \xc3\xa9 obrigat\xc3\xb3rio" in response.data

        with client.application.app_context():
            from flask_backend.db import db_session
            from flask_backend.models import BlogPost

            post = (
                db_session.query(BlogPost)
                .filter_by(content="Some validation test content")
                .first()
            )
            assert post is None


class TestAdminBlogEdit:
    def test_admin_blog_edit_requires_login(self, client, test_blog_post):
        """Test that admin blog edit requires authentication."""
        response = client.get(f'/admin/blog/{test_blog_post["id"]}/edit')
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_admin_blog_edit_get_with_auth_returns_200(
        self, auth_headers, test_blog_post
    ):
        """Test that admin blog edit GET returns 200 when authenticated."""
        response = auth_headers.get(f'/admin/blog/{test_blog_post["id"]}/edit')
        assert response.status_code == 200
        assert b"Test Blog Post" in response.data

    def test_admin_blog_edit_nonexistent_post_returns_404(self, auth_headers):
        """Test that editing a non-existent post returns 404."""
        response = auth_headers.get("/admin/blog/99999/edit")
        assert response.status_code == 404


class TestAdminBlogUpdate:
    def test_admin_blog_edit_post_updates_post(
        self, client, auth_headers, test_blog_post
    ):
        """Test that admin blog edit POST updates the post."""
        response = auth_headers.post(
            f'/admin/blog/{test_blog_post["id"]}/edit',
            data={
                "title": "Updated Test Post",
                "content": "This is updated test content.",
                "excerpt": "Updated test excerpt",
                "slug": "updated-test-post",
                "published": "on",
                "featured_image": "https://example.com/updated-image.jpg",
                "featured_image_alt": "Updated test image",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Updated Test Post" in response.data

        with client.application.app_context():
            from flask_backend.db import db_session
            from flask_backend.models import BlogPost

            post = (
                db_session.query(BlogPost).filter_by(title="Updated Test Post").first()
            )
            assert post is not None

    def test_admin_blog_edit_post_validation_errors(
        self, client, auth_headers, test_blog_post
    ):
        """Test that admin blog edit POST shows validation errors."""
        response = auth_headers.post(
            f'/admin/blog/{test_blog_post["id"]}/edit',
            data={
                "title": "",  # Empty title should cause error
                "content": "Some validation test content",
            },
        )
        assert response.status_code == 200
        assert b"T\xc3\xadtulo \xc3\xa9 obrigat\xc3\xb3rio" in response.data

        with client.application.app_context():
            from flask_backend.db import db_session
            from flask_backend.models import BlogPost

            post = (
                db_session.query(BlogPost)
                .filter_by(content="Some validation test content")
                .first()
            )
            assert post is None


class TestAdminBlogDelete:
    def test_admin_blog_delete_requires_login(self, client, test_blog_post):
        """Test that admin blog delete requires authentication."""
        response = client.post(f'/admin/blog/{test_blog_post["id"]}/delete')
        assert response.status_code == 302
        assert b"/auth/login" in response.data

        with client.application.app_context():
            from flask_backend.db import db_session
            from flask_backend.models import BlogPost

            post = db_session.query(BlogPost).filter_by(id=test_blog_post["id"]).first()
            assert post is not None

    def test_admin_blog_delete_with_auth_deletes_post(
        self, client, auth_headers, test_blog_post
    ):
        """Test that admin blog delete removes the post when authenticated."""
        response = auth_headers.post(
            f'/admin/blog/{test_blog_post["id"]}/delete', follow_redirects=True
        )
        assert response.status_code == 200
        assert b"admin/blog" in response.data

        with client.application.app_context():
            from flask_backend.db import db_session
            from flask_backend.models import BlogPost

            post = db_session.query(BlogPost).filter_by(id=test_blog_post["id"]).first()
            assert post is None

    def test_admin_blog_delete_nonexistent_post_returns_404(self, auth_headers):
        """Test that deleting a non-existent post returns 404."""
        response = auth_headers.post("/admin/blog/99999/delete")
        assert response.status_code == 404


class TestAdminBlogTogglePublish:
    def test_admin_blog_toggle_publish_requires_login(self, client, test_blog_post):
        """Test that admin blog toggle publish requires authentication."""
        current_status = test_blog_post["published"]
        response = client.post(f'/admin/blog/{test_blog_post["id"]}/toggle-publish')
        assert response.status_code == 302
        assert b"/auth/login" in response.data

        with client.application.app_context():
            from flask_backend.db import db_session
            from flask_backend.models import BlogPost

            post = (
                db_session.query(BlogPost).filter_by(published=current_status).first()
            )
            assert post is not None

    def test_admin_blog_toggle_publish_with_auth_toggles_status(
        self, client, auth_headers, test_blog_post
    ):
        """Test that admin blog toggle publish changes the published status."""
        # Initially published
        assert test_blog_post["published"]

        response = auth_headers.post(
            f'/admin/blog/{test_blog_post["id"]}/toggle-publish', follow_redirects=True
        )
        assert response.status_code == 200
        # Should redirect back to admin index
        assert b"admin/blog" in response.data

        with client.application.app_context():
            from flask_backend.db import db_session
            from flask_backend.models import BlogPost

            post = db_session.query(BlogPost).filter_by(published=False).first()
            assert post is not None
