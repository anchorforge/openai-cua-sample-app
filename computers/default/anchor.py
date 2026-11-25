import os
from typing import Tuple

from dotenv import load_dotenv
from playwright.sync_api import Browser
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
import requests

from ..shared.base_playwright import BasePlaywrightComputer


load_dotenv()


class AnchorBrowser(BasePlaywrightComputer):
    """
    Computer implementation for Anchor browser (https://anchorbrowser.io)
    Requires an API key in the .env file as ANCHORBROWSER_API_KEY (ANCHOR_API_KEY also works)

    IMPORTANT: The `goto` and navigation tools are already implemented and recommended
    when using the Anchor computer to help the agent navigate more effectively.
    """

    def __init__(
        self,
        width: int = 1024,
        height: int = 900,
        proxy_active: bool = True,
        adblock_active: bool = True,
        popup_blocking_active: bool = True,
        captcha_active: bool = True,
        timeout: int = 15,
        idle_timeout: int = 2,
        debug: bool = False,
    ):
        """Initialize the Anchor browser session"""
        super().__init__()
        self.api_key = os.getenv("ANCHORBROWSER_API_KEY") or os.getenv("ANCHOR_API_KEY")
        if not self.api_key:
            raise ValueError("ANCHORBROWSER_API_KEY (or ANCHOR_API_KEY) not found in .env file")

        self.debug = debug
        self.base_url = "https://api.anchorbrowser.io/v1"
        self.session_id = None
        self.dimensions = (width, height)
        self.proxy_config = {"active": proxy_active}
        self.adblock_config = {
            "active": adblock_active,
            "popup_blocking_active": popup_blocking_active,
        }
        self.captcha_config = {"active": captcha_active}
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        self._browser = None
        self._page = None

        if self.debug:
            print(f"Anchor browser initialized with viewport {width}x{height}")

    def _get_browser_and_page(self) -> Tuple[Browser, Page]:
        """
        Get browser and page objects.
        For Anchor, we don't have direct browser/page objects, but we simulate them
        for compatibility with the BasePlaywrightComputer interface.
        """
        # Create a session with Anchor API
        width, height = self.dimensions
        response = requests.post(
            f"{self.base_url}/sessions",
            headers={"anchor-api-key": f"{self.api_key}"},
            json={
                "session": {
                    "proxy": {"active": self.proxy_config["active"]},
                    "timeout": {
                        "max_duration": self.timeout,
                        "idle_timeout": self.idle_timeout,
                    },
                },
                "browser": {
                    "viewport": {"width": width, "height": height},
                    "captcha_solver": {"active": self.captcha_config["active"]},
                    "adblock": {"active": self.adblock_config["active"]},
                    "popup_blocker": {
                        "active": self.adblock_config["popup_blocking_active"]
                    },
                    "headless": {"active": False},
                },
            },
        )
        response.raise_for_status()
        session = response.json().get("data", {})
        self.session_id = session.get("id")
        if not self.session_id:
            raise ValueError("Failed to create Anchor browser session")

        browser = self._playwright.chromium.connect_over_cdp(session["cdp_url"])
        context = browser.contexts[0]
        context.on("page", self._handle_new_page)
        page = context.pages[0]
        page.goto("https://bing.com")
        return browser, page

    def _handle_new_page(self, page: Page):
        """Handle the creation of a new page."""
        print("New page created")
        self._page = page
        page.on("close", self._handle_page_close)

    def _handle_page_close(self, page: Page):
        """Handle the closure of a page."""
        print("Page closed")
        if self._page == page:
            if self._browser.contexts[0].pages:
                self._page = self._browser.contexts[0].pages[-1]
            else:
                print("Warning: All pages have been closed.")
                self._page = None

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources when exiting"""
        if self.session_id:
            requests.delete(
                f"{self.base_url}/sessions/{self.session_id}",
                headers={"anchor-api-key": f"{self.api_key}"},
            )
            if self.debug:
                print(f"Ended Anchor session: {self.session_id}")
            self.session_id = None

    def screenshot(self) -> str:
        """
        Capture a screenshot of the current viewport using CDP.

        Returns:
            str: A base64 encoded string of the screenshot.
        """
        try:
            # Get CDP session from the page
            cdp_session = self._page.context.new_cdp_session(self._page)

            # Capture screenshot using CDP
            result = cdp_session.send(
                "Page.captureScreenshot", {"format": "png", "fromSurface": True}
            )

            return result["data"]
        except PlaywrightError as error:
            print(
                f"CDP screenshot failed, falling back to standard screenshot: {error}"
            )
            return super().screenshot()
