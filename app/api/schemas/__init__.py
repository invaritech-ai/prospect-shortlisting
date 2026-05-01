"""API schema modules."""

from app.api.schemas.scrape import (
    JobActionResult,
    JobEnqueueResult,
    ScrapeJobCreate,
    ScrapeJobRead,
    ScrapeRunRead,
    ScrapePageContentRead,
    ScrapePageRead,
)
from app.api.schemas.analysis import AnalysisJobDetailRead, AnalysisPipelineJobRead
from app.api.schemas.prompt import PromptCreate, PromptRead, PromptUpdate
from app.api.schemas.scrape_prompt import ScrapePromptCreate, ScrapePromptRead, ScrapePromptUpdate
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
    "ScrapeRunRead",
    "PromptCreate",
    "PromptRead",
    "PromptUpdate",
    "ScrapePromptCreate",
    "ScrapePromptRead",
    "ScrapePromptUpdate",
    "AnalysisPipelineJobRead",
    "AnalysisJobDetailRead",
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
