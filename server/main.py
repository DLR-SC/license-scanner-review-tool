# SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
#
# SPDX-License-Identifier: Apache-2.0

import json
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "PUT", "DELETE"],
    allow_headers=["*"],
)

SCAN_RESULT_PATH = Path(__file__).parent / "ort-out" / "scan-result.yml"
ORT_OUT_PATH = Path(__file__).parent / "ort-out"
PKG_CONFIG_PATH = Path(__file__).parent / "ort-out" / "package-configurations.yml"
CURATIONS_PATH = Path(__file__).parent / "ort-out" / "curations.yml"

CACHE_TTL: dict[str, float] = {
    "github_stars": 3600,  # 1 hour
    "npm_downloads": 86400,  # 24 hours
    "pypi_downloads": 86400,  # 24 hours
    "license_text": 86400 * 30,  # 30 days
    "scancode_index": 86400 * 7,  # 7 days
}

SPDX_ID_RE = re.compile(r"^[A-Za-z0-9\-\.+]+$")

CACHE_BACKEND: str = os.environ.get("CACHE_BACKEND", "memory")  # "memory" | "disk"
CACHE_FILE: Path = Path(
    os.environ.get("CACHE_FILE", str(Path(__file__).parent / "cache.json"))
)

_cache: dict[str, tuple[float, Any]] = {}  # key -> (expires_at, value)


def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.time() > expires_at:
        del _cache[key]
        return None
    return value


def _cache_set(key: str, value: Any, ttl: float) -> None:
    serializable = value.model_dump() if hasattr(value, "model_dump") else value
    _cache[key] = (time.time() + ttl, serializable)
    if CACHE_BACKEND == "disk":
        _save_cache()


def _save_cache() -> None:
    with CACHE_FILE.open("w") as f:
        json.dump({k: list(v) for k, v in _cache.items()}, f)


def _load_cache() -> None:
    if not CACHE_FILE.exists():
        return
    with CACHE_FILE.open() as f:
        data = json.load(f)
    now = time.time()
    _cache.update({k: (v[0], v[1]) for k, v in data.items() if v[0] > now})


if CACHE_BACKEND == "disk":
    _load_cache()


class VcsInfo(BaseModel):
    type: str = ""
    url: str = ""
    revision: str = ""
    path: str = ""


class DeclaredLicensesProcessed(BaseModel):
    spdx_expression: str = ""


class Repository(BaseModel):
    vcs: VcsInfo
    vcs_processed: VcsInfo


class Project(BaseModel):
    id: str
    definition_file_path: str = ""
    declared_licenses: list[str] = []
    declared_licenses_processed: DeclaredLicensesProcessed = DeclaredLicensesProcessed()
    scope_names: list[str] = []
    homepage_url: str = ""


class Package(BaseModel):
    id: str
    purl: str = ""
    authors: list[str] = []
    declared_licenses: list[str] = []
    declared_licenses_processed: DeclaredLicensesProcessed = DeclaredLicensesProcessed()
    description: str = ""
    homepage_url: str = ""
    vcs_url: str = ""
    vcs_siblings: list[str] = []


class LicenseLocation(BaseModel):
    path: str
    start_line: int
    end_line: int


class LicenseFinding(BaseModel):
    license: str
    location: LicenseLocation
    score: float


class PackageScanResult(BaseModel):
    package_id: str = ""
    provenance: dict
    licenses: list[LicenseFinding]


class OrtResult(BaseModel):
    repository: Repository
    projects: list[Project]
    packages: list[Package]
    scan_results: list[PackageScanResult]



def parse_vcs(raw: dict) -> VcsInfo:
    return VcsInfo(
        type=raw.get("type", ""),
        url=raw.get("url", ""),
        revision=raw.get("revision", ""),
        path=raw.get("path", ""),
    )


def pkg_id_to_dir(pkg_id: str) -> Path | None:
    parts = pkg_id.split(":")
    if len(parts) < 4:
        return None
    type_, namespace, name, version = parts[0], parts[1], parts[2], parts[3]
    if not namespace:
        namespace = "unknown"
    return ORT_OUT_PATH / type_ / namespace / name / version


class PathExclude(BaseModel):
    pattern: str
    reason: str = ""
    comment: str = ""


class PackagePathExcludes(BaseModel):
    package_id: str
    path_excludes: list[PathExclude]


class AddPathExcludeRequest(BaseModel):
    package_id: str
    pattern: str
    reason: str = ""
    comment: str = ""


