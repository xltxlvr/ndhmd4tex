#!/usr/bin/env python3
r"""tex2ndhmd.py — LaTeX -> ndhmd(4tex) 초안 변환기.

ndhmd4tex.py 는 ndhmd 방언 -> LaTeX 방향이다. 이 스크립트는 그 반대다.

목표는 100% 무손실 왕복이 아니라 "거의 손대지 않아도 될 정도"의 초안이다.
완전한 LaTeX 파서를 새로 짜지 않는다 — pandoc의 LaTeX 리더를 거쳐 markdown을
얻은 뒤, ndhmd4tex 문법에 맞도록 기계적으로 손보는 후처리 스크립트다.

    LaTeX --[pandoc -f latex+raw_tex]--> pandoc식 markdown --[후처리]--> ndhmd

pandoc이 모르는 매크로/환경은 raw_tex 리더 확장 덕분에 사라지지 않고
`` `...`{=latex} `` 인라인 스팬이나 ```` ```{=latex} ```` 블록으로 보존된다.
이건 ndhmd4tex.py 가 이미 지원하는 raw 통과 문법과 같은 것이라 대개 손댈
필요가 없다. 후처리는 그 나머지 — pandoc과 ndhmd4tex의 문법이 우연히
다른 자리, 그리고 방치하면 ndhmd4tex 쪽에서 조용히 깨지는 자리만 고친다.

사용법:
    python3 tex2ndhmd.py 입력.tex -o 출력.md
    python3 tex2ndhmd.py 입력.tex          # 표준출력으로

필요한 것: pandoc (PATH에 있어야 한다). 그 외 외부 의존성 없음.

Copyright (c) 2026 Nova de Hi
Licensed under the MIT License. See LICENSE for details.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

__version__ = "0.2.1"


# --------------------------------------------------------------------------
# 1. 별행수식 환경 미리 빼두기
# --------------------------------------------------------------------------
#
# pandoc은 \begin{equation}/align/gather/multline/eqnarray 를 "아는" 구문으로
# 취급해서 $$...$$ 로 재작성해버린다. raw_tex 확장도 이건 막지 못한다 —
# 수식 환경은 pandoc이 raw로 남기는 대상이 아니라 자기 나름대로 해석하는
# 대상이기 때문이다. 문제는 그 안의 \label 이 $$...$$ 안에 텍스트로만
# 남고, $$...$$ 자체가 번호 없는 수식이라 \ref 로 참조할 카운터가 없어진다
# 는 것이다 — 원본에서 번호가 매겨지던 수식의 상호참조가 조용히 죽는다.
#
# 반면 ndhmd4tex.py 자신의 MATH_ENV_RE 는 이 환경들을 원문 그대로(줄
# 단위가 아니라 블록 전체를) raw로 보호하도록 이미 되어 있다. 그러니
# pandoc에게 넘기기 전에 이 환경들을 원문에서 통째로 뽑아 자리표시자로
# 바꿔두고, 후처리 마지막 단계에서 원문 그대로 되돌리면 번호와 \label이
# 그대로 살아난다.
_MATH_ENV_NAMES = r"equation\*?|align\*?|gather\*?|multline\*?|eqnarray\*?"
_MATH_ENV_RE = re.compile(
    r"\\begin\{(" + _MATH_ENV_NAMES + r")\}.*?\\end\{\1\}", re.DOTALL
)

_PLACEHOLDER_TMPL = "Xtexndhmdplaceholder{:04d}X"
_PLACEHOLDER_RE = re.compile(r"Xtexndhmdplaceholder(\d{4})X")


def extract_math_envs(tex_source):
    """수식 환경을 뽑아 자리표시자로 바꾼다. (치환된 소스, {번호: 원문}) 반환.

    자리표시자는 문단 하나를 통째로 차지하는 형태로 심는다(앞뒤에 빈 줄).
    pandoc이 이걸 평범한 한 단어짜리 문단으로 보고 그대로 통과시켜야
    나중에 정확히 되찾을 수 있다 — 문단 중간에 심으면 pandoc이 줄바꿈을
    합치거나 이스케이프를 붙여 자리표시자 자체가 손상될 수 있다.
    """
    store = {}

    def _replace(m):
        idx = len(store)
        store[idx] = m.group(0)
        return "\n\n" + _PLACEHOLDER_TMPL.format(idx) + "\n\n"

    replaced = _MATH_ENV_RE.sub(_replace, tex_source)
    return replaced, store


def restore_math_envs(markdown_text, store):
    def _sub(m):
        idx = int(m.group(1))
        return store.get(idx, m.group(0))

    return _PLACEHOLDER_RE.sub(_sub, markdown_text)


# --------------------------------------------------------------------------
# 2. pandoc 호출
# --------------------------------------------------------------------------

# grid_tables/simple_tables 를 끄고 pipe_tables 만 켠다 — ndhmd4tex.py 가
# 이해하는 표 형식은 파이프 표뿐이다(14장).
#
# raw_html 도 끈다. 캡션·라벨·너비가 다 붙은 그림처럼 순수 markdown
# 이미지 문법 하나로 표현이 안 되는 구조를 만나면, 이 확장이 켜진 채로는
# pandoc이 `<figure><img .../><figcaption>...</figcaption></figure>` 같은
# raw HTML 블록으로 폴백해버린다(실측 확인). ndhmd4tex.py는 HTML을 전혀
# 모르므로 이게 그냥 리터럴 텍스트로 떨어져 `<`, `>`, `"` 같은 문자가
# 깨지고, 심지어 안의 큰따옴표가 ndhmd4tex 자신의 스마트따옴표 변환에
# 걸려 `''`로 바뀌는 등 이중으로 망가진다. 꺼두면 같은 구조를 중첩
# fenced div(`::: {#id .figure} ... ::: caption ... ::: :::`)로 내는데,
# 이건 최소한 markdown 문법이라 후처리로 재조립할 수 있다
# (convert_figure_divs 참고).
_PANDOC_WRITER = "markdown-grid_tables-simple_tables-raw_html+pipe_tables"


def run_pandoc(tex_text, cwd):
    """pandoc으로 LaTeX -> markdown(+메타데이터) 변환. stdout 텍스트를 돌려준다."""
    cmd = [
        "pandoc",
        "-f", "latex+raw_tex",
        "-t", _PANDOC_WRITER,
        "-s",  # front matter(YAML) 블록 포함 — title/author/date 를 건진다.
        "--wrap=none",  # 줄바꿈을 pandoc이 임의로 넣지 않게 한다.
    ]
    try:
        proc = subprocess.run(
            cmd, input=tex_text, capture_output=True, text=True,
            encoding="utf-8", cwd=str(cwd), timeout=120,
        )
    except FileNotFoundError:
        print("오류: pandoc 을 찾을 수 없습니다. PATH에 설치되어 있어야 합니다.",
              file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("오류: pandoc 실행이 시간 초과되었습니다.", file=sys.stderr)
        sys.exit(1)
    if proc.returncode != 0:
        print(f"오류: pandoc이 실패했습니다(종료 코드 {proc.returncode}).",
              file=sys.stderr)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        sys.exit(1)
    if proc.stderr:
        # pandoc이 자잘한 경고를 stderr로 내는 경우가 있다(예: 알 수 없는
        # 패키지 옵션). 변환 자체는 계속되므로 그대로 넘겨서 보여주기만 한다.
        print(proc.stderr, file=sys.stderr, end="")
    return proc.stdout


# --------------------------------------------------------------------------
# 3. front matter 분리
# --------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def split_pandoc_output(text):
    """pandoc -s 출력에서 (front matter 원문 또는 None, 본문) 을 분리한다."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def build_front_matter(pandoc_fm_text):
    """pandoc의 title/author/date 를 뽑아 ndhmd4tex front matter로 다시 짠다.

    pandoc의 YAML을 그대로 복사하지 않는 이유: pandoc 메타데이터에는
    ndhmd4tex.py가 모르는 키가 섞여 나올 수 있고(예: lang, header-includes),
    author 가 리스트 형태(`- 홍길동`)로 나오는 등 표현이 달라 그대로 복사하면
    오히려 헷갈린다. 여기서는 필요한 세 값만 뽑아 이 도구의 관례대로 다시
    쓴다.
    """
    title = author = date = None
    if pandoc_fm_text:
        # 아주 단순한 값만 뽑는다(줄 하나짜리 title/date, 한 줄 또는
        # "- 이름" 리스트 하나짜리 author). YAML 파서를 쓰지 않는 이유는
        # 이 스크립트가 pandoc 외에 아무 의존성도 요구하지 않게 하기
        # 위해서다 — PyYAML조차 없는 환경에서도 그냥 돌아가야 한다.
        lines = pandoc_fm_text.split("\n")
        i = 0
        while i < len(lines):
            ln = lines[i]
            m = re.match(r"^title:\s*(.*)$", ln)
            if m:
                title = m.group(1).strip().strip('"').strip("'")
            m = re.match(r"^date:\s*(.*)$", ln)
            if m:
                date = m.group(1).strip().strip('"').strip("'")
            if re.match(r"^author:\s*$", ln) and i + 1 < len(lines):
                m2 = re.match(r"^-\s*(.*)$", lines[i + 1])
                if m2:
                    author = m2.group(1).strip().strip('"').strip("'")
                    i += 1
            else:
                m = re.match(r"^author:\s*(.*)$", ln)
                if m and m.group(1).strip():
                    author = m.group(1).strip().strip('"').strip("'")
            i += 1

    lines = ["---"]
    if title:
        lines.append(f"title: {title}")
    else:
        lines.append("title: 제목 없음  # TODO")
    if author:
        lines.append(f"author: {author}")
    if date:
        lines.append(f"date: {date}")
    lines.append("class: article  # TODO: 원본 \\documentclass 확인 후 조정")
    lines.append("toplevel: section  # article 계열이면 필요. book/report면 지울 것")
    lines.append("# setup: ndhmd-default.nmd   # 공용 헤더를 쓴다면 주석 해제")
    lines.append("---")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# 4. 본문 후처리 — 여기가 진짜 변환기다
