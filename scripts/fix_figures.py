#!/usr/bin/env python3
"""Поправка фигура и табела у поглављима:

1) Сваки `\\begin{figure}...\\end{figure}` који има празан `\\caption{}` и након
   њега у следећем непразном пасусу почиње „Слика N.N.…" → опис се убацује у
   `\\caption{}`, додаје се `\\label{fig:<broj>}`, а изворни bare-text пасус се
   уклања.

2) Дуплиране фигуре заредом које показују исту слику се мерџују у једну.

3) `\\resizebox{\\textwidth}{!}{...}` се мења у `\\adjustbox{max width=\\textwidth}{...}`
   тако да се мале табеле не растежу — само превелике се смањују.

4) Где год се у телу текста појави фраза „на Слици N.N.", „Слика N.N." итд., замена
   са `\\ref{fig:<broj>}` или `Сликом~\\ref{fig:<broj>}`.

5) Аналогно и за табеле.
"""
from __future__ import annotations
import sys
import re
from pathlib import Path

FIG_RE = re.compile(
    r"\\begin\{figure\}(?:\[[^\]]*\])?\s*(.*?)\\end\{figure\}",
    re.DOTALL,
)

# „Слика 1.12 Опис..." или „Слика 1.12. Опис" или „Слика 1.12: Опис" или само „Слика 1.12"
SLIKA_CAPTION_RE = re.compile(
    r"^\s*\\textit\{\s*Слика\s+(\d+\.?\d*)\.?\s*(.*?)\s*\}\s*$|"
    r"^\s*Слика\s+(\d+\.?\d*)\.?\s*(.+?)\s*$",
    re.MULTILINE,
)

# „Табела 1.12 Опис..." исто као слика
TABELA_CAPTION_RE = re.compile(
    r"^\s*\\textit\{\s*Табела\s+(\d+\.?\d*)\.?\s*(.*?)\s*\}\s*$|"
    r"^\s*Табела\s+(\d+\.?\d*)\.?\s*(.+?)\s*$",
    re.MULTILINE,
)


def process_figures(text: str, chapter: str) -> tuple[str, list[tuple[str, str]]]:
    """Обради све `figure` окружења, премести описе у `\\caption{}`.

    Враћа (нов текст, листа (figure_number, caption_text) за касније референцирање).
    Бројеви слика се додељују секвенцијално (chapter.1, chapter.2, ...).
    """
    figures_found: list[tuple[str, str]] = []
    out_parts: list[str] = []
    pos = 0
    seq = 0  # секвенцијални број у овом поглављу
    fig_iter = list(re.finditer(r"\\begin\{figure\}(?:\[[^\]]*\])?", text))
    for m in fig_iter:
        end_m = re.search(r"\\end\{figure\}", text[m.end():])
        if not end_m:
            continue
        fig_start = m.start()
        fig_end = m.end() + end_m.end()
        fig_content = text[fig_start:fig_end]
        out_parts.append(text[pos:fig_start])

        # Ако фигура већ има непразан \caption{...} — само додај \label{}
        m_existing = re.search(r"\\caption\{([^{}]*?(?:\{[^{}]*\}[^{}]*)*)\}", fig_content)
        if m_existing and m_existing.group(1).strip():
            seq += 1
            cap_num_assigned = f"{int(chapter)}.{seq}"
            label = f"fig:{chapter}-{seq}"
            cap_text_existing = m_existing.group(1).strip()
            # ако нема \label, додај га
            if "\\label{" not in fig_content:
                new_fig = fig_content.replace(
                    "\\end{figure}", f"    \\label{{{label}}}\n\\end{{figure}}"
                )
            else:
                new_fig = fig_content
            figures_found.append((cap_num_assigned, cap_text_existing))
            out_parts.append(new_fig)
            pos = fig_end
            continue

        # Шта следи након фигуре? Тражимо bare-text опис.
        after = text[fig_end:]
        next_chunk = after.lstrip()
        skipped = len(after) - len(next_chunk)
        m_cap = re.match(r"(.*?)(?:\n\s*\n|\n\\|\Z)", next_chunk, re.DOTALL)
        caption_block = m_cap.group(1).strip() if m_cap else ""

        cap_text: str | None = None
        # Покушај 1: „Слика N.N. опис" или „Слика . опис" или „Слика А: опис"
        m_slika = re.match(
            r"^(?:\\textit\{)?\s*Слика\s*(?:\d+\.?\d*|[А-Яа-я]|\.)?[.:]?\s*(.+?)\s*\}?\s*$",
            caption_block, re.DOTALL,
        )
        if m_slika and m_slika.group(1).strip():
            cap_text = m_slika.group(1).strip().rstrip("}").rstrip(".")
        elif caption_block and len(caption_block) < 400 and not caption_block.startswith("\\"):
            # Описни пасус без „Слика" префикса — узми као caption ако није предугачак
            cap_text = caption_block.rstrip(".")
            # Уклони могуће `\textbf{\textit{...}}` омотаче
            cap_text = re.sub(r"\\textbf\{\\textit\{([^{}]+)\}\}", lambda m: m.group(1), cap_text)
            cap_text = re.sub(r"\\textit\{\\textbf\{([^{}]+)\}\}", lambda m: m.group(1), cap_text)
        cap_num = None  # увек секвенцијално додељујемо
        if cap_text:
            seq += 1
            cap_num = f"{int(chapter)}.{seq}"

        # ажурирај \caption{}
        new_fig = fig_content
        if cap_num and cap_text is not None:
            label = f"fig:{chapter}-{seq}"
            new_caption = f"\\caption{{{cap_text}}}\n    \\label{{{label}}}"
            # замени први `\caption{...}` (било празан или нет) — користимо lambda да избегнемо escape парсирање
            new_fig2, n = re.subn(r"\\caption\{[^{}]*\}(?:\s*\\label\{[^}]*\})?", lambda _m: new_caption, new_fig, count=1)
            if n == 0:
                new_fig2 = new_fig.replace("\\end{figure}", f"    {new_caption}\n\\end{{figure}}")
            new_fig = new_fig2
            figures_found.append((cap_num, cap_text))
            out_parts.append(new_fig)
            # advance pos past the figure AND the caption block
            pos = fig_end + skipped + len(m_cap.group(1)) if m_cap else fig_end
        else:
            out_parts.append(new_fig)
            pos = fig_end

    out_parts.append(text[pos:])
    return "".join(out_parts), figures_found


