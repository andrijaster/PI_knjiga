# Пословна интелигенција — Уџбеник (LaTeX)

Структура књиге у LaTeX-у, коначни облик за штампу.

## Структура

```
knjiga/
├── main.tex                 ← главни фајл (B5, book class, XeLaTeX)
├── references.bib           ← BibTeX база
├── poglavlja/
│   ├── 01-uvod.tex          ← Увод у Пословну интелигенцију
│   ├── 02-skladista.tex     ← Системи извештавања и Складишта података
│   ├── 03-ozp.tex           ← Откривање законитости у подацима
│   └── 04-automatizacija.tex← Аутоматизација одлучивања
├── slike/
│   ├── 01/                  ← слике поглавља 1
│   ├── 02/                  ← слике поглавља 2
│   ├── 03/                  ← (празно — ОЗП.docx нема уграђене слике)
│   └── 04/                  ← слике поглавља 4
└── scripts/
    ├── docx2tex.py          ← конвертер .docx → .tex
    ├── cyrillize.py         ← транслитератор латиница → ћирилица
    ├── postprocess.py       ← скида docx стилизацију
    └── keep_latin.txt       ← листа имена која остају на латиници
```

## Инсталација алата (потребно једном)

Овај пројекат користи **XeLaTeX** (због ћирилице и OpenType фонтова).

```bash
sudo apt install -y texlive-xetex texlive-lang-european \
    texlive-fonts-recommended texlive-latex-extra \
    texlive-bibtex-extra biber fonts-paratype
```

## Компајлирање

```bash
cd knjiga
xelatex main.tex
biber main
xelatex main.tex
xelatex main.tex
```

Финални PDF: `main.pdf`.

## Селективна компилација (за брже итерације на једном поглављу)

У `main.tex` пре `\begin{document}` додати:

```latex
\includeonly{poglavlja/03-ozp}
```

## Регенерисање из извора

Када се измене изворни .docx фајлови:

```bash
# Поглавље 1
python3 scripts/docx2tex.py "../Увод у пословну интелигенцију.docx" \
    01 slike/01 poglavlja/01-uvod.tex "Увод у Пословну интелигенцију"
python3 scripts/postprocess.py poglavlja/01-uvod.tex

# Поглавље 2
python3 scripts/docx2tex.py \
    "../Складишта података/Visualization and Data Warehousing.sr.docx" \
    02 slike/02 poglavlja/02-skladista.tex "Системи извештавања и Складишта података"
cp -n "../Складишта података/slike/"* slike/02/
python3 scripts/postprocess.py poglavlja/02-skladista.tex

# Поглавље 3
python3 scripts/docx2tex.py "../ОЗП.docx" \
    03 slike/03 poglavlja/03-ozp.tex "Откривање законитости у подацима"
python3 scripts/postprocess.py poglavlja/03-ozp.tex

# Поглавље 4 (из латиничне LaTeX верзије)
# Извући тело из ../Predavanje_AI_automatizacija/main.tex и
# демотовати наслове за један ниво, затим:
python3 scripts/cyrillize.py poglavlja/04-automatizacija-latin.tex \
    poglavlja/04-automatizacija.tex scripts/keep_latin.txt
```

## Напомене

- **Цела књига је на ћирилици**, осим имена софтвера, акронима и техничких
  термина (n8n, LLM, RAG, OLAP, JSON, API, ...) — листа је у
  `scripts/keep_latin.txt`.
- Слике су преузете из извора како јесу — могу се касније заменити квалитетнијим
  верзијама без измена у .tex фајловима (само заменити фајл у `slike/XX/` или
  по потреби исправити име у `\includegraphics{...}`).
- BibTeX база `references.bib` је преузета у целости из претходне верзије.
