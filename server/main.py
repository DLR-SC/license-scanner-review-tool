# SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
#
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import os
import re
import time
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("uvicorn")


def _unique_id(route: APIRoute) -> str:
    return route.name


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_scan_data()
    yield


app = FastAPI(lifespan=lifespan, generate_unique_id_function=_unique_id)
api_router = APIRouter()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "PUT", "DELETE"],
    allow_headers=["*"],
)

ORT_OUT_PATH = Path(os.environ.get("ORT_OUT_PATH", Path(__file__).parent / "ort-out"))
SCAN_RESULT_PATH = ORT_OUT_PATH / "scan-result.yml"
PKG_CONFIG_PATH = ORT_OUT_PATH / "package-configurations.yml"
CURATIONS_PATH = ORT_OUT_PATH / "curations.yml"

_scan_data: dict | None = None

_pkg_vcs_path: dict[str, str] = {}
_pkg_siblings: dict[str, list[str]] = {}


def _load_vcs_sibling_data() -> None:
    global _pkg_vcs_path, _pkg_siblings
    _pkg_vcs_path = {}
    _pkg_siblings = {}
    if _scan_data is None:
        return
    for pkg in _scan_data.get("analyzer", {}).get("result", {}).get("packages", []):
        pid = pkg.get("id", "")
        vp = pkg.get("vcs_processed", {}).get("path", "") or pkg.get("vcs", {}).get(
            "path", ""
        )
        _pkg_vcs_path[pid] = vp
    provenance_map: dict[tuple[str, str], list[str]] = {}
    for prov in _scan_data.get("scanner", {}).get("provenances", []):
        pid = prov.get("id", "")
        pkg_prov = prov.get("package_provenance", {})
        vcs = pkg_prov.get("vcs_info", {})
        url = vcs.get("url", "")
        revision = pkg_prov.get("resolved_revision", "") or vcs.get("revision", "")
        if url and revision:
            provenance_map.setdefault((url, revision), []).append(pid)
    for pkg_ids in provenance_map.values():
        if len(pkg_ids) > 1:
            for pid in pkg_ids:
                _pkg_siblings[pid] = [i for i in pkg_ids if i != pid]


def _load_scan_data() -> None:
    global _scan_data
    _scan_data = None
    if SCAN_RESULT_PATH.exists():
        logger.info("Loading scan data from %s", SCAN_RESULT_PATH)
        with SCAN_RESULT_PATH.open() as f:
            _scan_data = yaml.safe_load(f)
        logger.info("Scan data loaded")
    else:
        logger.warning("Scan result file not found: %s", SCAN_RESULT_PATH)
    _load_vcs_sibling_data()


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
    encoded_namespace = urllib.parse.quote(namespace, safe="")
    return ORT_OUT_PATH / type_ / encoded_namespace / name / version


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


class LicenseFindingCuration(BaseModel):
    path: str
    start_lines: str
    line_count: int
    detected_license: str
    reason: str = ""
    comment: str = ""
    concluded_license: str


class PackageFindingCurations(BaseModel):
    package_id: str
    license_finding_curations: list[LicenseFindingCuration]


class SetFindingCurationRequest(BaseModel):
    package_id: str
    path: str
    start_lines: str
    line_count: int
    detected_license: str
    reason: str = ""
    comment: str = ""
    concluded_license: str


class FileContentLine(BaseModel):
    number: int
    content: str
    highlighted: bool


class FileContent(BaseModel):
    lines: list[FileContentLine] | None
    total_lines: int = 0


def _resolve_file_via_vcs_sibling(package_id: str, path: str) -> Path | None:
    # For packages with VCS siblings (monorepos), a file referenced in a license
    # finding may be stored under a sibling package's ORT output directory rather than the
    # current package's directory.
    # This happens because the ORT download command accounts for the VCS path of the package,
    # while the scanner scans the complete repository.
    # We assume that the files are downloaded via ORT's download command
    # because it is more reliable than extracting the files from the scanner step.
    current_vcs_path = _pkg_vcs_path.get(package_id, "")
    if not current_vcs_path or path.startswith(current_vcs_path):
        return None
    best_sibling: str | None = None
    best_len = -1
    for sibling_id in _pkg_siblings.get(package_id, []):
        sibling_vcs_path = _pkg_vcs_path.get(sibling_id, "")
        if path.startswith(sibling_vcs_path) and len(sibling_vcs_path) > best_len:
            best_sibling = sibling_id
            best_len = len(sibling_vcs_path)
    if best_sibling is None:
        return None
    sibling_dir = pkg_id_to_dir(best_sibling)
    if sibling_dir is None:
        return None
    candidate = sibling_dir / path
    return candidate if candidate.is_file() else None