def process_tables(text: str, chapter: str) -> tuple[str, list[tuple[str, str]]]:
    """Аналогно за табеле — `\\begin{table}` блокови."""
    tables_found: list[tuple[str, str]] = []
    out_parts: list[str] = []
    pos = 0
    seq = 0
    for m in list(re.finditer(r"\\begin\{table\}(?:\[[^\]]*\])?", text)):
        end_m = re.search(r"\\end\{table\}", text[m.end():])
        if not end_m:
            continue
        tab_start = m.start()
        tab_end = m.end() + end_m.end()
        tab_content = text[tab_start:tab_end]
        out_parts.append(text[pos:tab_start])

        # Ако табела већ има непразан \caption{...}
        m_existing = re.search(r"\\caption\{([^{}]*?(?:\{[^{}]*\}[^{}]*)*)\}", tab_content)
        if m_existing and m_existing.group(1).strip():
            seq += 1
            label = f"tab:{chapter}-{seq}"
            cap_text_existing = m_existing.group(1).strip()
            if "\\label{" not in tab_content:
                new_tab = tab_content.replace(
                    "\\end{table}", f"    \\label{{{label}}}\n\\end{{table}}"
                )
            else:
                new_tab = tab_content
            tables_found.append((f"{int(chapter)}.{seq}", cap_text_existing))
            out_parts.append(new_tab)
            pos = tab_end
            continue

        after = text[tab_end:]
        next_chunk = after.lstrip()
        skipped = len(after) - len(next_chunk)
        m_cap = re.match(r"(.*?)(?:\n\s*\n|\n\\|\Z)", next_chunk, re.DOTALL)
        caption_block = m_cap.group(1).strip() if m_cap else ""
        cap_text = None
        m_tabela = re.match(
            r"^(?:\\textit\{)?\s*Табела\s*(?:\d+\.?\d*|[А-Яа-я]|\.)?[.:]?\s*(.+?)\s*\}?\s*$",
            caption_block, re.DOTALL,
        )
        if m_tabela and m_tabela.group(1).strip():
            cap_text = m_tabela.group(1).strip().rstrip("}").rstrip(".")
            cap_text = re.sub(r"\\textbf\{\\textit\{([^{}]+)\}\}", lambda m: m.group(1), cap_text)
        cap_num = None
        if cap_text:
            seq += 1
            cap_num = f"{int(chapter)}.{seq}"

        new_tab = tab_content
        if cap_num and cap_text is not None:
            label = f"tab:{chapter}-{seq}"
            new_caption = f"\\caption{{{cap_text}}}\n    \\label{{{label}}}"
            new_tab2, n = re.subn(r"\\caption\{[^{}]*\}(?:\s*\\label\{[^}]*\})?", lambda _m: new_caption, new_tab, count=1)
            if n == 0:
                new_tab2 = new_tab.replace("\\end{table}", f"    {new_caption}\n\\end{{table}}")
            new_tab = new_tab2
            tables_found.append((cap_num, cap_text))
            out_parts.append(new_tab)
            pos = tab_end + skipped + len(m_cap.group(1)) if m_cap else tab_end
        else:
            out_parts.append(new_tab)
            pos = tab_end

    out_parts.append(text[pos:])
    return "".join(out_parts), tables_found


