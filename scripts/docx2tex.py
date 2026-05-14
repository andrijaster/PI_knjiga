#!/usr/bin/env python3
"""Конвертер .docx → .tex за уџбеник.

Чита word/document.xml, чува наслове (Heading1..5), пасусе, листе, табеле,
екстрахује слике у одредишни фолдер и шаље LaTeX на излаз.

Употреба:
    docx2tex.py <docx-fajl> <chapter-prefix> <images-out-dir> <tex-out-file>

chapter-prefix: 01, 02, 03 — користи се за именовање слика и нумерисање.
"""
from __future__ import annotations
import sys
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PIC = "{http://schemas.openxmlformats.org/drawingml/2006/picture}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"


def omml_to_latex(elem):
    """Грубо OMML → LaTeX за inline формуле."""
    if elem is None:
        return ''
    tag = elem.tag.replace(M, '')
    if tag == 't':
        return elem.text or ''
    if tag == 'r':
        return ''.join(omml_to_latex(c) for c in elem)
    if tag in ('oMath', 'oMathPara'):
        return ''.join(omml_to_latex(c) for c in elem)
    if tag == 'sSub':
        e = sub = None
        for c in elem:
            t = c.tag.replace(M, '')
            if t == 'e': e = c
            elif t == 'sub': sub = c
        return omml_to_latex(e) + '_{' + omml_to_latex(sub) + '}'
    if tag == 'sSup':
        e = sup = None
        for c in elem:
            t = c.tag.replace(M, '')
            if t == 'e': e = c
            elif t == 'sup': sup = c
        return omml_to_latex(e) + '^{' + omml_to_latex(sup) + '}'
    if tag == 'sSubSup':
        e = sub = sup = None
        for c in elem:
            t = c.tag.replace(M, '')
            if t == 'e': e = c
            elif t == 'sub': sub = c
            elif t == 'sup': sup = c
        return omml_to_latex(e) + '_{' + omml_to_latex(sub) + '}^{' + omml_to_latex(sup) + '}'
    if tag == 'f':
        num = den = None
        for c in elem:
            t = c.tag.replace(M, '')
            if t == 'num': num = c
            elif t == 'den': den = c
        return '\\frac{' + omml_to_latex(num) + '}{' + omml_to_latex(den) + '}'
    if tag == 'rad':
        e = deg = None
        for c in elem:
            t = c.tag.replace(M, '')
            if t == 'e': e = c
            elif t == 'deg': deg = c
        if deg is not None and ''.join(omml_to_latex(c) for c in deg).strip():
            return '\\sqrt[' + omml_to_latex(deg) + ']{' + omml_to_latex(e) + '}'
        return '\\sqrt{' + omml_to_latex(e) + '}'
    if tag == 'nary':
        chr_ = ''
        e = sub = sup = None
        for c in elem:
            t = c.tag.replace(M, '')
            if t == 'naryPr':
                chr_elem = c.find(M + 'chr')
                if chr_elem is not None:
                    chr_ = chr_elem.get(M + 'val', '∑')
            elif t == 'e': e = c
            elif t == 'sub': sub = c
            elif t == 'sup': sup = c
        op = '\\sum' if chr_ in ('∑', '', None) else '\\int' if chr_ == '∫' else '\\prod' if chr_ == '∏' else '\\sum'
        s = op
        if sub is not None: s += '_{' + omml_to_latex(sub) + '}'
        if sup is not None: s += '^{' + omml_to_latex(sup) + '}'
        if e is not None: s += ' ' + omml_to_latex(e)
        return s
    if tag == 'd':
        e_parts = [omml_to_latex(c) for c in elem if c.tag.replace(M,'')=='e']
        return '(' + ''.join(e_parts) + ')'
    if tag == 'm':
        rows = []
        for mr in elem.findall(M + 'mr'):
            cells = [omml_to_latex(c) for c in mr if c.tag.replace(M,'')=='e']
            rows.append(' & '.join(cells))
        return '\\begin{matrix} ' + ' \\\\ '.join(rows) + ' \\end{matrix}'
    return ''.join(omml_to_latex(c) for c in elem)


