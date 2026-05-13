# SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
#
# SPDX-License-Identifier: Apache-2.0

import urllib.parse

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

    response = client.get("/api/v1/github-stars?url=https://github.com/owner/repo")

    assert response.status_code == 200
    assert response.json() == {"stars": 42}
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert requests[0].url.path == "/repos/owner/repo"


def test_github_stars_non_github_url_returns_none():
    response = client.get("/api/v1/github-stars?url=https://gitlab.com/owner/repo")

    assert response.status_code == 200
    assert response.json() == {"stars": None}


def test_github_stars_api_error_returns_none(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo",
        status_code=404,
    )

    response = client.get("/api/v1/github-stars?url=https://github.com/owner/repo")

    assert response.status_code == 200
    assert response.json() == {"stars": None}


def test_github_stars_git_suffix_stripped(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo",
        json={"stargazers_count": 7},
    )

    response = client.get("/api/v1/github-stars?url=https://github.com/owner/repo.git")

    assert response.status_code == 200
    assert response.json() == {"stars": 7}
    assert httpx_mock.get_requests()[0].url.path == "/repos/owner/repo"


def test_github_stars_cached_on_second_call(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo",
        json={"stargazers_count": 10},
    )

    client.get("/api/v1/github-stars?url=https://github.com/owner/repo")
    response = client.get("/api/v1/github-stars?url=https://github.com/owner/repo")

    assert response.json() == {"stars": 10}
    assert len(httpx_mock.get_requests()) == 1


# /downloads — npm


def test_downloads_npm_returns_weekly_count(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.npmjs.org/downloads/point/last-week/lodash",
        json={"downloads": 5_000_000},
    )

    response = client.get("/api/v1/downloads?purl=pkg:npm/lodash%401.0.0")

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

    response = client.get("/api/v1/downloads?purl=pkg:npm/%40scope%2Fpkg%401.0.0")

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

    response = client.get("/api/v1/downloads?purl=pkg:npm/lodash%401.0.0")

    assert response.status_code == 200
    assert response.json() == {"weekly_downloads": None}


def test_downloads_npm_cached_on_second_call(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.npmjs.org/downloads/point/last-week/lodash",
        json={"downloads": 99},
    )

    client.get("/api/v1/downloads?purl=pkg:npm/lodash%401.0.0")
    response = client.get("/api/v1/downloads?purl=pkg:npm/lodash%401.0.0")

    assert response.json() == {"weekly_downloads": 99}
    assert len(httpx_mock.get_requests()) == 1


# /downloads — PyPI


def test_downloads_pypi_returns_weekly_count(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://pypistats.org/api/packages/requests/recent",
        json={"data": {"last_week": 10_000_000}},
    )

    response = client.get("/api/v1/downloads?purl=pkg:pypi/requests%401.0.0")

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

    response = client.get("/api/v1/downloads?purl=pkg:pypi/requests%401.0.0")

    assert response.status_code == 200
    assert response.json() == {"weekly_downloads": None}


def test_downloads_pypi_cached_on_second_call(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://pypistats.org/api/packages/requests/recent",
        json={"data": {"last_week": 42}},
    )

    client.get("/api/v1/downloads?purl=pkg:pypi/requests%401.0.0")
    response = client.get("/api/v1/downloads?purl=pkg:pypi/requests%401.0.0")

    assert response.json() == {"weekly_downloads": 42}
    assert len(httpx_mock.get_requests()) == 1


# /downloads — unknown ecosystem


def test_downloads_unknown_purl_returns_none():
    response = client.get("/api/v1/downloads?purl=pkg:maven/com.example/foo%401.0.0")

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
    original_path = main_module.SCAN_RESULT_PATH
    original_data = main_module._scan_data

    def write(data: dict):
        path = tmp_path / "scan-result.yml"
        path.write_text(yaml.dump(data))
        main_module.SCAN_RESULT_PATH = path
        main_module._scan_data = data
        main_module._load_vcs_sibling_data()
        return path

    yield write
    main_module.SCAN_RESULT_PATH = original_path
    main_module._scan_data = original_data
    main_module._load_vcs_sibling_data()


def test_scan_result_missing_file(tmp_path):
    original_path = main_module.SCAN_RESULT_PATH
    original_data = main_module._scan_data
    main_module.SCAN_RESULT_PATH = tmp_path / "nonexistent.yml"
    main_module._scan_data = None
    try:
        response = client.get("/api/v1/scan-result")
        assert response.status_code == 404
    finally:
        main_module.SCAN_RESULT_PATH = original_path
        main_module._scan_data = original_data


