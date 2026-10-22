#!/usr/bin/env python3
"""Build branded CV PDFs from content/*.md using Chromium. Fraunces is bundled in fonts/."""
import html, pathlib, shutil, subprocess, os

OUT = pathlib.Path(__file__).parent
PDF_OUT = OUT.parent / "download"


# ---------------------------------------------------------------- content
# Content lives in content/*.md. Format:
#
#   ---                       front matter: file, title, tag, links (list)
#   file: CV_..._short
#   ...
#   ---
#   # Sidebar                 everything until "# Main" goes in the dark column
#   ## Section                sidebar section label
#   ### Sub-heading           optional
#   text lines                a line ending in two spaces = line break
#   # Main
#   ## Section                main section heading
#   paragraph                 free text
#   - bullet                  list item
#   ### Job or org            starts a job block (Experience-style)
#   *meta line*               italic line right after ### = role · dates
#
# Inline: **bold**, *italic*. Nothing else.

import re, html as _html

def inline(s):
    s = _html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    s = re.sub(r"  \n", "<br>", s)
    return s.replace("\n", " ")

def load_shared():
    """content/_shared.md: blocks that start with `::: name` and run to the next `:::`."""
    p = OUT / "content" / "_shared.md"
    if not p.exists():
        return {}
    blocks, name, buf = {}, None, []
    for ln in p.read_text(encoding="utf-8").splitlines():
        if ln.startswith("::: "):
            if name: blocks[name] = "\n".join(buf).strip("\n")
            name, buf = ln[4:].strip(), []
        elif name is not None and not ln.startswith("# "):
            buf.append(ln)
    if name: blocks[name] = "\n".join(buf).strip("\n")
    return blocks

def expand(text, shared):
    """Replace a line that is only `{{name}}` (any indent) with that shared block, re-indented."""
    def repl(m):
        indent, name = m.group(1), m.group(2)
        if name not in shared:
            raise SystemExit(f"unknown shared block {{{{{name}}}}}")
        return "\n".join(indent + l if l else l for l in shared[name].splitlines())
    return re.sub(r"^([ \t]*)\{\{([\w-]+)\}\}[ \t]*$", repl, text, flags=re.M)

def parse(path):
    text = expand(pathlib.Path(path).read_text(encoding="utf-8"), load_shared())
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    fm, body = m.group(1), m.group(2)
    meta = {"links": []}
    key = None
    for line in fm.splitlines():
        if line.lstrip().startswith("- ") and key:
            meta[key].append(line.lstrip()[2:].strip())
        elif ":" in line:
            k, v = line.split(":", 1); key = k.strip(); v = v.strip()
            meta[key] = [] if v == "" else v
    cv = dict(file=meta["file"], title=meta["title"], tag=meta["tag"], links=meta["links"], side=[], main=[])

    # split into Sidebar / Main
    parts = re.split(r"^# (Sidebar|Main)\s*$", body, flags=re.M)
    zones = {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}

    def blocks(lines):
        """yield ('h2'|'h3'|'meta'|'p'|'list', payload)"""
        buf, lst = [], []
        def flush():
            nonlocal buf, lst
            if lst: yield_items.append(("list", lst)); lst = []
            if buf: yield_items.append(("p", "\n".join(buf))); buf = []
        yield_items = []
        for ln in lines:
            if ln.startswith("## "): flush(); yield_items.append(("h2", ln[3:].strip()))
            elif ln.startswith("### "): flush(); yield_items.append(("h3", ln[4:].strip()))
            elif ln.startswith("- "): 
                if buf: yield_items.append(("p", "\n".join(buf))); buf = []
                lst.append(ln[2:].strip())
            elif ln.strip() == "": flush()
            elif re.fullmatch(r"\*[^*].*\*", ln.strip()) and yield_items and yield_items[-1][0] == "h3":
                yield_items.append(("meta", ln.strip()[1:-1]))
            else:
                if lst: yield_items.append(("list", lst)); lst = []
                buf.append(ln.rstrip("\n"))
        flush()
        return yield_items

    # sidebar
    cur = None
    for kind, val in blocks(zones.get("Sidebar", "").splitlines()):
        if kind == "h2": cur = (val, []); cv["side"].append(cur)
        elif kind == "h3": cur[1].append([val, ""])
        elif kind == "p":
            if cur[1] and cur[1][-1][1] == "": cur[1][-1][1] = inline(val)
            else: cur[1].append(["", inline(val)])
        elif kind == "list": cur[1].append(["", "<br>".join(inline(x) for x in val)])

    # main
    section = None
    for kind, val in blocks(zones.get("Main", "").splitlines()):
        if kind == "h2":
            section = {"head": val, "kind": None, "body": []}; cv["main"].append(section)
        elif kind == "h3":
            section["kind"] = "jobs"; section["body"].append([val, "", "", []])
        elif kind == "meta":
            section["body"][-1][1] = inline(val)
        elif kind == "p":
            if section["kind"] == "jobs": section["body"][-1][2] = inline(val)
            else:
                section["kind"] = "blocks"
                section["body"].append(("p", inline(val)))
        elif kind == "list":
            if section["kind"] == "jobs": section["body"][-1][3] = [inline(x) for x in val]
            else:
                section["kind"] = "blocks"
                section["body"].append(("list", [inline(x) for x in val]))
    cv["main"] = [(s["head"], s["kind"], s["body"]) for s in cv["main"]]
    return cv

