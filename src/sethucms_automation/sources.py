"""Page sources: the first step of a workflow. They turn an address into HTML and readable text."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from bs4 import BeautifulSoup

from .logs import log_event
from .models import FetchedPage


class PageSource(Protocol):
    """Anything that can fetch a page. Tests use a fake one."""

    def fetch(self, url: str) -> FetchedPage: ...


def html_to_text(html: str) -> str:
    """Turn HTML into readable text. Scripts, styles and hidden templates are dropped."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text("\n").splitlines()]
    return "\n".join(line for line in lines if line)


@dataclass(frozen=True)
class LoginForm:
    """Where the sign-in form is and how to fill it. Credentials are passed in, never stored here."""

    login_url: str
    username_selector: str
    password_selector: str
    submit_selector: str
    #: A selector that only exists once signed in. The login is treated as failed without it.
    signed_in_selector: str


class StaticSource:
    """Serves HTML you already have, for example a downloaded file. Good for tests and dry runs."""

    def __init__(self, html: str, url: str = "static://page") -> None:
        self._html = html
        self._url = url

    def fetch(self, url: str) -> FetchedPage:
        return FetchedPage(url=self._url, html=self._html, text=html_to_text(self._html))


class PlaywrightSource:
    """Opens a real browser, optionally signs in first, and returns the page after scripts have run.

    Install the extras first:  pip install "sethucms[automation]" && playwright install chromium
    """

    def __init__(
        self,
        *,
        login: Optional[LoginForm] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout_ms: int = 30_000,
        headless: bool = True,
    ) -> None:
        if login is not None and not (username and password):
            raise ValueError("A login form needs a username and a password.")
        self._login = login
        self._username = username
        self._password = password
        self._timeout_ms = timeout_ms
        self._headless = headless

    def fetch(self, url: str) -> FetchedPage:
        # Imported here so the rest of the package works without Playwright installed.
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self._headless)
            try:
                context = browser.new_context()
                context.set_default_timeout(self._timeout_ms)
                page = context.new_page()
                if self._login is not None:
                    self._sign_in(page)
                page.goto(url, wait_until="networkidle")
                html = page.content()
                final_url = page.url
            finally:
                browser.close()
        log_event("page_fetched", html_length=len(html))
        return FetchedPage(url=final_url, html=html, text=html_to_text(html))

    def _sign_in(self, page) -> None:
        """Fill the form, submit it, and make sure we really are signed in."""
        form = self._login
        page.goto(form.login_url, wait_until="domcontentloaded")
        page.fill(form.username_selector, self._username)
        page.fill(form.password_selector, self._password)
        page.click(form.submit_selector)
        # A wrong password usually returns to the form quietly, so wait for proof of sign-in.
        page.wait_for_selector(form.signed_in_selector)
        log_event("signed_in")
