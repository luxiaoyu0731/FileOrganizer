from pydantic import BaseModel, Field
from typing import Optional


class AiConfig(BaseModel):
    base_url: str = Field(..., description="API base URL (any OpenAI-compatible endpoint)")
    api_key: str = Field(..., description="API key")
    model: str = Field(..., description="Model name")


class ScanConfig(BaseModel):
    paths: list[str] = Field(..., description="Directories to scan")
    exclude_patterns: list[str] = Field(
        default=[".DS_Store", "Thumbs.db", "desktop.ini"],
        description="File/dir names to exclude",
    )
    max_size_mb: float = Field(default=500.0, description="Max file size in MB")


class ScanResult(BaseModel):
    path: str
    size_bytes: int
    modified_time: str
    extension: str
    sha256: str


class ClassifyRequest(BaseModel):
    files: list[ScanResult]
    ai_config: AiConfig


class ClassificationResult(BaseModel):
    path: str
    category: str
    subcategory: str
    sub_path: list[str] = []   # multi-level path segments: [L1, L2, L3, ...]
    suggested_name: str
    confidence: float
    reasoning: str
    classification_method: str = "ai"


class ExecuteRequest(BaseModel):
    classifications: list[ClassificationResult]
    archive_root: str
    rename_strategy: str = Field(
        default="semantic_date",
        description="semantic_date | date_prefix | preserve_original",
    )
    ai_config: Optional[AiConfig] = None
    scan_paths: list[str] = Field(default=[], description="Original scan paths for auto-cleanup")


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