# --------------------------------------------------------------------------

# 코드 스팬(`...`)과 raw 스팬(`...`{=latex}), 펜스드 코드블록은 이 뒤의
# 정규식 치환이 절대 건드리면 안 된다. ndhmd4tex.py 자신의 _mask_inline_code
# 와 같은 이유다 — 안의 내용이 우연히 다른 패턴과 겹치면 안 된다.


def _mask_protected_spans(text):
    """백틱 스팬과 펜스드 코드블록을 자리표시자로 가린다. (가려진 텍스트, 저장소)."""
    store = []

    def _stash(s):
        idx = len(store)
        store.append(s)
        return f"\x00MASK{idx}\x00"

    # 펜스드 코드블록 먼저(``` ... ```, 언어 태그나 {=latex} 포함 가능).
    text = re.sub(r"```.*?\n.*?\n```", lambda m: _stash(m.group(0)), text,
                  flags=re.DOTALL)
    # 인라인 코드/raw 스팬. 백틱 개수가 다양할 수 있으나(중첩 백틱 방지용)
    # 실무에서는 거의 항상 단일 백틱이므로 단일 백틱 기준으로 처리한다.
    text = re.sub(r"`[^`\n]*`(?:\{=\w+\})?", lambda m: _stash(m.group(0)), text)
    return text, store