@api_router.get("/file-content", response_model=FileContent)
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
        file_path = _resolve_file_via_vcs_sibling(package_id, path) or file_path
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


@api_router.get("/downloads", response_model=DownloadStats)
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
                logger.error("Failed to fetch npm downloads for %s: %s", name, r.text)
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
                logger.error("Failed to fetch PyPI downloads for %s: %s", name, r.text)
                return DownloadStats(weekly_downloads=None)
            result = DownloadStats(weekly_downloads=r.json()["data"]["last_week"])
            _cache_set(cache_key, result, CACHE_TTL["pypi_downloads"])
            return result

        return DownloadStats(weekly_downloads=None)


class GitHubStars(BaseModel):
    stars: int | None


@api_router.get("/github-stars", response_model=GitHubStars)
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


@api_router.get("/license-text", response_model=LicenseText)
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


class DependencyGraphNode(BaseModel):
    pkg: int = 0
    fragment: int | None = None


class DependencyGraphEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    from_: int = Field(0, alias="from")
    to: int = 0


class DependencyGraphScopeEntry(BaseModel):
    root: int
    fragment: int | None = None


class DependencyGraph(BaseModel):
    packages: list[str] = []
    nodes: list[DependencyGraphNode] = []
    edges: list[DependencyGraphEdge] = []
    scopes: dict[str, list[DependencyGraphScopeEntry]] = {}


@api_router.get("/dependency-graph")
def get_dependency_graph() -> dict[str, DependencyGraph]:
    if _scan_data is None:
        raise HTTPException(
            status_code=404, detail=f"scan-result.yml not found at {SCAN_RESULT_PATH}"
        )
    raw = _scan_data["analyzer"]["result"].get("dependency_graphs", {})
    return {k: DependencyGraph.model_validate(v) for k, v in raw.items()}


@api_router.get("/scan-result", response_model=OrtResult)
def get_scan_result():
    if _scan_data is None:
        raise HTTPException(
            status_code=404, detail=f"scan-result.yml not found at {SCAN_RESULT_PATH}"
        )

    data = _scan_data
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


@api_router.get("/path-excludes", response_model=PackagePathExcludes)
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


def _upsert_path_exclude(configs: list[dict], package_id: str, exclude: dict) -> dict:
    entry = next((c for c in configs if c.get("id") == package_id), None)
    if entry is None:
        entry = {"id": package_id, "path_excludes": []}
        configs.append(entry)
    excludes: list[dict] = entry.setdefault("path_excludes", [])
    if not any(e.get("pattern") == exclude["pattern"] for e in excludes):
        excludes.append(exclude)
    return entry


def _delete_path_exclude(
    configs: list[dict], package_id: str, pattern: str
) -> dict | None:
    entry = next((c for c in configs if c.get("id") == package_id), None)
    if entry is None:
        return None
    entry["path_excludes"] = [
        e for e in entry.get("path_excludes") or [] if e.get("pattern") != pattern
    ]
    return entry


@api_router.put("/path-excludes", response_model=PackagePathExcludes)
def add_path_exclude(req: AddPathExcludeRequest):
    configs = _read_pkg_configs()
    exclude = {"pattern": req.pattern, "reason": req.reason, "comment": req.comment}
    entry = _upsert_path_exclude(configs, req.package_id, exclude)
    for sibling_id in _pkg_siblings.get(req.package_id, []):
        _upsert_path_exclude(configs, sibling_id, exclude.copy())
    _write_pkg_configs(configs)
    return PackagePathExcludes(
        package_id=req.package_id,
        path_excludes=[PathExclude(**e) for e in entry["path_excludes"]],
    )


@api_router.delete("/path-excludes", response_model=PackagePathExcludes)
def remove_path_exclude(package_id: str, pattern: str):
    configs = _read_pkg_configs()
    entry = _delete_path_exclude(configs, package_id, pattern)
    if entry is None:
        return PackagePathExcludes(package_id=package_id, path_excludes=[])
    for sibling_id in _pkg_siblings.get(package_id, []):
        _delete_path_exclude(configs, sibling_id, pattern)
    _write_pkg_configs(configs)
    return PackagePathExcludes(
        package_id=package_id,
        path_excludes=[PathExclude(**e) for e in entry["path_excludes"]],
    )


@api_router.get("/license-curations", response_model=PackageCuration)
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


@api_router.put("/license-curations", response_model=PackageCuration)
def set_license_curation(req: SetCurationRequest):
    curations = _read_curations()
    entry = next((c for c in curations if c.get("id") == req.package_id), None)
    if entry is None:
        entry = {"id": req.package_id, "curations": {}}
        curations.append(entry)
    entry["curations"] = {
        "comment": req.comment,
        "concluded_license": req.concluded_license,
    }
    _write_curations(curations)
    return PackageCuration(
        package_id=req.package_id,
        comment=req.comment,
        concluded_license=req.concluded_license,
    )


