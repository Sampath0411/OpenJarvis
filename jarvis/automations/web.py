"""Web automations — open sites, web search, quick weather, wikipedia lookups."""
from __future__ import annotations

import urllib.parse
import webbrowser

import requests

from .registry import tool


@tool(
    name="open_website",
    description=(
        "Open a URL in the default browser. Use this ONLY for explicit website/URL "
        "requests (e.g. 'open https://github.com', 'open google.com'). For things like "
        "'open chrome', 'open leave.txt', or 'open videos in file explorer', use "
        "'smart_open' instead."
    ),
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string", "description": "URL or domain to open."}},
        "required": ["url"],
    },
)
def open_website(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}"


@tool(
    name="web_search",
    description="Open a Google search for a query in the browser.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
def web_search(query: str) -> str:
    q = urllib.parse.quote_plus(query)
    webbrowser.open(f"https://www.google.com/search?q={q}")
    return f"Searching the web for: {query}"


@tool(
    name="play_youtube",
    description="Search and open YouTube results for a song or video.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
def play_youtube(query: str) -> str:
    q = urllib.parse.quote_plus(query)
    webbrowser.open(f"https://www.youtube.com/results?search_query={q}")
    return f"Opening YouTube for: {query}"


@tool(
    name="get_weather",
    description="Get current weather for a city (uses the free wttr.in service, no API key).",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
)
def get_weather(city: str) -> str:
    try:
        r = requests.get(f"https://wttr.in/{urllib.parse.quote(city)}?format=3", timeout=10)
        if r.ok:
            return r.text.strip()
        return f"Weather service returned {r.status_code}."
    except requests.RequestException as exc:
        return f"Couldn't fetch weather: {exc}"


@tool(
    name="wikipedia",
    description="Get a short summary of a topic from Wikipedia.",
    parameters={
        "type": "object",
        "properties": {"topic": {"type": "string"}},
        "required": ["topic"],
    },
)
def wikipedia(topic: str) -> str:
    slug = urllib.parse.quote(topic.replace(" ", "_"))
    try:
        r = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}", timeout=10
        )
        if r.ok:
            data = r.json()
            return data.get("extract", "No summary found.")
        return f"Wikipedia returned {r.status_code} for '{topic}'."
    except requests.RequestException as exc:
        return f"Couldn't reach Wikipedia: {exc}"
