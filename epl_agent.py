"""
EPL Search Agent
================
A simple agent that searches the web for the latest English Premier League
results, summarises match highlights, and displays the current table standings.

Usage:
    python epl_agent.py

The agent performs four steps:
  1. Google-search for the latest EPL match results
  2. Extract and display scores from the search results
  3. Google-search for the current EPL league table
  4. Extract and display the standings + key highlights
"""

import re
import sys
import time
import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds – doubles each retry


# ---------------------------------------------------------------------------
# Networking helpers
# ---------------------------------------------------------------------------


def _request_with_retry(url: str, params: dict | None = None,
                        max_chars: int = 0) -> requests.Response:
    """GET *url* with automatic retries on transient failures."""
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            wait = RETRY_BACKOFF * (2 ** (attempt - 1))
            print(f"    [retry {attempt}/{MAX_RETRIES}] connection error, "
                  f"waiting {wait}s ...")
            time.sleep(wait)
        except requests.HTTPError as exc:
            raise  # non-transient – don't retry
    raise last_exc  # type: ignore[misc]


def google_search(query: str, num_results: int = 10) -> list[dict]:
    """
    Perform a Google search and return a list of result dicts with
    'title', 'link', and 'snippet' keys.
    """
    params = {"q": query, "num": num_results, "hl": "en"}
    resp = _request_with_retry("https://www.google.com/search", params=params)
    soup = BeautifulSoup(resp.text, "html.parser")

    results = []
    for g in soup.select("div.g, div.tF2Cxc"):
        title_el = g.select_one("h3")
        link_el = g.select_one("a[href]")
        snippet_el = g.select_one("div.VwiC3b, span.aCOpRe, div.IsZvec")
        if title_el and link_el:
            results.append({
                "title": title_el.get_text(strip=True),
                "link": link_el["href"],
                "snippet": (snippet_el.get_text(strip=True)
                            if snippet_el else ""),
            })
    return results[:num_results]


def fetch_page_text(url: str, max_chars: int = 15000) -> str:
    """Fetch a URL and return its visible text content, truncated."""
    try:
        resp = _request_with_retry(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:max_chars]
    except Exception as exc:
        return f"[Could not fetch page: {exc}]"


# ---------------------------------------------------------------------------
# Agent search actions
# ---------------------------------------------------------------------------


def search_epl_results() -> str:
    """Search Google for the latest EPL match results and return raw text."""
    queries = [
        "English Premier League latest results today 2025",
        "EPL match results this week scores",
    ]
    collected: list[str] = []
    seen_links: set[str] = set()

    for query in queries:
        try:
            results = google_search(query)
        except Exception as exc:
            collected.append(f"[Search failed for '{query}': {exc}]")
            continue

        for r in results:
            if r["link"] not in seen_links:
                seen_links.add(r["link"])
                collected.append(f"### {r['title']}\n{r['snippet']}\n")

        # Fetch full page text from top 2 results for richer data
        for r in results[:2]:
            if r["link"].startswith("http"):
                page = fetch_page_text(r["link"], max_chars=8000)
                collected.append(
                    f"--- Content from {r['title']} ---\n{page}\n")

    return "\n".join(collected)


def search_epl_standings() -> str:
    """Search Google for the current EPL table standings and return raw text."""
    queries = [
        "Premier League table standings 2024-25",
        "EPL table 2025 current standings points",
    ]
    collected: list[str] = []
    seen_links: set[str] = set()

    for query in queries:
        try:
            results = google_search(query)
        except Exception as exc:
            collected.append(f"[Search failed for '{query}': {exc}]")
            continue

        for r in results:
            if r["link"] not in seen_links:
                seen_links.add(r["link"])
                collected.append(f"### {r['title']}\n{r['snippet']}\n")

        for r in results[:2]:
            if r["link"].startswith("http"):
                page = fetch_page_text(r["link"], max_chars=8000)
                collected.append(
                    f"--- Content from {r['title']} ---\n{page}\n")

    return "\n".join(collected)


# ---------------------------------------------------------------------------
# Summarisation / extraction (regex-based, no LLM dependency)
# ---------------------------------------------------------------------------


def extract_scores(text: str) -> list[str]:
    """
    Extract lines that look like football scores, e.g.
    'Arsenal 2-1 Chelsea', 'Man City 3 - 0 Everton'.
    """
    pattern = re.compile(
        r"([A-Z][A-Za-z\s\.&']+?)\s+(\d+)\s*[-–]\s*(\d+)\s+"
        r"([A-Z][A-Za-z\s\.&']+)"
    )
    matches = pattern.findall(text)
    scores: list[str] = []
    for home, hg, ag, away in matches:
        home, away = home.strip(), away.strip()
        if len(home) > 3 and len(away) > 3:
            scores.append(f"  {home} {hg} - {ag} {away}")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for s in scores:
        key = re.sub(r"\s+", " ", s.strip().lower())
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


