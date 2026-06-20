# -*- coding: utf-8 -*-
"""
ThreadIntel Research Engine
Aggregates data from multiple sources for a given topic.

Sources:
  1. Reddit       — PRAW (real discussions, sentiment, pain points)
  2. Hacker News  — Algolia API (tech community, free, no auth)
  3. Google News  — RSS feed (recent news headlines, free, no key)
  4. DuckDuckGo   — instant results (general web, free, no key)
  5. Stack Exchange — API (tech/dev topics, free)
  6. Product Hunt  — GraphQL API (product launches, free)

Returns: structured dict of raw findings passed to email_brief.py for formatting.

Run standalone:
  python threadintel/research.py "your topic"
"""

import os, sys, json, re, time, logging
from pathlib import Path
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

log = logging.getLogger("threadintel.research")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

HEADERS = {"User-Agent": "ThreadIntel Research/1.0 (contact: syed.aayan.rehman@gmail.com)"}
TIMEOUT = 12


def _with_retry(fn, retries=2, backoff=2.0):
    """Run fn() with simple exponential backoff on failure."""
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < retries:
                wait = backoff ** attempt
                log.warning("Retry %d/%d after %.1fs — %s", attempt + 1, retries, wait, e)
                time.sleep(wait)
    raise last_exc

# Subreddit suggestions by topic keyword
_SUBREDDIT_MAP = {
    "marketing":        ["marketing", "digital_marketing", "SEO", "PPC"],
    "saas":             ["SaaS", "startups", "entrepreneur", "microsaas"],
    "startup":          ["startups", "entrepreneur", "SideProject", "IndieHackers"],
    "product":          ["ProductManagement", "startups", "SaaS"],
    "developer":        ["programming", "webdev", "devops", "ExperiencedDevs"],
    "ai":               ["artificial", "MachineLearning", "LocalLLaMA", "ChatGPT"],
    "ecommerce":        ["ecommerce", "Entrepreneur", "dropship", "AmazonSeller"],
    "finance":          ["personalfinance", "investing", "financialindependence"],
    "crypto":           ["CryptoCurrency", "Bitcoin", "ethereum", "defi"],
    "design":           ["graphic_design", "UI_Design", "web_design", "UXDesign"],
    "sales":            ["sales", "b2b", "entrepreneur"],
    "hr":               ["humanresources", "recruiting", "jobs"],
    "security":         ["netsec", "cybersecurity", "sysadmin"],
    "data":             ["datascience", "MachineLearning", "dataengineering"],
    "content":          ["content_marketing", "blogging", "copywriting"],
}

_STOP_WORDS = {
    "what", "are", "is", "do", "does", "how", "why", "when", "where", "which",
    "people", "users", "customers", "developers", "founders", "saying", "think",
    "about", "with", "from", "that", "this", "the", "and", "for", "in", "on",
    "at", "to", "of", "a", "an", "their", "right", "currently",
    "reddit", "hackernews", "hacker", "news",
    # Note: year numbers (2024, 2025, 2026) intentionally NOT here — they improve
    # recency relevance in Google News and HN searches
}

def extract_search_terms(topic: str, max_words: int = 6) -> str:
    """Extract the most meaningful search keywords from a verbose topic."""
    words = re.findall(r'\b[a-zA-Z]{2,}\b', topic)
    keywords = [w for w in words if w.lower() not in _STOP_WORDS]
    return " ".join(keywords[:max_words]) or topic[:50]


def suggest_subreddits(topic: str) -> list:
    """Return relevant subreddits for a topic based on keyword matching."""
    t = topic.lower()
    subs = []
    for kw, subreddit_list in _SUBREDDIT_MAP.items():
        if kw in t:
            subs.extend(subreddit_list)
    return list(dict.fromkeys(subs))[:4]  # dedupe, max 4

# ─────────────────────────────────────────────
# SOURCE 1: REDDIT
# ─────────────────────────────────────────────

