# ruff: noqa: E402

from urllib.parse import urljoin

import pytest
import requests

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright


def open_page(browser, base_url: str, path: str):
    context = browser.new_context()
    page = context.new_page()
    page.goto(urljoin(base_url, path), wait_until="domcontentloaded")
    return context, page


def assert_download_button_for_loaded_image(
    page,
    image_selector: str,
    button_selector: str,
):
    image = page.locator(image_selector).first
    button = page.locator(button_selector).first

    expect(image).to_be_visible()

    page.wait_for_function(
        """
        ({ imageSelector, buttonSelector }) => {
            const img = document.querySelector(imageSelector);
            const btn = document.querySelector(buttonSelector);

            if (!img || !btn) return false;

            const style = window.getComputedStyle(btn);

            return (
                img.complete === true &&
                img.naturalWidth > 0 &&
                img.classList.contains("is-loaded") &&
                style.opacity === "1" &&
                style.visibility === "visible" &&
                style.pointerEvents === "auto"
            );
        }
        """,
        arg={"imageSelector": image_selector, "buttonSelector": button_selector},
    )

    expect(button).to_be_visible()


def assert_download_request_happens(
    page,
    base_url: str,
    expected_image_path: str,
    button_selector: str,
):
    expected_url = urljoin(base_url, expected_image_path)
    requests_seen = []

    def handle_request(request):
        requests_seen.append(request.url)

    page.on("request", handle_request)
    for el in page.locator(button_selector).all():
        el.click()
        page.wait_for_timeout(500)

    assert expected_url in requests_seen


@pytest.fixture()
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("page_key", "image_selector", "button_selector"),
    [
        (
            "home",
            ".poster-download-anchor img",
            ".poster-download-anchor .download-btn",
        ),
        (
            "show",
            ".poster-download-anchor img",
            ".poster-download-anchor .download-btn",
        ),
        ("posters", ".image-container .poster-image", ".image-container .download-btn"),
    ],
)
def test_download_button_appears_only_after_image_load_and_triggers_download(
    browser,
    live_server,
    page_key,
    image_selector,
    button_selector,
):
    base_url = live_server["base_url"]
    page_path = live_server["base_paths"][page_key]
    image_path = live_server["image_paths"][page_key]

    response = requests.get(urljoin(base_url, page_path), timeout=5)
    assert response.status_code == 200

    context, page = open_page(browser, base_url, page_path)

    try:
        assert_download_button_for_loaded_image(
            page=page,
            image_selector=image_selector,
            button_selector=button_selector,
        )

        assert_download_request_happens(
            page=page,
            base_url=base_url,
            expected_image_path=image_path,
            button_selector=button_selector,
        )
    finally:
        context.close()