def replace_references(text: str, figures: list[tuple[str, str]], tables: list[tuple[str, str]], chapter: str) -> str:
    """Замени помињања „Слика N.N." у тексту референцама `\\ref{}`."""
    # Skip inside figure/table environments to avoid replacing \caption text
    # Mark protected regions
    protected: list[tuple[int, int]] = []
    for m in re.finditer(r"\\begin\{(figure|table)\}.*?\\end\{\1\}", text, re.DOTALL):
        protected.append(m.span())

    def in_protected(idx: int) -> bool:
        for s, e in protected:
            if s <= idx < e:
                return True
        return False

    # Мапа од броја у листи (нпр. "1.5") -> seq у labelu (нпр. 5)
    fig_map = {num: idx + 1 for idx, (num, _) in enumerate(figures)}
    tab_map = {num: idx + 1 for idx, (num, _) in enumerate(tables)}

    def repl_fig(m: re.Match) -> str:
        if in_protected(m.start()):
            return m.group(0)
        prefix = m.group(1)
        num = m.group(2).rstrip(".")
        if num not in fig_map:
            return m.group(0)
        label = f"fig:{chapter}-{fig_map[num]}"
        return f"{prefix}~\\ref{{{label}}}"

    text = re.sub(r"(Слик[аеуои]|Сликом)\s+(\d+\.\d+)\.?", repl_fig, text)

    # Такође покривамо просте бројеве „Слика N" — мапирају се на seq у поглављу
    def repl_fig_bare(m: re.Match) -> str:
        if in_protected(m.start()):
            return m.group(0)
        prefix = m.group(1)
        try:
            num = int(m.group(2))
        except ValueError:
            return m.group(0)
        if 1 <= num <= len(figures):
            label = f"fig:{chapter}-{num}"
            return f"{prefix}~\\ref{{{label}}}"
        return m.group(0)

    text = re.sub(r"(Слик[аеуои]|Сликом)\s+(\d+)(?!\.\d)", repl_fig_bare, text)

    def repl_tab(m: re.Match) -> str:
        if in_protected(m.start()):
            return m.group(0)
        prefix = m.group(1)
        num = m.group(2).rstrip(".")
        if num not in tab_map:
            return m.group(0)
        label = f"tab:{chapter}-{tab_map[num]}"
        return f"{prefix}~\\ref{{{label}}}"

    text = re.sub(r"(Табел[аеуои]|Табелом)\s+(\d+\.\d+)\.?", repl_tab, text)

    def repl_tab_bare(m: re.Match) -> str:
        if in_protected(m.start()):
            return m.group(0)
        prefix = m.group(1)
        try:
            num = int(m.group(2))
        except ValueError:
            return m.group(0)
        if 1 <= num <= len(tables):
            return f"{prefix}~\\ref{{tab:{chapter}-{num}}}"
        return m.group(0)

    text = re.sub(r"(Табел[аеуои]|Табелом)\s+(\d+)(?!\.\d)", repl_tab_bare, text)
    return text


def normalize_resizebox_to_adjustbox(text: str) -> str:
    """`\\resizebox{\\textwidth}{!}{...}` → `\\begin{adjustbox}{max width=\\textwidth}...\\end{adjustbox}`.

    Овако се мале табеле не растежу — само превелике се смањују.
    """
    pat = re.compile(r"\\resizebox\{\\textwidth\}\{!\}\{%?\s*\n?", re.DOTALL)
    text = pat.sub(lambda _m: "\\begin{adjustbox}{max width=\\textwidth}\n", text)
    text = re.sub(r"\\end\{tabular\}\s*\n\s*\}", lambda _m: "\\end{tabular}\n\\end{adjustbox}", text)
    text = re.sub(r"\\end\{tabular\*\}\s*\n\s*\}", lambda _m: "\\end{tabular*}\n\\end{adjustbox}", text)
    return text


def process_file(path: Path, chapter: str) -> dict:
    src = path.read_text(encoding="utf-8")
    src = normalize_resizebox_to_adjustbox(src)
    src, figs = process_figures(src, chapter)
    src, tabs = process_tables(src, chapter)
    src = replace_references(src, figs, tabs, chapter)
    path.write_text(src, encoding="utf-8")
    return {"figures": len(figs), "tables": len(tabs)}


def main():
    if len(sys.argv) != 3:
        print("Usage: fix_figures.py <tex_path> <chapter_id>", file=sys.stderr)
        sys.exit(1)
    info = process_file(Path(sys.argv[1]), sys.argv[2])
    print(f"{sys.argv[1]}: figures={info['figures']}, tables={info['tables']}")


if __name__ == "__main__":
    main()
