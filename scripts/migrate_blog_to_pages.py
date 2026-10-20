#!/usr/bin/env python3
"""Move the pi-rsi pages from blog.pocketplay.win (a VPS) to static hosting (GitHub Pages).

    scripts/migrate_blog_to_pages.py MIRROR VENDOR --out site --base /pi-rsi

MIRROR is a crawl of the blog's /rsi/, /files/rsi/ and the pi-rsi posts (/en|zh/blog/pi-rsi-*/);
VENDOR holds the platform stylesheets the pages were designed with (pp.css, blog.css, style.*.css)
and their fonts. Each page keeps its <main> and its own assets; the platform shell (site navigation,
account and analytics scripts) is dropped and every link is rebased onto BASE. The output is plain
static files: no build step runs on the host. Experiment files the blog linked but never served are
restored from experiments/ when they still exist locally.
"""
from __future__ import annotations

import argparse
import html
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OLD = "https://blog.pocketplay.win"
NEW_HOST = "https://xiehuanyi.github.io"
GITHUB = "https://github.com/xiehuanyi/pi-rsi"
TEXT = {".html", ".js", ".css", ".json", ".md", ".txt", ".xml"}
PLATFORM = re.compile(r"/(?:_kit|_platform|_pp)/|/assets/style\.[0-9a-f]+\.css")
OURS = re.compile(r"^/(?:rsi|files/rsi)/|^/(?:en|zh)/blog/pi-rsi-")


def rebase(text: str, base: str) -> str:
    """Point blog URLs of migrated pages at BASE; leave the rest of the blog as external links."""
    text = re.sub(re.escape(OLD) + r"(/(?:rsi|files/rsi)/|/(?:en|zh)/blog/pi-rsi-)", base + r"\1", text)
    return re.sub(r"""(["'(=\s`])(/(?:rsi|files/rsi)/|/(?:en|zh)/blog/pi-rsi-)""", r"\1" + base + r"\2", text)


def external_links(fragment: str, base: str) -> str:
    """Root-relative links into the rest of the PocketPlay blog become absolute links to it.

    The icon sprite is copied with the stylesheets; injected Cloudflare challenge scripts are dropped."""
    fragment = re.sub(r'(?:' + re.escape(OLD) + r')?/_kit/v2/icons\.svg(?:\?v=[0-9a-f]+)?', base + "/assets/kit/v2/icons.svg",
                      fragment)
    fragment = re.sub(r"<script>\(function\(\)\{function c\(\).*?</script>", "", fragment, flags=re.S)
    return re.sub(r'(href|src)="/(?!' + re.escape(base.strip("/")) + r'/)', r'\1="' + OLD + "/", fragment)


def strip_platform(page: str) -> str:
    """Drop the PocketPlay network bar, analytics and bridge scripts from a standalone page."""
    platform = r'(?:' + re.escape(OLD) + r')?/(?:_pp|_kit|_platform)/'
    page = re.sub(r'<script\b[^>]*src="' + platform + r'[^"]*"[^>]*></script>\s*', "", page)
    page = re.sub(r'<link\b[^>]*href="' + platform + r'[^"]*"[^>]*>\s*', "", page)
    return re.sub(r'<nav class="pp-network".*?</nav>\s*', "", page, flags=re.S)


