# SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
#
# SPDX-License-Identifier: Apache-2.0

import pytest
import yaml
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock

import main as main_module
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
    assert (
        httpx_mock.get_requests()[0].url.path == "/downloads/point/last-week/@scope/pkg"
    )


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


# /scan-result

BASE = {
    "repository": {"vcs": {}, "vcs_processed": {}},
    "analyzer": {"result": {"projects": [], "packages": [], "dependency_graphs": {}}},
    "scanner": {"provenances": [], "scan_results": []},
}


@pytest.fixture
def scan_result_file(tmp_path):
    original = main_module.SCAN_RESULT_PATH

    def write(data: dict):
        path = tmp_path / "scan-result.yml"
        path.write_text(yaml.dump(data))
        main_module.SCAN_RESULT_PATH = path
        return path

    yield write
    main_module.SCAN_RESULT_PATH = original


def test_scan_result_missing_file(tmp_path):
    original = main_module.SCAN_RESULT_PATH
    main_module.SCAN_RESULT_PATH = tmp_path / "nonexistent.yml"
    try:
        response = client.get("/scan-result")
        assert response.status_code == 404
    finally:
        main_module.SCAN_RESULT_PATH = original


def test_scan_result_empty(scan_result_file):
    scan_result_file(BASE)

    response = client.get("/scan-result")

    assert response.status_code == 200
    body = response.json()
    assert body["packages"] == []
    assert body["projects"] == []
    assert body["scan_results"] == []


def test_scan_result_package_fields(scan_result_file):
    data = {
        **BASE,
        "analyzer": {
            "result": {
                "projects": [],
                "packages": [
                    {
                        "id": "Maven:com.example:foo:1.0",
                        "purl": "pkg:maven/com.example/foo@1.0",
                        "authors": ["Alice", "Bob"],
                        "declared_licenses": ["Apache-2.0"],
                        "declared_licenses_processed": {
                            "spdx_expression": "Apache-2.0"
                        },
                        "description": "A foo library",
                        "homepage_url": "https://example.com",
                        "vcs_processed": {
                            "url": "https://github.com/example/foo",
                            "revision": "abc",
                            "type": "Git",
                            "path": "",
                        },
                    }
                ],
                "dependency_graphs": {},
            }
        },
    }
    scan_result_file(data)

    response = client.get("/scan-result")

    assert response.status_code == 200
    pkg = response.json()["packages"][0]
    assert pkg["id"] == "Maven:com.example:foo:1.0"
    assert pkg["purl"] == "pkg:maven/com.example/foo@1.0"
    assert pkg["authors"] == ["Alice", "Bob"]
    assert pkg["declared_licenses"] == ["Apache-2.0"]
    assert pkg["declared_licenses_processed"]["spdx_expression"] == "Apache-2.0"
    assert pkg["description"] == "A foo library"
    assert pkg["homepage_url"] == "https://example.com"
    assert pkg["vcs_url"] == "https://github.com/example/foo"


def test_scan_result_vcs_provenance_linked(scan_result_file):
    data = {
        **BASE,
        "analyzer": {
            "result": {
                "projects": [],
                "packages": [{"id": "NPM::lodash:4.0.0"}],
                "dependency_graphs": {},
            }
        },
        "scanner": {
            "provenances": [
                {
                    "id": "NPM::lodash:4.0.0",
                    "package_provenance": {
                        "vcs_info": {
                            "url": "https://github.com/lodash/lodash",
                            "revision": "",
                        },
                        "resolved_revision": "deadbeef",
                    },
                }
            ],
            "scan_results": [
                {
                    "provenance": {
                        "vcs_info": {"url": "https://github.com/lodash/lodash"},
                        "resolved_revision": "deadbeef",
                    },
                    "summary": {
                        "licenses": [
                            {
                                "license": "MIT",
                                "location": {
                                    "path": "LICENSE",
                                    "start_line": 1,
                                    "end_line": 1,
                                },
                                "score": 100.0,
                            }
                        ]
                    },
                }
            ],
        },
    }
    scan_result_file(data)

    response = client.get("/scan-result")

    assert response.status_code == 200
    body = response.json()
    assert len(body["scan_results"]) == 1
    sr = body["scan_results"][0]
    assert sr["package_id"] == "NPM::lodash:4.0.0"
    assert sr["licenses"][0]["license"] == "MIT"
    assert sr["licenses"][0]["location"]["path"] == "LICENSE"
    assert sr["licenses"][0]["score"] == 100.0


