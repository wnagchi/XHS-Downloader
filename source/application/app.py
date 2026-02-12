from asyncio import (
    Event,
    Queue,
    QueueEmpty,
    create_task,
    gather,
    sleep,
    Future,
    CancelledError,
)
from contextlib import suppress
from datetime import datetime
from json import dumps
from re import compile
from urllib.parse import urlparse
from textwrap import dedent
from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import RedirectResponse
from fastmcp import FastMCP
from typing import Annotated
from pydantic import Field
from types import SimpleNamespace
from pyperclip import copy, paste
from uvicorn import Config, Server
from typing import Callable

from ..expansion import (
    # BrowserCookie,
    Cleaner,
    Converter,
    Namespace,
    beautify_string,
)
from ..module import (
    BatchDownloadParams,
    DownloadShareParams,
    DownloadShareResponse,
    DownloadStatistics,
    SQLiteDataResponse,
    TaskAcceptedResponse,
    TaskManager,
    TaskStatusResponse,
    __VERSION__,
    ERROR,
    MASTER,
    REPOSITORY,
    ROOT,
    VERSION_BETA,
    VERSION_MAJOR,
    VERSION_MINOR,
    WARNING,
    DataRecorder,
    ExtractData,
    ExtractParams,
    IDRecorder,
    Manager,
    MapRecorder,
    logging,
    # sleep_time,
    ScriptServer,
    INFO,
)
from ..translation import _, switch_language

from ..module import Mapping
from .download import Download
from .explore import Explore
from .image import Image
from .request import Html
from .user_posted import UserPosted
from .video import Video
from rich import print

__all__ = ["XHS"]


def data_cache(function):
    async def inner(
        self,
        data: dict,
    ):
        if self.manager.record_data:
            download = data["下载地址"]
            lives = data["动图地址"]
            local = data.get("本地文件路径", [])
            await function(
                self,
                data,
            )
            data["下载地址"] = download
            data["动图地址"] = lives
            data["本地文件路径"] = local

    return inner


class Print:
    def __init__(
        self,
        func: Callable = print,
    ):
        self.func = func

    def __call__(
        self,
    ):
        return self.func


