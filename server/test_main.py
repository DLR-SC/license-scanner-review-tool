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
