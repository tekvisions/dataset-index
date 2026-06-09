#!/usr/bin/env python3
"""The Dataset Index — recompute the living index of data-centric AI tooling from live
GitHub signals, and write data.json + SEO (sitemap, rss, robots, llms.txt).

Scope = the tools that build, label, synthesize, curate and serve ML datasets: labeling &
annotation platforms, synthetic-data generation, data curation/quality, augmentation, and
dataset frameworks/loaders/versioning. TOOLS, not raw data dumps (momentum ranks active tools).
Excludes general ML frameworks (pytorch/sklearn), LLM/chat tooling, image/diffusion, and the
sibling indexes (RAG/eval/prompt/etc). Gathered, deduped, FILTERED (precision over recall),
categorized, scored.

Only the GitHub *search* payload is used. Env: GITHUB_TOKEN (required for a usable rate limit).
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.github.com"
SITE_URL = "https://dataset.kymatalabs.com"   # fixed to the real alias after first deploy
SITE_NAME = "The Dataset Index"

QUERIES = [
    "topic:dataset stars:>250",
    "topic:datasets stars:>250",
    "topic:data-labeling stars:>80",
    "topic:data-annotation stars:>80",
    "topic:annotation-tool stars:>120",
    "topic:synthetic-data stars:>70",
    "topic:data-augmentation stars:>120",
    "topic:data-version-control stars:>90",
    "topic:data-centric-ai stars:>60",
    "topic:active-learning stars:>150",
    "data labeling tool in:name,description stars:>200",
    "synthetic data generation in:name,description stars:>120",
    "dataset management in:name,description stars:>150",
    "annotation tool in:name,description stars:>250",
    "data quality machine learning in:name,description stars:>150",
]


def token() -> str:
    return (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()


HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "dataset-index"}
if token():
    HEADERS["Authorization"] = f"Bearer {token()}"

_DATA_TOPICS = {"data-labeling", "data-annotation", "annotation-tool", "annotation", "labeling",
                "image-annotation", "text-annotation", "synthetic-data", "data-augmentation",
                "data-version-control", "data-versioning", "data-quality", "data-curation",
                "data-cleaning", "data-centric-ai", "active-learning", "dataset-generation",
                "dataset", "datasets", "dataset-management", "data-labelling", "labelling",
                "data-preprocessing", "feature-store", "data-validation"}
_DATA_PHRASES = re.compile(
    r"\b(data[- ]?label(l)?ing|data annotation|annotation (tool|platform|interface)|label(l)?ing (tool|platform)"
    r"|synthetic[- ]?data|data augmentation|data version(ing| control)|data quality|data curation"
    r"|data cleaning|data[- ]centric|active learning|dataset (management|generation|tool|builder|hub|catalog)"
    r"|training data|feature store|data validation|image (label|annotat)|text (label|annotat)"
    r"|label studio|data preprocessing)\b", re.I)
# General ML/DL frameworks, LLM/chat, image/diffusion, dataframe/BI libs, raw-dataset dumps,
# and sibling-index repos that match but aren't data-CENTRIC TOOLING. Lowercased full_name
# (is_data lowercases before the lookup); _ANTI (name+desc) catches the rest.
_DENY = {
    "huggingface/transformers", "pytorch/pytorch", "tensorflow/tensorflow",
    "scikit-learn/scikit-learn", "keras-team/keras", "pandas-dev/pandas",
    "pola-rs/polars", "huggingface/diffusers", "comfyanonymous/comfyui",
    "open-webui/open-webui", "ggerganov/llama.cpp", "apache/spark", "ray-project/ray",
    "jdah/awesome-public-datasets", "huggingface/datasets-server",
    # bleed: API/resource lists, finance-data libs, screen tools, eval/observability,
    # browser/color/string libs, LLM-app platforms, tutorials/resource collections
    "public-apis/public-apis", "alyssaxuu/screenity", "akfamily/akshare",
    "dataelement/bisheng", "satellite-image-deep-learning/techniques", "arize-ai/phoenix",
    "mdn/browser-compat-data", "splware/esproc", "ashvardanian/stringzilla",
    "jon-becker/prediction-market-analysis", "langwatch/langwatch", "pgmpy/pgmpy",
    "meodai/color-names", "vowpalwabbit/vowpal_wabbit", "colour-science/colour",
    "ksnip/ksnip", "roapi/roapi", "ganjinzero/awesome_chinese_medical_nlp",
    "prabhuomkar/pytorch-cpp", "yongzhuo/nlp_xiaojiang", "styfeng/dataaug4nlp",
    "sciphi-ai/synthesizer", "tigerlab-ai/tiger",
}
_ANTI = re.compile(
    r"\b(awesome|curated list|prompt engineering|tutorial|course|roadmap|cheat ?sheet"
    r"|paper[- ]?(list|survey)|reading list|survey (on|of)|interview questions|book\b"
    r"|stable diffusion|text[- ]to[- ]image|image generation|comfyui|chatgpt clone|llm chat(bot)?"
    r"|model context protocol|\bmcp\b|deep learning (examples|tutorial)|from scratch"
    r"|leetcode|competitive programming|business intelligence|\bbi\b dashboard"
    r"|screenshot|screen recorder|screen capture|financial data|stock market|crypto exchange"
    r"|browser compat|color names|colour science|online learning system|prediction market"
    r"|observability & eval|\bobservability\b|list of (free|public)|collective list"
    r"|the dataset for|dataset of (the|all)|this dataset|raw data of)\b", re.I)


def gh(url: str, *, retries: int = 4):
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (403, 429):
                reset = e.headers.get("X-RateLimit-Reset")
                wait = 5 * (attempt + 1)
                if reset:
                    try:
                        wait = max(wait, min(60, int(reset) - int(time.time()) + 2))
                    except ValueError:
                        pass
                print(f"  rate-limited — sleeping {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            if 500 <= e.code < 600:
                time.sleep(3 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(3 * (attempt + 1))
    if last:
        raise last
    raise RuntimeError(f"gh failed: {url}")


def search(q: str, per_page: int = 40) -> list[dict]:
    url = (f"{API}/search/repositories?q={urllib.parse.quote(q)}"
           f"&sort=stars&order=desc&per_page={per_page}")
    try:
        return gh(url).get("items", [])
    except Exception as e:
        print(f"  query failed [{q}]: {e}", file=sys.stderr)
        return []


def is_data(r: dict) -> bool:
    full = (r.get("full_name") or "").lower()
    if full in _DENY:
        return False
    name = r.get("name") or ""
    desc = r.get("description") or ""
    if _ANTI.search(f"{name} {desc}"):       # name+desc → catches awesome-*/raw-dataset/framework names
        return False
    topics = {t.lower() for t in (r.get("topics") or [])}
    if topics & _DATA_TOPICS:
        return True
    return bool(_DATA_PHRASES.search(f"{r.get('name','')} {desc}"))


def categorize(r: dict) -> str:
    topics = {t.lower() for t in (r.get("topics") or [])}
    blob = f"{(r.get('name') or '').lower()} {(r.get('description') or '').lower()} {' '.join(topics)}"
    if re.search(r"label(l)?ing|annotat|\bcvat\b|label studio|doccano|bounding box|active learning", blob):
        return "Labeling & Annotation"
    if re.search(r"synthetic[- ]?data|data generation|\bsdv\b|distilabel|faker|generate (synthetic|fake)"
                 r"|gretel|mostly[- ]?ai", blob):
        return "Synthetic Data"
    if re.search(r"data quality|data validation|data curation|data cleaning|dedup|cleanlab|fastdup"
                 r"|outlier|great expectations|data drift|noisy label", blob):
        return "Curation & Quality"
    if re.search(r"augmentation|albumentations|nlpaug|audiomentations|imgaug|augment", blob):
        return "Augmentation"
    if re.search(r"version(ing| control)|\bdvc\b|lakefs|deeplake|\blance\b|webdataset|feature store"
                 r"|data lineage|data catalog|\bdelta lake\b", blob):
        return "Versioning & Frameworks"
    if re.search(r"awesome|curated|collection|directory|\bhub\b|catalog", blob):
        return "Collections & Hubs"
    return "Versioning & Frameworks"


def days_since(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds() / 86400.0
    except ValueError:
        return None


def momentum(r: dict, max_stars: int) -> int:
    stars = r.get("stargazers_count", 0) or 0
    star_norm = math.log10(stars + 1) / math.log10(max(max_stars, 10) + 1)
    pushed = days_since(r.get("pushed_at"))
    recency = 0.2 if pushed is None else max(0.0, 1.0 - max(0.0, pushed) / 180.0)
    created = days_since(r.get("created_at"))
    young = (1.0 - created / 120.0) if (created is not None and created < 120 and stars >= 20) else 0.0
    return max(1, min(100, round((0.55 * star_norm + 0.32 * recency + 0.13 * young) * 100)))


def slugify(full_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", full_name.lower()).strip("-")


def build_items() -> list[dict]:
    seen: dict[str, dict] = {}
    for q in QUERIES:
        for r in search(q):
            full = r.get("full_name")
            if full and full not in seen and is_data(r):
                seen[full] = r
        time.sleep(0.7)
    raw = list(seen.values())
    max_stars = max((r.get("stargazers_count", 0) or 0) for r in raw) if raw else 10
    items = []
    for r in raw:
        owner = r.get("owner") or {}
        items.append({
            "name": r.get("name", ""), "full_name": r.get("full_name", ""),
            "slug": slugify(r.get("full_name", "")), "url": r.get("html_url", ""),
            "owner": owner.get("login", ""), "owner_avatar": owner.get("avatar_url", ""),
            "stars": r.get("stargazers_count", 0) or 0, "forks": r.get("forks_count", 0) or 0,
            "open_issues": r.get("open_issues_count", 0) or 0, "language": r.get("language") or "",
            "license": ((r.get("license") or {}) or {}).get("spdx_id") or "",
            "pushed_at": r.get("pushed_at"), "created_at": r.get("created_at"),
            "description": (r.get("description") or "").strip(), "topics": r.get("topics") or [],
            "category": categorize(r), "momentum": momentum(r, max_stars),
        })
    items.sort(key=lambda x: (x["momentum"], x["stars"]), reverse=True)
    for i, it in enumerate(items, 1):
        it["rank"] = i
    return items


def write_json(items: list[dict]) -> dict:
    cats: dict[str, int] = {}
    for it in items:
        cats[it["category"]] = cats.get(it["category"], 0) + 1
    data = {"generated_at": datetime.now(timezone.utc).isoformat(), "count": len(items),
            "categories": [{"name": k, "count": v} for k, v in sorted(cats.items(), key=lambda x: -x[1])],
            "items": items}
    with open(os.path.join(HERE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


def write_seo(data: dict) -> None:
    items = data["items"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [f"  <url><loc>{SITE_URL}/</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for it in items:
        urls.append(f"  <url><loc>{SITE_URL}/p/{it['slug']}/</loc><lastmod>{now}</lastmod>"
                    f"<changefreq>weekly</changefreq><priority>0.6</priority></url>")
    open(os.path.join(HERE, "sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n</urlset>\n")
    open(os.path.join(HERE, "robots.txt"), "w", encoding="utf-8").write(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")

    def esc(s):
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    rss_items = [
        f"    <item><title>{esc(it['full_name'])} — momentum {it['momentum']}</title>"
        f"<link>{SITE_URL}/p/{it['slug']}/</link><guid isPermaLink=\"false\">{esc(it['full_name'])}</guid>"
        f"<description>{esc(it['description'][:300])}</description></item>" for it in items[:30]]
    open(os.path.join(HERE, "rss.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0">\n  <channel>\n'
        f"    <title>{SITE_NAME}</title>\n    <link>{SITE_URL}</link>\n"
        "    <description>The living index of data-centric AI tooling — labeling, synthetic data, curation, augmentation, dataset frameworks.</description>\n"
        + "\n".join(rss_items) + "\n  </channel>\n</rss>\n")

    lines = [f"# {SITE_NAME}", "",
             "> The living index of data-centric AI tooling — data labeling & annotation, synthetic",
             "> data, curation & quality, augmentation, and dataset frameworks — ranked daily by GitHub momentum.", "",
             f"Updated: {data['generated_at']}", f"Tools indexed: {data['count']}", "",
             "## Top data-centric AI tools by momentum", ""]
    for it in items[:40]:
        lines.append(f"- [{it['full_name']}]({it['url']}) — momentum {it['momentum']}, "
                     f"⭐{it['stars']} — {it['category']} — {it['description'][:100]}")
    open(os.path.join(HERE, "llms.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")


def main() -> int:
    if not token():
        print("WARNING: no GITHUB_TOKEN — low rate limit, partial results", file=sys.stderr)
    items = build_items()
    if not items:
        print("ERROR: no data tools found — refusing to write empty data.json", file=sys.stderr)
        return 1
    data = write_json(items)
    write_seo(data)
    print(f"wrote data.json: {len(items)} data tools across {len(data['categories'])} categories")
    print("  top 5:", ", ".join(f"{it['full_name']}({it['momentum']})" for it in items[:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
