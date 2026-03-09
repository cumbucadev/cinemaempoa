# Application tests

This directory contains tests related to the flask_backend module of the cinemaempoa project.

## Test Structure

Regardless of which part of the app is being tested, we attempt to test
how well different parts of the codebase interact with eachother.

This practice is sometimes called **integration testing**, but I prefer the **feature testing** terminology (taken from Laravel, even though this is a Python project :P - see https://laravel.com/docs/12.x/testing#introduction for more details).

The whole point is making sure that the functionallity under test works in a similar manner to which it would work in reality.

It is up to the developer to decide how much functionality each test should integrate and how much it should mock.

### Test Files

- `conftest.py` - Test configuration and fixtures
- `test_service` - General testing for the service submodule
- `test_routes` - General testing for the application routes: focused on validation, error handling and responses
- `test_database_isolation.py` - Tests to ensure database isolation and cleanup
- `e2e` - End-to-end frontend tests for JavaScript-driven behaviors, such as poster download button visibility

### Test Configuration

The tests are configured to:

1. **Use a separate test database** - Each test gets a fresh temporary SQLite database
2. **Avoid overwriting production data** - The production `flask_backend.sqlite` is never touched
3. **Clean up after each test** - Temporary database files are automatically removed
4. **Provide test fixtures** - Pre-configured test data for consistent testing

## Running the Tests

You can run all tests at once with `pytest flask_backend/tests` or target specific test files, for ex.

```
pytest flask_backend/tests/test_routes/test_blog.py
```

### Frontend E2E tests

The project now also supports frontend end-to-end tests for JavaScript behavior.

These tests use Playwright because the feature under test depends on dynamic DOM updates after image load, which is not reliably covered by plain HTML parsing with `requests` and `BeautifulSoup`.

Before running the E2E suite, install the Python dependency and the browser binaries:

```
pip install -r requirements.txt
python -m playwright install chromium
```

Run only the frontend E2E tests with:

```
pytest flask_backend/tests/e2e -m e2e
```

Or run a specific file, for example:

```
pytest flask_backend/tests/e2e/test_poster_download_e2e.py -m e2e
```

## Test Fixtures

The tests use several fixtures defined in `conftest.py`:

- `app` - Flask application with test configuration
- `client` - Test client for making HTTP requests
- `test_user` - A test user for authentication
- `auth_headers` - Authenticated client for admin tests

For frontend E2E coverage, the suite should additionally provide fixtures that:

- seed movies and screenings with poster images
- start the Flask application in test mode on a local HTTP port
- open a browser page and wait for the image and button states to stabilize

The initial E2E scope should validate the `downloadImage` button behavior on these pages:

- `/`
- `/movies/<slug>`
- `/movies/posters`