def _read_pkg_configs() -> list[dict]:
    if not PKG_CONFIG_PATH.exists():
        return []
    with PKG_CONFIG_PATH.open() as f:
        data = yaml.safe_load(f)
    return data or []


def _write_pkg_configs(configs: list[dict]) -> None:
    PKG_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PKG_CONFIG_PATH.open("w") as f:
        yaml.dump(configs, f, default_flow_style=False, allow_unicode=True)


class PackageCuration(BaseModel):
    package_id: str
    comment: str = ""
    concluded_license: str | None = None


class SetCurationRequest(BaseModel):
    package_id: str
    comment: str = ""
    concluded_license: str


def _read_curations() -> list[dict]:
    if not CURATIONS_PATH.exists():
        return []
    with CURATIONS_PATH.open() as f:
        data = yaml.safe_load(f)
    return data or []


def _write_curations(curations: list[dict]) -> None:
    CURATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CURATIONS_PATH.open("w") as f:
        yaml.dump(curations, f, default_flow_style=False, allow_unicode=True)


class FileContentLine(BaseModel):
    number: int
    content: str
    highlighted: bool


class FileContent(BaseModel):
    lines: list[FileContentLine] | None
    total_lines: int = 0


@app.get("/file-content", response_model=FileContent)
def get_file_content(
    package_id: str,
    path: str,
    start_line: int,
    end_line: int,
    context_before: int = 5,
    context_after: int = 5,
):
    pkg_dir = pkg_id_to_dir(package_id)
    if pkg_dir is None:
        return FileContent(lines=None)
    file_path = pkg_dir / path
    if not file_path.is_file():
        return FileContent(lines=None)
    all_lines = file_path.read_text(errors="replace").splitlines()
    fetch_start = max(0, start_line - 1 - context_before)
    fetch_end = min(len(all_lines), end_line + context_after)
    lines = [
        FileContentLine(
            number=i + 1,
            content=all_lines[i],
            highlighted=(start_line <= i + 1 <= end_line),
        )
        for i in range(fetch_start, fetch_end)
    ]
    return FileContent(lines=lines, total_lines=len(all_lines))


class DownloadStats(BaseModel):
    weekly_downloads: int | None


@app.get("/downloads", response_model=DownloadStats)
async def get_downloads(purl: str):
    async with httpx.AsyncClient() as client:
        if purl.startswith("pkg:npm/"):
            name = urllib.parse.unquote(purl.removeprefix("pkg:npm/").rsplit("@", 1)[0])
            cache_key = f"npm_downloads:{name}"
            if (cached := _cache_get(cache_key)) is not None:
                return cached
            r = await client.get(
                f"https://api.npmjs.org/downloads/point/last-week/{name}"
            )
            if r.status_code != 200:
                return DownloadStats(weekly_downloads=None)
            result = DownloadStats(weekly_downloads=r.json()["downloads"])
            _cache_set(cache_key, result, CACHE_TTL["npm_downloads"])
            return result

        elif purl.startswith("pkg:pypi/"):
            name = urllib.parse.unquote(purl.removeprefix("pkg:pypi/").split("@")[0])
            cache_key = f"pypi_downloads:{name}"
            if (cached := _cache_get(cache_key)) is not None:
                return cached
            r = await client.get(f"https://pypistats.org/api/packages/{name}/recent")
            if r.status_code != 200:
                return DownloadStats(weekly_downloads=None)
            result = DownloadStats(weekly_downloads=r.json()["data"]["last_week"])
            _cache_set(cache_key, result, CACHE_TTL["pypi_downloads"])
            return result

        return DownloadStats(weekly_downloads=None)


class GitHubStars(BaseModel):
    stars: int | None


@app.get("/github-stars", response_model=GitHubStars)
async def get_github_stars(url: str):
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    if not m:
        return GitHubStars(stars=None)
    owner, repo = m.group(1), m.group(2)
    cache_key = f"github_stars:{owner}/{repo}"
    if (cached := _cache_get(cache_key)) is not None:
        return cached
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers={"Accept": "application/vnd.github+json"},
        )
        if r.status_code != 200:
            return GitHubStars(stars=None)
        result = GitHubStars(stars=r.json()["stargazers_count"])
        _cache_set(cache_key, result, CACHE_TTL["github_stars"])
        return result


