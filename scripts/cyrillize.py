#!/usr/bin/env python3
r"""Транслитератор латиница - ћирилица за српски LaTeX текст.

Чува:
- садржај lstlisting, verbatim, Verbatim окружења
- LaTeX команде (опц. аргументи [..], обавезни {..} за \cite/\ref/
  \label/\url/\href/\lstinline/\texttt/\includegraphics)
- математичке моде $...$ и \(...\)/\[...\]
- ASCII речи које се подударају са заштићеним именима (из keep_latin.txt)

Уоптеба:
    cyrillize.py <input.tex> <output.tex> <keep_latin.txt>
"""
from __future__ import annotations
import sys
import re
from pathlib import Path

# Транслитерациона табела — дигрaфи прво
DIGRAPHS = [
    ("DŽ", "Џ"), ("Dž", "Џ"), ("dž", "џ"),
    ("LJ", "Љ"), ("Lj", "Љ"), ("lj", "љ"),
    ("NJ", "Њ"), ("Nj", "Њ"), ("nj", "њ"),
]
LETTERS = {
    "A": "А", "B": "Б", "C": "Ц", "Č": "Ч", "Ć": "Ћ",
    "D": "Д", "Đ": "Ђ", "E": "Е", "F": "Ф", "G": "Г",
    "H": "Х", "I": "И", "J": "Ј", "K": "К", "L": "Л",
    "M": "М", "N": "Н", "O": "О", "P": "П", "R": "Р",
    "S": "С", "Š": "Ш", "T": "Т", "U": "У", "V": "В",
    "Z": "З", "Ž": "Ж",
    "a": "а", "b": "б", "c": "ц", "č": "ч", "ć": "ћ",
    "d": "д", "đ": "ђ", "e": "е", "f": "ф", "g": "г",
    "h": "х", "i": "и", "j": "ј", "k": "к", "l": "л",
    "m": "м", "n": "н", "o": "о", "p": "п", "r": "р",
    "s": "с", "š": "ш", "t": "т", "u": "у", "v": "в",
    "z": "з", "ž": "ж",
    # ретки страни знаци
    "Q": "К", "q": "к",
    "W": "В", "w": "в",
    "X": "Х", "x": "х",
    "Y": "И", "y": "и",
}

# Знаци који чине „реч" — латинична слова + цифре + дефис/апостроф у речи
WORD_RE = re.compile(r"[A-Za-zÀ-žĀ-ſ0-9][A-Za-zÀ-žĀ-ſ0-9'\-_./]*")


def transliterate_word(w: str) -> str:
    """Транслитерује једну латиничну реч у ћирилицу."""
    # прво дигрaфи
    out = w
    # Стратегија: процеси карактер по карактер и тражи дигрaф унапред
    result = []
    i = 0
    while i < len(out):
        # покушај 2-знакни дигрaф
        two = out[i:i+2]
        digraph_hit = False
        for src, dst in DIGRAPHS:
            if two == src:
                result.append(dst)
                i += 2
                digraph_hit = True
                break
        if digraph_hit:
            continue
        ch = out[i]
        result.append(LETTERS.get(ch, ch))
        i += 1
    return "".join(result)


def load_keep_set(path: str) -> set[str]:
    keep: set[str] = set()
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        keep.add(s)
    return keep


def has_latin(text: str) -> bool:
    return bool(re.search(r"[A-Za-zÀ-žĀ-ſ]", text))


# Шаблони регија које треба прескочити (садржај задржати на латиници)
# Списак (re, group_index_of_content). Користимо један комбиновани regex с
# заменом ради лакоће.

