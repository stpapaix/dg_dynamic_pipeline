"""Generate a customer-facing PDF explaining ops_pipeline3 and its Spark replacement.

Chapters:
  1. Pipeline ops_pipeline3 explained (steps, no diagram)
  2. The replacement notebook, rendered as clean readable code blocks
  3. Parallelism and scaling notes

Pure-Python: xhtml2pdf (HTML -> PDF).
"""

import html
import json
import os

from xhtml2pdf import pisa

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTEBOOK = os.path.join(_ROOT, "notebooks", "replace_ops_pipeline3.ipynb")
OUT_PDF = os.path.join(_ROOT, "reports", "ops_pipeline3_explained.pdf")


def load_cells():
    nb = json.load(open(NOTEBOOK, encoding="utf-8"))
    return [{"type": c["cell_type"], "src": "".join(c["source"])} for c in nb["cells"]]


def render_code(code):
    """Render a code cell as a clean, indentation-preserving monospace block."""
    lines = []
    for raw in code.split("\n"):
        esc = html.escape(raw)
        stripped = esc.lstrip(" ")
        indent = len(esc) - len(stripped)
        pad = "&nbsp;" * indent
        if stripped.startswith("#"):
            lines.append(pad + f'<font color="#6a9955">{stripped}</font>')  # comment
        else:
            lines.append((pad + stripped) if stripped else "&nbsp;")
    return '<div class="code">' + "<br/>".join(lines) + "</div>"


def md_inline(text):
    import re

    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r'<font face="Courier" color="#a31515">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


def render_markdown_cell(src):
    out = []
    for line in src.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("### "):
            out.append(f'<p class="h3">{md_inline(s[4:])}</p>')
        elif s.startswith("## "):
            out.append(f'<p class="h2">{md_inline(s[3:])}</p>')
        elif s.startswith("# "):
            out.append(f'<p class="h1cell">{md_inline(s[2:])}</p>')
        elif s.startswith("> "):
            out.append(f'<p class="note">{md_inline(s[2:])}</p>')
        elif s[:2] in ("- ", "* ") or (len(s) > 2 and s[0].isdigit() and s[1] == "."):
            out.append(f'<p class="li">{md_inline(s)}</p>')
        else:
            out.append(f"<p>{md_inline(s)}</p>")
    return "\n".join(out)


def render_notebook():
    parts = []
    for cell in load_cells():
        if cell["type"] == "markdown":
            parts.append(f'<div class="nbmd">{render_markdown_cell(cell["src"])}</div>')
        else:
            parts.append(render_code(cell["src"]))
    return "\n".join(parts)


CH1 = """
<p class="h1">Chapter 1 &ndash; The <font face="Courier">ops_pipeline3</font> pipeline</p>
<p><b>Purpose.</b> <font face="Courier">ops_pipeline3</font> is a <b>metadata-driven incremental
ingestion</b> pipeline. It copies data from an <b>Eventhouse (KQL database)</b> into
<b>Lakehouse Delta tables</b>, driven by a control table &ndash; so new source tables are onboarded by
simply adding a row, with no change to the pipeline itself.</p>
<p class="flow">datacopyjobsetup &nbsp;&#8594;&nbsp; LookupDueJobs &nbsp;&#8594;&nbsp; ForEach
&nbsp;&#8594;&nbsp; Copy (KQL &#8594; Lakehouse) &nbsp;&#8594;&nbsp; Delta tables</p>
<p class="h2">Parameters &amp; variables</p>
<p class="li">- <font face="Courier">ops_lakehouse</font> &ndash; target Lakehouse (control table + destination tables).</p>
<p class="li">- <font face="Courier">ops_kql_db</font> &ndash; source KQL / Eventhouse database.</p>
<p class="li">- <font face="Courier">vRunId</font> &ndash; variable capturing the pipeline Run Id.</p>
<p class="h2">Step 1 &ndash; LookupDueJobs (Lookup)</p>
<p>Reads <b>every row</b> of <font face="Courier">dbo.datacopyjobsetup</font>
(<font face="Courier">firstRowOnly = false</font>). Each row is one copy job with columns
<font face="Courier">SourceName</font>, <font face="Courier">WatermarkColumn</font>,
<font face="Courier">LastUpdated</font>, <font face="Courier">DestinationName</font>.</p>
<p class="h2">Step 2 &ndash; ForEach + CopyDynamicKQLTables</p>
<p>The <b>ForEach</b> loops over the lookup rows (<font face="Courier">batchCount = 20</font>). Each row runs one <b>Copy</b>:</p>
<p class="li">- <b>Source</b>: dynamic KQL
<font face="Courier">&lt;SourceName&gt; | where &lt;WatermarkColumn&gt; &gt; datetime(&lt;LastUpdated&gt;)</font>
(incremental pull).</p>
<p class="li">- <b>Sink</b>: Lakehouse table <font face="Courier">dbo.&lt;DestinationName&gt;</font>, <b>Append</b> (V-Order).</p>
<p class="note">Note: the pipeline never updates <font face="Courier">LastUpdated</font>; the notebook offers an optional step to advance it.</p>
"""

