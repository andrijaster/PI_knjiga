#!/usr/bin/env python3
"""Постпроцесинг LaTeX фајлова насталих из docx-а:
- скида општи `\\textbf{\\textit{...}}` омотач око целог пасуса када га аутор
  докуменама користи као дифолт стил (јер цео текст постаје масно-курзив, што
  у штампи није жељено)
- уклања ауто-генерисане редове попут "Table of Contents", "Литература\\n\\d+"
- стандардизује пасусне размаке

Употреба: postprocess.py <input.tex> [<output.tex>]
"""
from __future__ import annotations
import sys
import re
from pathlib import Path


def strip_global_bolditalic(text: str) -> str:
    # Прво: на нивоу целе линије која се састоји само од `\textbf{\textit{...}}` —
    # склони омотач (али сачувај остатак)
    out_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        # уклоплети омотач у више корака
        # ниво линије: страпуј само ако се ради о једном омотачу који обухвата целу линију
        m = re.fullmatch(r"\\textbf\{\\textit\{(.+)\}\}", stripped)
        if m and "\\textbf" not in m.group(1) and "\\textit" not in m.group(1):
            out_lines.append(m.group(1))
            continue
        m = re.fullmatch(r"\\textit\{\\textbf\{(.+)\}\}", stripped)
        if m and "\\textbf" not in m.group(1) and "\\textit" not in m.group(1):
            out_lines.append(m.group(1))
            continue
        out_lines.append(line)
    text = "\n".join(out_lines)

    # Сада на нивоу инлајн фрагмената — \textbf{\textit{...}} који обухвата
    # дугачак чисти текст без угнежђених команди (>40 знакова) — третира се
    # као default style и облик се скида.
    def maybe_strip(m: re.Match) -> str:
        inner = m.group(1)
        # ако садржи угнежђене команде, не дирај
        if "\\" in inner:
            return m.group(0)
        if len(inner) < 40:
            return m.group(0)
        return inner

    text = re.sub(r"\\textbf\{\\textit\{([^{}]+)\}\}", maybe_strip, text)
    text = re.sub(r"\\textit\{\\textbf\{([^{}]+)\}\}", maybe_strip, text)
    return text


def remove_junk(text: str) -> str:
    # Уклони "Table of Contents" реткове на врху
    text = re.sub(r"^\s*\\textbf\{\\textit\{Table of Contents\}\}\s*\n+", "", text, count=1)
    text = re.sub(r"^\s*\\textbf\{Table of Contents\}\s*\n+", "", text, count=1)
    text = re.sub(r"^\s*Table of Contents\s*\n+", "", text, count=1)
    # Уклони усамљене бројеве (page numbers сачуване из TOC-а)
    text = re.sub(r"^\s*\d+\s*$\n", "", text, flags=re.MULTILINE)
    return text


def normalize_blank_lines(text: str) -> str:
    # више од две узастопне празне линије -> две
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def process(text: str) -> str:
    text = strip_global_bolditalic(text)
    text = remove_junk(text)
    # second pass — после стрипинга могло је да се појави нови junk
    text = re.sub(r"^Table of Contents\s*$", "", text, flags=re.MULTILINE)
    text = normalize_blank_lines(text)
    return text


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: postprocess.py <in.tex> [<out.tex>]", file=sys.stderr)
        sys.exit(1)
    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else inp
    src = Path(inp).read_text(encoding="utf-8")
    processed = process(src)
    Path(out).write_text(processed, encoding="utf-8")
    print(f"Wrote {out} ({len(processed)} bytes)")


if __name__ == "__main__":
    main()