def test_scan_result_source_artifact_provenance_linked(scan_result_file):
    artifact_url = "https://registry.npmjs.org/lodash/-/lodash-4.0.0.tgz"
    data = {
        **BASE,
        "analyzer": {
            "result": {
                "projects": [],
                "packages": [{"id": "NPM::lodash:4.0.0"}],
                "dependency_graphs": {},
            }
        },
        "scanner": {
            "provenances": [
                {
                    "id": "NPM::lodash:4.0.0",
                    "package_provenance": {
                        "source_artifact": {"url": artifact_url},
                    },
                }
            ],
            "scan_results": [
                {
                    "provenance": {
                        "source_artifact": {"url": artifact_url},
                    },
                    "summary": {
                        "licenses": [
                            {
                                "license": "MIT",
                                "location": {
                                    "path": "LICENSE",
                                    "start_line": 1,
                                    "end_line": 1,
                                },
                                "score": 99.0,
                            }
                        ]
                    },
                }
            ],
        },
    }
    scan_result_file(data)

    response = client.get("/scan-result")

    assert response.status_code == 200
    body = response.json()
    assert len(body["scan_results"]) == 1
    assert body["scan_results"][0]["package_id"] == "NPM::lodash:4.0.0"


def test_scan_result_vcs_siblings(scan_result_file):
    vcs_url = "https://github.com/example/mono"
    revision = "cafebabe"
    data = {
        **BASE,
        "analyzer": {
            "result": {
                "projects": [],
                "packages": [
                    {"id": "Maven:com.example:foo:1.0"},
                    {"id": "Maven:com.example:bar:1.0"},
                ],
                "dependency_graphs": {},
            }
        },
        "scanner": {
            "provenances": [
                {
                    "id": "Maven:com.example:foo:1.0",
                    "package_provenance": {
                        "vcs_info": {"url": vcs_url, "revision": ""},
                        "resolved_revision": revision,
                    },
                },
                {
                    "id": "Maven:com.example:bar:1.0",
                    "package_provenance": {
                        "vcs_info": {"url": vcs_url, "revision": ""},
                        "resolved_revision": revision,
                    },
                },
            ],
            "scan_results": [
                {
                    "provenance": {
                        "vcs_info": {"url": vcs_url},
                        "resolved_revision": revision,
                    },
                    "summary": {"licenses": []},
                }
            ],
        },
    }
    scan_result_file(data)

    response = client.get("/scan-result")

    assert response.status_code == 200
    body = response.json()
    pkgs = {p["id"]: p for p in body["packages"]}
    assert pkgs["Maven:com.example:foo:1.0"]["vcs_siblings"] == [
        "Maven:com.example:bar:1.0"
    ]
    assert pkgs["Maven:com.example:bar:1.0"]["vcs_siblings"] == [
        "Maven:com.example:foo:1.0"
    ]
    # one scan_result per package
    assert len(body["scan_results"]) == 2
    pkg_ids = {sr["package_id"] for sr in body["scan_results"]}
    assert pkg_ids == {"Maven:com.example:foo:1.0", "Maven:com.example:bar:1.0"}


def test_scan_result_unmatched_provenance(scan_result_file):
    data = {
        **BASE,
        "analyzer": {
            "result": {
                "projects": [],
                "packages": [{"id": "NPM::lodash:4.0.0"}],
                "dependency_graphs": {},
            }
        },
        "scanner": {
            "provenances": [
                {
                    "id": "NPM::lodash:4.0.0",
                    "package_provenance": {
                        "vcs_info": {
                            "url": "https://github.com/lodash/lodash",
                            "revision": "",
                        },
                        "resolved_revision": "aabbccdd",
                    },
                }
            ],
            "scan_results": [
                {
                    "provenance": {
                        "vcs_info": {"url": "https://github.com/lodash/lodash"},
                        "resolved_revision": "00000000",  # different revision — no match
                    },
                    "summary": {"licenses": []},
                }
            ],
        },
    }
    scan_result_file(data)

    response = client.get("/scan-result")

    assert response.status_code == 200
    assert response.json()["scan_results"] == []


# /file-content


@pytest.fixture
def file_content_dir(tmp_path):
    original = main_module.ORT_OUT_PATH
    main_module.ORT_OUT_PATH = tmp_path

    def make_file(pkg_id: str, rel_path: str, content: str):
        parts = pkg_id.split(":")
        type_, namespace, name, version = (
            parts[0],
            parts[1] or "unknown",
            parts[2],
            parts[3],
        )
        pkg_dir = tmp_path / type_ / namespace / name / version
        pkg_dir.mkdir(parents=True, exist_ok=True)
        f = pkg_dir / rel_path
        f.write_text(content)
        return f

    yield make_file
    main_module.ORT_OUT_PATH = original