def _unmask_protected_spans(text, store):
    def _sub(m):
        return store[int(m.group(1))]
    return re.sub(r"\x00MASK(\d+)\x00", _sub, text)


def with_masking(func):
    """본문 전체에 적용할 정규식 치환 함수를, 보호 스팬을 가린 채로 돌린다."""
    def wrapper(text):
        masked, store = _mask_protected_spans(text)
        masked = func(masked)
        return _unmask_protected_spans(masked, store)
    return wrapper


# ── 4.0. raw 블록 펜스 태그: pandoc -> ndhmd4tex ──────────────────────
#
# pandoc은 "이 펜스 안은 특정 출력 형식(latex)에 대해서만 그대로 통과시켜라"
# 는 뜻으로 ```` ```{=latex} ```` 정보 문자열을 쓴다. 반면 ndhmd4tex.py의
# _FENCE_OPEN_RE 는 정보 문자열로 `[a-zA-Z0-9_-]*` 만 받아들인다 — 중괄호와
# `=`이 든 `{=latex}`는 이 정규식에 아예 매치되지 않아 코드블록으로도
# 인식되지 못한 채 평문으로 떨어진다(실측 확인). ndhmd4tex.py 자신의 raw
# 통과 관례는 언어 태그를 `raw`/`tex`/`latex` 로 쓰는 것이므로(10장), 그
# 형태로 먼저 바꿔둔다. 이 치환은 블록의 첫 줄(여는 펜스)에만 적용된다.

_RAW_FENCE_OPEN_RE = re.compile(r"^```\{=latex\}\s*$", re.MULTILINE)


def convert_raw_fence_tags(text):
    return _RAW_FENCE_OPEN_RE.sub("```raw", text)


# ── 4.0.5. 그림 div 재조립: pandoc 중첩 div -> ndhmd4tex 단일 이미지 문법 ──
#
# 캡션·라벨·너비가 다 붙은 그림은 순수 markdown 이미지 문법 하나로 표현이
# 안 되니, pandoc(raw_html 끈 상태)은 이렇게 중첩된 fenced div로 낸다.
#
#   ::: {#fig:pi .figure}          (라벨이 없으면 `::: figure` bare 형태)
#   ```{=latex}
#   \centering
#   ```
#   ![](pi.png){width="3cm"}
#
#   ::: caption
#   원주율
#   :::
#   :::
#
# 이걸 그대로 두면 convert_fenced_divs 가 바깥 div를 `:::{figure ...}`
# 로, 안쪽 `::: caption` 을 또 다른 `:::{caption}` 환경으로 바꿔버려
# ndhmd4tex.py 가 이해하지 못하는 이중 중첩 구조가 된다. 이 특정 패턴을
# convert_fenced_divs 보다 먼저 인식해서, ndhmd4tex.py 의 원래 그림
# 문법 한 줄로 재조립한다 — `![캡션](pi.png){width="3cm", label="fig:pi"}`.
# 안의 raw 블록(`\centering` 등)은 float 안 흔한 관례라 대개 없어도
# 무방하므로 버린다(완전한 보존이 필요하면 사람이 캡션 앞뒤에 다시 끼워
#넣을 수 있게, 버린 내용이 있었다는 주석을 남긴다).

_FIGURE_DIV_OPEN_ATTR_RE = re.compile(r"^:::\s*\{#([\w:.\-]+)\s+\.figure\}\s*$")
_FIGURE_DIV_OPEN_BARE_RE = re.compile(r"^:::\s+figure\s*$")
_FIGURE_IMG_RE = re.compile(r"^!\[\]\(([^)]+)\)(?:\{([^}]*)\})?\s*$")
_CAPTION_DIV_OPEN_RE = re.compile(r"^:::\s+caption\s*$")


