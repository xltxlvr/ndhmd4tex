# ndhmd4tex

A **Markdown → LaTeX converter** built with Korean typesetting in mind, plus a few companion tools.
You write in an extended Markdown called the "ndhmd dialect" (ndhmarkdown dialect);
`ndhmd4tex.py` turns it into `.tex` and, if you ask, compiles it and opens the PDF.

The default header assumes oblivoir (memoir-based) + kotex, but `class:` and `preamble:`
in the front matter let you change that freely.

## What's in the box

| File | Role |
|---|---|
| `ndhmd4tex.py` | The converter: Markdown (ndhmd dialect) → LaTeX, compiling, checking (`--lint`) |
| `ndhmd2html.py` | Companion converter: the same manuscripts → HTML/XHTML (a first step toward EPUB). Needs `ndhmd4tex.py` beside it |
| `ndhmd-default.nmd` | Default header applied to manuscripts that have no front matter |
| `ndhmdsync.py`, `ndhmdsync.ini.example` | Two-way navigation between the PDF and the source `.md` (via SyncTeX) |
| `sample_mapping.yaml` | Example `mapping:` settings for changing which LaTeX commands markup turns into |
| `ndhmd4tex_quickstart.md` | From installation to your first PDF |
| `ndhmd4tex_dialect_guide.md` / `_en.md` | Syntax reference (Korean / English) |
| `ndhmd4tex_cheatsheet.tex`, `.pdf` | One-page syntax summary |
| `CHANGELOG.md` | Change history |

## Requirements

- Python 3 and PyYAML (`pip install pyyaml`)
- To produce a PDF: TeX Live or MiKTeX. The default header needs oblivoir and kotex;
  for Korean, xelatex or lualatex (`--pdfxe`, `--pdflua`) is recommended.
  The compile wrapper `ksruncltex` is available from its
  [home page](https://nonametex.imweb.me/?bmode=view&idx=170827898&t=board);
  to compile with standard tools instead, use `--latexmk`.
- Optional: `pandoc` (`--pandoc`), `multimarkdown` (`--mmd`), and `-shell-escape` if you use `minted`

## Quick start

```
python3 ndhmd4tex.py manuscript.md              # write manuscript.tex
python3 ndhmd4tex.py manuscript.md --pdfxe      # compile with xelatex and open the PDF
python3 ndhmd4tex.py manuscript.md --lint       # check for common markup mistakes
```

A minimal manuscript:

````markdown
---
title: My First Document
author: Jane Doe
---

# Getting started

**Bold**, *italic*, `code`, and a footnote.[^1]

[^1]: Footnotes are written like this.
````

With no front matter, `ndhmd-default.nmd` is used as the base.
`python3 ndhmd4tex.py --init-setup` copies that file into the current folder so you can edit it.

## Main features

- **Korean-friendly syntax**: the `||` join marker for paragraphs that start with a particle, Korean quotation marks and ellipsis handling, and more
- **Tables**: PHP Markdown Extra pipe tables and pandoc grid tables (row/column spans, multi-line cells, header and footer rows).
  Long columns wrap automatically via `tablewrap`
- **Footnote kinds**: choose among `\footnote`, `\sidefootnote`, `\pagenote`, `\verbfootnote` and others with tags
- **`showexam`**: a documentation block that shows source and converted result side by side, or stacked (`layout=stack`)
- **Mapping rules**: change what each piece of markup becomes in LaTeX through YAML (`mapping:`, `mappingrule:`, `--config`)
- **Splitting documents**: `{{file}}` transclusion, and `setup:` so several documents share one header
- **External tools**: an `external` block runs a tool registered in the mapping (lilypond, graphviz, a script…) and brings its output in as a figure or text; opt-in with `--external`, cached in `_external/`
- **Outsourcing modes**: `--pandoc` and `--mmd` hand only the body conversion to pandoc or MultiMarkdown, while the header and preamble stay with this tool
- **PDF navigation**: `--syncinfo` writes a `.nmdsync` file, and `ndhmdsync.py` searches backwards from the PDF to the line in the source `.md`

## Documentation

New here? Start with `ndhmd4tex_quickstart.md`. The full syntax is in `ndhmd4tex_dialect_guide.md`
(English: `_en.md`), and the cheatsheet gives the overview at a glance.
The guide can also be opened with `python3 ndhmd4tex.py --guide`.
All options are listed by `python3 ndhmd4tex.py --help`.

## License

MIT. See [LICENSE](LICENSE).
