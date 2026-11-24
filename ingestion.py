"""Safe text/PDF extraction and bounded web-page ingestion."""
from __future__ import annotations

import html
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

MAX_UPLOAD = 10 * 1024 * 1024
MAX_WEB = 2 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".html", ".htm"}


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._skip = 0
        self._title = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        if tag.lower() == "title":
            self._title = True
        if tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "br", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
        if tag.lower() == "title":
            self._title = False
        if tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "br", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._title:
            self.title_parts.append(data)
        if not self._skip:
            self.parts.append(data)


def parse_document(filename: str, raw: bytes) -> list[tuple[int | None, str]]:
    if len(raw) > MAX_UPLOAD:
        raise ValueError("上传文件最多 10 MB")
    suffix = "." + filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("支持 PDF、TXT、Markdown 和 HTML 文件")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            from pypdf.errors import PdfReadError
        except ImportError as error:
            raise RuntimeError("PDF 支持需要安装 pypdf（pip install -r requirements.txt）") from error
        try:
            reader = PdfReader(__import__("io").BytesIO(raw), strict=True)
            if len(reader.pages) > 500:
                raise ValueError("PDF 最多支持 500 页")
            return [(number, page.extract_text() or "") for number, page in enumerate(reader.pages, 1)]
        except (PdfReadError, ValueError):
            raise
        except Exception as error:
            raise ValueError("无法读取此 PDF") from error
    text = raw.decode("utf-8-sig", errors="replace")
    if suffix in {".html", ".htm"}:
        parser = TextExtractor()
        parser.feed(text)
        text = "\n".join(parser.parts)
    if "\ufffd" in text:
        raise ValueError("文本编码不是有效 UTF-8")
    return [(None, text)]


def _validate_url(url: str) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("只允许没有账号密码的 HTTP/HTTPS 网页地址")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("网页地址端口无效") from error
    expected_port = 443 if parsed.scheme == "https" else 80
    if port not in {None, expected_port}:
        raise ValueError("为安全起见，仅允许标准 HTTP/HTTPS 端口")
    try:
        addresses = {ipaddress.ip_address(parsed.hostname)}
    except ValueError:
        try:
            addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(parsed.hostname, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
        except OSError as error:
            raise ValueError("无法解析该网页地址") from error
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("为安全起见，不允许访问本机、内网或保留 IP 地址")
    return parsed


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        target = urllib.parse.urljoin(request.full_url, newurl)
        if urllib.parse.urlsplit(request.full_url).scheme == "https" and urllib.parse.urlsplit(target).scheme != "https":
            raise ValueError("不允许从 HTTPS 重定向到不安全的 HTTP")
        _validate_url(target)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def fetch_webpage(url: str) -> tuple[str, str, str]:
    _validate_url(url)
    opener = urllib.request.build_opener(SafeRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "KBQA/1.0 (text-only knowledge-base importer)", "Accept": "text/html,text/plain;q=0.9"})
    try:
        with opener.open(request, timeout=10) as response:
            final_url = response.geturl()
            _validate_url(final_url)
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
                raise ValueError("只支持导入 HTML 或纯文本网页")
            raw = response.read(MAX_WEB + 1)
            if len(raw) > MAX_WEB:
                raise ValueError("网页正文最多 2 MB")
            charset = response.headers.get_content_charset() or "utf-8"
    except (urllib.error.URLError, TimeoutError) as error:
        raise ValueError("网页抓取失败或超时") from error
    text = raw.decode(charset, errors="replace")
    title = ""
    if content_type in {"text/html", "application/xhtml+xml"}:
        parser = TextExtractor()
        parser.feed(text)
        title = re.sub(r"\s+", " ", " ".join(parser.title_parts)).strip()
        text = "\n".join(parser.parts)
    text = html.unescape(re.sub(r"\n{3,}", "\n\n", text)).strip()
    if not text:
        raise ValueError("网页中没有可提取的正文")
    return final_url, title, text
