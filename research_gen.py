"""Wikipedia research fetcher for chronicle-forge.

Searches Wikipedia for the given topic, fetches intro extracts from the top
results, and returns a condensed research bundle for the script generator.
"""
import requests
from dotenv import load_dotenv

load_dotenv()

WIKI_API          = "https://en.wikipedia.org/w/api.php"
MAX_SOURCES       = 3
MAX_EXTRACT_CHARS = 8000   # full article body — much richer than intro-only

# Wikimedia policy requires a descriptive User-Agent; generic or missing UA → 403
WIKI_HEADERS = {
    "User-Agent": "chronicle-forge/1.0 (AI documentary generator) python-requests"
}


def _search_wikipedia(topic: str) -> list:
    params = {
        "action": "query",
        "list":   "search",
        "srsearch": topic,
        "format": "json",
        "srlimit": MAX_SOURCES,
    }
    resp = requests.get(WIKI_API, params=params, headers=WIKI_HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()["query"]["search"]


def _fetch_page(title: str) -> dict:
    params = {
        "action":      "query",
        "titles":      title,
        "prop":        "extracts|info",
        # exintro omitted — fetch the full article body, not just the lead section.
        # Story generation needs narrative detail: specific events, people, causes,
        # consequences — all buried after the intro in Wikipedia articles.
        "explaintext": True,
        "inprop":      "url",
        "format":      "json",
        "redirects":   True,
    }
    resp = requests.get(WIKI_API, params=params, headers=WIKI_HEADERS, timeout=10)
    resp.raise_for_status()
    pages = resp.json()["query"]["pages"]
    page  = next(iter(pages.values()))
    extract = page.get("extract", "")
    if "missing" in page or not extract.strip():
        raise ValueError(f"No usable article text for {title!r}")
    if len(extract) > MAX_EXTRACT_CHARS:
        extract = extract[:MAX_EXTRACT_CHARS] + "…"
    return {
        "title":   page.get("title", title),
        "extract": extract,
        "url":     page.get("fullurl",
                            f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"),
    }


def fetch_research(topic: str, verbose: bool = False) -> dict:
    """
    Search Wikipedia for the topic and return a research bundle.

    Returns:
        {
          "summary": str,                        # concatenated extract text for LLM
          "sources": [{"title": str, "url": str}, ...]   # for YouTube description
        }
    """
    print(f"  Searching Wikipedia: {topic!r}...")
    try:
        results = _search_wikipedia(topic)
    except Exception as exc:
        raise RuntimeError("Research search failed; refusing to generate an unsourced story.") from exc

    if not results:
        raise RuntimeError("No research results; refine the topic before generating a story.")

    pages = []
    for r in results:
        if verbose:
            print(f"  Fetching: {r['title']!r}")
        try:
            page = _fetch_page(r["title"])
            pages.append(page)
        except Exception as exc:
            print(f"  Warning: failed to fetch {r['title']!r}: {exc}")

    if not pages:
        raise RuntimeError("No usable research pages; retry before generating a story.")

    summary_parts = []
    sources       = []
    for p in pages:
        summary_parts.append(f"=== {p['title']} ===\n{p['extract']}")
        sources.append({"title": p["title"], "url": p["url"]})

    summary = "\n\n".join(summary_parts)
    print(f"  Found {len(pages)} source(s): {', '.join(p['title'] for p in pages)}")
    return {"summary": summary, "sources": sources}