CONTENT = sorted(p for p in (OUT / "content").glob("*.md") if not p.name.startswith("_"))

# ---------------------------------------------------------------- render
PAL = dict(dark="#1e2c3a", light="#f3efe6", gold="#d99a3d", accent2="#2f8fb0", soft="#9CC5D4")
CSS_T = """
@font-face { font-family: 'Fraunces'; src: url('fonts/fraunces-latin-wght-normal.woff2') format('woff2'); font-weight: 100 900; }
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { font-family: 'Inter', sans-serif; font-size: 8.6pt; line-height: 1.36; color: #1c232b; background: {light};
       -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.page { width: 210mm; position: relative; }
.band { position: fixed; left: 0; top: 0; width: 64mm; height: 297mm; background: {dark}; z-index: 0; }
.side { position: absolute; left: 0; top: 0; width: 64mm; height: 296mm; color: {light}; padding: 14mm 7mm 10mm 10mm; overflow: hidden; z-index: 1; }
.side .contour { position: absolute; left: -10mm; top: -6mm; width: 95mm; opacity: .16; }
.side > * { position: relative; }
.name { font-family: 'Fraunces', Georgia, serif; font-weight: 600; font-size: 23pt; line-height: 1.02; letter-spacing: -.015em; margin: 0 0 3mm; }
.name span { color: {gold}; }
.tag { font-size: 8.2pt; line-height: 1.4; color: {soft}; margin: 0 0 5mm; }
.links { list-style: none; padding: 0; margin: 0 0 5mm; font-size: 8.1pt; color: {light}; }
.links li { margin: 0 0 1.1mm; }
.side h3 { font-family: 'Inter', sans-serif; font-size: 7.4pt; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: {gold}; margin: 5mm 0 1.6mm; padding-bottom: 1.2mm; border-bottom: .5pt solid rgba({gold_rgb},.45); }
.side h4 { font-size: 8.1pt; font-weight: 600; margin: 2mm 0 .5mm; color: {light}; }
.side p { font-size: 7.9pt; line-height: 1.38; margin: 0 0 1.4mm; color: #E6E2DA; }
.main { margin-left: 64mm; padding: 0 12mm 0 11mm; position: relative; z-index: 1; }
.flow { width: 100%; border-collapse: collapse; }
.flow td, .flow th { padding: 0; vertical-align: top; }
.flow thead th { height: 13mm; }
.flow tfoot td { height: 10mm; }
.main h2 { font-family: 'Fraunces', Georgia, serif; font-size: 12.5pt; font-weight: 600; letter-spacing: -.01em; margin: 4.6mm 0 1.8mm; color: {dark}; display: flex; align-items: center; gap: 3mm; break-after: avoid; }
.main h2:first-child { margin-top: 0; }
.main h2::after { content: ""; flex: 1; height: .6pt; background: {gold}; }
.main p { margin: 0 0 1.8mm; }
.job { margin: 0 0 3mm; break-inside: avoid; }
.job h3 { font-family: 'Inter', sans-serif; font-size: 10pt; font-weight: 600; margin: 0; }
.job .meta { font-size: 8.4pt; color: {accent2}; font-weight: 500; margin: .3mm 0 1mm; }
ul { margin: 0 0 1.5mm; padding-left: 4mm; }
li { margin: 0 0 .8mm; padding-left: .5mm; }
li::marker { color: {gold}; }
.foot { font-size: 7.4pt; color: #8A959B; margin-top: 4mm; display: flex; justify-content: space-between; }
.foot b { color: {gold}; font-weight: 600; }
"""