async def _get_spdx_to_key_map(client: httpx.AsyncClient) -> dict[str, str]:
    cache_key = "scancode_index"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        r = await client.get("https://scancode-licensedb.aboutcode.org/index.json")
    except httpx.RequestError:
        return {}
    if r.status_code != 200:
        return {}
    mapping: dict[str, str] = {}
    for entry in r.json():
        key = entry.get("license_key")
        if not key:
            continue
        spdx = entry.get("spdx_license_key")
        if spdx:
            mapping[spdx] = key
        for alt in entry.get("other_spdx_license_keys") or []:
            if alt and not alt.startswith("LicenseRef-"):
                mapping[alt] = key
    _cache_set(cache_key, mapping, CACHE_TTL["scancode_index"])
    return mapping


class LicenseText(BaseModel):
    text: str | None


@app.get("/license-text", response_model=LicenseText)
async def get_license_text(license: str):
    if not SPDX_ID_RE.match(license):
        return LicenseText(text=None)
    cache_key = f"license_text:{license}"
    if (cached := _cache_get(cache_key)) is not None:
        return cached
    async with httpx.AsyncClient() as client:
        spdx_map = await _get_spdx_to_key_map(client)
        license_key = spdx_map.get(license)
        if license_key is None:
            return LicenseText(text=None)
        url = f"https://scancode-licensedb.aboutcode.org/{license_key}.LICENSE"
        try:
            r = await client.get(url)
        except httpx.RequestError:
            return LicenseText(text=None)
    if r.status_code != 200:
        return LicenseText(text=None)
    result = LicenseText(text=r.text)
    _cache_set(cache_key, result, CACHE_TTL["license_text"])
    return result


@app.get("/dependency-graph")
def get_dependency_graph() -> dict:
    if not SCAN_RESULT_PATH.exists():
        raise HTTPException(
            status_code=404, detail=f"scan-result.yml not found at {SCAN_RESULT_PATH}"
        )
    with SCAN_RESULT_PATH.open() as f:
        data = yaml.safe_load(f)
    return data["analyzer"]["result"].get("dependency_graphs", {})


@app.get("/scan-result", response_model=OrtResult)
def get_scan_result():
    if not SCAN_RESULT_PATH.exists():
        raise HTTPException(
            status_code=404, detail=f"scan-result.yml not found at {SCAN_RESULT_PATH}"
        )

    with SCAN_RESULT_PATH.open() as f:
        data = yaml.safe_load(f)

    repo_raw = data["repository"]
    repository = Repository(
        vcs=parse_vcs(repo_raw.get("vcs", {})),
        vcs_processed=parse_vcs(repo_raw.get("vcs_processed", {})),
    )

    analyzer_result = data["analyzer"]["result"]

    projects = [
        Project(
            id=p["id"],
            definition_file_path=p.get("definition_file_path", ""),
            declared_licenses=p.get("declared_licenses", []),
            declared_licenses_processed=DeclaredLicensesProcessed(
                spdx_expression=p.get("declared_licenses_processed", {}).get(
                    "spdx_expression", ""
                )
            ),
            scope_names=p.get("scope_names", []),
            homepage_url=p.get("homepage_url", ""),
        )
        for p in analyzer_result.get("projects", [])
    ]

    packages = [
        Package(
            id=pkg["id"],
            purl=pkg.get("purl", ""),
            authors=pkg.get("authors", []),
            declared_licenses=pkg.get("declared_licenses", []),
            declared_licenses_processed=DeclaredLicensesProcessed(
                spdx_expression=pkg.get("declared_licenses_processed", {}).get(
                    "spdx_expression", ""
                )
            ),
            description=pkg.get("description", ""),
            homepage_url=pkg.get("homepage_url", ""),
            vcs_url=pkg.get("vcs_processed", {}).get("url", "")
            or pkg.get("vcs", {}).get("url", ""),
        )
        for pkg in analyzer_result.get("packages", [])
    ]

    scanner_data = data.get("scanner", {})

    provenance_map: dict[tuple[str, str], list[str]] = {}
    for prov in scanner_data.get("provenances", []):
        pkg_id = prov.get("id", "")
        pkg_prov = prov.get("package_provenance", {})
        vcs = pkg_prov.get("vcs_info", {})
        url = vcs.get("url", "")
        revision = pkg_prov.get("resolved_revision", "") or vcs.get("revision", "")
        if url and revision:
            provenance_map.setdefault((url, revision), []).append(pkg_id)
        else:
            artifact_url = pkg_prov.get("source_artifact", {}).get("url", "")
            if artifact_url:
                provenance_map.setdefault(("artifact", artifact_url), []).append(pkg_id)

    id_to_pkg = {p.id: p for p in packages}
    for pkg_ids in provenance_map.values():
        if len(pkg_ids) > 1:
            for pid in pkg_ids:
                if pid in id_to_pkg:
                    id_to_pkg[pid].vcs_siblings = [i for i in pkg_ids if i != pid]

    scan_results = []
    for sr in scanner_data.get("scan_results", []):
        prov = sr["provenance"]
        vcs_url = prov.get("vcs_info", {}).get("url", "")
        revision = prov.get("resolved_revision", "")
        artifact_url = prov.get("source_artifact", {}).get("url", "")
        pkg_ids = (
            provenance_map.get((vcs_url, revision))
            or provenance_map.get(("artifact", artifact_url))
            or []
        )
        findings = [
            LicenseFinding(
                license=lf["license"],
                location=LicenseLocation(
                    path=lf["location"]["path"],
                    start_line=lf["location"]["start_line"],
                    end_line=lf["location"]["end_line"],
                ),
                score=lf.get("score", 0.0),
            )
            for lf in sr.get("summary", {}).get("licenses", [])
        ]
        provenance_dict = {
            "vcs_info": prov.get("vcs_info", {}),
            "resolved_revision": prov.get("resolved_revision", ""),
        }
        for pid in pkg_ids:
            scan_results.append(
                PackageScanResult(
                    package_id=pid,
                    provenance=provenance_dict,
                    licenses=findings,
                )
            )

    return OrtResult(
        repository=repository,
        projects=projects,
        packages=packages,
        scan_results=scan_results,
    )


