from typing import Any, Literal

from pydantic import BaseModel, Field


class ExtractParams(BaseModel):
    url: str
    download: bool = False
    index: list[str | int] | None = None
    cookie: str | None = None
    proxy: str | None = None
    skip: bool = False


class ExtractData(BaseModel):
    message: str
    params: ExtractParams
    data: dict | None


class DownloadShareParams(BaseModel):
    url: str = Field(description="小红书作品链接或短链接，必填")
    index: list[str | int] | None = Field(
        default=None,
        description="仅下载图文作品中的指定图片序号，例如 [1, 3, 5]",
    )
    cookie: str | None = Field(
        default=None,
        description="请求时使用的 Cookie（需包含 a1），未传时使用程序配置中的 Cookie",
    )
    proxy: str | None = Field(
        default=None,
        description="请求代理，可选，支持 http(s)/socks5",
    )
    skip: bool = Field(
        default=False,
        description="是否跳过已存在下载记录的作品",
    )


class BatchDownloadParams(BaseModel):
    profile_url: str = Field(
        description="发布者主页链接或 xhslink 手机分享短链接，必填",
    )
    cookie: str | None = Field(
        default=None,
        description="请求时使用的 Cookie（需包含 a1），未传时使用程序配置中的 Cookie",
    )
    proxy: str | None = Field(
        default=None,
        description="请求代理，可选，支持 http(s)/socks5",
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        description="最多处理的作品数量，默认不限制",
    )


class DownloadStatistics(BaseModel):
    all: int = 0
    success: int = 0
    fail: int = 0
    skip: int = 0
    filtered: int = 0


class DownloadShareResponse(BaseModel):
    message: str
    params: DownloadShareParams
    data: dict | None
    stats: DownloadStatistics


class TaskAcceptedResponse(BaseModel):
    message: str
    task_id: str
    status_url: str


class TaskStatusResponse(BaseModel):
    task_id: str
    mode: str
    status: Literal["pending", "running", "completed", "failed"]
    started_at: str
    finished_at: str | None = None
    progress: DownloadStatistics
    summary: DownloadStatistics
    errors: list[str] = Field(default_factory=list)


class SQLiteDataResponse(BaseModel):
    message: str
    data: dict[str, list[dict[str, Any]]]
