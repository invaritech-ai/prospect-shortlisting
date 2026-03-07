"""API schema modules."""

from app.api.schemas.scrape import (
    JobEnqueueResult,
    JobActionResult,
    ScrapeJobCreate,
    ScrapeJobRead,
    ScrapePageContentRead,
    ScrapePageRead,
)
from app.api.schemas.analysis import AnalysisJobDetailRead, AnalysisRunJobRead
from app.api.schemas.prompt import PromptCreate, PromptRead, PromptUpdate
from app.api.schemas.run import RunCreateRequest, RunCreateResult, RunRead
from app.api.schemas.upload import (
    CompanyList,
    CompanyDeleteRequest,
    CompanyDeleteResult,
    CompanyListItem,
    CompanyRead,
    CompanyScrapeRequest,
    CompanyScrapeResult,
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
    "PromptCreate",
    "PromptRead",
    "PromptUpdate",
    "AnalysisRunJobRead",
    "AnalysisJobDetailRead",
    "RunCreateRequest",
    "RunCreateResult",
    "RunRead",
    "UploadValidationError",
    "CompanyRead",
    "CompanyListItem",
    "CompanyList",
    "CompanyDeleteRequest",
    "CompanyDeleteResult",
    "CompanyScrapeRequest",
    "CompanyScrapeResult",
    "UploadCompanyList",
    "UploadList",
    "UploadRead",
    "UploadCreateResult",
    "UploadDetail",
]