@app.get("/path-excludes", response_model=PackagePathExcludes)
def get_path_excludes(package_id: str):
    configs = _read_pkg_configs()
    entry = next((c for c in configs if c.get("id") == package_id), None)
    if entry is None:
        return PackagePathExcludes(package_id=package_id, path_excludes=[])
    excludes = [
        PathExclude(
            pattern=e.get("pattern", ""),
            reason=e.get("reason", ""),
            comment=e.get("comment", ""),
        )
        for e in entry.get("path_excludes") or []
    ]
    return PackagePathExcludes(package_id=package_id, path_excludes=excludes)


@app.put("/path-excludes", response_model=PackagePathExcludes)
def add_path_exclude(req: AddPathExcludeRequest):
    configs = _read_pkg_configs()
    entry = next((c for c in configs if c.get("id") == req.package_id), None)
    if entry is None:
        entry = {"id": req.package_id, "path_excludes": []}
        configs.append(entry)
    excludes: list[dict] = entry.setdefault("path_excludes", [])
    if not any(e.get("pattern") == req.pattern for e in excludes):
        excludes.append({"pattern": req.pattern, "reason": req.reason, "comment": req.comment})
    _write_pkg_configs(configs)
    return PackagePathExcludes(
        package_id=req.package_id,
        path_excludes=[PathExclude(**e) for e in excludes],
    )


@app.delete("/path-excludes", response_model=PackagePathExcludes)
def remove_path_exclude(package_id: str, pattern: str):
    configs = _read_pkg_configs()
    entry = next((c for c in configs if c.get("id") == package_id), None)
    if entry is None:
        return PackagePathExcludes(package_id=package_id, path_excludes=[])
    entry["path_excludes"] = [
        e for e in entry.get("path_excludes") or [] if e.get("pattern") != pattern
    ]
    _write_pkg_configs(configs)
    return PackagePathExcludes(
        package_id=package_id,
        path_excludes=[PathExclude(**e) for e in entry["path_excludes"]],
    )


@app.get("/license-curations", response_model=PackageCuration)
def get_license_curation(package_id: str):
    curations = _read_curations()
    entry = next((c for c in curations if c.get("id") == package_id), None)
    if entry is None:
        return PackageCuration(package_id=package_id)
    cur = entry.get("curations") or {}
    return PackageCuration(
        package_id=package_id,
        comment=cur.get("comment", ""),
        concluded_license=cur.get("concluded_license"),
    )


@app.put("/license-curations", response_model=PackageCuration)
def set_license_curation(req: SetCurationRequest):
    curations = _read_curations()
    entry = next((c for c in curations if c.get("id") == req.package_id), None)
    if entry is None:
        entry = {"id": req.package_id, "curations": {}}
        curations.append(entry)
    entry["curations"] = {"comment": req.comment, "concluded_license": req.concluded_license}
    _write_curations(curations)
    return PackageCuration(
        package_id=req.package_id,
        comment=req.comment,
        concluded_license=req.concluded_license,
    )


@app.delete("/license-curations", response_model=PackageCuration)
def remove_license_curation(package_id: str):
    curations = _read_curations()
    curations = [c for c in curations if c.get("id") != package_id]
    _write_curations(curations)
    return PackageCuration(package_id=package_id)