def test_scan_result_empty(scan_result_file):
    scan_result_file(BASE)

    response = client.get("/api/v1/scan-result")

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

    response = client.get("/api/v1/scan-result")

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

    response = client.get("/api/v1/scan-result")

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

    response = client.get("/api/v1/scan-result")

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

    response = client.get("/api/v1/scan-result")

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

    response = client.get("/api/v1/scan-result")

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
        pkg_dir = (
            tmp_path / type_ / urllib.parse.quote(namespace, safe="") / name / version
        )
        pkg_dir.mkdir(parents=True, exist_ok=True)
        f = pkg_dir / rel_path
        f.write_text(content)
        return f

    yield make_file
    main_module.ORT_OUT_PATH = original


def test_file_content_bad_package_id():
    response = client.get(
        "/api/v1/file-content?package_id=NPM:lodash&path=LICENSE&start_line=1&end_line=1"
    )
    assert response.status_code == 200
    assert response.json() == {"lines": None, "total_lines": 0}


def test_file_content_missing_package_dir(tmp_path):
    original = main_module.ORT_OUT_PATH
    main_module.ORT_OUT_PATH = tmp_path
    try:
        response = client.get(
            "/api/v1/file-content?package_id=NPM::lodash:4.0.0&path=LICENSE&start_line=1&end_line=1"
        )
        assert response.status_code == 200
        assert response.json() == {"lines": None, "total_lines": 0}
    finally:
        main_module.ORT_OUT_PATH = original


def test_file_content_missing_file(file_content_dir):
    file_content_dir("NPM::lodash:4.0.0", "README.md", "hello")
    response = client.get(
        "/api/v1/file-content?package_id=NPM::lodash:4.0.0&path=LICENSE&start_line=1&end_line=1"
    )
    assert response.status_code == 200
    assert response.json() == {"lines": None, "total_lines": 0}


def test_file_content_returns_lines(file_content_dir):
    content = "\n".join(f"line{i}" for i in range(1, 6))
    file_content_dir("NPM::lodash:4.0.0", "LICENSE", content)
    response = client.get(
        "/api/v1/file-content?package_id=NPM::lodash:4.0.0&path=LICENSE&start_line=2&end_line=3&context_before=0&context_after=0"
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
        "/api/v1/file-content?package_id=NPM::lodash:4.0.0&path=LICENSE&start_line=5&end_line=5"
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
        "/api/v1/file-content?package_id=NPM::lodash:4.0.0&path=LICENSE&start_line=1&end_line=1&context_before=10&context_after=10"
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
        "/api/v1/file-content?package_id=NPM::lodash:4.0.0&path=LICENSE&start_line=3&end_line=3&context_before=10&context_after=10"
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
        "/api/v1/file-content?package_id=PyPI::requests:2.0&path=LICENSE&start_line=1&end_line=1&context_before=0&context_after=0"
    )
    assert response.status_code == 200
    lines = response.json()["lines"]
    assert len(lines) == 1
    assert lines[0] == {"number": 1, "content": "MIT License", "highlighted": True}


def test_file_content_scoped_npm_package(file_content_dir):
    file_content_dir("NPM:@babel:helper-string-parser:7.27.1", "LICENSE", "MIT License")
    response = client.get(
        "/api/v1/file-content?package_id=NPM:%40babel:helper-string-parser:7.27.1&path=LICENSE&start_line=1&end_line=1&context_before=0&context_after=0"
    )
    assert response.status_code == 200
    lines = response.json()["lines"]
    assert len(lines) == 1
    assert lines[0] == {"number": 1, "content": "MIT License", "highlighted": True}


def test_file_content_empty_file(file_content_dir):
    file_content_dir("NPM::lodash:4.0.0", "LICENSE", "")
    response = client.get(
        "/api/v1/file-content?package_id=NPM::lodash:4.0.0&path=LICENSE&start_line=1&end_line=1&context_before=0&context_after=0"
    )
    assert response.status_code == 200
    assert response.json() == {"lines": [], "total_lines": 0}