def shell(*, lang, title, description, path, base, head, body, alternate=None, site="", body_class="pp pp-v2"):
    home = f"{base}/zh/" if lang.startswith("zh") else f"{base}/"
    switch = (f'<a href="{alternate}" hreflang="{"en" if lang.startswith("zh") else "zh"}">'
              f'{"English" if lang.startswith("zh") else "中文"}</a>') if alternate else ""
    note = ("最初发表于 PocketPlay 博客，现托管在 GitHub Pages。" if lang.startswith("zh")
            else "First published on the PocketPlay blog; now hosted on GitHub Pages.")
    return f"""<!doctype html>
<html lang="{lang}"{f' data-pp-site="{site}"' if site else ""}{"" if body_class else " data-rsi-legacy"}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{NEW_HOST}{base}{path}">
<link rel="icon" href="{base}/assets/favicon.svg" type="image/svg+xml">
{head}
<link rel="stylesheet" href="{base}/assets/site.css">
</head>
<body class="{body_class}">
<div class="rsi-bar" role="banner"><a class="rsi-home" href="{home}">pi-rsi</a><span class="rsi-links">{switch}<a href="{GITHUB}">GitHub</a></span></div>
{body}
<div class="rsi-bar rsi-foot" role="contentinfo"><span>{note}</span><a href="{GITHUB}">{GITHUB.removeprefix("https://")}</a></div>
</body>
</html>
"""


def migrate_page(src: str, rel: str, base: str) -> str:
    """Keep <main> and the page's own assets; drop the platform shell."""
    start, end = src.find("<main"), src.rfind("</main>") + len("</main>")
    lang = (re.search(r'<html[^>]*\blang="([^"]+)"', src) or [None, "en"])[1]
    title = html.unescape((re.search(r"<title>(.*?)</title>", src, re.S) or [None, "pi-rsi"])[1]).strip()
    description = (re.search(r'<meta name="description" content="([^"]*)"', src) or [None, ""])[1]
    alternate = next((rebase(href, base) for code, href in re.findall(
        r'<link rel="alternate" hreflang="([A-Za-z-]+)" href="([^"]+)"', src)
        if not lang.startswith(code[:2]) and code[:2] in ("en", "zh")), None)
    assets = re.finditer(r'<link\b[^>]*rel="stylesheet"[^>]*>|<script\b[^>]*\bsrc="([^"]*)"[^>]*></script>', src)
    head, tail = [], []
    vendor = []
    if "/_kit/v2/pp.css" in src:
        vendor.append(f'<link rel="stylesheet" href="{base}/assets/kit/v2/pp.css">')
    if "/_platform/v2/blog.css" in src:
        vendor.append(f'<link rel="stylesheet" href="{base}/assets/platform/blog.css">')
    if re.search(r"/assets/style\.[0-9a-f]+\.css", src):
        vendor.append(f'<link rel="stylesheet" href="{base}/assets/platform/style.css">')
    for m in assets:
        tag = m.group(0)
        url = (re.search(r'(?:href|src)="([^"]+)"', tag) or [None, ""])[1]
        if PLATFORM.search(url) or not OURS.search(url.removeprefix(OLD)):
            continue
        (head if tag.startswith("<link") or m.start() < start else tail).append(rebase(tag, base))
    main = external_links(rebase(src[start:end], base), base)
    site = (re.search(r'<html[^>]*\bdata-pp-site="([^"]+)"', src) or [None, ""])[1]
    body_class = (re.search(r'<body[^>]*\bclass="([^"]+)"', src) or [None, ""])[1]
    return shell(lang=lang, title=html.escape(title), description=description, path="/" + rel.removesuffix("index.html"),
                 base=base, head="\n".join(vendor + head), body=main + "\n" + "\n".join(tail), alternate=alternate,
                 site=site, body_class=body_class)


