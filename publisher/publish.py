"""Publish one explicitly allowed page through Liquipedia's bot API."""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


API_URL = "https://liquipedia.net/geoguessr/api.php"
MANAGED_TEST_MARKER = "<!-- LOWLANDS_LEAGUE_MANAGED_TEST_PAGE -->"
MIN_REQUEST_INTERVAL_SECONDS = 15.0
MAX_WIKICODE_BYTES = 200_000


class PublishError(RuntimeError):
    """A safe, user-facing publisher error."""


@dataclass(frozen=True)
class Config:
    username: str
    password: str
    contact: str
    page_title: str
    wikicode: str
    edit_summary: str
    allowed_titles: frozenset[str]


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise PublishError(f"Required environment value {name} is missing.")
    return value


def load_config() -> Config:
    encoded = required_env("INPUT_CONTENT_B64")
    try:
        raw = base64.b64decode(encoded, validate=True)
        wikicode = raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise PublishError("The supplied wikicode is not valid UTF-8 base64.") from exc

    if len(raw) > MAX_WIKICODE_BYTES:
        raise PublishError(
            f"The wikicode is {len(raw)} bytes; the safety limit is "
            f"{MAX_WIKICODE_BYTES} bytes."
        )

    allowed = frozenset(
        title.strip()
        for title in required_env("LIQUIPEDIA_ALLOWED_TITLES").split("|")
        if title.strip()
    )
    page_title = required_env("INPUT_PAGE_TITLE")
    if page_title not in allowed:
        raise PublishError(
            f"Safety stop: {page_title!r} is not in LIQUIPEDIA_ALLOWED_TITLES."
        )
    if page_title == "User:DialloBOT/test" and not wikicode.startswith(
        MANAGED_TEST_MARKER
    ):
        raise PublishError("The managed test-page marker is missing from the wikicode.")

    return Config(
        username=required_env("LIQUIPEDIA_BOT_USERNAME"),
        password=required_env("LIQUIPEDIA_BOT_PASSWORD"),
        contact=required_env("LIQUIPEDIA_CONTACT"),
        page_title=page_title,
        wikicode=wikicode,
        edit_summary=required_env("INPUT_EDIT_SUMMARY"),
        allowed_titles=allowed,
    )


class LiquipediaClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": f"LowlandsLeagueBot/1.0 ({config.contact})",
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
            }
        )
        self._last_request_at = 0.0

    def _request(self, method: str, **kwargs: Any) -> dict[str, Any]:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)

        try:
            response = self.session.request(
                method,
                API_URL,
                timeout=(15, 60),
                **kwargs,
            )
        except requests.RequestException as exc:
            raise PublishError(f"Liquipedia request failed: {exc}") from exc
        finally:
            self._last_request_at = time.monotonic()

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "not supplied")
            raise PublishError(
                "Liquipedia returned HTTP 429. No retry was attempted; "
                f"Retry-After: {retry_after}."
            )
        if not response.ok:
            raise PublishError(
                f"Liquipedia returned HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
        try:
            data = response.json()
        except requests.JSONDecodeError as exc:
            raise PublishError("Liquipedia returned a non-JSON response.") from exc
        if "error" in data:
            error = data["error"]
            raise PublishError(
                f"Liquipedia API error {error.get('code', 'unknown')}: "
                f"{error.get('info', 'No details supplied.')}"
            )
        return data

    def _get_login_token(self) -> str:
        data = self._request(
            "GET",
            params={
                "action": "query",
                "meta": "tokens",
                "type": "login",
                "format": "json",
                "formatversion": "2",
            },
        )
        token = data.get("query", {}).get("tokens", {}).get("logintoken")
        if not token:
            raise PublishError("Liquipedia did not return a login token.")
        return str(token)

    def login(self) -> dict[str, Any]:
        login = self._request(
            "POST",
            data={
                "action": "login",
                "lgname": self.config.username,
                "lgpassword": self.config.password,
                "lgtoken": self._get_login_token(),
                "format": "json",
                "formatversion": "2",
            },
        ).get("login", {})

        if login.get("result") != "Success" and "@" in self.config.username:
            account, bot_name = self.config.username.rsplit("@", 1)
            login = self._request(
                "POST",
                data={
                    "action": "login",
                    "lgname": account,
                    "lgpassword": f"{bot_name}@{self.config.password}",
                    "lgtoken": self._get_login_token(),
                    "format": "json",
                    "formatversion": "2",
                },
            ).get("login", {})

        if login.get("result") != "Success":
            reason = login.get("reason") or login.get("result") or "unknown response"
            raise PublishError(f"Liquipedia login failed: {reason}")

        data = self._request(
            "GET",
            params={
                "action": "query",
                "meta": "userinfo",
                "uiprop": "groups|rights",
                "format": "json",
                "formatversion": "2",
            },
        )
        user = data.get("query", {}).get("userinfo", {})
        if user.get("anon") is not None or not user.get("name"):
            raise PublishError("The authenticated session is anonymous.")
        if "bot" not in user.get("groups", []):
            raise PublishError(f"{user['name']} does not have the Liquipedia bot role.")
        return user

    def page_and_token(self) -> tuple[dict[str, Any], str]:
        data = self._request(
            "GET",
            params={
                "action": "query",
                "prop": "revisions",
                "meta": "tokens",
                "type": "csrf",
                "titles": self.config.page_title,
                "rvprop": "ids|timestamp|content",
                "rvslots": "main",
                "format": "json",
                "formatversion": "2",
            },
        )
        query = data.get("query", {})
        token = query.get("tokens", {}).get("csrftoken")
        pages = query.get("pages", [])
        page = pages[0] if pages else {"missing": True}
        if not token:
            raise PublishError("Liquipedia did not return a CSRF token.")
        return page, str(token)

    def publish(self) -> dict[str, Any]:
        page, token = self.page_and_token()
        exists = not page.get("missing", False)
        revision: dict[str, Any] = {}
        current_text = ""
        if exists and page.get("revisions"):
            revision = page["revisions"][0]
            current_text = (
                revision.get("slots", {}).get("main", {}).get("content", "")
            )

        if (
            exists
            and self.config.page_title == "User:DialloBOT/test"
            and MANAGED_TEST_MARKER not in current_text
        ):
            raise PublishError(
                "Safety stop: the existing test page was not created by this publisher."
            )
        if current_text == self.config.wikicode:
            return {"result": "NoChange", "oldrevid": revision.get("revid")}

        payload: dict[str, str] = {
            "action": "edit",
            "title": self.config.page_title,
            "text": self.config.wikicode,
            "summary": self.config.edit_summary,
            "token": token,
            "assert": "user",
            "maxlag": "5",
            "bot": "1",
            "watchlist": "nochange",
            "format": "json",
            "formatversion": "2",
        }
        if exists:
            payload["baserevid"] = str(revision.get("revid", ""))
            if revision.get("timestamp"):
                payload["basetimestamp"] = str(revision["timestamp"])
        else:
            payload["createonly"] = "1"

        edit = self._request("POST", data=payload).get("edit", {})
        if edit.get("result") != "Success":
            raise PublishError(
                f"Liquipedia did not confirm the edit: {edit.get('result', 'unknown')}"
            )
        return edit


def append_step_summary(config: Config, user: dict[str, Any], edit: dict[str, Any]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    result = edit.get("result", "unknown")
    revision = edit.get("newrevid") or edit.get("oldrevid") or "unchanged"
    text = (
        "## Liquipedia publication\n\n"
        f"- Account: `{user.get('name', 'unknown')}`\n"
        f"- Page: `{config.page_title}`\n"
        f"- Result: `{result}`\n"
        f"- Revision: `{revision}`\n"
    )
    Path(summary_path).write_text(text, encoding="utf-8")


def main() -> int:
    try:
        config = load_config()
        client = LiquipediaClient(config)
        user = client.login()
        edit = client.publish()
        append_step_summary(config, user, edit)
        print(
            json.dumps(
                {
                    "ok": True,
                    "page": config.page_title,
                    "result": edit.get("result"),
                    "revision": edit.get("newrevid") or edit.get("oldrevid"),
                }
            )
        )
        return 0
    except PublishError as exc:
        print(f"::error::{exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
