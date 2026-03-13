import pytest
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock

from main import app, _cache

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_cache():
    _cache.clear()
    yield
    _cache.clear()


def test_github_stars_returns_star_count(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo",
        json={"stargazers_count": 42},
    )

    response = client.get("/github-stars?url=https://github.com/owner/repo")

    assert response.status_code == 200
    assert response.json() == {"stars": 42}
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert requests[0].url.path == "/repos/owner/repo"


def test_github_stars_non_github_url_returns_none():
    response = client.get("/github-stars?url=https://gitlab.com/owner/repo")

    assert response.status_code == 200
    assert response.json() == {"stars": None}


def test_github_stars_api_error_returns_none(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo",
        status_code=404,
    )

    response = client.get("/github-stars?url=https://github.com/owner/repo")

    assert response.status_code == 200
    assert response.json() == {"stars": None}


def test_github_stars_git_suffix_stripped(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo",
        json={"stargazers_count": 7},
    )

    response = client.get("/github-stars?url=https://github.com/owner/repo.git")

    assert response.status_code == 200
    assert response.json() == {"stars": 7}
    assert httpx_mock.get_requests()[0].url.path == "/repos/owner/repo"


def test_github_stars_cached_on_second_call(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo",
        json={"stargazers_count": 10},
    )

    client.get("/github-stars?url=https://github.com/owner/repo")
    response = client.get("/github-stars?url=https://github.com/owner/repo")

    assert response.json() == {"stars": 10}
    assert len(httpx_mock.get_requests()) == 1


# /downloads — npm


def test_downloads_npm_returns_weekly_count(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.npmjs.org/downloads/point/last-week/lodash",
        json={"downloads": 5_000_000},
    )

    response = client.get("/downloads?purl=pkg:npm/lodash%401.0.0")

    assert response.status_code == 200
    assert response.json() == {"weekly_downloads": 5_000_000}
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert requests[0].url.path == "/downloads/point/last-week/lodash"


def test_downloads_npm_scoped_package(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.npmjs.org/downloads/point/last-week/@scope/pkg",
        json={"downloads": 100},
    )

    response = client.get("/downloads?purl=pkg:npm/%40scope%2Fpkg%401.0.0")

    assert response.status_code == 200
    assert response.json() == {"weekly_downloads": 100}
    assert httpx_mock.get_requests()[0].url.path == "/downloads/point/last-week/@scope/pkg"


def test_downloads_npm_api_error_returns_none(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.npmjs.org/downloads/point/last-week/lodash",
        status_code=404,
    )

    response = client.get("/downloads?purl=pkg:npm/lodash%401.0.0")

    assert response.status_code == 200
    assert response.json() == {"weekly_downloads": None}


def test_downloads_npm_cached_on_second_call(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.npmjs.org/downloads/point/last-week/lodash",
        json={"downloads": 99},
    )

    client.get("/downloads?purl=pkg:npm/lodash%401.0.0")
    response = client.get("/downloads?purl=pkg:npm/lodash%401.0.0")

    assert response.json() == {"weekly_downloads": 99}
    assert len(httpx_mock.get_requests()) == 1


# /downloads — PyPI


def test_downloads_pypi_returns_weekly_count(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://pypistats.org/api/packages/requests/recent",
        json={"data": {"last_week": 10_000_000}},
    )

    response = client.get("/downloads?purl=pkg:pypi/requests%401.0.0")

    assert response.status_code == 200
    assert response.json() == {"weekly_downloads": 10_000_000}
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert requests[0].url.path == "/api/packages/requests/recent"


def test_downloads_pypi_api_error_returns_none(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://pypistats.org/api/packages/requests/recent",
        status_code=500,
    )

    response = client.get("/downloads?purl=pkg:pypi/requests%401.0.0")

    assert response.status_code == 200
    assert response.json() == {"weekly_downloads": None}


def test_downloads_pypi_cached_on_second_call(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://pypistats.org/api/packages/requests/recent",
        json={"data": {"last_week": 42}},
    )

    client.get("/downloads?purl=pkg:pypi/requests%401.0.0")
    response = client.get("/downloads?purl=pkg:pypi/requests%401.0.0")

    assert response.json() == {"weekly_downloads": 42}
    assert len(httpx_mock.get_requests()) == 1


# /downloads — unknown ecosystem


def test_downloads_unknown_purl_returns_none():
    response = client.get("/downloads?purl=pkg:maven/com.example/foo%401.0.0")

    assert response.status_code == 200
    assert response.json() == {"weekly_downloads": None}