SITE_CSS = """/* Frame for pages migrated from blog.pocketplay.win; page styles come from the original stylesheets. */
:root{--rsi-bar-bg:#f6f4ef;--rsi-bar-fg:#2b2a27;--rsi-bar-line:#e3dfd6;--rsi-bar-link:#3b5bdb}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--rsi-bar-bg:#1b1c20;--rsi-bar-fg:#e7e5df;--rsi-bar-line:#2e3036;--rsi-bar-link:#8ea5ff}}
html[data-rsi-legacy]{--rsi-bar-bg:#fafafa;--rsi-bar-fg:#22252a;--rsi-bar-line:#e8e9ec;--rsi-bar-link:#285ea5}
.rsi-bar{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;
  padding:10px 16px;background:var(--rsi-bar-bg);color:var(--rsi-bar-fg);border-bottom:1px solid var(--rsi-bar-line);
  font:14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}
.rsi-bar a{color:var(--rsi-bar-link);text-decoration:none}
.rsi-bar a:hover{text-decoration:underline}
.rsi-bar .rsi-links{display:flex;gap:16px}
.rsi-home{font-weight:600;color:var(--rsi-bar-fg)!important}
.rsi-foot{border-top:1px solid var(--rsi-bar-line);border-bottom:0;margin-top:48px;font-size:13px}
.rsi-index{max-width:760px;margin:0 auto;padding:32px 16px;font:16px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--rsi-bar-fg)}
.rsi-index h1{font-size:28px;margin:0 0 8px}.rsi-index h2{font-size:18px;margin:32px 0 8px}
.rsi-index a{color:var(--rsi-bar-link)}.rsi-index ul{padding-left:20px}.rsi-index li{margin:6px 0}
.rsi-index .lede{color:inherit;opacity:.8}
"""

FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#3b5bdb"/>'
           '<path d="M9 23V9m0 0h6a4 4 0 0 1 0 8H9m6 0 5 6" stroke="#fff" stroke-width="3" fill="none" '
           'stroke-linecap="round" stroke-linejoin="round"/></svg>')

