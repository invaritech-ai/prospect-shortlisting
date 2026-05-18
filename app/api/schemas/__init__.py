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
    "DomainList",
    "DomainRead",
    "UploadList",
    "UploadRead",
    "UploadCreateResult",
]
