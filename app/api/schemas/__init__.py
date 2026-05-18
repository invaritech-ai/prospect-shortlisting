"""API schema modules."""

from app.api.schemas.scrape import (
    LetterCountsResponse,
    ScrapeBatchCreate,
    ScrapeBatchList,
    ScrapeBatchRead,
    ScrapeResultRead,
    ScrapeSettingsCreate,
    ScrapeSettingsRead,
)
from app.api.schemas.analysis import AnalysisJobDetailRead, AnalysisPipelineJobRead
from app.api.schemas.prompt import PromptCreate, PromptRead, PromptUpdate
from app.api.schemas.upload import (
    DomainList,
    DomainRead,
    UploadCreateResult,
    UploadList,
    UploadRead,
)

__all__ = [
    "LetterCountsResponse",
    "ScrapeBatchCreate",
    "ScrapeBatchList",
    "ScrapeBatchRead",
    "ScrapeResultRead",
    "ScrapeSettingsCreate",
    "ScrapeSettingsRead",
    "PromptCreate",
    "PromptRead",
    "PromptUpdate",
    "AnalysisPipelineJobRead",
    "AnalysisJobDetailRead",
    "DomainList",
    "DomainRead",
    "UploadList",
    "UploadRead",
    "UploadCreateResult",
]
