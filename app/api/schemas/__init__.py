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
    AiReviewJobCreate,
    AiReviewJobRead,
    AiReviewJobStatusRead,
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
    "AiReviewJobCreate",
    "AiReviewJobRead",
    "AiReviewJobStatusRead",
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