class XHS:
    VERSION_MAJOR = VERSION_MAJOR
    VERSION_MINOR = VERSION_MINOR
    VERSION_BETA = VERSION_BETA
    LINK = compile(r"(?:https?://)?www\.xiaohongshu\.com/explore/\S+")
    USER = compile(r"(?:https?://)?www\.xiaohongshu\.com/user/profile/[a-z0-9]+/\S+")
    PROFILE = compile(
        r"(?:https?://)?(?:www\.)?xiaohongshu\.com/user/profile/([a-zA-Z0-9]+)"
    )
    SHARE = compile(r"(?:https?://)?www\.xiaohongshu\.com/discovery/item/\S+")
    SHORT = compile(r"(?:https?://)?xhslink\.com/[^\s\"<>\\^`{|}，。；！？、【】《》]+")
    ID = compile(r"(?:explore|item)/(\S+)?\?")
    ID_USER = compile(r"user/profile/[a-z0-9]+/(\S+)?\?")
    SQLITE_FIELD_MAP = {
        "explore_data": {
            "采集时间": "collected_at",
            "作品ID": "note_id",
            "作品类型": "note_type",
            "作品标题": "title",
            "作品描述": "description",
            "作品标签": "tags",
            "发布时间": "published_at",
            "最后更新时间": "updated_at",
            "收藏数量": "favorite_count",
            "评论数量": "comment_count",
            "分享数量": "share_count",
            "点赞数量": "like_count",
            "作者昵称": "author_nickname",
            "作者ID": "author_id",
            "作者链接": "author_url",
            "作品链接": "note_url",
            "下载地址": "download_urls",
            "动图地址": "live_photo_urls",
            "本地文件路径": "local_file_paths",
        },
        "explore_id": {
            "ID": "note_id",
        },
        "mapping_data": {
            "ID": "author_id",
            "NAME": "author_name",
        },
    }
    __INSTANCE = None
    CLEANER = Cleaner()

    def __new__(cls, *args, **kwargs):
        if not cls.__INSTANCE:
            cls.__INSTANCE = super().__new__(cls)
        return cls.__INSTANCE

    def __init__(
        self,
        mapping_data: dict = None,
        work_path="",
        folder_name="Download",
        name_format="发布时间 作者昵称 作品标题",
        user_agent: str = None,
        cookie: str = "",
        proxy: str | dict = None,
        timeout=10,
        chunk=1024 * 1024,
        max_retry=5,
        record_data=False,
        image_format="JPEG",
        image_download=True,
        video_download=True,
        live_download=False,
        video_preference="resolution",
        folder_mode=False,
        download_record=True,
        author_archive=False,
        write_mtime=False,
        language="zh_CN",
        # read_cookie: int | str = None,
        script_server: bool = False,
        script_host="0.0.0.0",
        script_port=5558,
        **kwargs,
    ):
        switch_language(language)
        self.print = Print()
        self.manager = Manager(
            ROOT,
            work_path,
            folder_name,
            name_format,
            chunk,
            user_agent,
            cookie,
            # self.read_browser_cookie(read_cookie) or cookie,
            proxy,
            timeout,
            max_retry,
            record_data,
            image_format,
            image_download,
            video_download,
            live_download,
            video_preference,
            download_record,
            folder_mode,
            author_archive,
            write_mtime,
            script_server,
            self.CLEANER,
            self.print,
        )
        self.mapping_data = mapping_data or {}
        self.map_recorder = MapRecorder(
            self.manager,
        )
        self.mapping = Mapping(self.manager, self.map_recorder)
        self.html = Html(self.manager)
        self.image = Image()
        self.video = Video()
        self.explore = Explore()
        self.convert = Converter()
        self.download = Download(self.manager)
        self.id_recorder = IDRecorder(self.manager)
        self.data_recorder = DataRecorder(self.manager)
        self.task_manager = TaskManager()
        self.clipboard_cache: str = ""
        self.queue = Queue()
        self.event = Event()
        self.script = None
        self.init_script_server(
            script_host,
            script_port,
        )

    def __extract_image(self, container: dict, data: Namespace):
        container["下载地址"], container["动图地址"] = self.image.get_image_link(
            data, self.manager.image_format
        )

    def __extract_video(
        self,
        container: dict,
        data: Namespace,
    ):
        container["下载地址"] = self.video.deal_video_link(
            data,
            self.manager.video_preference,
        )
        container["动图地址"] = [
            None,
        ]

    async def __download_files(
        self,
        container: dict,
        download: bool,
        index,
        count: SimpleNamespace,
    ):
        name = self.__naming_rules(container)
        container["本地文件路径"] = []
        if (u := container["下载地址"]) and download:
            if await self.skip_download(i := container["作品ID"]):
                self.logging(_("作品 {0} 存在下载记录，跳过下载").format(i))
                count.skip += 1
            else:
                __, result, local_paths = await self.download.run(
                    u,
                    container["动图地址"],
                    index,
                    container["作者ID"]
                    + "_"
                    + self.CLEANER.filter_name(container["作者昵称"]),
                    name,
                    container["作品类型"],
                    container["时间戳"],
                )
                container["本地文件路径"] = local_paths
                if not result:
                    count.skip += 1
                elif all(result):
                    count.success += 1
                    await self.__add_record(
                        i,
                    )
                else:
                    count.fail += 1
        elif not u:
            self.logging(_("提取作品文件下载地址失败"), ERROR)
            count.fail += 1
        await self.save_data(container)

    @data_cache
    async def save_data(
        self,
        data: dict,
    ):
        data["采集时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data["下载地址"] = " ".join(data["下载地址"])
        data["动图地址"] = " ".join(i or "NaN" for i in data["动图地址"])
        data["本地文件路径"] = dumps(data.get("本地文件路径", []), ensure_ascii=False)
        data.pop("时间戳", None)
        await self.data_recorder.add(**data)

    async def __add_record(
        self,
        id_: str,
    ) -> None:
        await self.id_recorder.add(id_)

    async def extract(
        self,
        url: str,
        download=False,
        index: list | tuple = None,
        data=True,
    ) -> list[dict]:
        if not (
            urls := await self.extract_links(
                url,
            )
        ):
            self.logging(_("提取小红书作品链接失败"), WARNING)
            return []
        statistics = SimpleNamespace(
            all=len(urls),
            success=0,
            fail=0,
            skip=0,
        )
        self.logging(_("共 {0} 个小红书作品待处理...").format(statistics.all))
        result = [
            await self.__deal_extract(
                i,
                download,
                index,
                data,
                count=statistics,
            )
            for i in urls
        ]
        self.show_statistics(
            statistics,
        )
        return result

    def show_statistics(
        self,
        statistics: SimpleNamespace,
    ) -> None:
        self.logging(
            _("共处理 {0} 个作品，成功 {1} 个，失败 {2} 个，跳过 {3} 个").format(
                statistics.all,
                statistics.success,
                statistics.fail,
                statistics.skip,
            ),
        )

    async def extract_cli(
        self,
        url: str,
        download=True,
        index: list | tuple = None,
        data=False,
    ) -> None:
        url = await self.extract_links(
            url,
        )
        if not url:
            self.logging(_("提取小红书作品链接失败"), WARNING)
            return
        if index:
            await self.__deal_extract(
                url[0],
                download,
                index,
                data,
            )
        else:
            statistics = SimpleNamespace(
                all=len(url),
                success=0,
                fail=0,
                skip=0,
            )
            [
                await self.__deal_extract(
                    u,
                    download,
                    index,
                    data,
                    count=statistics,
                )
                for u in url
            ]
            self.show_statistics(
                statistics,
            )

    async def extract_links(
        self,
        url: str,
    ) -> list:
        urls = []
        for i in url.split():
            if u := self.SHORT.search(i):
                i = await self.html.request_url(
                    u.group(),
                    False,
                )
            if u := self.SHARE.search(i):
                urls.append(u.group())
            elif u := self.LINK.search(i):
                urls.append(u.group())
            elif u := self.USER.search(i):
                urls.append(u.group())
        return urls

    def extract_id(self, links: list[str]) -> list[str]:
        ids = []
        for i in links:
            if j := self.ID.search(i):
                ids.append(j.group(1))
            elif j := self.ID_USER.search(i):
                ids.append(j.group(1))
        return ids

    async def _get_html_data(
        self,
        url: str,
        data: bool,
        cookie: str = None,
        proxy: str = None,
        count=SimpleNamespace(
            all=0,
            success=0,
            fail=0,
            skip=0,
        ),
    ) -> tuple[str, Namespace | dict]:
        if await self.skip_download(id_ := self.__extract_link_id(url)) and not data:
            msg = _("作品 {0} 存在下载记录，跳过处理").format(id_)
            self.logging(msg)
            count.skip += 1
            return id_, {"message": msg}
        self.logging(_("开始处理作品：{0}").format(id_))
        html = await self.html.request_url(
            url,
            cookie=cookie,
            proxy=proxy,
        )
        namespace = self.__generate_data_object(html)
        if not namespace:
            self.logging(_("{0} 获取数据失败").format(id_), ERROR)
            count.fail += 1
            return id_, {}
        return id_, namespace

    def _extract_data(
        self,
        namespace: Namespace,
        id_: str,
        count,
    ):
        data = self.explore.run(namespace)
        if not data:
            self.logging(_("{0} 提取数据失败").format(id_), ERROR)
            count.fail += 1
            return {}
        return data

    async def _deal_download_tasks(
        self,
        data: dict,
        namespace: Namespace,
        id_: str,
        download: bool,
        index: list | tuple | None,
        count: SimpleNamespace,
    ):
        if data["作品类型"] == _("视频"):
            self.__extract_video(data, namespace)
        elif data["作品类型"] in {
            _("图文"),
            _("图集"),
        }:
            self.__extract_image(data, namespace)
        else:
            self.logging(_("未知的作品类型：{0}").format(id_), WARNING)
            data["下载地址"] = []
            data["动图地址"] = []
        await self.update_author_nickname(
            data,
        )
        await self.__download_files(
            data,
            download,
            index,
            count,
        )
        # await sleep_time()
        return data

    async def __deal_extract(
        self,
        url: str,
        download: bool,
        index: list | tuple | None,
        data: bool,
        cookie: str = None,
        proxy: str = None,
        count=SimpleNamespace(
            all=0,
            success=0,
            fail=0,
            skip=0,
        ),
    ):
        id_, namespace = await self._get_html_data(
            url,
            data,
            cookie,
            proxy,
            count,
        )
        if not isinstance(namespace, Namespace):
            return namespace
        if not (
            data := self._extract_data(
                namespace,
                id_,
                count,
            )
        ):
            return data
        data = await self._deal_download_tasks(
            data
            | {
                "作品链接": url,
            },
            namespace,
            id_,
            download,
            index,
            count,
        )
        self.logging(_("作品处理完成：{0}").format(id_))
        return data

    async def deal_script_tasks(
        self,
        data: dict,
        index: list | tuple | None,
        count=SimpleNamespace(
            all=0,
            success=0,
            fail=0,
            skip=0,
        ),
    ):
        namespace = self.json_to_namespace(data)
        id_ = namespace.safe_extract("noteId", "")
        if not (
            data := self._extract_data(
                namespace,
                id_,
                count,
            )
        ):
            return data
        return await self._deal_download_tasks(
            data,
            namespace,
            id_,
            True,
            index,
            count,
        )

    @staticmethod
    def json_to_namespace(data: dict) -> Namespace:
        return Namespace(data)

    async def update_author_nickname(
        self,
        container: dict,
    ):
        if a := self.CLEANER.filter_name(
            self.mapping_data.get(i := container["作者ID"], "")
        ):
            container["作者昵称"] = a
        else:
            container["作者昵称"] = self.manager.filter_name(container["作者昵称"]) or i
        await self.mapping.update_cache(
            i,
            container["作者昵称"],
        )

    @staticmethod
    def __extract_link_id(url: str) -> str:
        link = urlparse(url)
        return link.path.split("/")[-1]

    def __generate_data_object(self, html: str) -> Namespace:
        data = self.convert.run(html)
        return Namespace(data)

    def __naming_rules(self, data: dict) -> str:
        keys = self.manager.name_format.split()
        values = []
        for key in keys:
            match key:
                case "发布时间":
                    values.append(self.__get_name_time(data))
                case "作品标题":
                    values.append(self.__get_name_title(data))
                case _:
                    values.append(data[key])
        return beautify_string(
            self.CLEANER.filter_name(
                self.manager.SEPARATE.join(values),
                default=self.manager.SEPARATE.join(
                    (
                        data["作者ID"],
                        data["作品ID"],
                    )
                ),
            ),
            length=128,
        )

    @staticmethod
    def __get_name_time(data: dict) -> str:
        return data["发布时间"].replace(":", ".")

    def __get_name_title(self, data: dict) -> str:
        return (
            beautify_string(
                self.manager.filter_name(data["作品标题"]),
                64,
            )
            or data["作品ID"]
        )

    async def monitor(
        self,
        delay=1,
        download=True,
        data=False,
    ) -> None:
        self.logging(
            _(
                "程序会自动读取并提取剪贴板中的小红书作品链接，并自动下载链接对应的作品文件，如需关闭，请点击关闭按钮，或者向剪贴板写入 “close” 文本！"
            ),
            style=MASTER,
        )
        self.event.clear()
        copy("")
        await gather(
            self.__get_link(delay),
            self.__receive_link(delay, download=download, index=None, data=data),
        )

    async def __get_link(self, delay: int):
        while not self.event.is_set():
            if (t := paste()).lower() == "close":
                self.stop_monitor()
            elif t != self.clipboard_cache:
                self.clipboard_cache = t
                create_task(self.__push_link(t))
            await sleep(delay)

    async def __push_link(
        self,
        content: str,
    ):
        await gather(
            *[
                self.queue.put(i)
                for i in await self.extract_links(
                    content,
                )
            ]
        )

    async def __receive_link(self, delay: int, *args, **kwargs):
        while not self.event.is_set() or self.queue.qsize() > 0:
            with suppress(QueueEmpty):
                await self.__deal_extract(self.queue.get_nowait(), *args, **kwargs)
            await sleep(delay)

    def stop_monitor(self):
        self.event.set()

    async def skip_download(self, id_: str) -> bool:
        return bool(await self.id_recorder.select(id_))

    async def __aenter__(self):
        await self.id_recorder.__aenter__()
        await self.data_recorder.__aenter__()
        await self.map_recorder.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.id_recorder.__aexit__(exc_type, exc_value, traceback)
        await self.data_recorder.__aexit__(exc_type, exc_value, traceback)
        await self.map_recorder.__aexit__(exc_type, exc_value, traceback)
        await self.close()

    async def close(self):
        await self.stop_script_server()
        await self.manager.close()

    @staticmethod
    def __rows_to_dicts(
        columns: list[str],
        rows: list[tuple],
        field_map: dict[str, str] | None = None,
    ) -> list[dict[str, object]]:
        field_map = field_map or {}
        data = []
        for row in rows:
            item = {}
            for key, value in zip(columns, row):
                item[field_map.get(key, key)] = value
            data.append(item)
        return data

    async def __fetch_table_rows(
        self,
        database,
        table: str,
    ) -> list[dict[str, object]]:
        cursor = await database.execute(f"SELECT * FROM {table};")
        try:
            rows = await cursor.fetchall()
            columns = [i[0] for i in (cursor.description or ())]
            return self.__rows_to_dicts(
                columns,
                rows,
                self.SQLITE_FIELD_MAP.get(table),
            )
        finally:
            await cursor.close()

    async def get_sqlite_data(self) -> dict[str, list[dict]]:
        if not all(
            (
                self.data_recorder.database,
                self.id_recorder.database,
                self.map_recorder.database,
            )
        ):
            raise RuntimeError(_("数据库未初始化"))
        return {
            "explore_data": await self.__fetch_table_rows(
                self.data_recorder.database,
                "explore_data",
            ),
            "explore_id": await self.__fetch_table_rows(
                self.id_recorder.database,
                "explore_id",
            ),
            "mapping_data": await self.__fetch_table_rows(
                self.map_recorder.database,
                "mapping_data",
            ),
        }

    # @staticmethod
    # def read_browser_cookie(value: str | int) -> str:
    #     return (
    #         BrowserCookie.get(
    #             value,
    #             domains=[
    #                 "xiaohongshu.com",
    #             ],
    #         )
    #         if value
    #         else ""
    #     )

    async def run_api_server(
        self,
        host="0.0.0.0",
        port=5556,
        log_level="info",
    ):
        api = FastAPI(
            debug=self.VERSION_BETA,
            title="XHS-Downloader",
            version=__VERSION__,
        )
        self.setup_routes(api)
        config = Config(
            api,
            host=host,
            port=port,
            log_level=log_level,
        )
        server = Server(config)
        await server.serve()

    def setup_routes(
        self,
        server: FastAPI,
    ):
        @server.get(
            "/",
            summary=_("跳转至项目 GitHub 仓库"),
            description=_("重定向至项目 GitHub 仓库主页"),
            tags=["API"],
        )
        async def index():
            return RedirectResponse(url=REPOSITORY)

        @server.get(
            "/xhs/sqlite/data",
            summary=_("获取 SQLite 存储数据"),
            description=_("返回 SQLite 中已存储的作品记录、下载记录和映射数据"),
            tags=["API"],
            response_model=SQLiteDataResponse,
        )
        async def sqlite_data():
            try:
                data = await self.get_sqlite_data()
            except RuntimeError as error:
                raise HTTPException(status_code=503, detail=str(error)) from error
            except Exception as error:
                raise HTTPException(
                    status_code=500,
                    detail=_("读取 SQLite 数据失败：{0}").format(repr(error)),
                ) from error
            return SQLiteDataResponse(
                message=_("获取 SQLite 数据成功"),
                data=data,
            )

        @server.post(
            "/xhs/detail",
            summary=_("获取作品数据及下载地址"),
            description=_(
                dedent("""
                **参数**:
                        
                - **url**: 小红书作品链接，自动提取，不支持多链接；必需参数
                - **download**: 是否下载作品文件；设置为 true 将会耗费更多时间；可选参数
                - **index**: 下载指定序号的图片文件，仅对图文作品生效；download 参数设置为 false 时不生效；可选参数
                - **cookie**: 请求数据时使用的 Cookie；可选参数
                - **proxy**: 请求数据时使用的代理；可选参数
                - **skip**: 是否跳过存在下载记录的作品；设置为 true 将不会返回存在下载记录的作品数据；可选参数
                """)
            ),
            tags=["API"],
            response_model=ExtractData,
        )
        async def handle(extract: ExtractParams):
            data = None
            url = await self.extract_links(
                extract.url,
            )
            if not url:
                msg = _("提取小红书作品链接失败")
            else:
                if data := await self.__deal_extract(
                    url[0],
                    extract.download,
                    extract.index,
                    not extract.skip,
                    self._resolve_cookie(extract.cookie),
                    self._resolve_proxy(extract.proxy),
                ):
                    msg = _("获取小红书作品数据成功")
                else:
                    msg = _("获取小红书作品数据失败")
            return ExtractData(message=msg, params=extract, data=data)

        @server.post(
            "/xhs/download/share",
            summary=_("下载指定作品链接文件"),
            description=_(
                dedent("""
                **参数**:

                - **url**: 小红书作品链接或短链接；必填
                - **index**: 指定下载图片序号，仅对图文作品生效；可选
                - **cookie**: 本次请求使用的 Cookie；可选
                - **proxy**: 本次请求使用的代理（http(s)/socks5）；可选
                - **skip**: 是否跳过存在下载记录的作品；可选
                """)
            ),
            tags=["API"],
            response_model=DownloadShareResponse,
        )
        async def download_share_api(extract: DownloadShareParams):
            message, data, stats = await self.download_share(extract)
            return DownloadShareResponse(
                message=message,
                params=extract,
                data=data,
                stats=DownloadStatistics(**stats),
            )

        @server.post(
            "/xhs/download/user-posted",
            summary=_("下载发布者全部作品"),
            description=_(
                dedent("""
                **参数**:

                - **profile_url**: 发布者主页链接，支持手机端分享文案中的 `xhslink.com` 短链接；必填
                - **cookie**: 本次请求使用的 Cookie；可选
                - **proxy**: 本次请求使用的代理（http(s)/socks5）；可选
                - **limit**: 最多处理作品数量；可选
                """)
            ),
            tags=["API"],
            response_model=TaskAcceptedResponse,
        )
        async def download_user_posted(params: BatchDownloadParams):
            task_id = self.create_download_task(
                mode="posted",
                profile_url=params.profile_url,
                cookie=params.cookie,
                proxy=params.proxy,
                limit=params.limit,
                video_only=False,
            )
            return TaskAcceptedResponse(
                message=_("批量下载任务已创建"),
                task_id=task_id,
                status_url=f"/xhs/tasks/{task_id}",
            )

        @server.post(
            "/xhs/download/me-liked-videos",
            summary=_("下载本人点赞视频"),
            description=_(
                dedent("""
                **参数**:

                - **profile_url**: 本人主页链接，支持手机端分享文案中的 `xhslink.com` 短链接；必填
                - **cookie**: 本次请求使用的 Cookie；可选
                - **proxy**: 本次请求使用的代理（http(s)/socks5）；可选
                - **limit**: 最多处理作品数量；可选
                """)
            ),
            tags=["API"],
            response_model=TaskAcceptedResponse,
        )
        async def download_me_liked(params: BatchDownloadParams):
            task_id = self.create_download_task(
                mode="liked",
                profile_url=params.profile_url,
                cookie=params.cookie,
                proxy=params.proxy,
                limit=params.limit,
                video_only=True,
            )
            return TaskAcceptedResponse(
                message=_("批量下载任务已创建"),
                task_id=task_id,
                status_url=f"/xhs/tasks/{task_id}",
            )

        @server.post(
            "/xhs/download/me-saved-videos",
            summary=_("下载本人收藏视频"),
            description=_(
                dedent("""
                **参数**:

                - **profile_url**: 本人主页链接，支持手机端分享文案中的 `xhslink.com` 短链接；必填
                - **cookie**: 本次请求使用的 Cookie；可选
                - **proxy**: 本次请求使用的代理（http(s)/socks5）；可选
                - **limit**: 最多处理作品数量；可选
                """)
            ),
            tags=["API"],
            response_model=TaskAcceptedResponse,
        )
        async def download_me_saved(params: BatchDownloadParams):
            task_id = self.create_download_task(
                mode="saved",
                profile_url=params.profile_url,
                cookie=params.cookie,
                proxy=params.proxy,
                limit=params.limit,
                video_only=True,
            )
            return TaskAcceptedResponse(
                message=_("批量下载任务已创建"),
                task_id=task_id,
                status_url=f"/xhs/tasks/{task_id}",
            )

        @server.get(
            "/xhs/tasks/{task_id}",
            summary=_("查询批量下载任务状态"),
            description=_(
                dedent("""
                **路径参数**:

                - **task_id**: 创建批量下载任务接口返回的任务 ID
                """)
            ),
            tags=["API"],
            response_model=TaskStatusResponse,
        )
        async def get_task_status(
            task_id: Annotated[str, Path(description=_("批量下载任务 ID"))]
        ):
            if not (task := self.task_manager.get(task_id)):
                raise HTTPException(status_code=404, detail=_("任务不存在"))
            return TaskStatusResponse(
                task_id=task["task_id"],
                mode=task["mode"],
                status=task["status"],
                started_at=task["started_at"],
                finished_at=task["finished_at"],
                progress=DownloadStatistics(**task["progress"]),
                summary=DownloadStatistics(**task["summary"]),
                errors=task["errors"],
            )

    async def run_mcp_server(
        self,
        transport="streamable-http",
        host="0.0.0.0",
        port=5556,
        log_level="INFO",
    ):
        mcp = FastMCP(
            "XHS-Downloader",
            instructions=dedent("""
                本服务器提供两个 MCP 接口，分别用于获取小红书作品信息数据和下载小红书作品文件，二者互不依赖，可独立调用。
                
                支持的作品链接格式：
                - https://www.xiaohongshu.com/explore/...
                - https://www.xiaohongshu.com/discovery/item/...
                - https://xhslink.com/...
                
                get_detail_data
                功能：输入小红书作品链接，返回该作品的信息数据，不会下载文件。
                参数：
                - url（必填）：小红书作品链接
                返回：
                - message：结果提示
                - data：作品信息数据
                
                download_detail
                功能：输入小红书作品链接，下载作品文件，默认不返回作品信息数据。
                参数：
                - url（必填）：小红书作品链接
                - index（选填）：根据用户指定的图片序号（如用户说“下载第1和第3张”时，index应为 [1, 3]），生成由所需图片序号组成的列表；如果用户未指定序号，则该字段为 None
                - return_data（可选）：是否返回作品信息数据；如需返回作品信息数据，设置此参数为 true，默认值为 false
                返回：
                - message：结果提示
                - data：作品信息数据，不需要返回作品信息数据时固定为 None
                """),
            version=__VERSION__,
        )

        @mcp.tool(
            name="get_detail_data",
            description=dedent("""
                功能：输入小红书作品链接，返回该作品的信息数据，不会下载文件。
                
                参数：
                url（必填）：小红书作品链接，格式如：
                - https://www.xiaohongshu.com/explore/...
                - https://www.xiaohongshu.com/discovery/item/...
                - https://xhslink.com/...
                
                返回：
                - message：结果提示
                - data：作品信息数据
                """),
            tags={
                "小红书",
                "XiaoHongShu",
                "RedNote",
            },
            annotations={
                "title": "获取小红书作品信息数据",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            },
        )
        async def get_detail_data(
            url: Annotated[str, Field(description=_("小红书作品链接"))],
        ) -> dict:
            msg, data = await self.deal_detail_mcp(
                url,
                False,
                None,
            )
            return {
                "message": msg,
                "data": data,
            }

        @mcp.tool(
            name="download_detail",
            description=dedent("""
                功能：输入小红书作品链接，下载作品文件，默认不返回作品信息数据。
                
                参数：
                url（必填）：小红书作品链接，格式如：
                - https://www.xiaohongshu.com/explore/...
                - https://www.xiaohongshu.com/discovery/item/...
                - https://xhslink.com/...
                index（选填）：根据用户指定的图片序号（如用户说“下载第1和第3张”时，index应为 [1, 3]），生成由所需图片序号组成的列表；如果用户未指定序号，则该字段为 None
                return_data（可选）：是否返回作品信息数据；如需返回作品信息数据，设置此参数为 true，默认值为 false
                
                返回：
                - message：结果提示
                - data：作品信息数据，不需要返回作品信息数据时固定为 None
                """),
            tags={
                "小红书",
                "XiaoHongShu",
                "RedNote",
                "Download",
                "下载",
            },
            annotations={
                "title": "下载小红书作品文件，可以返回作品信息数据",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            },
        )
        async def download_detail(
            url: Annotated[str, Field(description=_("小红书作品链接"))],
            index: Annotated[
                list[str | int] | None,
                Field(default=None, description=_("指定需要下载的图文作品序号")),
            ],
            return_data: Annotated[
                bool,
                Field(default=False, description=_("是否需要返回作品信息数据")),
            ],
        ) -> dict:
            msg, data = await self.deal_detail_mcp(
                url,
                True,
                index,
            )
            match (
                bool(data),
                return_data,
            ):
                case (True, True):
                    return {
                        "message": msg + ", " + _("作品文件下载任务执行完毕"),
                        "data": data,
                    }
                case (True, False):
                    return {
                        "message": _("作品文件下载任务执行完毕"),
                        "data": None,
                    }
                case (False, True):
                    return {
                        "message": msg + ", " + _("作品文件下载任务未执行"),
                        "data": None,
                    }
                case (False, False):
                    return {
                        "message": msg + ", " + _("作品文件下载任务未执行"),
                        "data": None,
                    }
                case _:
                    raise ValueError

        await mcp.run_async(
            transport=transport,
            host=host,
            port=port,
            log_level=log_level,
        )

    async def deal_detail_mcp(
        self,
        url: str,
        download: bool,
        index: list[str | int] | None,
    ):
        data = None
        url = await self.extract_links(
            url,
        )
        if not url:
            msg = _("提取小红书作品链接失败")
        elif data := await self.__deal_extract(
            url[0],
            download,
            index,
            True,
        ):
            msg = _("获取小红书作品数据成功")
        else:
            msg = _("获取小红书作品数据失败")
        return msg, data

    @staticmethod
    def _stats_to_dict(
        stats: SimpleNamespace,
        filtered: int = 0,
    ) -> dict[str, int]:
        return {
            "all": int(stats.all),
            "success": int(stats.success),
            "fail": int(stats.fail),
            "skip": int(stats.skip),
            "filtered": int(filtered),
        }

    @classmethod
    def extract_profile_id(
        cls,
        profile_url: str,
    ) -> str:
        return r.group(1) if (r := cls.PROFILE.search(profile_url)) else ""

    async def resolve_profile_id(
        self,
        profile_url: str,
        proxy: str | None = None,
    ) -> str:
        profile_url = (profile_url or "").strip()
        if not profile_url:
            return ""
        if user_id := self.extract_profile_id(profile_url):
            return user_id
        if short := self.SHORT.search(profile_url):
            if resolved := await self.html.request_url(
                short.group(),
                content=False,
                proxy=proxy,
                follow_redirects=True,
            ):
                if user_id := self.extract_profile_id(resolved):
                    return user_id
        return ""

    @staticmethod
    def _resolve_cookie(cookie: str | None) -> str | None:
        if not cookie:
            return None
        if not isinstance(cookie, str):
            return None
        cookie = cookie.strip()
        if not cookie or cookie.lower() == "string":
            return None
        return cookie

    @staticmethod
    def _resolve_proxy(proxy: str | None) -> str | None:
        if not proxy:
            return None
        if not isinstance(proxy, str):
            return None
        proxy = proxy.strip()
        if not proxy or proxy.lower() == "string":
            return None
        if proxy.startswith(
            (
                "http://",
                "https://",
                "socks5://",
                "socks5h://",
            )
        ):
            return proxy
        return None

    async def download_share(
        self,
        extract: DownloadShareParams,
    ) -> tuple[str, dict | None, dict[str, int]]:
        data = None
        stats = SimpleNamespace(
            all=1,
            success=0,
            fail=0,
            skip=0,
        )
        url = await self.extract_links(
            extract.url,
        )
        if not url:
            msg = _("提取小红书作品链接失败")
        elif data := await self.__deal_extract(
            url[0],
            True,
            extract.index,
            not extract.skip,
            self._resolve_cookie(extract.cookie),
            self._resolve_proxy(extract.proxy),
            count=stats,
        ):
            msg = _("作品文件下载任务执行完毕")
        else:
            msg = _("作品文件下载任务未执行")
        return msg, data, self._stats_to_dict(stats)

    def create_download_task(
        self,
        mode: str,
        profile_url: str,
        cookie: str | None,
        proxy: str | None,
        limit: int | None,
        video_only: bool,
    ) -> str:
        task_id = self.task_manager.create(mode)
        create_task(
            self._run_download_task(
                task_id=task_id,
                mode=mode,
                profile_url=profile_url,
                cookie=self._resolve_cookie(cookie),
                proxy=self._resolve_proxy(proxy),
                limit=limit,
                video_only=video_only,
            )
        )
        return task_id

    async def _run_download_task(
        self,
        task_id: str,
        mode: str,
        profile_url: str,
        cookie: str | None,
        proxy: str | None,
        limit: int | None,
        video_only: bool,
    ):
        statistics = SimpleNamespace(
            all=0,
            success=0,
            fail=0,
            skip=0,
        )
        filtered = 0
        try:
            if not (user_id := await self.resolve_profile_id(profile_url, proxy)):
                self.task_manager.fail(task_id, _("主页链接格式错误"))
                return

            loader = UserPosted(
                self.manager,
                cookie,
                proxy,
            )
            links = await loader.run(
                mode=mode,
                user_id=user_id,
                limit=limit,
            )
            statistics.all = len(links)
            self.task_manager.mark_running(task_id, len(links))
            if not links:
                self.task_manager.complete(
                    task_id,
                    all_count=0,
                    success=0,
                    fail=0,
                    skip=0,
                    filtered=0,
                )
                return

            for link in links:
                try:
                    is_filtered, error = await self._batch_deal_extract(
                        link,
                        cookie,
                        proxy,
                        video_only,
                        statistics,
                    )
                    if is_filtered:
                        filtered += 1
                    if error:
                        self.task_manager.add_error(task_id, error)
                except Exception as error:
                    statistics.fail += 1
                    self.task_manager.add_error(
                        task_id,
                        _("{0} 下载失败：{1}").format(link, repr(error)),
                    )
                progress = self._stats_to_dict(
                    statistics,
                    filtered,
                )
                self.task_manager.update_progress(
                    task_id,
                    all_count=progress["all"],
                    success=progress["success"],
                    fail=progress["fail"],
                    skip=progress["skip"],
                    filtered=progress["filtered"],
                )

            summary = self._stats_to_dict(
                statistics,
                filtered,
            )
            self.task_manager.complete(
                task_id,
                all_count=summary["all"],
                success=summary["success"],
                fail=summary["fail"],
                skip=summary["skip"],
                filtered=summary["filtered"],
            )
        except Exception as error:
            self.task_manager.fail(
                task_id,
                _("批量任务执行失败：{0}").format(repr(error)),
                all_count=statistics.all,
                success=statistics.success,
                fail_count=statistics.fail,
                skip=statistics.skip,
                filtered=filtered,
            )

    async def _batch_deal_extract(
        self,
        url: str,
        cookie: str | None,
        proxy: str | None,
        video_only: bool,
        count: SimpleNamespace,
    ) -> tuple[bool, str | None]:
        id_, namespace = await self._get_html_data(
            url,
            True,
            cookie,
            proxy,
            count,
        )
        if not isinstance(namespace, Namespace):
            if message := namespace.get("message") if isinstance(namespace, dict) else None:
                return False, message
            return False, _("作品 {0} 处理失败").format(id_)

        if not (
            data := self._extract_data(
                namespace,
                id_,
                count,
            )
        ):
            return False, _("作品 {0} 数据提取失败").format(id_)

        if video_only and data["作品类型"] != _("视频"):
            return True, None

        await self._deal_download_tasks(
            data
            | {
                "作品链接": url,
            },
            namespace,
            id_,
            True,
            None,
            count,
        )
        self.logging(_("作品处理完成：{0}").format(id_))
        return False, None

    def init_script_server(
        self,
        host="0.0.0.0",
        port=5558,
    ):
        if self.manager.script_server:
            self.run_script_server(host, port)

    async def switch_script_server(
        self,
        host="0.0.0.0",
        port=5558,
        switch: bool = None,
    ):
        if switch is None:
            switch = self.manager.script_server
        if switch:
            self.run_script_server(
                host,
                port,
            )
        else:
            await self.stop_script_server()

    def run_script_server(
        self,
        host="0.0.0.0",
        port=5558,
    ):
        if not self.script:
            self.script = create_task(self._run_script_server(host, port))

    async def _run_script_server(
        self,
        host="0.0.0.0",
        port=5558,
    ):
        async with ScriptServer(self, host, port):
            await Future()

    async def stop_script_server(self):
        if self.script:
            self.script.cancel()
            with suppress(CancelledError):
                await self.script
            self.script = None

    async def _script_server_debug(self):
        await self.switch_script_server(
            switch=self.manager.script_server,
        )

    def logging(self, text, style=INFO):
        logging(
            self.print,
            text,
            style,
        )