def search_reddit(topic, limit=40, subreddits=None, time_filter="all"):
    """
    Search Reddit via PRAW (authenticated) or public JSON fallback.
    subreddits: list of subreddit names to target, e.g. ['marketing', 'SaaS']
                If None, auto-suggests based on topic keywords.
    time_filter: 'all' | 'year' | 'month' | 'week' | 'day'
    """
    results = []
    client_id     = os.getenv("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.getenv("REDDIT_SECRET", "").strip()
    user_agent    = os.getenv("REDDIT_USER_AGENT", "ThreadIntel/1.0").strip()

    # Auto-suggest subreddits if none specified
    if subreddits is None:
        subreddits = suggest_subreddits(topic)

    sub_target = "+".join(subreddits) if subreddits else "all"

    search_query = extract_search_terms(topic)

    try:
        if client_id and client_secret:
            import praw
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
            target = reddit.subreddit(sub_target)
            for post in target.search(search_query, sort="relevance", time_filter=time_filter, limit=limit):
                results.append({
                    "source":    "Reddit",
                    "subreddit": post.subreddit.display_name,
                    "title":     post.title,
                    "text":      (post.selftext or "")[:500],
                    "score":     post.score,
                    "comments":  post.num_comments,
                    "url":       f"https://reddit.com{post.permalink}",
                    "date":      datetime.fromtimestamp(post.created_utc).strftime("%b %Y"),
                })
        else:
            # PullPush fallback (free Reddit archive API — no auth needed)
            import time as _time
            time_map    = {"week": 7, "month": 30, "year": 365, "day": 1}
            after_param = (f"&after={int(_time.time()) - time_map[time_filter]*86400}"
                           if time_filter in time_map else "")
            q = requests.utils.quote(search_query)

            # Search globally first, then optionally per-subreddit
            targets = [""] + ([f"&subreddit={s}" for s in (subreddits or [])[:2]])
            per     = max(limit // max(len(targets), 1), 5)
            seen    = set()
            for sub_param in targets:
                url = (f"https://api.pullpush.io/reddit/search/submission/"
                       f"?q={q}&size={per}&sort_type=score{sub_param}{after_param}")
                try:
                    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                    if r.status_code != 200:
                        continue
                    for p in r.json().get("data", []):
                        pid = p.get("id", "")
                        if pid in seen:
                            continue
                        seen.add(pid)
                        results.append({
                            "source":    "Reddit",
                            "subreddit": p.get("subreddit", ""),
                            "title":     p.get("title", ""),
                            "text":      (p.get("selftext") or "")[:500],
                            "score":     p.get("score", 0),
                            "comments":  p.get("num_comments", 0),
                            "url":       f"https://reddit.com{p.get('permalink', '')}",
                            "date":      datetime.fromtimestamp(p.get("created_utc", 0)).strftime("%b %Y"),
                        })
                except Exception:
                    continue
    except Exception as e:
        print(f"  Reddit: {e}")

    print(f"  Reddit: {len(results)} posts found (subreddits: {sub_target}, time: {time_filter})")
    return results


# ─────────────────────────────────────────────
# SOURCE 2: HACKER NEWS (Algolia API — free, no auth)
# ─────────────────────────────────────────────

def search_hackernews(topic, limit=20, days_ago=None):
    """
    Search Hacker News via Algolia API. Free, no key.
    days_ago: restrict to posts from last N days (e.g. 7 for this week)
    """
    results = []
    try:
        url = "https://hn.algolia.com/api/v1/search"
        params = {"query": extract_search_terms(topic), "hitsPerPage": limit, "tags": "story"}
        if days_ago:
            cutoff = int((datetime.utcnow() - timedelta(days=days_ago)).timestamp())
            params["numericFilters"] = f"created_at_i>{cutoff}"
        r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            for hit in r.json().get("hits", []):
                results.append({
                    "source":   "Hacker News",
                    "title":    hit.get("title", ""),
                    "text":     (hit.get("story_text") or "")[:400],
                    "score":    hit.get("points", 0),
                    "comments": hit.get("num_comments", 0),
                    "url":      hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                    "date":     hit.get("created_at", "")[:7],
                })
    except Exception as e:
        print(f"  Hacker News: {e}")

    print(f"  Hacker News: {len(results)} stories found")
    return results


# ─────────────────────────────────────────────
# SOURCE 3: GOOGLE NEWS RSS (free, no key)
# ─────────────────────────────────────────────

def search_news(topic, limit=15, days_ago=None):
    """Pull recent news via Google News RSS. No API key required."""
    results = []
    try:
        import xml.etree.ElementTree as ET
        seen_titles = set()

        # Map days_ago → Google News 'when' parameter
        when_param = ""
        if days_ago:
            if days_ago <= 7:
                when_param = "&when=7d"
            elif days_ago <= 30:
                when_param = "&when=1m"
            elif days_ago <= 180:
                when_param = "&when=6m"

        # Run two queries: one with clean keywords, one with original topic for coverage
        keywords = extract_search_terms(topic, max_words=6)
        queries = list(dict.fromkeys([keywords, topic[:80]]))  # dedupe if same

        for q in queries:
            encoded = requests.utils.quote(q)
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en{when_param}"
            try:
                r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                if r.status_code != 200:
                    continue
                root = ET.fromstring(r.content)
                for item in root.findall(".//item")[:limit]:
                    title   = item.findtext("title", "").split(" - ")[0]
                    fp      = re.sub(r"[^a-z0-9]", "", title.lower())[:50]
                    if fp in seen_titles:
                        continue
                    seen_titles.add(fp)
                    link    = item.findtext("link", "")
                    pubdate = item.findtext("pubDate", "")
                    desc    = re.sub(r"<[^>]+>", "", item.findtext("description", ""))[:400]
                    results.append({
                        "source": "News",
                        "title":  title,
                        "text":   desc,
                        "url":    link,
                        "date":   pubdate[:16] if pubdate else "",
                        "score":  0,
                    })
            except Exception:
                continue

    except Exception as e:
        print(f"  News: {e}")

    print(f"  News: {len(results)} articles found")
    return results


# ─────────────────────────────────────────────
# SOURCE 4: DUCKDUCKGO SEARCH (free, no key)
# ─────────────────────────────────────────────

def search_web(topic, limit=10):
    """General web search via DuckDuckGo (ddgs package). Free, no API key."""
    results = []
    try:
        from ddgs import DDGS
        q = extract_search_terms(topic, max_words=8)
        with DDGS() as ddgs:
            for hit in ddgs.text(q, max_results=limit):
                results.append({
                    "source": "Web (DuckDuckGo)",
                    "title":  hit.get("title", ""),
                    "text":   hit.get("body", "")[:500],
                    "url":    hit.get("href", ""),
                    "date":   "",
                    "score":  0,
                })
    except ImportError:
        print("  Web: install 'ddgs' package to enable (pip install ddgs)")
    except Exception as e:
        print(f"  DuckDuckGo: {e}")

    print(f"  Web: {len(results)} results found")
    return results


# ─────────────────────────────────────────────
# SOURCE 5: STACK EXCHANGE (free, no auth for read)
# ─────────────────────────────────────────────

def search_stackoverflow(topic, limit=10):
    """Search Stack Overflow/Exchange. Best for tech topics. Free, no auth needed."""
    results = []
    try:
        url = "https://api.stackexchange.com/2.3/search/advanced"
        params = {
            "q":       extract_search_terms(topic, max_words=6),
            "site":    "stackoverflow",
            "sort":    "relevance",
            "order":   "desc",
            "pagesize": limit,
            "filter":  "withbody",
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            for item in r.json().get("items", []):
                body = re.sub(r"<[^>]+>", "", item.get("body", ""))[:400]
                results.append({
                    "source":   "Stack Overflow",
                    "title":    item.get("title", ""),
                    "text":     body,
                    "score":    item.get("score", 0),
                    "url":      item.get("link", ""),
                    "date":     datetime.fromtimestamp(item.get("creation_date", 0)).strftime("%b %Y"),
                    "answered": item.get("is_answered", False),
                })
    except Exception as e:
        print(f"  Stack Overflow: {e}")

    print(f"  Stack Overflow: {len(results)} questions found")
    return results


# ─────────────────────────────────────────────
# SOURCE 6: PRODUCT HUNT (GraphQL, free)
# ─────────────────────────────────────────────

def search_producthunt(topic, limit=8):
    """Search Product Hunt via GraphQL API. Free dev token."""
    results = []
    ph_token = os.getenv("PRODUCTHUNT_TOKEN", "").strip()
    if not ph_token:
        print("  Product Hunt: skipped (no PRODUCTHUNT_TOKEN in .env)")
        return results
    try:
        url = "https://api.producthunt.com/v2/api/graphql"
        query = """
        query($q: String!) {
          posts(query: $q, first: 8) {
            edges { node {
              name tagline description
              votesCount commentsCount
              website createdAt
            }}
          }
        }"""
        headers = {**HEADERS, "Authorization": f"Bearer {ph_token}", "Content-Type": "application/json"}
        r = requests.post(url, json={"query": query, "variables": {"q": topic}},
                          headers=headers, timeout=TIMEOUT)
        if r.status_code == 200:
            for edge in r.json().get("data", {}).get("posts", {}).get("edges", []):
                node = edge["node"]
                results.append({
                    "source": "Product Hunt",
                    "title":  node.get("name", ""),
                    "text":   f"{node.get('tagline','')}. {node.get('description','')[:300]}",
                    "score":  node.get("votesCount", 0),
                    "url":    node.get("website", ""),
                    "date":   (node.get("createdAt") or "")[:7],
                })
    except Exception as e:
        print(f"  Product Hunt: {e}")

    print(f"  Product Hunt: {len(results)} products found")
    return results


# ─────────────────────────────────────────────
# SOURCE 7: NEWSAPI (100 req/day free tier)
# ─────────────────────────────────────────────

def search_newsapi(topic, limit=10):
    """Search NewsAPI for structured news. Free tier: 100 requests/day."""
    results = []
    api_key = os.getenv("NEWSAPI_KEY", "").strip()
    if not api_key:
        print("  NewsAPI: skipped (no NEWSAPI_KEY in .env — get free key at newsapi.org)")
        return results
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q":        topic,
            "sortBy":   "relevancy",
            "pageSize": limit,
            "language": "en",
            "apiKey":   api_key,
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            for art in r.json().get("articles", []):
                results.append({
                    "source":    f"News ({art.get('source', {}).get('name', 'Unknown')})",
                    "title":     art.get("title", ""),
                    "text":      (art.get("description") or "")[:400],
                    "url":       art.get("url", ""),
                    "date":      (art.get("publishedAt") or "")[:10],
                    "score":     0,
                })
    except Exception as e:
        print(f"  NewsAPI: {e}")

    print(f"  NewsAPI: {len(results)} articles found")
    return results


def search_indiehackers(topic, limit=8):
    """Scrape IndieHackers posts/discussions for a topic using DuckDuckGo site: search."""
    results = []
    try:
        import urllib.parse, re
        query = urllib.parse.quote(f'site:indiehackers.com "{topic}"')
        url = f"https://html.duckduckgo.com/html/?q={query}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            print(f"  IndieHackers: HTTP {r.status_code}")
            return results
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select(".result__a")[:limit]:
            href = a.get("href", "")
            title = a.get_text(strip=True)
            # Extract real URL from DDG redirect
            m = re.search(r'uddg=(https?://[^&]+)', href)
            clean_url = urllib.parse.unquote(m.group(1)) if m else href
            if "indiehackers.com" not in clean_url:
                continue
            snippet_el = a.find_next(".result__snippet")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            results.append({
                "source":    "IndieHackers",
                "title":     title,
                "text":      snippet[:400],
                "url":       clean_url,
                "score":     0,
                "sentiment": "",
            })
    except Exception as e:
        print(f"  IndieHackers: {e}")
    print(f"  IndieHackers: {len(results)} posts found")
    return results


def search_github_issues(topic, limit=10):
    """Search GitHub Issues and Discussions for community pain points."""
    results = []
    try:
        import urllib.parse
        q = urllib.parse.quote(topic)
        # Search issues first
        url = f"https://api.github.com/search/issues?q={q}&sort=reactions&order=desc&per_page={limit}"
        headers = {**HEADERS, "Accept": "application/vnd.github+json"}
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
        if r.status_code == 200:
            for item in r.json().get("items", []):
                results.append({
                    "source":    "GitHub Issues",
                    "title":     item.get("title", ""),
                    "text":      (item.get("body") or "")[:400],
                    "url":       item.get("html_url", ""),
                    "score":     item.get("reactions", {}).get("+1", 0),
                    "comments":  item.get("comments", 0),
                    "date":      (item.get("created_at") or "")[:10],
                    "sentiment": "",
                })
        elif r.status_code == 403:
            print("  GitHub Issues: rate-limited (unauthenticated). Set GITHUB_TOKEN in .env to increase limit.")
    except Exception as e:
        print(f"  GitHub Issues: {e}")
    print(f"  GitHub Issues: {len(results)} issues found")
    return results


# ─────────────────────────────────────────────
# AGGREGATOR — run all sources
# ─────────────────────────────────────────────

def research(topic, sources=None, subreddits=None, time_filter="all", days_ago=None):
    """
    Run all sources for a topic in PARALLEL. Returns structured findings dict.

    sources:     list of source names to include, or None for all
    subreddits:  list of subreddit names to target (None = auto-detect)
    time_filter: Reddit time filter: 'all'|'year'|'month'|'week'|'day'
    days_ago:    restrict HN/News to last N days (e.g. 7)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_sources = sources or [
        "reddit", "hackernews", "news", "web",
        "stackoverflow", "producthunt", "newsapi",
        "indiehackers", "github_issues",
    ]
    print(f"\n[ThreadIntel Research Engine]")
    print(f"Topic: {topic}")
    print(f"Sources: {', '.join(all_sources)}")
    if time_filter != "all" or days_ago:
        print(f"Time filter: Reddit={time_filter}, HN/News=last {days_ago or 'all'} days")
    t0 = datetime.now()
    print(f"Started: {t0.strftime('%H:%M:%S')} (parallel)\n")

    all_source_keys = [
        "reddit", "hackernews", "news", "web",
        "stackoverflow", "producthunt", "newsapi",
        "indiehackers", "github_issues",
    ]
    findings = {
        "topic":         topic,
        "researched_at": t0.isoformat(),
        "sources_used":  [],
        **{k: [] for k in all_source_keys},
    }

    # Map source name → callable
    _runners = {
        "reddit":        lambda: search_reddit(topic, subreddits=subreddits, time_filter=time_filter),
        "hackernews":    lambda: search_hackernews(topic, days_ago=days_ago),
        "news":          lambda: search_news(topic, days_ago=days_ago),
        "web":           lambda: search_web(topic),
        "stackoverflow": lambda: search_stackoverflow(topic),
        "producthunt":   lambda: search_producthunt(topic),
        "newsapi":       lambda: search_newsapi(topic),
        "indiehackers":  lambda: search_indiehackers(topic),
        "github_issues": lambda: search_github_issues(topic),
    }

    label_map = {
        "reddit": "Reddit", "hackernews": "Hacker News",
        "news": "Google News", "web": "Web (DuckDuckGo)",
        "stackoverflow": "Stack Overflow",
        "producthunt": "Product Hunt", "newsapi": "NewsAPI",
        "indiehackers": "IndieHackers", "github_issues": "GitHub Issues",
    }

    with ThreadPoolExecutor(max_workers=9) as pool:
        futures = {
            pool.submit(_with_retry, _runners[s]): s
            for s in all_sources
            if s in _runners
        }
        for future in as_completed(futures):
            src = futures[future]
            try:
                result = future.result()
                findings[src] = result
                if result:
                    findings["sources_used"].append(label_map.get(src, src))
                    log.info("  %-15s %d results", src, len(result))
            except Exception as e:
                log.warning("  %-15s failed: %s", src, e)

    elapsed = (datetime.now() - t0).total_seconds()
    total   = sum(len(findings[s]) for s in all_source_keys)
    print(f"\nTotal: {total} results across {len(findings['sources_used'])} sources ({elapsed:.1f}s)")
    print(f"Sources: {' · '.join(sorted(findings['sources_used']))}")

    add_sentiment(findings)
    s = findings.get("sentiment_summary", {})
    print(f"Sentiment: {s.get('positive_pct',0)}% positive · {s.get('negative_pct',0)}% negative · {s.get('neutral_pct',0)}% neutral")

    return findings


# ─────────────────────────────────────────────
# SENTIMENT ANALYSIS (no external lib needed)
# ─────────────────────────────────────────────

_POSITIVE = {
    "love","great","excellent","amazing","best","perfect","awesome","fantastic",
    "useful","helpful","recommend","happy","easy","fast","good","nice","brilliant",
    "impressed","works","solved","fixed","success","simple","clear","efficient",
    "better","improved","gain","win","benefit","grow","reliable","solid","clean",
}
_NEGATIVE = {
    "hate","terrible","broken","awful","bad","worst","useless","horrible","annoying",
    "problem","issue","bug","error","fail","crash","slow","frustrating","waste",
    "disappointed","wrong","missing","lack","ugly","confusing","complicated","painful",
    "difficult","expensive","overpriced","regret","avoid","cancel","churn","quit",
    "unreliable","unstable","deprecated","dead","shutdown","abandoned","scam",
}

def _sentiment_score(text: str) -> str:
    """Return 'positive', 'negative', or 'neutral' for a text snippet."""
    if not text:
        return "neutral"
    words = set(re.findall(r"\b[a-z]+\b", text.lower()))
    pos = len(words & _POSITIVE)
    neg = len(words & _NEGATIVE)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def add_sentiment(findings: dict) -> dict:
    """
    Enrich findings by adding a 'sentiment' key to each result item
    and a top-level 'sentiment_summary' dict with counts.
    Mutates findings in-place and returns it.
    """
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    source_keys = ["reddit", "hackernews", "news", "newsapi", "web", "stackoverflow", "producthunt", "indiehackers", "github_issues"]

    for key in source_keys:
        for item in findings.get(key, []):
            combined = f"{item.get('title', '')} {item.get('text', '')}"
            s = _sentiment_score(combined)
            item["sentiment"] = s
            counts[s] += 1

    total = sum(counts.values()) or 1
    findings["sentiment_summary"] = {
        **counts,
        "positive_pct": round(counts["positive"] / total * 100),
        "negative_pct": round(counts["negative"] / total * 100),
        "neutral_pct":  round(counts["neutral"]  / total * 100),
        "overall": max(counts, key=counts.get),
    }
    return findings


def _deduplicate(items: list, key="title") -> list:
    """Remove near-duplicate items by normalising and comparing titles."""
    import re as _re
    seen = set()
    out  = []
    for item in items:
        raw = (item.get(key) or "").lower()
        # strip punctuation/spaces for fingerprint
        fp = _re.sub(r"[^a-z0-9]", "", raw)[:60]
        if fp and fp not in seen:
            seen.add(fp)
            out.append(item)
    return out


def summarise_for_prompt(findings):
    """
    Compress raw findings into a rich text block for the Groq prompt.
    - Deduplicates identical titles across sources
    - Surfaces top posts with engagement scores
    - Includes direct quote snippets so Groq can cite them
    - Provides real data stats so Groq doesn't need to hallucinate numbers
    """
    lines = []
    topic = findings.get("topic", "")
    lines.append(f"RESEARCH FINDINGS FOR: {topic}")
    lines.append(f"Sources searched: {' · '.join(findings.get('sources_used', []))}")
    lines.append(f"Date: {findings.get('researched_at', '')[:10]}")

    s = findings.get("sentiment_summary", {})
    if s:
        lines.append(
            f"Sentiment breakdown: {s.get('positive_pct',0)}% positive · "
            f"{s.get('negative_pct',0)}% negative · "
            f"{s.get('neutral_pct',0)}% neutral"
        )

    # Collect ALL items across sources, deduplicate, sort by engagement
    source_keys = ["reddit", "hackernews", "news", "newsapi", "web", "stackoverflow", "producthunt", "indiehackers", "github_issues"]
    all_items = []
    for key in source_keys:
        for item in findings.get(key, []):
            item.setdefault("_source_key", key)
            all_items.append(item)

    all_items = _deduplicate(all_items, key="title")
    total = len(all_items)
    lines.append(f"Total unique findings after deduplication: {total}")
    lines.append("")

    # Real stats Groq can reference directly
    reddit_count = len(findings.get("reddit", []))
    hn_count     = len(findings.get("hackernews", []))
    news_count   = len([i for k in ("news","newsapi") for i in findings.get(k, [])])
    if reddit_count:
        lines.append(f"DATA STAT: {reddit_count} Reddit posts found for this topic")
    if hn_count:
        lines.append(f"DATA STAT: {hn_count} Hacker News discussions found")
    if news_count:
        lines.append(f"DATA STAT: {news_count} news articles found")
    lines.append("")

    # Top posts by engagement (upvotes + comments)
    high_engagement = sorted(
        [i for i in all_items if i.get("score", 0) > 0],
        key=lambda x: (x.get("score", 0) + x.get("comments", 0) * 3),
        reverse=True,
    )[:6]

    if high_engagement:
        lines.append("=== TOP POSTS BY COMMUNITY ENGAGEMENT ===")
        for item in high_engagement:
            src   = item.get("source", "")
            score = item.get("score", 0)
            cmts  = item.get("comments", 0)
            lines.append(f"• [{src}] {item.get('title', '')} (↑{score} · {cmts} comments)")
            if item.get("text"):
                lines.append(f"  QUOTE: \"{item['text'][:250].strip()}\"")
            lines.append(f"  URL: {item.get('url', '')}")
        lines.append("")

    # Per-source breakdown (top 6 each, sorted by score)
    for key in source_keys:
        items = findings.get(key, [])
        if not items:
            continue
        label = {
            "reddit": "REDDIT", "hackernews": "HACKER NEWS", "news": "GOOGLE NEWS",
            "newsapi": "NEWS API", "web": "WEB SEARCH", "stackoverflow": "STACK OVERFLOW",
            "producthunt": "PRODUCT HUNT",
        }.get(key, key.upper())

        items_sorted = sorted(items, key=lambda x: x.get("score", 0), reverse=True)[:6]
        lines.append(f"=== {label} ({len(items)} results) ===")
        for item in items_sorted:
            title = item.get("title", "")
            text  = (item.get("text") or "").strip()[:220]
            date  = item.get("date", "")
            sent  = item.get("sentiment", "")
            parts = [f"• {title}"]
            if date:   parts[0] += f" [{date}]"
            if sent:   parts[0] += f" [{sent}]"
            lines.append(parts[0])
            if text:
                lines.append(f"  \"{text}\"")
        lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# MULTI-TOPIC COMPARISON
# ─────────────────────────────────────────────

def research_comparison(topics: list, sources=None) -> dict:
    """
    Research multiple topics and merge findings for a comparison report.
    e.g. research_comparison(["Notion", "Linear", "Asana"])

    Returns a merged findings dict with per-entity breakdowns and a
    combined summarise_for_prompt() string.
    """
    if not topics:
        raise ValueError("topics list cannot be empty")

    print(f"\n[ThreadIntel Comparison Engine]")
    print(f"Comparing: {' vs '.join(topics)}\n")

    all_findings = {}
    combined_reddit = []
    combined_hn     = []
    combined_news   = []
    combined_sources_used = set()

    for t in topics:
        print(f"--- Researching: {t} ---")
        f = research(t, sources=sources)
        all_findings[t] = f
        combined_reddit.extend(f.get("reddit", []))
        combined_hn.extend(f.get("hackernews", []))
        combined_news.extend(f.get("news", []))
        combined_sources_used.update(f.get("sources_used", []))

    merged = {
        "topic":         " vs ".join(topics),
        "entities":      topics,
        "researched_at": datetime.now().isoformat(),
        "sources_used":  list(combined_sources_used),
        "reddit":        combined_reddit,
        "hackernews":    combined_hn,
        "news":          combined_news,
        "web":           [],
        "stackoverflow": [],
        "producthunt":   [],
        "newsapi":       [],
        "indiehackers":  [],
        "github_issues": [],
        "per_entity":    all_findings,
    }

    # Merge other sources
    for key in ["web", "stackoverflow", "producthunt", "newsapi", "indiehackers", "github_issues"]:
        for t in topics:
            merged[key].extend(all_findings[t].get(key, []))

    add_sentiment(merged)

    _ALL_KEYS = ["reddit","hackernews","news","web","stackoverflow","producthunt","newsapi","indiehackers","github_issues"]
    total = sum(len(merged.get(s,[])) for s in _ALL_KEYS)
    print(f"\nComparison total: {total} results across {len(merged['sources_used'])} sources")

    return merged


# ─────────────────────────────────────────────
# MAIN (standalone test)
# ─────────────────────────────────────────────

def smart_research(topic: str, sources=None, time_filter="all", days_ago=None) -> dict:
    """
    Auto-detects comparison topics and routes accordingly.
    Use this as the single entry point from worker.py and email_brief.py.
    """
    import re as _re
    # Detect multi-entity comparison: "X vs Y", "X versus Y", "X or Y vs Z"
    vs_pattern = _re.split(r'\s+vs\.?\s+|\s+versus\s+', topic, flags=_re.IGNORECASE)
    if len(vs_pattern) >= 2:
        # Strip common filler
        entities = [e.strip().split(" vs ")[0].strip() for e in vs_pattern]
        entities = [e for e in entities if e]
        if len(entities) >= 2:
            return research_comparison(entities, sources=sources)

    return research(topic, sources=sources, time_filter=time_filter, days_ago=days_ago)


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else input("Research topic: ").strip()
    if not topic:
        sys.exit(0)

    findings = smart_research(topic)

    # Save raw findings to .tmp/
    out_path = ROOT / ".tmp" / f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(findings, indent=2, ensure_ascii=False))
    print(f"\nSaved to: {out_path}")

    # Print summary
    print("\n--- SUMMARY FOR PROMPT ---")
    print(summarise_for_prompt(findings)[:2000])
