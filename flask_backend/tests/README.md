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

## Test Fixtures

The tests use several fixtures defined in `conftest.py`:

- `app` - Flask application with test configuration
- `client` - Test client for making HTTP requests
- `test_user` - A test user for authentication
- `auth_headers` - Authenticated client for admin tests
