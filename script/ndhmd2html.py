#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ndhmd2html.py — ndhmd 방언 Markdown 을 HTML 로 바꾼다.

ndhmd4tex.py 가 PDF(LaTeX) 출판용이라면 이 도구는 EPUB 으로 가는 길목인 HTML
출력용이다. ndhmd4tex.py(없으면 확장자 없는 텍스트 스크립트 ndhmd4tex)와 같은 폴더에 두고 쓴다. 방언 해석(front matter,
setup 체인, {{포함}}, 주석, 블록 분할, 표 해석, 각종 정규식)은 ndhmd4tex 의
함수를 그대로 불러 쓰므로 두 도구가 원고를 다르게 읽을 일이 없다. 새로 쓴 것은
"무엇을 내보내는가" 뿐이다.

원칙
----
1. 조판 전용 마크업은 무시한다. 리스트의 `{!...}` 옵션, 그림의 place/align/
   wrapspec, 표의 env/rowhead, 환경의 raw= 속성, `\vspace` `\newpage` 같은
   조판 명령이 여기에 든다. `||` 는 두 평문단을 한 `<p>` 로 잇는 데만 쓰고
   (그것이 원고의 뜻이므로) 그 밖의 자리에서는 무시한다.
2. `:::{환경}` 은 표준 HTML 로 옮길 수 있는 것(quote, quotation, center, table,
   figure, verse, hverse, thebibliography)만 옮기고, 나머지는
   `<div class="환경이름">` 으로 감싸 식별만 가능하게 한다. 속성은
   `data-키="값"` 으로 남긴다. 꾸미는 일은 CSS 의 몫이다.