_MATH_REPLACEMENTS = [
    ('⇒', r' \Rightarrow '), ('∪', r' \cup '), ('∩', r' \cap '),
    ('∈', r' \in '), ('⊆', r' \subseteq '), ('⊂', r' \subset '),
    ('⋅', r' \cdot '), ('…', r' \ldots '), ('∞', r'\infty '),
    ('β', r'\beta '), ('α', r'\alpha '), ('σ', r'\sigma '),
    ('π', r'\pi '), ('η', r'\eta '), ('μ', r'\mu '),
    ('θ', r'\theta '), ('λ', r'\lambda '), ('γ', r'\gamma '),
    ('δ', r'\delta '), ('ε', r'\epsilon '), ('ω', r'\omega '),
    ('Σ', r'\Sigma '), ('Δ', r'\Delta '), ('Π', r'\Pi '),
    ('Ω', r'\Omega '), ('≤', r' \le '), ('≥', r' \ge '),
    ('≠', r' \ne '), ('≈', r' \approx '), ('×', r' \times '),
    ('|', r'\vert '),
]


def latex_math_cleanup(s: str) -> str:
    import re as _re
    for old, new in _MATH_REPLACEMENTS:
        s = s.replace(old, new)
    s = _re.sub(r'([а-яА-Я][а-яА-Я]+)', lambda m: r'\textrm{' + m.group(1) + r'}', s)
    return s

# LaTeX special chars → escape
LATEX_ESCAPE = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# Heading level → LaTeX command. The first Heading1/Heading2 in the file is the chapter title.
HEADING_CMDS = {
    1: r"\chapter",
    2: r"\section",
    3: r"\subsection",
    4: r"\subsubsection",
    5: r"\paragraph",
    6: r"\subparagraph",
}


def latex_escape(text: str) -> str:
    """Escape LaTeX special characters in plain text."""
    out = []
    for ch in text:
        if ch in LATEX_ESCAPE:
            out.append(LATEX_ESCAPE[ch])
        elif ch == '"':
            out.append('„')  # placeholder, csquotes-friendly
        else:
            out.append(ch)
    return "".join(out)


def get_text_from_run(r: ET.Element) -> str:
    """Extract concatenated text from a <w:r> run, preserving spaces."""
    parts = []
    for t in r:
        tag = t.tag
        if tag == W + "t":
            parts.append(t.text or "")
        elif tag == W + "tab":
            parts.append("\t")
        elif tag == W + "br":
            parts.append("\n")
    return "".join(parts)


def get_run_formatting(r: ET.Element) -> dict:
    """Detect bold, italic, monospaced."""
    rpr = r.find(W + "rPr")
    fmt = {"bold": False, "italic": False, "mono": False}
    if rpr is None:
        return fmt
    if rpr.find(W + "b") is not None:
        fmt["bold"] = True
    if rpr.find(W + "i") is not None:
        fmt["italic"] = True
    rfonts = rpr.find(W + "rFonts")
    if rfonts is not None:
        ascii_font = (rfonts.get(W + "ascii") or "").lower()
        if any(m in ascii_font for m in ("courier", "consolas", "mono")):
            fmt["mono"] = True
    return fmt


def wrap_run(text: str, fmt: dict) -> str:
    """Wrap escaped text in LaTeX formatting commands."""
    if not text.strip():
        return text
    escaped = latex_escape(text)
    if fmt["mono"]:
        escaped = r"\texttt{" + escaped + "}"
    if fmt["bold"] and fmt["italic"]:
        escaped = r"\textbf{\textit{" + escaped + "}}"
    elif fmt["bold"]:
        escaped = r"\textbf{" + escaped + "}"
    elif fmt["italic"]:
        escaped = r"\textit{" + escaped + "}"
    return escaped


def get_paragraph_style(p: ET.Element) -> tuple[str | None, int | None]:
    """Return (style_id, numId for list items)."""
    ppr = p.find(W + "pPr")
    if ppr is None:
        return None, None
    style_id = None
    pstyle = ppr.find(W + "pStyle")
    if pstyle is not None:
        style_id = pstyle.get(W + "val")
    numId = None
    numpr = ppr.find(W + "numPr")
    if numpr is not None:
        nid = numpr.find(W + "numId")
        if nid is not None:
            try:
                numId = int(nid.get(W + "val"))
            except (TypeError, ValueError):
                numId = None
    return style_id, numId