CH3 = """
<p class="h1">Chapter 3 &ndash; Parallelism &amp; scaling</p>
<p>The ForEach used <b>batchCount = 20</b>. In Spark the real limit is the <b>Eventhouse</b> concurrency:</p>
<p class="li">- <b>Single (query) mode</b> &ndash; query API, capped at <b>500,000 rows</b>. Small tables only.</p>
<p class="li">- <b>Distributed mode</b> &ndash; reads via <font face="Courier">.export</font>. No row cap, but uses an export slot.</p>
<p class="h2">Why concurrency was limited to 1</p>
<p>The Eventhouse reported <font face="Courier">Export Capacity: 1</font>, so 8 parallel jobs got <b>throttled</b>.</p>
<p align="center"><b>concurrent exports &#8776; total cores &#215; 0.75</b></p>
<p>So <font face="Courier">max_parallel = 8</font> needs about <b>11 warm cores</b>.</p>
<p class="h2">Scaling on your F64 capacity</p>
<p>Open the <b>Eventhouse</b> &rarr; <b>Capacity Planner</b> and raise <b>Minimum consumption</b>; verify with
<font face="Courier">.show capacity</font> (Export row) before raising <font face="Courier">max_parallel</font>.</p>
<table width="72%" align="center" cellpadding="6" style="margin-top:8px; border:0.75pt solid #999;">
<tr style="background-color:#0f6cbd; color:#ffffff;"><td><b>max_parallel</b></td><td><b>Warm cores (~)</b></td><td><b>Action</b></td></tr>
<tr><td>1 (current)</td><td>any</td><td>nothing &ndash; sequential, safe on Capacity 1</td></tr>
<tr style="background-color:#f3f3f3;"><td>4</td><td>~6</td><td>raise Minimum consumption 1&ndash;2 levels</td></tr>
<tr><td>8</td><td>~11</td><td>Minimum consumption to Medium/Large</td></tr>
</table>
<p class="note">Keeping more cores warm increases cost &ndash; raise for the batch window, then lower again.
The notebook keeps a retry-with-backoff as a safety net for transient throttling.</p>
"""

CSS = """
@page { size: A4; margin: 1.8cm 1.6cm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 10pt; color: #1b1b1b; line-height: 1.4; }
p { margin: 4px 0; }
.cover-title { font-size: 26pt; color: #0f6cbd; font-weight: bold; margin-top: 240px; text-align: center; }
.cover-sub { font-size: 12pt; color: #555; text-align: center; margin-top: 10px; }
.h1 { font-size: 17pt; color: #0f6cbd; font-weight: bold; border-bottom: 1.5pt solid #0f6cbd; padding-bottom: 4px; }
.h2 { font-size: 12.5pt; color: #0b5394; font-weight: bold; margin-top: 12px; }
.h3 { font-size: 11pt; color: #333; font-weight: bold; margin-top: 8px; }
.h1cell { font-size: 13pt; color: #0f6cbd; font-weight: bold; }
.li { margin: 3px 0 3px 12px; }
.flow { text-align: center; background-color: #eef6fc; border: 0.75pt solid #0f6cbd; color: #0b5394;
        padding: 7px; margin: 10px 0; font-size: 10.5pt; font-weight: bold; }
.note { background-color: #fff7e6; border-left: 3pt solid #d68a00; padding: 6px 9px; margin: 8px 0; }
.nbmd { margin: 10px 0 2px 0; }
.code { background-color: #f6f8fa; border-left: 3pt solid #0f6cbd; padding: 8px 10px; margin: 4px 0 12px 0;
        font-family: Courier, monospace; font-size: 8.5pt; line-height: 1.45; }
"""

HTML_DOC = f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="cover-title">Modernizing ops_pipeline3</div>
<div class="cover-sub">From a Data Factory pipeline to a Spark notebook in Microsoft Fabric</div>
<div class="cover-sub">Prepared for the customer &middot; 2026-09-03</div>
<div style="page-break-after: always;"></div>
{CH1}
<div style="page-break-after: always;"></div>
<p class="h1">Chapter 2 &ndash; The replacement notebook</p>
<p>Markdown cells are shown as formatted text; code cells are shown as clean, readable code blocks with preserved indentation.</p>
{render_notebook()}
<div style="page-break-after: always;"></div>
{CH3}
</body></html>"""


def main():
    os.makedirs(os.path.dirname(OUT_PDF), exist_ok=True)
    with open(OUT_PDF, "wb") as fh:
        result = pisa.CreatePDF(HTML_DOC, dest=fh)
    if result.err:
        raise RuntimeError("PDF generation failed")
    print(f"PDF written to {OUT_PDF}")


if __name__ == "__main__":
    main()