def test_file_content_vcs_sibling_fallback(file_content_dir, scan_result_file):
    # Package A has vcs.path "packages/core"; sibling B has vcs.path "packages/utils".
    # A file at "packages/utils/LICENSE" is stored under B's ORT dir, not A's.
    # Requesting the file for package A should fall back to the sibling B's directory.
    nested = file_content_dir("NPM::pkg-b:1.0.0", "LICENSE", "placeholder")
    pkg_b_dir = nested.parent
    (pkg_b_dir / "packages" / "utils").mkdir(parents=True, exist_ok=True)
    (pkg_b_dir / "packages" / "utils" / "LICENSE").write_text("MIT License")

    scan_result_file(
        {
            **BASE,
            "analyzer": {
                "result": {
                    "projects": [],
                    "packages": [
                        {
                            "id": "NPM::pkg-a:1.0.0",
                            "vcs_processed": {
                                "path": "packages/core",
                                "url": "",
                                "type": "",
                                "revision": "",
                            },
                        },
                        {
                            "id": "NPM::pkg-b:1.0.0",
                            "vcs_processed": {
                                "path": "packages/utils",
                                "url": "",
                                "type": "",
                                "revision": "",
                            },
                        },
                    ],
                    "dependency_graphs": {},
                }
            },
            "scanner": {
                "provenances": [
                    {
                        "id": "NPM::pkg-a:1.0.0",
                        "package_provenance": {
                            "vcs_info": {
                                "url": "https://github.com/example/monorepo",
                                "revision": "abc123",
                            },
                            "resolved_revision": "abc123",
                        },
                    },
                    {
                        "id": "NPM::pkg-b:1.0.0",
                        "package_provenance": {
                            "vcs_info": {
                                "url": "https://github.com/example/monorepo",
                                "revision": "abc123",
                            },
                            "resolved_revision": "abc123",
                        },
                    },
                ],
                "scan_results": [],
            },
        }
    )

    response = client.get(
        "/api/v1/file-content?package_id=NPM::pkg-a:1.0.0&path=packages/utils/LICENSE&start_line=1&end_line=1&context_before=0&context_after=0"
    )
    assert response.status_code == 200
    lines = response.json()["lines"]
    assert lines is not None
    assert len(lines) == 1
    assert lines[0]["content"] == "MIT License"


# /license-text

INDEX_MIT = [
    {"license_key": "mit", "spdx_license_key": "MIT", "other_spdx_license_keys": []}
]
INDEX_APACHE = [
    {
        "license_key": "apache-2.0",
        "spdx_license_key": "Apache-2.0",
        "other_spdx_license_keys": [],
    }
]
INDEX_BSD = [
    {
        "license_key": "bsd-new",
        "spdx_license_key": "BSD-3-Clause",
        "other_spdx_license_keys": [],
    }
]
INDEX_EMPTY: list = []


def test_license_text_returns_text(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://scancode-licensedb.aboutcode.org/index.json",
        json=INDEX_MIT,
    )
    httpx_mock.add_response(
        url="https://scancode-licensedb.aboutcode.org/mit.LICENSE",
        text="MIT License\n\nPermission is hereby granted...",
    )

    response = client.get("/api/v1/license-text?license=MIT")

    assert response.status_code == 200
    assert response.json() == {"text": "MIT License\n\nPermission is hereby granted..."}
    assert len(httpx_mock.get_requests()) == 2


def test_license_text_unknown_license_returns_none(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://scancode-licensedb.aboutcode.org/index.json",
        json=INDEX_EMPTY,
    )

    response = client.get("/api/v1/license-text?license=NOT-A-LICENSE")

    assert response.status_code == 200
    assert response.json() == {"text": None}
    assert len(httpx_mock.get_requests()) == 1


def test_license_text_invalid_id_returns_none_without_fetching(httpx_mock: HTTPXMock):
    response = client.get("/api/v1/license-text?license=../etc/passwd")

    assert response.status_code == 200
    assert response.json() == {"text": None}
    assert len(httpx_mock.get_requests()) == 0


def test_license_text_cached_on_second_call(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://scancode-licensedb.aboutcode.org/index.json",
        json=INDEX_APACHE,
    )
    httpx_mock.add_response(
        url="https://scancode-licensedb.aboutcode.org/apache-2.0.LICENSE",
        text="Apache License\nVersion 2.0",
    )

    client.get("/api/v1/license-text?license=Apache-2.0")
    response = client.get("/api/v1/license-text?license=Apache-2.0")

    assert response.json() == {"text": "Apache License\nVersion 2.0"}
    assert len(httpx_mock.get_requests()) == 2