def heading_level(style: str | None) -> int | None:
    if not style:
        return None
    m = re.match(r"Heading(\d+)", style)
    if m:
        return int(m.group(1))
    return None


def extract_image_rels(docx_path: str) -> dict[str, str]:
    """Return {rId: media-internal-path}."""
    rels: dict[str, str] = {}
    with zipfile.ZipFile(docx_path) as z:
        try:
            data = z.read("word/_rels/document.xml.rels")
        except KeyError:
            return rels
        root = ET.fromstring(data)
        for rel in root:
            rid = rel.get("Id")
            target = rel.get("Target", "")
            if "media/" in target:
                rels[rid] = target if target.startswith("media/") else target.split("/", 1)[-1]
    return rels


def extract_images(docx_path: str, prefix: str, out_dir: Path, rels: dict[str, str]) -> dict[str, str]:
    """Extract media images. Returns {rId: new-filename}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    with zipfile.ZipFile(docx_path) as z:
        # Sort rIds by numeric suffix of media path for deterministic numbering
        def key(item):
            rid, target = item
            m = re.search(r"image(\d+)", target)
            return int(m.group(1)) if m else 999
        for rid, target in sorted(rels.items(), key=key):
            internal = "word/" + target if not target.startswith("word/") else target
            try:
                data = z.read(internal)
            except KeyError:
                # try alt
                try:
                    data = z.read("word/media/" + os.path.basename(target))
                except KeyError:
                    continue
            ext = os.path.splitext(target)[1].lower() or ".png"
            new_name = f"{prefix}-{len(mapping)+1:02d}{ext}"
            (out_dir / new_name).write_bytes(data)
            mapping[rid] = new_name
    return mapping


def process_paragraph(p: ET.Element, image_map: dict[str, str], prefix: str) -> tuple[str, str, int | None]:
    """Return (kind, latex_text, list_numId).

    kind ∈ {"heading-N", "para", "list", "image", "empty"}
    """
    style, numId = get_paragraph_style(p)
    level = heading_level(style)

    # Прво ископај све OMML формуле унутар пасуса
    omml_formulas: list[str] = []
    for omath in list(p.iter(M + 'oMath')) + list(p.iter(M + 'oMathPara')):
        latex = omml_to_latex(omath).strip()
        if latex:
            omml_formulas.append(latex_math_cleanup(latex))

    # Collect runs
    runs_text: list[str] = []
    images: list[str] = []
    for child in p.iter():
        if child.tag == W + "r":
            # Find image references inside this run
            for blip in child.iter(A + "blip"):
                rid = blip.get(R + "embed")
                if rid and rid in image_map:
                    images.append(image_map[rid])
            fmt = get_run_formatting(child)
            text = get_text_from_run(child)
            if text:
                runs_text.append(wrap_run(text, fmt))

    body = "".join(runs_text).strip()

    # Ако пасус има формуле, додај их као display math на крај тела
    if omml_formulas:
        for f in omml_formulas:
            body += f"\n\n\\[\n{f}\n\\]\n"
        return "para", body + "\n", None

    if images and not body:
        # Pure image paragraph
        latex = ""
        for img in images:
            latex += (
                "\n\\begin{figure}[h]\n"
                "    \\centering\n"
                f"    \\includegraphics[width=0.85\\linewidth]{{slike/{prefix}/{img}}}\n"
                f"    \\caption{{}}\n"
                "\\end{figure}\n"
            )
        return "image", latex, None

    if images and body:
        # mixed
        latex = body + "\n"
        for img in images:
            latex += (
                "\n\\begin{figure}[h]\n"
                "    \\centering\n"
                f"    \\includegraphics[width=0.85\\linewidth]{{slike/{prefix}/{img}}}\n"
                f"    \\caption{{}}\n"
                "\\end{figure}\n"
            )
        return "para", latex, None

    if level is not None:
        if not body:
            return "empty", "", None
        cmd = HEADING_CMDS.get(level, r"\paragraph")
        # Strip leading section numbers like "1.2.3 " (we let LaTeX number)
        clean = re.sub(r"^\s*\d+(\.\d+)*\.?\s+", "", body)
        return f"heading-{level}", f"\n{cmd}{{{clean}}}\n", None

    if not body:
        return "empty", "", None

    if numId is not None:
        return "list", body, numId

    return "para", body + "\n", None


def process_table(tbl: ET.Element, image_map: dict[str, str], prefix: str) -> str:
    """Render a <w:tbl> as a LaTeX tabular."""
    rows: list[list[str]] = []
    for row in tbl.findall(W + "tr"):
        cells: list[str] = []
        for cell in row.findall(W + "tc"):
            cell_parts: list[str] = []
            for p in cell.findall(W + "p"):
                kind, text, _ = process_paragraph(p, image_map, prefix)
                if kind not in ("empty", "image"):
                    cell_parts.append(text.strip())
            cells.append(" \\newline ".join(cell_parts))
        rows.append(cells)
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    col_spec = "|" + "p{0.9\\linewidth/" + str(ncols) + "}|" * ncols if False else "|" + "l|" * ncols
    out = ["\n\\begin{table}[h]", "\\centering", f"\\begin{{tabular}}{{{col_spec}}}", "\\hline"]
    for i, row in enumerate(rows):
        padded = row + [""] * (ncols - len(row))
        out.append(" & ".join(padded) + " \\\\")
        out.append("\\hline")
    out.append("\\end{tabular}")
    out.append("\\end{table}\n")
    return "\n".join(out)


def convert(docx_path: str, prefix: str, images_dir: str, out_tex: str, chapter_title_override: str | None = None) -> None:
    images_out = Path(images_dir)
    rels = extract_image_rels(docx_path)
    image_map = extract_images(docx_path, prefix, images_out, rels)

    with zipfile.ZipFile(docx_path) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    body = root.find(W + "body")
    assert body is not None

    output: list[str] = []
    output.append(f"% Аутоматски генерисано из {os.path.basename(docx_path)}\n")
    chapter_emitted = False
    current_list_numId: int | None = None

    def close_list():
        nonlocal current_list_numId
        if current_list_numId is not None:
            output.append("\\end{itemize}\n")
            current_list_numId = None

    for elem in body:
        tag = elem.tag
        if tag == W + "p":
            kind, text, numId = process_paragraph(elem, image_map, prefix)
            if kind.startswith("heading-"):
                close_list()
                level = int(kind.split("-")[1])
                # First heading becomes chapter regardless of level
                if not chapter_emitted:
                    chapter_emitted = True
                    if chapter_title_override:
                        output.append(f"\n\\chapter{{{chapter_title_override}}}\n")
                    else:
                        # Replace this heading's command with \chapter
                        text2 = re.sub(r"^\s*\\(chapter|section|subsection|subsubsection|paragraph|subparagraph)",
                                       r"\\chapter", text)
                        output.append(text2)
                    continue
                # demote: Heading2 → \section if file's chapter was at level 1; we keep relative levels
                output.append(text)
            elif kind == "list":
                if current_list_numId != numId:
                    close_list()
                    output.append("\\begin{itemize}\n")
                    current_list_numId = numId
                output.append(f"  \\item {text}\n")
            elif kind in ("para", "image"):
                close_list()
                if kind == "para":
                    output.append(text + "\n")
                else:
                    output.append(text)
            # empty → skip
        elif tag == W + "tbl":
            close_list()
            output.append(process_table(elem, image_map, prefix))
        elif tag == W + "sectPr":
            pass
    close_list()

    if not chapter_emitted and chapter_title_override:
        output.insert(1, f"\\chapter{{{chapter_title_override}}}\n")

    Path(out_tex).write_text("".join(output), encoding="utf-8")


def main():
    if len(sys.argv) < 5:
        print("Usage: docx2tex.py <docx> <prefix> <images_dir> <out_tex> [chapter_title]", file=sys.stderr)
        sys.exit(1)
    docx = sys.argv[1]
    prefix = sys.argv[2]
    images_dir = sys.argv[3]
    out_tex = sys.argv[4]
    title = sys.argv[5] if len(sys.argv) > 5 else None
    convert(docx, prefix, images_dir, out_tex, title)
    print(f"Wrote {out_tex}")


if __name__ == "__main__":
    main()