def convert_figure_divs(text):
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        m_attr = _FIGURE_DIV_OPEN_ATTR_RE.match(lines[i])
        m_bare = _FIGURE_DIV_OPEN_BARE_RE.match(lines[i]) if not m_attr else None
        if m_attr or m_bare:
            label = m_attr.group(1) if m_attr else None
            j = i + 1
            img_path, img_attrs, caption = None, "", None
            dropped_raw = False
            depth = 1  # 바깥 :::{...figure} 하나가 이미 열린 상태
            while j < len(lines) and depth > 0:
                ln = lines[j]
                if ln.strip() == ":::":
                    depth -= 1
                    j += 1
                    continue
                if _CAPTION_DIV_OPEN_RE.match(ln):
                    depth += 1
                    j += 1
                    cap_lines = []
                    while j < len(lines) and lines[j].strip() != ":::":
                        cap_lines.append(lines[j])
                        j += 1
                    caption = " ".join(x.strip() for x in cap_lines if x.strip())
                    depth -= 1  # 캡션 div의 닫는 ::: 를 여기서 이미 소비
                    j += 1
                    continue
                m_img = _FIGURE_IMG_RE.match(ln)
                if m_img:
                    img_path, img_attrs = m_img.group(1), (m_img.group(2) or "")
                    j += 1
                    continue
                if ln.strip() == "```{=latex}":
                    dropped_raw = True
                    j += 1
                    while j < len(lines) and lines[j].strip() != "```":
                        j += 1
                    j += 1
                    continue
                j += 1  # 빈 줄 등은 건너뛴다
            if img_path is not None:
                attrs = [a.strip() for a in img_attrs.split(",") if a.strip()]
                if label:
                    attrs.append(f'label="{label}"')
                attr_str = ("{" + ", ".join(attrs) + "}") if attrs else ""
                cap = caption or ""
                out.append(f"![{cap}]({img_path}){attr_str}")
                if dropped_raw:
                    out.append(
                        "<!-- tex2ndhmd: 그림 안의 raw LaTeX(예: \\centering)은 "
                        "옮기지 않고 버렸다. 필요하면 손으로 다시 넣을 것. -->"
                    )
                i = j
                continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


# ── 4.1. fenced div: pandoc 표기 -> ndhmd4tex 표기 ─────────────────────
#
# pandoc: ::: name              또는  ::: {.name key="val" ...}
# ndhmd4tex: :::{name}          또는  :::{name key="val" ...}   (공백 없이!)
#
# 닫는 ":::" 는 이미 양쪽이 같은 표기라 손댈 것이 없다.

_DIV_OPEN_BARE_RE = re.compile(r"^:::\s+([a-zA-Z][\w-]*)\s*$", re.MULTILINE)
_DIV_OPEN_ATTR_RE = re.compile(r"^:::\s*\{([^}]*)\}\s*$", re.MULTILINE)


def _parse_pandoc_div_attrs(attr_str):
    """pandoc의 `{.name key="val" #id}` 속성 문자열을 (이름, 속성딕셔너리)로.

    `.name` 은 환경 이름으로, `#id` 는 label= 속성으로 옮긴다. 이름이 없으면
    "div"를 임시 이름으로 쓴다 — ndhmd4tex.py 의 default 환경 템플릿이
    받아준다(안의 raw= 로 그대로 통과).
    """
    name = None
    attrs = {}
    for tok in attr_str.split():
        if tok.startswith("."):
            if name is None:
                name = tok[1:]
        elif tok.startswith("#"):
            attrs["label"] = tok[1:]
        elif "=" in tok:
            k, v = tok.split("=", 1)
            attrs[k] = v.strip('"')
    return name or "div", attrs


def convert_fenced_divs(text):
    def _bare(m):
        return f":::{{{m.group(1)}}}"

    def _attr(m):
        name, attrs = _parse_pandoc_div_attrs(m.group(1))
        extra = "".join(f", {k}=\"{v}\"" for k, v in attrs.items())
        return f":::{{{name}{extra}}}"

    # attr-form(중괄호)을 먼저 바꾼다. 그 뒤에 bare-form을 돌리는 이유는
    # 순서가 반대면 사고가 난다: bare-form이 먼저 `::: center`를
    # `:::{center}`로 바꿔놓으면, 그 결과가 attr-form 정규식(중괄호가
    # 있으면 매치)에 다시 걸려 `_parse_pandoc_div_attrs("center")`가 돌게
    #된다. "center"는 `.`으로 시작하지 않으니 클래스로 인식되지 못하고
    # 결국 이름이 통째로 "div"로 뭉개진다(실측으로 확인한 버그). attr-form을
    # 먼저 처리해두면 그 출력(`:::{name...}`, `:::`와 `{` 사이에 공백 없음)
    # 은 bare-form 정규식(`:::` 뒤에 공백 1개 이상을 요구)과 애초에 형태가
    # 달라 재매치되지 않는다.
    text = _DIV_OPEN_ATTR_RE.sub(_attr, text)
    text = _DIV_OPEN_BARE_RE.sub(_bare, text)
    return text


# ── 4.2. 인용 문법: pandoc -> ndhmd4tex refcite 프리픽스 ──────────────
#
# pandoc [@key]  (괄호형, \citep 상당)      -> [@p:key]
# pandoc @key    (본문형, \citet 상당)      -> [@t:key]
#
# 대괄호 없는 본문형은 오탐 위험이 있다(이메일 등에도 @ 이 나온다). 인용
# 키 문자(영숫자·:·_·-)로만 이루어져야 하고 앞이 단어 경계여야 매치되게
# 좁혀서 위험을 줄인다. 마침표는 키 문자에서 뺀다 — "@jones2019." 처럼
# 문장 끝에 붙으면 마침표까지 키로 삼켜버리기 쉽다(bibtex 키 관례상 마침표를
# 실제로 쓰는 경우는 드물다).
#
# 괄호형을 먼저 바꾼 뒤 본문형 정규식을 돌리므로, 그 결과로 생긴
# `[@p:key]` 안의 `@`를 본문형이 다시 잡아 이중으로 감싸지 않도록(실제로
# `[[@t:p:key]]`처럼 깨지는 것을 실측으로 확인했다) `[` 바로 뒤는 제외한다.