# /path-excludes


@pytest.fixture
def pkg_config_file(tmp_path):
    original = main_module.PKG_CONFIG_PATH

    def write(data: list):
        path = tmp_path / "package-configurations.yml"
        path.write_text(yaml.dump(data))
        main_module.PKG_CONFIG_PATH = path

    main_module.PKG_CONFIG_PATH = tmp_path / "package-configurations.yml"
    yield write
    main_module.PKG_CONFIG_PATH = original


def test_path_excludes_missing_file_returns_empty(pkg_config_file):
    response = client.get("/api/v1/path-excludes?package_id=NPM::lodash:4.0.0")
    assert response.status_code == 200
    assert response.json() == {"package_id": "NPM::lodash:4.0.0", "path_excludes": []}


def test_path_excludes_populated_file_returns_list(pkg_config_file):
    pkg_config_file(
        [
            {
                "id": "NPM::lodash:4.0.0",
                "path_excludes": [
                    {"pattern": "tests/**", "reason": "TEST_TOOL_OF", "comment": ""}
                ],
            }
        ]
    )
    response = client.get("/api/v1/path-excludes?package_id=NPM::lodash:4.0.0")
    assert response.status_code == 200
    assert response.json() == {
        "package_id": "NPM::lodash:4.0.0",
        "path_excludes": [
            {"pattern": "tests/**", "reason": "TEST_TOOL_OF", "comment": ""}
        ],
    }


