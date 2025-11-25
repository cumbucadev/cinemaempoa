"""
Smoke tests for the website content pages such as about, contact, etc
"""


class TestAbout:
    def test_about_page_returns_200(self, client):
        response = client.get("/about")
        assert response.status_code == 200