_CITE_BRACKET_RE = re.compile(r"\[@([\w:\-]+)\]")
_CITE_BARE_RE = re.compile(r"(?<!\[)(?<![\w@])@([\w:\-]+)")


def convert_citations(text):
    text = _CITE_BRACKET_RE.sub(lambda m: f"[@p:{m.group(1)}]", text)
    text = _CITE_BARE_RE.sub(lambda m: f"[@t:{m.group(1)}]", text)
    return text


# ── 4.3. raw 스팬 상호참조 -> ndhmd4tex 축약형 ────────────────────────
#
# `\ref{x}`{=latex}      -> [#x]
# `\pageref{x}`{=latex}  -> [page:x]
# `\nameref{x}`{=latex}  -> [name:x]
# `\eqref{x}`{=latex}    -> [E:x]
#
# 굳이 축약형으로 바꾸는 이유: raw 스팬 그대로 두어도 동작은 하지만(둘 다
# 결국 같은 LaTeX을 내놓는다), ndhmd4tex 관용구를 쓰는 편이 사람이 읽고
# 손보기에 더 낫다 — 이 스크립트의 목표가 "손대지 않아도 될 정도"이므로
# 사람이 훑어볼 결과물의 가독성도 값어치가 있다.

_REFCITE_RAW_RE = re.compile(
    r"`\\(ref|pageref|nameref|eqref)\{([^}]+)\}`\{=latex\}"
)
_REFCITE_MAP = {"ref": "#", "pageref": "page:", "nameref": "name:", "eqref": "E:"}


def convert_refcite_raw(text):
    def _sub(m):
        cmd, label = m.group(1), m.group(2)
        return f"[{_REFCITE_MAP[cmd]}{label}]"
    return _REFCITE_RAW_RE.sub(_sub, text)


# ── 4.4. 위/아래첨자: pandoc 단일 캐럿/틸드 -> raw 스팬 ───────────────
#
# pandoc: ^위^ / ~아래~  (단일 문자 델리미터)
# ndhmd4tex: 이 문법 자체가 없다 — 단일 ^ 는 자동 이스케이프 대상이라
#   \textasciicircum{}로 깨지고, 단일 ~ 는 raw로 그대로 흘러가 유효하지
#   않은 LaTeX이 된다(7.2장 참고, 물결표 정책). 그대로 두면 반드시 깨지므로
#   raw 스팬으로 감싸 원래 뜻(위/아래첨자)을 명시적으로 살린다.
#
# 취소선 ~~...~~ (이중 틸드)와 헷갈리지 않도록 이중 틸드는 건드리지 않는다.

_SUPERSCRIPT_RE = re.compile(r"\^([^\^\s]+)\^")
_SUBSCRIPT_RE = re.compile(r"(?<!~)~([^~\s]+)~(?!~)")


def convert_super_subscript(text):
    text = _SUPERSCRIPT_RE.sub(
        lambda m: "`\\textsuperscript{%s}`{=latex}" % m.group(1), text)
    text = _SUBSCRIPT_RE.sub(
        lambda m: "`\\textsubscript{%s}`{=latex}" % m.group(1), text)
    return text


# ── 4.4.5. 조사 매크로: raw 스팬 감싸기를 벗긴다 ───────────────────────
#
# ndhmd4tex.py 자신이 이 열 개를 "그대로 통과시키는" 리터럴 매크로로 이미
# 알고 있다(literal_macros 기본값, 7장) — 영문·숫자 뒤에 한글 조사를
# 자연스럽게 붙이기 위한 것으로, 이 방언에서는 문장마다 나올 만큼 흔하다.
# 그런데 pandoc은 이걸 모르는 매크로로 보고 raw_tex 확장에 따라 매번
# `` `\은 `{=latex} `` 식으로 감싸 낸다 — 틀린 것은 아니지만(ndhmd4tex.py
# 로 다시 돌려도 결과는 같다), 조사가 문장마다 나오다 보니 원고 전체가
# raw 스팬 잡음으로 뒤덮여 정작 손봐야 할 곳을 찾기 어려워진다.
#
# 이 열 개를 벗겨서 원래 조사 매크로 표기 그대로 남긴다. 뒤에 남는 공백은
# 있으면 있는 대로, 없으면 없는 대로 그대로 보존한다 — 한글 매크로
# (`\은` 등)는 LaTeX에서 매크로 이름과 뒤따르는 한글을 가르는 경계로 공백이
# 실제로 필요하지만(kotex/luatexko 계열이 한글 음절에도 "letter" catcode를
# 주므로, 공백이나 `{}` 없이 붙이면 뒤 글자까지 매크로 이름에 먹혀버린다),
# `\<`는 특수문자라 그 경계가 저절로 생겨 원고에 공백을 안 둔 채 쓰는
# 경우가 흔하다(실측 확인: `` `\<`{=latex} ``, 공백 없음). 어느 쪽이든
# 원본에 있던 그대로를 pandoc이 raw 스팬 안에 고스란히 담아 오므로, 내용을
# 바꾸지 않고 백틱 감싸기만 벗기면 된다.
#
# `으로`를 `로`보다 먼저 적어둔 것은 가독성을 위한 것일 뿐 정규식 동작에는
# 영향이 없다 — 매치는 그 자리에서 시작하는 정확한 문자열만 성립하므로
# (`\으로`의 `으` 위치에서 `로`라는 대안은 애초에 후보가 되지 않는다),
# 순서를 바꿔도 결과는 같다.

