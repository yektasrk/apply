#!/usr/bin/env python3
"""Serve the local LLM wiki with lightweight Markdown and Mermaid rendering."""

from __future__ import annotations

import argparse
import json
import posixpath
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
WIKI_ROOT = ROOT / "wiki"


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    metadata: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line or line.startswith("  "):
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')
    return metadata


def first_heading(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def page_records() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for path in sorted(WIKI_ROOT.rglob("*.md")):
        rel = path.relative_to(WIKI_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        metadata = parse_frontmatter(text)
        records.append(
            {
                "path": rel,
                "title": metadata.get("title") or first_heading(text) or rel,
                "type": metadata.get("type") or rel.split("/", 1)[0],
                "status": metadata.get("status") or "",
            }
        )
    return records


def safe_wiki_path(raw_path: str) -> Path | None:
    clean_path = posixpath.normpath(unquote(raw_path)).lstrip("/")
    if clean_path == "." or clean_path.startswith("../") or not clean_path.endswith(".md"):
        return None
    path = (WIKI_ROOT / clean_path).resolve()
    try:
        path.relative_to(WIKI_ROOT.resolve())
    except ValueError:
        return None
    if not path.is_file():
        return None
    return path


APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LLM Wiki</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8f5;
      --panel: #ffffff;
      --ink: #182026;
      --muted: #5f6d76;
      --line: #dce3df;
      --accent: #246b61;
      --accent-2: #9b4d2e;
      --code: #eef3ef;
      --shadow: 0 12px 30px rgba(22, 36, 32, 0.08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
    }

    .shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
    }

    aside {
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
      padding: 22px;
      border-right: 1px solid var(--line);
      background: #fbfcfa;
    }

    main {
      min-width: 0;
      padding: 34px clamp(20px, 5vw, 70px);
    }

    .brand {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 18px;
    }

    .brand h1 {
      margin: 0;
      font-size: 1.1rem;
      font-weight: 760;
      letter-spacing: 0;
    }

    .pill {
      border: 1px solid var(--line);
      color: var(--muted);
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 0.75rem;
      white-space: nowrap;
    }

    .search {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      padding: 10px 12px;
      font: inherit;
      margin-bottom: 20px;
    }

    .group-title {
      margin: 18px 0 7px;
      color: var(--accent-2);
      font-size: 0.74rem;
      text-transform: uppercase;
      font-weight: 760;
      letter-spacing: 0.06em;
    }

    .nav-link {
      display: block;
      padding: 8px 9px;
      border-radius: 7px;
      color: var(--ink);
      text-decoration: none;
      font-size: 0.93rem;
    }

    .nav-link:hover,
    .nav-link.active {
      background: #edf2ee;
      color: var(--accent);
    }

    .page-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 18px;
      color: var(--muted);
    }

    article {
      max-width: 980px;
      margin: 0 auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: clamp(22px, 5vw, 54px);
    }

    article h1 {
      margin: 0 0 20px;
      font-size: clamp(2rem, 4vw, 3.8rem);
      line-height: 1.02;
      letter-spacing: 0;
    }

    article h2 {
      margin: 34px 0 12px;
      font-size: 1.35rem;
      line-height: 1.25;
      letter-spacing: 0;
    }

    article h3 {
      margin: 26px 0 10px;
      font-size: 1.08rem;
      letter-spacing: 0;
    }

    article p,
    article li {
      color: #27333a;
    }

    article a {
      color: var(--accent);
      text-decoration-thickness: 1px;
      text-underline-offset: 3px;
    }

    ul, ol {
      padding-left: 1.3rem;
    }

    code {
      background: var(--code);
      padding: 0.12rem 0.32rem;
      border-radius: 5px;
      font-size: 0.92em;
    }

    pre {
      overflow: auto;
      background: #111817;
      color: #eef6f0;
      border-radius: 8px;
      padding: 16px;
    }

    pre code {
      background: transparent;
      padding: 0;
      color: inherit;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      margin: 18px 0 8px;
      font-size: 0.94rem;
    }

    th, td {
      border: 1px solid var(--line);
      padding: 10px 12px;
      vertical-align: top;
    }

    th {
      background: #eef3ef;
      text-align: left;
    }

    .mermaid {
      margin: 18px 0;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfa;
      overflow: auto;
    }

    .status {
      margin: 0 auto 14px;
      max-width: 980px;
      color: var(--muted);
      font-size: 0.92rem;
    }

    @media (max-width: 820px) {
      .shell { grid-template-columns: 1fr; }
      aside {
        position: relative;
        height: auto;
        max-height: 45vh;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
      main { padding: 20px 14px; }
      article { padding: 22px 16px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand">
        <h1>LLM Wiki</h1>
        <span id="page-count" class="pill">0 pages</span>
      </div>
      <input id="search" class="search" type="search" placeholder="Search pages">
      <nav id="nav"></nav>
    </aside>
    <main>
      <div id="status" class="status"></div>
      <article id="content"></article>
    </main>
  </div>

  <script type="module">
    let pages = [];
    let currentPath = "";
    let mermaidLib = null;
    let mermaidLoadPromise = null;

    const nav = document.getElementById("nav");
    const content = document.getElementById("content");
    const status = document.getElementById("status");
    const search = document.getElementById("search");
    const pageCount = document.getElementById("page-count");

    const groupOrder = ["meta", "source", "topic", "entity", "query"];

    function escapeHtml(value) {
      return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function describeError(error) {
      if (error && typeof error === "object" && "message" in error) {
        return String(error.message);
      }
      try {
        return JSON.stringify(error);
      } catch (_jsonError) {
        return String(error);
      }
    }

    function titleCase(value) {
      return value.charAt(0).toUpperCase() + value.slice(1);
    }

    function resolveMarkdownLink(href) {
      if (/^[a-z]+:/i.test(href) || href.startsWith("#")) {
        return href;
      }
      if (!href.endsWith(".md")) {
        return href;
      }
      const base = currentPath.split("/");
      base.pop();
      const normalized = new URL(href, `http://wiki.local/${base.join("/")}/`).pathname.slice(1);
      return `#${normalized}`;
    }

    function inlineMarkdown(value) {
      let output = escapeHtml(value);
      output = output.replace(/`([^`]+)`/g, "<code>$1</code>");
      output = output.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      output = output.replace(/\[\[([^\]]+)\]\]/g, (_match, label) => {
        return `<span class="wiki-link">${escapeHtml(label)}</span>`;
      });
      output = output.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label, href) => {
        const resolved = resolveMarkdownLink(href);
        const external = /^[a-z]+:/i.test(resolved) ? ' target="_blank" rel="noreferrer"' : "";
        return `<a href="${escapeHtml(resolved)}"${external}>${label}</a>`;
      });
      return output;
    }

    function stripFrontmatter(markdown) {
      if (!markdown.startsWith("---\n")) {
        return markdown;
      }
      const end = markdown.indexOf("\n---", 4);
      return end === -1 ? markdown : markdown.slice(end + 5).trimStart();
    }

    function renderTable(lines) {
      const rows = lines.map((line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim()));
      const header = rows[0] || [];
      const body = rows.slice(2);
      return `<table><thead><tr>${header.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead><tbody>${body.map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    }

    function renderMarkdown(markdown) {
      const body = stripFrontmatter(markdown);
      const lines = body.split(/\r?\n/);
      const html = [];
      let listType = null;
      let inCode = false;
      let codeLang = "";
      let codeLines = [];

      function closeList() {
        if (listType) {
          html.push(`</${listType}>`);
          listType = null;
        }
      }

      function closeCode() {
        const code = codeLines.join("\n");
        if (codeLang.trim().toLowerCase() === "mermaid") {
          html.push(`<div class="mermaid">${escapeHtml(code)}</div>`);
        } else {
          html.push(`<pre><code>${escapeHtml(code)}</code></pre>`);
        }
        inCode = false;
        codeLang = "";
        codeLines = [];
      }

      for (let i = 0; i < lines.length; i += 1) {
        const line = lines[i];
        const fence = line.match(/^```(.*)$/);
        if (fence) {
          if (inCode) {
            closeCode();
          } else {
            closeList();
            inCode = true;
            codeLang = fence[1] || "";
            codeLines = [];
          }
          continue;
        }

        if (inCode) {
          codeLines.push(line);
          continue;
        }

        if (/^\|.+\|$/.test(line) && i + 1 < lines.length && /^\|\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$/.test(lines[i + 1])) {
          closeList();
          const tableLines = [line, lines[i + 1]];
          i += 2;
          while (i < lines.length && /^\|.+\|$/.test(lines[i])) {
            tableLines.push(lines[i]);
            i += 1;
          }
          i -= 1;
          html.push(renderTable(tableLines));
          continue;
        }

        if (!line.trim()) {
          closeList();
          continue;
        }

        const heading = line.match(/^(#{1,6})\s+(.+)$/);
        if (heading) {
          closeList();
          const level = heading[1].length;
          html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
          continue;
        }

        const unordered = line.match(/^\s*-\s+(.+)$/);
        if (unordered) {
          if (listType !== "ul") {
            closeList();
            html.push("<ul>");
            listType = "ul";
          }
          html.push(`<li>${inlineMarkdown(unordered[1])}</li>`);
          continue;
        }

        const ordered = line.match(/^\s*\d+\.\s+(.+)$/);
        if (ordered) {
          if (listType !== "ol") {
            closeList();
            html.push("<ol>");
            listType = "ol";
          }
          html.push(`<li>${inlineMarkdown(ordered[1])}</li>`);
          continue;
        }

        closeList();
        html.push(`<p>${inlineMarkdown(line)}</p>`);
      }

      if (inCode) {
        closeCode();
      }
      closeList();
      return html.join("\n");
    }

    function groupPages(items) {
      const groups = new Map();
      for (const page of items) {
        const type = page.type || "other";
        if (!groups.has(type)) {
          groups.set(type, []);
        }
        groups.get(type).push(page);
      }
      return [...groups.entries()].sort((a, b) => {
        const ai = groupOrder.indexOf(a[0]);
        const bi = groupOrder.indexOf(b[0]);
        return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi) || a[0].localeCompare(b[0]);
      });
    }

    function renderNav() {
      const term = search.value.trim().toLowerCase();
      const filtered = pages.filter((page) => {
        return !term || page.title.toLowerCase().includes(term) || page.path.toLowerCase().includes(term);
      });
      nav.innerHTML = groupPages(filtered).map(([type, items]) => {
        const links = items.map((page) => {
          const active = page.path === currentPath ? " active" : "";
          return `<a class="nav-link${active}" href="#${page.path}">${escapeHtml(page.title)}</a>`;
        }).join("");
        return `<div class="group-title">${titleCase(type)}</div>${links}`;
      }).join("");
      pageCount.textContent = `${pages.length} page${pages.length === 1 ? "" : "s"}`;
    }

    async function renderMermaid() {
      const nodes = content.querySelectorAll(".mermaid");
      if (!nodes.length) {
        return;
      }
      if (!mermaidLib) {
        mermaidLoadPromise = mermaidLoadPromise || new Promise((resolve, reject) => {
          const script = document.createElement("script");
          script.src = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js";
          script.onload = () => resolve(window.mermaid);
          script.onerror = () => reject(new Error("Could not load Mermaid from the CDN."));
          document.head.appendChild(script);
        });
        try {
          mermaidLib = await mermaidLoadPromise;
          mermaidLib.initialize({
            startOnLoad: false,
            securityLevel: "loose",
            theme: "base",
            themeVariables: {
              primaryColor: "#edf2ee",
              primaryTextColor: "#182026",
              primaryBorderColor: "#246b61",
              lineColor: "#5f6d76",
              secondaryColor: "#f4ebe5",
              tertiaryColor: "#fbfcfa"
            }
          });
        } catch (error) {
          status.textContent = `Mermaid could not load: ${describeError(error)}`;
          return;
        }
      }
      try {
        if (mermaidLib.run) {
          await mermaidLib.run({ nodes: Array.from(nodes) });
        } else {
          mermaidLib.init(undefined, Array.from(nodes));
        }
      } catch (error) {
        status.textContent = `Mermaid render failed: ${describeError(error)}`;
      }
    }

    async function loadPage(path) {
      currentPath = path || "index.md";
      status.textContent = "";
      renderNav();
      const response = await fetch(`/api/page?path=${encodeURIComponent(currentPath)}`);
      if (!response.ok) {
        content.innerHTML = `<h1>Page not found</h1><p>${escapeHtml(currentPath)}</p>`;
        return;
      }
      const markdown = await response.text();
      content.innerHTML = renderMarkdown(markdown);
      await renderMermaid();
      renderNav();
    }

    async function boot() {
      const response = await fetch("/api/pages");
      pages = await response.json();
      search.addEventListener("input", renderNav);
      window.addEventListener("hashchange", () => loadPage(location.hash.slice(1) || "index.md"));
      renderNav();
      await loadPage(location.hash.slice(1) || "index.md");
    }

    boot().catch((error) => {
      content.innerHTML = `<h1>Could not load wiki</h1><p>${escapeHtml(describeError(error))}</p>`;
    });
  </script>
</body>
</html>
"""


class WikiHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_text(self, text: str, content_type: str = "text/plain; charset=utf-8", status: int = 200) -> None:
        self.send_bytes(text.encode("utf-8"), content_type, status)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self.send_text(APP_HTML, "text/html; charset=utf-8")
            return

        if parsed.path == "/api/pages":
            self.send_text(json.dumps(page_records()), "application/json; charset=utf-8")
            return

        if parsed.path == "/api/page":
            path_values = parse_qs(parsed.query).get("path", [])
            if not path_values:
                self.send_text("missing path", status=400)
                return
            path = safe_wiki_path(path_values[0])
            if path is None:
                self.send_text("not found", status=404)
                return
            self.send_text(path.read_text(encoding="utf-8"), "text/markdown; charset=utf-8")
            return

        self.send_text("not found", status=404)


def serve(host: str, port: int, attempts: int) -> None:
    for candidate in range(port, port + attempts):
        try:
            server = ThreadingHTTPServer((host, candidate), WikiHandler)
        except OSError:
            continue
        print(f"Serving LLM wiki at http://{host}:{candidate}/", flush=True)
        print("Press Ctrl+C to stop.", flush=True)
        server.serve_forever()
    raise SystemExit(f"No free port found from {port} to {port + attempts - 1}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local LLM wiki.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--attempts", type=int, default=50)
    args = parser.parse_args()
    serve(args.host, args.port, args.attempts)


if __name__ == "__main__":
    main()
