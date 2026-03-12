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
    allow_methods=["GET"],
    allow_headers=["*"],
)

SCAN_RESULT_PATH = Path(__file__).parent / "ort-out" / "scan-result.yml"
ORT_OUT_PATH = Path(__file__).parent / "ort-out"

CACHE_TTL: dict[str, float] = {
    "github_stars":   3600,   # 1 hour
    "npm_downloads":  86400,  # 24 hours
    "pypi_downloads": 86400,  # 24 hours
}

CACHE_BACKEND: str = os.environ.get("CACHE_BACKEND", "memory")  # "memory" | "disk"
CACHE_FILE: Path = Path(os.environ.get("CACHE_FILE", str(Path(__file__).parent / "cache.json")))

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
    dependency_count: int = 0


class Package(BaseModel):
    id: str
    purl: str = ""
    authors: list[str] = []
    declared_licenses: list[str] = []
    declared_licenses_processed: DeclaredLicensesProcessed = DeclaredLicensesProcessed()
    description: str = ""
    homepage_url: str = ""
    vcs_url: str = ""
    dependency_count: int = 0
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


def compute_dependency_counts(
    analyzer_result: dict,
) -> tuple[dict[str, int], dict[str, int]]:
    project_dep_counts: dict[str, int] = {}
    package_dep_counts: dict[str, int] = {}

    dependency_graphs = analyzer_result.get("dependency_graphs", {})
    projects_raw = analyzer_result.get("projects", [])
    packages_raw = analyzer_result.get("packages", [])

    for _pm, graph in dependency_graphs.items():
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        scopes = graph.get("scopes", {})
        packages_list = graph.get("packages", [])

        # node index → package-list index
        node_to_pkg: dict[int, int] = {i: nodes[i].get("pkg") for i in range(len(nodes)) if "pkg" in nodes[i]}

        # node index → child node indices
        adjacency: dict[int, list[int]] = {}
        for edge in edges:
            src = edge.get("from")
            dst = edge.get("to")
            if src is not None and dst is not None:
                adjacency.setdefault(src, []).append(dst)

        # package-list index → package id
        pkg_index_to_id: dict[int, str] = {i: packages_list[i] for i in range(len(packages_list))}

        # package id → node index (for counting outgoing edges)
        pkg_id_to_node: dict[str, int] = {}
        for node_idx, pkg_idx in node_to_pkg.items():
            pkg_id = pkg_index_to_id.get(pkg_idx)
            if pkg_id is not None:
                pkg_id_to_node[pkg_id] = node_idx

        # Project counts: BFS from each scope root
        project_id_suffix_map: dict[str, str] = {}
        for proj in projects_raw:
            proj_id = proj["id"]
            # id format: Type:Namespace:Name:Version
            suffix = ":".join(proj_id.split(":")[2:])  # Name:Version
            project_id_suffix_map[suffix] = proj_id

        for scope_key, scope_entry in scopes.items():
            # scope_key format: <name>:<version>:<scope-name>
            # project suffix = <name>:<version>
            parts = scope_key.rsplit(":", 1)
            proj_suffix = parts[0] if len(parts) == 2 else scope_key

            proj_id = project_id_suffix_map.get(proj_suffix)
            if proj_id is None:
                continue

            root = scope_entry.get("root")
            if root is None:
                continue

            # BFS to collect unique package indices
            visited_nodes: set[int] = set()
            queue = [root]
            pkg_indices: set[int] = set()
            while queue:
                node = queue.pop()
                if node in visited_nodes:
                    continue
                visited_nodes.add(node)
                pkg_idx = node_to_pkg.get(node)
                if pkg_idx is not None:
                    pkg_indices.add(pkg_idx)
                for child in adjacency.get(node, []):
                    if child not in visited_nodes:
                        queue.append(child)

            project_dep_counts[proj_id] = project_dep_counts.get(proj_id, 0) + len(pkg_indices)

        # Package counts: direct children in adjacency
        for pkg in packages_raw:
            pkg_id = pkg["id"]
            node_idx = pkg_id_to_node.get(pkg_id)
            if node_idx is not None:
                package_dep_counts[pkg_id] = len(adjacency.get(node_idx, []))
            else:
                package_dep_counts.setdefault(pkg_id, 0)

    return project_dep_counts, package_dep_counts


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


class FileContentLine(BaseModel):
    number: int
    content: str
    highlighted: bool


class FileContent(BaseModel):
    lines: list[FileContentLine] | None


@app.get("/file-content", response_model=FileContent)
def get_file_content(package_id: str, path: str, start_line: int, end_line: int, context: int = 5):
    pkg_dir = pkg_id_to_dir(package_id)
    if pkg_dir is None:
        return FileContent(lines=None)
    file_path = pkg_dir / path
    if not file_path.is_file():
        return FileContent(lines=None)
    all_lines = file_path.read_text(errors="replace").splitlines()
    fetch_start = max(0, start_line - 1 - context)
    fetch_end = min(len(all_lines), end_line + context)
    lines = [
        FileContentLine(
            number=i + 1,
            content=all_lines[i],
            highlighted=(start_line <= i + 1 <= end_line),
        )
        for i in range(fetch_start, fetch_end)
    ]
    return FileContent(lines=lines)


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
            r = await client.get(f"https://api.npmjs.org/downloads/point/last-week/{name}")
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


@app.get("/scan-result", response_model=OrtResult)
def get_scan_result():
    if not SCAN_RESULT_PATH.exists():
        raise HTTPException(status_code=404, detail=f"scan-result.yml not found at {SCAN_RESULT_PATH}")

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
                spdx_expression=p.get("declared_licenses_processed", {}).get("spdx_expression", "")
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
                spdx_expression=pkg.get("declared_licenses_processed", {}).get("spdx_expression", "")
            ),
            description=pkg.get("description", ""),
            homepage_url=pkg.get("homepage_url", ""),
            vcs_url=pkg.get("vcs_processed", {}).get("url", "") or pkg.get("vcs", {}).get("url", ""),
        )
        for pkg in analyzer_result.get("packages", [])
    ]

    project_dep_counts, package_dep_counts = compute_dependency_counts(analyzer_result)
    for proj in projects:
        proj.dependency_count = project_dep_counts.get(proj.id, 0)
    for pkg in packages:
        pkg.dependency_count = package_dep_counts.get(pkg.id, 0)

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
            scan_results.append(PackageScanResult(
                package_id=pid,
                provenance=provenance_dict,
                licenses=findings,
            ))

    return OrtResult(
        repository=repository,
        projects=projects,
        packages=packages,
        scan_results=scan_results,
    )