_JOSA_RAW_RE = re.compile(
    r"`(\\(?:은|는|이|가|을|를|와|과|으로|로|<) ?)`\{=latex\}"
)


def unwrap_josa_raw_spans(text):
    return _JOSA_RAW_RE.sub(lambda m: m.group(1), text)


# ── 4.5. pandoc의 markdown 보호용 백슬래시 이스케이프 되돌리기 ────────
#
# pandoc은 자기가 만드는 markdown이 다시 markdown으로 안전하게 읽히도록
# `*` `_` `[` `]` 같은 markdown 특수문자를 `\*` `\_` 식으로 이스케이프해
# 내보낸다. 그런데 ndhmd4tex.py 는 이 관례를 모른다 — 백슬래시 자체를
# escape_chars 로 취급해 `\textbackslash{}`로 바꿔버리므로, 이스케이프된
# 문자가 오히려 깨진다(`\*` -> `\textbackslash{}*`). 그러니 pandoc이 보호
# 목적으로 붙인 단일 백슬래시는 여기서 미리 벗겨낸다.
#
# 실제 매크로 이름(`\ref`, `\alpha` 등)은 이미 백틱 raw 스팬 안에 있어
# 마스킹으로 보호되므로 이 치환의 대상이 되지 않는다. 벗겨내는 것은 "백슬래시
# 바로 뒤에 영숫자가 아닌 문장부호 한 글자"인 경우로 한정한다.
#
# 알려진 한계: 정말로 문장 안에 짝 맞는 `*`가 두 개 이상 우연히 있었고
# 그것이 강조로 의도된 게 아니었다면, 벗겨낸 뒤 ndhmd4tex가 그 둘을
# 강조로 잘못 묶을 수 있다. 흔치 않은 경우이고, 사람이 훑어보며 고칠
# "손볼 거리"로 남겨둔다(변환기 자체 주석에도 이 사실을 적어 둔다).

_PANDOC_ESCAPE_RE = re.compile(r"\\([^\w\s])")


def unescape_pandoc_markdown(text):
    return _PANDOC_ESCAPE_RE.sub(lambda m: m.group(1), text)


# ── 4.6. 들여쓴 코드블록 -> 펜스드 코드블록 ────────────────────────────
#
# `\begin{verbatim}` 등은 pandoc이 4칸 들여쓰기 코드블록으로 내놓는데,
# ndhmd4tex.py 는 펜스(```)만 코드블록으로 인식한다(10장). 빈 줄로 둘러싸인,
# 모든 줄이 4칸 이상 들여써진 블록을 찾아 펜스로 감싼다.


def convert_indented_code_blocks(text):
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("    ") and ln.strip() and (
            not out or out[-1].strip() == ""
        ):
            block = []
            while i < len(lines) and (
                lines[i].startswith("    ") or not lines[i].strip()
            ):
                if not lines[i].strip() and (
                    i + 1 >= len(lines) or not lines[i + 1].startswith("    ")
                ):
                    break
                block.append(lines[i][4:] if lines[i].startswith("    ") else "")
                i += 1
            while block and block[-1] == "":
                block.pop()
            out.append("```")
            out.extend(block)
            out.append("```")
            continue
        out.append(ln)
        i += 1
    return "\n".join(out)


# ── 4.7. 표 헤더 승격 ──────────────────────────────────────────────────
#
# 원본 LaTeX 표에 \toprule/\midrule 같은 구분 표시가 없으면 pandoc은 어느
# 행이 헤더인지 알 길이 없어 빈 헤더 행을 새로 지어 넣는다:
#
#   |      |      |
#   |:-----|:-----|
#   | 이름 | 나이 |
#   | 철수 | 20   |
#
# 십중팔구 원저자는 "이름/나이"를 헤더로 의도했을 것이므로, 빈 헤더 행을
# 지우고 그 다음 데이터 행을 헤더로 승격한다. 헤더가 진짜로 비어 있는
# (드문) 경우까지 완벽하게 구분할 수는 없다 — 이것도 훑어볼 거리 중 하나다.