def extract_table_rows(text: str) -> list[str]:
    """
    Extract table-like rows:  Pos  Team  Played  Won  Drawn  Lost  …  Points
    """
    rows: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        m = re.match(
            r"(\d{1,2})[.\s)]+([A-Za-z\s\.&']+?)\s+"
            r"(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+"
            r".*?(\d{1,3})\s*$",
            line,
        )
        if m:
            pos, team, played, won, drawn, lost, pts = m.groups()
            rows.append(
                f"  {pos:>2}. {team.strip():<25s}  P:{played:>2}  "
                f"W:{won:>2}  D:{drawn:>2}  L:{lost:>2}  Pts:{pts:>3}"
            )

    seen: set[str] = set()
    unique: list[str] = []
    for r in rows:
        key = r.strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def extract_highlights(text: str) -> list[str]:
    """Pull out lines that contain notable football keywords."""
    keywords = [
        "goal", "winner", "defeat", "victory", "draw", "injury",
        "red card", "penalty", "hat-trick", "clean sheet", "comeback",
        "top scorer", "unbeaten", "record", "manager", "sacked",
    ]
    highlights: list[str] = []
    seen: set[str] = set()
    for line in text.split("\n"):
        stripped = line.strip()
        if len(stripped) < 30:
            continue
        low = stripped.lower()
        for kw in keywords:
            if kw in low and stripped not in seen:
                seen.add(stripped)
                highlights.append(stripped[:150])
                break
    return highlights[:10]


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

DIVIDER = "-" * 64


def _print_section(title: str):
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


def _print_raw_fallback(text: str, max_lines: int = 25):
    """Print raw text lines when structured extraction yields nothing."""
    printed = 0
    for line in text.split("\n"):
        line = line.strip()
        if line and not line.startswith("---") and not line.startswith("###"):
            print(f"  {line[:120]}")
            printed += 1
            if printed >= max_lines:
                break
    if printed == 0:
        print("  (no data available)")


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------


def run_agent():
    print("=" * 64)
    print("  EPL SEARCH AGENT")
    print("  Searching for the latest Premier League information ...")
    print("=" * 64)

    # ------------------------------------------------------------------
    # Step 1 – Search for recent results
    # ------------------------------------------------------------------
    print("\n[1/4] Searching for latest EPL match results ...")
    results_text = search_epl_results()

    # ------------------------------------------------------------------
    # Step 2 – Extract & display scores
    # ------------------------------------------------------------------
    print("[2/4] Extracting match scores ...")
    scores = extract_scores(results_text)

    _print_section("LATEST EPL MATCH RESULTS")
    if scores:
        for s in scores[:20]:
            print(s)
    else:
        print("  (Could not parse individual scores "
              "– showing raw search snippets)\n")
        _print_raw_fallback(results_text)

    # ------------------------------------------------------------------
    # Step 3 – Search for table standings
    # ------------------------------------------------------------------
    print(f"\n[3/4] Searching for EPL table standings ...")
    standings_text = search_epl_standings()

    # ------------------------------------------------------------------
    # Step 4 – Extract & display standings table
    # ------------------------------------------------------------------
    print("[4/4] Extracting table standings ...")
    table_rows = extract_table_rows(standings_text)

    _print_section("EPL TABLE STANDINGS (2024-25 Season)")
    if table_rows:
        print(f"  {'#':>2}  {'Team':<25s}  {'P':>2}  {'W':>2}  "
              f"{'D':>2}  {'L':>2}  {'Pts':>3}")
        print("  " + "-" * 55)
        for r in table_rows[:20]:
            print(r)
    else:
        print("  (Could not parse a structured table "
              "– showing raw search snippets)\n")
        _print_raw_fallback(standings_text)

    # ------------------------------------------------------------------
    # Highlights
    # ------------------------------------------------------------------
    _print_section("KEY HIGHLIGHTS")
    combined = results_text + "\n" + standings_text
    highlights = extract_highlights(combined)
    if highlights:
        for i, h in enumerate(highlights, 1):
            print(f"  {i}. {h}")
    else:
        print("  No specific highlights extracted from search results.")

    print("\n" + "=" * 64)
    print("  Agent finished. Data sourced from Google Search.")
    print("=" * 64)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        run_agent()
    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
        sys.exit(0)
    except Exception as exc:
        print(f"\n  Agent error: {exc}")
        print("  Make sure you have internet access and "
              "the required packages installed:")
        print("    pip install requests beautifulsoup4")
        sys.exit(1)