CONTOUR = """<svg class="contour" viewBox="0 0 400 300" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="__SOFT__" stroke-width="1.2">
<path d="M20 260 C60 200,120 220,160 170 S240 90,300 80 S380 60,400 40"/>
<path d="M0 235 C50 185,110 200,150 150 S225 75,290 65 S370 45,400 25"/>
<path d="M0 210 C45 170,100 180,140 130 S215 60,280 50 S360 30,400 10"/>
<path d="M0 185 C40 155,90 160,130 110 S205 45,270 35 S350 15,400 -5"/>
<path d="M0 160 C35 140,80 140,120 90 S195 30,260 20 S340 0,400 -20"/>
<path d="M60 300 C100 260,150 270,190 230 S270 170,330 160 S400 140,400 130"/>
<path d="M100 300 C140 270,190 280,230 245 S300 195,360 185 S400 170,400 165"/>
</svg>"""


def esc(s):
    return s  # content is trusted HTML written above


def css():
    g=PAL["gold"].lstrip("#"); rgb=",".join(str(int(g[i:i+2],16)) for i in (0,2,4))
    out=CSS_T.replace("{gold_rgb}",rgb)
    for k,v in PAL.items(): out=out.replace("{"+k+"}",v)
    return out

def render(cv):
    side = [CONTOUR.replace('__SOFT__', PAL['soft']), f'<h1 class="name">{cv["title"].replace(" ", "<br>", 1)}<span>.</span></h1>',
            f'<p class="tag">{cv["tag"]}</p>',
            "<ul class='links'>" + "".join(f"<li>{l}</li>" for l in cv["links"]) + "</ul>"]
    for head, items in cv["side"]:
        side.append(f"<h3>{head}</h3>")
        for h4, body in items:
            if h4:
                side.append(f"<h4>{h4}</h4>")
            side.append(f"<p>{body}</p>")
    main = []
    for head, kind, body in cv["main"]:
        main.append(f"<h2>{head}</h2>")
        if kind == "blocks":
            for block_kind, block_body in body:
                if block_kind == "p":
                    main.append(f"<p>{block_body}</p>")
                elif block_kind == "list":
                    main.append("<ul>" + "".join(f"<li>{x}</li>" for x in block_body) + "</ul>")
        elif kind == "jobs":
            for org, meta, desc, bullets in body:
                main.append('<div class="job">')
                main.append(f"<h3>{org}</h3>")
                if meta:
                    main.append(f'<div class="meta">{meta}</div>')
                if desc:
                    main.append(f"<p>{desc}</p>")
                if bullets:
                    main.append("<ul>" + "".join(f"<li>{b}</li>" for b in bullets) + "</ul>")
                main.append("</div>")
    main.append('<div class="foot"><span>Marco Bernasocchi · berna.io · October 2026</span><span><b>Keep seeding.</b></span></div>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{cv['title']}</title><style>{css()}</style></head>
<body><div class="band"></div><div class="page"><aside class="side">{''.join(side)}</aside><main class="main"><table class="flow"><thead><tr><th></th></tr></thead><tfoot><tr><td></td></tr></tfoot><tbody><tr><td>{''.join(main)}</td></tr></tbody></table></main></div></body></html>"""


import os, json
if os.environ.get("PAL"): PAL.update(json.loads(os.environ["PAL"]))
SUF=os.environ.get("SUF","")

CHROMIUM = os.environ.get("CHROMIUM") or next((p for p in map(shutil.which, ("chromium", "chromium-browser", "google-chrome", "chrome")) if p), None)

def build_with_chromium(html_path, pdf_path):
    """Build a PDF with a system Chromium binary."""
    if not CHROMIUM:
        raise SystemExit("No Chromium binary found. Install Chromium (for example, `apt install chromium`) or set CHROMIUM=/path/to/chrome.")
    subprocess.run([CHROMIUM, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
                    "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", html_path.as_uri()],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def main():
    PDF_OUT.mkdir(parents=True, exist_ok=True)
    for cv in (parse(p) for p in CONTENT):
        html_path = OUT / f"{cv['file']}{SUF}.html"
        pdf_path = PDF_OUT / f"{cv['file']}{SUF}.pdf"
        html_path.write_text(render(cv), encoding="utf-8")
        build_with_chromium(html_path, pdf_path)
        html_path.unlink()
        print("built", cv["file"], "->", pdf_path)

main()