INDEX = {
    "en": dict(title="pi-rsi · research notes", path="/", alternate="/zh/", body="""<main class="rsi-index">
<h1>pi-rsi research notes</h1>
<p class="lede">Write-ups and interactive records from <a href="https://github.com/xiehuanyi/pi-rsi">pi-rsi</a>,
an automated research harness: agents choose and implement hypotheses, a frozen evaluator measures them, and the
harness keeps the search tree, the evidence and the research wiki.</p>
<h2>Write-ups</h2>
<ul>
<li><a href="BASE/en/blog/pi-rsi-casmi26-proxy-alignment-20261015/">CASMI26: how a biased proxy stalled the search</a> (2026-10-15) —
<a href="BASE/rsi/interactive/casmi26-newflow-20261015/en/">interactive score chart and search tree</a></li>
<li><a href="BASE/en/blog/pi-rsi-airline-20261004/">Airline satisfaction: an experiment and its research wiki</a> (2026-10-04) —
<a href="BASE/rsi/interactive/airline-20261004/en/">overview</a>, <a href="BASE/rsi/interactive/airline-20261004/en/tree/">search tree</a>,
<a href="BASE/rsi/interactive/airline-20261004/en/wiki/">research wiki</a></li>
</ul>
<h2>Earlier notebook (Chinese)</h2>
<p>First experiments with the original tree scheduler (Kaggriculture, House Prices, Spaceship Titanic):
<a href="BASE/rsi/">notebook index</a>, <a href="BASE/rsi/experiments/">experiments</a>, <a href="BASE/rsi/analysis/">analyses</a>.</p>
</main>"""),
    "zh": dict(title="pi-rsi · 研究笔记", path="/zh/", alternate="/", body="""<main class="rsi-index">
<h1>pi-rsi 研究笔记</h1>
<p class="lede"><a href="https://github.com/xiehuanyi/pi-rsi">pi-rsi</a> 的文章与交互记录。pi-rsi 是一个自动研究框架：
agent 选择并实现假设，冻结的评估器给出官方分数，框架保存搜索树、证据和研究 Wiki。</p>
<h2>文章</h2>
<ul>
<li><a href="BASE/zh/blog/pi-rsi-casmi26-proxy-alignment-20261015/">CASMI26：有偏的代理指标如何拖住搜索</a>（2026-10-15）——
<a href="BASE/rsi/interactive/casmi26-newflow-20261015/zh/">交互式分数曲线与搜索树</a></li>
<li><a href="BASE/zh/blog/pi-rsi-airline-20261004/">航空满意度：一次实验与它的研究 Wiki</a>（2026-10-04）——
<a href="BASE/rsi/interactive/airline-20261004/zh/">概览</a>、<a href="BASE/rsi/interactive/airline-20261004/zh/tree/">搜索树</a>、
<a href="BASE/rsi/interactive/airline-20261004/zh/wiki/">研究 Wiki</a></li>
</ul>
<h2>早期实验笔记</h2>
<p>最初的树调度器上的实验（Kaggriculture、House Prices、Spaceship Titanic）：
<a href="BASE/rsi/">笔记首页</a>、<a href="BASE/rsi/experiments/">实验</a>、<a href="BASE/rsi/analysis/">分析</a>。</p>
</main>"""),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mirror", type=Path)
    ap.add_argument("vendor", type=Path)
    ap.add_argument("--out", type=Path, default=REPO / "site")
    ap.add_argument("--base", default="/pi-rsi")
    a = ap.parse_args()
    base, out = a.base.rstrip("/"), a.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    pages = 0
    for f in sorted(p for p in a.mirror.rglob("*") if p.is_file()):
        rel = f.relative_to(a.mirror).as_posix()
        if rel.endswith("sitemap.xml"):
            continue  # the platform's sitemaps; the new site is listed by its own sitemap below
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if f.suffix not in TEXT:
            shutil.copy2(f, target)
            continue
        text = f.read_text(encoding="utf-8")
        if f.suffix == ".html" and "<main" in text and ("/_kit/" in text or "/_platform/" in text):
            text = migrate_page(text, rel, base)
            pages += 1
        elif f.suffix == ".html":
            text = strip_platform(external_links(rebase(text, base), base))
        else:
            text = rebase(text, base)
        target.write_text(text, encoding="utf-8")

    # Node notes the blog linked but did not serve; restore them from local experiments.
    restored = 0
    for page in out.glob("rsi/experiments/*/index.html"):
        for path in re.findall(re.escape(base) + r"/files/rsi/runs/([^\"']+)", page.read_text(encoding="utf-8")):
            target = out / "files/rsi/runs" / path
            source = REPO / "experiments" / path
            if not target.exists() and source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                restored += 1

    assets = out / "assets"
    (assets / "kit/v2").mkdir(parents=True)
    (assets / "platform").mkdir(parents=True)
    shutil.copy2(a.vendor / "pp.css", assets / "kit/v2/pp.css")
    shutil.copy2(a.vendor / "icons.svg", assets / "kit/v2/icons.svg")
    shutil.copytree(a.vendor / "fonts", assets / "kit/fonts")
    shutil.copy2(a.vendor / "blog.css", assets / "platform/blog.css")
    shutil.copy2(next(a.vendor.glob("style.*.css")), assets / "platform/style.css")
    (assets / "site.css").write_text(SITE_CSS, encoding="utf-8")
    (assets / "favicon.svg").write_text(FAVICON, encoding="utf-8")
    for lang, page in INDEX.items():
        target = out / page["path"].lstrip("/") / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(shell(lang=lang, title=page["title"], description=page["title"], path=page["path"], base=base,
                                head=f'<link rel="stylesheet" href="{base}/assets/kit/v2/pp.css">',
                                body=page["body"].replace("BASE", base), alternate=base + page["alternate"]),
                          encoding="utf-8")
    (out / "404.html").write_text(shell(lang="en", title="Not found · pi-rsi", description="", path="/404.html",
                                        base=base, head="", body=f'<main class="rsi-index"><h1>Not found</h1>'
                                        f'<p><a href="{base}/">pi-rsi research notes</a></p></main>'), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    urls = sorted(NEW_HOST + base + "/" + p.relative_to(out).as_posix().removesuffix("index.html")
                  for p in out.rglob("index.html"))
    (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/'
                                     'schemas/sitemap/0.9">\n' + "".join(f"<url><loc>{u}</loc></url>\n" for u in urls)
                                     + "</urlset>\n", encoding="utf-8")
    print(f"{pages} pages rebuilt, {restored} node files restored, {len(urls)} pages listed -> {out}")


if __name__ == "__main__":
    main()
