from typing import TYPE_CHECKING, Any

from ..module import retry, sleep_time

try:
    from xhshow import Xhshow
except ImportError:
    Xhshow = None

if TYPE_CHECKING:
    from ..module import Manager

__all__ = ["UserPosted"]


class UserPosted:
    BASE = "https://edith.xiaohongshu.com"
    ENDPOINTS = {
        "posted": "/api/sns/web/v1/user_posted",
        "liked": "/api/sns/web/v1/note/like/page",
        "saved": "/api/sns/web/v2/note/collect/page",
    }
    PAGE_SIZE = 30

    def __init__(
        self,
        manager: "Manager",
        cookies: str | None = None,
        proxy: str | None = None,
    ):
        self.headers = manager.blank_headers.copy()
        self.client = manager.request_client
        self.cookies = self.get_cookie(cookies)
        self.retry = manager.retry
        self.timeout = manager.timeout
        self.proxy = proxy
        self._encipher = None

    @property
    def encipher(self):
        if self._encipher is None:
            if Xhshow is None:
                raise RuntimeError("Missing dependency: xhshow")
            self._encipher = Xhshow()
        return self._encipher

    def get_cookie(self, cookies: str | None = None) -> dict | str:
        if cookies:
            self.headers["cookie"] = cookies
            return cookies
        try:
            cookie_data = dict(self.client.cookies)
        except Exception:
            # Some cookie jars may contain duplicated names (e.g. acw_tc under
            # different domains), which can raise CookieConflict when cast to
            # dict directly.
            cookie_data = {
                cookie.name: cookie.value
                for cookie in self.client.cookies.jar
                if getattr(cookie, "name", None)
            }
        cookie_string = "; ".join(f"{k}={v}" for k, v in cookie_data.items())
        if cookie_string:
            self.headers["cookie"] = cookie_string
            return cookie_string
        return cookie_data

    async def run(
        self,
        mode: str,
        user_id: str,
        limit: int | None = None,
    ) -> list[str]:
        if mode not in self.ENDPOINTS:
            raise ValueError(f"Unsupported mode: {mode}")
        cursor = ""
        urls: list[str] = []
        cache: set[str] = set()
        while True:
            url = self.BASE + self.ENDPOINTS[mode]
            params = self._build_params(mode, user_id, cursor)
            data = await self.get_data(url, params)
            notes = self._extract_notes(data)
            if not notes:
                break
            for note_id, token in notes:
                if not note_id:
                    continue
                if token:
                    item = (
                        f"https://www.xiaohongshu.com/discovery/item/{note_id}?source=webshare"
                        f"&xhsshare=pc_web&xsec_token={token}&xsec_source=pc_share"
                    )
                else:
                    item = f"https://www.xiaohongshu.com/discovery/item/{note_id}"
                if item not in cache:
                    cache.add(item)
                    urls.append(item)
                if limit and len(urls) >= limit:
                    return urls[:limit]
            cursor, has_more = self._extract_paging(data, cursor)
            if not has_more:
                break
        return urls

    @staticmethod
    def _build_params(mode: str, user_id: str, cursor: str) -> dict:
        params = {
            "num": UserPosted.PAGE_SIZE,
            "cursor": cursor,
        }
        if mode == "posted":
            params["user_id"] = user_id
        else:
            params["user_id"] = user_id
        return params

    @retry
    async def get_data(self, url: str, params: dict):
        headers = self.get_headers(url, params)
        response = await self.client.get(
            url,
            params=params,
            headers=headers,
            follow_redirects=True,
            timeout=self.timeout,
        )
        await sleep_time()
        response.raise_for_status()
        return response.json()

    def get_headers(self, url: str, params: dict):
        headers = self.encipher.sign_headers_get(
            uri=url,
            cookies=self.cookies,
            params=params,
        )
        return headers | self.headers

    @classmethod
    def _extract_paging(
        cls,
        data: dict[str, Any],
        fallback_cursor: str,
    ) -> tuple[str, bool]:
        body = cls._extract_body(data)
        cursor = cls._pick(
            body,
            "cursor",
            "next_cursor",
            "nextCursor",
            default=fallback_cursor,
        )
        has_more = bool(
            cls._pick(
                body,
                "has_more",
                "hasMore",
                default=False,
            )
        )
        return str(cursor), has_more

    @classmethod
    def _extract_notes(cls, data: dict[str, Any]) -> list[tuple[str, str]]:
        body = cls._extract_body(data)
        notes = []
        raw = cls._pick(
            body,
            "notes",
            "note_list",
            "noteList",
            "items",
            default=[],
        )
        for item in raw or []:
            note_id = cls._pick(
                item,
                "note_id",
                "noteId",
                "id",
                "note.note_id",
                "note.noteId",
                "note.id",
                default="",
            )
            token = cls._pick(
                item,
                "xsec_token",
                "xsecToken",
                "note.xsec_token",
                "note.xsecToken",
                default="",
            )
            notes.append((str(note_id or ""), str(token or "")))
        return notes

    @staticmethod
    def _extract_body(data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {}
        if isinstance(data.get("data"), dict):
            return data["data"]
        return data

    @staticmethod
    def _pick(data: dict[str, Any], *keys: str, default=None):
        for key in keys:
            value = UserPosted._deep_get(data, key)
            if value is not None:
                return value
        return default

    @staticmethod
    def _deep_get(data: Any, key: str):
        current = data
        for item in key.split("."):
            if not isinstance(current, dict) or item not in current:
                return None
            current = current[item]
        return current
