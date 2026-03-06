"""API schema modules."""

from app.api.schemas.scrape import (
    JobEnqueueResult,
    JobActionResult,
    ScrapeJobCreate,
    ScrapeJobRead,
    ScrapePageContentRead,
    ScrapePageRead,
)
from app.api.schemas.upload import (
    CompanyList,
    CompanyDeleteRequest,
    CompanyDeleteResult,
    CompanyListItem,
    CompanyRead,
    UploadCompanyList,
    UploadCreateResult,
    UploadDetail,
    UploadList,
    UploadRead,
    UploadValidationError,
)

__all__ = [
    "ScrapeJobCreate",
    "ScrapeJobRead",
    "ScrapePageRead",
    "ScrapePageContentRead",
    "JobActionResult",
    "JobEnqueueResult",
    "UploadValidationError",
    "CompanyRead",
    "CompanyListItem",
    "CompanyList",
    "CompanyDeleteRequest",
    "CompanyDeleteResult",
    "UploadCompanyList",
    "UploadList",
    "UploadRead",
    "UploadCreateResult",
    "UploadDetail",
]