def test_file_content_bad_package_id():
    response = client.get(
        "/file-content?package_id=NPM:lodash&path=LICENSE&start_line=1&end_line=1"
    )
    assert response.status_code == 200
    assert response.json() == {"lines": None}


def test_file_content_missing_package_dir(tmp_path):
    original = main_module.ORT_OUT_PATH
    main_module.ORT_OUT_PATH = tmp_path
    try:
        response = client.get(
            "/file-content?package_id=NPM::lodash:4.0.0&path=LICENSE&start_line=1&end_line=1"
        )
        assert response.status_code == 200
        assert response.json() == {"lines": None}
    finally:
        main_module.ORT_OUT_PATH = original


def test_file_content_missing_file(file_content_dir):
    file_content_dir("NPM::lodash:4.0.0", "README.md", "hello")
    response = client.get(
        "/file-content?package_id=NPM::lodash:4.0.0&path=LICENSE&start_line=1&end_line=1"
    )
    assert response.status_code == 200
    assert response.json() == {"lines": None}


def test_file_content_returns_lines(file_content_dir):
    content = "\n".join(f"line{i}" for i in range(1, 6))
    file_content_dir("NPM::lodash:4.0.0", "LICENSE", content)
    response = client.get(
        "/file-content?package_id=NPM::lodash:4.0.0&path=LICENSE&start_line=2&end_line=3&context=0"
    )
    assert response.status_code == 200
    lines = response.json()["lines"]
    assert len(lines) == 2
    assert lines[0] == {"number": 2, "content": "line2", "highlighted": True}
    assert lines[1] == {"number": 3, "content": "line3", "highlighted": True}


def test_file_content_default_context(file_content_dir):
    content = "\n".join(f"line{i}" for i in range(1, 11))
    file_content_dir("NPM::lodash:4.0.0", "LICENSE", content)
    response = client.get(
        "/file-content?package_id=NPM::lodash:4.0.0&path=LICENSE&start_line=5&end_line=5"
    )
    assert response.status_code == 200
    lines = response.json()["lines"]
    assert len(lines) == 10
    assert lines[0]["number"] == 1
    assert lines[9]["number"] == 10
    highlighted = [l for l in lines if l["highlighted"]]
    assert len(highlighted) == 1
    assert highlighted[0]["number"] == 5


def test_file_content_context_clamped_at_start(file_content_dir):
    content = "\n".join(f"line{i}" for i in range(1, 4))
    file_content_dir("NPM::lodash:4.0.0", "LICENSE", content)
    response = client.get(
        "/file-content?package_id=NPM::lodash:4.0.0&path=LICENSE&start_line=1&end_line=1&context=10"
    )
    assert response.status_code == 200
    lines = response.json()["lines"]
    assert len(lines) == 3
    assert lines[0]["number"] == 1
    highlighted = [l for l in lines if l["highlighted"]]
    assert len(highlighted) == 1
    assert highlighted[0]["number"] == 1


def test_file_content_context_clamped_at_end(file_content_dir):
    content = "\n".join(f"line{i}" for i in range(1, 4))
    file_content_dir("NPM::lodash:4.0.0", "LICENSE", content)
    response = client.get(
        "/file-content?package_id=NPM::lodash:4.0.0&path=LICENSE&start_line=3&end_line=3&context=10"
    )
    assert response.status_code == 200
    lines = response.json()["lines"]
    assert len(lines) == 3
    assert lines[2]["number"] == 3
    highlighted = [l for l in lines if l["highlighted"]]
    assert len(highlighted) == 1
    assert highlighted[0]["number"] == 3


def test_file_content_empty_namespace(file_content_dir):
    file_content_dir("PyPI::requests:2.0", "LICENSE", "MIT License")
    response = client.get(
        "/file-content?package_id=PyPI::requests:2.0&path=LICENSE&start_line=1&end_line=1&context=0"
    )
    assert response.status_code == 200
    lines = response.json()["lines"]
    assert len(lines) == 1
    assert lines[0] == {"number": 1, "content": "MIT License", "highlighted": True}


def test_file_content_empty_file(file_content_dir):
    file_content_dir("NPM::lodash:4.0.0", "LICENSE", "")
    response = client.get(
        "/file-content?package_id=NPM::lodash:4.0.0&path=LICENSE&start_line=1&end_line=1&context=0"
    )
    assert response.status_code == 200
    assert response.json() == {"lines": []}
