"""API schema modules."""

from app.api.schemas.scrape import (
    LetterCountsResponse,
    ScrapeBatchCreate,
    ScrapeBatchList,
    ScrapeBatchRead,
    ScrapeJobStatusRead,
    ScrapeResultRead,
    ScrapeSettingsCreate,
    ScrapeSettingsRead,
)
from app.api.schemas.analysis import (
    AiReviewDomainAnalysis,
    AiReviewDomainList,
    AiReviewDomainRow,
    AiReviewLabelCounts,
)
from app.api.schemas.upload import (
    DomainList,
    DomainRead,
    UploadCreateResult,
    UploadList,
    UploadRead,
)

__all__ = [
    "AiReviewDomainList",
    "AiReviewDomainAnalysis",
    "AiReviewDomainRow",
    "AiReviewLabelCounts",
    "LetterCountsResponse",
    "ScrapeBatchCreate",
    "ScrapeBatchList",
    "ScrapeBatchRead",
    "ScrapeJobStatusRead",
    "ScrapeResultRead",
    "ScrapeSettingsCreate",
    "ScrapeSettingsRead",
    "DomainList",
    "DomainRead",
    "UploadList",
    "UploadRead",
    "UploadCreateResult",
]