3. raw LaTeX(```tex 펜스, {{tex:파일}}, tabular/tblr 환경, `lines: raw` 환경)은
   HTML 로 옮길 수 없으므로 생략하고 개수를 알린다. `--keep-raw` 를 주면
   `<pre class="rawtex">` 로 남긴다. 수식은 LaTeX 원문 그대로 내보내 MathJax 가
   읽게 한다.
4. 출력은 언제나 XML 로도 올바른(well-formed) 마크업이다. 빈 요소는 `<br />`
   처럼 닫고 개체는 `&amp; &lt; &gt; &quot; &#160;` 만 쓴다. id 는 XML 이름
   규칙에 맞게 고친다(`fig:one` -> `fig-one`). EPUB 의 XHTML 로 그대로 가져갈 수
   있게 하기 위해서다.

그 밖에 정한 것
--------------
- 헤딩 번호는 기본으로 매긴다(`<span class="secnum">`). `[#라벨]` 이 PDF 에서처럼
  번호로 보이려면 번호가 있어야 하기 때문이다. `--no-number-sections` 를 주면
  번호를 빼고 `[#라벨]` 은 그 절의 제목을 보인다. 그림·표 번호는 캡션이 있는
  것에만 매긴다. 수식 번호와 `[E:라벨]` 은 MathJax 가 맡는다.
- 헤딩의 id 는 `{#라벨}` 이 있으면 그것, 없으면 제목에서 만든다(`첫-장`).
- 각주는 종류에 상관없이 문서 끝 `section.footnotes` 에 모으고 번호는 나타난
  순서대로 매긴다. `{sym}` 은 기호(* † ‡ …)를, `{opt=3}` 은 그 번호를 쓴다.
- 한국어 조사 매크로(`\은 \는 \이 \가 \을 \를 \와 \과 \으로 \로`, `\이라{}`)는
  바로 앞 글자(참조가 번호로 바뀐 뒤의 글자)의 받침을 보고 고른다.
- `"따옴표"` 는 유니코드 따옴표로, `---` `--` 는 — –, `...` 는 …, `~` 는 줄바꿈
  없는 공백으로 바꾼다. mapping 의 `quotes` `tilde` `wavedash` `linecomment`
  `description_syntax` `refcite` `notes` `extra_inline` 은 그대로 따른다.
- 히브리·아랍·시리아 문자 구간은 `<span class="rtl" lang="he" dir="rtl">` 로 감싼다.
  무엇을 구간으로 볼지는 front matter 의 `RTLtypeset` (detect: auto | markup)을
  ndhmd4tex 과 똑같이 따른다. `RTLtypeset: none` 이면 감싸지 않는다.
  `:::{hebrew}` 같은 RTL 블록은 `<div class="hebrew rtl" lang="he" dir="rtl">`, RTL 글자만
  있는 독립 문단은 `<p lang="he" dir="rtl">` 가 되고 그 안의 구간은 다시 감싸지 않는다.
- ```` ```external ```` 블록은 ndhmd4tex 과 같은 규칙·같은 캐시(`_external/`)로 처리한다.
  실행에는 `--external` 이 필요하고 결과가 캐시에 있으면 없어도 된다. 그림 결과가
  PDF 면 같은 이름의 PNG 를 옆에 만들어 그것을 쓴다(도구 정의의 `web` 명령, 없으면
  PySide6 의 QtPdf · pdftocairo · pdftoppm · gs 순). `result: tex` 는 raw LaTeX 이므로
  생략된다.
- front matter 의 `bibliography:` 가 있으면 문헌 목록을 **`.bbl` 에서** 만든다. LaTeX 과
  biber/bibtex 을 먼저 돌려 `<입력이름>.bbl` 이 있어야 한다(`--bbl FILE` 로 바꿀 수 있다).
  없으면 목록 자리에 "[LaTeX과 biber/bibtex을 먼저 실행하여야 문헌 목록이 생성됩니다.]" 를
  넣고 경고한다. bibtex 형식 `.bbl` 은 thebibliography 그 자체라 바로 읽는다. biber 형식은
  biblatex 내부 형식이라 못 읽으므로 `bbl2bibitem.lua` 가 만든 `<이름>-thebib.tex` 를 읽고,
  없으면 `--bibharvest` 로 만든다(texlua, lualatex, 이전 빌드의 `.tex` 필요; 스크립트는 이
  도구 옆·작업 폴더·공유 리소스 폴더에서 찾는다). 목록은 문서 끝에 놓이고 `\printbibliography`
  나 `\bibliography{…}` 를 쓴 자리에 놓을 수도 있다. 본문에 thebibliography 환경이 있으면 그것을
  쓴다. 항목 라벨이 natbib 꼴 `Short(Year)` 면 저자-연도, 아니면 번호이며, 인용 `[@키]` 는 목록의
  항목으로 링크된다(`\citet` -> 저자 (연도), `\citep`/`\cite` -> (저자, 연도), 번호 방식 -> [1]).
  `.bib` 가 `.bbl` 보다 새로우면 경고한다.
- 본문에 직접 쓴 `<`, `>`, `&` 는 글자로 나간다. HTML 을 그대로 넣으려면
  `` `<br />`{=html} `` 처럼 쓴다(ndhmd4tex 은 이 스팬을 버린다).
- 모르는 LaTeX 매크로 `\이름{인자}` 는 `<span class="tex-이름">인자</span>` 가 된다.
  mapping 에 HTML 전용 규칙을 둘 수 있다(ndhmd4tex 은 이 키를 무시한다).

      html:
        macros:
          keys: "<kbd>%(1)s</kbd>"          # \keys{Ctrl}
        environments:
          note: aside                        # :::{note} -> <aside class="note">
          tip: {tag: aside, class: "admonition tip"}

딸림 스타일시트
--------------
변환할 때마다 출력 파일 옆에 `<출력이름>_simple.css` 를 두고 HTML 에서 연결한다.
꾸밈을 최소로 한 출발점이고, 이 도구가 내는 class 가 모두 적혀 있으며 문서에만
나오는 class(환경 이름, `tex-매크로`, extra_inline 규칙 이름)는 빈 규칙으로
들어간다. **이미 있는 파일은 덮어쓰지 않는다** — 손본 것을 지키기 위해서다.
문서에 새 class 가 생기면 그것만 파일 끝에 빈 규칙으로 덧붙인다. 처음부터 다시
받으려면 파일을 지우고 변환한다. `--no-simple-css` 로 끌 수 있고, `--css` 로 준
스타일시트는 이 파일 뒤에 연결되어 이것을 덮어쓴다.

내보내는 class (CSS 를 쓸 때의 손잡이)
------------------------------------
  header.title-block  h1.title  p.subtitle  p.author  p.date
  nav.toc             span.secnum           h?.unnumbered
  figure.figure(.wrap)  figure.table  img.inline  span.caption-label
  div.math.display    span.math.inline
  pre > code.language-이름               pre.rawtex
  div.showexam(.showexam-side|.showexam-stack) > pre.showexam-src + div.showexam-result
  blockquote.quote / blockquote.quotation
  div.verse > p.stanza                   div.center
  section.bibliography > p.bibitem > span.bib-label     span.citation
  section.frame > h2.frametitle, p.framesubtitle
  div.환경이름 (그 밖의 모든 :::{환경})
  hr.asterism                            li > span.item-label
  sup.fnref > a   section.footnotes > div.footnote.fn-종류 > sup.fn-mark, a.fn-back
  span.sidenote.note-종류 (sidepar, sidebar)
  a.ref.ref-종류      span.label         span.index[data-index]   span.rtl
  em.dotemph   span.smallcaps   span.texlogo   span.tex-매크로이름
"""

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def _is_text_script(path):
    """확장자 없는 ndhmd4tex 가 실행 파일(바이너리)이 아니라 텍스트 스크립트인지."""
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return False
    if not head or b"\0" in head:
        return False
    if head[:2] == b"MZ" or head[:4] == b"\x7fELF" or head[:4] in (
            b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe",
            b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
        return False
    import codecs
    try:
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)
    except UnicodeDecodeError:
        return False
    return True


def _load_extensionless(dirs):
    """ndhmd4tex.py 가 없을 때, 옆의 확장자 없는 스크립트 `ndhmd4tex` 를 모듈로 읽는다.
    바이너리(실행 파일)는 읽지 않는다. 성공하면 모듈, 아니면 None."""
    import importlib.machinery
    import importlib.util
    for d in dirs:
        cand = Path(d) / "ndhmd4tex"
        if not (cand.is_file() and _is_text_script(cand)):
            continue
        loader = importlib.machinery.SourceFileLoader("ndhmd4tex", str(cand))
        spec = importlib.util.spec_from_loader("ndhmd4tex", loader)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["ndhmd4tex"] = mod
        try:
            loader.exec_module(mod)
        except Exception:
            sys.modules.pop("ndhmd4tex", None)
            continue
        return mod
    return None


try:
    import ndhmd4tex as nd
except ImportError as _e:      # pragma: no cover
    nd = None
    _dirs = [_HERE]
    if getattr(sys, "frozen", False):
        _dirs.append(Path(sys.executable).resolve().parent)
    # ndhmd4tex.py 가 아예 없을 때만 확장자 없는 스크립트를 찾는다(있는데 가져오기가 실패한 것은 그 오류를 보인다)
    if not any((Path(d) / "ndhmd4tex.py").exists() for d in _dirs):
        nd = _load_extensionless(_dirs)
    if nd is None:
        print("오류: ndhmd4tex.py 를 찾을 수 없습니다. ndhmd2html.py 와 같은 폴더에 두십시오.\n"
              "  (확장자 없는 스크립트 `ndhmd4tex` 도 텍스트 파일이면 쓸 수 있습니다. 바이너리는 쓸 수 없습니다.)\n"
              f"  ({_e})", file=sys.stderr)
        sys.exit(1)

__version__ = "0.8.0"

_NEEDS = ("split_blocks", "resolve_includes", "parse_grid_table", "resolve_quotes", "quotes_cjk_only", "_scope_replace", "scope_cut_endinput", "apply_scope_markers", "_scope_is_marker",
          "_comment_spans", "_parse_note_tag", "JOIN_BR", "rtl_wrap", "rtl_only_script", "expand_external")
_missing = [n for n in _NEEDS if not hasattr(nd, n)]
if _missing:      # pragma: no cover
    print("오류: 옆에 있는 ndhmd4tex.py (%s) 가 너무 옛 판입니다. 0.22.0 이상이 필요합니다.\n"
          "  없는 것: %s" % (getattr(nd, "__version__", "?"), ", ".join(_missing)), file=sys.stderr)
    sys.exit(1)

# --------------------------------------------------------------------------
# 0. 내부 표지 문자 (사용자 영역, 원고에 나올 일이 없는 문자)
# --------------------------------------------------------------------------
BLK_O, BLK_C = "\uE020", "\uE021"                 # 문단 밖으로 꺼내야 할 블록 요소
TOK_O, TOK_C, TOK_S = "\uE030", "\uE031", "\uE032"  # 나중에 채울 것(참조·조사·목차)
BR = "\uE040"                                     # 강제 줄바꿈(줄 끝 공백 두 칸)

_BLK_RE = re.compile(BLK_O + r"(.*?)" + BLK_C, re.S)
_TOK_RE = re.compile(TOK_O + r"([^" + TOK_C + r"]*)" + TOK_C)
_TAG_RE = re.compile(r"<[^>]*>")
_MATHJAX_URL = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def esc_attr(s):
    return esc(s).replace('"', "&quot;")


def blk(html):
    """블록 요소임을 표시한다. 문단 안에 섞여 있으면 wrap_p 가 밖으로 꺼낸다."""
    return BLK_O + html + BLK_C if html else ""


def tok(*fields):
    return TOK_O + TOK_S.join(str(f) for f in fields) + TOK_C


def xid(label):
    """라벨을 XML 이름 규칙에 맞는 id 로. `fig:one` -> `fig-one`."""
    s = re.sub(r"[^\w.\-]", "-", str(label).strip())
    if not s or not (s[0].isalpha() or s[0] == "_"):
        s = "id-" + s
    return s


def plain(html):
    """HTML 조각에서 태그와 표지를 걷어낸 글자만(속성 값·<title> 용, 이스케이프 유지)."""
    html = _BLK_RE.sub(lambda m: m.group(1), html)

    def _t(m):
        f = m.group(1).split(TOK_S)
        return f[-1] if f[0] in ("ref", "cite", "josa") else ""
    html = _TOK_RE.sub(_t, html)
    html = re.sub(r'<sup class="fnref">.*?</sup>', "", html, flags=re.S)
    return re.sub(r"\s+", " ", _TAG_RE.sub("", html)).strip()


def attr_text(html):
    """HTML 조각을 속성 값으로(plain 은 이미 이스케이프돼 있으므로 따옴표만 바꾼다)."""
    return plain(html).replace('"', "&quot;")


def slug(html):
    """헤딩 제목에서 자동 id 를 만든다(pandoc 과 비슷하게: 글자·숫자만 남기고 공백은 -)."""
    import html as _h
    t = re.sub(r"[^\w\- ]", "", _h.unescape(plain(html))).strip().lower()
    t = re.sub(r"\s+", "-", t)
    return t or "section"


# --------------------------------------------------------------------------
# 1. 변환 상태
# --------------------------------------------------------------------------
_NAMES = {
    "ko": {"figure": "그림", "table": "표", "toc": "목차", "notes": "주", "bib": "참고 문헌"},
    "en": {"figure": "Figure", "table": "Table", "toc": "Contents", "notes": "Notes", "bib": "References"},
    "ja": {"figure": "図", "table": "表", "toc": "目次", "notes": "注", "bib": "参考文献"},
}
_FN_SYMBOLS = ["*", "†", "‡", "§", "¶", "‖", "**", "††", "‡‡"]


class Ctx:
    def __init__(self, cfg, meta, base_dir, opts):
        self.cfg, self.meta, self.base_dir, self.opts = cfg, meta, Path(base_dir), opts
        self.pr = nd.Protector()
        self.se_store = []
        self.lang = str(opts.lang or meta.get("lang") or "ko")
        names = dict(_NAMES.get(self.lang.split("-")[0].lower(), _NAMES["en"]))
        if meta.get("figurename"):
            names["figure"] = str(meta["figurename"])
        if meta.get("tablename"):
            names["table"] = str(meta["tablename"])
        self.names = names
        self.notes = []            # 각주: {kind, body, sym, symval, opt}
        self.fn_n = 0
        self.sym_n = 0
        self.labels = {}           # id -> {kind, num, title}
        self.used_ids = set()
        self.headings = []         # (level, id, html, num, unnumbered)
        self.sec = [0] * 7
        self.cur_sec = ("", "")    # (번호, 제목) — {#id} 가 가리킬 현재 절
        self.fig_n = self.tab_n = 0
        self.bib = {}              # 키 -> 표시 라벨
        self.has_bib = False
        self.math = False
        self.math_labels = set()   # 수식 안의 \label — 번호는 MathJax 가 매긴다
        self.raw_omitted = 0
        self.has_toc_tok = self.has_title_tok = False
        self.has_bib_tok = False   # \printbibliography / \bibliography 를 본문에 직접 썼는가
        self.bib_html = ""
        self._warned = set()
        hcfg = cfg.get("html") if isinstance(cfg.get("html"), dict) else {}
        self.user_macros = hcfg.get("macros") or {}
        self.user_envs = hcfg.get("environments") or {}
        self.literal = set(cfg.get("literal_macros", [])) | set(cfg.get("extra_macros", []))
        self.macro_re = nd.build_macro_re(cfg)
        self.refcite_re = nd.build_refcite_re(cfg)
        self.refcite_raw_re = nd.build_refcite_re(cfg, with_rawopt=True)
        gp = meta.get("graphicspath") or []
        self.graphicspath = [gp] if isinstance(gp, str) else list(gp)
        self.rtl = nd.resolve_rtl(meta)       # RTLtypeset: none 이면 None
        self.locals = []                      # 진행 중인 inline() 들의 Protector
        self.rtl_ambient = None               # RTL 블록 안이면 그 문자 이름

    def warn(self, msg):
        if msg not in self._warned:
            self._warned.add(msg)
            print("경고: " + msg, file=sys.stderr)

    def new_id(self, want, auto=False):
        base = xid(want)
        i, cand = 1, base
        while cand in self.used_ids:
            i += 1
            cand = f"{base}-{i}"
        if not auto and cand != base:
            self.warn(f"라벨 '{want}' 이(가) 중복됩니다. 두 번째부터는 id 를 '{cand}' 처럼 바꿉니다.")
        self.used_ids.add(cand)
        return cand

    def label(self, raw, kind, num="", title=""):
        """라벨을 등록하고 id 를 돌려준다."""
        i = self.new_id(raw)
        self.labels.setdefault(xid(raw), {"kind": kind, "num": num, "title": title, "id": i})
        return i

    def inl(self, text):
        return inline(text, self)

    def full(self, html):
        """바깥 inline() 들이 보호해 둔 조각까지 모두 되돌린다.

        각주 본문이나 그림 캡션처럼 '제자리에 돌려주지 않고 따로 보관하는' HTML 은
        바깥 호출이 끝날 때의 복원을 받지 못한다. 보관하기 전에 여기서 되돌려야
        코드 스팬·수식·RTL 구간이 자리표시자로 남지 않는다."""
        for loc in reversed(self.locals):
            html = loc.restore(html)
        return html


# --------------------------------------------------------------------------
# 2. 인라인
# --------------------------------------------------------------------------
def _protect_code(text, ctx, local):
    """코드 스팬. nd.protect_inline_code 와 같은 CommonMark 규칙이다."""
    out = []
    i, n = 0, len(text)
    run_re = nd._BACKTICK_RUN_RE
    while i < n:
        if text[i] == "\\" and i + 1 < n and text[i + 1] == "`":
            out.append(local.protect("`"))
            i += 2
            continue
        m = run_re.match(text, i)
        if not m:
            out.append(text[i])
            i += 1
            continue
        run_len = m.end() - m.start()
        j = m.end()
        cs = ce = None
        while j < n and text[j] != "\n":
            m2 = run_re.match(text, j)
            if m2:
                if (m2.end() - m2.start()) == run_len:
                    cs, ce = m2.start(), m2.end()
                    break
                j = m2.end()
            else:
                j += 1
        if cs is None:
            out.append(text[m.start():m.end()])
            i = m.end()
            continue
        content = text[m.end():cs]
        if len(content) >= 2 and content[0] == " " and content[-1] == " " and content.strip(" "):
            content = content[1:-1]
        raw_m = nd._RAW_ATTR_RE.match(text, ce)
        if raw_m:
            # `...`{=html} 은 그대로 내보내고, {=latex} 등 다른 형식은 버린다.
            if raw_m.group(1).lower() in ("html", "html5", "xhtml"):
                out.append(local.protect(content))
            i = raw_m.end()
            continue
        out.append(local.protect("<code>%s</code>" % esc(content)))
        i = ce
    return "".join(out)


def _split_macro(tokstr):
    """`\이름*[opt]{a}{b}` -> (이름, [opt...], [인자...]). 이름이 없으면 None."""
    m = re.match(r"\\([a-zA-Z\uAC00-\uD7A3\u1100-\u11FF]+)\*?", tokstr)
    if not m:
        return None, [], []
    rest, opts, args, i = tokstr[m.end():], [], [], 0
    while i < len(rest):
        if rest[i] == "[":
            j = rest.find("]", i)
            if j < 0:
                break
            opts.append(rest[i + 1:j])
            i = j + 1
        elif rest[i] == "{":
            depth, j = 0, i
            while j < len(rest):
                if rest[j] == "{":
                    depth += 1
                elif rest[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            args.append(rest[i + 1:j])
            i = j + 1
        else:
            break
    return m.group(1), opts, args


def _tag(tag, cls=None):
    attr = f' class="{cls}"' if cls else ""
    return lambda a, o, c: f"<{tag}{attr}>" + c.inl(a[0] if a else "") + f"</{tag}>"


def _text(s):
    return lambda a, o, c: s


def _pass(a, o, c):
    return c.inl(a[-1]) if a else ""


def _logo(a, o, c, name=""):
    return '<span class="texlogo">%s</span>' % name


_DROP = """hfill vfill noindent indent centering raggedright raggedleft newpage clearpage
cleardoublepage pagebreak nopagebreak bigskip medskip smallskip vspace hspace vskip hskip kern
phantom hphantom vphantom relax protect nolinebreak allowbreak sloppy fussy small footnotesize
scriptsize tiny large Large LARGE huge Huge normalsize bfseries itshape ttfamily sffamily
rmfamily mdseries upshape scshape normalfont selectfont thispagestyle pagestyle setlength
addtolength setcounter addtocounter frontmatter mainmatter backmatter appendix printindex
listoffigures listoftables bibliography bibliographystyle input include usepackage nocite
markboth markright addcontentsline phantomsection penalty break nobreak leavevmode strut null
index firmlist tightlist looselist color""".split()

_MACROS = {
    "textbf": _tag("strong"), "emph": _tag("em"), "textit": _tag("em"), "textsl": _tag("em"),
    "texttt": _tag("code"), "textsc": _tag("span", "smallcaps"),
    "underline": _tag("u"), "uline": _tag("u"), "sout": _tag("del"), "st": _tag("del"),
    "textsuperscript": _tag("sup"), "textsubscript": _tag("sub"),
    "dotemph": _tag("em", "dotemph"),
    "textsf": _tag("span", "sans"), "textrm": _pass, "textnormal": _pass, "mbox": _pass, "hbox": _pass,
    "text": _pass, "textup": _pass, "textmd": _pass,
    "ldots": _text("…"), "dots": _text("…"), "textellipsis": _text("…"),
    "textemdash": _text("—"), "textendash": _text("–"),
    "textbackslash": _text("\\"), "textasciitilde": _text("~"), "textasciicircum": _text("^"),
    "textbar": _text("|"), "textless": _text("&lt;"), "textgreater": _text("&gt;"),
    "S": _text("§"), "P": _text("¶"), "copyright": _text("©"), "textregistered": _text("®"),
    "texttrademark": _text("™"), "dag": _text("†"), "ddag": _text("‡"), "textbullet": _text("•"),
    "quad": _text("\u2003"), "qquad": _text("\u2003\u2003"), "enspace": _text("\u2002"),
    "thinspace": _text("\u2009"), "nobreakspace": _text("&#160;"),
    "and": _text(", "), "par": _text("<br />\n"), "newline": _text("<br />\n"),
    "linebreak": _text("<br />\n"),
    "today": lambda a, o, c: esc(_today(c.lang)),
    "url": lambda a, o, c: '<a href="%s">%s</a>' % (esc_attr(a[0]), esc(a[0])) if a else "",
    "href": lambda a, o, c: ('<a href="%s">%s</a>' % (esc_attr(a[0]), c.inl(a[1]))
                             if len(a) >= 2 else _pass(a, o, c)),
    "footnote": lambda a, o, c: _note(a[0] if a else "", None, c),
    "thanks": lambda a, o, c: _note(a[0] if a else "", None, c),
    "label": lambda a, o, c: _anchor(a[0], c) if a else "",
    "ref": lambda a, o, c: tok("ref", "ref", xid(a[0]), esc(a[0])) if a else "",
    "pageref": lambda a, o, c: tok("ref", "page", xid(a[0]), esc(a[0])) if a else "",
    "autoref": lambda a, o, c: tok("ref", "cref", xid(a[0]), esc(a[0])) if a else "",
    "cref": lambda a, o, c: tok("ref", "cref", xid(a[0]), esc(a[0])) if a else "",
    "Cref": lambda a, o, c: tok("ref", "cref", xid(a[0]), esc(a[0])) if a else "",
    "nameref": lambda a, o, c: tok("ref", "title", xid(a[0]), esc(a[0])) if a else "",
    "titleref": lambda a, o, c: tok("ref", "title", xid(a[0]), esc(a[0])) if a else "",
    "eqref": lambda a, o, c: _eqref(a[0], c) if a else "",
    "textcolor": lambda a, o, c: ('<span class="textcolor" style="color: %s;">%s</span>'
                                  % (esc_attr(a[0]), c.inl(a[1])) if len(a) >= 2 else _pass(a, o, c)),
    "colorbox": lambda a, o, c: ('<span class="colorbox" style="background-color: %s;">%s</span>'
                                 % (esc_attr(a[0]), c.inl(a[1])) if len(a) >= 2 else _pass(a, o, c)),
    "ruby": lambda a, o, c: ("<ruby>%s<rt>%s</rt></ruby>" % (c.inl(a[0]), c.inl(a[1]))
                             if len(a) >= 2 else _pass(a, o, c)),
    "tableofcontents": lambda a, o, c: _toc_tok(c),
    "maketitle": lambda a, o, c: _title_tok(c),
}
for _n in ("cite", "citet", "citep", "citeauthor", "citeyear", "parencite", "textcite"):
    _MACROS[_n] = (lambda a, o, c, v=_n: tok("cite", v, a[-1]) if a else "")
for _n, _s in (("LaTeX", "LaTeX"), ("TeX", "TeX"), ("XeTeX", "XeTeX"), ("LuaTeX", "LuaTeX"),
               ("XeLaTeX", "XeLaTeX"), ("LuaLaTeX", "LuaLaTeX"), ("pdfTeX", "pdfTeX"),
               ("pdfLaTeX", "pdfLaTeX"), ("BibTeX", "BibTeX"), ("ConTeXt", "ConTeXt"),
               ("KoTeX", "ko.TeX"), ("kotex", "ko.TeX"), ("LaTeXe", "LaTeX2ε")):
    _MACROS[_n] = (lambda a, o, c, s=_s: _logo(a, o, c, s))
for _n in _DROP:
    _MACROS[_n] = _text("")
# 문헌 목록 자리: \printbibliography, \bibliography{…} 를 쓴 곳에 목록을 놓는다.
for _n in ("printbibliography", "bibliography"):
    _MACROS[_n] = (lambda a, o, c: _bib_tok(c))

_PUNCT_MACROS = {"\\\\": "<br />\n", "\\,": "\u2009", "\\;": "\u2005", "\\%": "%",
                 "\\&": "&amp;", "\\#": "#", "\\_": "_", "\\{": "{", "\\}": "}"}
_HANGUL_NAME_RE = re.compile(r"[\uAC00-\uD7A3]+")


def _today(lang):
    d = datetime.date.today()
    if lang.startswith("ko"):
        return f"{d.year}년 {d.month}월 {d.day}일"
    return d.strftime("%B %d, %Y").replace(" 0", " ")


def _toc_tok(ctx):
    ctx.has_toc_tok = True
    return blk(tok("toc"))


def _bib_tok(ctx):
    ctx.has_bib_tok = True
    return blk(tok("bibliography"))


def _title_tok(ctx):
    ctx.has_title_tok = True
    return blk(tok("titleblock"))


def _eqref(label, ctx):
    ctx.math = True
    return '<span class="math inline">\\(\\eqref{%s}\\)</span>' % esc(label)


def _anchor(raw, ctx):
    num, title = ctx.cur_sec
    i = ctx.label(raw, "anchor", num, title)
    return '<span id="%s" class="label"></span>' % esc_attr(i)


def _macro(tokstr, ctx):
    if tokstr in _PUNCT_MACROS:
        return _PUNCT_MACROS[tokstr]
    if tokstr in ctx.literal:
        name = tokstr[1:]
        # 한국어 조사 매크로(\은 \는 \으로 ...)는 앞 글자를 보고 나중에 고른다.
        return tok("josa", name) if _HANGUL_NAME_RE.fullmatch(name) else ""
    name, opts, args = _split_macro(tokstr)
    if name is None:
        return ""
    user = ctx.user_macros.get(name)
    if user is not None:
        vals = {str(i + 1): ctx.inl(a) for i, a in enumerate(args)}
        vals["opt"] = esc(opts[0]) if opts else ""
        try:
            return str(user) % vals
        except (KeyError, TypeError, ValueError):
            ctx.warn(f"html.macros.{name} 템플릿이 인자 {len(args)}개와 맞지 않습니다.")
            return _pass(args, opts, ctx)
    fn = _MACROS.get(name)
    if fn is not None:
        return fn(args, opts, ctx)
    if _HANGUL_NAME_RE.fullmatch(name) and not any(a.strip() for a in args):
        return tok("josa", name)          # \이라{}고 같은 조사 활용형
    inner = ctx.inl(args[-1]) if args else ""
    return '<span class="tex-%s">%s</span>' % (esc_attr(name), inner)


def _len_css(v):
    """LaTeX 길이를 CSS 길이로. 옮길 수 없으면 None."""
    v = str(v or "").strip()
    m = re.fullmatch(r"([0-9]*\.?[0-9]+)?\s*\\(?:linewidth|textwidth|columnwidth|hsize|paperwidth)", v)
    if m:
        return "%g%%" % (float(m.group(1) or 1) * 100)
    m = re.fullmatch(r"([0-9]*\.?[0-9]+)\s*(cm|mm|in|pt|bp|em|ex|px|pc|%)", v)
    if m:
        return m.group(1) + ("pt" if m.group(2) == "bp" else m.group(2))
    return None


_WEB_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif")


def _img_src(path, ctx):
    """그림 경로를 HTML 이 쓸 수 있게 고른다. graphicspath 와 확장자 생략을 풀고,
    PDF/EPS 처럼 브라우저가 못 보이는 형식이면 같은 이름의 웹 형식을 찾는다."""
    if nd._URL_RE.match(path) or path.startswith("data:"):
        return path
    p = Path(path)
    dirs = [ctx.base_dir] + [ctx.base_dir / g for g in ctx.graphicspath]

    out_dir = getattr(ctx.opts, "out_dir", None) or ctx.base_dir

    def rel(target):
        # 출력 파일이 원고와 다른 폴더에 놓여도 그림을 찾을 수 있게 그 폴더 기준으로 적는다.
        try:
            return os.path.relpath(target, out_dir).replace(os.sep, "/")
        except ValueError:
            return str(target)

    def find(q):
        for d in dirs:
            if (d / q).is_file():
                return rel(d / q)
        return None
    if p.suffix.lower() in _WEB_EXT:
        return find(p) or (path if p.is_absolute() else rel(ctx.base_dir / p))
    for ext in _WEB_EXT:
        hit = find(p.with_suffix(ext) if p.suffix else Path(str(p) + ext))
        if hit:
            return hit
    if p.suffix:
        ctx.warn(f"그림 '{path}' 은(는) 브라우저가 표시하지 못하는 형식입니다. "
                 f"같은 이름의 PNG/SVG/JPG 를 옆에 두면 그것을 씁니다.")
    return find(p) or (path if p.is_absolute() else rel(ctx.base_dir / p))


def _unbrace(v):
    v = (v or "").strip()
    while v.startswith("{") and v.endswith("}"):
        v = v[1:-1].strip()
    return v


def _figure(caption_raw, path, attrs, ctx):
    attrs = dict(attrs)
    empty_quotes = caption_raw.strip() in {'""', "''", "\u201c\u201d", "\u2018\u2019"}
    has_caption = bool(caption_raw.strip()) and not empty_quotes
    attr_caption = attrs.pop("caption", None)
    cap_src = caption_raw if has_caption else (attr_caption or "")
    label = _unbrace(attrs.pop("label", None))
    wrap = "wrap" in attrs
    is_inline = "inline" in attrs
    href = _unbrace(attrs.pop("href", None))
    styles = []
    for key in ("width", "height"):
        css = _len_css(attrs.get(key))
        if css:
            styles.append(f"{key}: {css};")
    if is_inline and not styles:
        for part in (attrs.get("inlinespec") or "").split(","):
            k, _, v = part.partition("=")
            css = _len_css(v) if k.strip() in ("width", "height") else None
            if css:
                styles.append(f"{k.strip()}: {css};")
    cap_html = ctx.full(ctx.inl(cap_src)) if cap_src else ""
    img = '<img src="%s" alt="%s"' % (esc_attr(_img_src(path, ctx)), attr_text(cap_html))
    if styles:
        img += ' style="%s"' % " ".join(styles)
    as_block = (bool(cap_src) or empty_quotes or wrap) and not is_inline
    if is_inline:
        img += ' class="inline"'
    if label and not as_block:
        num, title = ctx.cur_sec
        img += ' id="%s"' % esc_attr(ctx.label(label, "anchor", num, title))
    img += " />"
    if href:
        img = '<a href="%s">%s</a>' % (esc_attr(href), img)
    if not as_block:
        return img
    cls = "figure wrap" if wrap else "figure"
    fid, cap = "", ""
    num = ""
    if cap_src:
        ctx.fig_n += 1
        num = str(ctx.fig_n)
        cap = ('\n<figcaption><span class="caption-label">%s %s.</span> %s</figcaption>'
               % (esc(ctx.names["figure"]), num, cap_html))
    if label:
        fid = ' id="%s"' % esc_attr(ctx.label(label, "figure", num, plain(cap_html)))
    return blk('<figure class="%s"%s>\n%s%s\n</figure>' % (cls, fid, img, cap))


def _link(label, url, ctx):
    if url.startswith("#"):
        target = xid(url[1:])
        if not label.strip():
            return tok("ref", "ref", target, esc(url[1:]))
        return '<a href="#%s">%s</a>' % (esc_attr(target), ctx.inl(label))
    if not label.strip():
        return '<a href="%s">%s</a>' % (esc_attr(url), esc(url))
    return '<a href="%s">%s</a>' % (esc_attr(url), ctx.inl(label))


def _note(text_, tag_raw, ctx):
    """각주. 종류 꼬리표({side} {page} {sym} {opt=3} ...)는 class 와 표지로만 남긴다."""
    spec = nd._parse_note_tag(tag_raw, ctx.cfg)
    leftover = ""
    if spec is None or spec == "bad":
        if tag_raw is not None:
            leftover = esc("{" + tag_raw + "}")
        spec = {"kind": "default", "sym": False, "symval": None, "opt": None}
    kind = spec["kind"]
    if isinstance(text_, nd.BlockNote):        # 여러 문단·환경을 담은 각주
        body = ctx.full(ctx.pr.restore(blocks(text_.split("\n"), ctx)).strip())
    else:
        body = ctx.full(ctx.inl(text_))
    if kind in ("sidepar", "sidebar"):
        return '<span class="sidenote note-%s" role="note">%s</span>%s' % (kind, body, leftover)
    ctx.notes.append({"kind": kind, "body": body, "sym": spec["sym"],
                      "symval": spec["symval"], "opt": (spec["opt"] or "").strip("[]")})
    return tok("fn", len(ctx.notes) - 1) + leftover


def _refkind(tmpl):
    t = str(tmpl)
    for pat, kind in ((r"\\pageref", "page"), (r"\\cite|\\parencite|\\textcite", "cite"),
                      (r"\\eqref", "eq"), (r"\\figurename", "fig"), (r"\\tablename", "tab"),
                      (r"\\titleref|\\nameref", "title"), (r"\\[Cc]ref|\\autoref", "cref"),
                      (r"\\ref", "ref")):
        if re.search(pat, t):
            return kind
    return "ref"


def _refcite(prefix, label, ctx):
    tmpl = ctx.cfg["refcite"].get(prefix)
    if tmpl is None:
        return None
    kind = _refkind(tmpl)
    label = label.strip()
    if kind == "cite":
        m = re.search(r"\\(\w+)", str(tmpl))
        return tok("cite", m.group(1) if m else "cite", label)
    if kind == "eq":
        return _eqref(label, ctx)
    return tok("ref", kind, xid(label), esc(label))


_LANG_CODE = {"hebrew": "he", "arabic": "ar", "syriac": "syr", "persian": "fa", "farsi": "fa",
              "urdu": "ur", "yiddish": "yi", "kurdish": "ku", "pashto": "ps", "sindhi": "sd",
              "uyghur": "ug"}

def _rtl_code(script, ctx):
    return _LANG_CODE.get(ctx.rtl["langs"][script], _LANG_CODE[script])


_INLINE_HTML = {
    "bold_italic": "<strong><em>%s</em></strong>", "bold": "<strong>%s</strong>",
    "italic": "<em>%s</em>", "strike": "<del>%s</del>",
    "emphdot": '<em class="dotemph">%s</em>',
    "sans": '<span class="sans">%s</span>',
    "sans_bold": '<strong class="sans">%s</strong>',
}


def _quotes(ctx):
    q = nd.resolve_quotes(ctx.cfg)
    if q is None:
        return ("\u201c", "\u201d", "\u2018", "\u2019")
    return (q[0], q[1], q[2] or "\u2018", q[3] or "\u2019")


def _wavedash(ctx):
    wd = nd.resolve_wavedash(ctx.cfg)
    return "~" if wd is None or wd.startswith("\\") else wd


def inline(text, ctx):
    local = nd.Protector()
    ctx.locals.append(local)
    try:
        return _inline(text, ctx, local)
    finally:
        ctx.locals.pop()


def _inline(text, ctx, local):
    cfg = ctx.cfg

    def P(html):
        return local.protect(html)

    text = text.replace(BR, P("<br />\n"))
    text = _protect_code(text, ctx, local)
    text = re.sub(r"\^\^M", lambda m: P("\n"), text)

    def do_math(m):
        ctx.math = True
        s = m.group(0)
        inner = s[1:-1] if s.startswith("$") else s[2:-2]
        return P('<span class="math inline">\\(%s\\)</span>' % esc(inner))
    text = nd.INLINE_MATH_RE.sub(do_math, text)
    text = nd._VERB_SPAN_RE.sub(lambda m: P("<code>%s</code>" % esc(m.group(2))), text)

    # 그림의 {속성} 은 매크로 단계보다 먼저 떼어 둔다. width=0.5\linewidth 의
    # \linewidth 가 매크로로 처리돼 사라지면 너비를 읽을 수 없다.
    raw_attrs = {}

    def _stash(m):
        if not m.group(3):
            return m.group(0)
        key = "\uE050%d\uE051" % len(raw_attrs)
        raw_attrs[key] = m.group(3)
        a, b = m.start(3) - m.start(0), m.end(3) - m.start(0)
        return m.group(0)[:a] + key + m.group(0)[b:]
    text = nd.FIGURE_RE.sub(_stash, text)
    text = nd.FIGURE_REF_RE.sub(_stash, text)

    text = ctx.macro_re.sub(lambda m: P(_macro(m.group(0), ctx)), text)
    if ctx.rtl:
        # RTL 구간. 브라우저가 방향을 알아서 처리하므로 언어와 방향만 표시한다.
        # RTL 블록 안에서는 이미 그 언어·방향이므로 감싸지 않는다.
        text = nd.rtl_wrap(text, ctx.rtl, lambda script, inner: P(
            esc(inner) if script == ctx.rtl_ambient else
            '<span class="rtl" lang="%s" dir="rtl">%s</span>' % (_rtl_code(script, ctx), esc(inner))))
    text = nd.INLINE_LABEL_RE.sub(lambda m: P(_anchor(m.group(1), ctx)), text)

    def do_figure_ref(m):
        defn = cfg.get("_refdefs", {}).get(m.group(2))
        if defn is None:
            ctx.warn(f"정의되지 않은 참조 [{m.group(2)}] 를 그림에 썼습니다.")
            return P(esc(m.group(0)))
        m2 = nd._REF_DEF_VALUE_RE.match(defn)
        attrs = nd.parse_figure_attrs(m2.group(2) or "")
        for k, v in nd.parse_figure_attrs(raw_attrs.get(m.group(3), m.group(3)) or "").items():
            if v == "" and k != "align":
                attrs.pop(k, None)
            else:
                attrs[k] = v
        return P(_figure(m.group(1), m2.group(1), attrs, ctx))

    def do_link_ref(m):
        defn = cfg.get("_refdefs", {}).get(m.group(2))
        if defn is None:
            ctx.warn(f"정의되지 않은 참조 [{m.group(2)}] 를 링크에 썼습니다.")
            return P(esc(m.group(0)))
        return P(_link(m.group(1), nd._REF_LINK_DEF_VALUE_RE.match(defn).group(1), ctx))

    def do_footnote(m):
        fid, tag = m.group(1), m.group(2)
        content = cfg.get("_footnotes", {}).get(fid)
        if content is not None:
            return P(_note(content, tag, ctx))
        if cfg.get("inline_footnote", True):
            return P(_note(fid, tag, ctx))
        ctx.warn(f"정의되지 않은 각주 [^{fid}] 를 참조했습니다.")
        return m.group(0)

    def do_refcite(m):
        out = _refcite(m.group(1), m.group(2), ctx)
        return m.group(0) if out is None else P(out)

    def do_index(m):
        shown, term = m.group(1) or "", m.group(2) or m.group(1) or ""
        return P('<span class="index" data-index="%s">%s</span>' % (esc_attr(term), esc(shown)))

    text = ctx.refcite_raw_re.sub(do_refcite, text)         # rawopt 는 조판 인자라 버린다
    text = nd.FIGURE_REF_RE.sub(do_figure_ref, text)
    text = nd.FIGURE_RE.sub(
        lambda m: P(_figure(m.group(1), m.group(2),
                            nd.parse_figure_attrs(raw_attrs.get(m.group(3), m.group(3))), ctx)), text)
    text = nd.LINK_REF_RE.sub(do_link_ref, text)
    text = nd.LINK_RE.sub(lambda m: P(_link(m.group(1), m.group(2), ctx)), text)
    text = nd.INLINE_FOOTNOTE_TAG_RE.sub(lambda m: P(_note(m.group(1), m.group(2), ctx)), text)
    text = nd.FOOTNOTE_REF_TAG_RE.sub(do_footnote, text)
    text = ctx.refcite_re.sub(do_refcite, text)
    text = nd.INDEX_RE.sub(do_index, text)
    # 대시는 링크·그림 뒤에 바꾼다(URL 안의 -- 를 건드리지 않게).
    text = re.sub(r"(?<!-)---(?!-)", lambda m: P("—"), text)
    text = re.sub(r"(?<!-)--(?!-)", lambda m: P("–"), text)

    text = nd.ESCAPED_QUOTE_RE.sub(lambda m: P(esc_attr(m.group(1)) if m.group(1) == '"' else "'"), text)
    text = nd.convert_smart_quotes(
        text, _quotes(ctx), lambda s: P(esc(s)),
        cjk_only=nd.quotes_cjk_only(ctx.cfg),
        fallback=("\u201c", "\u201d", "\u2018", "\u2019"))

    tmode = nd.resolve_tilde(cfg)
    wd = _wavedash(ctx)
    text = re.sub(r"\\~", lambda m: P(esc(wd)), text)
    if cfg.get("ellipsis"):
        text = re.sub(r"\.\.\.", lambda m: P("…"), text)

    for rule in list(cfg.get("extra_inline", []) or []) + list(cfg["inline"]):
        name = str(rule.get("name", "inline"))
        tmpl = _INLINE_HTML.get(name) or '<span class="%s">%%s</span>' % esc_attr(name)

        def _apply(m, t=tmpl):
            g = m.group(1) if m.groups() else m.group(0)
            return P(t % esc(g or ""))
        try:
            text = re.sub(rule["pattern"], _apply, text)
        except re.error:
            ctx.warn(f"인라인 규칙 '{name}' 의 pattern 을 읽지 못해 건너뜁니다.")

    if tmode in ("pandoc", "multimarkdown"):
        text = nd._SUB_CLOSED_RE.sub(lambda m: P("<sub>%s</sub>" % esc(m.group(1))), text)
        text = nd._SUP_CLOSED_RE.sub(lambda m: P("<sup>%s</sup>" % esc(m.group(1))), text)
        if tmode == "multimarkdown":
            text = nd._SUB_OPEN_RE.sub(lambda m: P("<sub>%s</sub>" % esc(m.group(1))), text)
            text = nd._SUP_OPEN_RE.sub(lambda m: P("<sup>%s</sup>" % esc(m.group(1))), text)
    elif tmode == "wavedash":
        text = text.replace("~", P(esc(wd)))
    else:
        text = text.replace("~", P("&#160;"))        # LaTeX 의 줄바꿈 없는 공백
    return local.restore(esc(text))


# --------------------------------------------------------------------------
# 3. 블록 이전 단계
# --------------------------------------------------------------------------
_SILENT_RAW_RE = re.compile(
    r"\\(?:newpage|clearpage|cleardoublepage|pagebreak|bigskip|medskip|smallskip|vfill|"
    r"appendix|frontmatter|mainmatter|backmatter|noindent|listoffigures|listoftables|"
    r"printindex|bibliographystyle|bibliography|vspace|thispagestyle|pagestyle|"
    r"setcounter|addtocounter|setlength|phantomsection|addcontentsline|nocite)\*?"
    r"(?:\[[^\]]*\])?(?:\{[^{}]*\})*")


def raw_tex(src, ctx):
    """raw LaTeX 블록. 목차·표제 명령만 알아듣고 나머지는 생략한다."""
    rest = src
    out = []
    if re.search(r"\\maketitle\b", rest):
        out.append(_title_tok(ctx))
        rest = re.sub(r"\\maketitle\b", "", rest)
    if re.search(r"\\tableofcontents\*?", rest):
        out.append(_toc_tok(ctx))
        rest = re.sub(r"\\tableofcontents\*?", "", rest)
    rest = re.sub(r"(?m)(?<!\\)%.*$", "", _SILENT_RAW_RE.sub("", rest))
    if rest.strip():
        ctx.raw_omitted += 1
        if ctx.opts.keep_raw:
            out.append(blk('<pre class="rawtex"><code>%s</code></pre>' % esc(src.strip("\n"))))
    return "".join(out)


def code_block(lang, body, ctx):
    lang = (lang or "").strip()
    if lang in ("raw", "tex", "latex"):
        return raw_tex(body, ctx)
    cls = "" if lang in ("", "text", "verb") else ' class="language-%s"' % esc_attr(lang)
    return blk("<pre><code%s>%s</code></pre>" % (cls, esc(body)))


def math_display(raw, ctx):
    ctx.math = True
    raw = raw.strip()
    ctx.math_labels.update(re.findall(r"\\label\{([^{}]*)\}", raw))
    if raw.startswith("$$") and raw.endswith("$$"):
        raw = "\\[" + raw[2:-2] + "\\]"
    return blk('<div class="math display">%s</div>' % esc(raw))


def extract_fences(text, ctx, pr):
    """nd.extract_code_fences 와 같은 규칙으로 코드 펜스를 뽑아 HTML 로 보호한다."""
    lines = text.split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        m = nd._FENCE_OPEN_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        flen, lang, body = len(m.group(1)), m.group(2), []
        ind = len(lines[i]) - len(lines[i].lstrip(" "))     # 펜스의 들여쓰기만큼 내용도 당긴다
        i += 1
        while i < n:
            c = nd._FENCE_CLOSE_RE.match(lines[i])
            if c and len(c.group(1)) >= flen:
                i += 1
                break
            ln = lines[i]
            body.append(ln[min(ind, len(ln) - len(ln.lstrip(" "))):])
            i += 1
        out.append(pr.protect(code_block(lang, "\n".join(body), ctx)))
    return "\n".join(out)


def protect_blocks(text, ctx, pr):
    cfg = ctx.cfg
    text = extract_fences(text, ctx, pr)
    text = nd.scope_cut_endinput(nd.COMMENT_RE.sub(nd._scope_replace(text), text))
    if cfg.get("linecomment"):
        text = nd.LINECOMMENT_RE.sub("", text)
    text, _ = nd._protect_regex_outside_code(
        text, nd.MATH_ENV_RE, lambda raw: pr.protect(math_display(raw, ctx)))
    text, _ = nd._protect_regex_outside_code(
        text, nd.TABLE_ENV_RE, lambda raw: pr.protect(raw_tex(raw, ctx)))
    text, _ = nd._protect_regex_outside_code(
        text, nd.DISPLAY_MATH_RE, lambda raw: pr.protect(math_display(raw, ctx)))
    return text


class _RawCatch:
    """{{tex:파일}} 이 끼워 넣는 raw LaTeX 을 가로챈다."""
    def __init__(self, ctx):
        self.ctx = ctx

    def protect(self, raw):
        return self.ctx.pr.protect(raw_tex(raw, self.ctx))


# --------------------------------------------------------------------------
# 4. 블록
# --------------------------------------------------------------------------
def flow(html, ctx):
    """li / dd / td 처럼 블록을 그대로 품을 수 있는 자리용: 표지만 걷어낸다."""
    return _BLK_RE.sub(lambda m: "\n" + m.group(1) + "\n", ctx.pr.restore(html)).strip()


def wrap_p(inner, ctx):
    """문단 내용을 <p> 로 감싼다. 안에 섞인 블록 요소는 문단을 끊고 밖으로 꺼낸다."""
    inner = ctx.pr.restore(inner)
    out, last = [], 0

    def text_part(t):
        t = re.sub(r"^(?:\s*<br />\s*)+|(?:\s*<br />\s*)+$", "", t.strip())
        if t:
            out.append("<p>%s</p>" % t)
    for m in _BLK_RE.finditer(inner):
        text_part(inner[last:m.start()])
        if m.group(1).strip():
            out.append(m.group(1))
        last = m.end()
    text_part(inner[last:])
    return "\n".join(out)


def _join_lines(first, rest):
    """문단·항목의 여러 줄을 한 줄로. 줄 끝 공백 두 칸은 강제 줄바꿈."""
    segs = [first] + list(rest)
    out = ""
    for i, seg in enumerate(segs):
        s = seg.strip()
        out += s
        if i != len(segs) - 1:
            if nd._BLOCK_PLACEHOLDER_ONLY_RE.match(s):
                out += "\n"
            else:
                out += BR if seg.endswith("  ") else " "
    return out


def _kind(b, ctx):
    first = b[0]
    if nd.ENV_OPEN_RE.match(first):
        return "env"
    if nd.FRAME_OPEN_RE.match(first):
        return "frame"
    if len(b) == 1:
        if nd._SE_PH_RE.fullmatch(first.strip()):
            return "showexam"
        if nd.HEADING_RE.match(first):
            return "heading"
        if nd.HR_STAR_RE.match(first):
            return "asterism"
        if nd.HR_DASH_RE.match(first):
            return "hr"
    if nd.LIST_ESCAPE_UL_RE.match(first) or nd.LIST_ESCAPE_OL_RE.match(first):
        return "para"
    if nd.UL_RE.match(first) or nd.OL_RE.match(first) or nd.desc_match(first, ctx.cfg):
        return "list"
    if nd.QUOTE_RE.match(first):
        return "quote"
    if nd._is_grid_table(b):
        try:
            nd.parse_grid_table(b)
            return "grid"
        except nd.GridTableError as e:
            ctx.warn(f"grid 표를 해석하지 못해 문단으로 처리합니다 ({e}).")
            return "para"
    if len(b) >= 2 and "|" in first and nd.TABLE_SEP_RE.match(b[1]):
        return "table"
    if len(b) == 1 and nd._PH_RE.fullmatch(first.strip()):
        return "placeholder"
    return "para"


def _para_text(b):
    first = b[0]
    m = nd.LIST_ESCAPE_UL_RE.match(first)
    if m:
        first = m.group(1) + m.group(2) + m.group(3)
    else:
        m = nd.LIST_ESCAPE_OL_RE.match(first)
        if m:
            first = m.group(1) + m.group(2) + m.group(3) + m.group(4)
    return _join_lines(first, b[1:])


def _math_only(b):
    return len(b) == 1 and re.fullmatch(r"\\\(.*\\\)", b[0].strip()) is not None


def blocks(lines, ctx):
    bl = []
    lead = []           # 각 블록 앞의 <!--ndhmd ...--> 표지 줄(구간 지시)
    for b, mark in nd.split_blocks(lines):
        k = 0
        while k < len(b) and nd._scope_is_marker(b[k]):
            k += 1
        if k < len(b):
            lead.append(b[:k])
            bl.append((b[k:], mark))
        else:                                   # 끝에 남은 표지뿐인 블록
            nd.apply_scope_markers(b, ctx.cfg)
    kinds = [_kind(b, ctx) for b, _ in bl]
    out = []
    i, n = 0, len(bl)
    while i < n:
        b, mark = bl[i]
        nd.apply_scope_markers(lead[i], ctx.cfg)
        k = kinds[i]
        if k == "para":
            ptext = _para_text(b)
            rtl_p = None
            if (ctx.rtl and ctx.rtl["detect"] == "auto" and not ctx.rtl_ambient
                    and mark not in nd._JOINS):
                rtl_p = nd.rtl_only_script(ptext)      # RTL 글자만 있는 독립 문단
            ctx.rtl_ambient = rtl_p or ctx.rtl_ambient
            try:
                html = ctx.inl(ptext)
            finally:
                if rtl_p:
                    ctx.rtl_ambient = None
            # `||` 로 이은 두 평문단은 한 문단이다. 빈 줄 뒤의 `||` 는 줄만 바꾼다.
            # 한쪽이 수식만 있는 문단(external 의 result: math)이면 공백으로 잇는다 —
            # LaTeX 쪽에서 그 결과는 문단이 아닌 블록이라 `||` 가 줄바꿈(=공백)으로
            # 잇기 때문에, 두 출력이 같은 글이 되게 맞춘다.
            while mark in nd._JOINS and i + 1 < n and kinds[i + 1] == "para":
                nxt = bl[i + 1][0]
                nd.apply_scope_markers(lead[i + 1], ctx.cfg)
                if _math_only(bl[i][0]) or _math_only(nxt):
                    glue = " "
                else:
                    glue = "<br />\n" if mark == nd.JOIN_BR else ""
                html += glue + ctx.inl(_para_text(nxt))
                i += 1
                mark = bl[i][1]
            piece = wrap_p(html, ctx)
            if rtl_p:
                piece = piece.replace("<p>", '<p lang="%s" dir="rtl">' % _rtl_code(rtl_p, ctx))
        elif k == "env":
            piece = environment(b, ctx)
        elif k == "frame":
            piece = frame(b, ctx)
        elif k == "showexam":
            piece = showexam(int(nd._SE_PH_RE.fullmatch(b[0].strip()).group(1)), ctx)
        elif k == "heading":
            piece = heading(b[0], ctx)
        elif k == "asterism":
            piece = '<hr class="asterism" />'
        elif k == "hr":
            piece = "<hr />"
        elif k == "list":
            piece = lst(b, ctx)
        elif k == "quote":
            piece = blockquote(b, ctx)
        elif k == "grid":
            piece = grid_table(b, ctx)
        elif k == "table":
            piece = pipe_table(b, ctx)
        else:
            piece = flow(b[0].strip(), ctx)
        if piece:
            out.append(piece)
        i += 1
    return "\n".join(out)


def heading(line, ctx):
    m = nd.HEADING_RE.match(line)
    level = len(m.group(1))
    attrs = nd.parse_heading_attrs(m.group(3))
    title_html = flow(ctx.inl(m.group(2).strip()), ctx)
    unnumbered = bool(attrs.get("unnumbered"))
    num = ""
    if ctx.opts.number_sections and not unnumbered:
        top = min((h[0] for h in ctx.headings), default=level)
        top = min(top, level)
        ctx.sec[level] += 1
        for d in range(level + 1, 7):
            ctx.sec[d] = 0
        num = ".".join(str(ctx.sec[d]) for d in range(top, level + 1))
    title_plain = plain(title_html)
    ctx.cur_sec = (num, title_plain)
    if attrs.get("label"):
        hid = ctx.label(attrs["label"], "heading", num, title_plain)
    else:
        hid = ctx.new_id(slug(title_html), auto=True)
    toc_html = flow(ctx.inl(attrs["toc"]), ctx) if attrs.get("toc") else title_html
    ctx.headings.append((level, hid, toc_html, num, unnumbered))
    cls = ' class="unnumbered"' if unnumbered else ""
    numspan = '<span class="secnum">%s</span> ' % num if num else ""
    return '<h%d id="%s"%s>%s%s</h%d>' % (level, esc_attr(hid), cls, numspan, title_html, level)


def _item_label(text):
    """`-[라벨] 본문` 의 라벨과 나머지. 라벨이 아니면 (None, text)."""
    if not text.startswith("["):
        return None, text
    depth = 0
    for i, ch in enumerate(text):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[1:i], text[i + 1:].lstrip()
    return None, text


def lst(lines, ctx):
    """리스트. 항목 수집은 nd.render_list 와 같고, `{!옵션}` 은 버린다."""
    items = []
    for line in lines:
        m_ul = nd.UL_RE.match(line)
        m_ol = nd.OL_RE.match(line)
        m_desc = None if (m_ul or m_ol) else nd.desc_match(line, ctx.cfg)
        if m_ul:
            indent = len(m_ul.group(1))
            _opt, content, opt_space = nd._extract_brace_option(m_ul.group(2))
            if opt_space is not None:
                has_space = opt_space
            else:
                after = indent + 1
                has_space = after < len(line) and line[after] in " \t"
            items.append([indent, content, [], None, "itemize", has_space])
        elif m_ol:
            indent = len(m_ol.group(1))
            _opt, content, opt_space = nd._extract_brace_option(m_ol.group(3))
            if opt_space is not None:
                has_space = opt_space
            else:
                after = indent + len(m_ol.group(2)) + 1
                has_space = after < len(line) and line[after] in " \t"
            items.append([indent, content, [], None, "enumerate", has_space])
        elif m_desc:
            indent, term, content = m_desc
            _opt, content, _ = nd._extract_brace_option(content)
            items.append([indent, content, [], term.strip(), "description", True])
        elif items:
            items[-1][2].append(line)
    if not items:
        return ""
    base = min(it[0] for it in items)
    env = next(it[4] for it in items if it[0] == base)
    tag = {"itemize": "ul", "enumerate": "ol", "description": "dl"}[env]
    out = ["<%s>" % tag]
    i = 0
    while i < len(items):
        indent, content, cont, term, _t, has_space = items[i]
        if indent != base:
            i += 1
            continue
        j = i + 1
        sub = []
        while j < len(items) and items[j][0] > base:
            sub.append(nd._reconstruct_item_line(items[j]))
            sub.extend(items[j][2])
            j += 1
        full = _join_lines(content, cont)
        sub_html = ("\n" + lst(sub, ctx) + "\n") if sub else ""
        if tag == "dl":
            if term is not None:
                out.append("<dt>%s</dt>" % flow(ctx.inl(term), ctx))
            out.append("<dd>%s%s</dd>" % (flow(ctx.inl(full), ctx), sub_html))
        else:
            lab_html = ""
            if not has_space:
                lab, rest = _item_label(full)
                if lab is not None:
                    lab_html = '<span class="item-label">%s</span> ' % ctx.inl(lab)
                    full = rest
            out.append("<li>%s%s%s</li>" % (lab_html, flow(ctx.inl(full), ctx), sub_html))
        i = j
    out.append("</%s>" % tag)
    return "\n".join(out)


def blockquote(lines, ctx):
    inner = [nd.QUOTE_RE.match(ln).group(1) if nd.QUOTE_RE.match(ln) else ln for ln in lines]
    body = [ln for ln in inner]
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    cls = "quotation" if any(not ln.strip() for ln in body) else "quote"
    return '<blockquote class="%s">\n%s\n</blockquote>' % (cls, blocks(inner, ctx))


_ALIGN_CSS = {"l": "left", "c": "center", "r": "right"}


def _cell(tag, html, align, span=""):
    style = ' style="text-align: %s;"' % _ALIGN_CSS[align] if align in ("c", "r") else ""
    return "<%s%s%s>%s</%s>" % (tag, span, style, html, tag)


def _table_open(tattrs, ctx):
    """<table> 여는 태그와 <caption>. caption/label 만 쓰고 env/rowhead 는 버린다."""
    cap_src = tattrs.get("caption")
    label = _unbrace(tattrs.get("label"))
    num, cap = "", ""
    cap_html = ctx.inl(cap_src) if cap_src else ""
    if cap_src:
        ctx.tab_n += 1
        num = str(ctx.tab_n)
        cap = ('\n<caption><span class="caption-label">%s %s.</span> %s</caption>'
               % (esc(ctx.names["table"]), num, cap_html))
    tid = ' id="%s"' % esc_attr(ctx.label(label, "table", num, plain(cap_html))) if label else ""
    return "<table%s>%s" % (tid, cap)


def pipe_table(lines, ctx):
    rows = [ln.strip() for ln in lines if ln.strip()]
    tattrs = {}
    if len(rows) >= 3:
        m = nd._TABLE_ATTR_LINE_RE.match(rows[-1])
        if m:
            tattrs = nd.parse_figure_attrs(m.group(1))
            rows = rows[:-1]
    header = nd._split_table_row(rows[0])
    ncol = len(header)
    aligns = []
    for col in nd._split_table_row(rows[1]):
        aligns.append("c" if col.startswith(":") and col.endswith(":")
                      else "r" if col.endswith(":") else "l")
    aligns = (aligns + ["l"] * ncol)[:ncol]
    out = [_table_open(tattrs, ctx), "<thead>",
           "<tr>" + "".join(_cell("th", flow(ctx.inl(h), ctx), a) for h, a in zip(header, aligns)) + "</tr>",
           "</thead>", "<tbody>"]
    for r in rows[2:]:
        cells = (nd._split_table_row(r) + [""] * ncol)[:ncol]
        out.append("<tr>" + "".join(_cell("td", flow(ctx.inl(c), ctx), a)
                                    for c, a in zip(cells, aligns)) + "</tr>")
    out += ["</tbody>", "</table>"]
    return "\n".join(out)


def grid_table(b, ctx):
    tbl, attr = nd.parse_grid_table(b)
    tattrs = nd.parse_figure_attrs(nd._TABLE_ATTR_LINE_RE.match(attr).group(1)) if attr else {}
    nrows, ncols, aligns = tbl["nrows"], tbl["ncols"], tbl["aligns"]
    grid = [[None] * ncols for _ in range(nrows)]
    for cl in tbl["cells"]:
        grid[cl["row"]][cl["col"]] = cl
    out = [_table_open(tattrs, ctx)]
    if (tattrs.get("widths") or "").strip().strip("\"'").lower() == "dash":
        total = float(sum(max(w, 1) for w in tbl["dash_widths"]))
        out.append("<colgroup>" + "".join('<col style="width: %.1f%%;" />' % (max(w, 1) / total * 100)
                                          for w in tbl["dash_widths"]) + "</colgroup>")
    hrows, fstart = tbl["header_rows"], tbl["footer_start"]
    sections = []
    if hrows:
        sections.append(("thead", 0, hrows))
    sections.append(("tbody", hrows, fstart if fstart is not None else nrows))
    if fstart is not None:
        sections.append(("tfoot", fstart, nrows))
    for sec, a, z in sections:
        if a >= z:
            continue
        out.append("<%s>" % sec)
        for r in range(a, z):
            cells = []
            for c in range(ncols):
                cl = grid[r][c]
                if cl is None:
                    continue
                paras = [flow(ctx.inl(p), ctx) for p in cl["paras"]]
                html = paras[0] if len(paras) == 1 else "".join("<p>%s</p>" % p for p in paras)
                span = (' rowspan="%d"' % cl["rs"] if cl["rs"] > 1 else "") + \
                       (' colspan="%d"' % cl["cs"] if cl["cs"] > 1 else "")
                cells.append(_cell("th" if sec == "thead" else "td", html, aligns[c], span))
            out.append("<tr>" + "".join(cells) + "</tr>")
        out.append("</%s>" % sec)
    out.append("</table>")
    return "\n".join(out)


_ENV_SKIP_ATTRS = {"raw", "place", "align", "widest", "label", "caption"}
_BIBITEM_RE = re.compile(r"\\bibitem(?:\[([^\]]*)\])?\{([^{}]*)\}")


def _data_attrs(attrs, skip=_ENV_SKIP_ATTRS):
    out = ""
    for k, v in attrs.items():
        if k in skip or not re.fullmatch(r"[A-Za-z][\w-]*", k):
            continue
        out += ' data-%s="%s"' % (k.lower(), esc_attr(v))
    return out


def _keep_lines(inner, ctx):
    """줄을 지키는 환경(운문): 빈 줄로 연을 나누고 줄마다 <br />."""
    stanzas, cur = [], []
    for ln in inner:
        if ln.strip():
            cur.append(flow(ctx.inl(ln.strip()), ctx))
        elif cur:
            stanzas.append(cur)
            cur = []
    if cur:
        stanzas.append(cur)
    return "\n".join('<p class="stanza">%s</p>' % "<br />\n".join(s) for s in stanzas)


_AY_LABEL_RE = re.compile(r"^(.*?)\(([^()]*\d[^()]*)\)(.*)$", re.S)


def _bib_label_info(label):
    """\bibitem 의 [표시 라벨]. natbib 의 `Short(Year)Long` 이면 저자-연도, 아니면 그대로의 라벨."""
    label = label.strip()
    if label.startswith("{") and label.endswith("}"):
        label = label[1:-1].strip()
    m = _AY_LABEL_RE.match(label)
    if m and m.group(1).strip():
        return ("ay", m.group(1).replace("~", "\u00a0").strip(), m.group(2).strip())
    return label


def _bib_render(items, ctx):
    """items: [(키, 라벨 또는 None, 본문 한 줄)] -> <p class="bibitem"> 목록."""
    ctx.has_bib = True
    out = []
    for key, label, body in items:
        key = key.strip()
        info = _bib_label_info(label) if label else str(len(ctx.bib) + 1)
        ctx.bib[key] = info
        bid = ctx.new_id("bib-" + key, auto=True)
        html = flow(ctx.inl(body), ctx)
        if isinstance(info, tuple):
            out.append('<p class="bibitem ay" id="%s">%s</p>' % (esc_attr(bid), html))
        else:
            out.append('<p class="bibitem" id="%s"><span class="bib-label">[%s]</span> %s</p>'
                       % (esc_attr(bid), esc(info), html))
    return out


def _bibliography(inner, ctx):
    text = "\n".join(inner)
    ms = list(_BIBITEM_RE.finditer(text))
    items = []
    for n, m in enumerate(ms):
        body = text[m.end():ms[n + 1].start() if n + 1 < len(ms) else len(text)]
        items.append((m.group(2), m.group(1) or None,
                      " ".join(l.strip() for l in body.split("\n") if l.strip())))
    return '<section class="bibliography" role="doc-bibliography">\n%s\n</section>' % "\n".join(_bib_render(items, ctx))


# ---- front matter 의 bibliography: — .bbl 에서 문헌 목록 만들기 -------------------------
# ndhmd4tex 가 \addbibresource / \bibliography 를 넣어 LaTeX 로 컴파일하면 biber(또는 bibtex)가
# <이름>.bbl 을 만든다. 여기서는 그 .bbl 을 읽어 목록을 구성한다.
#   * bibtex 형식 .bbl: thebibliography 환경 그 자체 -> 바로 읽는다.
#   * biber 형식 .bbl : biblatex 내부 형식이라 못 읽는다. bbl2bibitem.lua 가 만든
#                       <이름>-thebib.tex (thebibliography 환경)를 읽는다(--bibharvest 로 만들 수 있다).
_BBL_COMBINING = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303",
                  "=": "\u0304", ".": "\u0307", "c": "\u0327", "v": "\u030c", "u": "\u0306",
                  "H": "\u030b", "k": "\u0328", "r": "\u030a"}
_BBL_LETTERS = {"ss": "ß", "o": "ø", "O": "Ø", "aa": "å", "AA": "Å", "ae": "æ", "AE": "Æ",
                "oe": "œ", "OE": "Œ", "l": "ł", "L": "Ł", "i": "ı", "j": "ȷ"}
_BBL_STYLE = {"em": "emph", "it": "textit", "bf": "textbf", "sc": "textsc", "sl": "textsl", "tt": "texttt"}
_BBL_GROUP_RE = re.compile(r"\{\\(em|it|bf|sc|sl|tt)\s+((?:[^{}]|\{[^{}]*\})*)\}")
_BBL_ACCENT_RE = re.compile(r"\\(['`^\"~=.])\s*(?:\{\\?([A-Za-z])\}|\\?([A-Za-z]))")
_BBL_ACCENT2_RE = re.compile(r"\\([cvuHkr])\s*(?:\{([A-Za-z])\}|\s([A-Za-z]))")
_BBL_LETTER_RE = re.compile(r"\\(ss|oe|OE|aa|AA|ae|AE|o|O|l|L)(?![A-Za-z])\s*(?:\{\})?")


def _strip_bare_braces(t):
    """대문자 보호용 {…} 같은 '맨 중괄호'를 벗긴다. \\macro{…} 의 인자 중괄호는 둔다."""
    out, stack = [], []          # stack: 이 { 가 인자 중괄호였는가
    after_arg = False            # 바로 앞이 인자 중괄호의 닫힘이었는가(\\href{…}{…})
    i = 0
    while i < len(t):
        c = t[i]
        if c == "\\" and i + 1 < len(t):
            out.append(t[i:i + 2])
            i += 2
            after_arg = False
            continue
        if c == "{":
            keep = bool(re.search(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])*$", "".join(out[-40:]))) or after_arg
            stack.append(keep)
            if keep:
                out.append(c)
            after_arg = False
        elif c == "}" and stack:
            keep = stack.pop()
            if keep:
                out.append(c)
            elif re.search(r"\\[A-Za-z]+$", "".join(out[-40:])):
                out.append("{}")           # {\\TeX}book -> \\TeX{}book (제어열이 뒤 글자를 먹지 않게)
            after_arg = keep
        else:
            out.append(c)
            after_arg = False
        i += 1
    return "".join(out)


def _bbl_text(raw):
    """.bbl 항목 본문의 BibTeX 잔재(\\newblock, {\\em …}, 악센트 …)를 ndhmd 가 읽는 모양으로."""
    t = raw.replace("\\newblock", " ")
    n = 1
    while n:
        t, n = _BBL_GROUP_RE.subn(lambda m: "\\%s{%s}" % (_BBL_STYLE[m.group(1)], m.group(2)), t)
    t = _BBL_ACCENT_RE.sub(lambda m: (m.group(2) or m.group(3)) + _BBL_COMBINING[m.group(1)], t)
    t = _BBL_ACCENT2_RE.sub(lambda m: (m.group(2) or m.group(3)) + _BBL_COMBINING[m.group(1)], t)
    t = re.sub(r"\\i(?![A-Za-z])\s*", "i", t)       # 악센트 밑에서는 점 없는 i 를 그냥 i 로
    t = _BBL_LETTER_RE.sub(lambda m: _BBL_LETTERS[m.group(1)], t)
    t = re.sub(r"\\(?:penalty\s*-?\d+|relax|protect|unskip)\b\s*", " ", t)
    t = t.replace("``", "\u201c").replace("\'\'", "\u201d")
    t = _strip_bare_braces(t)
    t = re.sub(r"[ \t]+", " ", t).strip()
    t = unicodedata.normalize("NFC", t)
    return t


def _bbl_items(text):
    """thebibliography 환경 안의 \\bibitem 들을 [(키, 라벨, 본문)] 로."""
    m = re.search(r"\\begin\{thebibliography\}\{[^}]*\}(.*?)\\end\{thebibliography\}", text, re.S)
    inner = m.group(1) if m else text
    inner = re.sub(r"(?m)^\s*%.*$", "", inner)
    # natbib 라벨 [{…}] 의 바깥 중괄호가 중첩이라 직접 훑는다
    items, pos = [], 0
    pat = re.compile(r"\\bibitem\s*")
    marks = [x.start() for x in pat.finditer(inner)]
    for n, st in enumerate(marks):
        seg = inner[st:marks[n + 1] if n + 1 < len(marks) else len(inner)]
        k = pat.match(seg).end()
        label = None
        if seg[k:k + 1] == "[":
            depth, e = 0, k
            while e < len(seg):
                if seg[e] == "{":
                    depth += 1
                elif seg[e] == "}":
                    depth -= 1
                elif seg[e] == "]" and depth == 0:
                    break
                e += 1
            label, k = seg[k + 1:e], e + 1
        km = re.match(r"\{([^{}]*)\}", seg[k:])
        if not km:
            continue
        body = seg[k + km.end():]
        body = _bbl_text(" ".join(l.strip() for l in body.split("\n") if l.strip()))
        items.append((km.group(1), label, body))
    return items


def _bib_harvest_script():
    here = Path(__file__).resolve().parent
    for d in [Path.cwd(), here]:
        if (d / "bbl2bibitem.lua").is_file():
            return d / "bbl2bibitem.lua"
    for d in nd.resource_dirs():
        f = nd._find_shallowest(d, "bbl2bibitem.lua")
        if f is not None:
            return f
    return None


def _bib_missing(ctx, why):
    ko = ctx.lang.lower().startswith("ko")
    msgs = {
        "nobbl": ("[LaTeX과 biber/bibtex을 먼저 실행하여야 문헌 목록이 생성됩니다.]",
                  "[Run LaTeX and biber/bibtex first to generate the reference list.]"),
        "biber": ("[biber 가 만든 .bbl 은 bbl2bibitem.lua 로 변환해야 합니다 (--bibharvest).]",
                  "[A biber .bbl must be converted with bbl2bibitem.lua (--bibharvest).]"),
        "fail": ("[문헌 목록을 만들지 못했습니다.]", "[The reference list could not be built.]"),
    }
    text = msgs[why][0 if ko else 1]
    return '<section class="bibliography bibliography-missing" role="doc-bibliography">\n<p class="bib-missing">%s</p>\n</section>' % esc(text)


# ---- biber 수확본의 수식 복원 -------------------------------------------------
# 수확기는 수학 글꼴 글리프를 TeX 소스로 되돌릴 수 없어 [[MATH?]] 표지만 남긴다.
# .bbl 의 필드에는 원문($…$)이 그대로 있으므로, 필드의 "글 + 수식 자리" 모양을 수확된 본문과 맞춰
# 표지를 원문으로 채운다. 추가 LaTeX 패스는 필요 없다.
_MATHSPAN_RE = re.compile(r"(?<!\\)\$(?:\\.|[^$\\])+\$|\\\((?:.|\n)*?\\\)", re.S)
_MATH_MARK = "[[MATH?]]"


def _brace_group(s, i):
    """s[i] == '{' 에서 짝이 맞는 '}' 까지. (안쪽, 끝 다음 위치)"""
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return None, len(s)


def _biber_math_fields(text):
    """biber .bbl -> {키: [수식을 포함한 필드 값, …]}"""
    out = {}
    for m in re.finditer(r"\\entry\{([^}]+)\}\{[^}]*\}(?:\{[^}]*\}){1,2}(.*?)\\endentry", text, re.S):
        key, seg = m.group(1), m.group(2)
        vals = []
        for fm in re.finditer(r"\\field\{[^}]+\}\{", seg):
            v, _ = _brace_group(seg, fm.end() - 1)
            if v and _MATHSPAN_RE.search(v):
                vals.append(v)
        for lm in re.finditer(r"\\list\{[^}]+\}\{\d+\}\{", seg):
            blk, _ = _brace_group(seg, lm.end() - 1)
            pos = 0
            while blk:
                i = blk.find("{", pos)
                if i < 0:
                    break
                g, pos = _brace_group(blk, i)
                if g and _MATHSPAN_RE.search(g):
                    vals.append(g)
        if vals:
            out[key.strip()] = vals
    return out


def _mnorm(t):
    """맞춰 보기용 정규화: 제어 단어·기호·공백을 버리고 글자만 남긴다(수식 자리 \\x00 은 유지)."""
    t = re.sub(r"\\[A-Za-z]+\*?", "", t)
    t = unicodedata.normalize("NFKD", t)
    return "".join(c.lower() for c in t
                   if c == "\x00" or (c.isalnum() and unicodedata.category(c) != "Mn"))


def _skeletons(value):
    """필드 값 -> [(골격 문자열, [채울 원문 묶음…]), …] (수식 사이가 공백뿐이면 한 표지로 합친 변형도)"""
    spans, parts, last = [], [], 0
    for m in _MATHSPAN_RE.finditer(value):
        parts.append(value[last:m.start()])
        spans.append(re.sub(r"\s+", " ", m.group(0)))
        last = m.end()
    parts.append(value[last:])
    res = []
    # 변형 A: 수식마다 표지 하나
    res.append((_mnorm("\x00".join(parts)), [[x] for x in spans]))
    # 변형 B: 사이 글이 공백뿐인 수식은 표지 하나로 합쳐진다(수확기가 수학 글꼴 연속 구간을 묶음)
    groups, gp = [[spans[0]]], [parts[0]]
    for i in range(1, len(spans)):
        if parts[i].strip() == "":
            groups[-1].append(spans[i])
        else:
            groups.append([spans[i]])
            gp.append(parts[i])
    if len(groups) != len(spans):
        gp.append(parts[-1])
        res.append((_mnorm("\x00".join(gp)), groups))
    return res


def _bib_math_fill(items, bbltext, ctx):
    """items 의 [[MATH?]] 를 .bbl 원문으로 채운다. 못 채운 항목은 경고."""
    fields = _biber_math_fields(bbltext)
    out, bad = [], []
    for key, label, body in items:
        n = body.count(_MATH_MARK)
        if not n:
            out.append((key, label, body))
            continue
        bn = _mnorm(body.replace(_MATH_MARK, "\x00"))
        filled = {}
        for value in fields.get(key.strip(), []):
            done = False
            for skel, groups in _skeletons(value):
                if "\x00" not in skel:
                    continue
                pos = bn.find(skel)
                while pos >= 0:
                    idx = bn[:pos].count("\x00")
                    targets = range(idx, idx + len(groups))
                    if not any(t in filled for t in targets):
                        for t, g in zip(targets, groups):
                            filled[t] = " ".join(g)
                        done = True
                        break
                    pos = bn.find(skel, pos + 1)
                if done:
                    break
        pieces = body.split(_MATH_MARK)
        rebuilt = pieces[0]
        for i in range(n):
            rebuilt += filled.get(i, "\u27e8수식\u27e9") + pieces[i + 1]
        if len(filled) < n:
            bad.append(key.strip())
        out.append((key, label, rebuilt))
    if bad:
        ctx.warn("수식을 .bbl 원문에서 찾아 채우지 못한 항목: " + ", ".join(bad)
                 + " (⟨수식⟩ 으로 남습니다. \\alpha 처럼 $ 밖의 수식이거나 필드 모양이 달라진 경우일 수 있습니다.)")
    return out



def bibliography_html(ctx, source_path):
    """bibliography: 가 있을 때의 문헌 목록 <section>. 못 만들면 안내 문구 목록."""
    opts = ctx.opts
    spec = ctx.meta.get("bibliography")
    title = None
    if isinstance(spec, dict) and spec.get("title"):
        title = str(spec["title"])
    stem = Path(source_path).stem if source_path else "output"
    bbl = Path(opts.bbl) if getattr(opts, "bbl", None) else ctx.base_dir / (stem + ".bbl")
    if not bbl.is_file():
        ctx.warn(f"{bbl.name} 이(가) 없습니다. LaTeX 과 biber/bibtex 을 먼저 실행하면 문헌 목록이 만들어집니다.")
        return _bib_missing(ctx, "nobbl")
    text = bbl.read_text(encoding="utf-8", errors="replace")
    # 선언한 .bib 가 .bbl 보다 새로우면 목록이 낡았을 수 있다
    res = spec.get("resource") if isinstance(spec, dict) else spec
    names = [res] if isinstance(res, str) else list(res or [])
    for n in (x.strip() for it in names for x in str(it).split(",")):
        bf = ctx.base_dir / (n if n.lower().endswith(".bib") else n + ".bib")
        if n and bf.is_file() and bf.stat().st_mtime > bbl.stat().st_mtime:
            ctx.warn(f"{bf.name} 이(가) {bbl.name} 보다 새롭습니다. 다시 컴파일해야 목록이 최신이 됩니다.")
    if "\\begin{thebibliography}" in text:
        source = text
    else:
        harvested = bbl.with_name(bbl.stem + "-thebib.tex")
        if getattr(opts, "bibharvest", False):
            script, texlua = _bib_harvest_script(), shutil.which("texlua")
            texfile = bbl.with_suffix(".tex")
            if script is None or texlua is None or not texfile.is_file():
                ctx.warn("--bibharvest: " + ("bbl2bibitem.lua" if script is None else "texlua" if texlua is None
                                              else texfile.name) + " 을(를) 찾을 수 없습니다.")
            else:
                try:
                    r = subprocess.run([texlua, str(script), str(texfile), "-o", str(harvested)],
                                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
                    if r.returncode != 0 or not harvested.is_file():
                        ctx.warn("--bibharvest 실패: " + (r.stderr or "").strip().splitlines()[-1:][0]
                                 if (r.stderr or "").strip() else "--bibharvest 실패")
                    elif r.stderr.strip():
                        print(r.stderr.strip(), file=sys.stderr)
                except (OSError, subprocess.SubprocessError) as e:
                    ctx.warn(f"--bibharvest 실패: {e}")
        if not harvested.is_file():
            ctx.warn(f"{bbl.name} 은(는) biber 형식이라 바로 읽을 수 없습니다. "
                     f"bbl2bibitem.lua 로 {harvested.name} 을(를) 만들거나 --bibharvest 를 주세요.")
            return _bib_missing(ctx, "biber")
        if harvested.stat().st_mtime < bbl.stat().st_mtime:
            ctx.warn(f"{harvested.name} 이(가) {bbl.name} 보다 오래됐습니다. --bibharvest 로 다시 만드세요.")
        source = harvested.read_text(encoding="utf-8", errors="replace")
    items = _bbl_items(source)
    if "\\begin{thebibliography}" not in text and any(_MATH_MARK in b for _, _, b in items):
        items = _bib_math_fill(items, text, ctx)
    if "\\begin{thebibliography}" not in text:
        # biber .bbl 의 항목 키와 수확 결과를 맞춰 본다: 빠진 키가 있으면 수확본이 낡은 것이다
        want = re.findall(r"\\entry\{([^}]+)\}\{", text)
        have = {k.strip() for k, _, _ in items}
        lost = [k for k in want if k not in have]
        if lost:
            ctx.warn(f"{bbl.name} 에는 있으나 {bbl.stem}-thebib.tex 에서 빠진 키: {', '.join(lost)}. "
                     f"수확본이 낡았을 수 있으니 --bibharvest 로 다시 만드세요."
                     + (" (방금 만든 결과에도 없다면 수확이 그 항목을 놓친 것입니다: "
                        f"{bbl.stem}-thebib.tex.warnings 를 확인하세요.)" if getattr(opts, "bibharvest", False) else ""))
    if not items:
        ctx.warn(f"{bbl.name} 에서 문헌 항목을 찾지 못했습니다.")
        return _bib_missing(ctx, "fail")
    head = '<h2 class="bibliography-title">%s</h2>\n' % esc(title or ctx.names["bib"])
    return ('<section class="bibliography" role="doc-bibliography">\n%s%s\n</section>'
            % (head, "\n".join(_bib_render(items, ctx))))


def environment(lines, ctx):
    m = nd.ENV_OPEN_RE.match(lines[0])
    name, attrs = m.group(1), nd.parse_attrs(m.group(2))
    inner = lines[1:-1] if nd.ENV_CLOSE_RE.match(lines[-1]) else lines[1:]
    if ctx.rtl and name not in ctx.cfg["environments"]:
        # RTL 블록: :::{hebrew} 처럼 RTL 언어 이름을 가진 환경
        for script, lang in ctx.rtl["langs"].items():
            if name == lang or name == getattr(nd, "_POLYGLOSSIA_ENVNAME", {}).get(lang):
                prev, ctx.rtl_ambient = ctx.rtl_ambient, script
                try:
                    body = blocks(inner, ctx)
                finally:
                    ctx.rtl_ambient = prev
                label = _unbrace(attrs.get("label"))
                idattr = ' id="%s"' % esc_attr(ctx.label(label, "env", *ctx.cur_sec)) if label else ""
                return ('<div class="%s rtl" lang="%s" dir="rtl"%s>\n%s\n</div>'
                        % (esc_attr(lang), _rtl_code(script, ctx), idattr, body))
    tmpl = ctx.cfg["environments"].get(name) or {}
    mode = str(tmpl.get("lines", "")).lower()
    if mode == "raw":
        return flow(raw_tex("\n".join(inner), ctx), ctx)

    label = _unbrace(attrs.get("label"))
    cap_src = attrs.get("caption")

    if name == "thebibliography":
        return _bibliography(inner, ctx)
    if name in ("table", "figure"):
        # 캡션 번호는 안쪽 내용보다 먼저 매긴다(안쪽 그림·표가 따로 번호를 먹지 않게
        # 하려는 것은 아니다 — LaTeX 과 같은 순서로 세려는 것이다).
        kind = name
        cap, num = "", ""
        cap_html = ctx.inl(cap_src) if cap_src else ""
        if cap_src:
            if kind == "table":
                ctx.tab_n += 1
                num = str(ctx.tab_n)
            else:
                ctx.fig_n += 1
                num = str(ctx.fig_n)
            cap = ('<figcaption><span class="caption-label">%s %s.</span> %s</figcaption>'
                   % (esc(ctx.names[kind]), num, cap_html))
        fid = ' id="%s"' % esc_attr(ctx.label(label, kind, num, plain(cap_html))) if label else ""
        body = blocks(inner, ctx)
        parts = [cap, body] if kind == "table" else [body, cap]
        return '<figure class="%s"%s>\n%s\n</figure>' % (kind, fid, "\n".join(p for p in parts if p))

    num, title = ctx.cur_sec
    idattr = ' id="%s"' % esc_attr(ctx.label(label, "env", num, plain(ctx.inl(cap_src or attrs.get("title") or "")) or title)) if label else ""
    user = ctx.user_envs.get(name)
    if isinstance(user, str):
        user = {"tag": user}
    if isinstance(user, dict):
        tag = str(user.get("tag") or "div")
        cls = str(user.get("class") or name)
    elif name in ("quote", "quotation"):
        tag, cls = "blockquote", name
    else:
        tag, cls = "div", name
    if mode == "keep":
        cls = name if name == "verse" else ("verse " + name if name == "hverse" else name + " lines")
        body = _keep_lines(inner, ctx)
    else:
        body = blocks(inner, ctx)
    return '<%s class="%s"%s%s>\n%s\n</%s>' % (tag, esc_attr(cls), idattr, _data_attrs(attrs), body, tag)


def frame(lines, ctx):
    attrs = nd.parse_attrs(nd.FRAME_OPEN_RE.match(lines[0]).group(1))
    inner = lines[1:-1] if nd.FRAME_CLOSE_RE.match(lines[-1]) else lines[1:]
    name = attrs.get("name")
    out = ['<section class="frame"%s>'
           % (' data-name="%s"' % esc_attr(name) if name and name != "frame" else "")]
    if attrs.get("title"):
        out.append('<h2 class="frametitle">%s</h2>' % flow(ctx.inl(attrs["title"]), ctx))
    if attrs.get("subtitle"):
        out.append('<p class="framesubtitle">%s</p>' % flow(ctx.inl(attrs["subtitle"]), ctx))
    body = blocks(inner, ctx)
    if body:
        out.append(body)
    out.append("</section>")
    return "\n".join(out)


def fragment(md_text, ctx, depth=0):
    """showexam 의 결과 쪽: 본문 처리만 다시 돌린다."""
    store = []
    md_text = nd.expand_external(md_text, ctx.cfg, ctx.base_dir, web=True)
    text = nd.extract_showexam(md_text, store) if depth < 3 else md_text
    saved = (ctx.pr, ctx.se_store, getattr(ctx, "_se_depth", 0))
    ctx.pr, ctx.se_store, ctx._se_depth = nd.Protector(), store, depth + 1
    try:
        text = protect_blocks(text, ctx, ctx.pr)
        return ctx.pr.restore(blocks(text.split("\n"), ctx)).strip()
    finally:
        ctx.pr, ctx.se_store, ctx._se_depth = saved


def showexam(idx, ctx):
    if idx >= len(ctx.se_store):
        return ""
    src, opts = ctx.se_store[idx]
    conf = dict(ctx.cfg.get("showexam") or {})
    layout = str(opts.get("layout", conf.get("layout", "side"))).strip().lower()
    if layout == "auto":
        try:
            limit = float(opts.get("stack_width", conf.get("stack_width", 36)))
        except (TypeError, ValueError):
            limit = 36
        import unicodedata
        longest = max((sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in ln)
                       for ln in src.split("\n")), default=0)
        layout = "stack" if longest > limit else "side"
    if layout not in ("side", "stack"):
        layout = "side"
    lang = str(opts.get("lang", conf.get("lang", "markdown")))
    result = fragment(src, ctx, getattr(ctx, "_se_depth", 0))
    return ('<div class="showexam showexam-%s">\n'
            '<pre class="showexam-src"><code class="language-%s">%s</code></pre>\n'
            '<div class="showexam-result">\n%s\n</div>\n</div>'
            % (layout, esc_attr(lang), esc(src), result))


# --------------------------------------------------------------------------
# 5. 나중에 채우는 것: 참조, 목차, 표제, 조사
# --------------------------------------------------------------------------
def _ref_html(kind, target, shown, ctx):
    info = ctx.labels.get(target)
    if info is None and shown in ctx.math_labels:
        return '<span class="math inline">\\(\\ref{%s}\\)</span>' % shown
    if info is None:
        ctx.warn(f"정의되지 않은 라벨 '{shown}' 을(를) 참조했습니다.")
        # 끊긴 링크를 만들지 않는다(EPUB 검사기가 오류로 본다).
        return '<span class="ref ref-%s ref-undefined">%s</span>' % (kind, shown)
    num, title, lk = info["num"], info["title"], info["kind"]
    names = ctx.names
    if kind == "title":
        text = title or num or shown
    elif kind == "fig":
        text = "%s %s" % (esc(names["figure"]), num or shown)
    elif kind == "tab":
        text = "%s %s" % (esc(names["table"]), num or shown)
    elif kind == "cref" and lk in ("figure", "table") and num:
        text = "%s %s" % (esc(names[lk]), num)
    else:
        text = num or title or shown
    return '<a class="ref ref-%s" href="#%s">%s</a>' % (kind, esc_attr(info["id"]), text)


def _cite_html(variant, keys, ctx):
    items = []                      # (키, 정보 또는 None)
    for key in (k.strip() for k in keys.split(",")):
        if not key:
            continue
        if key not in ctx.bib and ctx.has_bib:
            ctx.warn(f"문헌 목록에 없는 키 '{key}' 을(를) 인용했습니다.")
        items.append((key, ctx.bib.get(key)))

    def link(key, text):
        return '<a href="#%s">%s</a>' % (esc_attr(xid("bib-" + key)), text)

    if items and all(isinstance(i, tuple) for _, i in items):
        # 저자-연도: citet = 저자 (연도), citep/cite = (저자, 연도; …), citeauthor, citeyear
        if variant in ("citeauthor", "citeyear"):
            n = 1 if variant == "citeauthor" else 2
            body = ", ".join(link(k, esc(i[n])) for k, i in items)
            return '<span class="citation cite-%s">%s</span>' % (esc_attr(variant), body)
        if variant in ("citet", "textcite"):
            body = ", ".join("%s (%s)" % (link(k, esc(i[1])), link(k, esc(i[2]))) for k, i in items)
        else:
            body = "(" + "; ".join(link(k, "%s, %s" % (esc(i[1]), esc(i[2]))) for k, i in items) + ")"
        return '<span class="citation cite-%s">%s</span>' % (esc_attr(variant), body)
    parts = []
    for key, info in items:
        if info is None:
            parts.append('<span class="cite-missing" title="문헌 목록에 없는 키">%s</span>' % esc(key))
        else:
            parts.append(link(key, esc(info[1] + ", " + info[2]) if isinstance(info, tuple) else esc(info)))
    return '<span class="citation cite-%s">[%s]</span>' % (esc_attr(variant), ", ".join(parts))


def toc_html(ctx):
    heads = [h for h in ctx.headings if h[0] <= ctx.opts.toc_depth]
    if not heads:
        return ""
    out = ['<nav class="toc" role="doc-toc">', '<h2 class="toc-title">%s</h2>' % esc(ctx.names["toc"])]
    stack = []
    for level, hid, html, num, _un in heads:
        # 목차 항목에는 각주 표지·닻·링크를 넣지 않는다(같은 각주가 두 번 나가지 않게).
        html = _TOK_RE.sub(lambda m: "" if m.group(1).startswith("fn") else m.group(0), html)
        html = re.sub(r'<span id="[^"]*" class="label"></span>|</?a\b[^>]*>', "", html)
        while stack and stack[-1] > level:
            out.append("</li>\n</ul>")
            stack.pop()
        if stack and stack[-1] == level:
            out.append("</li>")
        else:
            out.append("<ul>")
            stack.append(level)
        numspan = '<span class="secnum">%s</span> ' % num if num else ""
        out.append('<li><a href="#%s">%s%s</a>' % (esc_attr(hid), numspan, html))
    while stack:
        out.append("</li>\n</ul>")
        stack.pop()
    out.append("</nav>")
    return "\n".join(out)


def _authors(meta):
    """author: 값을 저자 목록으로. 문자열 안의 \\and 로도 나눈다."""
    a = meta.get("author")
    items = a if isinstance(a, list) else [a] if a else []
    out = []
    for it in items:
        out += [p.strip() for p in re.split(r"\s*\\and\b\s*", str(it)) if p.strip()]
    return out


def title_block(ctx):
    meta = ctx.meta
    if not meta.get("title"):
        return ""
    out = ['<header class="title-block">',
           '<h1 class="title">%s</h1>' % flow(ctx.inl(str(meta["title"])), ctx)]
    if meta.get("subtitle"):
        out.append('<p class="subtitle">%s</p>' % flow(ctx.inl(str(meta["subtitle"])), ctx))
    for a in _authors(meta):
        out.append('<p class="author">%s</p>' % flow(ctx.inl(a), ctx))
    for key in ("institute", "date"):
        if meta.get(key):
            out.append('<p class="%s">%s</p>' % (key, flow(ctx.inl(str(meta[key])), ctx)))
    out.append("</header>")
    return "\n".join(out)


_JOSA_PAIRS = {"은": ("은", "는"), "는": ("은", "는"), "이": ("이", "가"), "가": ("이", "가"),
               "을": ("을", "를"), "를": ("을", "를"), "과": ("과", "와"), "와": ("과", "와"),
               "으로": ("으로", "로"), "로": ("으로", "로")}
_DIGIT_FINAL = {"0": 1, "1": 2, "2": 0, "3": 1, "4": 0, "5": 0, "6": 1, "7": 2, "8": 2, "9": 0}


def _final(ch):
    """받침: 0 없음, 1 있음, 2 ㄹ 받침, None 알 수 없음."""
    if "가" <= ch <= "힣":
        j = (ord(ch) - 0xAC00) % 28
        return 0 if j == 0 else 2 if j == 8 else 1
    return _DIGIT_FINAL.get(ch)


def _josa(name, before):
    text = _TAG_RE.sub("", before[-400:])
    f = None
    for ch in reversed(text):
        if ch.isalnum():
            f = _final(ch)
            break
    if f is None:
        return name
    if name in _JOSA_PAIRS:
        with_final, without = _JOSA_PAIRS[name]
        if with_final == "으로":
            return with_final if f == 1 else without
        return with_final if f else without
    if name.startswith("이") and len(name) > 1:
        return name if f else name[1:]
    if name.startswith("으") and len(name) > 1:
        return name if f == 1 else name[1:]
    return name


def number_notes(html, ctx):
    """각주 표지에 번호를 매긴다. 번호는 문서에 나타난 순서를 따르고(LaTeX 과 같다),
    각주 안의 각주는 그 각주가 목록에 실리는 순서대로 뒤에 이어진다."""
    order = []

    def sub(m):
        f = m.group(1).split(TOK_S)
        if f[0] != "fn":
            return m.group(0)
        note = ctx.notes[int(f[1])]
        if note["sym"]:
            if note["symval"] is not None:
                n = note["symval"]
            elif note["opt"].isdigit():
                n = int(note["opt"])
            else:
                n = ctx.sym_n + 1
            ctx.sym_n = n
            mark = _FN_SYMBOLS[n - 1] if 1 <= n <= len(_FN_SYMBOLS) else str(n)
        elif note["opt"]:
            mark = note["opt"]          # \footnote[3]{...} 처럼 번호를 직접 준 것
        else:
            ctx.fn_n += 1
            mark = str(ctx.fn_n)
        order.append((note, mark))
        k = len(order)
        return ('<sup class="fnref"><a id="fnref-%d" href="#fn-%d" role="doc-noteref">%s</a></sup>'
                % (k, k, esc(mark)))

    html = _TOK_RE.sub(sub, html)
    items, i = [], 0
    while i < len(order):
        note, mark = order[i]
        i += 1
        body = _TOK_RE.sub(sub, flow(note["body"], ctx))
        items.append('<div class="footnote fn-%s" id="fn-%d" role="doc-footnote">'
                     '<sup class="fn-mark">%s</sup> %s '
                     '<a class="fn-back" href="#fnref-%d" role="doc-backlink">↩</a></div>'
                     % (esc_attr(note["kind"]), i, esc(mark), body, i))
    if not items:
        return html
    return (html.rstrip("\n") + '\n<section class="footnotes" role="doc-endnotes">\n<hr />\n'
            + "\n".join(items) + "\n</section>\n")


def resolve_tokens(html, ctx, title_html, toc):
    placed = []

    def place(m):
        f = m.group(1).split(TOK_S)
        if f[0] == "bibliography":
            # \printbibliography 를 여러 번 쓴 문서(en+ko 분할 등): HTML 은 키워드로 거르지 않으므로
            # 전체 목록을 첫 자리에 한 번만 놓고 나머지는 비운다(이중 출력 방지).
            if placed:
                return ""
            placed.append(1)
            return ctx.bib_html
        return toc if f[0] == "toc" else title_html if f[0] == "titleblock" else m.group(0)
    html = number_notes(_TOK_RE.sub(place, html), ctx)

    def refs(m):
        f = m.group(1).split(TOK_S)
        if f[0] == "ref":
            return _ref_html(f[1], f[2], f[3], ctx)
        if f[0] == "cite":
            return _cite_html(f[1], f[2], ctx)
        return m.group(0)
    html = _TOK_RE.sub(refs, html)
    out, last = [], 0
    for m in _TOK_RE.finditer(html):          # 조사는 참조가 글자로 바뀐 뒤에 고른다
        out.append(html[last:m.start()])
        f = m.group(1).split(TOK_S)
        out.append(_josa(f[1], "".join(out[-3:])) if f[0] == "josa" else "")
        last = m.end()
    out.append(html[last:])
    return "".join(out).replace(BLK_O, "").replace(BLK_C, "")


# --------------------------------------------------------------------------
# 5.5. 딸림 스타일시트 (<출력이름>_simple.css)
# --------------------------------------------------------------------------
# 꾸밈을 최소로 한 출발점이다. 어떤 class 가 나오는지 한눈에 보이고 고치기 쉽게,
# 한 덩어리에 한 가지씩만 적는다. 이미 있는 파일은 덮어쓰지 않는다(손본 것을
# 지키려고). 그 대신 문서에 새로 나온 class 가 파일에 없으면 빈 규칙을 끝에 보탠다.
SIMPLE_CSS = """\
/* %(name)s — ndhmd2html %(version)s 이 만든 기본 스타일시트.
   마음대로 고쳐 쓰면 된다. 이 파일이 이미 있으면 ndhmd2html 은 덮어쓰지 않고,
   문서에 새로 나온 class 만 맨 끝에 빈 규칙으로 덧붙인다. */

/* ── 바탕 ─────────────────────────────────────────────── */
html { font-size: 100%%; }
body {
  max-width: 40em;
  margin: 2em auto;
  padding: 0 1em;
  line-height: 1.7;
  word-break: keep-all;          /* 한글을 어절 단위로 줄바꿈 */
  overflow-wrap: break-word;
}
p { margin: 0.8em 0; }
a { color: inherit; }
img { max-width: 100%%; height: auto; }

/* ── 표제 (title: author: date:) ──────────────────────── */
header.title-block { text-align: center; margin-bottom: 3em; }
h1.title { font-size: 1.9em; margin-bottom: 0.3em; }
p.subtitle { font-size: 1.2em; }
p.author { margin: 0.2em 0; }
p.institute { margin: 0.2em 0; }
p.date { margin: 0.2em 0; }

/* ── 헤딩 ─────────────────────────────────────────────── */
h1, h2, h3, h4, h5, h6 { line-height: 1.3; margin: 1.6em 0 0.6em; }
h1 { font-size: 1.7em; }
h2 { font-size: 1.4em; }
h3 { font-size: 1.2em; }
h4, h5, h6 { font-size: 1em; }
span.secnum { margin-right: 0.4em; }   /* 헤딩 번호. 숨기려면 display: none */
.unnumbered { }                        /* {unnumbered} 를 단 헤딩 */

/* ── 목차 (--toc, tocloft: toc) ───────────────────────── */
nav.toc { margin: 2em 0; }
h2.toc-title { font-size: 1.2em; }
nav.toc ul { list-style: none; padding-left: 1.2em; }
nav.toc > ul { padding-left: 0; }
nav.toc a { text-decoration: none; }

/* ── 리스트 ───────────────────────────────────────────── */
ul, ol { padding-left: 1.6em; }
li { margin: 0.2em 0; }
span.item-label { font-weight: bold; }  /* -[라벨] 항목의 라벨 */
dt { font-weight: bold; margin-top: 0.6em; }
dd { margin-left: 1.6em; }

/* ── 인용 ─────────────────────────────────────────────── */
blockquote { margin: 1em 0 1em 1.6em; }
blockquote.quote { }                    /* 한 문단짜리 인용, :::{quote} */
blockquote.quotation { }                /* 여러 문단 인용, :::{quotation} */

/* ── 구분선 ───────────────────────────────────────────── */
hr { border: 0; border-top: 1px solid currentColor; margin: 2em 0; }
hr.asterism {                           /* *** : 장면 전환 */
  border: 0; text-align: center; margin: 1.5em 0;
}
hr.asterism::after { content: "* * *"; }

/* ── 표 ───────────────────────────────────────────────── */
table {
  border-collapse: collapse;
  margin: 1em auto;
  border-top: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
}
th, td { padding: 0.3em 0.8em; vertical-align: top; }
thead th { border-bottom: 1px solid currentColor; }
tfoot td { border-top: 1px solid currentColor; }
td p { margin: 0.3em 0; }               /* grid 표의 여러 문단 셀 */
caption { margin-bottom: 0.4em; }
figure.table { margin: 1.5em 0; text-align: center; }   /* :::{table caption=...} */

/* ── 그림 ─────────────────────────────────────────────── */
figure { margin: 1.5em 0; }
figure.figure { text-align: center; }
figure.wrap {                           /* {wrap} : 글이 옆으로 흐르는 그림 */
  float: right; margin: 0 0 1em 1.5em; max-width: 45%%;
}
figcaption { font-size: 0.92em; margin-top: 0.4em; }
span.caption-label { font-weight: bold; }   /* "그림 1." "표 1." */
img.inline { height: 1em; vertical-align: -0.1em; }   /* {inline} 그림 */

/* ── 코드 ─────────────────────────────────────────────── */
code { font-family: monospace; font-size: 0.92em; }
.sans { font-family: sans-serif; }   /* _산세_ */
pre {
  padding: 0.7em 1em;
  border: 1px solid #ccc;
  overflow-x: auto;
  line-height: 1.4;
  white-space: pre;
}
pre code { font-size: 0.9em; }
pre.rawtex { border-style: dashed; }    /* --keep-raw 로 남긴 raw LaTeX */

/* ── 수식 (MathJax 가 그린다) ─────────────────────────── */
div.math.display { margin: 1em 0; overflow-x: auto; text-align: center; }
span.math.inline { }

/* ── showexam : 원문과 결과 ───────────────────────────── */
div.showexam { margin: 1.2em 0; }
div.showexam-side { display: flex; gap: 1em; align-items: flex-start; }
div.showexam-side > pre.showexam-src { flex: 1 1 46%%; margin: 0; }
div.showexam-side > div.showexam-result { flex: 1 1 50%%; }
div.showexam-stack > pre.showexam-src { margin-bottom: 0; }
div.showexam-stack > div.showexam-result { border-top: 1px solid currentColor; }
pre.showexam-src { white-space: pre-wrap; }
div.showexam-result > :first-child { margin-top: 0; }

/* ── 운문과 줄을 지키는 환경 ──────────────────────────── */
div.verse { margin: 1em 0 1em 1.6em; }
div.hverse { }
p.stanza { margin: 1em 0; }             /* 연. 행은 <br /> 로 나뉜다 */
div.lines { }                           /* lines: keep 으로 정의한 그 밖의 환경 */
div.center { text-align: center; }

/* ── 문헌 목록과 인용 ─────────────────────────────────── */
section.bibliography { }
p.bibitem { padding-left: 2.5em; text-indent: -2.5em; }
p.bibitem.ay { padding-left: 2em; text-indent: -2em; }
.bibliography-title { font-size: 1.3em; }
.bib-missing { font-style: italic; color: #666; }
.cite-missing { color: #b00; }
span.bib-label { display: inline-block; min-width: 2.5em; text-indent: 0; }
span.citation { }

/* ── 각주와 방주 ──────────────────────────────────────── */
sup.fnref { line-height: 0; }
sup.fnref a { text-decoration: none; }
section.footnotes { font-size: 0.9em; margin-top: 3em; }
div.footnote { margin: 0.4em 0; }
sup.fn-mark { margin-right: 0.2em; }
a.fn-back { text-decoration: none; }
div.fn-default { }                      /* 각주 종류: [^x], ^[...] */
div.fn-side { }                         /* {side} */
div.fn-page { }                         /* {page} */
div.fn-verb { }                         /* {verb} */
span.sidenote { font-size: 0.9em; }     /* {sidepar} {sidebar} : 방주 */
span.note-sidepar { }
span.note-sidebar { }

/* ── 참조·라벨·색인 ───────────────────────────────────── */
a.ref { text-decoration: none; }
a.ref-ref { }                           /* [#라벨] */
a.ref-page { }                          /* [page:라벨] */
a.ref-fig { }                           /* [F:라벨] */
a.ref-tab { }                           /* [T:라벨] */
a.ref-title { }                         /* [title:라벨] [name:라벨] */
a.ref-cref { }                          /* [C:라벨] */
.ref-undefined { color: #c00; }         /* 정의되지 않은 라벨 */
span.label { }                          /* {#id} 가 놓인 자리(보이지 않는다) */
span.index { }                          /* [[색인어]] */
span.rtl { }                            /* 히브리·아랍 문자 구간 (lang, dir="rtl" 이 붙는다) */
div.rtl { }                             /* :::{hebrew} 같은 RTL 블록 */
p[dir="rtl"] { }                        /* RTL 글자만 있는 독립 문단 */

/* ── 글자 꾸밈 ────────────────────────────────────────── */
em.dotemph {                            /* ^^방점^^ */
  font-style: normal;
  -webkit-text-emphasis: dot; text-emphasis: dot;
}
span.smallcaps { font-variant: small-caps; }
span.texlogo { }                        /* \\LaTeX 따위 */
span.textcolor { }
span.colorbox { }

/* ── Beamer 프레임 ────────────────────────────────────── */
section.frame { margin: 2em 0; padding: 1em 1.5em; border: 1px solid #ccc; }
h2.frametitle { margin-top: 0; font-size: 1.3em; }
p.framesubtitle { }
"""

_CSS_DOC_HEAD = "\n/* ── 이 문서에 나온 그 밖의 class ───────────────────────\n" \
                "   :::{환경} 이름, 모르는 LaTeX 매크로(tex-이름), extra_inline 규칙 이름 등 */\n"
_CSS_IDENT_RE = re.compile(r"-?[_a-zA-Z\u0080-￿][\w\-\u0080-￿]*")


def _css_selector(cls):
    return "." + cls if _CSS_IDENT_RE.fullmatch(cls) else '[class~="%s"]' % cls.replace('"', '\\"')


def _css_has(css_text, cls):
    if _CSS_IDENT_RE.fullmatch(cls):
        return re.search(r"\.%s(?![\w\-\u0080-￿])" % re.escape(cls), css_text) is not None
    return ('[class~="%s"]' % cls) in css_text


def doc_classes(html):
    """문서에 실제로 나온 class 이름들(나온 순서대로). language-* 는 뺀다."""
    seen = []
    for m in re.finditer(r'class="([^"]*)"', html):
        for c in m.group(1).split():
            if not c.startswith("language-") and c not in seen:
                seen.append(c)
    return seen


def write_simple_css(path, html):
    """딸림 스타일시트를 만든다. 이미 있으면 그대로 두고 새 class 만 덧붙인다.
    (상태, 덧붙인 class 목록) 을 돌려준다."""
    classes = doc_classes(html)
    if path.exists():
        old = path.read_text(encoding="utf-8")
        new = [c for c in classes if not _css_has(old, c)]
        if new:
            add = "\n/* ndhmd2html 이 덧붙임: 문서에 새로 나온 class */\n" + \
                  "".join("%s { }\n" % _css_selector(c) for c in new)
            path.write_text(old.rstrip("\n") + "\n" + add, encoding="utf-8")
        return "kept", new
    base = SIMPLE_CSS % {"name": path.name, "version": __version__}
    extra = [c for c in classes if not _css_has(base, c)]
    if extra:
        base += _CSS_DOC_HEAD + "".join("%s { }\n" % _css_selector(c) for c in extra)
    path.write_text(base, encoding="utf-8")
    return "new", extra


# --------------------------------------------------------------------------
# 6. 최상위
# --------------------------------------------------------------------------
def convert(body, cfg, meta, base_dir, opts, source_path=None):
    """front matter 를 뗀 본문(body)을 HTML 조각으로 바꾼다. (html, ctx) 를 돌려준다."""
    cfg = dict(cfg)
    ctx = Ctx(cfg, meta, base_dir, opts)
    body = nd.resolve_includes(body, ctx.base_dir, _RawCatch(ctx), self_path=source_path)
    # ```external 블록: ndhmd4tex 과 같은 캐시(_external/)를 쓴다. PDF 결과는 옆에 PNG 를
    # 만들어 두고, 그림 경로 해석(_img_src)이 그 PNG 를 고른다.
    cfg["_external_enabled"] = bool(getattr(opts, "external", False))
    body = nd.expand_external(body, cfg, ctx.base_dir, web=True)
    body = nd.extract_showexam(body, ctx.se_store)
    body = protect_blocks(body, ctx, ctx.pr)
    body, cfg["_footnotes"] = nd.extract_footnotes(body)
    body, cfg["_refdefs"] = nd.extract_reference_defs(body)

    main = ctx.pr.restore(blocks(body.split("\n"), ctx))
    if meta.get("bibliography") and not ctx.has_bib:
        # 본문에 thebibliography 환경을 직접 쓰지 않았으면 .bbl 에서 목록을 만든다.
        ctx.bib_html = bibliography_html(ctx, source_path)
        if not ctx.has_bib_tok:
            main = main.rstrip("\n") + "\n" + ctx.bib_html

    before = str(meta.get("beforestart") or "")
    tocloft = meta.get("tocloft") if isinstance(meta.get("tocloft"), dict) else {}
    want_title = opts.title_block or bool(meta.get("maketitle")) or "\\maketitle" in before
    want_toc = opts.toc or bool(tocloft.get("toc")) or "\\tableofcontents" in before
    title_html = title_block(ctx)        # 표제의 각주가 본문 각주 뒤 번호를 받는다
    head = []
    if want_title and not ctx.has_title_tok:
        head.append(tok("titleblock"))
    if want_toc and not ctx.has_toc_tok:
        head.append(tok("toc"))
    html = resolve_tokens("\n".join(p for p in head + [main] if p), ctx, title_html, toc_html(ctx))
    html = re.sub(r"\n{3,}", "\n\n", html).strip() + "\n"
    if ctx.raw_omitted and not opts.keep_raw:
        print(f"알림: raw LaTeX 블록 {ctx.raw_omitted}개를 생략했습니다 "
              f"(--keep-raw 를 주면 <pre class=\"rawtex\"> 로 남깁니다).", file=sys.stderr)
    return html, ctx


def build_document(body_html, ctx):
    meta, opts = ctx.meta, ctx.opts
    title = plain(flow(ctx.inl(str(meta["title"])), ctx)) if meta.get("title") else ""
    lang = esc_attr(ctx.lang)
    out = []
    if opts.xhtml:
        out.append('<?xml version="1.0" encoding="utf-8"?>')
        out.append("<!DOCTYPE html>")
        out.append('<html xmlns="http://www.w3.org/1999/xhtml" lang="%s" xml:lang="%s">' % (lang, lang))
    else:
        out.append("<!DOCTYPE html>")
        out.append('<html lang="%s">' % lang)
    out += ["<head>", '<meta charset="utf-8" />',
            '<meta name="generator" content="ndhmd2html %s" />' % __version__,
            '<meta name="viewport" content="width=device-width, initial-scale=1" />',
            "<title>%s</title>" % (title or esc(opts.fallback_title))]
    for a in _authors(meta):
        text = attr_text(flow(inline(re.sub(r"\^\[.*?\]", "", a), ctx), ctx))
        if text:
            out.append('<meta name="author" content="%s" />' % text)
    for css in opts.css or []:
        out.append('<link rel="stylesheet" href="%s" />' % esc_attr(css))
    if ctx.math and opts.mathjax:
        out.append("<script>window.MathJax = {tex: {tags: 'ams'}};</script>")
        out.append('<script defer="defer" src="%s"></script>' % esc_attr(opts.mathjax))
    out += ["</head>", "<body>", body_html.rstrip("\n"), "</body>", "</html>"]
    return "\n".join(out) + "\n"


def load_cfg(meta, src_path, cli_config, map_base=None):
    """ndhmd4tex 와 같은 순서로 매핑을 읽는다(mapping: -> mappingrule: -> --config)."""
    cfg_path = cli_config or meta.get("mapping")
    paths = cfg_path if isinstance(cfg_path, list) else ([cfg_path] if cfg_path else [])
    resolved = []
    for one in paths:
        near = [Path.cwd()] if cli_config else [map_base or src_path.parent]
        found, tried = nd.resolve_resource(one, near=near)
        if found is None:
            raise nd.ConfigError("매핑 파일을 찾을 수 없습니다: %s\n  찾아본 곳:\n%s"
                                 % (one, "\n".join("    %s" % t for t in tried)))
        resolved.append(found)
    cfg = nd.load_configs(resolved)
    rule = meta.get("mappingrule")
    if rule:
        extra = nd.yaml.safe_load(rule)
        if extra is not None and not isinstance(extra, dict):
            raise nd.ConfigError("front matter의 mappingrule 은 key: value 형태여야 합니다.")
        if extra:
            cfg = nd.deep_merge(cfg, extra)
            if cli_config:
                cfg = nd.deep_merge(cfg, nd.load_config_raw(resolved[0]))
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="ndhmd2html.py",
        description="ndhmd 방언 Markdown 을 HTML 로 바꾼다 (EPUB 준비용).")
    ap.add_argument("input", help="입력 .md")
    ap.add_argument("-o", "--output", help="출력 파일 (기본: 입력 이름.html, --xhtml 이면 .xhtml)")
    ap.add_argument("--body-only", action="store_true", help="<body> 안쪽 조각만 낸다")
    ap.add_argument("--xhtml", action="store_true", help="XHTML 문서로 낸다 (EPUB 용)")
    ap.add_argument("--css", action="append", metavar="URL",
                    help="더 연결할 스타일시트 (여러 번 가능, 기본 스타일시트 뒤에 온다)")
    ap.add_argument("--no-simple-css", dest="simple_css", action="store_false",
                    help="<출력이름>_simple.css 를 만들지도 연결하지도 않는다")
    ap.add_argument("--toc", action="store_true", help="목차를 넣는다")
    ap.add_argument("--toc-depth", type=int, default=3, metavar="N", help="목차에 넣을 헤딩 깊이 (기본 3)")
    ap.add_argument("--title-block", action="store_true", help="표제(제목·저자·날짜)를 본문 앞에 넣는다")
    ap.add_argument("--no-number-sections", dest="number_sections", action="store_false",
                    help="헤딩에 번호를 매기지 않는다 (이때 [#라벨] 은 번호 대신 제목을 보인다)")
    ap.add_argument("--mathjax", nargs="?", const=_MATHJAX_URL, default=_MATHJAX_URL, metavar="URL",
                    help="수식이 있을 때 넣을 MathJax 주소")
    ap.add_argument("--no-mathjax", dest="mathjax", action="store_const", const=None,
                    help="MathJax 스크립트를 넣지 않는다")
    ap.add_argument("--keep-raw", action="store_true", help="raw LaTeX 블록을 <pre class=\"rawtex\"> 로 남긴다")
    ap.add_argument("--external", action="store_true",
                    help="```external 블록의 외부 도구 실행을 허용한다 (mapping 에 등록한 도구만)")
    ap.add_argument("--bbl", metavar="FILE",
                    help="문헌 목록을 읽을 .bbl (기본: 입력 이름.bbl). front matter 의 bibliography: 가 있을 때 쓴다")
    ap.add_argument("--bibharvest", action="store_true",
                    help="biber 형식 .bbl 이면 bbl2bibitem.lua 로 <이름>-thebib.tex 를 (다시) 만든다 "
                         "(texlua, lualatex 필요; 이전 빌드의 .tex 가 있어야 한다)")
    ap.add_argument("--lang", help="문서 언어 (기본: front matter 의 lang, 없으면 ko)")
    ap.add_argument("--config", help="매핑 파일 (ndhmd4tex 의 --config 와 같다)")
    ap.add_argument("--setup", help="헤더 파일 (ndhmd4tex 의 --setup 과 같다)")
    ap.add_argument("--inherit-meta", metavar="main.md",
                    help="이 파일만 변환할 때 main 파일의 헤더를 쓴다(ndhmd4tex 의 --inherit-meta 와 같다). "
                         "이 파일 자신의 front matter 는 버리고 title/author/date 등은 상속하지 않는다")
    ap.add_argument("--default", dest="default_setup", help="기본 헤더 파일. NONE 이면 쓰지 않는다")
    ap.add_argument("--version", action="version",
                    version="ndhmd2html %s (ndhmd4tex %s)" % (__version__, nd.__version__))
    opts = ap.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    src = Path(opts.input)
    out_path = Path(opts.output) if opts.output else src.with_suffix(".xhtml" if opts.xhtml else ".html")
    try:
        text = nd.read_source_text(src)
        cli_default = opts.default_setup
        if cli_default and cli_default != "NONE" and not Path(cli_default).suffix:
            cli_default += ".nmd"
        inherit_dir = None
        try:
            if opts.inherit_meta and Path(opts.inherit_meta).resolve() != src.resolve():
                meta, _chain, ignored, inh_warns = nd.resolve_inherited_meta(
                    opts.inherit_meta, text, src, cli_setup=opts.setup, cli_default=cli_default)
                body_md = nd.split_frontmatter(text, source=src, lenient=True)[1]
                inherit_dir = Path(opts.inherit_meta).parent
                if ignored:
                    print("알림: --inherit-meta: %s 자신의 front matter 는 무시합니다 (%s)."
                          % (src.name, ", ".join(ignored)), file=sys.stderr)
                for w in inh_warns:
                    print("경고: " + w, file=sys.stderr)
            else:
                meta, body_md, _chain = nd.resolve_meta(text, src, cli_setup=opts.setup, cli_default=cli_default)
        except nd.SetupError as e:
            # setup 파일은 대개 LaTeX 헤더(class, preamble)라 HTML 에는 없어도 된다.
            print("경고: setup 파일을 읽지 못해 문서 자신의 front matter 만 씁니다.\n  %s"
                  % str(e).replace("\n", "\n  "), file=sys.stderr)
            raw_meta, body_md = nd.split_frontmatter(text, source=src)
            meta = {k: v for k, v in (raw_meta or {}).items()
                    if k.rstrip("+") != nd.SETUP_KEY}
        cfg = load_cfg(meta, src, opts.config, inherit_dir)
        opts.fallback_title = src.stem
        opts.out_dir = out_path.parent
        body, ctx = convert(body_md, cfg, meta, src.parent, opts, source_path=src)
    except (nd.SourceError, nd.SetupError, nd.ConfigError, nd.IncludeError, nd.ExternalError) as e:
        print("오류: %s" % e, file=sys.stderr)
        return 1
    css_note = ""
    if opts.simple_css:
        css_path = out_path.with_name(out_path.stem + "_simple.css")
        try:
            state, added = write_simple_css(css_path, body)
            css_note = "새로 만듦" if state == "new" else "이미 있어 그대로 둠"
            if state == "kept" and added:
                css_note += "; 새 class %d개를 끝에 덧붙임: %s" % (len(added), ", ".join(added))
            if not opts.body_only:
                opts.css = [css_path.name] + list(opts.css or [])
        except OSError as e:
            print("경고: 스타일시트를 쓰지 못했습니다 (%s)." % e, file=sys.stderr)
    out_text = body if opts.body_only else build_document(body, ctx)
    out_path.write_text(out_text, encoding="utf-8")
    print("[ndhmd2html] 변환 완료: %s" % out_path, file=sys.stderr)
    if css_note:
        print("[ndhmd2html] 스타일시트: %s (%s)" % (css_path, css_note), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