def test_path_excludes_put_creates_entry(pkg_config_file):
    response = client.put(
        "/api/v1/path-excludes",
        json={
            "package_id": "NPM::lodash:4.0.0",
            "pattern": "tests/**",
            "reason": "TEST_TOOL_OF",
            "comment": "",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "package_id": "NPM::lodash:4.0.0",
        "path_excludes": [
            {"pattern": "tests/**", "reason": "TEST_TOOL_OF", "comment": ""}
        ],
    }
    # verify file was written
    written = yaml.safe_load(main_module.PKG_CONFIG_PATH.read_text())
    assert written[0]["id"] == "NPM::lodash:4.0.0"
    assert written[0]["path_excludes"][0]["pattern"] == "tests/**"


def test_path_excludes_put_twice_no_duplicates(pkg_config_file):
    client.put(
        "/api/v1/path-excludes",
        json={
            "package_id": "NPM::lodash:4.0.0",
            "pattern": "tests/**",
            "reason": "TEST_TOOL_OF",
            "comment": "",
        },
    )
    client.put(
        "/api/v1/path-excludes",
        json={
            "package_id": "NPM::lodash:4.0.0",
            "pattern": "docs/**",
            "reason": "DOCUMENTATION_OF",
            "comment": "",
        },
    )
    # same pattern again — should not duplicate
    client.put(
        "/api/v1/path-excludes",
        json={
            "package_id": "NPM::lodash:4.0.0",
            "pattern": "tests/**",
            "reason": "TEST_TOOL_OF",
            "comment": "",
        },
    )
    response = client.get("/api/v1/path-excludes?package_id=NPM::lodash:4.0.0")
    excludes = response.json()["path_excludes"]
    assert len(excludes) == 2
    patterns = [e["pattern"] for e in excludes]
    assert patterns == ["tests/**", "docs/**"]


def test_path_excludes_delete_removes_pattern(pkg_config_file):
    pkg_config_file(
        [
            {
                "id": "NPM::lodash:4.0.0",
                "path_excludes": [
                    {"pattern": "tests/**", "reason": "TEST_TOOL_OF", "comment": ""},
                    {"pattern": "docs/**", "reason": "DOCUMENTATION_OF", "comment": ""},
                ],
            }
        ]
    )
    response = client.delete(
        "/api/v1/path-excludes?package_id=NPM::lodash:4.0.0&pattern=tests%2F%2A%2A"
    )
    assert response.status_code == 200
    assert response.json() == {
        "package_id": "NPM::lodash:4.0.0",
        "path_excludes": [
            {"pattern": "docs/**", "reason": "DOCUMENTATION_OF", "comment": ""}
        ],
    }


def test_path_excludes_delete_nonexistent_pattern_returns_unchanged(pkg_config_file):
    pkg_config_file(
        [
            {
                "id": "NPM::lodash:4.0.0",
                "path_excludes": [
                    {"pattern": "tests/**", "reason": "TEST_TOOL_OF", "comment": ""}
                ],
            }
        ]
    )
    response = client.delete(
        "/api/v1/path-excludes?package_id=NPM::lodash:4.0.0&pattern=nonexistent%2F%2A%2A"
    )
    assert response.status_code == 200
    assert response.json() == {
        "package_id": "NPM::lodash:4.0.0",
        "path_excludes": [
            {"pattern": "tests/**", "reason": "TEST_TOOL_OF", "comment": ""}
        ],
    }


def test_path_excludes_put_propagates_to_siblings(pkg_config_file, scan_result_file):
    scan_result_file(MONOREPO_SIBLINGS_DATA)
    client.put(
        "/api/v1/path-excludes",
        json={
            "package_id": "NPM::pkg-a:1.0.0",
            "pattern": "tests/**",
            "reason": "TEST_TOOL_OF",
            "comment": "",
        },
    )
    written = yaml.safe_load(main_module.PKG_CONFIG_PATH.read_text())
    entries = {e["id"]: e for e in written}
    assert "NPM::pkg-a:1.0.0" in entries
    assert "NPM::pkg-b:1.0.0" in entries
    assert entries["NPM::pkg-a:1.0.0"]["path_excludes"][0]["pattern"] == "tests/**"
    assert entries["NPM::pkg-b:1.0.0"]["path_excludes"][0]["pattern"] == "tests/**"


def test_path_excludes_delete_propagates_to_siblings(pkg_config_file, scan_result_file):
    scan_result_file(MONOREPO_SIBLINGS_DATA)
    pkg_config_file(
        [
            {
                "id": "NPM::pkg-a:1.0.0",
                "path_excludes": [
                    {"pattern": "tests/**", "reason": "TEST_TOOL_OF", "comment": ""}
                ],
            },
            {
                "id": "NPM::pkg-b:1.0.0",
                "path_excludes": [
                    {"pattern": "tests/**", "reason": "TEST_TOOL_OF", "comment": ""}
                ],
            },
        ]
    )
    client.delete(
        "/api/v1/path-excludes?package_id=NPM%3A%3Apkg-a%3A1.0.0&pattern=tests%2F%2A%2A"
    )
    written = yaml.safe_load(main_module.PKG_CONFIG_PATH.read_text())
    entries = {e["id"]: e for e in written}
    assert entries["NPM::pkg-a:1.0.0"].get("path_excludes", []) == []
    assert entries["NPM::pkg-b:1.0.0"].get("path_excludes", []) == []


# /license-curations


@pytest.fixture
def curations_file(tmp_path):
    original = main_module.CURATIONS_PATH

    def write(data: list):
        path = tmp_path / "curations.yml"
        path.write_text(yaml.dump(data))
        main_module.CURATIONS_PATH = path

    main_module.CURATIONS_PATH = tmp_path / "curations.yml"
    yield write
    main_module.CURATIONS_PATH = original


def test_license_curations_missing_file_returns_null(curations_file):
    response = client.get("/api/v1/license-curations?package_id=NPM::lodash:4.0.0")
    assert response.status_code == 200
    assert response.json() == {
        "package_id": "NPM::lodash:4.0.0",
        "comment": "",
        "concluded_license": None,
    }


def test_license_curations_populated_file_returns_curation(curations_file):
    curations_file(
        [
            {
                "id": "NPM::lodash:4.0.0",
                "curations": {
                    "comment": "Upstream declares MIT",
                    "concluded_license": "MIT",
                },
            }
        ]
    )
    response = client.get("/api/v1/license-curations?package_id=NPM::lodash:4.0.0")
    assert response.status_code == 200
    assert response.json() == {
        "package_id": "NPM::lodash:4.0.0",
        "comment": "Upstream declares MIT",
        "concluded_license": "MIT",
    }


def test_license_curations_put_creates_entry(curations_file):
    response = client.put(
        "/api/v1/license-curations",
        json={
            "package_id": "NPM::lodash:4.0.0",
            "comment": "",
            "concluded_license": "MIT",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "package_id": "NPM::lodash:4.0.0",
        "comment": "",
        "concluded_license": "MIT",
    }
    written = yaml.safe_load(main_module.CURATIONS_PATH.read_text())
    assert written[0]["id"] == "NPM::lodash:4.0.0"
    assert written[0]["curations"]["concluded_license"] == "MIT"


def test_license_curations_put_twice_upserts(curations_file):
    client.put(
        "/api/v1/license-curations",
        json={
            "package_id": "NPM::lodash:4.0.0",
            "comment": "first",
            "concluded_license": "MIT",
        },
    )
    client.put(
        "/api/v1/license-curations",
        json={
            "package_id": "NPM::lodash:4.0.0",
            "comment": "second",
            "concluded_license": "Apache-2.0",
        },
    )
    response = client.get("/api/v1/license-curations?package_id=NPM::lodash:4.0.0")
    assert response.json()["concluded_license"] == "Apache-2.0"
    assert response.json()["comment"] == "second"
    written = yaml.safe_load(main_module.CURATIONS_PATH.read_text())
    assert len(written) == 1


def test_license_curations_delete_removes_entry(curations_file):
    curations_file(
        [
            {
                "id": "NPM::lodash:4.0.0",
                "curations": {"comment": "", "concluded_license": "MIT"},
            }
        ]
    )
    response = client.delete("/api/v1/license-curations?package_id=NPM::lodash:4.0.0")
    assert response.status_code == 200
    assert response.json() == {
        "package_id": "NPM::lodash:4.0.0",
        "comment": "",
        "concluded_license": None,
    }
    written = yaml.safe_load(main_module.CURATIONS_PATH.read_text())
    assert written is None or written == []


def test_license_curations_delete_nonexistent_returns_null(curations_file):
    response = client.delete("/api/v1/license-curations?package_id=NPM::lodash:4.0.0")
    assert response.status_code == 200
    assert response.json() == {
        "package_id": "NPM::lodash:4.0.0",
        "comment": "",
        "concluded_license": None,
    }


def test_license_curations_all_empty_file_returns_empty_list(curations_file):
    response = client.get("/api/v1/license-curations/all")
    assert response.status_code == 200
    assert response.json() == []


def test_license_curations_all_returns_all_entries(curations_file):
    curations_file(
        [
            {
                "id": "NPM::lodash:4.0.0",
                "curations": {
                    "comment": "Upstream declares MIT",
                    "concluded_license": "MIT",
                },
            },
            {
                "id": "NPM::express:4.18.0",
                "curations": {
                    "comment": "",
                    "concluded_license": "MIT",
                },
            },
        ]
    )
    response = client.get("/api/v1/license-curations/all")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    by_id = {e["package_id"]: e for e in data}
    assert by_id["NPM::lodash:4.0.0"] == {
        "package_id": "NPM::lodash:4.0.0",
        "comment": "Upstream declares MIT",
        "concluded_license": "MIT",
    }
    assert by_id["NPM::express:4.18.0"] == {
        "package_id": "NPM::express:4.18.0",
        "comment": "",
        "concluded_license": "MIT",
    }


def test_license_text_spdx_id_differs_from_key(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://scancode-licensedb.aboutcode.org/index.json",
        json=INDEX_BSD,
    )
    httpx_mock.add_response(
        url="https://scancode-licensedb.aboutcode.org/bsd-new.LICENSE",
        text="BSD 3-Clause License\n\nRedistribution and use...",
    )

    response = client.get("/api/v1/license-text?license=BSD-3-Clause")

    assert response.status_code == 200
    assert response.json() == {
        "text": "BSD 3-Clause License\n\nRedistribution and use..."
    }
    assert httpx_mock.get_requests()[1].url.path == "/bsd-new.LICENSE"


# /finding-curations

FINDING_CURATION = {
    "path": "src/util.cpp",
    "start_lines": "3",
    "line_count": 11,
    "detected_license": "GPL-2.0-only",
    "reason": "CODE",
    "comment": "scanner matched a variable name",
    "concluded_license": "Apache-2.0",
}

FINDING_CURATION_2 = {
    "path": "src/other.cpp",
    "start_lines": "10",
    "line_count": 1,
    "detected_license": "MIT",
    "reason": "CODE",
    "comment": "",
    "concluded_license": "MIT",
}


def test_finding_curations_missing_file_returns_empty(pkg_config_file):
    response = client.get("/api/v1/finding-curations?package_id=NPM::lodash:4.0.0")
    assert response.status_code == 200
    assert response.json() == {
        "package_id": "NPM::lodash:4.0.0",
        "license_finding_curations": [],
    }


def test_finding_curations_populated_file_returns_list(pkg_config_file):
    pkg_config_file(
        [
            {
                "id": "NPM::lodash:4.0.0",
                "license_finding_curations": [FINDING_CURATION],
            }
        ]
    )
    response = client.get("/api/v1/finding-curations?package_id=NPM::lodash:4.0.0")
    assert response.status_code == 200
    data = response.json()
    assert data["package_id"] == "NPM::lodash:4.0.0"
    assert len(data["license_finding_curations"]) == 1
    assert data["license_finding_curations"][0] == FINDING_CURATION


def test_finding_curations_entry_without_curations_key_returns_empty(pkg_config_file):
    pkg_config_file(
        [
            {
                "id": "NPM::lodash:4.0.0",
                "path_excludes": [
                    {"pattern": "tests/**", "reason": "TEST_TOOL_OF", "comment": ""}
                ],
            }
        ]
    )
    response = client.get("/api/v1/finding-curations?package_id=NPM::lodash:4.0.0")
    assert response.status_code == 200
    assert response.json()["license_finding_curations"] == []


def test_finding_curations_put_creates_entry(pkg_config_file):
    response = client.put(
        "/api/v1/finding-curations",
        json={"package_id": "NPM::lodash:4.0.0", **FINDING_CURATION},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["package_id"] == "NPM::lodash:4.0.0"
    assert len(data["license_finding_curations"]) == 1
    assert data["license_finding_curations"][0] == FINDING_CURATION
    written = yaml.safe_load(main_module.PKG_CONFIG_PATH.read_text())
    assert written[0]["id"] == "NPM::lodash:4.0.0"
    assert (
        written[0]["license_finding_curations"][0]["path"] == FINDING_CURATION["path"]
    )
    assert (
        written[0]["license_finding_curations"][0]["concluded_license"]
        == FINDING_CURATION["concluded_license"]
    )


def test_finding_curations_put_two_different_findings(pkg_config_file):
    client.put(
        "/api/v1/finding-curations",
        json={"package_id": "NPM::lodash:4.0.0", **FINDING_CURATION},
    )
    client.put(
        "/api/v1/finding-curations",
        json={"package_id": "NPM::lodash:4.0.0", **FINDING_CURATION_2},
    )
    response = client.get("/api/v1/finding-curations?package_id=NPM::lodash:4.0.0")
    assert len(response.json()["license_finding_curations"]) == 2


def test_finding_curations_put_upserts_same_key(pkg_config_file):
    client.put(
        "/api/v1/finding-curations",
        json={"package_id": "NPM::lodash:4.0.0", **FINDING_CURATION},
    )
    updated = {**FINDING_CURATION, "concluded_license": "MIT", "comment": "updated"}
    client.put(
        "/api/v1/finding-curations", json={"package_id": "NPM::lodash:4.0.0", **updated}
    )
    response = client.get("/api/v1/finding-curations?package_id=NPM::lodash:4.0.0")
    curations = response.json()["license_finding_curations"]
    assert len(curations) == 1
    assert curations[0]["concluded_license"] == "MIT"
    assert curations[0]["comment"] == "updated"


def test_finding_curations_put_preserves_path_excludes(pkg_config_file):
    pkg_config_file(
        [
            {
                "id": "NPM::lodash:4.0.0",
                "path_excludes": [
                    {"pattern": "tests/**", "reason": "TEST_TOOL_OF", "comment": ""}
                ],
            }
        ]
    )
    client.put(
        "/api/v1/finding-curations",
        json={"package_id": "NPM::lodash:4.0.0", **FINDING_CURATION},
    )
    written = yaml.safe_load(main_module.PKG_CONFIG_PATH.read_text())
    entry = written[0]
    assert len(entry["path_excludes"]) == 1
    assert entry["path_excludes"][0]["pattern"] == "tests/**"
    assert len(entry["license_finding_curations"]) == 1


def test_finding_curations_delete_removes_entry(pkg_config_file):
    pkg_config_file(
        [
            {
                "id": "NPM::lodash:4.0.0",
                "license_finding_curations": [FINDING_CURATION, FINDING_CURATION_2],
            }
        ]
    )
    response = client.delete(
        f"/api/v1/finding-curations"
        f"?package_id=NPM%3A%3Alodash%3A4.0.0"
        f"&path={FINDING_CURATION['path']}"
        f"&start_lines={FINDING_CURATION['start_lines']}"
        f"&detected_license={FINDING_CURATION['detected_license']}"
    )
    assert response.status_code == 200
    curations = response.json()["license_finding_curations"]
    assert len(curations) == 1
    assert curations[0]["path"] == FINDING_CURATION_2["path"]


def test_finding_curations_delete_nonexistent_package_returns_empty(pkg_config_file):
    response = client.delete(
        "/api/v1/finding-curations"
        "?package_id=NPM%3A%3Alodash%3A4.0.0"
        "&path=src%2Futil.cpp"
        "&start_lines=3"
        "&detected_license=GPL-2.0-only"
    )
    assert response.status_code == 200
    assert response.json() == {
        "package_id": "NPM::lodash:4.0.0",
        "license_finding_curations": [],
    }


def test_finding_curations_delete_nonexistent_key_returns_unchanged(pkg_config_file):
    pkg_config_file(
        [{"id": "NPM::lodash:4.0.0", "license_finding_curations": [FINDING_CURATION]}]
    )
    response = client.delete(
        "/api/v1/finding-curations"
        "?package_id=NPM%3A%3Alodash%3A4.0.0"
        "&path=src%2Fother.cpp"
        "&start_lines=1"
        "&detected_license=MIT"
    )
    assert response.status_code == 200
    curations = response.json()["license_finding_curations"]
    assert len(curations) == 1
    assert curations[0]["path"] == FINDING_CURATION["path"]


MONOREPO_SIBLINGS_DATA = {
    **BASE,
    "analyzer": {
        "result": {
            "projects": [],
            "packages": [
                {"id": "NPM::pkg-a:1.0.0"},
                {"id": "NPM::pkg-b:1.0.0"},
            ],
            "dependency_graphs": {},
        }
    },
    "scanner": {
        "provenances": [
            {
                "id": "NPM::pkg-a:1.0.0",
                "package_provenance": {
                    "vcs_info": {
                        "url": "https://github.com/example/mono",
                        "revision": "",
                    },
                    "resolved_revision": "cafebabe",
                },
            },
            {
                "id": "NPM::pkg-b:1.0.0",
                "package_provenance": {
                    "vcs_info": {
                        "url": "https://github.com/example/mono",
                        "revision": "",
                    },
                    "resolved_revision": "cafebabe",
                },
            },
        ],
        "scan_results": [],
    },
}


def test_finding_curations_put_propagates_to_siblings(
    pkg_config_file, scan_result_file
):
    scan_result_file(MONOREPO_SIBLINGS_DATA)
    client.put(
        "/api/v1/finding-curations",
        json={"package_id": "NPM::pkg-a:1.0.0", **FINDING_CURATION},
    )
    written = yaml.safe_load(main_module.PKG_CONFIG_PATH.read_text())
    entries = {e["id"]: e for e in written}
    assert "NPM::pkg-a:1.0.0" in entries
    assert "NPM::pkg-b:1.0.0" in entries
    assert (
        entries["NPM::pkg-a:1.0.0"]["license_finding_curations"][0]["path"]
        == FINDING_CURATION["path"]
    )
    assert (
        entries["NPM::pkg-b:1.0.0"]["license_finding_curations"][0]["path"]
        == FINDING_CURATION["path"]
    )


def test_finding_curations_delete_propagates_to_siblings(
    pkg_config_file, scan_result_file
):
    scan_result_file(MONOREPO_SIBLINGS_DATA)
    pkg_config_file(
        [
            {"id": "NPM::pkg-a:1.0.0", "license_finding_curations": [FINDING_CURATION]},
            {"id": "NPM::pkg-b:1.0.0", "license_finding_curations": [FINDING_CURATION]},
        ]
    )
    client.delete(
        f"/api/v1/finding-curations"
        f"?package_id=NPM%3A%3Apkg-a%3A1.0.0"
        f"&path={FINDING_CURATION['path']}"
        f"&start_lines={FINDING_CURATION['start_lines']}"
        f"&detected_license={FINDING_CURATION['detected_license']}"
    )
    written = yaml.safe_load(main_module.PKG_CONFIG_PATH.read_text())
    entries = {e["id"]: e for e in written}
    assert entries["NPM::pkg-a:1.0.0"].get("license_finding_curations", []) == []
    assert entries["NPM::pkg-b:1.0.0"].get("license_finding_curations", []) == []
