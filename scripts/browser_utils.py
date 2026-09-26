"""
Browser Utilities for NotebookLM Skill
Handles browser launching, stealth features, and common interactions
"""

import json
import time
import random
from typing import Optional, List

from patchright.sync_api import Playwright, BrowserContext, Page
from config import BROWSER_PROFILE_DIR, STATE_FILE, BROWSER_ARGS, USER_AGENT


class BrowserFactory:
    """Factory for creating configured browser contexts"""

    @staticmethod
    def launch_persistent_context(
        playwright: Playwright,
        headless: bool = True,
        user_data_dir: str = str(BROWSER_PROFILE_DIR)
    ) -> BrowserContext:
        """
        Launch a persistent browser context with anti-detection features
        and cookie workaround.
        """
        # Launch persistent context
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            channel="chrome",  # Use real Chrome
            headless=headless,
            no_viewport=True,
            ignore_default_args=["--enable-automation"],
            user_agent=USER_AGENT,
            args=BROWSER_ARGS
        )

        # Cookie Workaround for Playwright bug #36139
        # Session cookies (expires=-1) don't persist in user_data_dir automatically
        BrowserFactory._inject_cookies(context)

        return context

    @staticmethod
    def _inject_cookies(context: BrowserContext):
        """Inject cookies from state.json if available"""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                    if 'cookies' in state and len(state['cookies']) > 0:
                        context.add_cookies(state['cookies'])
                        # print(f"  🔧 Injected {len(state['cookies'])} cookies from state.json")
            except Exception as e:
                print(f"  ⚠️  Could not load state.json: {e}")


class StealthUtils:
    """Human-like interaction utilities"""

    @staticmethod
    def random_delay(min_ms: int = 100, max_ms: int = 500):
        """Add random delay"""
        time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

    @staticmethod
    def human_type(page: Page, selector: str, text: str, wpm_min: int = 320, wpm_max: int = 480):
        """Type with human-like speed"""
        element = page.query_selector(selector)
        if not element:
            # Try waiting if not immediately found
            try:
                element = page.wait_for_selector(selector, timeout=2000)
            except:
                pass
        
        if not element:
            print(f"⚠️ Element not found for typing: {selector}")
            return

        # Click to focus
        element.click()

        # Type via page-level keyboard. Typing on the stored ElementHandle
        # fails against NotebookLM's current UI because the textarea is
        # re-rendered on first keystroke (React re-mount), which detaches
        # the handle and raises `ElementHandle.type: Element is not attached
        # to the DOM`. page.keyboard.type targets whatever element has
        # focus at the moment of the keystroke, so it survives re-renders.
        for char in text:
            page.keyboard.type(char, delay=random.uniform(25, 75))
            if random.random() < 0.05:
                time.sleep(random.uniform(0.15, 0.4))

    @staticmethod
    def realistic_click(page: Page, selector: str):
        """Click with realistic movement"""
        element = page.query_selector(selector)
        if not element:
            return

        # Optional: Move mouse to element (simplified)
        box = element.bounding_box()
        if box:
            x = box['x'] + box['width'] / 2
            y = box['y'] + box['height'] / 2
            page.mouse.move(x, y, steps=5)

        StealthUtils.random_delay(100, 300)
        element.click()
        StealthUtils.random_delay(100, 300)


# Reads the bot message right after the question at the given index. NotebookLM
# puts a collapsible "Thoughts" header (thinking-chain-view) in front of the answer
# body, and while generating only this header is present, so it is left out
_ANSWER_AFTER_QUESTION_JS = """
index => {
    const messages = document.querySelectorAll('.from-user-container, .to-user-container');
    let questionIndex = -1;
    for (const message of messages) {
        if (message.classList.contains('from-user-container')) {
            questionIndex += 1;
            if (questionIndex > index) return '';
            continue;
        }
        if (questionIndex !== index) continue;
        const body = message.querySelector('.message-text-content') || message;
        const clone = body.cloneNode(true);
        clone.querySelectorAll('thinking-chain-view').forEach(node => node.remove());
        return clone.innerText.trim();
    }
    return '';
}
"""


class ChatUtils:
    """Locate the answer to a question in the NotebookLM chat"""

    MESSAGE_SELECTOR = ".from-user-container, .to-user-container"
    QUESTION_SELECTOR = ".from-user-container"

    @staticmethod
    def wait_for_history(page: Page, stable_polls: int = 3, timeout_seconds: int = 20) -> None:
        """Wait until the number of rendered chat messages stops changing

        Past messages are rendered several seconds after the input appears.
        Counting questions or typing before that mixes old answers into the
        new one and can drop typed characters (#25)
        """
        last_count = -1
        stable = 0
        deadline = time.time() + timeout_seconds
        while time.time() < deadline and stable < stable_polls:
            count = len(page.query_selector_all(ChatUtils.MESSAGE_SELECTOR))
            stable = stable + 1 if count == last_count else 0
            last_count = count
            time.sleep(1)

    @staticmethod
    def count_questions(page: Page) -> int:
        """Count the questions currently shown in the chat"""
        return len(page.query_selector_all(ChatUtils.QUESTION_SELECTOR))

    @staticmethod
    def answer_after_question(page: Page, index: int) -> str:
        """Return the answer to the question at index, or an empty string if not yet shown"""
        return page.evaluate(_ANSWER_AFTER_QUESTION_JS, index)