# Идентификујемо blокове који се замењују placeholder-има пре обраде, и
# враћају после.
SKIP_PATTERNS = [
    # ЦЕЛА библиографија (укључује \bibitem кључеве и енглеске наводе)
    (re.compile(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", re.DOTALL), 0),
    # окружења verbatim/lstlisting (цео блок остаје нетакнут)
    (re.compile(r"\\begin\{(lstlisting|verbatim|Verbatim|minted|alltt|bibtex)\}.*?\\end\{\1\}", re.DOTALL), 0),
    # display math
    (re.compile(r"\\\[.*?\\\]", re.DOTALL), 0),
    # inline math \( ... \)
    (re.compile(r"\\\(.*?\\\)", re.DOTALL), 0),
    # inline math $..$
    (re.compile(r"(?<!\\)\$[^\$]*\$"), 0),
    # коментари
    (re.compile(r"(?<!\\)%[^\n]*"), 0),
    # \begin{tabular}{|p{5cm}|c|...} — argspec мора да остане у латиници
    # (allow ONE level of nested {...} since p{5cm} нести)
    (re.compile(r"\\begin\{tabular\*?\}\s*(?:\[[^\]]*\])?\s*\{(?:[^{}]|\{[^{}]*\})*\}"), 0),
    (re.compile(r"\\begin\{tabularx\}\s*\{(?:[^{}]|\{[^{}]*\})*\}\s*\{(?:[^{}]|\{[^{}]*\})*\}"), 0),
    (re.compile(r"\\begin\{array\}\s*(?:\[[^\]]*\])?\s*\{(?:[^{}]|\{[^{}]*\})*\}"), 0),
    # \addcontentsline{toc}{chapter}{text} — прва два аргумента су LaTeX токени
    (re.compile(r"\\addcontentsline\s*\{[^{}]*\}\s*\{[^{}]*\}"), 0),
    # \bibitem{key} — кључ остаје на латиници
    (re.compile(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}"), 0),
    # \cite, \ref, \label итд. — фуункција + аргументи
    (re.compile(r"\\(?:cite|citep|citet|cref|ref|label|url|href|lstinline|texttt|includegraphics|input|include|bibliography|addbibresource|usepackage|documentclass|graphicspath|hypersetup|definecolor|color|lstset|geometry|setmainfont|setsansfont|setmonofont|RequirePackage|providecommand|newcommand|renewcommand|DeclareMathOperator|pagestyle|thispagestyle|setlength|setcounter)\b(?:\s*\[[^\]]*\])*\s*\{[^{}]*\}(?:\s*\{[^{}]*\})*"), 0),
    # \begin{env}[options] — име окружења + опц. аргументи остају на латиници
    (re.compile(r"\\begin\{[A-Za-z*]+\}\s*(?:\[[^\]]*\])?"), 0),
    # \end{env}
    (re.compile(r"\\end\{[A-Za-z*]+\}"), 0),
    # \command[options] (нпр. \includegraphics[width=...] је већ горе, ово за остатак)
    (re.compile(r"\\[A-Za-z@]+\*?\s*\[[^\]]*\]"), 0),
    # Голи \command (\textbf, \emph, \chapter…) — само име, без {} аргумента
    (re.compile(r"\\[A-Za-z@]+\*?"), 0),
    # Дужинске јединице после цифара/тачки (5cm, 0.5em, 12pt итд.) — остају на латиници
    (re.compile(r"(?<![A-Za-zА-Яа-я])(?:\d+(?:\.\d+)?)(?:cm|mm|pt|in|em|ex|pc|bp|dd|cc|sp|px|mu)\b"), 0),
]


# Српска латиница: знакови који указују да је текст СРПСКИ а не ENGLESKI
SERBIAN_LATIN_HINT = re.compile(r"[čćšžđČĆŠŽĐ]|\b(?:lj|nj|dž|Lj|Nj|Dž)\b")


def is_english_text(s: str) -> bool:
    """Хеуристика: садржај `\\textit{...}` је енглески ако нема српских дијакритика
    и нема дугачких прохибиханих кластера (lj/nj/dž) и ако је > половине ASCII слова."""
    if SERBIAN_LATIN_HINT.search(s):
        return False
    # Ако је кратко (нпр. "engl."), задржи на латиници ради сигурности
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    ascii_letters = sum(1 for c in letters if 'A' <= c <= 'Z' or 'a' <= c <= 'z')
    return ascii_letters / len(letters) > 0.8


# Шаблон за \textit{X} и \emph{X} — обрада засебно
TEXTIT_RE = re.compile(r"\\(textit|emph)\{([^{}]+)\}")


def protect_regions(text: str) -> tuple[str, list[str]]:
    """Замени осетљиве регије placeholder-има, врати измењен текст + листу."""
    placeholders: list[str] = []

    def store(m: re.Match) -> str:
        placeholders.append(m.group(0))
        return f"\x01\x02{len(placeholders)-1}\x03"

    out = text

    # Прво: заштити \textit{...} ако је садржај претежно енглески
    def protect_engl_textit(m: re.Match) -> str:
        cmd, inner = m.group(1), m.group(2)
        if is_english_text(inner):
            placeholders.append(m.group(0))
            return f"\x01\x02{len(placeholders)-1}\x03"
        return m.group(0)
    out = TEXTIT_RE.sub(protect_engl_textit, out)

    for pat, _ in SKIP_PATTERNS:
        out = pat.sub(store, out)
    return out, placeholders


def restore_regions(text: str, placeholders: list[str]) -> str:
    """Враћа placeholder-е, рекурзивно — јер protect-фазе могу да угнезде један у други
    (нпр. \\textit{...} унутар thebibliography блока)."""
    pat = re.compile(r"\x01\x02(\d+)\x03")
    for _ in range(20):  # ограничен број рунда
        new_text = pat.sub(lambda m: placeholders[int(m.group(1))], text)
        if new_text == text:
            return text
        text = new_text
    return text


def cyrillize_text(text: str, keep: set[str]) -> str:
    """Транслитерује „обичан текст" — речи које нису у keep, изван заштићених региона."""

    def word_repl(m: re.Match) -> str:
        w = m.group(0)
        if w in keep:
            return w
        if not has_latin(w):
            return w
        if re.match(r"^https?://", w):
            return w
        # Деклинација типа "n8n-а", "LLM-ови" — задржи stem на латиници,
        # транслитеруј само суфикс после "-"
        if '-' in w:
            stem, sep, suffix = w.partition('-')
            if stem in keep and suffix and re.fullmatch(r"[A-Za-zÀ-žĀ-ſ]+", suffix):
                return stem + sep + transliterate_word(suffix)
        return transliterate_word(w)

    return WORD_RE.sub(word_repl, text)


def cyrillize(text: str, keep: set[str]) -> str:
    protected, placeholders = protect_regions(text)
    converted = cyrillize_text(protected, keep)
    return restore_regions(converted, placeholders)


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: cyrillize.py <input.tex> <output.tex> <keep_latin.txt>", file=sys.stderr)
        sys.exit(1)
    inp, out, keep_file = sys.argv[1:4]
    src = Path(inp).read_text(encoding="utf-8")
    keep = load_keep_set(keep_file)
    result = cyrillize(src, keep)
    Path(out).write_text(result, encoding="utf-8")
    print(f"Wrote {out} ({len(result)} bytes)")


if __name__ == "__main__":
    main()