@api_router.delete("/license-curations", response_model=PackageCuration)
def remove_license_curation(package_id: str):
    curations = _read_curations()
    curations = [c for c in curations if c.get("id") != package_id]
    _write_curations(curations)
    return PackageCuration(package_id=package_id)


@api_router.get("/license-curations/all", response_model=list[PackageCuration])
def get_all_license_curations():
    curations = _read_curations()
    return [
        PackageCuration(
            package_id=c["id"],
            comment=c.get("curations", {}).get("comment", ""),
            concluded_license=c.get("curations", {}).get("concluded_license"),
        )
        for c in curations
    ]


def _parse_finding_curations(entry: dict) -> list[LicenseFindingCuration]:
    return [
        LicenseFindingCuration(
            path=c.get("path", ""),
            start_lines=str(c.get("start_lines", "")),
            line_count=int(c.get("line_count", 0)),
            detected_license=c.get("detected_license", ""),
            reason=c.get("reason", ""),
            comment=c.get("comment", ""),
            concluded_license=c.get("concluded_license", ""),
        )
        for c in entry.get("license_finding_curations") or []
    ]


@api_router.get("/finding-curations", response_model=PackageFindingCurations)
def get_finding_curations(package_id: str):
    configs = _read_pkg_configs()
    entry = next((c for c in configs if c.get("id") == package_id), None)
    if entry is None:
        return PackageFindingCurations(
            package_id=package_id, license_finding_curations=[]
        )
    return PackageFindingCurations(
        package_id=package_id,
        license_finding_curations=_parse_finding_curations(entry),
    )


def _upsert_finding_curation(
    configs: list[dict], package_id: str, finding: dict
) -> dict:
    entry = next((c for c in configs if c.get("id") == package_id), None)
    if entry is None:
        entry = {"id": package_id}
        configs.append(entry)
    curations: list[dict] = entry.setdefault("license_finding_curations", [])
    existing = next(
        (
            c
            for c in curations
            if c.get("path") == finding["path"]
            and str(c.get("start_lines", "")) == finding["start_lines"]
            and c.get("detected_license") == finding["detected_license"]
        ),
        None,
    )
    if existing is not None:
        existing.update(finding)
    else:
        curations.append(finding)
    return entry


def _delete_finding_curation(
    configs: list[dict],
    package_id: str,
    path: str,
    start_lines: str,
    detected_license: str,
) -> dict | None:
    entry = next((c for c in configs if c.get("id") == package_id), None)
    if entry is None:
        return None
    entry["license_finding_curations"] = [
        c
        for c in entry.get("license_finding_curations") or []
        if not (
            c.get("path") == path
            and str(c.get("start_lines", "")) == start_lines
            and c.get("detected_license") == detected_license
        )
    ]
    return entry


@api_router.put("/finding-curations", response_model=PackageFindingCurations)
def set_finding_curation(req: SetFindingCurationRequest):
    configs = _read_pkg_configs()
    finding = {
        "path": req.path,
        "start_lines": req.start_lines,
        "line_count": req.line_count,
        "detected_license": req.detected_license,
        "reason": req.reason,
        "comment": req.comment,
        "concluded_license": req.concluded_license,
    }
    entry = _upsert_finding_curation(configs, req.package_id, finding)
    for sibling_id in _pkg_siblings.get(req.package_id, []):
        _upsert_finding_curation(configs, sibling_id, finding.copy())
    _write_pkg_configs(configs)
    return PackageFindingCurations(
        package_id=req.package_id,
        license_finding_curations=_parse_finding_curations(entry),
    )


@api_router.delete("/finding-curations", response_model=PackageFindingCurations)
def remove_finding_curation(
    package_id: str, path: str, start_lines: str, detected_license: str
):
    configs = _read_pkg_configs()
    entry = _delete_finding_curation(
        configs, package_id, path, start_lines, detected_license
    )
    if entry is None:
        return PackageFindingCurations(
            package_id=package_id, license_finding_curations=[]
        )
    for sibling_id in _pkg_siblings.get(package_id, []):
        _delete_finding_curation(
            configs, sibling_id, path, start_lines, detected_license
        )
    _write_pkg_configs(configs)
    return PackageFindingCurations(
        package_id=package_id,
        license_finding_curations=_parse_finding_curations(entry),
    )


app.include_router(api_router, prefix="/api/v1")


FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", ""))

if FRONTEND_DIST and FRONTEND_DIST.exists():

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _serve_frontend(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
