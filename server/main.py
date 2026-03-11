import re
import urllib.parse
from pathlib import Path

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


class LicenseLocation(BaseModel):
    path: str
    start_line: int
    end_line: int


class LicenseFinding(BaseModel):
    license: str
    location: LicenseLocation
    score: float


class PackageScanResult(BaseModel):
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


class DownloadStats(BaseModel):
    weekly_downloads: int | None


@app.get("/downloads", response_model=DownloadStats)
async def get_downloads(purl: str):
    async with httpx.AsyncClient() as client:
        if purl.startswith("pkg:npm/"):
            name = urllib.parse.unquote(purl.removeprefix("pkg:npm/").rsplit("@", 1)[0])
            r = await client.get(f"https://api.npmjs.org/downloads/point/last-week/{name}")
            if r.status_code != 200:
                return DownloadStats(weekly_downloads=None)
            return DownloadStats(weekly_downloads=r.json()["downloads"])

        elif purl.startswith("pkg:pypi/"):
            name = urllib.parse.unquote(purl.removeprefix("pkg:pypi/").split("@")[0])
            r = await client.get(f"https://pypistats.org/api/packages/{name}/recent")
            if r.status_code != 200:
                return DownloadStats(weekly_downloads=None)
            return DownloadStats(weekly_downloads=r.json()["data"]["last_week"])

        return DownloadStats(weekly_downloads=None)


class GitHubStars(BaseModel):
    stars: int | None


@app.get("/github-stars", response_model=GitHubStars)
async def get_github_stars(url: str):
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    if not m:
        return GitHubStars(stars=None)
    owner, repo = m.group(1), m.group(2)
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers={"Accept": "application/vnd.github+json"},
        )
        if r.status_code != 200:
            return GitHubStars(stars=None)
        return GitHubStars(stars=r.json()["stargazers_count"])


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
    scan_results = [
        PackageScanResult(
            provenance={
                "vcs_info": sr["provenance"].get("vcs_info", {}),
                "resolved_revision": sr["provenance"].get("resolved_revision", ""),
            },
            licenses=[
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
            ],
        )
        for sr in scanner_data.get("scan_results", [])
    ]

    return OrtResult(
        repository=repository,
        projects=projects,
        packages=packages,
        scan_results=scan_results,
    )