_EMPTY_HEADER_RE = re.compile(r"^\s*(\|\s*)+\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def promote_table_headers(text):
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        if (
            _EMPTY_HEADER_RE.match(lines[i])
            and i + 2 < len(lines)
            and _TABLE_SEP_RE.match(lines[i + 1])
            and "|" in lines[i + 2]
        ):
            out.append(lines[i + 2])  # 데이터 첫 행을 헤더로
            out.append(lines[i + 1])  # 구분선은 그대로
            i += 3
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


# ── 4.8. 블록 경계에 빈 줄 보정 ────────────────────────────────────────
#
# ndhmd4tex.py 는 헤딩이 앞뒤로 빈 줄에 둘러싸인 **한 줄짜리 독립 블록**일
# 것을 엄격히 요구한다(3장) — 이건 이번 대화 내내 --lint가 가장 많이 잡아온
# 실수이기도 하다. 그런데 pandoc은 raw 블록(```` ```{=latex} ... ``` ````)
# 바로 뒤에 헤딩이 오는 경우 그 사이에 빈 줄을 넣지 않는 특이 동작이 있다
# (실측 확인). 그 상태로 두면 헤딩 줄이 앞 문단에 파묻혀 평문으로 남고,
# 오류 없이 조용히 헤딩 자체가 사라진다 — 정확히 이 스크립트가 피하려는
# 종류의 실패다.
#
# 그래서 펜스(```)와 헤딩(#...) 둘레에 빈 줄이 있는지 다시 훑어 없으면
# 채워 넣는다. 커스텀 환경(:::)은 다루지 않는다 — pandoc 자신이 만드는
# fenced div는 실측상 이미 빈 줄로 잘 감싸여 나온다.

_HEADING_LINE_RE = re.compile(r"^#{1,6}\s")
_FENCE_LINE_RE = re.compile(r"^```")


def ensure_block_blank_lines(text):
    lines = text.split("\n")
    out = []
    in_fence = False
    for i, ln in enumerate(lines):
        is_fence_line = bool(_FENCE_LINE_RE.match(ln))
        is_heading = (not in_fence) and bool(_HEADING_LINE_RE.match(ln))

        needs_blank_before = is_heading or (is_fence_line and not in_fence)
        if needs_blank_before and out and out[-1].strip() != "":
            out.append("")

        out.append(ln)

        if is_fence_line:
            in_fence = not in_fence

        just_closed_fence = is_fence_line and not in_fence
        if (is_heading or just_closed_fence) and i + 1 < len(lines) \
                and lines[i + 1].strip() != "":
            out.append("")

    return "\n".join(out)


# ── 4.9. 느슨한 리스트를 다시 촘촘하게 ────────────────────────────────
#
# pandoc은 LaTeX itemize/enumerate 를 원문에 항목 사이 빈 줄이 없어도
# 습관적으로 "느슨한(loose) 리스트"로 내보낸다 — 각 `\item`을 별개 문단으로
# 감싸 항목 사이에 빈 줄을 넣는다(실측 확인). 그런데 ndhmd4tex.py는 리스트
# 항목 사이 빈 줄을 "리스트가 거기서 끝났다"는 뜻으로 읽으므로, 원래 하나였던
# 리스트가 여러 개의 별도 리스트로 쪼개진다 — 오류 없이 조용히 벌어지는
# 실패라 특히 위험하다. 같은 마커(`-`/`*`/`+`/숫자)의 항목이 빈 줄 하나만
# 사이에 두고 연달아 있으면 그 빈 줄을 지워 다시 하나의 리스트로 합친다.

_LIST_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s")


def collapse_loose_lists(text):
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        m1 = _LIST_ITEM_RE.match(lines[i])
        if (
            m1
            and i + 2 < len(lines)
            and lines[i + 1].strip() == ""
        ):
            m2 = _LIST_ITEM_RE.match(lines[i + 2])
            if m2 and m1.group(2)[:1].isdigit() == m2.group(2)[:1].isdigit():
                out.append(lines[i])
                i += 2  # 빈 줄을 건너뛴다
                continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


# ── 4.10. 표 + 캡션을 `:::{table}` 로 묶기 ─────────────────────────────
#
# ndhmd4tex.py 의 파이프 표 문법 자체에는 캡션을 붙일 자리가 없다 — 캡션이
# 붙은 뜬다니는 표를 만들려면 `:::{table caption="...", label="..."}`
# 환경으로 감싸야 한다(17.1장). pandoc은 캡션이 있는 표를 두 가지 형태로
# 낸다.
#
#   (a) \label 이 없으면: 표 바로 뒤에 `: 캡션` 줄만 붙는다.
#   (b) \label 이 있으면: 표+캡션 전체를 `::: {#id} ... :::` 로 감싼다
#       (convert_fenced_divs 를 거치면 `:::{div label="id"} ... :::` 형태가
#       된다 — pandoc이 이름을 안 주므로 "div"로 떨어진다).
#
# 어느 쪽이든 손대지 않으면 `: 캡션` 줄이 그냥 리터럴 텍스트로 남고 표에는
# 캡션이 전혀 붙지 않는다 — 원본 정보가 눈에 안 띄게 사라지는 조용한 손실
# 이라 반드시 고쳐야 한다. 이 함수는 convert_fenced_divs 다음에 실행되어야
# 한다(케이스 b가 이미 `:::{...}` 형태로 정규화된 뒤여야 파싱이 쉽다).

_TABLE_CAPTION_LINE_RE = re.compile(r"^:\s+(.*)$")
_NDHMD_DIV_OPEN_RE = re.compile(r"^:::\{([^}]*)\}\s*$")


def convert_table_captions(text):
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        # (b) 이미 :::{...} 로 감싸진 경우
        div_m = _NDHMD_DIV_OPEN_RE.match(lines[i])
        if div_m:
            j = i + 1
            content = []
            while j < len(lines) and lines[j].strip() != ":::":
                content.append(lines[j])
                j += 1
            if j < len(lines):
                k = len(content) - 1
                while k >= 0 and content[k].strip() == "":
                    k -= 1
                cap = None
                if k >= 0:
                    cm = _TABLE_CAPTION_LINE_RE.match(content[k])
                    if cm:
                        cap = cm.group(1).strip()
                        content = content[:k]
                        while content and content[-1].strip() == "":
                            content.pop()
                if cap is not None and any("|" in ln for ln in content):
                    # 첫 토큰(pandoc이 못 지어준 이름, 보통 "div")은 버리고
                    # 나머지 속성(대개 label=...)만 살려 table 로 다시 짓는다.
                    parts = div_m.group(1).split(None, 1)
                    rest = parts[1] if len(parts) > 1 else ""
                    attrs = f'caption="{cap}"' + (f", {rest}" if rest else "")
                    out.append(f":::{{table {attrs}}}")
                    out.extend(content)
                    out.append(":::")
                    i = j + 1
                    continue
        # (a) 감싸지 않고 표 바로 뒤에 캡션 줄만 있는 경우
        if "|" in lines[i]:
            j = i
            tbl = []
            while j < len(lines) and "|" in lines[j]:
                tbl.append(lines[j])
                j += 1
            k = j
            while k < len(lines) and lines[k].strip() == "":
                k += 1
            if k < len(lines):
                cm = _TABLE_CAPTION_LINE_RE.match(lines[k])
                if cm:
                    cap = cm.group(1).strip()
                    out.append(f':::{{table caption="{cap}"}}')
                    out.extend(tbl)
                    out.append(":::")
                    i = k + 1
                    continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


# --------------------------------------------------------------------------
# 5. 파이프라인 조립
# --------------------------------------------------------------------------

_BODY_TRANSFORMS = [
    convert_raw_fence_tags,
    convert_figure_divs,
    convert_fenced_divs,
    convert_citations,
    convert_refcite_raw,
    convert_super_subscript,
]


def convert_body(markdown_body, math_store):
    text = markdown_body

    # 마스킹이 필요 없는 것부터: 이 넷은 raw 스팬 자체를 만들거나 인식하는
    # 단계라 순서가 중요하다(코드 스팬 마스킹 전에 raw 스팬 패턴을 인식해야
    # 하므로 여기서는 마스킹하지 않는다 — 이 함수들 스스로 백틱 스팬을
    # 대상으로 삼기 때문이다).
    for fn in _BODY_TRANSFORMS:
        text = fn(text)

    # 이제부터는 진짜 "아무 데나 있는 텍스트"를 건드리는 단계이므로
    # 코드/raw 스팬을 가린 채로 돌린다.
    text = with_masking(unescape_pandoc_markdown)(text)

    # 조사 매크로 벗기기는 반드시 이 unescape *뒤*에 온다. \< 처럼 매크로
    # 이름이 영문/기호 하나뿐인 경우, 벗겨내 백틱을 없애고 나면 bare한
    # `\<` 텍스트가 남는데, 이걸 unescape 보다 먼저 해버리면 그 다음에
    # 도는 unescape_pandoc_markdown이 이걸 "pandoc이 붙인 markdown 보호용
    # 백슬래시"로 오인해서 도로 벗겨버린다(`\<` -> `<`, 백슬래시가 통째로
    # 사라짐 — 실측으로 확인한 버그). 한글 조사(`\은` 등)는 뒤 글자가
    # 유니코드 문자라 unescape_pandoc_markdown의 "단어문자 아님" 조건에
    # 안 걸려 우연히 안전했지만, `\<`처럼 뒤가 특수문자인 경우는 정확히
    # 그 조건에 걸린다. unescape가 끝난 뒤에 벗기면 이 문제 자체가
    # 생기지 않는다.
    text = unwrap_josa_raw_spans(text)

    text = convert_table_captions(text)
    text = collapse_loose_lists(text)
    text = convert_indented_code_blocks(text)
    text = promote_table_headers(text)
    text = ensure_block_blank_lines(text)

    text = restore_math_envs(text, math_store)
    return text


def convert(tex_text, cwd):
    tex_with_placeholders, math_store = extract_math_envs(tex_text)
    pandoc_out = run_pandoc(tex_with_placeholders, cwd)
    fm_text, body = split_pandoc_output(pandoc_out)
    front_matter = build_front_matter(fm_text)
    body = convert_body(body, math_store)
    body = body.strip("\n") + "\n"
    return front_matter + "\n" + body


# --------------------------------------------------------------------------
# 6. CLI
# --------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(
        description="LaTeX 문서를 ndhmd4tex.py 가 읽을 수 있는 ndhmd 초안으로 "
                    "변환한다. 100%% 무손실이 아니라 '거의 손대지 않아도 될 "
                    "정도'가 목표다. 변환 후 --lint 로 점검할 것을 권한다."
    )
    ap.add_argument("input", help="입력 .tex 파일")
    ap.add_argument("-o", "--output", metavar="파일",
                    help="출력 .md 파일 (기본: 표준출력)")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.is_file():
        print(f"오류: 파일을 찾을 수 없습니다: {src}", file=sys.stderr)
        sys.exit(1)

    tex_text = src.read_text(encoding="utf-8", errors="replace")
    result = convert(tex_text, cwd=src.parent)

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
        print(f"변환 완료: {args.output}", file=sys.stderr)
        print(
            "  기계 변환 초안입니다. 다음을 사람이 확인하십시오:\n"
            "  - front matter의 class/toplevel\n"
            "  - 표 헤더가 제대로 승격됐는지\n"
            "  - `\\textsuperscript`/`\\textsubscript` 로 바뀐 자리\n"
            "  - `python3 ndhmd4tex.py 출력.md --lint` 로 마크업 실수 점검",
            file=sys.stderr,
        )
    else:
        print(result)


if __name__ == "__main__":
    main()
