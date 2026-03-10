from pathlib import Path

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

SCAN_RESULT_PATH = Path(__file__).parent.parent / "ort-out" / "scan-result.yml"


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


def parse_vcs(raw: dict) -> VcsInfo:
    return VcsInfo(
        type=raw.get("type", ""),
        url=raw.get("url", ""),
        revision=raw.get("revision", ""),
        path=raw.get("path", ""),
    )


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
        )
        for pkg in analyzer_result.get("packages", [])
    ]

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
