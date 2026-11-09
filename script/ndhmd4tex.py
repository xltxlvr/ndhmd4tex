#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ndhmd4tex.py — ndhmarkdown -> LaTeX 변환기
#
# Copyright (c) 2026 Nova de Hi
# Licensed under the MIT License. See LICENSE for details.

import argparse
import copy
import itertools
import re
import sys
import os
import subprocess
import shlex
import shutil
import hashlib
import urllib.request
import urllib.parse
import time
import unicodedata
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("이 스크립트는 PyYAML이 필요합니다:  pip install pyyaml")

__version__ = "0.20.4"

# --------------------------------------------------------------------------
# 0. 보호(placeholder) 메커니즘
# --------------------------------------------------------------------------

_PH_OPEN = "\uE000"
_PH_CLOSE = "\uE001"
# 플레이스홀더는 "<보호기 id>-<저장 인덱스>" 형태로 인코딩한다.
# 예전에는 인덱스만 사용했는데, 이 경우 서로 다른 Protector 인스턴스(예: 블록 단위의
# 전역 pr 과 process_inline() 안에서 매번 새로 만드는 local)가 우연히 같은 인덱스를
# 가지면 restore() 가 남의 보호 내용을 대신 복원해버리는 충돌이 발생했다.
# (예: 문단 중간에 섞인 $$...$$ 블록이 pr 로 index 0 을 부여받았는데, 같은 문단의
#  인라인 수식 $x$ 가 local 에서도 index 0 을 부여받으면 local.restore() 가 pr 의
#  플레이스홀더까지 잘못 치환해버림.)
_PH_RE = re.compile(_PH_OPEN + r"(\d+)-(\d+)" + _PH_CLOSE)
_protector_id_counter = itertools.count()

# render_paragraph()가 실행되는 시점(문단의 여러 줄을 한 줄로 접는 단계)에는
# protect_block_level()이 이미 코드펜스/디스플레이 수식/수식·표 환경/HTML
# 주석을 전부 "그 줄 하나만 통째로 차지하는" 플레이스홀더로 압축해 둔 뒤다.
# 반면 인라인 코드·인라인 수식은 아직 process_inline()을 안 거쳐서 원본
# 그대로(백틱/$ 등) 남아 있다 — 즉 "이 줄 전체가 정확히 플레이스홀더
# 하나뿐인가"는 이 시점에서 "블록 레벨에서 보호된 내용인가"와 사실상 같은
# 뜻이다. 이 정규식은 그 판별에 쓴다.
_BLOCK_PLACEHOLDER_ONLY_RE = re.compile(r"^" + _PH_OPEN + r"\d+-\d+" + _PH_CLOSE + r"$")


# --------------------------------------------------------------------------
# --syncinfo 를 위한 줄 번호 추적
# --------------------------------------------------------------------------
#
# ndhmd4tex.py 의 본문 처리는 "여러 줄을 자리표시자 하나로 축약"하는 단계가
# 여러 번 있다(코드펜스, 별행수식/표 환경의 raw 보호, 각주 정의 추출 등).
# --syncinfo 는 "최종 .tex 의 이 줄이 원본 .md 의 몇 번째 줄이었나"를 알아야
# 하는데, 이걸 위해 텍스트 처리 로직 자체를 바꾸는 것은 위험하다 — 실제로
# 시도해보니(코드펜스가 사라진 자리를 빈 줄로 채워 줄 수를 유지하는 방식)
# 리스트 항목 바로 뒤에 빈 줄 없이 여러 줄짜리 코드펜스가 오는 경우 새로
# 생긴 빈 줄 때문에 리스트가 쪼개지는 회귀가 실제로 발생했다.
#
# 그래서 텍스트 처리 로직은 한 글자도 바꾸지 않고, 각 축약 단계가 "이전
# 단계 기준으로 몇 번째~몇 번째 줄이 몇 줄로 줄었는지"만 옆에서 기록하게
# 한다. LineOriginMap 이 그 기록들을 순서대로 받아 누적 적용하면서,
# "지금 시점 텍스트의 각 줄이 최초 원본의 몇 번째 줄이었나"를 계속
# 갱신해 나간다.
class LineOriginMap:
    def __init__(self, initial_origin):
        # origin[i] = 지금 시점 텍스트의 i번째 줄(0-based)이 가리키는,
        # "그 앞 단계" 기준 위치. 단일 파일일 때는 그냥 정수(0-based 줄
        # 번호)면 충분하지만, {{포함}}이 섞이면 "어느 파일의 몇 번째
        # 줄인지"를 같이 담아야 하므로 (파일경로, 줄번호) 튜플을 넣을 수도
        # 있다. apply_shrink()/resolve() 는 이 값을 그대로 복사하기만 할
        # 뿐 내용을 들여다보지 않으므로, 정수든 튜플이든 그대로 동작한다.
        # 항등 매핑으로 시작하려면 range(n_lines)를 그대로 넘기면 된다.
        self.origin = list(initial_origin)

    def apply_shrink(self, events):
        """events: [(start, end, new_len), ...]. "지금 시점 기준 줄 인덱스
        [start, end) 구간이 new_len 줄로 줄었다"는 기록의 리스트. start 순으로
        정렬되어 있고 서로 겹치지 않는다고 가정한다. 이 함수를 호출한 뒤에는
        self.origin 이 "축약 후 텍스트의 각 줄" 기준으로 다시 채워진다.

        축약된 구간을 대표하는 origin 값은 그 구간의 **첫 줄**의 origin이다.
        여는 펜스/블록 시작 줄이 곧 자리표시자가 놓이는 자리이므로, 자리
        표시자로 사용자를 안내했을 때 "그 블록이 시작하는 지점"으로 가는
        것이 가장 자연스럽다.
        """
        if not events:
            return
        new_origin = []
        ev_i = 0
        i = 0
        n = len(self.origin)
        while i < n:
            if ev_i < len(events) and events[ev_i][0] == i:
                start, end, new_len = events[ev_i]
                rep = self.origin[start]
                new_origin.extend([rep] * new_len)
                i = end
                ev_i += 1
            else:
                new_origin.append(self.origin[i])
                i += 1
        self.origin = new_origin

    def resolve(self, line_idx):
        """지금 시점 텍스트의 line_idx(0-based) 줄이 최초 원본의 몇 번째
        줄(0-based)이었는지 돌려준다(단일 파일) — 또는 {{포함}}이 섞인
        경우 (파일경로, 줄번호) 튜플. 범위를 벗어난 인덱스가 들어오는 것은
        호출부의 버그이니(apply_shrink가 항상 원본과 같은 길이를 유지하는
        한 일어날 수 없다), 그 경우에도 무너지지 않도록 인덱스 자체를
        그대로 돌려주는 안전망만 둔다.
        """
        if 0 <= line_idx < len(self.origin):
            return self.origin[line_idx]
        return line_idx


def _line_events_for_full_line_matches(text, pattern, new_len):
    """패턴 매치가 그 줄(들)을 통째로(처음부터 끝까지) 차지하는 경우에만
    (start, end, new_len) 이벤트를 만든다. 매치 앞뒤로 같은 줄에 다른
    텍스트가 남아 있으면(문장 중간에 낀 인라인 주석·인라인 수식 등) 그
    매치는 줄 수 자체를 바꾸지 않으므로 이벤트를 만들지 않는다 — 안
    만드는 것이 정답이다, 그 줄은 원래 있던 자리에 그대로 있으니까.

    매치 문자열 자신이 그 마지막 줄을 끝내는 개행 문자까지 삼켰다면
    (LINECOMMENT_RE처럼 정규식 자체에 `\\n?`을 넣어 둔 경우), 그 개행은
    "다음 줄로 넘어가는 구분자"가 아니라 "그 줄 자신을 마무리하는
    문자"이므로 두 곳에서 각각 보정해야 한다 — 둘 다 빠뜨리면 실제로
    겪은 것처럼 이벤트 자체가 통째로 안 만들어지거나(아래), 만들어져도
    줄 수가 하나 더 많게 계산된다:

    1. "그 줄의 끝(line_end)"을 찾을 때: 매치가 이미 그 개행을 삼켰다면
       m.end()는 이미 다음 줄의 시작이다. 이 사실을 모른 채 m.end()부터
       또 다음 개행을 찾으면, 그 다음 줄(원래는 무관한 줄)의 끝을
       "이 줄의 끝"으로 잘못 잡는다 — 그러면 that 다음 줄의 내용이
       고스란히 after에 섞여 들어가 "매치 뒤에 다른 텍스트가 있다"고
       오판하고, 그 줄 전체를 차지한 게 분명한 매치인데도 이벤트를
       아예 만들지 않는다(실제로 LINECOMMENT_RE에서 겪은 버그 — 트랜스
       클루전된 서브파일 안 라인 코멘트가 origin 축약에서 통째로
       빠져서, 그 이후 모든 origin이 계속 한 줄씩 밀렸다).
    2. "차지한 줄 수(end_line)"를 셀 때: 매치 안의 개행 개수를 그대로
       줄 수로 쓰면, 매치 자신을 마무리한 개행까지 "다음 줄로 넘어간
       것"으로 잘못 세어 실제보다 한 줄 더 차지한 것으로 계산된다.

    COMMENT_RE/MATH_ENV_RE/TABLE_ENV_RE/DISPLAY_MATH_RE는 전부 `-->`,
    `}`, `$$`, `\\]`처럼 개행이 아닌 문자로 끝나는 매치만 만들어서 이
    문제가 애초에 없다 — 그래도 이 함수 자체는 "매치가 개행으로
    끝나는가"만 보고 두 곳 모두 일관되게 보정하므로, 앞으로 개행으로
    끝나는 새 패턴이 추가돼도 자동으로 안전하다.
    """
    events = []
    for m in pattern.finditer(text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        match_text = text[m.start():m.end()]
        ends_with_newline = match_text.endswith("\n")
        if ends_with_newline:
            # 매치 자신이 이미 그 줄의 개행을 삼켰다 — m.end()는 벌써
            # 다음 줄의 시작이므로, "이 줄의 끝"은 그 개행 바로 앞이다.
            line_end = m.end() - 1
        else:
            nxt = text.find("\n", m.end())
            line_end = nxt if nxt != -1 else len(text)
        before = text[line_start:m.start()]
        after = text[m.end():line_end]
        start_line = text.count("\n", 0, line_start)
        newline_count = match_text.count("\n")
        if ends_with_newline:
            newline_count -= 1
        end_line = start_line + newline_count + 1
        if before.strip() == "" and after.strip() == "":
            events.append((start_line, end_line, new_len))
        elif newline_count > 0:
            # 매치 앞/뒤에 같은 줄 텍스트가 남아 있어도(`{\small\begin{tblr}`
            # 처럼 앞에 붙거나 `\end{tblr} 뒤에 글`처럼 뒤에 붙는 경우), 매치
            # 안에 개행이 있으면 여러 줄이 한 줄(앞 텍스트+자리표시자+뒤
            # 텍스트)로 합쳐진다 — 줄 수가 실제로 줄어드는 것이다. 이때
            # 이벤트를 안 만들면 origin이 합쳐지기 전 줄 수 그대로 남아서
            # 그 뒤의 모든 위치가 (합쳐진 줄 수 - 1)만큼 계속 밀린다.
            # 한 줄은 앞/뒤 텍스트 때문에 반드시 남으므로 new_len은 1이다.
            # (한 줄 안에서 끝나는 매치는 줄 수를 안 바꾸니 이벤트가 없다.)
            events.append((start_line, end_line, 1))
    # 같은 줄을 공유하는 두 매치(`\end{tblr}\begin{tblr}`처럼 한 줄에서
    # 맞물리는 경우)는 구간이 겹친다 — apply_shrink는 겹치지 않는 이벤트를
    # 가정하므로 하나의 구간으로 합친다(공유된 줄이 남으니 new_len은 1).
    merged = []
    for ev in events:
        if merged and ev[0] < merged[-1][1]:
            ps, pe, _ = merged[-1]
            merged[-1] = (ps, max(pe, ev[1]), 1)
        else:
            merged.append(ev)
    return merged


class Protector:
    def __init__(self):
        self.id = next(_protector_id_counter)
        self.store = []

    def protect(self, raw: str) -> str:
        idx = len(self.store)
        self.store.append(raw)
        return f"{_PH_OPEN}{self.id}-{idx}{_PH_CLOSE}"

    def restore(self, text: str) -> str:
        def _sub(m):
            pid, idx = int(m.group(1)), int(m.group(2))
            if pid != self.id:
                # 다른 Protector 인스턴스가 심어놓은 플레이스홀더는 건드리지 않는다.
                return m.group(0)
            if idx < len(self.store):
                return self.store[idx]
            return m.group(0)

        prev = None
        while prev != text:
            prev = text
            text = _PH_RE.sub(_sub, text)
        return text


# --------------------------------------------------------------------------
# 1. 기본 설정값 (외부 mapping.yaml 로 override/추가 가능)
# --------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "headings": {
        1: "chapter",
        2: "section",
        3: "subsection",
        4: "subsubsection",
        5: "paragraph",
        6: "subparagraph",
    },
    "inline": [
        {"name": "bold_italic", "pattern": r"\*\*\*(.+?)\*\*\*", "template": r"\textbf{\emph{%s}}"},
        {"name": "bold", "pattern": r"\*\*(.+?)\*\*", "template": r"\textbf{%s}"},
        {"name": "italic", "pattern": r"\*(.+?)\*", "template": r"\emph{%s}"},
        {"name": "strike", "pattern": r"~~(.+?)~~", "template": r"\sout{%s}"},
        # ^^방점^^ -> \dotemph{...} (전통 한국어 편집물의 방점 표시).
        # preamble에 \dotemph를 정의해둬야 한다(예: \newcommand{\dotemph}[1]{...}).
        {"name": "emphdot", "pattern": r"\^\^(.+?)\^\^", "template": r"\dotemph{%s}"},
    ],
    # ── 커스텀 환경 (:::{name}) ────────────────────────────────────
    # default는 등록되지 않은 이름에 쓰이는 폴백이다.
    #
    # table/figure를 기본 제공하는 이유: :::{table place=... caption=...}은
    # 누구나 그렇게 쓸 거라고 기대하는 형태인데, 등록돼 있지 않으면 default
    # 템플릿이 걸려 속성이 전부 버려진다. 떠다니는 상자는 place/caption/
    # label/align 조합이 사실상 고정이라 기본값으로 넣어둘 만하다.
    # 캡션 위치가 다르다 — 표는 내용 위(begin), 그림은 내용 아래(end)가
    # 관례이므로 그렇게 배치했다.
    "environments": {
        "default": {"begin": r"\begin{%(name)s}%(raw)s", "end": r"\end{%(name)s}"},
        "quote": {"begin": r"\begin{quote}", "end": r"\end{quote}"},
        "center": {"begin": r"\begin{center}", "end": r"\end{center}"},
        "table": {
            "begin": (
                "\\begin{table}[%(place|htbp)s]\n"
                "?%(align|\\centering)s\n"
                "?\\caption{%(caption)s}\n"
                "?\\label{%(label)s}"
            ),
            "end": r"\end{table}",
        },
        # \begin{thebibliography}{...} 의 인자는 "가장 넓은 라벨"이다.
        # raw={99} 로도 되지만 이름 있는 속성이 덜 헷갈린다.
        # 운문. 행 구조를 원문 그대로 넘긴다(lines: keep).
        # hverse 는 oblivoir-misc 가 제공하며 행 끝에 \\ 를 요구하지 않는다.
        # 표준 verse 는 요구하므로 line_end 로 붙여 준다.
        "hverse": {
            "begin": r"\begin{hverse}",
            "end": r"\end{hverse}",
            "lines": "keep",
        },
        "verse": {
            "begin": r"\begin{verse}",
            "end": r"\end{verse}",
            "lines": "keep",
            "line_end": r" \\",
        },
        "thebibliography": {
            "begin": r"\begin{thebibliography}{%(widest|99)s}",
            "end": r"\end{thebibliography}",
        },
        "figure": {
            "begin": (
                "\\begin{figure}[%(place|htbp)s]\n"
                "?%(align|\\centering)s"
            ),
            "end": (
                "?\\caption{%(caption)s}\n"
                "?\\label{%(label)s}\n"
                "\\end{figure}"
            ),
        },
    },
    # [prefix라벨] 형태의 상호참조/인용 문법. 키는 대괄호 안 라벨 앞에 붙는
    # 프리픽스 문자열, 값은 %s에 라벨이 들어가는 LaTeX 템플릿이다. 책마다
    # 참조 매크로 이름을 다르게 쓰고 싶으면(예: \nameref 대신 직접 정의한
    # \hbref) mapping.yaml에서 해당 항목만 override하면 된다:
    #   refcite:
    #     "name:": '\hbref{%s}'
    # title:/name:은 결과적으로 거의 같은 것을 가리키지만(둘 다 "제목
    # 참조"), 편집 관행상 별도 매크로 이름으로 구분해 쓰는 경우가 있어
    # 둘 다 기본 제공한다. name:은 hyperref가 제공하는 표준 \nameref를
    # 쓰고, title:은 \titleref처럼 프로젝트에서 직접 정의해 쓰는 매크로를
    # 가정한다(마치 \dotemph처럼 — preamble에 정의 필요).
    # C:는 cleveref의 \Cref이다(preamble에 \usepackage{cleveref} 필요).
    # 여러 라벨을 한 번에 참조하고 싶으면 cleveref가 콤마 구분을 그대로
    # 지원하므로 [C:sec:a,sec:b] -> \Cref{sec:a,sec:b}가 별도 처리 없이
    # 그냥 동작한다. \crefrange{a}{b}처럼 인자가 둘로 나뉘는 "범위" 참조는
    # 이 대괄호 문법으로 지원하지 않는다 — 7장의 raw 매크로 통과 규칙 덕분에
    # 본문에 \crefrange{sec:a}{sec:b}를 직접 써도 그대로 통과하므로 새
    # 문법을 얹을 실익이 적다.
    "refcite": {
        "#": r"\ref{%s}",
        "page:": r"\pageref{%s}",
        "@": r"\cite{%s}",
        # natbib/biblatex 계열. 단행본에서는 본문 흐름에 저자를 끌어들이는
        # \citet 과 괄호 안에 넣는 \citep 의 구분이 사실상 필수다.
        # 프리픽스는 쓰일 때만 발동하므로 natbib을 안 쓰는 문서에는 부담이
        # 없다. 페이지 지정처럼 인자가 붙는 형태는 이 축약형으로 감당하지
        # 않는다 — \citep[p.~33]{key} 라고 직접 쓰면 매크로 규칙으로 그대로
        # 통과한다.
        "@t:": r"\citet{%s}",
        "@p:": r"\citep{%s}",
        "@a:": r"\citeauthor{%s}",
        "@y:": r"\citeyear{%s}",
        # amsmath의 수식 참조. 괄호까지 붙여 (1) 처럼 나온다.
        # 기본 헤더가 amsmath를 부르므로 웬만하면 그냥 쓸 수 있다.
        #
        # 프리픽스를 "eq:" 가 아니라 "E:" 로 둔 이유: 프리픽스는 라벨에서
        # 잘려나가므로, "eq:" 로 두면 관례대로 이름 붙인 \label{eq:c} 를
        # 가리키려고 [eq:c] 라 쓴 것이 \eqref{c} 가 되어버린다. 제대로
        # 쓰려면 [eq:eq:c] 라고 겹쳐 적어야 하는데 그럴 이유가 없다.
        "E:": r"\eqref{%s}",
        # \fref / \tref (memoir) 를 흉내낸 것. 참조할 때마다 "그림", "표"를
        # 손으로 적는 수고를 던다. \figurename / \tablename 은 어느 클래스나
        # 정의하고 kotex·babel이 언어에 맞게 바꿔주므로, 한국어 문서에서는
        # cleveref(C:)보다 오히려 손이 덜 간다.
        # ~ 를 쓴 것은 이름과 번호 사이에서 줄이 갈리지 않게 하기 위해서다.
        "F:": r"\figurename~\ref{%s}",
        "T:": r"\tablename~\ref{%s}",
        "title:": r"\titleref{%s}",
        "name:": r"\nameref{%s}",
        "C:": r"\Cref{%s}",
    },
    # 인라인 raw 스팬 `...`{=포맷} 에서 "그대로 통과"로 인정할 포맷 이름.
    # 여기 없는 포맷(예: {=html})은 Pandoc과 마찬가지로 통째로 버려진다.
    "raw_inline_formats": ["latex", "tex", "raw"],
    # inline 규칙 **앞에** 덧붙일 규칙들. inline 은 리스트형이라 손대면 전체가
    # 교체되는데, 규칙 하나 더하자고 기본 다섯 개를 통째로 베껴 오는 것은
    # 번거롭고 기본값이 바뀌면 뒤처진다. 이 키는 기본 목록을 그대로 둔 채
    # 앞에 끼워 넣는다.
    #
    # 뒤가 아니라 앞인 이유: 인라인 규칙은 위에서부터 차례로 적용되므로
    # 긴 델리미터가 먼저 와야 한다. 예를 들어 ***...*** 규칙을 뒤에 붙이면
    # 그보다 앞선 **...** 가 먼저 먹어버려 아무 일도 일어나지 않는다.
    #
    # 반대로 기본 규칙보다 **짧거나 겹치는** 델리미터를 앞에 두면 기본 규칙을
    # 가려버린다(예: *...* 를 앞에 두면 **굵게** 가 깨진다). 새 델리미터를
    # 더할 때만 쓰고, 기존 것을 바꿀 때는 inline 자체를 override 할 것.
    "extra_inline": [],
    # > 로 시작하는 인용구가 쓸 환경.
    #
    # 인용 범위 안에 (처음과 끝을 뺀) 빈 줄이 하나라도 있으면, 즉 인용이 두
    # 문단 이상이면 blockquote_multi_env 를 쓴다. LaTeX의 관례가 그렇다 —
    # quote 는 문단 들여쓰기가 없어 짧은 한 문단 인용에 맞고, quotation 은
    # 각 문단의 첫 줄을 들여쓰므로 여러 문단짜리 긴 인용에 맞는다.
    #
    # 인용구 안의 빈 줄은 > 만 있는 줄로 적는다. 진짜 빈 줄은 블록 자체를
    # 끊어 인용구 두 개가 되어버린다.
    #
    # 둘을 같은 값으로 두면 이 구분이 사라진다(예전 동작).
    "blockquote_env": "quote",
    "blockquote_multi_env": "quotation",
    # 설명 리스트를 어느 표기까지 인정할지.
    #
    #   "both"   중괄호형 {용어} ::  설명  과 맨 표기 용어 :: 설명  둘 다
    #   "braces" 중괄호형만. 맨 표기를 만나면 경고를 찍고 평범한 문단으로 둔다
    #
    # 맨 표기는 산문에 우연히 " :: " 가 들어가면 오인식될 여지가 남는다.
    # 중괄호형은 줄 첫머리에 {..} 를 요구하고 :: 뒤에 공백/탭 두 개 이상을
    # 요구하므로 사실상 그 여지가 없다.
    #
    # 기본값을 "braces" 로 하지 않은 이유는, 이미 맨 표기로 쓰인 원고가
    # 조용히 평범한 문단으로 퇴화하는 것이 오인식보다 더 나쁘기 때문이다.
    # "braces" 로 바꾸면 그런 줄마다 경고가 나오므로 옮겨 적을 자리를 찾을
    # 수 있다.
    "description_syntax": "both",
    # front matter에 있는 "우리가 모르는 키"를 프리앰블에 매크로로 넘길 때
    # 붙일 접두사. theme: dark 이면 \def\NMtheme{dark} 이 만들어진다.
    #
    # multimarkdown은 접두사 없이 \def\theme{dark} 로 넘긴다. 그것은 위험하다 —
    # 원고에 흔히 쓰는 낱말이 그대로 제어열 이름이 되므로 클래스나 패키지의
    # 명령을 소리 없이 덮어쓸 수 있다. 접두사를 붙이면 충돌 가능성이 사실상
    # 사라지면서 쓸모는 그대로 남는다.
    #
    # 빈 문자열로 두면 이 기능을 끈다.
    "metadata_macro_prefix": "NM",
    # ![](x.png){inline, ...} 이 쓸 명령. 줄글 중간에 작은 그림을 끼울 때
    # 쓰는 inlinegraphicx 패키지가 제공한다. 로딩은 저자 몫이다.
    # inlinespec= 로 준 문자열은 이 명령의 대괄호 인자로 **그대로** 넘어간다.
    "inline_graphics_cmd": "inlinegraphics",
    # 떠다니지 않는 자리에 캡션만 다는 명령(capt-of 또는 caption 패키지).
    # \caption 은 float 안에서만 되지만 이것은 아무 데서나 된다.
    "captionof_cmd": "captionof",
    # \animategraphics 에 넘길 초당 프레임 수. GIF는 프레임마다 지연이 다를 수
    # 있지만 이 명령은 하나의 fps만 받으므로 원본 타이밍을 그대로 살릴 수 없다.
    "animation_fps": 10,
    # ![](x.png){wrap, ...} 이 쓸 환경 이름. 본문이 그림을 둘러싸게 하는
    # 것으로, wrapstuff 패키지가 제공한다. 패키지 로딩은 사용자 몫이다.
    #
    # 환경의 대괄호 인자는 wrapspec= 로 준 문자열을 **그대로** 넘긴다.
    # 이 스크립트가 해석하지 않으므로, 환경이 무엇을 받든 저자가 정한다.
    "wrap_env": "wrapstuff",
    # 마침표 세 개(...)를 바꿀 LaTeX. 마침표를 나란히 찍으면 간격이 붙어버려
    # 조판상 틀린 결과가 나오므로 줄임표 명령으로 바꾼다(multimarkdown과 같은
    # 처리다).
    #
    # 끝의 {} 는 장식이 아니라 필수다. 한글 음절이 letter(catcode 11)인 조판
    # 환경에서 \ldots이렇게 라고 쓰면 TeX이 \ldots이렇게 를 통째로 하나의
    # 제어열 이름으로 읽어 Undefined control sequence 를 낸다. {} 가 그 경계를
    # 끊는다.
    #
    # 한국어 조판에서 줄임표는 폰트에 따라 모양과 간격이 제각각이라, 명령을
    # 갈아끼울 수 있어야 한다. 흔히 쓰는 대안:
    #   '\dots{}'          amsmath. 앞뒤 문맥에 따라 간격을 조절한다
    #   '\textellipsis{}'  텍스트용 줄임표
    #   '……'                유니코드 줄임표 두 개. 한국어 전통 표기(6점)
    #   '\myellip{}'       프로젝트에서 직접 정의한 것
    # 빈 문자열로 두면 변환하지 않고 마침표 세 개를 그대로 내보낸다.
    "ellipsis": r"\ldots{}",
    # 물결표 정책(7.2). "default"면 ~ 와 \~ 를 둘 다 원문 그대로 LaTeX에
    # 넘긴다(옛 동작). 그 밖의 값을 주면 ~ 는 여전히 LaTeX의 묶음빈칸
    # (nobreak space)이고, \~ 는 이 값으로 바뀐다. 값은 세 가지 꼴이다.
    #   - 유니코드 코드포인트(16진수): FF5E, U+FF5E (따옴표를 권장)
    #   - 한 글자 그대로: "～"
    #   - LaTeX 매크로: \koreanWaveDash  (뒤에 {}가 자동으로 붙는다)
    "wavedash": "default",
    # ~ 와 ^ 의 해석 방언: latex(기본, ~ 는 묶음빈칸) | pandoc | multimarkdown
    "tilde": "latex",
    # 직선 따옴표를 무엇으로 바꿀까. tex(기본, ``..'' `..') / unicode(“..” ‘..’) /
    # 임의 문자: 2글자(큰따옴표 여닫이만, 작은따옴표는 tex 그대로) 또는 4글자
    # (큰따옴표 여닫이 + 작은따옴표 여닫이). 여러 글자짜리는 같은 길이의 리스트로.
    "quotes": "tex",
    # [[표시|색인어]] 색인 문법이 만들어낼 LaTeX. %(text)s 에 표시 텍스트가,
    # %(term)s 에 색인어가 들어간다.
    #
    # TeX의 \index 는 인자를 특수한 방식으로 읽는 프리미티브에 가까워서
    # 사용자가 재정의하기가 몹시 까다롭다. 그래서 명령 이름을 하드코딩하는
    # 대신 통째로 갈아끼울 수 있게 해두었다. 직접 정의한 매크로로 바꾸려면
    #   index_template: '%(text)s\myidx{%(term)s}'
    # 처럼 적는다. 인자를 둘 받는 매크로라면
    #   index_template: '\myidx{%(text)s}{%(term)s}'
    # 같은 것도 된다 — 표시 텍스트를 어디에 놓을지까지 템플릿이 정한다.
    #
    # 두 값 모두 이스케이프나 인라인 서식 처리를 거치지 않고 raw 그대로
    # 꽂힌다. makeindex가 \index 인자 안에서 !(계층), @(정렬키), |(서식)을
    # 특수하게 쓰기 때문에, 건드리면 그 문법을 못 쓰게 된다.
    "index_template": r"%(text)s\index{%(term)s}",
    # 정의를 찾을 수 없는 [^...] 를 "인라인 각주"로 볼지 여부.
    #
    # 각주 정의의 식별자는 [A-Za-z0-9_-]+ 로 제한돼 있다. 그래서 대괄호 안의
    # 내용이 그 모양이 아니거나 수집된 정의에 없으면, 그것은 참조일 수가
    # 없다 — 그 자리에서 각주 본문을 바로 적은 것으로 읽는다.
    #   [^각주 텍스트]  ->  \footnote{각주 텍스트}
    #
    # false로 두면 예전처럼 경고를 찍고 원문을 그대로 남긴다. 참조 식별자에
    # 오타를 냈을 때 [^ndh2024x] 같은 것이 조용히 각주로 둔갑하는 게 싫다면
    # 그 편이 안전하다.
    "inline_footnote": True,
    # 각주 종류 등록부. 본문에서 `^[...]{이름}` / `[^id]{이름}` 꼴의 꼬리표로
    # 고른다(꼬리표가 없으면 `default`). 값은 템플릿 문자열이다. 템플릿에는 %(text)s(각주 본문)와
    # %(opt)s(번호 지정 옵션 `[3]` 또는 빈 문자열)를 쓴다. 예전 꼴 `%s`
    # 하나만 써도 된다(본문). 사용자가 mapping에서 `notes:` 아래 항목을 더하면
    # 이 기본 항목과 합쳐진다(같은 이름은 덮어씀). `\footnoteA` 같은
    # 각주 계열은 프리앰블에 \newfootnoteseries{A} 가 있어야 한다.
    "notes": {
        "default": r"\footnote%(opt)s{%(text)s}",
        "side": r"\sidefootnote%(opt)s{%(text)s}",
        "page": r"\pagenote%(opt)s{%(text)s}",
        "sidepar": r"\sidepar{%(text)s}",
        "sidebar": r"\sidebar{%(text)s}",
        "verb": r"\verbfootnote%(opt)s{%(text)s}",
    },
    # 행 머리(들여쓰기 없이 정확히 첫 칸)에 // 로 시작하는 줄은 LaTeX
    # 사용자에게 익숙한 "라인 코멘트"로 통째로 지운다. 기본은 꺼져 있다
    # (false) — 코드 예제에 C/JS 류 // 주석이 자주 나오는데, 그게 들여쓰기
    # 없이 첫 칸부터 시작하는 경우와 겹칠 위험이 있어서다. 다만 코드
    # 펜스(```...```)는 이 검사보다 먼저 자리표시자로 보호되므로, 펜스
    # **안의** // 는 이 옵션을 켜도 절대 지워지지 않는다 — 위험한 것은
    # 오직 펜스 밖, 원고 본문에 우연히 첫 칸부터 // 로 시작하는 줄이
    # 있는 경우뿐이다(흔치 않다). 필요할 때만 mapping.yaml에서
    # linecomment: true 로 켤 것.
    "linecomment": False,
    # 파이프 표가 줄 폭을 넘칠 것 같으면 폭이 큰 열만 l/c/r 대신 X[l]/X[c]/X[r]
    # (tabularray의 자동 줄바꿈 열)로 바꾼다. 값은 "한 줄에 들어간다고 보는
    # 폭"이며 반 em 단위다(한글·CJK 한 글자=2, 그 밖은 1) — 70이면 한글
    # 약 35자. 표의 추정 폭이 이 값 이하이면 아무것도 바꾸지 않으므로(출력이
    # 이전과 완전히 같다) 기준이 좀 틀려도 경계 근처의 표만 영향을 받는다.
    # 0 또는 false 로 두면 이 기능을 끈다. mapping 키이며 front matter 키가
    # 아니다. X 열이 하나라도 있으면 tabularray는 표를 \linewidth 전체
    # 폭으로 늘리기 때문에, 넘치지 않는 표에는 일부러 적용하지 않는다.
    "tablewrap": 70,
    "verbatim_env": "verbatim",
    "codeblock_template": "\\begin{minted}{%(lang)s}\n%(body)s\n\\end{minted}",
    # ```showexam 블록: 왼쪽에 마크다운 원문(verbatim), 오른쪽에 그것을 변환한
    # 결과를 나란히 놓는다. LaTeX 쪽에서는 만들 수 없는 물건이라 스크립트가
    # 원문을 두 번 쓴다 — 한 번은 그대로, 한 번은 파이프라인에 다시 통과시켜서.
    #
    # 주의: verbatim/minted는 "매크로 인자" 안에서 깨진다. 그래서 template을
    # 고칠 때 왼쪽 상자를 \fbox{...}나 \parbox{...}로 감싸면 안 된다.
    # minipage는 인자가 아니라 환경 본문이라 안전하고, 테두리가 필요하면
    # minted의 frame= 옵션이나 tcolorbox/mdframed를 쓸 것.
    #
    # 펜스 줄에서 블록마다 덮어쓸 수 있다:
    #   ```showexam ratio=0.4 style=verbatim align=c lang=text frame=none
    "showexam": {
        "ratio": 0.46,   # 왼쪽(원문) 상자의 \linewidth 대비 폭
        "gap": 0.04,     # 두 상자 사이 여백. 오른쪽 폭 = 1 - ratio - gap
        "align": "t",    # minipage 세로 정렬: t / c / b
        # style은 아래 styles의 키를 고른다. 긴 줄이 상자 밖으로 삐져나오는지가
        # 실질적인 선택 기준이다:
        #   minted     — 줄바꿈됨. 예쁘지만 -shell-escape가 필요하고 느리다.
        #   lstlisting — 줄바꿈됨. listings 패키지만 있으면 되고 빠르다.
        #   verbatim   — 줄바꿈 안 됨(!). 추가 패키지가 필요 없는 대신,
        #                긴 줄은 오른쪽 상자를 뚫고 여백까지 넘어간다.
        "style": "minted",
        "lang": "markdown",
        # 원문 상자의 테두리. 기본 template은 테두리를 그리지 않으므로 listing이
        # 직접 그린다. 반대로 template을 tcolorbox처럼 "이미 테두리가 있는"
        # 것으로 바꾸면 상자 안에 상자가 겹치니, 그때는 frame: none으로 끈다.
        # single/none 외의 값(lines, leftline, shadowbox 등)은 minted와
        # lstlisting의 frame= 옵션에 그대로 전달된다.
        "frame": "single",
        # 배치: side(좌우, 기본) / stack(위아래) / auto.
        #   stack — 원문 상자를 본문 전체 폭으로 놓고 그 아래에 결과를 잇는다.
        #           minipage를 쓰지 않으므로 쪽 나눔이 가능하다. ratio/gap/align은
        #           의미가 없어 무시된다.
        #   auto  — 원문에서 가장 긴 줄의 표시 폭(한글 2칸)이 stack_width를
        #           넘으면 stack, 아니면 side. 실제 상자 폭은 용지·글꼴에 따라
        #           달라서 어림셈이다. 펜스 줄의 layout= 이 항상 우선한다.
        "layout": "side",
        "stack_width": 36,
        # stack 에서 원문과 결과 사이를 가르는 것: rule(기본) / space / none,
        # 또는 임의의 LaTeX 코드.
        "sep": "rule",
        "styles": {
            "minted": (
                "\\begin{minted}[%(frame)sbreaklines,breakanywhere,"
                "fontsize=\\small,xleftmargin=0pt]{%(lang)s}\n%(src)s\n\\end{minted}"
            ),
            "lstlisting": (
                "\\begin{lstlisting}[%(frame)sbreaklines=true,breakatwhitespace=false,"
                "basicstyle=\\ttfamily\\small,columns=fullflexible,"
                "aboveskip=0pt,belowskip=0pt,xleftmargin=0pt]\n"
                "%(src)s\n\\end{lstlisting}"
            ),
            # verbatim은 테두리를 그릴 수단이 없으므로 %(frame)s를 쓰지 않는다.
            "verbatim": "\\begin{verbatim}\n%(src)s\n\\end{verbatim}",
        },
        # %(left)s 원문 상자 / %(right)s 결과 상자 / %(lw)s %(rw)s 폭 / %(align)s 정렬.
        # 왼쪽에서 topsep·partopsep을 0으로 만드는 이유: verbatim과 minted는
        # 내부적으로 trivlist라서 상자 맨 위에 여분의 수직 여백을 얹는다.
        # 그대로 두면 [t] 정렬이 오른쪽 본문보다 한 줄쯤 내려앉는다.
        "template": (
            "\\par\\medskip\\noindent\n"
            "\\begin{minipage}[%(align)s]{%(lw)s\\linewidth}%(strut)s\n"
            "\\setlength{\\topsep}{0pt}\\setlength{\\partopsep}{0pt}\n"
            "%(left)s\n"
            "\\end{minipage}\\hfill\n"
            "\\begin{minipage}[%(align)s]{%(rw)s\\linewidth}%(strut)s\n"
            "\\setlength{\\topsep}{0pt}\\setlength{\\partopsep}{0pt}\n"
            "%(right)s\n"
            "\\end{minipage}\n"
            "\\par\\medskip"
        ),
        # stack 배치용. %(left)s 원문 / %(right)s 결과 / %(sep)s 구분.
        "stack_template": (
            "\\par\\medskip\\noindent\n"
            "%(left)s\n"
            "%(sep)s\n"
            "%(right)s\n"
            "\\par\\medskip"
        ),
    },
    # ~ 가 빠져 있는 것은 의도다. 원고의 ~ 와 \~ 는 둘 다 손대지 않고 그대로
    # LaTeX 소스에 내보내며, 그것이 묶음빈칸인지 물결표인지는 LaTeX 쪽
    # (문서 클래스나 조사/물결표 처리 패키지)이 정한다(7.2 참고).
    # 모든 ~ 를 \textasciitilde{}로 바꾸던 예전 동작이 필요하면 mapping.yaml
    # 에서 이 목록에 "~" 를 도로 넣으면 된다 — _ESCAPE_MAP에는 남아 있다.
    "escape_chars": ["\\", "&", "%", "#", "_", "$", "{", "}", "^"],
    # \<처럼 알파벳 이름이 아니라서 \[a-zA-Z]+ 매크로 이름 패턴에 안 걸리는
    # "리터럴" 매크로 토큰 목록이다. 한국어 조사 매크로(\는, \으로 등)도
    # 같은 이유로 여기 있다 — 한글 음절이라 이름 패턴에 안 걸리고, 문자
    # 클래스를 한글까지 그냥 열면(예: [a-zA-Z가-힣]+) "\는맛있다"처럼
    # 공백 없이 바로 이어 쓰는 실제 관례 때문에 뒤에 오는 일반 한글 단어까지
    # 매크로 이름으로 그리디하게 먹혀버리는 위험이 있어서, 정확한 리터럴
    # 목록으로만 인식한다. build_macro_re()가 매번 이 목록으로 정규식을
    # 새로 만들며, 프리픽스 충돌 방지를 위해 긴 토큰부터 매치하도록 자동
    # 정렬한다(\으로를 \로보다, \에서를 \에보다 먼저 두는 것과 같은 이유 —
    # 순서를 직접 맞출 필요는 없다). 이 기본 목록 자체를 바꾸고 싶으면
    # mapping.yaml에서 이 키를 통째로 override.
    #
    # \라/\이라가 기본값에 없는 이유: 이 조사는 실제 문장에서 홀로 끝나는
    # 일이 드물고 거의 언제나 보조사가 뒤에 덧붙는다(\이라고, \이라는,
    # \이라도, \이라서 …). 리터럴 목록은 "정확히 이 문자열"만 인식하므로
    # 그런 활용형을 규칙으로 감당할 수 없다. 필요하면 쓰는 활용형을 통째로
    # extra_macros에 등록하면 된다 — 길이 내림차순 정렬 덕분에
    #   extra_macros: ["\\이라고", "\\라고", "\\이라는", "\\라는"]
    # 처럼 적어두면 긴 것부터 정확히 매치된다.
    "literal_macros": [
        r"\은", r"\는", r"\이", r"\가", r"\을", r"\를", r"\와", r"\과",
        r"\으로", r"\로",
        r"\<",
    ],
    # 프로젝트별로 토큰 몇 개만 추가하고 싶을 때 쓰는 확장 지점.
    # literal_macros 기본값은 그대로 둔 채 mapping.yaml에 이 키만
    # 적어주면 된다:
    #   extra_macros: ["\\>", "\\|"]
    "extra_macros": [],
}


def deep_merge(base, override):
    result = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


# extra_inline 처럼 "여러 mapping 파일에 걸쳐 이어붙이는" 것이 자연스러운
# 키. deep_merge()의 기본 규칙(나중 파일이 이긴다, 리스트는 항목별로
# 합치지 않고 통째로 덮어쓴다)을 그대로 따르면, 이 키들은 나중 파일이
# 앞 파일 것을 완전히 지워 버려서 "여러 파일에 나눠 적은 확장 규칙을
# 다 모은다"는 mapping: 리스트의 취지 자체를 못 살린다. 그래서 이 키만
# 예외로, 덮어쓰기가 아니라 이어붙이기(concat)를 한다.
_CONCAT_MAPPING_KEYS = {"extra_inline"}


def _merge_mapping_dicts(dicts):
    """여러 mapping.yaml의 raw 내용을 순서대로 하나로 접는다.

    보통의 키는 deep_merge와 같은 원칙 — 나중 파일이 이긴다. `setup:
    [a, b]`가 "뒤에 적은 파일이 이긴다"고 정한 것과 일관되게 맞췄다.
    다만 _CONCAT_MAPPING_KEYS 에 있는 키(extra_inline)만은 예외로,
    각 파일의 리스트를 순서대로 그대로 이어붙인다 — 그래야 "공통 규칙
    파일 + 프로젝트 전용 규칙 파일"처럼 서로 다른 파일에 나눠 적은
    확장 규칙이 서로를 지우지 않고 다 함께 남는다.
    """
    result = {}
    concat_acc = {k: [] for k in _CONCAT_MAPPING_KEYS}
    for d in dicts:
        for k in _CONCAT_MAPPING_KEYS:
            v = d.get(k)
            if v:
                if not isinstance(v, list):
                    raise ConfigError(f"'{k}' 는 리스트여야 합니다.")
                concat_acc[k].extend(v)
        rest = {k: v for k, v in d.items() if k not in _CONCAT_MAPPING_KEYS}
        result = deep_merge(result, rest)
    for k, v in concat_acc.items():
        if v:
            result[k] = v
    return result


def load_configs(paths):
    """mapping: 이 리스트일 때, 여러 YAML 파일을 순서대로 하나의 cfg로
    병합한다. load_config()의 상위 호환이다 — 경로 하나짜리 리스트를
    줘도 완전히 같은 결과를 낸다.

    합치는 원칙은 두 갈래다.
      - 보통의 키(headings, hr, custom_env 등)는 **나중 파일이 이긴다**
        (setup: [a, b] 와 같은 원칙 — front matter 전반의 override 규칙과
        일관되게 맞췄다).
      - extra_inline 만은 예외로 **모든 파일에 걸쳐 이어붙인다**
        (_merge_mapping_dicts 참고) — override 규칙을 그대로 적용하면
        나중 파일의 extra_inline이 앞 파일 것을 통째로 지워 버려서,
        "따로 나눠 적은 확장 규칙을 다 모은다"는 애초의 목적을 못
        살리기 때문이다.
    """
    if not paths:
        return copy.deepcopy(DEFAULT_CONFIG)
    raw_list = []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                user_cfg = yaml.safe_load(f) or {}
        except FileNotFoundError:
            raise ConfigError(f"매핑 파일을 찾을 수 없습니다: {path}")
        except OSError as e:
            raise ConfigError(f"매핑 파일을 읽을 수 없습니다: {path}\n  {e}")
        except yaml.YAMLError as e:
            raise ConfigError(f"매핑 파일의 YAML을 읽지 못했습니다: {path}\n  {e}")
        if not isinstance(user_cfg, dict):
            raise ConfigError(f"매핑 파일이 key: value 형태가 아닙니다: {path}")
        raw_list.append(user_cfg)
    merged_raw = _merge_mapping_dicts(raw_list)
    return deep_merge(DEFAULT_CONFIG, merged_raw)


class ConfigError(Exception):
    pass


def load_config_raw(path):
    """설정 파일의 YAML을 있는 그대로 돌려준다(기본값과 병합하지 않는다).

    mappingrule: 위에 --config 를 다시 얹을 때 쓴다. load_config() 가 돌려주는
    것은 DEFAULT_CONFIG 전체와 병합된 결과라, 그것을 통째로 다시 덮으면
    --config 파일이 건드리지 않은 키까지 죄다 기본값으로 되돌아간다 —
    mappingrule 이 바꿔 둔 것이 조용히 사라지는 회귀였다.
    """
    if path is None:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise ConfigError(f"매핑 파일을 찾을 수 없습니다: {path}")
    except OSError as e:
        raise ConfigError(f"매핑 파일을 읽을 수 없습니다: {path}\n  {e}")
    except yaml.YAMLError as e:
        raise ConfigError(f"매핑 파일의 YAML을 읽지 못했습니다: {path}\n  {e}")
    if not isinstance(user_cfg, dict):
        raise ConfigError(f"매핑 파일이 key: value 형태가 아닙니다: {path}")
    return user_cfg


def load_config(path):
    if path is None:
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(path, encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise ConfigError(f"매핑 파일을 찾을 수 없습니다: {path}")
    except OSError as e:
        raise ConfigError(f"매핑 파일을 읽을 수 없습니다: {path}\n  {e}")
    except yaml.YAMLError as e:
        raise ConfigError(f"매핑 파일의 YAML을 읽지 못했습니다: {path}\n  {e}")
    if not isinstance(user_cfg, dict):
        raise ConfigError(f"매핑 파일이 key: value 형태가 아닙니다: {path}")
    return deep_merge(DEFAULT_CONFIG, user_cfg)


# --------------------------------------------------------------------------
# 2. Front matter 분리
# --------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def split_frontmatter(text, source=None):
    """맨 앞의 --- ... --- 블록을 front matter로 떼어낸다.

    YAML이 깨졌을 때 조용히 {} 를 돌려주면 최악이다. 헤더가 통째로 본문으로
    흘러들어가 --- 는 구분선이 되고 class/preamble 은 사라진 채, 오류도 경고도
    없이 "그럴듯하지만 틀린" 문서가 나온다. 어디가 잘못됐는지 알려준다.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text

    where = f" ({source})" if source else ""
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        print(f"경고: front matter의 YAML을 읽지 못했습니다{where}. "
              f"헤더 없는 문서로 처리합니다.\n  {e}", file=sys.stderr)
        return {}, text
    if not isinstance(meta, dict):
        print(f"경고: front matter가 key: value 형태가 아닙니다{where}. "
              f"헤더 없는 문서로 처리합니다.", file=sys.stderr)
        return {}, text
    return meta, text[m.end():]


# --------------------------------------------------------------------------
# 2.2. 마스터 헤더 상속 — setup:
# --------------------------------------------------------------------------
#
# front matter에 `setup: 파일이름`을 적으면 그 파일의 front matter를 현재
# 문서의 헤더 "아래에 깔고" 병합한다. Org의 #+SETUPFILE:, pandoc의
# --metadata-file과 같은 발상이다.
#
# {{filename}} 포함과 정확히 대칭이다:
#   {{file.md}}      → 그 파일의 "본문"만 가져오고 front matter는 버린다
#   setup: file.md   → 그 파일의 "front matter"만 가져오고 본문은 버린다
# 따라서 완성된 기존 문서를 그대로 스타일 도너로 지정할 수 있다.
#
# 규칙:
#   1. 로컬(현재 파일)이 이긴다. 같은 키가 양쪽에 있으면 현재 파일 값으로
#      대체된다. 이어붙이고 싶으면 `키+:` 형태로 명시한다(preamble+: 등).
#      한 파일에 `preamble:`과 `preamble+:`이 같이 있으면 대체를 먼저
#      적용하고 그 결과에 이어붙인다.
#   2. `title`은 상속하지 않는다. 문서의 정체성이지 스타일이 아니며,
#      완성된 문서를 setup으로 지정했을 때 조용히 딸려오면 에러가 아니라
#      "잘못된 출력"이 나오기 때문이다.
#   3. `mapping`은 값은 상속되지만 경로는 **언제나 최상위 입력 파일의
#      디렉터리** 기준으로 풀린다. 유효한 mapping 설정은 항상 정확히
#      하나뿐이며(--config > 로컬 mapping > setup의 mapping), 여러 개가
#      병합되는 일은 없다. 같은 이유로 `mapping+:`는 무시하고 경고한다.
#   4. setup 파일이 또 `setup:`을 가질 수 있다(공용 기본 → 시리즈 공통 →
#      이 책). 이때 그 경로는 "그 키를 적은 파일"의 디렉터리 기준이다.
#      다만 체인은 MAX_SETUP_DEPTH(=2)단계까지만 허용한다. 즉 위 3단
#      구성이 허용되는 최대 형태이고, 그보다 깊어지면 오류로 중단한다.
#      setup 파일의 `setup:`을 조용히 무시하지 않는 이유: 완성된 문서를
#      스타일 도너로 지정했을 때 그 문서가 스스로 공용 헤더 위에 지어져
#      있으면, 무시하는 순간 스타일의 절반만 딸려온 채 에러 없이 잘못된
#      출력이 나온다. 순환 참조도 마찬가지로 오류로 잡는다.
#   5. setup 파일은 front matter를 가진 마크다운 문서일 수도 있고,
#      YAML만 적힌 파일일 수도 있다. `---`로 감싼 front matter가 있으면
#      그것을, 없으면 파일 전체를 YAML로 해석한다.

SETUP_KEY = "setup"

# setup 파일에서 상속하지 않는 키.
NON_INHERITED_KEYS = {"title"}

# 경로를 언제나 최상위 입력 파일 기준으로 푸는 키(= 이어붙이기 금지).
MAIN_RELATIVE_KEYS = {"mapping"}

# `키+:` 로 이어붙일 때 쓰는 구분자.
APPEND_SEPARATORS = {"classoption": ", ", "classoptions": ", "}
DEFAULT_APPEND_SEPARATOR = "\n"

MAX_SETUP_DEPTH = 2


class SourceError(Exception):
    pass


class ImageError(Exception):
    pass


# --encoding 으로 지정한 입력 인코딩. 지정하지 않으면 None 이고, 그때는
# UTF-8 을 먼저 시도한 뒤 아래 후보들로 물러선다.
SOURCE_ENCODING = None
_FALLBACK_ENCODINGS = ("utf-8", "cp949", "euc-kr")

# 텍스트일 리가 없는 확장자. 실수로 넘겼을 때 "0xe4 를 디코드할 수 없다"는
# 알쏭달쏭한 메시지 대신 무엇이 잘못됐는지 바로 알려주기 위한 것이다.
_BINARY_SUFFIXES = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp",
    ".zip", ".gz", ".7z", ".rar", ".docx", ".xlsx", ".pptx", ".hwp", ".hwpx",
    ".ttf", ".otf", ".woff", ".woff2", ".exe", ".dll", ".so", ".dylib",
    ".mp3", ".mp4", ".avi", ".mkv", ".epub", ".dvi",
}


def _normalize_newlines(text):
    r"""줄바꿈을 LF로 통일한다.

    이 스크립트의 블록/인라인 규칙은 거의 전부 줄 단위 정규식이고 상당수가
    `...\s*$` 가 아니라 `...$` 로 끝난다. CRLF 파일을 그대로 읽으면 줄 끝에
    남은 \r 때문에 그런 규칙이 조용히 빗나간다. 윈도우 편집기에서 만든 원고는
    기본이 CRLF이므로 실제로 자주 겪는다.

    실제로 이런 것들이 어긋났다.
      - `# 제목 {label=...}` 의 속성이 인식되지 않아 제목에 글자로 남음
      - 코드 펜스의 닫는 ``` 줄이 닫는 것으로 인식되지 않아
        그 아래 문서 전체가 코드 블록에 삼켜짐
    문제를 규칙마다 따로 막는 것보다 입구에서 한 번 통일하는 편이 확실하다.
    """
    if "\r" not in text:
        return text
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_source_text(path):
    """입력 파일을 텍스트로 읽는다. 실패하면 SourceError 를 낸다.

    맨 read_text(encoding="utf-8") 를 쓰면 세 가지 흔한 실수가 모두 날것의
    트레이스백으로 튀어나온다 — 파일 이름을 잘못 적었을 때, 폴더를 넘겼을 때,
    그리고 UTF-8 이 아닌 파일을 넘겼을 때다. 각각을 사람이 읽을 수 있는
    메시지로 바꾼다.

    인코딩은 UTF-8 을 먼저 시도하고, 실패하면 cp949/euc-kr 로 물러선다.
    한국어 윈도우에서 만들어진 .txt 원고가 cp949 인 경우가 흔하기 때문이다.
    물러섰을 때는 경고를 찍는다 — 조용히 넘어가면 깨진 글자가 나왔을 때
    원인을 찾을 수 없다.
    """
    path = Path(path)
    if not path.exists():
        raise SourceError(f"입력 파일을 찾을 수 없습니다: {path}")
    if path.is_dir():
        raise SourceError(f"폴더는 변환할 수 없습니다: {path}")

    try:
        data = path.read_bytes()
    except OSError as e:
        raise SourceError(f"파일을 읽을 수 없습니다: {path}\n  {e}")

    suffix = path.suffix.lower()
    if suffix in _BINARY_SUFFIXES or b"\x00" in data[:8192]:
        raise SourceError(
            f"텍스트 파일이 아닌 것 같습니다: {path}\n"
            f"  이 스크립트는 마크다운 원고(.md/.txt 등)를 입력으로 받습니다. "
            f"파일 이름을 다시 확인하십시오."
        )

    if SOURCE_ENCODING:
        try:
            return _normalize_newlines(data.decode(SOURCE_ENCODING))
        except (UnicodeDecodeError, LookupError) as e:
            raise SourceError(
                f"'{SOURCE_ENCODING}' 로 읽을 수 없습니다: {path}\n  {e}")

    for enc in _FALLBACK_ENCODINGS:
        try:
            text = data.decode(enc)
        except UnicodeDecodeError:
            continue
        if enc != "utf-8":
            print(
                f"경고: {path} 가 UTF-8 이 아니라서 {enc} 로 읽었습니다. "
                f"글자가 깨져 보이면 --encoding 으로 직접 지정하거나 파일을 "
                f"UTF-8 로 저장하십시오.",
                file=sys.stderr,
            )
        return _normalize_newlines(text)

    raise SourceError(
        f"인코딩을 알 수 없어 읽지 못했습니다: {path}\n"
        f"  {', '.join(_FALLBACK_ENCODINGS)} 를 시도했습니다. "
        f"--encoding 으로 직접 지정해 보십시오."
    )


class SetupError(Exception):
    pass


def merge_meta(base, override):
    """base(상속된 헤더) 위에 override(현재 파일 헤더)를 얹는다.

    `키+`는 base의 `키` 뒤에 이어붙이고, 그 외 키는 그대로 대체한다.
    base가 비어 있어도(= setup이 없어도) 반드시 한 번 호출해야 한다.
    그래야 `preamble+:`처럼 `+`가 붙은 키가 정규화되어 `preamble`로
    바뀐다 — 안 그러면 조용히 무시되어 내용이 통째로 사라진다.
    """
    result = dict(base or {})
    plain, appends = {}, {}
    for k, v in (override or {}).items():
        if isinstance(k, str) and k.endswith("+") and len(k) > 1:
            appends[k[:-1]] = v
        else:
            plain[k] = v

    result.update(plain)

    for k, v in appends.items():
        if k in MAIN_RELATIVE_KEYS:
            print(
                f"경고: `{k}+`는 지원하지 않습니다(유효한 {k} 설정은 하나뿐). 무시합니다.",
                file=sys.stderr,
            )
            continue
        old = result.get(k)
        if old is None or str(old).strip() == "":
            result[k] = v
            continue
        sep = APPEND_SEPARATORS.get(k, DEFAULT_APPEND_SEPARATOR)
        result[k] = str(old).rstrip() + sep + str(v).lstrip()

    return result


def load_setup_meta(path: Path):
    """setup 파일에서 헤더(dict)만 뽑아온다. 본문은 버린다."""
    try:
        text = read_source_text(path)
    except SourceError as e:
        raise SetupError(f"setup 파일을 읽을 수 없습니다 — {e}")
    except OSError as e:
        raise SetupError(f"setup 파일을 읽을 수 없습니다: {path} ({e})")

    # ---로 감싼 front matter가 있으면 그것만 쓴다(= 마크다운 문서).
    if FRONTMATTER_RE.match(text):
        meta, _ = split_frontmatter(text)
        return meta

    # 없으면 파일 전체를 YAML로 본다(= 헤더만 적힌 파일).
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise SetupError(f"setup 파일의 YAML을 해석할 수 없습니다: {path}\n{e}")
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SetupError(f"setup 파일의 최상위는 매핑이어야 합니다: {path}")
    return data


def _resolve_one_setup(name, base, decl_dir, seen, depth, chain):
    """setup: 의 이름 하나(문자열)를 읽어, base 위에 얹은 최종 meta를 돌려준다.

    base 는 "이 파일이 상속받는 대상"이다. setup: [a, b] 에서 b 를 해석할
    때는 base 가 빈 딕셔너리가 아니라 **a 까지 병합된 결과**여야 한다 —
    그래야 b.nmd 안의 `mappingrule+:` 가 a.nmd 의 mappingrule 위에 제대로
    이어붙는다. base 를 안 거치고 b 를 따로 완결된 상태로 해석해버리면(즉
    b 가 자기보다 앞의 형제를 전혀 모르는 채로 `+` 를 정규화해버리면),
    이어붙일 대상이 없어 `+` 가 그냥 새 키로 뒤바뀌어 앞의 내용이 통째로
    사라진다 — 실제로 이 함수를 분리하기 전에 그 버그가 있었다.
    """
    if depth >= MAX_SETUP_DEPTH:
        trail = " -> ".join(str(c) for c in (chain or [])) or "(최상위 파일)"
        raise SetupError(
            f"setup 체인이 너무 깊습니다(최대 {MAX_SETUP_DEPTH}단계).\n"
            f"  체인: {trail} -> {name}  <- 여기서 중단\n"
            f"  헤더를 어디서 물려받았는지 추적할 수 없게 되므로 의도적으로 막습니다. "
            f"중간 단계를 하나로 합치십시오."
        )

    # setup 파일은 그것을 적은 파일 옆을 먼저 보고, 없으면 공유 리소스
    # 폴더를 본다. 여러 원고가 헤더 하나를 나눠 쓰는 것이 원래 용법이다.
    target, tried = resolve_resource(name, near=[Path(decl_dir)])
    if target is None:
        trail = "\n".join(f"    {t}" for t in tried)
        raise SetupError(f"setup 파일을 찾을 수 없습니다: {name}\n  찾아본 곳:\n{trail}")

    key = target.resolve()
    if key in seen:
        trail = " -> ".join(str(c) for c in (chain or []))
        raise SetupError(f"setup 순환 참조입니다: {trail} -> {target}" if trail
                         else f"setup 순환 참조입니다: {target}")
    seen.add(key)
    if chain is not None:
        chain.append(target)

    own = load_setup_meta(target)
    own_setup = own.get(SETUP_KEY)
    own_names = (own_setup if isinstance(own_setup, list)
                 else [own_setup] if own_setup else [])

    # 이 파일 자신의 setup: 체인(own_names)을 base 위에 순서대로 먼저 얹고,
    # 그 결과를 다시 base 삼아 이 파일 자신의 나머지 내용(own, `+` 포함)을
    # 올린다. own_names 순회에도 이 함수를 그대로 재귀 호출하므로, 조상이
    # 몇 단계든 "누적된 base 위에 얹는다"는 원칙이 끝까지 일관된다.
    parent = base
    for n in own_names:
        parent = _resolve_one_setup(n, parent, target.parent, seen, depth + 1, chain)

    for k in NON_INHERITED_KEYS:
        parent.pop(k, None)

    result = merge_meta(parent, own)
    result.pop(SETUP_KEY, None)
    return result


def resolve_setup(meta, decl_dir, seen=None, depth=0, chain=None):
    """`setup:` 체인을 따라가며 헤더를 병합한 최종 meta를 돌려준다.

    decl_dir 은 이 meta 를 적은 파일이 있는 디렉터리다(setup 경로의 기준).
    chain 이 주어지면 실제로 읽어들인 setup 파일 경로가 순서대로 쌓인다.

    `setup:`은 문자열 하나뿐 아니라 **문자열의 리스트**도 받는다.
    `setup: [a.nmd, b.nmd]` 라고 쓰면 a.nmd, b.nmd 를 그 순서대로 하나씩
    읽어 앞의 것 위에 뒤의 것을 덮어쓰며 접어나간다 — 뒤에 적은 파일이
    이긴다는 점에서 front matter 안의 일반적인 override 규칙과 같다.
    `키+:` 로 적은 값은 여러 파일에 걸쳐서도 계속 이어붙는다 — b.nmd 를
    해석할 때 "이미 a.nmd 가 병합된 상태"를 base 로 넘겨주기 때문이다
    (_resolve_one_setup 참고). 같은 파일 이름이 실수로 두 번 들어가면
    순환 참조로 보고 막는다 — setup: [a.nmd, a.nmd] 는 의미가 없고,
    대개 오타다.
    """
    meta = meta or {}
    seen = set() if seen is None else seen

    name = meta.get(SETUP_KEY)
    if not name:
        # setup이 없어도 `키+` 정규화를 위해 반드시 통과시킨다.
        return merge_meta({}, meta)

    names = name if isinstance(name, list) else [name]

    parent = {}
    for n in names:
        parent = _resolve_one_setup(n, parent, decl_dir, seen, depth, chain)

    merged = merge_meta(parent, meta)
    merged.pop(SETUP_KEY, None)
    return merged


# front matter가 아예 없는 글을 위한 기본 헤더 파일. 다음 순서로 찾는다.
#   1) 현재 작업 폴더
#   2) 이 스크립트가 놓인 폴더  (배포 시 py 파일과 함께 딸려간다는 전제)
# 둘 다 없으면 아무 일도 일어나지 않고 예전처럼 book 클래스로 떨어진다.
DEFAULT_SETUP_NAME = "ndhmd-default.nmd"

# 여러 문서가 나눠 쓰는 설정 파일(mapping yaml, setup용 .nmd)을 찾을 곳.
# 문서 옆이나 작업 폴더에서 못 찾았을 때만 본다 — 가까운 것이 언제나 이긴다.
RESOURCE_ENV = "NDHMARKDOWN_RESOURCE_DIRECTORY"


def _find_shallowest(base, filename):
    """base 아래를 얕은 순서(BFS)로 훑어 filename 이라는 파일을 찾는다.

    "먼저 발견되는 것"을 "최대한 상위 디렉터리에 있는 것"으로 정의한다 —
    base 바로 안(깊이 0)부터 확인하고, 없으면 그 자식 폴더들(깊이 1),
    그 다음 손자 폴더들(깊이 2) 순으로 넓혀 간다. 같은 깊이에 후보가
    여럿이면 폴더 이름 알파벳 순으로 결정한다(운영체제의 디렉터리 순회
    순서에 기대면 실행할 때마다 결과가 달라질 수 있어서, 반드시 정렬해
    사용자가 예측할 수 있게 만들었다). 못 찾으면 None.

    OSError(권한 없음 등)로 못 읽는 폴더는 조용히 건너뛴다 — 리소스
    탐색 하나가 무관한 폴더 권한 문제로 전체가 죽는 것을 막기 위해서다.
    """
    level = [Path(base)]
    while level:
        level = sorted(level, key=lambda p: str(p))
        for d in level:
            cand = d / filename
            if cand.is_file():
                return cand
        next_level = []
        for d in level:
            try:
                next_level.extend(p for p in d.iterdir() if p.is_dir())
            except OSError:
                continue
        level = next_level
    return None


def _find_all_recursive(base, filename):
    """base 아래를 전부 훑어 filename 이라는 파일을 찾은 경로를 얕은
    순서대로 전부 돌려준다(--search-resource 진단용 — 첫 번째만
    쓰는 _find_shallowest() 와 달리 몇 개가 있는지, 어디 있는지 전부
    보여줘야 하므로 끝까지 훑는다).
    """
    out = []
    level = [Path(base)]
    while level:
        level = sorted(level, key=lambda p: str(p))
        for d in level:
            cand = d / filename
            if cand.is_file():
                out.append(cand)
        next_level = []
        for d in level:
            try:
                next_level.extend(p for p in d.iterdir() if p.is_dir())
            except OSError:
                continue
        level = next_level
    return out


def _conventional_dirs(subfolder, env_var=None, only_existing=True):
    r"""사용자 폴더의 관례적인 자리 + 프로그램이 놓인 폴더의 subfolder를
    순서대로 돌려준다. resource_dirs()와 guide_dirs()가 공유한다 —
    "공유 리소스는 어디에 두는가"라는 관례 자체는 리소스 파일이든 가이드
    문서든 똑같기 때문이다(자세한 설명은 resource_dirs()의 독스트링 참고,
    거기 있는 3단계 구조를 그대로 따른다).

    only_existing=False면 실제로 존재하는지 확인하지 않고 후보 경로를
    전부 그대로 돌려준다 — 아무 폴더도 없을 때 "어디를 만들어야 하는지"
    안내하는 오류 메시지에 쓰기 위해서다(예: --guide). 기본값(True)은
    지금까지와 같다.
    """
    out = []
    if env_var:
        env = os.environ.get(env_var, "")
        for part in env.split(os.pathsep):
            part = part.strip()
            if part:
                out.append(Path(part).expanduser())

    home = Path.home()
    out.append(home / "Library" / "ndhmd4tex" / subfolder)
    out.append(home / "ndhmd4tex" / subfolder)
    out.append(home / ".config" / "ndhmd4tex" / subfolder)

    if getattr(sys, "frozen", False):
        out.append(Path(sys.executable).resolve().parent / subfolder)
    else:
        out.append(Path(__file__).resolve().parent / subfolder)

    seen, dirs = set(), []
    for d in out:
        try:
            key = d.resolve()
        except OSError:
            key = d
        if key in seen:
            continue
        seen.add(key)
        if only_existing:
            if d.is_dir():
                dirs.append(d)
        else:
            dirs.append(d)
    return dirs


def resource_dirs():
    r"""공유 설정 파일을 찾을 폴더 목록을 순서대로 돌려준다.

        1) 환경변수 NDHMARKDOWN_RESOURCE_DIRECTORY
           경로 구분자(윈도우 ;, 그 외 :)로 여러 곳을 늘어놓을 수 있다.
        2) 사용자 폴더의 관례적인 자리
           macOS   ~/Library/ndhmd4tex/resources
           그 외   ~/ndhmd4tex/resources
           덧붙여 ~/.config/ndhmd4tex/resources 도 본다(XDG 관례).
        3) 프로그램이 놓인 폴더의 resources/
           배포판에 예제를 함께 담아 보낼 때를 위한 자리다.

    있는 폴더만 돌려준다. 플랫폼별로 갈리는 것을 하나만 보지 않고 전부
    훑는 이유는, 설정을 여러 기계에서 동기화해 쓰는 경우가 흔하기 때문이다.
    없는 폴더는 어차피 걸러지므로 잃는 것이 없다.
    """
    return _conventional_dirs("resources", env_var=RESOURCE_ENV)


GUIDE_ENV = "NDHMARKDOWN_GUIDE_DIRECTORY"


def guide_dirs():
    r"""가이드 문서(*.md, *.pdf)를 찾을 폴더 목록을 순서대로 돌려준다.

    resource_dirs()와 완전히 같은 3단계 구조를 "resources" 대신 "guide"
    폴더에 적용한 것뿐이다 — 공유 리소스를 어디 두는가라는 관례 자체는
    설정 파일이든 가이드 문서든 다르지 않다.

        1) 환경변수 NDHMARKDOWN_GUIDE_DIRECTORY
        2) ~/Library/ndhmd4tex/guide (macOS) / ~/ndhmd4tex/guide (그 외) /
           ~/.config/ndhmd4tex/guide
        3) 프로그램이 놓인 폴더의 guide/
    """
    return _conventional_dirs("guide", env_var=GUIDE_ENV)


def program_location():
    """실행 파일 또는 스크립트 자신의 경로($0에 해당)를 돌려준다.

    PyInstaller로 묶었을 때는 sys.executable(실행 파일 자신)이 $0 에 해당하는
    것이지 __file__ 이 아니다 — __file__ 은 --onefile 의 임시 압축 해제
    폴더나 --onedir 의 _internal 폴더를 가리켜 사용자가 보기에 무의미하다.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(__file__).resolve()


def search_resource(name):
    """name 을 현재 폴더와 모든 공유 리소스 폴더에서 찾아, 발견된 전체 경로를
    빠짐없이 돌려준다(중복 포함). resolve_resource() 와 달리 첫 매치에서
    멈추지 않는다 — 여러 곳에 같은 이름이 있어 어느 것이 실제로 쓰이는지
    헷갈릴 때를 위한 진단 도구이기 때문이다.

    name 이 DEFAULT_SETUP_NAME(ndhmd-default.nmd)과 일치하면 resource_dirs()
    뿐 아니라 default_setup_dirs()도 함께 훑는다. 이 파일은 스크립트/exe
    바로 옆(가장 흔한 배치)에서 실제로 읽히는데, 그 자리는 resource_dirs()
    가 보는 "프로그램 폴더의 resources/ 하위"와 다르다 — 그래서 예전에는
    `--search-resource ndhmd-default.nmd`가 정작 그 파일을 스크립트 옆에
    두었을 때도 못 찾는다고 나왔다. `--search-resource`를 인자 없이 썼을 때
    보여주는 목록(find_all_default_setups)과 결과가 어긋나면 안 된다.

    name 이 경로 구분자 없는 순수 파일 이름이면, resource_dirs() 아래를
    재귀적으로도 훑어서 하위 폴더에 있는 동명 파일까지 전부 보여준다 —
    resolve_resource() 는 "먼저 발견되는 것" 하나만 실제로 쓰지만, 이
    진단 도구는 그렇게 골라지지 않은 나머지 후보가 어디 있는지도 다
    보여줘야 "왜 저 파일이 아니라 이 파일이 쓰였는지"를 확인할 수 있다.
    깊은 순서대로 나오도록 얕은 것부터 담는다(_find_all_recursive() 의
    반환 순서 그대로).
    """
    p = Path(str(name)).expanduser()
    if p.is_absolute():
        return [p] if p.is_file() else []
    bases = [Path.cwd()] + resource_dirs()
    if p.name == DEFAULT_SETUP_NAME:
        bases += default_setup_dirs()
    found = []
    seen = set()

    def _add(cand):
        try:
            key = cand.resolve()
        except OSError:
            key = cand
        if key in seen:
            return
        seen.add(key)
        found.append(cand.resolve() if key == cand.resolve() else cand)

    for base in bases:
        cand = Path(base) / p
        if cand.is_file():
            _add(cand)

    if len(p.parts) == 1:
        for base in resource_dirs():
            for cand in _find_all_recursive(base, p.name):
                _add(cand)

    return found


def resolve_resource(name, near=()):
    """설정 파일 경로를 푼다. 못 찾으면 시도한 경로 목록과 함께 None.

    돌려주는 것은 (경로, 시도해본 경로들) 이다. 절대경로면 그대로 쓰고,
    상대경로면 near(문서 옆 등)를 먼저, 그다음 공유 리소스 폴더를 본다.

    name이 경로 구분자 없는 순수 파일 이름이고 위 방식으로 못 찾았으면,
    공유 리소스 폴더들(resource_dirs()) 아래를 재귀적으로 훑는다 —
    mapping.yaml/setup용 .nmd 파일을 폴더별로 정리해 두고("회사용/",
    "개인용/" 등) 파일 이름만으로 찾고 싶을 때를 위해서다. "먼저
    발견되는 것"은 "최대한 상위(얕은) 디렉터리에 있는 것"으로 정의한다
    (_find_shallowest() 참고) — 여러 폴더에 같은 이름이 있으면 어느
    것이 실제로 쓰였는지 예측 가능해야 하기 때문이다. 어느 후보를
    썼는지 헷갈리면 --search-resource로 전부 나열해 확인할 것.
    이름에 경로 구분자가 있으면(예: "회사용/mapping.yaml") 재귀를 아예
    안 한다 — 그건 이미 "정확히 여기서 찾으라"는 명시적 지정이라, 재귀로
    또 다른 후보를 끼워 넣을 이유가 없다.
    """
    p = Path(str(name)).expanduser()
    tried = []
    if p.is_absolute():
        tried.append(p)
        return (p if p.is_file() else None), tried
    dirs = list(near) + resource_dirs()
    for base in dirs:
        cand = Path(base) / p
        tried.append(cand)
        if cand.is_file():
            return cand, tried
    if len(p.parts) == 1:
        for base in resource_dirs():
            found = _find_shallowest(base, p.name)
            if found is not None:
                # 실제로 재귀에서 몇 단계를 훑었는지 하나하나 tried에
                # 적으면(폴더가 깊거나 많으면) 오류 메시지가 감당 안 될
                # 만큼 길어진다. "이 폴더 아래 어딘가"라는 뜻으로
                # 와일드카드 표기 하나만 남긴다.
                tried.append(Path(base) / "**" / p.name)
                return found, tried
        for base in resource_dirs():
            tried.append(Path(base) / "**" / p.name)
    return None, tried


def default_setup_dirs():
    r"""기본 헤더 파일을 찾을 폴더 목록을 순서대로 돌려준다.

    PyInstaller로 묶은 실행 파일에서는 __file__ 을 쓰면 안 된다. 실측하면
    이렇게 갈린다.

        --onefile :  __file__      -> C:\...\Temp\_MEIxxxx   (임시 압축 해제 폴더)
                     sys.executable -> ...\ndhmd4tex.exe
        --onedir  :  __file__      -> ...\ndhmd4tex\_internal
                     sys.executable -> ...\ndhmd4tex\ndhmd4tex.exe

    둘 다 exe 옆을 가리키지 않는다. onefile 의 임시 폴더는 실행이 끝나면
    사라지므로 사용자가 거기에 파일을 둘 수조차 없다. 그래서 얼어붙은
    상태에서는 sys.executable 의 폴더를 본다 — 사용자가 exe 옆에 두는
    ndhmd-default.nmd 가 여기서 잡힌다.

    마지막으로 sys._MEIPASS(번들 안에 딸려 들어간 자료 폴더)도 본다.
    .spec 에 datas=[("ndhmd-default.nmd", ".")] 를 넣어 기본 헤더를 exe 안에
    넣어두면, 사용자가 아무것도 두지 않아도 그것이 쓰인다.
    """
    dirs = [Path.cwd()]
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent)
    else:
        dirs.append(Path(__file__).resolve().parent)
    # 공유 리소스 폴더. 기계마다 쓰는 기본 헤더를 여기 한 번 두면 된다.
    dirs.extend(resource_dirs())
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            # 실행 파일 안에 묶여 온 사본은 맨 마지막 수단이다.
            dirs.append(Path(meipass))
    # 같은 폴더가 두 번 들어가는 경우를 걷어낸다(순서는 유지).
    seen, out = set(), []
    for d in dirs:
        try:
            key = d.resolve()
        except OSError:
            key = d
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def find_default_setup(name=None):
    """기본 헤더 파일을 찾아 경로를 돌려준다. 없으면 None.

    name 을 안 주면(기본값) DEFAULT_SETUP_NAME(ndhmd-default.nmd)을 찾는다
    — 예전과 완전히 같은 동작이다. name 을 주면(--default) 그 이름을 대신
    찾는다: 절대경로면 그 경로만 확인하고, 상대경로면 default_setup_dirs()
    를 순서대로 훑는다(cwd, 스크립트/exe 옆, 공유 리소스 폴더) —
    ndhmd-default.nmd 를 찾던 곳과 정확히 같은 자리들이다. --default 로
    지정한 파일도 "이 컴퓨터/이 작업 폴더에서 기본으로 쓸 헤더"라는
    점에서 성격이 같으므로, 굳이 다른 탐색 규칙을 새로 만들지 않았다.
    """
    if name is None:
        name = DEFAULT_SETUP_NAME
    p = Path(str(name))
    if p.is_absolute():
        return p if p.is_file() else None
    for d in default_setup_dirs():
        cand = d / name
        if cand.is_file():
            return cand
    return None


def find_all_default_setups():
    """기본 헤더 파일을 default_setup_dirs() 전체에서 훑어, 발견된 모든
    경로를 순서대로 돌려준다(중복 없이). 실제로 쓰이는 것은 이 중 맨 앞의
    하나뿐이지만(find_default_setup 참고), --search-resource 는 그 뒤에
    가려진 사본이 몇 개 더 있는지까지 보여주는 진단 도구다.
    """
    found, seen = [], set()
    for d in default_setup_dirs():
        cand = d / DEFAULT_SETUP_NAME
        if not cand.is_file():
            continue
        try:
            key = cand.resolve()
        except OSError:
            key = cand
        if key in seen:
            continue
        seen.add(key)
        found.append(cand.resolve() if key == cand.resolve() else cand)
    return found


def init_default_setup():
    """기본 헤더를 현재 폴더로 꺼내 쓴다. 종료 코드를 돌려준다.

    --onefile 로 묶은 실행 파일에서는 기본 헤더가 exe 안에 들어 있어서
    사용자가 열어볼 수도, 고칠 수도 없다. 꺼내 놓으면 그 사본이 (작업 폴더가
    가장 앞이므로) exe 안의 것을 가리게 되고, 그때부터 마음대로 손볼 수 있다.
    """
    dest = Path.cwd() / DEFAULT_SETUP_NAME
    if dest.exists():
        print(f"오류: 이미 있습니다 — {dest}\n"
              f"  덮어쓰지 않습니다. 새로 받으려면 기존 파일을 옮기거나 지우십시오.",
              file=sys.stderr)
        return 1

    src = None
    for d in default_setup_dirs():
        cand = d / DEFAULT_SETUP_NAME
        # 자기 자신을 원본으로 삼는 일이 없게 한다.
        if cand.is_file() and cand.resolve() != dest:
            src = cand
            break
    if src is None:
        print(f"오류: 꺼내 쓸 {DEFAULT_SETUP_NAME} 을 찾지 못했습니다. 찾아본 곳:",
              file=sys.stderr)
        for d in default_setup_dirs():
            print(f"  {d / DEFAULT_SETUP_NAME}", file=sys.stderr)
        return 1

    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"{dest} 를 만들었습니다.  (원본: {src})")
    print("이 파일을 고치면 이 폴더의 원고에 그대로 반영됩니다.")
    return 0


def apply_setup_fallback(raw_meta, cli_setup=None, cli_default=None):
    """문서의 front matter에 setup: 을 채워 넣는다.

    우선순위는 이렇다.
      1) CLI의 --setup            — 명시적으로 준 것이니 가장 세다.
                                    문서에 적힌 setup: 도 이것으로 갈아치운다
                                    (--config 가 front matter의 mapping: 을
                                     이기는 것과 같은 원칙).
      2) 문서 자신의 setup:       — 손대지 않는다.
      3) --default 로 지정한 파일, 또는(안 줬으면) ndhmd-default.nmd
                                    — 위 둘이 다 없을 때만 끼워 넣는다.
      4) 아무것도 없음            — 예전 그대로.

    --setup 과 --default 는 성격이 다르다. --setup 은 "이 실행에서는
    무조건 이 헤더를 쓰라"는 최우선 지시라 문서 자신의 setup: 마저
    덮어쓴다. --default 는 그보다 훨씬 약하다 — ndhmd-default.nmd 라는
    "최후의 fallback 파일 자체"를 다른 파일로 바꿔치기하는 것뿐이라,
    문서가 setup: 을 스스로 정했다면(2번) 여전히 그게 이긴다. 즉
    --default 는 "아무 헤더도 안 정한 문서들에 한해 어떤 파일을 기본으로
    쓸지"를 그때그때 바꾸는 것이고, --setup 은 "지금 이 변환만큼은
    다른 걸 다 무시하고 이 헤더로 강제한다"는 것이다.

    cli_default 가 정확히 문자열 "NONE"(대문자)이면 3번 단계 자체를
    건너뛴다 — ndhmd-default.nmd 를 포함해 어떤 기본 헤더도 찾지
    않는다. 확장자를 안 붙이는 등 값 자체의 전처리(.nmd 자동 보완)는
    호출부(main())에서 미리 끝내고 넘어온다.

    CLI 인자와 자동으로 찾은 파일은 작업 폴더 기준이라 절대경로로 바꿔서
    넣는다. resolve_setup() 은 상대경로를 "그 헤더를 적은 파일의 위치" 기준
    으로 푸는데, 그 기준이 여기서는 맞지 않기 때문이다.

    cli_setup 은 콤마로 여러 파일을 나열할 수 있다("a.nmd,b.nmd"). 그러면
    resolve_setup() 이 보는 setup: 값도 리스트가 되어, 문서 자신이
    setup: [a, b] 라고 쓴 것과 같은 방식(뒤가 앞을 덮어씀, `+` 는 계속
    이어붙음)으로 처리된다.
    """
    raw_meta = dict(raw_meta or {})
    if cli_setup:
        # 콤마로 여러 파일을 나열할 수 있다(front matter의 setup: [a, b]
        # 리스트 표기와 대응). argparse 위치 인자(입력 파일)와 겹치지 않게
        # 공백 대신 콤마로 구분한다.
        names = [s.strip() for s in str(cli_setup).split(",") if s.strip()]
        resolved = []
        for nm in names:
            target, tried = resolve_resource(nm, near=[Path.cwd()])
            if target is None:
                trail = "\n".join(f"    {t}" for t in tried)
                raise SetupError(
                    f"--setup 파일을 찾을 수 없습니다: {nm}\n  찾아본 곳:\n{trail}")
            resolved.append(str(target.resolve()))
        # 하나뿐이면 기존과 똑같이 문자열로 넣는다 — 굳이 리스트로 감싸
        # dump-meta 등의 출력 모양을 바꿀 이유가 없다.
        raw_meta[SETUP_KEY] = resolved[0] if len(resolved) == 1 else resolved
        return raw_meta
    if raw_meta.get(SETUP_KEY):
        return raw_meta
    if cli_default == "NONE":
        return raw_meta
    found = find_default_setup(cli_default)
    if found is not None:
        raw_meta[SETUP_KEY] = str(found)
    return raw_meta


def resolve_meta(text, src_path, cli_setup=None, cli_default=None):
    """최상위 입력 파일의 front matter를 setup 체인까지 해석해서 돌려준다.

    (meta, body, chain) 을 돌려준다. chain 은 실제로 읽어들인 setup 파일의
    경로 목록으로, --dump-meta 에서 헤더의 출처를 보여주는 데 쓴다.
    """
    src_path = Path(src_path)
    raw_meta, body = split_frontmatter(text, source=src_path)
    raw_meta = apply_setup_fallback(raw_meta, cli_setup, cli_default)
    try:
        seen = {src_path.resolve()}
    except OSError:
        seen = set()
    chain = []
    meta = resolve_setup(raw_meta, src_path.parent, seen, 0, chain)
    return meta, body, chain


# --------------------------------------------------------------------------
# 2.5. 파일 포함(inclusion) 처리 — {{filename}}
# --------------------------------------------------------------------------
#
# multimarkdown의 {{filename}} 트랜스클루전을 본떴다. 단, 다음 세 가지는
# 의도적으로 단순화했다(단행본 조판이라는 용례에서 상태 공유 — 각주 사전,
# toplevel 헤딩 매핑, Protector — 를 문서 전체 단위로 한 번만 처리하는 현재
# 구조를 유지하기 위함):
#
#   1. 재귀 포함을 지원하지 않는다. {{...}}는 "최상위 입력 파일"의 본문에서만
#      1회 해석되며, 포함된 파일의 내용 안에 또 {{...}}가 있어도 해석하지
#      않고 리터럴 텍스트로 남는다 — 포함은 정확히 한 단계만 허용된다.
#   2. 확장자를 포함해 파일 이름을 정확히 써야 한다. {{chapter1}}처럼
#      확장자를 생략하면 .md를 자동으로 붙여주지 않고, 그 이름 그대로
#      파일을 찾아 없으면 오류로 처리한다.
#   3. 경로 없이 파일 이름만 쓰면 "포함하는 파일"(=최상위 입력 파일)과 같은
#      폴더 기준으로 찾는다. 상대/절대 경로를 포함해서 쓰면 그 경로를
#      그대로 따른다(상대 경로는 마찬가지로 최상위 입력 파일의 폴더를
#      기준으로 결합한다).
#
# 포함되는 파일에 YAML frontmatter가 있으면 통째로 무시하고 본문만 사용한다
# (split_frontmatter를 그대로 재사용).
#
# 코드펜스(``` ... ```) 안의 {{...}}는 문법을 보여주기 위한 예시로 보고
# 치환하지 않는다. 한 줄짜리 인라인 코드로 `{{file.md}}`처럼 백틱으로 바로
#감싼 경우도 마찬가지로 건드리지 않는다 — 이 파일 다른 곳(COMMENT_RE,
# DISPLAY_MATH_RE 등)과 동일하게 (?<!`)/(?!`) 가드로 처리한다.

INCLUDE_RE = re.compile(r"(?<!`)\{\{([^{}\n]+?)\}\}(?!`)")


class IncludeError(Exception):
    pass


# {{포함}}은 이제 재귀적으로(포함된 파일 안의 {{...}}도) 해석된다 —
# 순환 포함은 즉시 오류로 잡아내지만(resolve_includes 참고), 순환이
# 없어도 사슬이 지나치게 길어지는 것까지는 그 감지로 못 막으므로 이
# 상한을 따로 둔다. 정상적인 원고가 이 깊이까지 갈 일은 사실상 없다 —
# 순전히 "무한히 깊어지는 걸 막는 안전망"이다.
_MAX_INCLUDE_DEPTH = 20


def _include_sub_outside_code(line, sub_fn):
    r"""한 줄에서 인라인 코드 스팬 **바깥에만** {{...}} 치환을 적용한다.

    INCLUDE_RE의 (?<!`)/(?!`) 가드는 백틱이 중괄호에 딱 붙어 있는 경우만
    막아준다. 그래서 `` `{{ user.name }}` `` 처럼 패딩 스페이스가 있거나,
    `` `\newcommand{\x}{{\it y}} z` `` 처럼 스팬 한복판에 {{ 가 있는 경우는
    여전히 진짜 포함 지시자로 오인해서 "포함 파일을 찾을 수 없습니다"로
    변환 전체를 중단시켰다. 코드 펜스는 resolve_includes()가 이미 건너뛰므로,
    같은 배려를 인라인 코드 스팬에도 해준다.

    스팬 판정은 protect_inline_code()와 같은 CommonMark 규칙이다: 여는 백틱
    런과 길이가 정확히 같은 런만 닫는 델리미터로 인정하고, 짝을 못 찾으면
    코드 스팬이 아닌 리터럴 백틱으로 취급한다.
    """
    out, buf = [], []
    i, n = 0, len(line)

    def flush():
        if buf:
            out.append(INCLUDE_RE.sub(sub_fn, "".join(buf)))
            buf.clear()

    while i < n:
        if line[i] == "\\" and i + 1 < n and line[i + 1] == "`":
            buf.append(line[i:i + 2])
            i += 2
            continue

        m = _BACKTICK_RUN_RE.match(line, i)
        if not m:
            buf.append(line[i])
            i += 1
            continue

        run_len = m.end() - m.start()
        j = m.end()
        close_end = None
        while j < n:
            m2 = _BACKTICK_RUN_RE.match(line, j)
            if m2:
                if (m2.end() - m2.start()) == run_len:
                    close_end = m2.end()
                    break
                j = m2.end()
            else:
                j += 1

        if close_end is None:
            buf.append(line[m.start():m.end()])
            i = m.end()
            continue

        flush()
        out.append(line[m.start():close_end])
        i = close_end

    flush()
    return "".join(out)


def _resolve_include_target(raw_name: str, base_dir: Path) -> Path:
    p = Path(raw_name)
    return p if p.is_absolute() else (base_dir / p)


def _read_include_body(raw_name: str, target: Path):
    """포함 파일을 읽어 (원본 전체 텍스트, front matter를 뗀 본문)을 돌려준다.

    resolve_includes()와 resolve_includes_tracked()가 공유한다 — 둘이
    똑같은 파일을 똑같은 방식으로 읽어야, --syncinfo가 만드는 줄 번호가
    실제 컴파일 결과와 어긋나지 않는다.
    """
    if not target.is_file():
        raise IncludeError(
            f"포함 파일을 찾을 수 없습니다: {{{{{raw_name}}}}}  (확인한 경로: {target})"
        )
    try:
        inc_text = read_source_text(target)
    except SourceError as e:
        raise IncludeError(str(e))
    _, inc_body_raw = split_frontmatter(inc_text)
    return inc_text, inc_body_raw


def _read_raw_tex_include(raw_name: str, target: Path) -> str:
    """{{tex:파일}} 전용 — 마크다운이 아니라 날 LaTeX 소스이므로 front
    matter라는 개념 자체가 없다. split_frontmatter()를 적용하면 안 된다 —
    그 파일이 우연히 "---"로 시작하기라도 하면 진짜 내용의 일부를 front
    matter로 오인해 잘라먹는다. resolve_includes()와
    resolve_includes_tracked()가 공유한다.
    """
    if not target.is_file():
        raise IncludeError(
            f"포함 파일을 찾을 수 없습니다: {{{{{raw_name}}}}}  (확인한 경로: {target})"
        )
    try:
        raw_text = read_source_text(target)
    except SourceError as e:
        raise IncludeError(str(e))
    return raw_text.strip("\n")


def _splice_raw_tex(raw_tex: str, pr) -> str:
    """{{tex:파일}} 로 읽은 raw LaTeX 텍스트를, 그 뒤를 잇는 마크다운
    파이프라인에서 안전하게 통과하도록 감싼다.

    pr(Protector)이 있으면(--pandoc이 아닌 일반 변환/--syncinfo 경로) 그
    자리표시자 체계로 통째로 감싸서, 이후의 모든 정규식 기반 처리(코드펜스
    보호, 인라인 강조·링크·각주 등)를 완전히 우회한다 — MATH_ENV_RE 등
    다른 raw 보호 지점과 같은 방식이다.

    pr이 없으면(--pandoc 모드) 애초에 Protector 자체를 안 쓴다 — 본문
    전체를 pandoc 서브프로세스에 markdown으로 그대로 넘기는 구조라, 우리
    자리표시자 문자를 pandoc이 이해하지 못하고 그냥 이상한 텍스트로
    출력해 버린다. 대신 pandoc이 표준으로 지원하는 raw-attribute
    코드펜스(```{=latex} ... ```)로 감싼다 — 실측으로 안의 내용(별표·
    밑줄·링크 문법·중괄호 등)이 전혀 마크다운으로 해석되지 않고 그대로
    통과되는 것을 확인했다. 앞뒤에 빈 줄을 둬서 독립된 블록으로
    인식되게 한다.
    """
    if pr is not None:
        return pr.protect(raw_tex)
    return "\n```{=latex}\n" + raw_tex + "\n```\n"


# `{{파일패턴;물음표=목록}}` 형태의 일괄(배치) 트랜스클루전. 예:
# `{{sub??.md;??=01-20}}` -> {{sub01.md}} ... {{sub20.md}} 를 한 번에 쓴
# 것과 같다. 물음표 뒤에 오는 등호·목록이 진짜 배치 지정인지 확인하려고
# 정규식으로 뒤에서부터 검사한다 — 파일 이름 자체에 세미콜론이 들어갈
# 일은 실무에서 거의 없다고 보고, 마지막 세미콜론을 기준으로 나누는
# 정도로 충분하다고 판단했다. 범위 구분자로 물결표(~)가 아니라 평범한
# 대시(-)를 쓴다 — 자판에서 더 흔하고 다른 문법에서도 범위 표기로
# 널리 쓰이는 기호다. 파일 이름 패턴 쪽에 대시가 들어가도(예:
# sub-file??.md) 마지막 세미콜론으로 목록 부분을 먼저 떼어내므로 섞일
# 걱정이 없다.
#
# 목록(등호 뒤)은 콤마로 구분된 여러 조각을 받는다 — 조각 하나하나는
# "숫자" 하나(`7`), "숫자-숫자" 범위(`01-10`), 또는 "숫자-*"(열린 범위,
# 아래 참고) 셋 중 하나다. `{{sub??.md;??=01-10,12-20}}`처럼 불연속
# 범위를, `{{sub?.md;?=1-3,7,9-10}}`처럼 단일 숫자와 범위를 섞어 쓸 수
# 있다. 콤마가 하나도 없으면(조각이 하나뿐이면) 기존의 단순 범위 문법과
# 완전히 같은 모양이 되므로, 이전 버전에서 쓰던 `{{sub??.md;??=01-20}}`
# 표기도 손볼 필요 없이 그대로 동작한다. 조각들은 적힌 순서 그대로
# 이어붙는다 — 정렬하거나 중복을 걸러내지 않는다. 겹치는 범위를 일부러
# 적으면(`1-5,3-7`) 3, 4, 5가 두 번 나오는데, 이것도 원고 작성자의
# 의도로 존중한다(다른 배치 목록형 문법에서 중복을 자동으로 걸러내지
# 않는 것과 같은 태도).
#
# "숫자-*"(열린 범위)만은 완전히 다른 철학으로 동작한다. `01-20`처럼
# 끝이 숫자로 고정된 범위는 그 안의 모든 파일이 실제로 존재해야 하고,
# 하나라도 없으면 (resolve_includes 단계에서) 시끄러운 오류로 멈춘다 —
# 이 방언 전체가 "조용한 실패를 만들지 않는다"는 태도를 지키기 때문이다.
# 반면 `01-*`는 "시작 번호부터, 실제로 있는 마지막 파일까지"를 뜻하며,
# 이를 위해 이 함수가 base_dir 을 실제로 뒤져(디렉터리 글롭) 존재하는
# 파일만 모은다 — 중간에 빠진 번호(예: sub11.md 없음)가 있어도 그냥
# 건너뛰고 다음 것(sub12.md)으로 자연스럽게 이어진다. 즉 `01-*`를 쓴다는
# 것 자체가 "있는 것만 있는 대로 가져오라"는 명시적 의도이므로, 이
# 경우만 예외적으로 조용히 건너뛴다 — 고정 범위의 엄격함은 그대로 둔
# 채, 필요한 사람만 이 문법으로 다른 동작을 선택하게 한 것이다. `*`는
# 오직 끝자리에서만 받는다(시작이 `*`이거나 `*-*`는 모호해서 지원하지
# 않는다).
_TRANSCLUSION_RANGE_RE = re.compile(r"^([?]+)=(.+)$")
_TRANSCLUSION_SEGMENT_RE = re.compile(r"^(\d+)(?:-(\d+))?$")
_TRANSCLUSION_OPEN_SEGMENT_RE = re.compile(r"^(\d+)-\*$")


def _scan_existing_numbers(pattern_for_glob, placeholder, width, base_dir, start):
    """base_dir 기준으로 pattern_for_glob 에 실제로 맞는 파일을 찾아,
    placeholder 자리의 값이 숫자이면서 start 이상인 것만 정수로 모아
    정렬해 돌려준다.

    물음표는 이미 "임의의 한 글자"를 뜻하는 표준 글롭 와일드카드와
    정확히 같은 문자라서, 이 함수는 pattern_for_glob 을 가공하지 않고
    그대로 Path.glob() 에 넘긴다 — 새 패턴 언어를 또 만들 이유가
    없었다. 다만 그 자리에 실제로 채워진 문자가 전부 숫자인 경우만
    인정한다(글롭 자체는 숫자인지 여부를 모르므로, 결과를 걸러내는
    책임은 이 함수가 진다).
    """
    idx = pattern_for_glob.index(placeholder)
    found = []
    try:
        matches = list(Path(base_dir).glob(pattern_for_glob))
    except (OSError, ValueError):
        matches = []
    for p in matches:
        try:
            rel = p.relative_to(base_dir).as_posix()
        except ValueError:
            continue
        num_str = rel[idx:idx + width]
        if len(num_str) == width and num_str.isdigit():
            n = int(num_str)
            if n >= start:
                found.append(n)
    return sorted(set(found))


def _expand_transclusion_range(raw_name: str, base_dir=None):
    """`파일패턴;물음표=목록` 형태를 감지해 개별 이름 목록을 돌려준다.

    예: `"sub??.md;??=01-20"` -> `["sub01.md", "sub02.md", ..., "sub20.md"]`.
    `"sub??.md;??=01-10,12-20"` -> 01~10과 12~20을 이어붙인 19개(11은
    빠진다). `"sub?.md;?=1-3,7,9-10"` -> `["sub1.md", "sub2.md",
    "sub3.md", "sub7.md", "sub9.md", "sub10.md"]`. `"tex:sub??.tex;??=1-3"`
    -> `["tex:sub1.tex", "tex:sub2.tex", "tex:sub3.tex"]` — `tex:` 접두사는
    "파일 이름 패턴"의 일부로 그냥 함께 실려 다니다가, 확장된 각 이름이
    그대로 기존 `{{tex:...}}` 판정 로직을 다시 타면서 알아서 처리된다.
    배치 확장 자체는 순수하게 "이름 문자열 하나를 여러 개로 부풀리는
    것"으로 국한하고, 그 뒤(파일 존재 확인, raw tex 여부 등)는 전부
    기존 로직에 그대로 맡긴다 — 새로운 개념을 얹는 게 아니라 입력
    문자열의 개수만 늘리는 셈이다.

    `"sub??.md;??=01-*"` -> base_dir 을 실제로 뒤져 01 이상이면서 실제로
    존재하는 파일을 전부 모아 정렬한다("sub11.md" 가 없으면 그냥 건너뛰고
    "sub12.md"로 이어진다). base_dir 이 주어지지 않았는데 이 문법을 쓰면
    IncludeError 를 낸다 — 어디를 뒤져야 할지 모르는 채로 조용히
    무시하면 안 되기 때문이다.

    **`?`/`??` 자리는 숫자 전용이다.** 셸 glob이나 정규식의 와일드카드처럼
    "아무 글자 하나"를 뜻하지 않는다 — 목록의 각 조각은 정수(범위)로만
    주어지고(`_TRANSCLUSION_SEGMENT_RE`가 `\\d+`로 강제), 채워 넣는 값도
    그 정수를 자릿수만큼 0으로 채운 것뿐이라(`str(int).zfill(width)`),
    결과에 숫자 아닌 문자가 들어갈 여지가 애초에 없다. 문자 범위(`a-z`)나
    일반적인 패턴 매칭은 지원하지 않는다 — 지원하려는 게 아니라 설계상
    배제한 것이다.

    자리 수(0을 채우는 폭)는 물음표 개수로 정한다 — `??`는 언제나 2자리
    (01, 02, ..., 20)로 채운다. 목록 전체에 폭이 하나로 통일 적용된다.
    자릿수가 넘어가도(예: `?=1-15`) 잘리지 않고 자연스럽게 1, ..., 9,
    10, ..., 15로 나온다 — 채움은 항상 "최소 자릿수"만 보장할 뿐, 그보다
    큰 수를 억지로 줄이지 않는다. 열린 범위(`01-*`)에서도 이 폭이 그대로
    글롭의 "몇 자리 숫자만 인정할지"를 결정한다 — `??`면 3자리 이상인
    파일(`sub100.md`)은 애초에 대상에서 제외된다.

    배치 패턴이 아니면(세미콜론이 없거나 뒷부분이 이 형식이 아니면)
    None을 돌려준다 — 호출부가 평범한 단일 파일 처리로 그대로 넘어가게
    하기 위해서다. 물음표가 파일 이름 패턴 안에 없거나, 목록의 어느
    조각이든 숫자·범위·열린범위 형식이 아니거나, 범위의 시작이 끝보다
    크거나, 열린 범위에 맞는 파일이 하나도 없으면 IncludeError로 명확히
    알린다 — 조용히 빈 목록으로 넘어가면 "왜 아무것도 안 나오지"를
    원고 작성자가 스스로 알아낼 방법이 없다(열린 범위 자체가 "있는
    것만 조용히 모은다"는 예외이지만, 그 대상 자체를 하나도 못 찾은
    경우까지 조용히 넘기면 오타를 잡을 수 없다).
    """
    if ";" not in raw_name:
        return None
    file_pattern, _, range_spec = raw_name.rpartition(";")
    m = _TRANSCLUSION_RANGE_RE.match(range_spec)
    if not m:
        return None
    placeholder, segments_str = m.group(1), m.group(2)
    if placeholder not in file_pattern:
        raise IncludeError(
            f"트랜스클루전 범위 지정 오류: {{{{{raw_name}}}}} — "
            f"'{placeholder}' 가 파일 이름 패턴 안에 없습니다."
        )
    width = len(placeholder)
    numbers = []
    for segment in segments_str.split(","):
        segment = segment.strip()
        m_open = _TRANSCLUSION_OPEN_SEGMENT_RE.match(segment)
        if m_open:
            if base_dir is None:
                raise IncludeError(
                    f"트랜스클루전 범위 지정 오류: {{{{{raw_name}}}}} — "
                    f"이 자리에서는 열린 범위(*)를 쓸 수 없습니다."
                )
            start = int(m_open.group(1))
            scan_pattern = file_pattern[len("tex:"):] if file_pattern.startswith("tex:") else file_pattern
            found = _scan_existing_numbers(scan_pattern, placeholder, width, base_dir, start)
            if not found:
                raise IncludeError(
                    f"트랜스클루전 범위 지정 오류: {{{{{raw_name}}}}} — "
                    f"'{segment}'(열린 범위)에 맞는 파일을 하나도 찾지 못했습니다."
                )
            numbers.extend(found)
            continue
        sm = _TRANSCLUSION_SEGMENT_RE.match(segment)
        if not sm:
            raise IncludeError(
                f"트랜스클루전 범위 지정 오류: {{{{{raw_name}}}}} — "
                f"'{segment}' 을 숫자·범위(예: 01-10)·열린범위(예: 01-*)로 이해할 수 없습니다."
            )
        start = int(sm.group(1))
        end = int(sm.group(2)) if sm.group(2) is not None else start
        if start > end:
            raise IncludeError(
                f"트랜스클루전 범위 지정 오류: {{{{{raw_name}}}}} — "
                f"'{segment}' 에서 시작({start})이 끝({end})보다 큽니다."
            )
        numbers.extend(range(start, end + 1))
    return [file_pattern.replace(placeholder, str(k).zfill(width)) for k in numbers]


def resolve_includes(text, base_dir: Path, pr=None, self_path=None, _chain=None, _depth=0):
    """`{{파일}}`을 재귀적으로 해석한다 — 포함된 파일의 본문 안에 또
    `{{서브서브파일}}`이 있어도 (그 안에 또 있어도, ...) 계속 파고든다.

    상대 경로는 재귀 깊이와 무관하게 항상 **최상위 입력 파일의 폴더**
    기준이다(20장) — base_dir 자체를 재귀 내내 그대로 물려주는 것으로
    이걸 보장한다. 포함되는 파일이 자기 폴더 기준의 상대 경로로 또
    다른 파일을 가리키고 싶다면, 최상위 파일 기준으로 다시 풀어서 적어야
    한다는 뜻이다 — "포함 관계가 몇 단계든, 경로만은 언제나 한 기준점
    (최상위 파일)에서 잰다"는 게 이 방언 전체의 일관된 태도다.

    self_path 는 최초 호출(최상위 파일 자신을 처리하는 시점)에서만
    의미가 있다 — 그 파일 자신을 순환 감지용 _chain에 미리 넣어 두려는
    것이다. 이게 없으면 "최상위 파일이 자기 자신을 포함하는" 가장 단순한
    순환이, 그 파일을 두 번째로 열 때가 아니라 세 번째로 열 때에야
    감지된다(자기 자신 → 그 사본 안에서 또 자기 자신 → 그제서야 "이미
    본 파일"로 걸림). 재귀 호출 쪽(_chain이 이미 채워진 뒤)에서는 이
    인자를 무시한다.

    _chain 은 "지금 이 재귀 스택 위에서 이미 열려 처리 중인 파일들"의
    정규화된 절대경로 집합이다. 어떤 파일을 열려는 순간 그 파일이 이미
    _chain 안에 있으면 순환 포함(A가 B를, B가 다시 A를 포함하는 식)
    이므로 IncludeError로 즉시 멈춘다 — 무한 재귀로 스택이 넘치거나
    변환이 응답 없이 멈춰버리는 대신, 무엇이 무엇을 순환 포함했는지
    보여주는 오류가 먼저 뜨게 하려는 것이다.

    _depth 는 그 보조 안전장치다. 순환이 없어도 포함 사슬이 지나치게
    길어지면(대개 실수로 엉뚱한 파일을 반복 포함한 경우) _MAX_INCLUDE_
    DEPTH 에서 마찬가지로 IncludeError로 멈춘다. 원고 안내서에도 적어
    뒀듯, 재귀 자체는 지원하지만 너무 깊이 중첩하는 것은 권장하지
    않는다 — 각 단계의 경로 기준이 전부 같은 하나(최상위 파일)라서,
    깊이 중첩할수록 "이 파일이 실제로 어디서 왔는지" 원고 작성자
    스스로도 추적하기 어려워지기 때문이다.
    """
    if _chain is None:
        _chain = frozenset({Path(self_path).resolve()}) if self_path is not None else frozenset()
    base_dir = Path(base_dir)

    def _resolve_path(raw_name: str) -> Path:
        return _resolve_include_target(raw_name, base_dir)

    def _sub(m):
        raw_name = m.group(1).strip()
        names = _expand_transclusion_range(raw_name, base_dir)
        if names is not None:
            # 배치 확장 자체는 "이름 문자열을 여러 개로 부풀리는 것"뿐이다.
            # 부풀린 뒤에는 {{이름1}}\n\n{{이름2}}\n\n... 형태의 텍스트를
            # 다시 resolve_includes() 에 통째로 맡겨서, tex: 판정이나
            # 파일 존재 확인 같은 나머지 처리를 전부 기존 로직 그대로
            # 재사용한다 — 빈 줄로 갈라둔 이유는 트랜스클루전이 "앞뒤로
            # 빈 줄을 둔 독립된 한 줄"일 때 가장 안전하게 인식되기
            # 때문이다(20장 권장 사항과 같다). _chain/_depth 를 그대로
            # 물려줘야 이 경로를 거쳐도 순환·깊이 감지가 리셋되지 않는다.
            expanded_block = "\n\n".join(f"{{{{{nm}}}}}" for nm in names)
            return resolve_includes(expanded_block, base_dir, pr, None, _chain, _depth)
        if raw_name.startswith("tex:"):
            tex_name = raw_name[len("tex:"):].strip()
            target = _resolve_path(tex_name)
            raw_tex = _read_raw_tex_include(raw_name, target)
            return _splice_raw_tex(raw_tex, pr)
        target = _resolve_path(raw_name).resolve()
        if target in _chain:
            chain_display = " -> ".join(str(p) for p in (*_chain, target))
            raise IncludeError(
                f"순환 포함이 있습니다: {chain_display}\n"
                f"  {{{{{raw_name}}}}} 가 이미 처리 중인 파일을 다시 가리킵니다."
            )
        if _depth + 1 >= _MAX_INCLUDE_DEPTH:
            raise IncludeError(
                f"포함 깊이가 {_MAX_INCLUDE_DEPTH}단계를 넘었습니다: {{{{{raw_name}}}}}\n"
                f"  순환 포함이 있는지 확인하거나, 트랜스클루전 구조를 더 얕게 두십시오."
            )
        inc_text, inc_body = _read_include_body(raw_name, target)
        inc_body = inc_body.strip("\n")
        # 재귀 지점: 방금 읽어들인 본문 안에도 {{...}}가 있을 수 있다.
        # base_dir 은 그대로, _chain 에는 방금 연 target 을 추가, _depth
        # 는 하나 늘려서 넘긴다.
        return resolve_includes(inc_body, base_dir, pr, None, _chain | {target}, _depth + 1)

    # extract_code_fences()와 동일한 CommonMark 규칙(_FENCE_OPEN_RE /
    # _FENCE_CLOSE_RE, 섹션 3에 정의됨)으로 줄 단위 스캔하며, 코드펜스 내부는
    # 건너뛴다. resolve_includes()는 protect_block_level()보다 먼저 실행되므로
    # 여기서 독자적으로 펜스를 추적해야 한다.
    lines = text.split("\n")
    out = []
    i, n = 0, len(lines)
    in_fence = False
    fence_len = 0

    while i < n:
        line = lines[i]

        if in_fence:
            close_m = _FENCE_CLOSE_RE.match(line)
            if close_m and len(close_m.group(1)) >= fence_len:
                in_fence = False
            out.append(line)
            i += 1
            continue

        open_m = _FENCE_OPEN_RE.match(line)
        if open_m:
            in_fence = True
            fence_len = len(open_m.group(1))
            out.append(line)
            i += 1
            continue

        out.append(_include_sub_outside_code(line, _sub))
        i += 1

    return "\n".join(out)


_INCLUDE_WHOLE_LINE_RE = re.compile(r"^\s*\{\{([^{}\n]+?)\}\}\s*$")


def _resolve_single_include(raw_name, target_resolver, pr, base_dir, _chain, _depth):
    """배치가 아닌 단일 raw_name 하나를 읽어 (텍스트, origin 목록)을
    돌려준다. origin의 각 항목은 (파일, 그 파일 안에서 0-based 줄 번호).

    resolve_includes_tracked()의 whole-line 분기와, 배치 트랜스클루전이
    확장한 이름 하나하나가 이 함수를 공유한다 — 배치 확장은 "이름
    문자열을 여러 개로 부풀리는 것"뿐이고, 부풀려진 각 이름을 실제로
    어떻게 읽어들일지(존재 확인, tex: 판정, front matter 오프셋 계산)는
    원래부터 있던 이 로직 그대로다.

    resolve_includes()와 마찬가지로 재귀적이다 — 방금 읽어들인 본문
    안에도 {{...}}가 있으면 resolve_includes_tracked()를 다시 불러
    풀어낸다. 그 재귀 호출이 돌려주는 origin은 이미 "그 재귀 호출에
    넘긴 텍스트(앞뒤 trim된 본문) 자신"을 0번째 줄로 삼아 계산돼
    있으므로, 이 함수가 원래 계산해 둔 first_local_line(원본 파일에서
    그 본문이 실제로 시작하는 줄)만큼 보정해 줘야 한다 — 단, target
    자신을 가리키는 항목만. 재귀 호출 안에서 또 다른 파일(서브서브)을
    가리키게 된 항목은 이미 그 자체로 올바른 절대 줄 번호이므로 손대면
    안 된다.
    """
    if raw_name.startswith("tex:"):
        tex_name = raw_name[len("tex:"):].strip()
        target = target_resolver(tex_name).resolve()
        raw_tex = _read_raw_tex_include(raw_name, target)
        text = _splice_raw_tex(raw_tex, pr)
        # pr.protect() 가 돌려주는 자리표시자는 언제나 정확히 한 줄
        # (개행이 없는 토큰 문자열)이므로 origin 항목도 하나만 필요하다.
        # raw tex 파일은 마크다운이 아니라서 "정확히 몇 번째 줄"이라는
        # 개념 자체가 의미가 없으므로, 파일 전체를 대표해 0번째 줄
        # (파일 시작)로 근사한다 — inverse search를 하면 이 tex 파일
        # 자체가 열리게 된다. raw tex는 마크다운이 아니므로 재귀 대상도
        # 아니다.
        return text, [(target, 0)]

    target = target_resolver(raw_name)

    # origin 에 저장되는 target 은 반드시 정규화된 절대경로여야 한다 —
    # base_dir 자체가(호출자의 실수로) 상대경로였거나 ".."를 포함하고
    # 있어도, 이 지점에서 한 번 더 resolve() 로 확실히 정리해 둔다.
    target = target.resolve()

    if target in _chain:
        chain_display = " -> ".join(str(p) for p in (*_chain, target))
        raise IncludeError(
            f"순환 포함이 있습니다: {chain_display}\n"
            f"  {{{{{raw_name}}}}} 가 이미 처리 중인 파일을 다시 가리킵니다."
        )
    if _depth + 1 >= _MAX_INCLUDE_DEPTH:
        raise IncludeError(
            f"포함 깊이가 {_MAX_INCLUDE_DEPTH}단계를 넘었습니다: {{{{{raw_name}}}}}\n"
            f"  순환 포함이 있는지 확인하거나, 트랜스클루전 구조를 더 얕게 두십시오."
        )

    inc_text, inc_body_raw = _read_include_body(raw_name, target)

    fm_char_len = len(inc_text) - len(inc_body_raw)
    fm_line_offset = inc_text[:fm_char_len].count("\n")
    inc_body = inc_body_raw.strip("\n")
    leading_trim = len(inc_body_raw) - len(inc_body_raw.lstrip("\n"))
    first_local_line = fm_line_offset + leading_trim

    resolved_text, nested_origin = resolve_includes_tracked(
        inc_body, base_dir, target, pr, _chain | {target}, _depth + 1
    )
    # nested_origin 항목 중 target(방금 연 이 파일) 자신을 가리키는
    # 것만 first_local_line 만큼 보정한다 — 재귀 호출은 inc_body를
    # 0번째 줄부터로 여기고 origin을 만들었으므로, 그 본문이 원본
    # 파일에서 실제로 시작하는 줄(front matter + 앞쪽 trim만큼)을
    # 더해야 target 파일 기준의 진짜 줄 번호가 된다. 다른 파일(더
    # 깊이 포함된 서브서브파일 등)을 가리키는 항목은 이미 그 자체로
    # 정확하므로 그대로 둔다.
    origin_entries = [
        (f, (ln + first_local_line) if f == target else ln)
        for f, ln in nested_origin
    ]
    return resolved_text, origin_entries


def resolve_includes_tracked(text, base_dir: Path, self_path, pr=None, _chain=None, _depth=0):
    """resolve_includes()와 완전히 같은 결과 텍스트를 만들면서, 동시에
    "결과의 각 줄이 어느 파일의 몇 번째 줄(0-based)에서 왔는지" 를 담은
    origin 리스트를 함께 돌려준다. --syncinfo 전용이다.

    resolve_includes()를 그대로 두고 병행해서 만든 이유: 줄 추적이라는
    부가 기능 때문에 실제 변환 경로(resolve_includes 자신)의 동작이
    조금이라도 달라지면 안 되기 때문이다 — 그래서 코드가 상당 부분
    중복되더라도, resolve_includes()가 쓰는 것과 정확히 같은 조각들
    (_resolve_include_target, _read_include_body, _include_sub_outside_code,
    코드펜스 추적 규칙, 순환·깊이 감지 규칙)을 그대로 재사용한다. 이
    함수가 만드는 텍스트가 resolve_includes()의 결과와 바이트 단위로
    같은지는 반드시 실측으로 검증해야 한다(다르면 .nmdsync 의 줄 번호가
    실제 .tex 와 어긋난다).

    정밀 추적은 "그 줄이 공백을 빼면 {{파일}} 하나뿐인" 경우로 한정한다.
    같은 줄에 다른 텍스트가 섞여 있거나(예: "본문 {{sub.md}} 계속") 코드
    펜스/인라인 코드 안이면, 그 줄 전체를 그냥 self_path(지금 처리 중인
    파일) 자신의 그 줄로 기록한다 — 이런 용법은 이 방언에서 사실상
    쓰이지 않고, 설령 쓰이더라도 "그 블록이 대략 이 근처에서 왔다"는
    근사치면 충분하기 때문이다.

    포함 파일 쪽의 줄 번호 계산: 포함되는 파일은 (1) front matter가
    떨어져 나가고 (2) 본문 앞뒤의 순수 개행이 strip("\n")으로 제거된
    뒤에야 스플라이스된다(resolve_includes() 참고). 그러므로 스플라이스된
    텍스트의 0번째 줄이 원본 파일의 몇 번째 줄이었는지 알아내려면 이
    두 트림이 각각 몇 줄을 먹었는지 정확히 되짚어야 한다:
      - front matter가 차지한 줄 수: 원본 텍스트 길이에서 body 길이를
        뺀 부분(=front matter 정규식이 매치한 부분)의 개행 개수.
      - 앞쪽 strip("\n")이 먹은 줄 수: 트림 전/후 텍스트 길이 차이가
        곧 제거된 개행 문자 수이고, 그 개수가 곧 제거된 빈 줄 수와
        같다(개행 하나가 그 앞의 빈 줄 하나를 끝낸다).
    두 값을 더하면 "스플라이스된 본문의 0번째 줄"이 원본 파일의 몇
    번째 줄(0-based)인지 나온다.

    {{포함}}은 resolve_includes()와 마찬가지로 이제 재귀적으로 해석된다
    — 포함된 파일 안에 또 다른 {{...}}가 있으면 (_resolve_single_include
    를 거쳐) 이 함수가 다시 불려 그 안까지 파고들고, origin도 재귀
    호출의 결과를 그대로 이어받아 정확한 최종 파일까지 추적한다.
    self_path/_chain/_depth 의 의미는 resolve_includes()와 같다 — 다만
    이 함수는 self_path 가 필수 인자다(최상위 호출이든 재귀 호출이든
    "지금 이 텍스트가 어느 파일의 것인지"를 항상 알아야 하기 때문에).
    _chain 이 None(최초 호출)이면 self_path 자신을 체인에 넣어 시작한다.
    """
    if _chain is None:
        _chain = frozenset({Path(self_path).resolve()})
    base_dir = Path(base_dir)

    def _resolve_path(raw_name: str) -> Path:
        return _resolve_include_target(raw_name, base_dir)

    lines = text.split("\n")
    out = []
    origin = []
    i, n = 0, len(lines)
    in_fence = False
    fence_len = 0

    while i < n:
        line = lines[i]

        if in_fence:
            close_m = _FENCE_CLOSE_RE.match(line)
            if close_m and len(close_m.group(1)) >= fence_len:
                in_fence = False
            out.append(line)
            origin.append((self_path, i))
            i += 1
            continue

        open_m = _FENCE_OPEN_RE.match(line)
        if open_m:
            in_fence = True
            fence_len = len(open_m.group(1))
            out.append(line)
            origin.append((self_path, i))
            i += 1
            continue

        whole_m = _INCLUDE_WHOLE_LINE_RE.match(line)
        if whole_m:
            raw_name = whole_m.group(1).strip()
            names = _expand_transclusion_range(raw_name, base_dir)

            if names is not None:
                # 배치 트랜스클루전 — 확장된 이름을 순서대로 하나씩
                # _resolve_single_include() 에 넘겨 처리하고 이어붙인다.
                # 파일과 파일 사이에는 빈 줄을 하나 끼워 넣어야 각각
                # 독립된 블록으로 인식된다(트랜스클루전이 "앞뒤로 빈
                # 줄"을 필요로 하는 것과 같은 이유 — 사용자가 직접
                # {{sub01.md}}\n\n{{sub02.md}}\n\n... 라고 하나하나
                # 적었을 때와 결과가 같아야 한다). 그 빈 줄 자체는
                # 정답이 없는 자리라 self_path의 이 줄(i)로 근사해
                # 기록한다. _chain/_depth 는 그대로 물려준다 — 배치로
                # 펼쳐진 파일들끼리는 서로 순환 관계를 이룰 일이 없지만
                # (형제 파일들일 뿐이다), 그중 하나가 다시 조상 파일을
                # 포함하려 드는 경우는 여전히 잡아야 한다.
                for idx, nm in enumerate(names):
                    piece_text, piece_origin = _resolve_single_include(
                        nm, _resolve_path, pr, base_dir, _chain, _depth)
                    if idx > 0:
                        out.append("")
                        origin.append((self_path, i))
                    out.append(piece_text)
                    origin.extend(piece_origin)
                i += 1
                continue

            text_piece, entries = _resolve_single_include(
                raw_name, _resolve_path, pr, base_dir, _chain, _depth)
            out.append(text_piece)
            origin.extend(entries)
            i += 1
            continue

        def _sub(m):
            raw_name = m.group(1).strip()
            names = _expand_transclusion_range(raw_name, base_dir)
            if names is not None:
                # 이 지점은 whole-line이 아닌 인라인 사용(다른 텍스트와
                # 한 줄에 섞여 있음)이다 — 애초에 정밀 추적을 포기하고
                # 그 줄 전체를 self_path 자신의 줄로 근사하는 경로라서
                # (바로 아래 origin.append 참고), 배치 확장도 텍스트
                # 치환만 정확히 해 주면 충분하다. resolve_includes()
                # 와 똑같이 재귀 호출로 나머지 처리를 위임한다 — 정밀한
                # origin은 필요 없어도 순환·깊이 감지는 이 경로에서도
                # 똑같이 적용돼야 하므로 _chain/_depth를 그대로 넘긴다.
                expanded_block = "\n\n".join(f"{{{{{nm}}}}}" for nm in names)
                return resolve_includes(expanded_block, base_dir, pr, None, _chain, _depth)
            if raw_name.startswith("tex:"):
                tex_name = raw_name[len("tex:"):].strip()
                target = _resolve_path(tex_name)
                raw_tex = _read_raw_tex_include(raw_name, target)
                return _splice_raw_tex(raw_tex, pr)
            # 여기도 정밀 추적을 포기한 경로이므로, 재귀·순환·깊이 처리는
            # resolve_includes()(비-tracked)에 그대로 위임한다 — 이 자리가
            # 만들 origin은 self_path의 근사치일 뿐이라 정밀한 origin
            # 합성까지 갈 필요가 없다.
            target = _resolve_path(raw_name).resolve()
            if target in _chain:
                chain_display = " -> ".join(str(p) for p in (*_chain, target))
                raise IncludeError(
                    f"순환 포함이 있습니다: {chain_display}\n"
                    f"  {{{{{raw_name}}}}} 가 이미 처리 중인 파일을 다시 가리킵니다."
                )
            if _depth + 1 >= _MAX_INCLUDE_DEPTH:
                raise IncludeError(
                    f"포함 깊이가 {_MAX_INCLUDE_DEPTH}단계를 넘었습니다: {{{{{raw_name}}}}}\n"
                    f"  순환 포함이 있는지 확인하거나, 트랜스클루전 구조를 더 얕게 두십시오."
                )
            _, inc_body = _read_include_body(raw_name, target)
            inc_body = inc_body.strip("\n")
            return resolve_includes(inc_body, base_dir, pr, None, _chain | {target}, _depth + 1)

        out.append(_include_sub_outside_code(line, _sub))
        origin.append((self_path, i))
        i += 1

    return "\n".join(out), origin


# --------------------------------------------------------------------------
# 3. 블록 이전 단계: 보호
# --------------------------------------------------------------------------

CODE_FENCE_RE = re.compile(r"```([a-zA-Z0-9_-]*)\n(.*?)\n```", re.DOTALL)
# 아래 세 정규식은 (?<!`) / (?!`) 로 둘러싸서, 백틱으로 직접 감싼 텍스트
# (예: `\begin{tblr}...\end{tblr}` 처럼 raw LaTeX 문법을 "설명하려고" 인라인
# 코드로 보여주는 경우)는 매치하지 않도록 한다. 인라인 코드 보호는 이
# 정규식들보다 훨씬 늦게(문단 단위 process_inline 안에서) 실행되므로, 이
# 가드가 없으면 예시로 보여주려던 텍스트를 진짜 raw LaTeX 환경/수식으로
# 오인식해서 escape 없이 통째로 보호해버려 컴파일 에러가 난다.
DISPLAY_MATH_RE = re.compile(r"(?<!`)(\$\$.*?\$\$|\\\[.*?\\\])(?!`)", re.DOTALL)
MATH_ENV_RE = re.compile(
    r"(?<!`)(\\begin\{(equation\*?|align\*?|gather\*?|multline\*?|eqnarray\*?)\}.*?\\end\{\2\})(?!`)",
    re.DOTALL,
)
TABLE_ENV_RE = re.compile(
    r"(?<!`)(\\begin\{(tabular|tabularx|tabulary|tblr|longtblr)\}.*?\\end\{\2\})(?!`)",
    re.DOTALL,
)
# pandoc과 동일한 HTML 스타일 주석. 여러 줄에 걸쳐도 되고(re.DOTALL), 여는
# "<!--"부터 그 뒤 첫 "-->"까지 통째로 제거된다(참, HTML 표준처럼 중첩은
# 지원하지 않는다 — 첫 "-->"에서 바로 닫힌다). 위의 세 정규식과 같은 이유로
# 백틱 바로 옆에 붙은 경우는 매치하지 않아서, "예시로 <!-- 이렇게 -->라고
# 씁니다"처럼 인라인 코드로 문법 자체를 보여줄 때 실제로 지워지지 않는다.
COMMENT_RE = re.compile(r"(?<!`)<!--.*?-->(?!`)", re.DOTALL)
# linecomment: true 일 때만 쓰는 라인 코멘트. "행 머리"를 들여쓰기 0칸으로
# 엄격히 제한한 이유: 인용구·리스트 항목 안에 들여써진 // 는 저자가 실제로
# 쓰려던 텍스트일 가능성이 높고, 코드 예제 안 // 는 애초에 코드펜스가
# 먼저 보호하므로 이 정규식이 볼 일이 없다.
#
# 뒤따르는 개행까지 함께 지운다(HTML 주석과 다른 점). 내용만 지우고
# 개행을 남기면 그 줄이 빈 줄로 바뀌는데, 리스트 항목 사이에 주석을 끼워
# 쓴 경우 원래 없던 빈 줄이 새로 생겨 리스트가 둘로 쪼개진다 — 실제로
# 리스트 항목 사이에 주석을 남기려는 것이 이 기능의 주된 용도이므로, 그
# 용도 자체를 방해하면 안 된다. 개행까지 지우면 인접한 줄이 그대로
# 붙어서 리스트가 하나로 유지된다. 문단 사이에 빈 줄로 감싸 쓴 경우
# (`문단\n\n// 주석\n\n문단`)는 애초에 있던 빈 줄이 그대로 남아 문단
# 분리는 유지된다.
LINECOMMENT_RE = re.compile(r"^//.*\n?", re.MULTILINE)

# 여는/닫는 펜스 한 줄만 판별하는 정규식 (줄 단위 스캔용).
# CommonMark와 동일하게: 여는 펜스는 (선택적 들여쓰기 0~3칸) + 백틱 3개 이상 +
# (선택) 언어 태그. 닫는 펜스는 (들여쓰기 0~3칸) + 백틱만으로 이루어진 줄이며,
# 그 개수가 여는 펜스의 개수 "이상"이어야 한다.
_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,})[ \t]*([a-zA-Z0-9_-]*)[ \t]*$")
_FENCE_CLOSE_RE = re.compile(r"^ {0,3}(`{3,})[ \t]*$")


def _render_code_block(lang, body, cfg):
    lang = (lang or "").strip()
    if lang in ["raw", "tex", "latex"]:
        return body
    elif not lang or lang in ["text", "verb"]:
        env_name = cfg.get("verbatim_env", "verbatim")
        return f"\\begin{{{env_name}}}\n{body}\n\\end{{{env_name}}}"
    else:
        tmpl = cfg.get("codeblock_template", "\\begin{minted}{%(lang)s}\n%(body)s\n\\end{minted}")
        return tmpl % {"lang": lang, "body": body}


def extract_code_fences(text, cfg, pr: Protector, sync_events=None):
    """백틱 펜스 코드 블록을 줄 단위로 스캔해 보호한다.

    이전에는 "```(lang)\\n(.*?)\\n```" 정규식 하나로 문서 전체를 훑었는데,
    이 방식은 펜스의 백틱 개수(길이)를 구분하지 못했다. 그래서 마크다운
    문법 자체를 설명하는 문서처럼 예시 코드펜스를 보여주려고 백틱 4개짜리
    펜스 안에 백틱 3개짜리 예제 펜스를 중첩시키면, 안쪽 예제의 여는/닫는
    펜스를 바깥쪽 펜스로 잘못 짝지어버리고, 그 여파로 그 뒤에 나오는 모든
    코드펜스의 짝짓기가 연쇄적으로 어긋나는 문제가 있었다.

    CommonMark(및 Pandoc)와 동일한 규칙을 적용한다: 여는 펜스의 백틱 개수를
    N이라 하면, 그 뒤로는 백틱 개수가 N 미만인 줄은 전부 내용으로 흡수되고,
    백틱만으로 이루어진 줄의 개수가 N 이상이어야 비로소 닫는 펜스로 인정한다.

    sync_events 가 리스트로 주어지면(--syncinfo 전용), 코드펜스 하나를 만날
    때마다 (여는줄_인덱스, 닫는줄_다음_인덱스, 1) 을 append 한다 — 이 펜스가
    차지했던 여러 줄이 자리표시자 한 줄로 줄었다는 뜻이다. None(기본값)이면
    이 기록을 아예 하지 않으므로, 기존 호출부는 완전히 그대로 동작한다.
    """
    lines = text.split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        m = _FENCE_OPEN_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue

        fence_start = i
        fence_len = len(m.group(1))
        lang = m.group(2)
        body_lines = []
        i += 1
        while i < n:
            close_m = _FENCE_CLOSE_RE.match(lines[i])
            if close_m and len(close_m.group(1)) >= fence_len:
                i += 1
                break
            body_lines.append(lines[i])
            i += 1
        # 닫는 펜스를 끝내 못 찾았어도(파일이 그대로 끝남) 그때까지 모은
        # 내용으로 코드 블록을 만든다 — 문서 전체가 깨지는 것보다는 낫다.
        if sync_events is not None:
            sync_events.append((fence_start, i, 1))
        out.append(pr.protect(_render_code_block(lang, "\n".join(body_lines), cfg)))
    return "\n".join(out)


# --------------------------------------------------------------------------
# 3.5. ```showexam — "원문 + 변환 결과" 2단 블록
# --------------------------------------------------------------------------
#
# 이 블록만은 다른 코드펜스보다 먼저, protect_block_level()보다도 앞에서
# 뽑아내야 한다. 본문이 두 갈래로 쓰이기 때문이다: 왼쪽 상자에는 손대지 않은
# 원문이 들어가고, 오른쪽 상자에는 그 원문을 파이프라인에 "다시" 통과시킨
# 결과가 들어간다. 그런데 그 재변환은 지금 당장 할 수 없다 — 각주 정의
# (cfg["_footnotes"])가 아직 수집되기 전이라, 예제 안의 각주 참조가 빈
# 내용으로 굳어버린다. 그래서 여기서는 자리표시자만 심어두고, 본문 변환이
# 전부 끝난 뒤 convert()에서 expand_showexam()으로 채운다.
#
# 자리표시자는 Protector와 마찬가지로 사용자 정의 영역 문자를 쓴다. 이 문자는
# escape_chars에도, 인라인 규칙에도 걸리지 않으므로 render_blocks를 그대로
# 통과한다. Protector의 \uE000/\uE001과는 다른 짝이라 서로 간섭하지 않는다.
_SE_OPEN, _SE_CLOSE = "\uE010", "\uE011"
_SE_PH_RE = re.compile(_SE_OPEN + r"(\d+)" + _SE_CLOSE)

# 정보 문자열에 =, . 같은 글자가 들어갈 수 있어서 _FENCE_OPEN_RE보다 헐겁다.
# 대신 백틱은 못 들어가게 막아 닫는 펜스와 헷갈리지 않게 한다.
_SE_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,})[ \t]*([^`]*)$")
_SE_INFO_RE = re.compile(r"^showexam\b[ \t]*(.*)$")
_SE_OPT_RE = re.compile(r"(\w+)\s*=\s*(\"[^\"]*\"|\S+)")

# 재귀 깊이 제한. showexam 안에 showexam을 넣는 것까지는 허용하되(문법 설명
# 문서에서 실제로 쓸 일이 있다) 무한히 파고들지는 않게 한다.
_SE_MAX_DEPTH = 3


def _se_parse_opts(raw):
    return {m.group(1): m.group(2).strip('"') for m in _SE_OPT_RE.finditer(raw or "")}


def extract_showexam(text, store, sync_events=None):
    """```showexam 블록을 뽑아내고 자리표시자로 바꾼다.

    일반 코드펜스도 함께 훑으면서 지나간다. 그래야 마크다운 문법 자체를
    설명하려고 백틱 4개짜리 펜스 안에 showexam 예제를 넣어둔 경우,
    그 안쪽을 진짜 showexam으로 오인해서 잡아가지 않는다.

    sync_events 가 리스트로 주어지면(--syncinfo 전용), 진짜 showexam
    블록 하나를 자리표시자 3줄(앞뒤 빈 줄 포함)로 줄일 때마다
    (시작줄, 끝줄, 3) 을 append한다. 평범한 펜스로 판명나 원래 모습으로
    되돌리는 경우는 줄 수가 안 바뀌므로 기록하지 않는다.
    """
    if _SE_OPEN in text:
        # 입력에 사용자 정의 영역 문자가 이미 들어 있으면 자리표시자와
        # 충돌한다. 실수로 섞여든 것이므로 지운다.
        text = text.replace(_SE_OPEN, "").replace(_SE_CLOSE, "")

    lines = text.split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        m = _SE_FENCE_OPEN_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue

        block_start = i
        fence_len = len(m.group(1))
        info_m = _SE_INFO_RE.match(m.group(2).strip())
        open_line = lines[i]
        body_lines = []
        close_line = None
        i += 1
        while i < n:
            close_m = _FENCE_CLOSE_RE.match(lines[i])
            if close_m and len(close_m.group(1)) >= fence_len:
                close_line = lines[i]
                i += 1
                break
            body_lines.append(lines[i])
            i += 1

        if info_m is None:
            # showexam이 아닌 평범한 펜스 — 원래 모습 그대로 되돌려놓고
            # extract_code_fences가 나중에 처리하게 둔다.
            out.append(open_line)
            out.extend(body_lines)
            if close_line is not None:
                out.append(close_line)
            continue

        store.append(("\n".join(body_lines), _se_parse_opts(info_m.group(1))))
        if sync_events is not None:
            sync_events.append((block_start, i, 3))
        # 앞뒤 빈 줄을 둬서 자리표시자가 독립된 문단으로 남게 한다.
        out.extend(["", f"{_SE_OPEN}{len(store) - 1}{_SE_CLOSE}", ""])
    return "\n".join(out)


def render_showexam(src, rendered, opts, cfg):
    """원문과 변환 결과를 좌우(minipage) 또는 위아래로 조립한다."""
    conf = dict(cfg.get("showexam") or {})
    styles = dict(conf.get("styles") or {})

    def _pick(key, default):
        return opts.get(key, conf.get(key, default))

    try:
        ratio = float(_pick("ratio", 0.46))
    except (TypeError, ValueError):
        ratio = 0.46
    try:
        gap = float(_pick("gap", 0.04))
    except (TypeError, ValueError):
        gap = 0.04
    ratio = min(max(ratio, 0.05), 0.9)
    right = max(1.0 - ratio - gap, 0.05)

    align = str(_pick("align", "t"))
    style = str(_pick("style", "minted"))
    listing_tmpl = (opts.get("listing") or styles.get(style)
                    or "\\begin{verbatim}\n%(src)s\n\\end{verbatim}")

    # frame은 "frame=single," 같은 옵션 조각으로 만들어 listing 템플릿에
    # 넘긴다. 끄고 싶을 때 빈 문자열이 되어야 하므로 쉼표까지 여기서 붙인다.
    frame = str(_pick("frame", "single")).strip().lower()
    frame_opt = "" if frame in ("", "none", "no", "off", "false", "0") else f"frame={frame},"

    left = listing_tmpl % {
        "src": src.rstrip("\n"),
        "lang": _pick("lang", "markdown"),
        "frame": frame_opt,
    }

    layout = str(_pick("layout", "side")).strip().lower()
    if layout == "auto":
        try:
            limit = float(_pick("stack_width", 36))
        except (TypeError, ValueError):
            limit = 36
        longest = max((sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
                           for ch in ln) for ln in src.split("\n")), default=0)
        layout = "stack" if longest > limit else "side"
    if layout not in ("side", "stack"):
        print(f"경고: showexam layout={layout!r} 를 알 수 없어 side로 둡니다.",
              file=sys.stderr)
        layout = "side"
    if layout == "stack":
        ignored = [k for k in ("ratio", "gap", "align") if k in opts]
        if ignored:
            print("경고: showexam layout=stack 에서는 " + ", ".join(ignored)
                  + " 가 무시됩니다.", file=sys.stderr)
        sep = str(_pick("sep", "rule"))
        sep = {
            "rule": ("\\par\\nopagebreak\\vspace{0.4\\baselineskip}"
                     "\\noindent\\rule{\\linewidth}{0.4pt}\\par\\nopagebreak"
                     "\\vspace{0.4\\baselineskip}"),
            "space": "\\par\\nopagebreak\\medskip",
            "none": "",
        }.get(sep.strip().lower(), sep)
        stack_tmpl = conf.get("stack_template") or (
            "\\par\\medskip\\noindent\n%(left)s\n%(sep)s\n%(right)s\n\\par\\medskip")
        return stack_tmpl % {"left": left, "right": rendered.strip(), "sep": sep}

    template = conf.get("template") or (
        "\\par\\medskip\\noindent\n"
        "\\begin{minipage}[%(align)s]{%(lw)s\\linewidth}\n%(left)s\n\\end{minipage}\\hfill\n"
        "\\begin{minipage}[%(align)s]{%(rw)s\\linewidth}\n%(right)s\n\\end{minipage}\n"
        "\\par\\medskip"
    )
    return template % {
        "left": left,
        "right": rendered.strip(),
        "lw": f"{ratio:.4f}",
        "rw": f"{right:.4f}",
        "align": align,
        "ratio": f"{ratio:.4f}",
        # [t] 정렬은 두 상자의 "첫 줄 베이스라인"을 맞춘다. 그래서 왼쪽에
        # frame이 붙거나 listing이 위쪽 여백을 얹으면 두 단이 어긋나 보인다.
        # 맨 앞의 \vspace{0pt}는 이를 "상자 윗변" 기준 정렬로 바꿔주는
        # 관용구다. c/b 정렬에서는 오히려 방해가 되므로 넣지 않는다.
        "strut": "\\vspace{0pt}" if align == "t" else "",
    }


def convert_fragment(md_text, cfg, depth=0):
    """마크다운 조각을 본문 LaTeX로 변환한다(문서 헤더 없이).

    convert()의 본문 처리 부분만 떼어낸 것. showexam의 오른쪽 상자를 채울 때
    쓴다. cfg는 호출 시점에 이미 _footnotes까지 채워져 있어야 한다.
    """
    store = []
    text = extract_showexam(md_text, store) if depth < _SE_MAX_DEPTH else md_text

    sub_pr = Protector()
    text = protect_block_level(text, cfg, sub_pr)
    out = render_blocks(text.split("\n"), cfg, sub_pr)
    out = sub_pr.restore(out)
    return expand_showexam(out, store, cfg, depth + 1).strip()


def expand_showexam(tex, store, cfg, depth=0):
    """자리표시자를 실제 2단 LaTeX 코드로 되돌린다."""
    if not store:
        return tex

    def _sub(m):
        idx = int(m.group(1))
        if idx >= len(store):
            return ""
        src, opts = store[idx]
        return render_showexam(src, convert_fragment(src, cfg, depth=depth), opts, cfg)

    return _SE_PH_RE.sub(_sub, tex)


def _protect_regex_outside_code(text, pattern, protect_fn):
    r"""pattern 에 매치되는 구간을 protect_fn(원본 매치 문자열)의 결과로
    치환하되, 인라인 코드 스팬(백틱) 안에서는 매치를 아예 무시한다.

    DISPLAY_MATH_RE/MATH_ENV_RE/TABLE_ENV_RE 는 원래 "(?<!`)...(?!`)"
    가드로 이걸 막으려 했지만, 그 가드는 "매치 경계 바로 옆에 백틱 한
    글자가 있는가"만 볼 뿐이라 `` `\[foo\]` ``처럼 백틱이 매치에 딱
    붙어 있을 때만 걸러진다 — `` `grep '\[foo\]'` ``처럼 백틱과 매치
    사이에 다른 문자(따옴표 등)가 하나라도 끼면 못 잡는다(실제로 겪은
    버그). protect_inline_code()가 아직 돌기 전(이 함수가 실행되는
    시점은 블록 레벨 단계라 인라인 코드 스팬 파싱보다 먼저다)이라
    코드 스팬 안의 문자가 원문 그대로 노출돼 있다는 걸 이 함수가
    메운다 — _mask_inline_code_multiline() 이 만든, 코드 스팬 부분만
    길이를 보존한 채 안전한 문자로 덮은 사본에서 매치 위치를 찾고,
    그 위치를 원본 text 에 그대로 적용한다(마스킹된 사본 자체를
    최종 결과로 쓰면 코드 스팬의 진짜 내용이 사라져 버린다).

    반환값은 (새 text, 매치를 찾는 데 쓴 마스킹된 사본) — 호출부가
    sync_events 용 줄 이벤트를 이 마스킹된 사본 기준으로 다시 계산할
    수 있도록 둘 다 돌려준다.
    """
    masked = _mask_inline_code_multiline(text)
    out = []
    last = 0
    for m in pattern.finditer(masked):
        out.append(text[last:m.start()])
        out.append(protect_fn(text[m.start():m.end()]))
        last = m.end()
    out.append(text[last:])
    return "".join(out), masked


def protect_block_level(text, cfg, pr: Protector, sync_events=None):
    """블록 레벨 보호(코드펜스/주석/수식·표 환경)를 순서대로 적용한다.

    sync_events 가 딕셔너리로 주어지면(--syncinfo 전용) 각 단계가 만든
    줄 축약 이벤트를 그 단계 이름 아래에 쌓는다. 각 단계는 "그 단계가
    시작하는 시점의 텍스트" 기준 줄 번호로 이벤트를 기록하므로, 호출하는
    쪽에서 LineOriginMap.apply_shrink() 를 정확히 이 순서대로(코드펜스 ->
    주석/라인코멘트 -> 수식·표 환경) 적용해야 누적 결과가 맞는다.
    """
    text = extract_code_fences(
        text, cfg, pr,
        sync_events=sync_events.setdefault("fence", []) if sync_events is not None else None,
    )
    # 주석 제거는 코드펜스 보호 바로 다음, 다른 raw 보호(수식/표 환경)보다
    # 먼저 실행한다 — 주석 안에 우연히 \begin{...}\end{...} 같은 텍스트가
    # 있어도 그게 raw 환경으로 오인식되기 전에 통째로 사라져야 하기 때문.
    if sync_events is not None:
        # COMMENT_RE.sub("", text) 는 매치가 정확히 한 줄 전체를 차지해도
        # 그 줄 자체(개행)는 지우지 않는다 — 매치가 개행을 포함하지 않으니
        # 그 줄은 "내용만 빈 줄"로 남는다. 실제로 줄어드는 것은 매치가
        # 여러 줄에 걸쳐 그 사이 개행까지 삼킨 경우(<!--\n...\n--> 형태의
        # 블록 주석)뿐이고, 그 경우도 결과는 항상 1줄이다. 그래서 new_len
        # 은 0이 아니라 1이다 — 처음에 0으로 잘못 넣어서 그 뒤에 오는 모든
        # 줄이 하나씩 밀리는 버그를 실측으로 잡았다(LINECOMMENT_RE는 정규식
        # 자체에 \n? 이 있어 진짜로 줄이 사라지므로 0이 맞다 — 아래 참고).
        sync_events.setdefault("comment", []).extend(
            _line_events_for_full_line_matches(text, COMMENT_RE, 1))
    text = COMMENT_RE.sub("", text)
    if cfg.get("linecomment"):
        if sync_events is not None:
            sync_events.setdefault("linecomment", []).extend(
                _line_events_for_full_line_matches(text, LINECOMMENT_RE, 0))
        text = LINECOMMENT_RE.sub("", text)
    # sync_events 기록도 반드시 마스킹된 사본(masked) 기준으로 해야
    # 한다 — 원본 text를 그대로 쓰면 인라인 코드 스팬 안의 가짜 매치가
    # --syncinfo의 줄 계산에도 그대로 흘러든다(_protect_regex_outside_code
    # 의 docstring 참고). 그래서 치환을 먼저 하고, 그때 함께 얻은
    # masked로 이벤트를 기록하는 순서로 뒤집었다.
    text, masked = _protect_regex_outside_code(text, MATH_ENV_RE, pr.protect)
    if sync_events is not None:
        sync_events.setdefault("mathenv", []).extend(
            _line_events_for_full_line_matches(masked, MATH_ENV_RE, 1))
    text, masked = _protect_regex_outside_code(text, TABLE_ENV_RE, pr.protect)
    if sync_events is not None:
        sync_events.setdefault("tableenv", []).extend(
            _line_events_for_full_line_matches(masked, TABLE_ENV_RE, 1))
    text, masked = _protect_regex_outside_code(text, DISPLAY_MATH_RE, pr.protect)
    if sync_events is not None:
        sync_events.setdefault("dispmath", []).extend(
            _line_events_for_full_line_matches(masked, DISPLAY_MATH_RE, 1))
    return text


# 각주 정의. 식별자는 라틴 알파벳/숫자/밑줄/붙임표/한글 음절만 쓸 수 있다.
# 공백을 안 넣는 것이 핵심이다 — [^...] 문법은 "참조"와 "즉석(인라인) 각주
# 본문"을 똑같은 대괄호 모양으로 겸하는데(바로 아래 do_footnote 참고), 이
# 둘을 가르는 것은 오직 "그 안의 문자열이 이미 정의된 식별자와 일치하는가"
# 뿐이다. 식별자에 공백이 들어가면 "이게 짧은 참조 식별자인지 아니면 그
# 자리에서 바로 쓴 여러 단어짜리 각주 본문인지"가 시각적으로도, 그리고
# 코드 판정 기준으로도 구분이 안 된다 — 반대로 공백 없는 한글은 그런
# 모호성이 없어서(ASCII 식별자와 똑같은 성격) 안전하게 허용할 수 있다.
# "가-힣"은 완성형 한글 음절 전체(U+AC00~U+D7A3) 범위다.
FOOTNOTE_DEF_RE = re.compile(r"^\[\^([A-Za-z0-9_\-가-힣]+)\]:\s?(.*)$")

# 정의처럼 생겼지만 식별자가 위 제한을 벗어난 줄을 찾아내기 위한 느슨한 패턴.
# 그냥 두면 정의로 수집되지 않은 채 본문에 남고, 게다가 인라인 각주 규칙에
# 걸려 그 줄까지 \footnote 로 둔갑한다 — 참조와 정의가 각각 엉뚱한 각주가
# 되어 조용히 이중으로 깨진다. 그래서 경고만이라도 띄운다.
_FOOTNOTE_DEF_LOOSE_RE = re.compile(r"^\[\^([^\]\n]+)\]:\s")

def extract_footnotes(text, sync_events=None):
    lines = text.split("\n")
    defs = {}
    out_lines = []
    i = 0
    while i < len(lines):
        m = FOOTNOTE_DEF_RE.match(lines[i])
        if m:
            def_start = i
            fid = m.group(1)
            parts = [m.group(2)]
            i += 1
            while i < len(lines) and (lines[i].startswith("    ") or lines[i].startswith("\t")):
                parts.append(lines[i].strip())
                i += 1
            defs[fid] = " ".join(p for p in parts if p != "").strip()
            if sync_events is not None:
                sync_events.append((def_start, i, 0))
            continue

        loose = _FOOTNOTE_DEF_LOOSE_RE.match(lines[i])
        if loose:
            print(
                f"경고: 각주 정의 '[^{loose.group(1)}]:' 의 식별자에 쓸 수 없는 "
                f"문자가 있습니다. 라틴 알파벳·숫자·밑줄(_)·붙임표(-)·한글만 됩니다. "
                f"이 줄은 정의로 수집되지 않고 본문에 그대로 남습니다.",
                file=sys.stderr,
            )

        out_lines.append(lines[i])
        i += 1
    return "\n".join(out_lines), defs


def extract_reference_defs(text, sync_events=None):
    """MultiMarkdown식 tagged reference 정의(`[라벨]: 값`)를 걷어내고,
    본문에서 제거한 뒤 {라벨: 값} 딕셔너리를 함께 돌려준다.

    extract_footnotes()와 거의 같은 얼개다 — 다만 여러 줄 이어쓰기는
    지원하지 않는다(각주 본문과 달리, 이미지 경로+속성이나 URL은 한
    줄을 넘길 일이 실무에서 거의 없다고 보았다). 값 자체가 "이미지
    정의인지 링크 정의인지"는 여기서 가르지 않는다 — 같은 라벨 풀을
    이미지 참조(![alt][라벨])와 링크 참조([text][라벨])가 공유하고,
    실제로 어느 쪽으로 해석할지는 참조하는 쪽(do_figure_ref/do_link_ref)
    이 결정한다. MultiMarkdown 자신도 이렇게 하나의 라벨 풀을 공유한다.
    """
    lines = text.split("\n")
    defs = {}
    out_lines = []
    for i, line in enumerate(lines):
        m = REF_DEF_RE.match(line)
        if m:
            defs[m.group(1)] = m.group(2).strip()
            if sync_events is not None:
                sync_events.append((i, i + 1, 0))
            continue
        out_lines.append(line)
    return "\n".join(out_lines), defs


# --------------------------------------------------------------------------
# 4. 인라인 처리
# --------------------------------------------------------------------------

INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_BACKTICK_RUN_RE = re.compile(r"`+")


# 코드 스팬 바로 뒤에 붙는 raw attribute. Pandoc의 `...`{=latex} 문법이다.
# 닫는 백틱과 여는 중괄호 사이에 공백이 있으면 안 된다 — 붙어 있어야만
# "이 스팬은 코드가 아니라 raw"라는 표시로 본다.
_RAW_ATTR_RE = re.compile(r"\{=([a-zA-Z][a-zA-Z0-9_+-]*)\}")


def protect_inline_code(text, cfg, local):
    """인라인 코드 스팬을 CommonMark 방식으로 처리한다.

    이전에는 "`([^`\\n]+)`" 처럼 백틱 하나만을 델리미터로 취급했다. 이 때문에
    `` `code` `` 처럼(내용에 리터럴 백틱을 넣을 때 쓰는 표준 표기, 백틱 두
    개로 감싸서 안쪽의 단일 백틱과 구분함) 겹쳐 쓴 백틱을 만나면, 그 안쪽의
    단일 백틱들을 델리미터로 오인해서 코드 스팬이 완전히 깨져버렸다.

    CommonMark와 동일하게: 여는 백틱의 개수(N)를 기록해두고, 그 뒤로 정확히
    같은 개수(N)의 백틱으로 이루어진 "런(run)"이 나와야 닫는 델리미터로
    인정한다. 그보다 짧거나 긴 백틱 런은 그대로 내용에 흡수된다. 같은 길이의
    닫는 런을 끝내 못 찾으면, 그 백틱들은 그냥 리터럴 문자로 남긴다. 코드
    스팬은 한 줄 안에서만 성립하므로 줄바꿈은 건너뛰지 않는다.

    \\` (백슬래시+백틱)는 "백틱 그 자체"를 리터럴로 출력하는 이스케이프다.
    단, 이 이스케이프는 **새 코드 스팬을 찾는 바깥쪽 루프에서만** 적용한다.
    이미 열린 스팬의 닫는 델리미터를 찾는 안쪽 루프에서는 적용하지 않는데,
    CommonMark에서도 코드 스팬 내용 안에서는 백슬래시 이스케이프가 적용되지
    않기 때문이다 — 이 구분이 없으면 `` `\\` `` 처럼 내용이 백슬래시로
    끝나는 정상적인 코드 스팬(예: TeX 줄바꿈 명령 \\\\ 를 보여주는 경우)의
    닫는 백틱을 이스케이프로 오인해서 스팬이 깨져버린다.
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == "\\" and i + 1 < n and text[i + 1] == "`":
            out.append(local.protect("`"))
            i += 2
            continue

        m = _BACKTICK_RUN_RE.match(text, i)
        if not m:
            out.append(text[i])
            i += 1
            continue

        run_len = m.end() - m.start()
        j = m.end()
        close_start = close_end = None
        while j < n and text[j] != "\n":
            m2 = _BACKTICK_RUN_RE.match(text, j)
            if m2:
                if (m2.end() - m2.start()) == run_len:
                    close_start, close_end = m2.start(), m2.end()
                    break
                j = m2.end()
            else:
                j += 1

        if close_start is None:
            # 짝이 맞는 닫는 백틱 런을 못 찾았다 — 코드 스팬이 아니라 그냥
            # 리터럴 백틱 문자들로 취급하고 계속 진행한다.
            out.append(text[m.start():m.end()])
            i = m.end()
            continue

        content = text[m.end():close_start]
        # CommonMark 관례: 내용이 스페이스로 시작·끝나고 전부 스페이스는
        # 아니면 양쪽 한 칸씩 벗겨낸다. 이 패딩 덕분에 내용이 백틱으로
        # 시작/끝나도 델리미터와 헷갈리지 않는다.
        if len(content) >= 2 and content[0] == " " and content[-1] == " " and content.strip(" "):
            content = content[1:-1]

        # 닫는 백틱에 `{=포맷}`이 붙어 있으면 코드 스팬이 아니라 인라인 raw
        # 스팬이다. 문장 한복판에 LaTeX 조각을 그대로 심는 탈출구로,
        # `\명령{인자}` 매크로 패턴에 걸리지 않는 것들(그룹 중괄호, 2단
        # 이상 중첩, 중괄호 뒤 선택인자 등)을 쓸 때 필요하다.
        raw_m = _RAW_ATTR_RE.match(text, close_end)
        if raw_m:
            if raw_m.group(1).lower() in cfg.get("raw_inline_formats", ()):
                out.append(local.protect(content))
            # 다른 포맷을 겨냥한 조각(예: `<br>`{=html})은 Pandoc과 똑같이
            # 통째로 버린다. LaTeX 출력에 넣을 자리가 없기 때문이다.
            i = raw_m.end()
            continue

        escaped = content.replace("\\", "\x00")
        # 코드 스팬 안의 ~ 는 묶음빈칸이 아니라 "눈에 보이는 물결표"여야 한다.
        # 코드를 그대로 보여주는 자리이기 때문이다. 그래서 escape_chars에서
        # ~ 가 빠져 있어도 여기서는 항상 이스케이프한다.
        escaped = escape_text(escaped, _with_tilde(cfg["escape_chars"]))
        escaped = escaped.replace("\x00", r"\textbackslash{}")
        out.append(local.protect(r"\texttt{%s}" % escaped))
        i = close_end
    return "".join(out)
INLINE_MATH_RE = re.compile(r"(\$[^$\n]+?\$|\\\([^)]*?\\\))")


def build_macro_re(cfg):
    """MACRO_RE를 cfg 기준으로 매번 새로 만든다.

    이름이 있는(`\\[a-zA-Z]+...`) 일반 매크로와, `\\,`/`\\;`처럼 고정된
    구두점 이스케이프는 그대로 두고, cfg["literal_macros"] +
    cfg["extra_macros"]로 "이름이 없는(non-alphabetic) 리터럴 매크로
    토큰"(예: `\\<`, 한국어 조사 매크로) 목록을 만든다. 이 목록은
    mapping.yaml로 자유롭게 커스터마이즈될 수 있으므로 모듈 레벨 상수로
    고정하지 않는다. 프리픽스 충돌 방지를 위해 긴 토큰부터 매치하도록
    길이 내림차순으로 정렬한다(`\\으로`를 `\\로`보다 먼저 두는 것과 같은
    이유 — 사용자가 mapping.yaml에 순서를 신경 써서 적을 필요는 없다).

    여기에 더해 `\\이름{}` 꼴의 **빈 그룹 종결자**를 인식한다. TeX에서
    제어열의 끝을 표시하면서 공백은 넣지 않는 표준 관용구이고, 영문
    이름에서는 위 첫 번째 패턴이 이미 처리해왔다(`\\LaTeX{}의`). 이름에
    한글이 섞이면 첫 패턴에 안 걸리므로 별도 대안으로 둔다.

    이 종결자가 있으면 리터럴 목록에 없는 이름도 통과한다. 목록이 필요했던
    이유가 "어디까지가 매크로 이름인지 알 수 없어서"였는데, `{}`는 작성자가
    그 경계를 직접 선언한 것이라 추측할 필요가 없기 때문이다. 조사 매크로의
    활용형(`\\이라{}고`, `\\이라{}는` …)처럼 경우의 수가 너무 많아 목록으로
    감당할 수 없는 것들을 위한 탈출구다. 같은 이유로 `\\이름{인자}`처럼
    인자를 받는 한글 이름 매크로도 함께 통과한다.
    """
    literal_tokens = list(cfg.get("literal_macros", [])) + list(cfg.get("extra_macros", []))
    literal_tokens.sort(key=len, reverse=True)
    parts = [
        # 선택인자 대괄호는 **여러 개** 올 수 있다. natbib의 prenote+postnote
        # (\citep[see][p.~33]{key})가 대표적인데, 예전에는 하나만 허용해서
        # 두 번째 대괄호부터 매치가 끊기고 뒤의 중괄호가 \{ \} 로
        # 이스케이프되는 깨진 출력이 나왔다.
        r"\\[a-zA-Z]+\*?"
        r"(?:\[[^\]\n]*\])*"
        r"(?:\{(?:[^{}]|\{[^{}]*\})*\})*",
        # 한글 이름 매크로 + 중괄호. 위 ASCII 패턴 다음에 와야 한다 —
        # 먼저 두면 \textbf{}{x} 같은 것을 \textbf{} 까지만 끊어버린다.
        #
        # 중괄호 그룹이 **최소 하나는 있어야** 한다. + 가 아니라 * 였다면
        # 맨 \한글 을 전부 매크로로 보게 되어, 리터럴 목록을 둔 이유였던
        # 그리디 매칭 위험이 그대로 되살아난다. 빈 그룹 \이라{} 는 TeX의
        # 표준 종결자 관용구이고 \이름{인자} 도 같은 규칙으로 받는데,
        # 어느 쪽이든 중괄호가 작성자의 "이름은 여기까지" 선언이다.
        #
        # 이름에는 한글 음절(U+AC00~U+D7A3)과 옛한글 자모(U+1100~U+11FF)를
        # 허용한다.
        r"\\[a-zA-Z\uAC00-\uD7A3\u1100-\u11FF]+\*?"
        r"(?:\[[^\]\n]*\])?"
        r"(?:\{(?:[^{}]|\{[^{}]*\})*\})+",
        r"\\\\|\\,|\\;|\\%|\\&|\\#|\\_|\\\{|\\\}",
    ]
    if literal_tokens:
        parts.append("|".join(re.escape(tok) for tok in literal_tokens))
    return re.compile("(" + "|".join(parts) + ")")


# --------------------------------------------------------------------------
# 그림 파일 내려받기와 형식 변환
# --------------------------------------------------------------------------
#
# 세 가지 걱정거리를 서로 다른 스위치로 나눠 둔다.
#
#   네트워크 접근 : --fetch-images   (기본 꺼짐)
#   형식 변환     : 옵션 없음. Pillow가 있으면 한다  (기본 켜짐)
#   애니메이션    : --animation[=N]  (기본 꺼짐, N 기본 40)
#
# 다운로드만 옵트인인 이유는 재현성이 아니라 보안이다. 남이 준 .md를 변환하는
# 것만으로 임의 주소에 요청이 나가면 곤란하다. 반면 형식 변환은 파일 하나를
# 더 만드는 일일 뿐이고, 로컬 .webp 를 쓴 사람이 URL도 안 쓰면서 다운로드
# 옵션을 켜야 하는 것은 이상하다.
#
# 변환본은 **원본이 있는 곳에** 나란히 만든다. URL로 받은 것은 _images/ 에,
# 로컬 파일을 변환한 것은 그 파일 옆에. 기준이 하나라 설명하기 쉽고, 원본이
# 남으므로 나중에 더 나은 도구로 다시 변환할 여지도 남는다.

IMAGE_CACHE_DIR = "_images"

# LaTeX(pdftex/xetex/luatex)이 그대로 받는 형식. bmp가 여기 있는 것은 실측
# 결과다 — 흔한 오해와 달리 xelatex은 bmp를 받는다.
_TEX_READY_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".eps", ".ps", ".bmp", ".mps"}

# Pillow로 PNG로 바꿔줄 수 있는 형식.
_CONVERTIBLE_EXT = {".tif", ".tiff", ".webp", ".gif"}

# 벡터라 래스터화가 손해이고, PDF로 바꾸려면 외부 도구(inkscape, rsvg-convert)
# 가 있어야 한다. 받아만 두고 저자에게 넘긴다.
_HANDOFF_EXT = {".svg", ".svgz", ".ai", ".psd"}

_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")

# Content-Type -> 확장자. URL 경로의 확장자를 믿을 수 없을 때 쓴다.
_CTYPE_EXT = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
    "image/webp": ".webp", "image/tiff": ".tiff", "image/bmp": ".bmp",
    "image/svg+xml": ".svg", "application/pdf": ".pdf",
}


def _pillow():
    """Pillow를 필요할 때만 불러온다. 없으면 None."""
    try:
        from PIL import Image, ImageSequence
        return Image, ImageSequence
    except ImportError:
        return None


def is_image_url(path):
    return bool(_URL_RE.match(str(path).strip()))


def _cache_name(url, ext):
    """URL에서 결정적인 파일 이름을 만든다.

    URL 마지막 조각을 그대로 쓰면 안 된다. 다른 출처에도 330px-... 같은 이름이
    얼마든지 있고, 퍼센트 인코딩과 유니코드가 파일 이름이 되면 그것대로
    골칫거리다. 해시는 충돌이 없고 "이미 받았나" 판정도 공짜로 된다.
    """
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return h + ext


def cached_image(url, base_dir):
    """이미 받아둔 그림이 있으면 그 경로를, 없으면 None.

    확장자를 미리 알 수 없으므로 후보를 차례로 뒤진다. 경로에서 얻은 확장자를
    먼저 보고, 그다음 우리가 다룰 줄 아는 형식들을 훑는다.

    이 조회는 네트워크를 쓰지 않는다. 그래서 --fetch-images 가 없어도 한다 —
    옵션이 막으려는 것은 바깥으로 나가는 요청이지, 이미 손에 있는 파일을
    쓰는 일이 아니다.
    """
    cache = Path(base_dir) / IMAGE_CACHE_DIR
    guess = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if guess:
        cand = cache / _cache_name(url, guess)
        if cand.is_file():
            return cand
    for ext in sorted(_TEX_READY_EXT | _CONVERTIBLE_EXT | _HANDOFF_EXT):
        cand = cache / _cache_name(url, ext)
        if cand.is_file():
            return cand
    return None


def fetch_image(url, base_dir):
    """URL 그림을 내려받아 로컬 경로를 돌려준다. 실패하면 ImageError.

    이미 받아둔 것이 있으면 네트워크를 쓰지 않는다. 두 번째 빌드부터는
    오프라인에서도 된다.
    """
    cache = Path(base_dir) / IMAGE_CACHE_DIR

    hit = cached_image(url, base_dir)
    if hit is not None:
        return hit
    guess = Path(urllib.parse.urlparse(url).path).suffix.lower()

    req = urllib.request.Request(url, headers={
        # User-Agent 없는 요청을 막는 곳이 많다(위키미디어가 그렇다).
        "User-Agent": f"ndhmd4tex/{__version__} (+https://github.com/)",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            data = resp.read()
    except Exception as e:
        raise ImageError(f"그림을 내려받지 못했습니다: {url}\n  {type(e).__name__}: {e}")

    # 확장자는 Content-Type을 먼저 믿는다. URL 경로의 확장자는 없거나 틀릴 수
    # 있고, 404 페이지가 200으로 오는 경우도 있다.
    ext = _CTYPE_EXT.get(ctype) or guess
    if not ext:
        raise ImageError(
            f"그림의 형식을 알 수 없습니다: {url}\n"
            f"  Content-Type: {ctype or '(없음)'} — URL에도 확장자가 없습니다.")
    if ctype and ctype.startswith("text/"):
        raise ImageError(
            f"그림이 아니라 문서가 돌아왔습니다: {url}\n"
            f"  Content-Type: {ctype} — 주소가 맞는지 확인하십시오.")

    try:
        cache.mkdir(parents=True, exist_ok=True)
        target = cache / _cache_name(url, ext)
        target.write_bytes(data)
    except OSError as e:
        raise ImageError(f"내려받은 그림을 저장하지 못했습니다: {e}")
    print(f"내려받음: {url}\n  -> {target}", file=sys.stderr)
    return target


def _split_animation(src, frames_limit):
    """애니메이션을 프레임 PNG로 쪼갠다. (접두사, 마지막번호, 총프레임) 또는 None.

    프레임은 **앞에서부터** frames_limit 개만 쓴다. 솎아내면 루프는 온전해지지만
    타이밍이 한 번 더 뭉개지는데, \animategraphics 가 이미 단일 fps만 받아
    프레임별 지연을 잃은 뒤다. 두 번 뭉개느니 단순한 쪽을 고른다.

    이미 뽑아둔 프레임을 재활용한다. GIF 자체를 여는 것(총 프레임 수를 아는
    것)은 싸지만, 프레임 하나하나를 PNG로 인코딩해 쓰는 것은 비싸다 — 매
    빌드마다 다시 하면 프레임이 많은 GIF에서 체감될 정도다. 그래서 "필요한
    수만큼 이미 있으면 인코딩을 건너뛴다."

    판단은 개수만으로 한다. 원본 GIF나 --animation 값이 바뀌었는데 우연히
    프레임 수가 같은 극단적인 경우는 놓칠 수 있지만, 그런 우연은 실무에서
    무시할 만하고, 폴더를 지우면 언제든 다시 뽑힌다.
    """
    mods = _pillow()
    if mods is None:
        return None
    Image, ImageSequence = mods
    try:
        im = Image.open(src)
        total = getattr(im, "n_frames", 1)
        if total <= 1:
            return None
        outdir = src.parent / (src.stem + src.suffix.replace(".", "-") + "-frames")
        n = total if frames_limit is None else min(total, frames_limit)

        # 캐시 판단: 0..n-1 프레임이 전부 이미 있으면 다시 인코딩하지 않는다.
        # "이미 30장 있는데 20장만 필요" 는 재활용(앞쪽 20장이 그대로 맞다),
        # "이미 20장 있는데 30장 필요" 는 재활용 불가 — 뒤 10장이 없으므로
        # 처음부터 다시 뽑는다(이어 뽑지 않는 이유: GIF 프레임은 이전 프레임에
        # 누적되는 경우가 있어 중간부터 이어 여는 것이 항상 안전하지 않다).
        if outdir.is_dir() and all((outdir / f"{i}.png").is_file() for i in range(n)):
            return (outdir.as_posix() + "/", n - 1, total)

        outdir.mkdir(parents=True, exist_ok=True)
        for i, fr in enumerate(ImageSequence.Iterator(im)):
            if i >= n:
                break
            fr.convert("RGB").save(outdir / f"{i}.png")
        # \animategraphics 는 접두사 뒤에 번호를 바로 붙인다. 구분자를 직접
        # 넣어야 하고, LaTeX 경로는 윈도우에서도 슬래시를 쓴다.
        return (outdir.as_posix() + "/", n - 1, total)
    except Exception as e:
        print(f"경고: 애니메이션을 쪼개지 못했습니다: {src}\n  {e}", file=sys.stderr)
        return None


def prepare_image(path, base_dir, cfg=None, fetch=False, animation=False):
    """그림 경로를 LaTeX이 쓸 수 있는 형태로 손질한다.

    (경로, 애니메이션정보) 를 돌려준다. 애니메이션정보는
    (프레임접두사, 마지막번호, 총프레임) 또는 None.
    """
    raw = str(path).strip()

    if is_image_url(raw):
        if fetch:
            local = fetch_image(raw, base_dir)
        else:
            # 내려받지는 않되, 예전에 받아둔 것이 있으면 그것을 쓴다.
            local = cached_image(raw, base_dir)
            if local is None:
                raise ImageError(
                    f"URL로 준 그림은 그대로 쓸 수 없습니다: {raw}\n"
                    f"  {Path(base_dir) / IMAGE_CACHE_DIR} 에 받아둔 것도 없습니다.\n"
                    f"  --fetch-images 로 내려받거나, 파일을 직접 받아 두십시오.")
    else:
        cand = Path(raw)
        local = cand if cand.is_absolute() else Path(base_dir) / cand
        if not local.is_file():
            # 확장자를 뺀 채 적는 관행이 있다(\includegraphics 가 찾아 준다).
            # 그때는 손대지 않고 그대로 넘긴다.
            return raw, None

    ext = local.suffix.lower()

    if ext in _HANDOFF_EXT:
        raise ImageError(
            f"LaTeX에 바로 넣을 수 없는 형식입니다: {local}\n"
            f"  파일은 그대로 두었습니다. PDF로 바꾸거나(inkscape --export-type=pdf),\n"
            f"  \\usepackage{{svg}} 와 -shell-escape 를 쓰거나, 다른 그림을 쓰십시오.")

    if ext in _CONVERTIBLE_EXT:
        mods = _pillow()
        if mods is None:
            raise ImageError(
                f"LaTeX에 바로 넣을 수 없는 형식입니다: {local}\n"
                f"  파일은 그대로 두었습니다. Pillow 를 설치하면 자동으로 바꿔 줍니다\n"
                f"  (pip install Pillow).")
        Image, _ = mods

        # animation 은 세 상태다: False = 끔, None = 상한 없음, 정수 = 상한.
        if animation is not False:
            info = _split_animation(local, animation)
            if info is not None:
                prefix, last, total = info
                base = Path(base_dir).resolve()
                try:
                    prefix = (Path(prefix).resolve().relative_to(base)).as_posix() + "/"
                except (ValueError, OSError):
                    pass
                return Path(local).as_posix(), (prefix, last, total)

        # 원본 확장자를 이름에 남긴다. p.webp 와 p.tiff 가 나란히 있을 때
        # 둘 다 p.png 가 되어 서로 덮어쓰는 것을 막는다.
        target = local.with_name(local.stem + local.suffix.replace(".", "-") + ".png")
        if not target.is_file():
            try:
                Image.open(local).convert("RGB").save(target)
            except Exception as e:
                raise ImageError(f"그림을 바꾸지 못했습니다: {local}\n  {e}")
            note = ""
            try:
                n = getattr(Image.open(local), "n_frames", 1)
                if n > 1:
                    note = f" (프레임 {n} 중 첫 장만)"
            except Exception:
                pass
            print(f"변환: {local} -> {target}{note}", file=sys.stderr)
        return _relpath(target, base_dir), None

    if ext and ext not in _TEX_READY_EXT:
        print(f"경고: LaTeX이 다루지 못할 수 있는 형식입니다: {local}", file=sys.stderr)

    return _relpath(local, base_dir), None


def _relpath(target, base_dir):
    r"""가능하면 문서 기준 상대경로로. .tex 이 옮겨 다녀도 덜 깨진다.

    구분자는 **반드시 슬래시**여야 한다. LaTeX 소스의 경로 구분자는 운영체제와
    무관하게 / 이고, 역슬래시는 제어열의 시작으로 읽힌다. str(Path) 는 윈도우
    에서 역슬래시를 내주므로 _images\dn.jpg 같은 것이 나가고, LaTeX은 그것을
    \d 라는 정의되지 않은 명령으로 읽는다. as_posix() 는 윈도우에서도 슬래시를
    주고, C:/... 형태는 LaTeX이 그대로 받는다.
    """
    try:
        return Path(target).resolve().relative_to(Path(base_dir).resolve()).as_posix()
    except (ValueError, OSError):
        return Path(target).as_posix()


# 속성부는 중괄호를 **한 겹까지** 품는다. inlinespec="strut={()}" 처럼 값 안에
# 중괄호가 드는 경우가 있는데, [^}]* 로는 첫 } 에서 끊겨 속성이 반토막 난다.
# 대체텍스트 자리도 대괄호를 한 겹까지 품는다. ![[표시](url)](img.png) 처럼
# 링크를 캡션으로 감싼 그림을 쓸 수 있게 하기 위해서다. 한 겹까지만
# 허용하는 이유는 wrapspec="strut={()}" 같은 속성부의 중괄호 규칙과 같다 —
# 완전한 재귀 매칭은 정규식으로 안전하게 할 수 없고, 실무에서 그 이상
# 중첩될 일도 없다.
FIGURE_RE = re.compile(
    r"!\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\(([^)\s]+)\)"
    r"(?:\{((?:[^{}]|\{[^{}]*\})*)\})?")
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

# MultiMarkdown식 "tagged reference"(같은 대상을 여러 번 참조할 때, 경로나
# URL을 한 곳에 정의해 두고 짧은 라벨로 재사용하는 문법). 예:
#
#   ![그림 설명][myfig]
#   ...
#   [myfig]: figurename.png width=3cm,respectratio
#
#   자세히 알고 싶으면 [][Markdown]을 보라.
#   ...
#   [Markdown]: https://en.wikipedia.org/wiki/MultiMarkdown
#
# 대괄호 **한 겹짜리** shortcut(`[Markdown]` 단독, 뒤에 `(...)`도 `[...]`
# 도 없이)은 일부러 지원하지 않는다 — 산문에서 강조나 메모 삼아 대괄호
# 하나만 쓰는 경우와 구별할 방법이 없어서, 이 방언 전체의 "명시적 문법만
# 인정한다"는 태도와 어긋난다. 대신 대괄호 **두 겹**(`][` 시퀀스, 표시
# 텍스트가 비어 있어도 됨)만 받는다 — 이 시퀀스는 일반 산문에 사실상
# 나타나지 않아 모호함이 없다(`[[...]]` 색인, `[^...]` 각주, `[#...]`
# 상호참조 전부 시작 문자가 달라서 이 정규식과 겹치지 않는다).
#
# 라벨 자리에 (?!\^) 를 둔 이유: `[텍스트][^id]`처럼 각주 참조 바로
# 앞에 다른 대괄호가 있는 경우, 이 정규식이 `^id`를 참조 라벨로
# 가로채면 안 된다 — 각주 네임스페이스는 항상 각주 규칙에 맡긴다.
#
# FIGURE_REF_RE 는 반드시 LINK_REF_RE 보다 먼저 처리해야 한다 —
# `![alt][label]`을 LINK_REF_RE 가 먼저 보면 `!` 를 무시하고
# `[alt][label]` 부분만 링크로 잘못 삼킬 수 있다(기존 FIGURE_RE가
# LINK_RE보다 먼저 처리되는 것과 같은 이유).
# 뒤에 `]` 바로 붙은 `{속성}`을 받는다(`![캡션](x.png){...}`의 FIGURE_RE와
# 같은 규칙 — 띄우면 속성이 아니라 본문이다). 정의 줄의 속성이 공유 기본값,
# 이쪽이 이 사용처만의 값이다.
FIGURE_REF_RE = re.compile(
    r"!\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\[(?!\^)([^\[\]]+)\]"
    r"(?:\{((?:[^{}]|\{[^{}]*\})*)\})?")
LINK_REF_RE = re.compile(r"\[([^\[\]]*)\]\[(?!\^)([^\[\]]+)\]")

# 참조 정의 줄: `[라벨]: 값`. `(?!\^)`로 각주 정의(`[^id]: ...`)와 겹치지
# 않게 한다 — 두 스캔이 실행되는 순서와 무관하게 항상 서로 배타적이게
# 하려는 것이다.
REF_DEF_RE = re.compile(r"^\[(?!\^)([^\[\]]+)\]:\s?(.*)$")

# 이미지 참조 정의의 값: 첫 토큰이 경로, 그 뒤(있으면)가 그대로
# parse_figure_attrs() 에 넘길 속성 문자열이다. 중괄호로 감싸지 않는다 —
# REF_DEF_RE 자체가 한 줄 전체를 이미 이 값으로 캡처해 왔으므로 또
# 감쌀 필요가 없다.
_REF_DEF_VALUE_RE = re.compile(r"^(\S+)\s*(.*)$")

# 링크 참조 정의의 값: URL 하나(뒤에 따옴표 붙은 제목이 있으면 버린다 —
# 인라인 링크의 제목처럼, 이 방언은 애초에 제목을 쓰지 않는다).
_REF_LINK_DEF_VALUE_RE = re.compile(r"^(\S+)(?:\s+\"[^\"]*\")?\s*$")

# 대괄호 안 내용에 제한을 두지 않는다. 식별자면 참조로, 아니면 인라인 각주
# 본문으로 읽는다(do_footnote 참고). 예전에는 [A-Za-z0-9_-]+ 만 받아서
# [^각주 텍스트] 같은 한국어 인라인 각주가 아예 매치되지 않았고, ^ 가
# \textasciicircum{} 으로 이스케이프된 채 대괄호와 함께 본문에 그대로
# 남았다. 닫는 대괄호와 줄바꿈만 못 들어간다.
# 대괄호 안 내용에 **대괄호 한 겹까지** 허용한다. 그래야 각주 본문에
# [#라벨] 같은 상호참조나 [용어설명] 같은 대괄호 표기를 넣을 수 있다.
# 예전 [^\]\n]+ 는 첫 ] 에서 끊겨 [^각주에 [#sec:a] 참조] 가
# \footnote{각주에 [\#sec:a} 참조] 라는 깨진 결과를 냈다.
# + 이지 * 가 아니다. 빈 [^] 나 ^[] 까지 각주로 잡으면 \footnote{} 라는
# 빈 각주가 생긴다. 예전 [^\]\n]+ 도 최소 한 글자를 요구했으므로 그 성질을
# 그대로 유지한다.
_BRACKET_BODY = r"(?:[^\[\]\n]|\[[^\[\]\n]*\])+"

FOOTNOTE_REF_RE = re.compile(r"\[\^(" + _BRACKET_BODY + r")\]")

# Pandoc의 인라인 각주 문법. 참조와 헷갈릴 여지가 없는 형태라, 새로 쓰는
# 원고에서 의도를 분명히 하고 싶을 때 쓴다. --pandoc 모드와도 표기가 같다.
#
# 앞의 (?<!\^) 가 핵심이다. 이것이 없으면 방점 ^^...^^ 의 닫는 캐럿 둘 중
# 뒤엣것이 바로 뒤 대괄호와 붙어 각주로 오인된다.
#
#   ^^르베그 적분^^[[|르베그 측도]]
#                 ~~ 여기서 ^[ 가 잡혀 색인 마크업을 통째로 먹었다
#
# 방점 규칙은 인라인 서식 루프(맨 뒤)에서 돌기 때문에 이 시점에는 아직
# ^^ 가 살아 있다. 캐럿 바로 뒤에 오는 ^[ 는 각주가 아니라고 보면
# 방점 뒤에 색인·상호참조가 붙는 흔한 조합이 전부 살아난다.
INLINE_FOOTNOTE_RE = re.compile(r"(?<!\^)\^\[(" + _BRACKET_BODY + r")\]")
# 꼬리표가 붙을 수 있는 꼴. 꼬리표 {..} 는 중괄호 한 겹, 줄 안에서만.
INLINE_FOOTNOTE_TAG_RE = re.compile(INLINE_FOOTNOTE_RE.pattern + r"(?:\{([^{}\n]*)\})?")
FOOTNOTE_REF_TAG_RE = re.compile(FOOTNOTE_REF_RE.pattern + r"(?:\{([^{}\n]*)\})?")
INDEX_RE = re.compile(r"\[\[(.*?)(?:\|(.*?))?\]\]")

# 어디든 붙일 수 있는 인라인 라벨. {#id} 는 pandoc에서 헤딩·스팬 전용
# 속성이지만, 여기서는 **인라인 어디서든** \label{id} 로 바뀐다 — 리스트
# 항목이나 각주처럼 전용 속성 문법이 없는 자리를 위한 것이다. 라벨 이름은
# pandoc/일반 관례를 따라 영숫자·:·_·-·. 만 받는다(공백이나 다른 특수문자가
# 들어간 잘못된 사용을 조용히 통과시키지 않기 위해).
INLINE_LABEL_RE = re.compile(r"\{#([A-Za-z0-9:_.-]+)\}")


def build_refcite_re(cfg, with_rawopt=False):
    """cfg["refcite"]의 프리픽스들로 [prefix라벨] 정규식을 만든다.

    프리픽스가 mapping.yaml로 자유롭게 추가/변경될 수 있으므로 모듈
    레벨 상수로 고정하지 않고 매번 cfg 기준으로 새로 만든다. 긴 프리픽스를
    먼저 시도하도록 길이 내림차순으로 정렬해둔다 — 지금 기본 프리픽스들
    사이에는 실제 충돌이 없지만(예: "#"와 "page:"), 사용자가 mapping.yaml에
    서로 겹치는 프리픽스(예: "c:"와 "cref:")를 추가할 가능성에 대비한
    방어적 조치다(\\으로/\\로 처리와 같은 이유).
    """
    prefixes = sorted(cfg["refcite"].keys(), key=len, reverse=True)
    alt = "|".join(re.escape(p) for p in prefixes)
    if with_rawopt:
        # `[@키]{rawopt="[see][p.~23]"}` — 닫는 `]` 바로 뒤의 `{rawopt=값}`.
        # 값은 따옴표로 감싸도 되고(따옴표 안에는 `}`나 `]`가 있어도 된다)
        # 감싸지 않아도 된다. 다른 키나 일반 중괄호 `{텍스트}`는 잡지 않는다.
        return re.compile(
            r"\[(" + alt + r")([^\]]+)\]"
            r"\{rawopt=(\"[^\"]*\"|'[^']*'|[^{}\"']*)\}")
    return re.compile(r"\[(" + alt + r")([^\]]+)\]")

# 백슬래시로 이스케이프한 따옴표( \" 또는 \' )는 스마트 따옴표 변환에서 제외하고
# 직선 따옴표 문자를 그대로 출력하기 위한 패턴이다.
ESCAPED_QUOTE_RE = re.compile(r"\\([\"'])")


_quotes_warned = set()


def resolve_quotes(cfg):
    """cfg["quotes"] 를 (큰여, 큰닫, 작은여, 작은닫) 으로 푼다.

    tex 이거나 잘못된 값이면 None(= 예전 동작). 작은따옴표 쌍은 2글자만 준
    경우 None 이고, 그때 작은따옴표는 tex 방식으로 둔다."""
    val = cfg.get("quotes", "tex")
    if isinstance(val, str):
        name = val.strip().lower()
        if name in ("", "tex", "latex"):
            return None
        if name == "unicode":
            return ("\u201c", "\u201d", "\u2018", "\u2019")
        items = list(val)            # 문자열은 글자 하나씩
    elif isinstance(val, (list, tuple)):
        items = [str(x) for x in val]
    else:
        items = None
    if items is None or len(items) not in (2, 4) or not all(items):
        if repr(val) not in _quotes_warned:
            _quotes_warned.add(repr(val))
            print(f"경고: quotes: {val!r} 을(를) 알 수 없습니다. tex / unicode / "
                  f"2 또는 4개의 문자(열)여야 합니다. tex 로 둡니다.", file=sys.stderr)
        return None
    if len(items) == 2:
        return (items[0], items[1], None, None)
    return tuple(items)


def convert_smart_quotes(text: str, quotes=None, protect=None) -> str:
    r"""LaTeX은 여는/닫는 따옴표에 서로 다른 문자를 쓴다.

    - 큰따옴표: 여는 것은 ``(백틱 두 개), 닫는 것은 ''(아포스트로피 두 개).
    - 작은따옴표: 여는 것은 `(백틱 한 개), 닫는 것은 '(아포스트로피, 그대로 둔다).

    한국어는 "그것"이라고 처럼 닫는 따옴표 바로 뒤에 조사가 공백 없이 붙는 일이
    매우 흔해서, pandoc처럼 "닫는 따옴표 뒤에 공백/구두점이 오는가"를 검사하는
    방식은 쓸 수 없다(요구사항 3). 그래서 이 함수는 오른쪽 문맥은 아예 보지 않는다:
    "여는" 위치(문자열 맨 앞이거나 공백 바로 뒤, 요구사항 1·2)만 정확히 골라
    먼저 치환하고, 그 다음 남아 있는 따옴표는 전부 "닫는" 것으로 간주해 일괄
    치환한다.

    "여는(*)닫는" 형태를 하나의 정규식으로 통째로 잡아내는 방식(즉 `"(.*)"` 류)은
    그 사이에 문단 구분을 위한 빈 줄이 끼어들 가능성이 많아 채택하지 않았다
    (요구사항의 사전 검토에서 확인된 문제).

    이 함수는 process_inline() 안에서, 코드/수식/원본 매크로/그림·링크·각주·참조·
    색인 문법이 이미 placeholder로 보호된 뒤 -- 그러나 굵게/기울임 등 인라인 서식
    규칙이 자기 캡처 구간을 protect()해버리기 전에 -- 호출되어야 한다. 그래야
    다른 기능적 문맥의 따옴표와 혼선이 없고(요구사항 5), 굵게/기울임 안의 따옴표도
    올바르게 변환된다.

    요구사항에는 "문두 또는 공백 뒤"만 명시되어 있었지만, 실제 문서에서는
    **"인용"** 처럼 굵게/기울임 기호(*, ~) 나 여는 괄호류([, (, {) 바로 뒤에
    따옴표가 오는 경우도 흔하다. 이런 위치는 공백이 아니라서 원래 규칙만으로는
    "여는" 것으로 인식되지 못하고 둘 다 "닫는" 것으로 오인되므로(둘 다 그 앞
    문자가 공백이 아니기 때문), 여는 문맥 판정에 이 문자들도 포함시킨다.
    """
    _OPEN_CTX = r"[\s([{*~]"

    if quotes is not None:
        # tex 가 아닌 모드. 결과 문자는 protect() 로 보호해서 뒤 단계(굵게·기울임
        # 규칙, 최종 escape_text)가 건드리지 못하게 한다. 여는/닫는 판정은 같다.
        dop, dcl, sop, scl = quotes
        text = re.sub(rf'(?:\A|(?<={_OPEN_CTX}))"', lambda m: protect(dop), text)
        text = text.replace('"', protect(dcl))
        if sop is None:
            # 2글자만 받았다: 작은따옴표는 tex 방식 그대로.
            text = re.sub(rf"(?:\A|(?<={_OPEN_CTX}))'", "`", text)
        else:
            text = re.sub(rf"(?:\A|(?<={_OPEN_CTX}))'", lambda m: protect(sop), text)
            text = text.replace("'", protect(scl))
        return text

    # 큰따옴표: 여는 위치만 먼저 치환한다. 남는 것은 전부 닫는 따옴표다.
    text = re.sub(rf'(?:\A|(?<={_OPEN_CTX}))"', "``", text)
    text = text.replace('"', "''")

    # 작은따옴표: 여는 위치만 백틱으로 치환한다. 닫는 작은따옴표는 TeX에서도
    # 아포스트로피(') 그대로 쓰므로 별도 치환이 필요 없다.
    text = re.sub(rf"(?:\A|(?<={_OPEN_CTX}))'", "`", text)
    return text

_ESCAPE_MAP = {
    # 참고: LaTeX의 표준 특수문자 10개는 # $ % & ~ _ ^ \ { } 이다.
    # 이전 버전은 이 중 "\"(백슬래시)와 "$"가 빠져 있었다. MACRO_RE/INLINE_MATH_RE에
    # 걸리지 않는 낱개 백슬래시나 짝이 맞지 않는 "$"가 본문에 남아 있으면 그대로
    # LaTeX으로 흘러들어가 컴파일 오류나 의도치 않은 수식 모드 전환을 일으킬 수 있다.
    "\\": r"\textbackslash{}",
    "&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_", "$": r"\$",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def _with_tilde(chars):
    """escape_chars 목록에 ~ 를 보탠 사본을 돌려준다."""
    chars = list(chars)
    if "~" not in chars:
        chars.append("~")
    return chars


def escape_text(text, chars):
    pattern = re.compile("|".join(re.escape(c) for c in chars))
    return pattern.sub(lambda m: _ESCAPE_MAP.get(m.group(0), m.group(0)), text)


def _split_attr_tokens(attr_str):
    """쉼표로 나누되 따옴표와 중괄호 안의 쉼표는 건드리지 않는다.

    맨 split(",") 이면 wrapspec="c,top=1" 처럼 값 안에 쉼표가 든 속성이
    반토막 난다. wrapspec 은 뒤 환경에 통째로 넘길 문자열이라 쉼표가 들어가는
    것이 정상이므로 여기서 보호해야 한다. raw={1cm}{1cm} 같은 중괄호 값도
    같은 이유로 함께 센다.
    """
    out, cur = [], []
    quote, depth = None, 0
    for ch in attr_str or "":
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch == "{":
            depth += 1
            cur.append(ch)
        elif ch == "}":
            depth = max(0, depth - 1)
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def parse_figure_attrs(attr_str):
    attrs = {}
    for token in _split_attr_tokens(attr_str):
        token = token.strip()
        if not token:
            continue
        if "=" in token:
            k, v = token.split("=", 1)
            v_cleaned = v.strip()
            # 감싼 따옴표 한 겹만 벗긴다. strip('"') 는 값 양끝의 따옴표를
            # 몇 개든 갉아먹는다.
            if len(v_cleaned) >= 2 and v_cleaned[0] == v_cleaned[-1] and v_cleaned[0] in "\"'":
                v_cleaned = v_cleaned[1:-1]
            attrs[k.strip()] = v_cleaned
        else:
            attrs[token] = None
    return attrs


_NOTE_TAGLIKE_RE = re.compile(r"[\w\s=,.\"'\[\]+-]*")
_VERB_SPAN_RE = re.compile(r"\\verb\*?([^A-Za-z*\s])(.*?)\1")
_note_warned = set()


def _parse_note_tag(raw, cfg):
    r"""각주 꼬리표 `{...}` 를 읽는다.

    None  = 꼬리표가 아니다(비었음) -> 호출 쪽이 기본 각주 + 원문 그대로 처리
    "bad" = 꼬리표처럼 읽으려 했으나 알아볼 수 없음
    dict  = {kind, sym(bool), symval(int|None), opt(str|None)}
    """
    if raw is None or not raw.strip():
        return None
    notes = cfg.get("notes") or {}
    kind, sym, symval, opt = None, False, None, None
    for k, v in parse_figure_attrs(raw).items():
        if k in ("sym", "symbol"):
            sym = True
            if v not in (None, ""):
                if not v.isdigit():
                    return "bad"
                symval = int(v)
        elif k == "opt":
            if not v:
                return "bad"
            opt = v if v.startswith("[") else f"[{v}]"
        elif v is None and k in notes:
            if kind is not None:
                return "bad"
            kind = k
        else:
            return "bad"
    return {"kind": kind or "default", "sym": sym, "symval": symval, "opt": opt}


def render_note(text_, tag_raw, cfg, pr, process):
    r"""각주 본문(text_)과 꼬리표 원문으로 LaTeX 각주 명령을 만든다.

    돌려주는 값은 (보호할 LaTeX, 뒤에 그대로 붙일 원문) 이다 — 꼬리표로
    읽히지 않은 `{...}` 는 예전처럼 본문에 그대로 남긴다.
    """
    spec = _parse_note_tag(tag_raw, cfg)
    leftover = ""
    if spec is None:
        spec = {"kind": "default", "sym": False, "symval": None, "opt": None}
        if tag_raw is not None:
            leftover = "{" + tag_raw + "}"
    elif spec == "bad":
        spec = {"kind": "default", "sym": False, "symval": None, "opt": None}
        leftover = "{" + tag_raw + "}"
        if _NOTE_TAGLIKE_RE.fullmatch(tag_raw) and tag_raw not in _note_warned:
            _note_warned.add(tag_raw)
            names = ", ".join(k for k in (cfg.get("notes") or {}) if k != "default")
            print(f"경고: 각주 뒤의 {{{tag_raw}}} 는 등록된 각주 종류가 아닙니다 "
                  f"(등록: {names}; sym, opt=). 본문에 그대로 남깁니다.",
                  file=sys.stderr)
    entry = (cfg.get("notes") or {}).get(spec["kind"]) or r"\footnote%(opt)s{%(text)s}"
    tmpl = entry.get("template", r"\footnote%(opt)s{%(text)s}") if isinstance(entry, dict) else str(entry)
    inner = process(text_)
    opt = spec["opt"] or ""
    if spec["sym"]:
        if spec["symval"] is not None:
            n = spec["symval"]
        elif opt and opt.strip("[]").isdigit():
            n = int(opt.strip("[]"))
        else:
            n = cfg.get("_sym_n", 0) + 1
        cfg["_sym_n"] = n
        if not 1 <= n <= 9 and ("sym", n) not in _note_warned:
            _note_warned.add(("sym", n))
            print(f"경고: 기호 각주 번호 {n} 은 \\fnsymbol 이 지원하는 1–9 를 벗어납니다.",
                  file=sys.stderr)
        opt = f"[{n}]"
    out = tmpl % {"opt": opt, "text": inner} if "%(" in tmpl else tmpl % inner
    if spec["sym"]:
        m = re.match(r"\\([A-Za-z]+)", tmpl)
        ctr = m.group(1) if m else "footnote"
        out = r"{\renewcommand{\the%s}{\fnsymbol{%s}}%s}" % (ctr, ctr, out)
    return out, leftover


_WAVEDASH_HEX_RE = re.compile(r"^(?:U\+|0x|\\u)?([0-9A-Fa-f]{4,6})$")
_WAVEDASH_MACRO_RE = re.compile(r"^\\[A-Za-z@]+$")
_wavedash_warned = set()


_TILDE_MODES = {
    "latex": "latex", "default": "latex", "": "latex",
    "pandoc": "pandoc",
    "multimarkdown": "multimarkdown", "mmd": "multimarkdown",
}
_tilde_warned = set()


def resolve_tilde(cfg):
    r"""mapping의 `tilde` 값을 "latex" | "pandoc" | "multimarkdown" 으로 푼다.

    알아볼 수 없는 값이면 경고를 한 번 찍고 latex(옛 동작)로 물러난다.
    """
    v = cfg.get("tilde", "latex")
    key = "" if v is None else str(v).strip().lower()
    if key in _TILDE_MODES:
        return _TILDE_MODES[key]
    if key not in _tilde_warned:
        _tilde_warned.add(key)
        print(f"경고: tilde 값 '{v}' 을(를) 알아볼 수 없습니다 "
              "(latex | pandoc | multimarkdown). latex 로 처리합니다.",
              file=sys.stderr)
    return "latex"


# 닫힌 꼴 ~x~ / ^x^ : 안에 공백이 없어야 한다(pandoc과 같은 규칙).
# 열린 꼴 ~x / ^x : multimarkdown 전용. 뒤따르는 글자·숫자 덩어리까지.
# 자리표시자(\uE000…\uE001)는 \W 이므로 열린 꼴이 그 앞에서 멈춘다.
_SUB_CLOSED_RE = re.compile(r"(?<![~])~(?!~)([^\s~]+?)~(?!~)")
_SUP_CLOSED_RE = re.compile(r"(?<![\^])\^(?!\^)([^\s^]+?)\^(?!\^)")
_SUB_OPEN_RE = re.compile(r"(?<![~])~(?!~)([^\W_]+)")
_SUP_OPEN_RE = re.compile(r"(?<![\^])\^(?!\^)([^\W_]+)")


def apply_tilde_caret(text, mode, escape_chars, local):
    r"""pandoc / multimarkdown 방언의 첨자 규칙을 적용한다.

    process_inline() 안에서, ^^방점^^·^[각주]·^^M·취소선 ~~ 가 모두 처리되고
    마지막 escape_text() 가 돌기 전에 불린다. 첨자가 되지 못한 ~ 는
    pandoc 에서는 뒤따르는 escape_text() 가 \textasciitilde{} 로 바꾸고
    (호출 쪽이 escape_chars 에 ~ 를 보탠다), multimarkdown 에서는 여기서
    \ensuremath{\sim} 이 된다.
    """
    def sub(g):
        return local.protect(r"\textsubscript{%s}" % escape_text(g, escape_chars))

    def sup(g):
        return local.protect(r"\textsuperscript{%s}" % escape_text(g, escape_chars))

    text = _SUB_CLOSED_RE.sub(lambda m: sub(m.group(1)), text)
    text = _SUP_CLOSED_RE.sub(lambda m: sup(m.group(1)), text)
    if mode == "multimarkdown":
        text = _SUB_OPEN_RE.sub(lambda m: sub(m.group(1)), text)
        text = _SUP_OPEN_RE.sub(lambda m: sup(m.group(1)), text)
        text = re.sub(r"~", lambda m: local.protect(r"\ensuremath{\sim}"), text)
    return text


def resolve_wavedash(cfg):
    r"""mapping의 `wavedash` 값을 `\~` 대신 내보낼 문자열로 풀어낸다.

    "default"(또는 비어 있음)면 None — `\~` 를 원문 그대로 LaTeX에 넘기는
    옛 동작이다. 그 밖에는:
      - 16진 코드포인트(`FF5E`, `U+FF5E`, `0xFF5E`, 숫자 3030 처럼 YAML이
        정수로 읽은 것도 16진 자리수로 본다) -> 그 문자
      - 한 글자 -> 그 글자 자신
      - `\이름` 꼴의 LaTeX 매크로 -> `\이름{}` (뒤 공백을 먹지 않도록)
    알아볼 수 없는 값이면 경고를 한 번 찍고 default로 물러난다.
    """
    v = cfg.get("wavedash", "default")
    if v is None or v is False:
        return None
    sv = str(v).strip()
    if sv == "" or sv.lower() == "default":
        return None
    m = _WAVEDASH_HEX_RE.match(sv)
    if m:
        cp = int(m.group(1), 16)
        if cp <= 0x10FFFF:
            return chr(cp)
    if _WAVEDASH_MACRO_RE.match(sv):
        return sv + "{}"
    if len(sv) == 1:
        return sv
    if sv not in _wavedash_warned:
        _wavedash_warned.add(sv)
        print(f"경고: wavedash 값 '{sv}' 을(를) 알아볼 수 없습니다 "
              f"(default / 16진 코드포인트 / 한 글자 / \\매크로). default로 처리합니다.",
              file=sys.stderr)
    return None


def process_inline(text, cfg, pr: Protector):
    local = Protector()

    text = protect_inline_code(text, cfg, local)

    # 원문에 직접 쓴 `^^M`은 "소스의 강제 개행"이다 — LaTeX한테 줄바꿈을
    # 하라는 뜻(그건 \\ 나 \newline)이 아니라, 생성되는 .tex *파일
    # 자체의 그 위치에 진짜 개행 문자를 박아 넣으라는 뜻이다. 이 방언은
    # 평문의 줄바꿈을 전부 공백으로 합쳐 버리므로(render_paragraph),
    # 줄 단위로 인자를 읽는 TeX 매크로(`\def\linecommand#1^^M{...}`처럼
    # 그 줄 끝까지를 인자로 삼는 것들)를 쓰려면 이렇게 명시적으로 개행을
    # 요청할 방법이 필요했다. `^^M`이라는 표기 자체도 TeX이 개행 문자
    # (캐리지리턴, 문자 코드 13)를 캐럿 표기법으로 나타낼 때 쓰는 바로
    # 그 표기라서, 이 방언에서 익숙한 이름을 그대로 가져왔다.
    #
    # local.protect()로 즉시 플레이스홀더로 바꿔 두는 이유는 mdash_cmd
    # 처리와 같다 — 그러지 않으면 뒤따르는 **굵게**/*기울임* 같은 인라인
    # 서식 루프가 이 자리를 다시 escape_text에 태워 망가뜨릴 수 있다.
    #
    # `^^방점^^`(emphdot, extra_inline 기본값)과 표기가 겹쳐 보이지만
    # 충돌하지 않는다 — emphdot 정규식(`\^\^(.+?)\^\^`)은 반드시 닫는
    # `^^`가 있어야 매치되는데, `^^M`은 짝이 없는 단독 캐럿 두 개+M이라
    # 그 패턴 자체에 안 걸린다. 다만 이 처리를 extra_inline보다 먼저
    # (지금 이 자리에서) 끝내 둬야, 뒤쪽 어딘가에 `^^다른방점^^`이 있을
    # 때 그 여는/닫는 캐럿과 `^^M`의 캐럿이 잘못 짝지어지는 오매칭을
    # 막을 수 있다.
    text = re.sub(r"\^\^M", lambda m: local.protect("\n"), text)

    def protect_raw(m):
        return local.protect(m.group(0))

    text = INLINE_MATH_RE.sub(protect_raw, text)
    # \verb|...| 구간은 어디서나 LaTeX 코드 그대로 통과시킨다. 매크로 보호가
    # \verb 만 떼어 보호하므로, 이 줄이 없으면 구분자 안의 _ # % 등이
    # 이스케이프되어 \verb 가 엉뚱한 글자를 찍는다. \verbfootnote 본문에서
    # \verb 를 쓰는 것이 이 처리의 주된 쓰임이다.
    text = _VERB_SPAN_RE.sub(protect_raw, text)
    text = build_macro_re(cfg).sub(protect_raw, text)

    # 독립된 줄이 아니라 "문장 중"에 등장하는 --- (앞뒤에 다른 대시가 붙지
    # 않은, 정확히 3개짜리)는 원고에서 흔히 \textemdash 같은 효과로 쓰인다.
    # 기본값은 \textemdash 자체를 방출한다 — 표준 LaTeX 명령이라 preamble에
    # 아무것도 정의하지 않아도 그대로 컴파일된다. em-dash 자리에 다른 명령을
    # 쓰고 싶으면 mapping.yaml의 mdash 키로 바꾸면 된다(예:
    # \newcommand{\ndhmdash}{\textemdash\hspace{0pt}} 처럼 자체 매크로를
    # preamble에 정의해 mdash: '\ndhmdash' 로 가리키는 식). local.protect()로
    # 즉시 보호해야 하는 이유: 그렇지 않으면 (1) 이 텍스트가 **굵게**\*\*...\*\*
    # 안에 있을 경우 그 처리 루프가 내용에 escape_text를 한 번 더 돌려서
    # 백슬래시가 \textbackslash{}로 이중 이스케이프되고, (2) 맨 마지막
    # escape_text 호출에서도 마찬가지로 깨진다.
    mdash_cmd = cfg.get("mdash", r"\textemdash{}")
    text = re.sub(r"(?<!-)---(?!-)", lambda m: local.protect(mdash_cmd), text)

    # {#id} -> \label{id}. 코드 스팬 안은 건드리지 않는다 — protect_inline_code
    # 가 이미 그 부분을 자리표시자로 바꿔 둔 뒤이므로 이 정규식이 볼 일이 없다.
    text = INLINE_LABEL_RE.sub(
        lambda m: local.protect(r"\label{%s}" % m.group(1)), text)

    def _do_figure_core(caption_raw, path, attr_str, pre_attrs=None):
        attrs = pre_attrs if pre_attrs is not None else parse_figure_attrs(attr_str)

        # 내려받기·형식 변환·애니메이션. 실패하면 원문을 그대로 두고 알린다 —
        # 그림 하나 때문에 문서 전체 변환을 멈출 일은 아니다.
        anim = None
        try:
            path, anim = prepare_image(
                path,
                cfg.get("_image_base") or ".",
                cfg=cfg,
                fetch=bool(cfg.get("_fetch_images")),
                animation=(cfg.get("_animation_frames") if cfg.get("_animation_on") else False),
            )
        except ImageError as e:
            print(f"오류: {e}", file=sys.stderr)
            return local.protect(m.group(0))

        # 대체텍스트가 빈 따옴표 한 쌍뿐이면 "캡션 없는 그림 플로트"로 읽는다.
        #   ![](x)      -> \includegraphics 만 (플로트 아님)
        #   ![텍스트](x) -> figure + \caption
        #   ![""](x)    -> figure, \caption 없음
        # 예전에는 이것이 \caption{``''} 이라는, 비어 보이지만 비어 있지 않은
        # 캡션으로 나갔다(따옴표 두 개가 스마트 따옴표 변환을 거친 결과).
        # 아무도 원할 리 없는 출력이라 규칙으로 승격시켜도 잃는 것이 없다.
        #
        # 참고: 따옴표는 캡션 구분자가 아니다. !["텍스트"](x) 는 따옴표까지
        # 포함한 캡션이 된다. 여기서 특별 취급하는 것은 "속이 완전히 빈"
        # 따옴표 쌍뿐이다.
        _EMPTY_QUOTES = {'""', "''", "\u201c\u201d", "\u2018\u2019"}
        caption_only_quotes = caption_raw.strip() in _EMPTY_QUOTES
        has_caption = bool(caption_raw.strip()) and not caption_only_quotes

        # caption= 속성과 대체텍스트는 **다른 것을 뜻한다.**
        #
        #   ![캡션](x.png)              -> figure 로 띄우고 \caption
        #   ![](x.png){caption="..."}   -> 띄우지 않고 \captionof (dry caption)
        #
        # 줄글 흐름에 그림을 그 자리에 두면서 캡션만 달고 싶을 때가 있다.
        # \caption 은 float 안에서만 되지만 \captionof 는 아무 데서나 되고,
        # 번호와 \label 은 그대로 이어받는다.
        #
        # wrap 배치에서는 예외다. 거기서는 wrapstuff 가 float 노릇을 하므로
        # \caption 을 그대로 쓴다.
        attr_caption = attrs.pop("caption", None)
        dry_caption = None
        if attr_caption and not has_caption and not caption_only_quotes:
            dry_caption = attr_caption
        
        label = attrs.pop("label", None)
        if label:
            label = label.strip()
            while label.startswith("{") and label.endswith("}"):
                label = label[1:-1].strip()
            
        place = attrs.pop("place", "htbp")
        if place:
            place = place.strip()
            while place.startswith("{") and place.endswith("}"):
                place = place[1:-1].strip()

        # align도 label/place와 마찬가지로 여기서 빼낸다. 남겨두면 나머지
        # 속성과 함께 \includegraphics의 옵션으로 흘러들어가 graphicx가
        # "keyval Error: align undefined"로 죽는다. 값은 raw로 나가므로
        # LaTeX 명령을 그대로 적는다(:::{figure} 환경과 같은 규칙).
        # align=""처럼 빈 값을 주면 정렬 명령 자체를 생략한다.
        align = attrs.pop("align", r"\centering")
        if align:
            align = align.strip()
            while align.startswith("{") and align.endswith("}"):
                align = align[1:-1].strip()

        # wrap: 본문이 그림을 둘러싸는 배치(wrapstuff). 단독 키라 값이 없다.
        # wrapspec 은 그 환경의 대괄호 인자로 **그대로** 넘어간다 — 이
        # 스크립트가 해석하지 않으므로 환경이 무엇을 받든 저자가 정한다.
        wrap = "wrap" in attrs
        attrs.pop("wrap", None)
        wrapspec = attrs.pop("wrapspec", None)
        if wrapspec:
            wrapspec = wrapspec.strip()
            while wrapspec.startswith("{") and wrapspec.endswith("}"):
                wrapspec = wrapspec[1:-1].strip()

        # 줄글 중간에 끼우는 작은 그림. inlinegraphicx 패키지가 맡는다.
        # wrap 과 마찬가지로 inlinespec= 은 해석하지 않고 그대로 넘긴다.
        inline_img = "inline" in attrs
        attrs.pop("inline", None)
        inlinespec = attrs.pop("inlinespec", None)
        if inlinespec:
            inlinespec = inlinespec.strip()
            while inlinespec.startswith("{") and inlinespec.endswith("}"):
                inlinespec = inlinespec[1:-1].strip()

        # 그림 자체에 링크를 건다. \href 는 hyperref 가 준다 — 로딩은 저자 몫.
        # 캡션이나 라벨이 아니라 \includegraphics 만 감싼다.
        href = attrs.pop("href", None)
        if href:
            href = href.strip()
            while href.startswith("{") and href.endswith("}"):
                href = href[1:-1].strip()

        opt_parts = [f"{k}={v}" if v is not None else k for k, v in attrs.items()]
        opts = ",".join(opt_parts)
        if anim is not None:
            # animate 패키지. 프레임별 지연은 살릴 수 없다 —
            # \animategraphics 가 단일 fps만 받기 때문이다.
            prefix, last, total = anim
            fps = cfg.get("animation_fps", 10)
            img_cmd = r"\animategraphics[%s]{%s}{%s}{0}{%d}" % (
                opts or "autoplay,loop", fps, prefix, last)
            if total > last + 1:
                print(f"알림: 프레임 {total} 중 앞 {last + 1} 장만 씁니다.",
                      file=sys.stderr)
        elif inline_img:
            spec = inlinespec or opts
            cmd = cfg.get("inline_graphics_cmd", "inlinegraphics")
            img_cmd = (r"\%s[%s]{%s}" % (cmd, spec, path)) if spec else (r"\%s{%s}" % (cmd, path))
        else:
            img_cmd = (r"\includegraphics[%s]{%s}" % (opts, path)) if opts else (r"\includegraphics{%s}" % path)

        if href:
            img_cmd = r"\href{%s}{%s}" % (href, img_cmd)

        if wrap:
            # 떠다니는 figure로 감싸지 않는다. wrapstuff 자체가 배치를
            # 맡으므로 place 는 쓰이지 않는다.
            #
            # 반환값이 인라인 자리표시자로 들어가므로, 이 환경은 뒤따르는
            # 본문과 **같은 문단**에 남는다. 그것이 이 배치가 요구하는
            # 조건이다 — 원고에서 그림 줄 다음에 빈 줄 없이 문단을 이어
            # 쓰면 된다.
            env = cfg.get("wrap_env", "wrapstuff")
            head = rf"\begin{{{env}}}[{wrapspec}]" if wrapspec else rf"\begin{{{env}}}"
            block = [head]
            if align:
                block.append(align)
            block.append(img_cmd)
            wrap_cap = caption_raw if has_caption else (dry_caption or "")
            if wrap_cap:
                block.append(r"\caption{%s}" % process_inline(wrap_cap, cfg, pr))
            if label:
                block.append(r"\label{%s}" % label)
            block.append(rf"\end{{{env}}}")
            return local.protect("\n".join(block))

        if dry_caption:
            # 띄우지 않고 그 자리에 두면서 캡션만 단다.
            capof = cfg.get("captionof_cmd", "captionof")
            block = [img_cmd,
                     r"\%s{figure}{%s}" % (capof, process_inline(dry_caption, cfg, pr))]
            if label:
                block.append(r"\label{%s}" % label)
            return local.protect("\n".join(block))

        # 띄울지 말지는 **대체텍스트 자리로만** 정한다. 속성으로는 정하지
        # 않는다 — 규칙이 하나여야 기억할 수 있다.
        #
        #   ![텍스트](x)  -> figure + \caption
        #   ![""](x)      -> figure, 캡션 없음
        #   ![](x){...}   -> 무엇을 적든 띄우지 않는다
        #
        # 예전에는 label= 만 있어도 띄웠는데, caption= 이 dry caption 이 된
        # 지금은 그 예외가 규칙을 흐릴 뿐이다. 띄우지 않는 그림에 번호를
        # 붙이고 싶으면 caption= 을 쓰면 된다(\captionof 가 번호를 맡는다).
        if has_caption or caption_only_quotes:
            block = [rf"\begin{{figure}}[{place}]"]
            if align:
                block.append(align)
            block.append(img_cmd)
            if has_caption:
                block.append(r"\caption{%s}" % process_inline(caption_raw, cfg, pr))
            if label:
                block.append(r"\label{%s}" % label)
            block.append(r"\end{figure}")
            return local.protect("\n".join(block))

        if label:
            # 캡션이 없는 \label 은 직전 카운터를 가리킨다 — 대개 저자가
            # 원한 것이 아니다. 그래도 적은 대로 내보내되 알려준다.
            print(
                f"경고: 캡션 없는 그림에 label={label} 을 달았습니다. "
                f"\\label 이 번호를 이어받지 못해 \\ref 가 엉뚱한 값을 냅니다. "
                f"caption= 을 함께 주면 \\captionof 가 번호를 맡습니다.",
                file=sys.stderr,
            )
            return local.protect(img_cmd + "\n" + r"\label{%s}" % label)

        return local.protect(img_cmd)

    def do_figure(m):
        return _do_figure_core(m.group(1), m.group(2), m.group(3))

    def do_figure_ref(m):
        caption_raw, ref_label = m.group(1), m.group(2)
        defn = cfg.get("_refdefs", {}).get(ref_label)
        if defn is None:
            print(f"경고: 정의되지 않은 참조 [{ref_label}] 를 그림에 썼습니다.", file=sys.stderr)
            # local.protect()로 즉시 감싸 둔다 — 그냥 원문을 반환하면 이
            # 자리가 아직 텍스트에 남아 있는 채로 뒤이은 LINK_REF_RE.sub()
            # 가 `[alt][라벨]` 부분(느낌표는 무시하고)을 또 한 번 링크
            # 참조로 시도해서, 이미 뜬 경고가 하나 더 중복으로 뜬다(텍스트
            # 자체는 원문 그대로 보존되므로 피해는 없지만, 경고가 헷갈리게
            # 두 번 뜨는 건 불필요하다).
            return local.protect(m.group(0))
        # 정의 값은 "경로 + (선택) 속성"을 공백으로만 구분한 한 줄이다.
        # {폭=...} 처럼 중괄호로 감싸지 않는다 — REF_DEF_RE 자체가
        # `[라벨]: 경로 속성,속성...` 한 줄만 받으므로, 중괄호를 강제하면
        # 그 안에 매번 중괄호를 또 넣어야 해서 번거롭다. 첫 토큰이 경로,
        # 나머지 전부가 parse_figure_attrs() 그대로 넘길 속성 문자열이다.
        m2 = _REF_DEF_VALUE_RE.match(defn)
        path = m2.group(1)
        attrs = parse_figure_attrs(m2.group(2) or "")
        use_attrs = parse_figure_attrs(m.group(3) or "")

        # 정의 줄의 속성은 "이미지의 공유 기본값", 사용처 `{...}`는 "이 그림
        # 인스턴스만의 값"이다. 같은 키는 사용처가 이긴다. 값을 비우면
        # (`label=`) 정의에 있던 그 속성을 지운다 — 다만 align은 빈 값이
        # 그 자체로 "정렬 명령 없음"이라는 뜻이라 지우지 않고 그대로 덮어쓴다.
        for k, v in use_attrs.items():
            if v == "" and k != "align":
                attrs.pop(k, None)
            else:
                attrs[k] = v

        # \label 은 그림 하나에 하나뿐이어야 한다. 정의 줄에 label=이 있는데
        # 사용처가 label을 따로 주지 않은 채 두 번 이상 쓰이면 같은 \label 이
        # 여러 번 나가 LaTeX가 "multiply defined"를 낸다 — 미리 알려 준다.
        if (attrs.get("label") and "label" not in use_attrs
                and "label" in parse_figure_attrs(m2.group(2) or "")):
            uses = cfg.setdefault("_reflabel_uses", {})
            uses[ref_label] = uses.get(ref_label, 0) + 1
            if uses[ref_label] == 2:
                print(f"경고: 참조 [{ref_label}] 의 정의에 label={attrs['label']} 가 있는데 "
                      f"여러 번 쓰입니다. \\label 이 중복됩니다 — 사용처에 "
                      f"![..][{ref_label}]{{label=...}} 로 따로 주십시오.", file=sys.stderr)
        return _do_figure_core(caption_raw, path, "", pre_attrs=attrs)

    def _do_link_core(label, url):
        # url이 #으로 시작하면 외부 URL이 아니라 문서 안 라벨을 가리키는
        # 것으로 본다. 진짜 URL은 http://, https://, mailto:, 상대경로
        # 파일명 등으로 시작하지 # 로 시작하는 법이 없으므로 구분에 모호함이
        # 없다. [#label] 상호참조 문법(16장, 대괄호 하나)과는 형태가 아예
        # 달라 충돌하지 않는다 — 이쪽은 [text](#label) 처럼 괄호가 있는
        # 링크 문법 안에서만 인식된다.
        #
        # \ref 가 아니라 \hyperref[label]{...} 를 쓰는 이유: \ref 는 번호만
        # 내놓으므로 "그 절로 가는 링크" 자체를 원하는 이 문법의 뜻과
        # 다르다. \hyperref[label]{...} 는 임의의 텍스트(또는 라벨 이름
        # 자체)를 그 라벨 위치로 가는 클릭 가능한 링크로 만든다(hyperref
        # 필요 — 로딩은 저자 몫).
        if url.startswith("#"):
            label_id = url[1:]
            if label.strip() == "":
                return local.protect(r"\hyperref[%s]{%s}" % (label_id, label_id))
            label_out = process_inline(label, cfg, pr)
            return local.protect(r"\hyperref[%s]{%s}" % (label_id, label_out))
        if label.strip() == "":
            return local.protect(r"\url{%s}" % url)
        label_out = process_inline(label, cfg, pr)
        # \href 는 hyperref 가 첫 인자를 verbatim 스캔으로 읽는 트릭을 쓰는데,
        # 그 트릭은 인자가 최상위 토큰 스트림에서 바로 읽힐 때만 통한다.
        # \caption{\href{...url...}{...}} 처럼 한 번 더 매크로 인자로 감싸이면
        # (커스텀 환경의 caption= 이 바로 이 경우다) verbatim 스캔이 아니라
        # 보통의 매크로 인자 확장을 거치므로, url 안의 % 부터 그 줄 나머지가
        # LaTeX 주석으로 통째로 사라진다.
        #
        # 본문에 직접 쓴 \href{...}{...} 는 이 문제가 없다(실측 확인). URL이
        # 라는 것이 이 자리에서 명백하므로 % 를 \% 로 미리 이스케이프해
        # 안전하게 만든다 — 실제 링크 대상에는 영향이 없다(PDF의 /URI 에는
        # \ 가 빠지고 원래 % 그대로 들어가는 것을 확인했다).
        url_safe = url.replace("%", r"\%")
        return local.protect(r"\href{%s}{%s}" % (url_safe, label_out))

    def do_link(m):
        return _do_link_core(m.group(1), m.group(2))

    def do_link_ref(m):
        label, ref_label = m.group(1), m.group(2)
        defn = cfg.get("_refdefs", {}).get(ref_label)
        if defn is None:
            print(f"경고: 정의되지 않은 참조 [{ref_label}] 를 링크에 썼습니다.", file=sys.stderr)
            # do_figure_ref와 같은 이유로 즉시 protect한다 — 뒤이은
            # 단계들과는 실제로 안 겹치는 것으로 확인했지만, 일관되게
            # "이 자리는 이미 처리를 시도했다"로 못박아 두는 편이 안전하다.
            return local.protect(m.group(0))
        # 링크 정의는 통째로 URL이다(이미지 정의와 달리 뒤에 속성이 붙지
        # 않는다) — 다만 `url "제목"`처럼 따옴표 붙은 제목이 있으면
        # 떼어낸다. 인라인 링크의 제목과 마찬가지로 이 방언은 제목을
        # 쓰지 않으므로(do_link 참고) 버려도 손실이 없다.
        m2 = _REF_LINK_DEF_VALUE_RE.match(defn)
        url = m2.group(1)
        # 표시 텍스트는 참조 시점에 쓴 그대로 넘긴다 — 빈 텍스트([][label])면
        # _do_link_core() 안의 기존 규칙(label.strip() == "" -> \url{...})이
        # 그대로 적용된다. [](url)과 [][label]이 정확히 같은 결과를 내야
        # 하므로, 여기서 라벨을 대신 채워 넣는 임의의 편의 규칙을 추가하지
        # 않는다.
        return _do_link_core(label, url)

    def _footnote(text_, tag=None):
        out, leftover = render_note(text_, tag, cfg, pr,
                                    lambda t: process_inline(t, cfg, pr))
        return local.protect(out) + leftover

    def do_footnote(m):
        fid = m.group(1)
        tag = m.group(2)
        content = cfg.get("_footnotes", {}).get(fid)
        if content is not None:
            return _footnote(content, tag)
        # 정의가 없다 = 참조가 아니다. 대괄호 안의 내용을 각주 본문으로 읽는다.
        if cfg.get("inline_footnote", True):
            return _footnote(fid, tag)
        print(f"경고: 정의되지 않은 각주 [^{fid}] 를 참조했습니다.", file=sys.stderr)
        return m.group(0)

    def do_inline_footnote(m):
        return _footnote(m.group(1), m.group(2))

    def do_ref_cite(m):
        prefix, label = m.group(1), m.group(2)
        tmpl = cfg["refcite"].get(prefix)
        if tmpl is None:
            # 이론상 REF_CITE_RE 자체가 cfg["refcite"]의 키로 만들어지므로
            # 여기 도달할 일은 없지만, 방어적으로 원문을 그대로 둔다.
            return m.group(0)
        return local.protect(tmpl % label)

    def do_ref_cite_rawopt(m):
        # \cite 의 대괄호 선택 인자(`\cite[see][p.~23]{key}`)를 **원문 그대로**
        # `{%s}` 바로 앞에 끼운다. 이 스크립트는 값을 해석하지 않는다 —
        # natbib의 [앞][뒤]든 biblatex든 저자가 적은 대로 나간다.
        prefix, label, raw = m.group(1), m.group(2), m.group(3)
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            raw = raw[1:-1]
        # 값이 `[`로 시작하지 않으면 대괄호가 빠진 것으로 보고 `[...]`로
        # 감싼다. 안 감싸면 `\cite` 뒤에 `p.~3`이 그대로 붙어 `\citep.~3{키}`
        # 라는 엉뚱한 명령이 된다(`\cite`의 선택 인자는 항상 대괄호다).
        # 값이 비면 선택 인자 없이 평범한 인용이 된다. `[`로 시작하는 값은
        # 한 글자도 건드리지 않는다(`[see][p.~23]` 같은 두 겹 포함).
        raw = raw.strip()
        if raw and not raw.startswith("["):
            raw = "[" + raw + "]"
        tmpl = cfg["refcite"].get(prefix)
        if tmpl is None:
            return m.group(0)
        if "{%s}" not in tmpl:
            print(f"경고: refcite '{prefix}' 의 템플릿에 {{%s}} 가 없어 rawopt 를 "
                  f"끼울 자리를 못 찾습니다. rawopt 는 무시합니다.", file=sys.stderr)
            return local.protect(tmpl % label)
        marker = "\x00"
        out = tmpl.replace("{%s}", marker + "{%s}", 1) % label
        return local.protect(out.replace(marker, raw))

    _INDEX_DEFAULT_TMPL = r"%(text)s\index{%(term)s}"

    def do_index(m):
        display_text = m.group(1) or ""
        index_term = m.group(2)
        # [[Term]] 처럼 구분자가 없거나 [[표시|]] 처럼 뒤가 비면 표시 텍스트를
        # 색인어로도 쓴다. [[|색인어]] 는 표시 없이 색인만 남긴다 — 이때
        # %(text)s 가 빈 문자열이 되므로 템플릿 하나로 세 경우가 다 처리된다.
        if not index_term:
            index_term = display_text

        tmpl = cfg.get("index_template", _INDEX_DEFAULT_TMPL)
        ctx = {"text": display_text, "term": index_term}
        try:
            out = tmpl % ctx
        except KeyError as e:
            missing = e.args[0] if e.args else "?"
            print(
                f"경고: index_template이 알 수 없는 자리표시자 '%({missing})s'를 "
                f"참조합니다. 쓸 수 있는 것은 %(text)s 와 %(term)s 뿐입니다. "
                f"기본 \\index 형태로 대체합니다.",
                file=sys.stderr,
            )
            out = _INDEX_DEFAULT_TMPL % ctx
        return local.protect(out)

    # rawopt 가 붙은 인용을 **맨 먼저** 처리한다. `{rawopt="[see][p.~23]"}` 의
    # `[see][p.~23]` 은 모양이 `[text][label]` 링크 참조와 같아서, 뒤의
    # LINK_REF_RE 가 먼저 보면 미정의 라벨 경고와 함께 가로채 버린다.
    text = build_refcite_re(cfg, with_rawopt=True).sub(do_ref_cite_rawopt, text)
    text = FIGURE_REF_RE.sub(do_figure_ref, text)
    text = FIGURE_RE.sub(do_figure, text)
    text = LINK_REF_RE.sub(do_link_ref, text)
    text = LINK_RE.sub(do_link, text)
    # ^[...] 를 먼저 처리한다. [^...] 규칙이 먼저 돌면 x^[a] 같은 것에서
    # 대괄호만 떼어가 엉뚱하게 갈릴 여지가 있다.
    text = INLINE_FOOTNOTE_TAG_RE.sub(do_inline_footnote, text)
    text = FOOTNOTE_REF_TAG_RE.sub(do_footnote, text)
    text = build_refcite_re(cfg).sub(do_ref_cite, text)
    text = INDEX_RE.sub(do_index, text)

    # \" 또는 \' 로 이스케이프된 따옴표는 스마트 변환 대상에서 제외하고
    # 직선 따옴표 문자 그대로 보호해둔다.
    text = ESCAPED_QUOTE_RE.sub(lambda m: local.protect(m.group(1)), text)

    # 스마트 따옴표 변환은 반드시 아래 굵게/기울임 등 인라인 서식 규칙보다
    # 먼저 실행해야 한다. 그 규칙들은 자신이 매치한 구간을 통째로 protect()
    # 해버리므로, 나중에 실행하면 예컨대 **"인용"** 안의 따옴표는 변환되지 않고
    # 그대로 남아버린다.
    text = convert_smart_quotes(text, resolve_quotes(cfg), local.protect)

    # 틸드 정책: ~ 와 \~ 를 **둘 다 원문 그대로** LaTeX에 넘기고, 무엇을
    # 뜻하는지는 LaTeX이 정하게 둔다.
    #
    # 맨 ~ 는 escape_chars에서 빠져 있으므로 아무것도 안 해도 그대로 나간다
    # (LaTeX의 묶음빈칸). 반면 \~ 는 여기서 보호해주지 않으면 맨 아래
    # escape_text()가 백슬래시를 \textbackslash{}로 바꿔 \textbackslash{}~
    # 라는 엉뚱한 것을 만든다. 그래서 "치환"이 아니라 "보호"만 한다.
    #
    # 예전에는 이 자리에서 \~ 를 \textasciitilde{}로 굳혔는데, 그러면 \~ 의
    # 의미를 스크립트가 먼저 확정해버려서 LaTeX 쪽에서 손댈 수 없게 된다.
    # 한국어 조판에서는 \~ 뒤에 숫자나 한글이 오면 물결표로 바꿔주는 식의
    # 패키지를 쓰기도 하는데, 그런 정의와 정면으로 충돌한다.
    #
    # 이 보호의 자리는 앞뒤 양쪽에서 고정된다.
    #   - convert_smart_quotes()보다 **뒤**여야 한다. 스마트 따옴표는 앞
    #     문자가 [\s([{*~] 이면 "여는 따옴표"로 보는데, 먼저 보호해버리면
    #     그 자리에 자리표시자가 들어가 앉아 \~"인용" 의 큰따옴표가 닫는
    #     모양으로 나온다.
    #   - 인라인 서식 규칙 루프보다 **앞**이어야 한다. 나중에 두면
    #     a\~~b~~ 에서 취소선 규칙이 백슬래시 뒤의 ~ 부터 세어 ~~b~~ 를
    #     잡아버린다 — 작성자가 escape한 물결표가 오히려 델리미터로
    #     둔갑하는 셈이다.
    tmode = resolve_tilde(cfg)
    ech = _with_tilde(cfg["escape_chars"]) if tmode != "latex" else cfg["escape_chars"]
    wd = resolve_wavedash(cfg)
    text = re.sub(r"\\~", lambda m: local.protect(wd if wd is not None else "\\~"), text)

    # 마침표 세 개 -> 줄임표. 자리는 위 틸드 규칙과 같은 이유로 여기다.
    #   - convert_smart_quotes() 보다 뒤여야 한다. 먼저 바꾸면 그 자리에
    #     보호 자리표시자가 앉아 ..."인용" 의 큰따옴표가 닫는 모양이 된다.
    #   - 인라인 서식 규칙보다 앞이어야 한다. 사용자가 마침표를 쓰는 규칙을
    #     추가했을 때 자리표시자가 쪼개지지 않는다.
    #
    # 이 시점에는 코드 스팬·수식·매크로·링크·각주·색인이 모두 자리표시자로
    # 보호된 뒤다. 그래서 `1...5` 같은 코드나 URL 안의 점 세 개, 이미 쓰여
    # 있는 \ldots 는 건드리지 않는다.
    #
    # 마침표가 넷 이상이면 왼쪽부터 셋씩 먹는다(.... -> 줄임표+마침표).
    # pandoc과 같은 동작이다.
    ellipsis = cfg.get("ellipsis", r"\ldots{}")
    if ellipsis:
        text = re.sub(r"\.\.\.", lambda m: local.protect(ellipsis), text)

    # extra_inline 이 앞, 기본 inline 이 뒤. 순서의 이유는 DEFAULT_CONFIG의
    # extra_inline 주석 참고.
    for rule in list(cfg.get("extra_inline", []) or []) + list(cfg["inline"]):
        def _apply(m, t=rule["template"], name=rule.get("name", "?")):
            # 캡처 그룹을 **전부** 템플릿에 넘긴다. 그래서 인자를 둘 이상
            # 받는 규칙도 쓸 수 있다.
            #   pattern:  '\*\[(.+?)\]\[(.+?)\]'
            #   template: '\Dialog{%s}{%s}'
            # 참여하지 않은 그룹(매치 안 된 선택 그룹)은 빈 문자열이 된다.
            # 캡처 그룹이 아예 없으면 매치 전체를 넘긴다.
            groups = m.groups()
            if not groups:
                groups = (m.group(0),)
            vals = tuple(escape_text(g or "", ech) for g in groups)
            try:
                return local.protect(t % vals)
            except (TypeError, ValueError) as e:
                print(
                    f"경고: 인라인 규칙 '{name}' 의 template 이 캡처 그룹 "
                    f"{len(vals)}개와 맞지 않습니다. 원문을 그대로 둡니다.\n"
                    f"  template: {t}\n  {e}",
                    file=sys.stderr,
                )
                return m.group(0)
        text = re.sub(rule["pattern"], _apply, text)

    if tmode != "latex":
        text = apply_tilde_caret(text, tmode, ech, local)
    text = escape_text(text, ech)
    text = local.restore(text)
    return text


# --------------------------------------------------------------------------
# 5. 블록 파서
# --------------------------------------------------------------------------

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)(?:\s+\{(.*?)\})?$")
HR_STAR_RE = re.compile(r"^\*{3,}\s*$")
HR_DASH_RE = re.compile(r"^-{3,}\s*$")
ENV_OPEN_RE = re.compile(r"^:::\{([a-zA-Z][\w-]*)\s*(.*)\}\s*$")
ENV_CLOSE_RE = re.compile(r"^:::\s*$")

# Beamer 프레임. `={4,}{속성}` 로 열고 `={4,}` 만으로(속성 없이) 닫는다 —
# `:::{이름}` ... `:::` 와 정확히 같은 관례(여는 쪽만 중괄호가 있고 닫는
# 쪽은 맨몸)를 그대로 따랐다. 4개 이상을 요구하는 이유는 `---`/`***`가
# 이미 수평선으로 예약돼 있는 것과 같은 논리로, 최소 개수를 두면 실수로
# 짧게 쓴 등호 줄과 구별하기 쉽다. 속성 문법은 `:::{}` 환경과 같은
# ATTR_KV_RE/parse_attrs 를 그대로 재사용한다(key="값" 또는 key=값,
# 쉼표로 나열) — 새 파싱 규칙을 또 만들 이유가 없었다.
FRAME_OPEN_RE = re.compile(r"^={4,}\{(.*)\}\s*$")
FRAME_CLOSE_RE = re.compile(r"^={4,}\s*$")

UL_RE = re.compile(r"^(\s*)[-*+](?:\s+|(?=\[))(.*)$")
OL_RE = re.compile(r"^(\s*)(\d+)[.)](?:\s+|(?=\[))(.*)$")

# 문단이 우연히 리스트 마커처럼 보이는 문자로 시작할 때(예: "1. 소요
# 시간은..."), 이걸 리스트로 인식하지 않고 있는 그대로 찍고 싶을 때 쓰는
# 이스케이프. UL_RE/OL_RE보다 먼저 검사해야 한다 — 이 검사에 걸리면
# 아예 리스트 디스패치 자체를 건너뛰고 문단으로 처리하므로, 여기를
# 지나 이스케이프를 벗겨낸 결과가 다시 UL_RE/OL_RE에 걸릴 걱정은 없다.
# 중괄호 문법을 고른 이유: 이 방언이 `{용어} :: 설명`, `{!옵션}`,
# `{unnumbered}`처럼 이미 중괄호 기반 표기를 여러 군데 쓰고 있어서
# 스타일이 일관되고, 백슬래시는 이 방언에서 인라인 각주(`\^[...]`)나
# 조사 매크로(`\은`, `\는` 등)처럼 이미 다른 여러 의미로 쓰이고 있어
# 줄 첫머리에 또 다른 뜻을 얹으면 오버로드가 될 수 있기 때문이다.
# `{옵션}` 뒤에 실제 마커가 이어와도(`- {!1.} 항목`) 이 정규식은 안
# 걸린다 — 그건 마커(`-`)가 이미 있고 그 뒤에 오는 리스트 옵션
# 블록(_extract_brace_option)이라, 애초에 이스케이프가 필요한 상황
# (마커 자체를 리터럴로 찍고 싶은 상황)이 아니다.
LIST_ESCAPE_UL_RE = re.compile(r"^(\s*)\{([-*+])\}(.*)$")
LIST_ESCAPE_OL_RE = re.compile(r"^(\s*)\{(\d+)\}([.)])(.*)$")
# 설명 리스트 `용어 :: 설명`.
#
# 예전 패턴 ^(\s*)(.*?)\s*::\s*(.*)$ 는 지나치게 헐거워서, 줄 어디에든 콜론이
# 둘 이상 붙어 있으면 통째로 설명 리스트로 삼켰다. 실제로 이런 것들이 다
# 걸렸다.
#
#   모두 `:::{name}` 이라는 일관된 문법으로   <- 환경 문법을 설명하는 문장
#   std::vector 를 쓴다                       <- C++ 이름공간
#   자세한 것은 `용어 :: 설명` 참고            <- 코드 스팬 안의 예시
#
# 그래서 세 가지를 요구한다.
#   1) :: 앞에 공백이 하나 이상 있을 것 (std::vector, a::b 를 걸러낸다)
#   2) :: 가 더 긴 콜론 덩어리의 일부가 아닐 것 ((?!:) 로 ::: 를 걸러낸다)
#   3) 용어가 비어 있지 않을 것
# 설명이 비어 있는 `용어 ::` 는 허용한다(세 번째 그룹이 None 이 된다).
#
# 코드 스팬 안의 :: 는 이것만으로 못 막는다. 아래 desc_match() 가 스팬을
# 가린 사본에 대고 매치해서 그 구멍을 메운다.
DESC_RE = re.compile(r"^(\s*)(\S.*?)\s+::(?!:)(?:\s+(.*?))?\s*$")


def _mask_inline_code(line):
    """인라인 코드 스팬 안을 같은 길이의 안전한 문자로 덮은 사본을 돌려준다.

    길이를 보존하므로, 가린 사본에서 얻은 매치 위치를 원본에 그대로 써서
    잘라낼 수 있다. 블록 단계에서는 아직 protect_inline_code() 가 돌기 전이라
    코드 스팬 안의 문자가 그대로 보인다는 점을 이 함수가 메운다.
    """
    if "`" not in line:
        return line
    out = []
    i, n = 0, len(line)
    while i < n:
        if line[i] == "\\" and i + 1 < n and line[i + 1] == "`":
            out.append(line[i:i + 2])
            i += 2
            continue
        m = _BACKTICK_RUN_RE.match(line, i)
        if not m:
            out.append(line[i])
            i += 1
            continue
        run = m.end() - m.start()
        j = m.end()
        close = None
        while j < n:
            m2 = _BACKTICK_RUN_RE.match(line, j)
            if m2:
                if (m2.end() - m2.start()) == run:
                    close = m2.end()
                    break
                j = m2.end()
            else:
                j += 1
        if close is None:
            out.append(line[m.start():m.end()])
            i = m.end()
            continue
        out.append("x" * (close - m.start()))
        i = close
    return "".join(out)


# 중괄호형 설명 리스트.  {용어} ::  설명
#
# 맨 표기(용어 :: 설명)가 남긴 마지막 오인식 여지를 없애기 위한 표기다.
# 두 가지를 요구한다.
#   1) 줄 첫머리(들여쓰기 제외)가 {..} 로 시작할 것
#   2) :: 뒤에 공백이나 탭이 **두 개 이상** 있을 것
# 산문이 우연히 이 꼴이 될 일은 사실상 없다. 덤으로 용어에 무엇이든 넣을 수
# 있다 — 공백, 콜론, {} 를 뺀 아무 문자나.
#
# 설명이 빈 {용어} :: 도 허용한다(세 번째 그룹이 None 이 된다).
DESC_BRACE_RE = re.compile(r"^(\s*)\{([^{}]+)\}[ \t]*::(?:[ \t]{2,}(.*?))?[ \t]*$")


def desc_match(line, cfg=None):
    """설명 리스트 줄이면 (들여쓰기, 용어, 설명)을, 아니면 None을 돌려준다.

    코드 스팬을 가린 사본에 매치한 뒤 위치로 원본을 잘라낸다. 길이를
    보존하는 마스킹이라 위치가 그대로 맞는다.
    """
    masked = _mask_inline_code(line)

    m = DESC_BRACE_RE.match(masked)
    if m:
        content = line[m.start(3):m.end(3)] if m.group(3) is not None else ""
        return len(m.group(1)), line[m.start(2):m.end(2)], content

    m = DESC_RE.match(masked)
    if not m:
        return None

    if cfg is not None and str(cfg.get("description_syntax", "both")).lower() == "braces":
        # 엄격 모드. 조용히 문단으로 떨어뜨리면 설명 리스트가 사라진 것을
        # 알아챌 수 없으므로, 옮겨 적을 자리를 알려준다.
        print(
            f"경고: 설명 리스트로 보이지만 중괄호형이 아니라 무시합니다 — "
            f"{line.strip()[:60]}\n"
            f"  description_syntax: braces 에서는 {{용어}} ::  설명 형태만 인정합니다.",
            file=sys.stderr,
        )
        return None

    content = line[m.start(3):m.end(3)] if m.group(3) is not None else ""
    return len(m.group(1)), line[m.start(2):m.end(2)], content

QUOTE_RE = re.compile(r"^>\s?(.*)$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
# :::{name key="v" key2=v2} 의 속성 파서. finditer로 key=value만 훑으므로
# 구분자는 공백이든 콤마든 상관없다. 다만 따옴표 없는 값에서 \S+ 를 쓰면
# 콤마까지 값으로 빨아들여서(place=htbp, → "htbp,") 조용히 오염됐다.
# 그래서 따옴표 없는 값에서는 공백과 콤마를 제외한다. 값에 콤마를 넣어야
# 하면 따옴표로 감싼다(raw="{1cm},{2cm}").
#
# 이 방언의 다른 속성 자리(figure의 {width=..., label=...}, heading의
# {unnumbered, label=...})가 모두 콤마 구분이라, 여기서도 콤마를 정식으로
# 받아 표기를 통일한다.
#
# 따옴표 값 안에 따옴표 자체를 넣어야 할 때는 두 번 겹쳐 쓴다(CSV/SQL
# 문자열 리터럴과 같은 관례) — `title="A --- ""B"""`이면 값이 정확히
# `A --- "B"`가 된다. `\"`(백슬래시 이스케이프)를 안 쓰는 이유는, 이
# 정규식 자체가 이스케이프라는 개념을 전혀 몰라서 어차피 `\"`를 만나도
# 그 앞의 백슬래시와 무관하게 바로 다음 `"`에서 값을 끊어버렸기
# 때문이다(즉 `\"`는 애초에 아무것도 escape하지 못하고 있었다) — 겹쳐
# 쓰는 방식은 정규식이 "따옴표 두 개가 연달아 오면 그건 값의 일부"라고
# 정확히 판단할 수 있어서 실제로 작동한다.
ATTR_KV_RE = re.compile(r'(\w+)\s*=\s*"((?:[^"]|"")*)"|(\w+)\s*=\s*([^\s,]+)')


# 환경 템플릿에서 쓰는 두 가지 확장.
#
#   %(key|기본값)s  속성이 없으면 기본값을 대신 꽂는다.
#   ?로 시작하는 줄  그 줄이 참조하는 속성이 하나라도 비어 있으면 줄을 통째로
#                    버린다. 맨 앞의 ? 는 줄을 남길 때 떼어낸다. 진짜 물음표로
#                    시작하는 줄이 필요하면 ?? 로 적는다.
#
# 이 둘이 없으면 caption이나 label처럼 있을 수도 없을 수도 있는 속성을 다룰
# 수 없었다. 하나라도 빠지면 %-포맷이 KeyError를 내고 템플릿 전체가 기본
# \begin{name} 으로 폴백해버렸기 때문이다. 그 폴백은 여전히 살아 있다 —
# 기본값도 ? 표시도 없는 속성이 빠지면 예전처럼 경고와 함께 폴백한다.
_TMPL_DEFAULT_RE = re.compile(r"%\((\w+)\|([^)]*)\)s")
_TMPL_PLACEHOLDER_RE = re.compile(r"%\((\w+)\)s")


def _apply_template_defaults(tmpl, ctx):
    """%(key|기본값)s 를 해소한다."""
    def _sub(m):
        key, default = m.group(1), m.group(2)
        # 판정 기준은 "값이 비었는가"가 아니라 "속성이 주어졌는가"다.
        # 그래야 align="" 처럼 일부러 빈 값을 줘서 기본값을 끄는 것이
        # 가능하다(빈 값이면 자리표시자가 남고, ? 줄이라면 그 줄이 버려진다).
        if key in ctx:
            return "%%(%s)s" % key
        # 기본값은 리터럴로 들어가므로 %-포맷이 다시 건드리지 않게 이스케이프
        return default.replace("%", "%%")
    return _TMPL_DEFAULT_RE.sub(_sub, tmpl)


def _apply_optional_lines(tmpl, ctx):
    """? 로 시작하는 줄 중 참조 속성이 비어 있는 것을 버린다."""
    out = []
    for line in tmpl.split("\n"):
        if not line.startswith("?"):
            out.append(line)
            continue
        if line.startswith("??"):
            out.append(line[1:])
            continue
        body = line[1:]
        keys = _TMPL_PLACEHOLDER_RE.findall(body)
        # 남아 있는 자리표시자가 모두 채워질 수 있을 때만 줄을 남긴다.
        # 자리표시자가 아예 없는 줄(= %(key|기본값)s 가 기본값으로 이미
        # 해소된 줄)은 버리지 않고 남긴다.
        if all(ctx.get(k) for k in keys):
            out.append(body)
    return "\n".join(out)


def parse_attrs(attr_str):
    attrs = {}
    for m in ATTR_KV_RE.finditer(attr_str or ""):
        if m.group(1):
            attrs[m.group(1)] = m.group(2).replace('""', '"')
        else:
            attrs[m.group(3)] = m.group(4)
    return attrs


def parse_heading_attrs(attr_str):
    attrs = {"unnumbered": False, "label": None}
    if not attr_str:
        return attrs
    for token in attr_str.split(","):
        token = token.strip()
        if not token:
            continue
        if token == "unnumbered" or token == "*":
            attrs["unnumbered"] = True
        elif "=" in token:
            k, v = token.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k == "label":
                attrs["label"] = v
            else:
                attrs[k] = v
        elif token.startswith("#"):
            attrs["label"] = token[1:]
    return attrs


# `||` 이음 표시. 블록 사이 구분자의 3상태 중 하나다.
#   False  : 빈 줄 없이 강제로 끊긴 것(:::/프레임 닫는 줄) -> "\n"
#   True   : 원문에 빈 줄이 있었음                           -> "\n\n"
#   JOIN   : `||` 로 명시적으로 이은 것                       -> "\n"
#            (앞뒤가 모두 평문 문단이면 앞 문단 끝에 `%` 를 붙인다)
#   JOIN_BR: 빈 줄 + `||`. 이음은 같되 `%` 대신 `\\` 로 행을 나눈다
JOIN_MARK = "||"
JOIN = "join"          # `||` 앞에 빈 줄이 없었다 -> 앞 문단 끝에 `%`
JOIN_BR = "join-br"    # `||` 앞에 빈 줄이 있었다 -> 앞 문단 끝에 `\\` (행 나눔)
_JOINS = (JOIN, JOIN_BR)


def _is_plain_paragraph(blk, cfg):
    """render_blocks() 의 분기 사슬에서 맨 끝 render_paragraph 로 떨어지는
    블록인가. 분기 조건이 바뀌면 이 함수도 같이 고쳐야 한다."""
    first = blk[0]
    if ENV_OPEN_RE.match(first) or FRAME_OPEN_RE.match(first):
        return False
    if HEADING_RE.match(first) and len(blk) == 1:
        return False
    if (HR_STAR_RE.match(first) or HR_DASH_RE.match(first)) and len(blk) == 1:
        return False
    if LIST_ESCAPE_UL_RE.match(first) or LIST_ESCAPE_OL_RE.match(first):
        return True
    if UL_RE.match(first) or OL_RE.match(first) or desc_match(first, cfg):
        return False
    if QUOTE_RE.match(first):
        return False
    if len(blk) >= 2 and "|" in first and TABLE_SEP_RE.match(blk[1]):
        return False
    if _is_grid_table(blk):
        try:
            parse_grid_table(blk)
            return False
        except GridTableError:
            return True
    if len(blk) == 1 and _PH_RE.fullmatch(blk[0].strip()):
        return False
    return True


def _join_suffix(prev_blk, next_blk, cfg, mark=JOIN):
    """`||` 로 이은 두 블록이 모두 평문 문단이면 앞 문단 끝에 붙일 것.
    JOIN 이면 `%` — 줄바꿈이 공백으로 남아 `''라고` 가 `'' 라고` 가 되는
    것을 막는다. JOIN_BR(빈 줄 + `||`)이면 `\\` — 그 자리에서 행을 나눈다.
    뒤 문단이 `[` 나 `*` 로 시작하면 `\\` 가 그것을 선택 인자로 삼아 버리므로
    `{}` 로 막는다. 어느 쪽이든 앞뒤 중 하나라도 문단이 아니면(목록·환경 등)
    아무것도 붙이지 않는다 — `\\` 를 목록 앞에 두면 빈 줄이 하나 생기기 때문."""
    if not (_is_plain_paragraph(prev_blk, cfg) and _is_plain_paragraph(next_blk, cfg)):
        return ""
    if mark == JOIN_BR:
        guard = "{}" if next_blk[0].lstrip()[:1] in ("[", "*") else ""
        return "\\\\" + guard
    return "%"


def split_blocks_indexed(lines):
    """split_blocks()와 완전히 같은 규칙으로 나누되, 각 블록이 lines의
    몇 번째 인덱스(0-based, [시작, 끝) 반개구간)에서 왔는지, 그리고
    split_blocks()의 had_blank_after(그 블록 뒤에 원문에 실제 빈 줄이
    있었는가)도 함께 돌려준다.

    --syncinfo 전용이다. split_blocks() 자체는 건드리지 않는다 — 실측으로
    확인한바 두 함수가 완전히 같은 블록 경계를 내놓으므로(뒤에 나오는
    render_blocks 재사용 부분 참고), 여기서 로직이 조금이라도 어긋나면
    sync 정보만 잘못되고 정작 .tex 출력에는 영향이 없다는 점에서 비교적
    안전하지만, 그래도 원본 split_blocks()와 동일하게 유지해야 한다.

    had_blank_after를 여기서도 반드시 같이 내야 하는 이유: generate_
    syncinfo()가 이 함수의 결과를 갖고 블록들을 다시 이어붙여 최종 .tex
    본문(body_tex)을 직접 만드는데, 그 이어붙이는 방식이 render_blocks()
    (--syncinfo 없을 때 쓰이는 일반 경로)와 정확히 같아야 한다. 한쪽은
    항상 "\\n\\n"으로, 다른 쪽은 had_blank_after에 따라 "\\n\\n"이나
    "\\n"으로 이으면, --syncinfo를 켜고 끄는 것만으로 같은 원고의 실제
    .tex 출력(문단 구분 여부)이 달라지는, sync 정확도보다 훨씬 심각한
    문제가 생긴다(실제로 겪은 버그 — {{포함}}으로 여러 파일을 합칠 때
    특히 잘 드러났다).
    """
    blocks = []
    buf = []
    buf_start = None
    env_depth = 0
    frame_depth = 0

    def flush(end_idx):
        nonlocal buf_start
        if buf:
            blocks.append([buf[:], buf_start, end_idx, False])
            buf.clear()
        buf_start = None

    for idx, line in enumerate(lines):
        if ENV_OPEN_RE.match(line):
            if env_depth == 0 and frame_depth == 0:
                flush(idx)
                buf_start = idx
            env_depth += 1
            buf.append(line)
            continue
        if ENV_CLOSE_RE.match(line) and env_depth > 0:
            env_depth -= 1
            buf.append(line)
            if env_depth == 0 and frame_depth == 0:
                flush(idx + 1)
            continue
        if FRAME_OPEN_RE.match(line):
            if env_depth == 0 and frame_depth == 0:
                flush(idx)
                buf_start = idx
            frame_depth += 1
            buf.append(line)
            continue
        if FRAME_CLOSE_RE.match(line) and frame_depth > 0:
            frame_depth -= 1
            buf.append(line)
            if env_depth == 0 and frame_depth == 0:
                flush(idx + 1)
            continue
        if env_depth > 0 or frame_depth > 0:
            buf.append(line)
            continue
        if line.strip() == "":
            flush(idx)
            if blocks and blocks[-1][3] not in _JOINS:
                blocks[-1][3] = True
        elif line.strip() == JOIN_MARK:
            flush(idx)
            if blocks and blocks[-1][3] != JOIN_BR:
                blocks[-1][3] = JOIN_BR if blocks[-1][3] is True else JOIN
        else:
            if not buf:
                buf_start = idx
            buf.append(line)
    flush(len(lines))
    return blocks


def split_blocks(lines):
    r"""빈 줄로 문서를 블록(문단·리스트·환경 등) 단위로 나눈다.

    각 블록은 (줄목록, had_blank_after) 쌍이다. had_blank_after는 "이
    블록과 다음 블록 사이에 원문에 실제로 빈 줄이 있었는가"를 뜻한다 —
    render_blocks()가 블록들을 이어붙일 때 이 값에 따라 빈 줄(새
    문단)로 이을지 그냥 줄바꿈으로 이을지를 정한다.

    이 구분이 필요한 이유: `:::{환경}`/Beamer 프레임(`={4,}`)은 재귀
    처리를 위해 닫는 줄을 만나는 즉시 강제로 블록을 끊는다(env_depth/
    frame_depth가 0으로 돌아오는 순간) — 원문에 빈 줄이 있었는지와
    무관하게. 그런데 "라는 예..."처럼 닫는 줄 바로 다음 줄(빈 줄 없이)
    에 글이 이어지면, 이 강제 분리 자체가 "새 문단"을 뜻하는 게
    아니다 — 한국어 조판에서는 이걸 새 문단(들여쓰기)으로 잘못 찍으면
    안 된다. 그래서 강제 분리는 일단 had_blank_after=False로 표시해
    두고, 그 뒤에 진짜 빈 줄을 만나면(그리고 그때 buf가 비어 있다면,
    즉 그 사이에 다른 내용 없이 곧장 빈 줄이 왔다면) 방금 플러시한
    블록의 표시를 True로 고쳐 쓴다.
    """
    blocks = []
    buf = []
    env_depth = 0
    frame_depth = 0

    def flush():
        if buf:
            blocks.append([buf[:], False])
            buf.clear()

    for line in lines:
        if ENV_OPEN_RE.match(line):
            if env_depth == 0 and frame_depth == 0:
                flush()
            env_depth += 1
            buf.append(line)
            continue
        if ENV_CLOSE_RE.match(line) and env_depth > 0:
            env_depth -= 1
            buf.append(line)
            if env_depth == 0 and frame_depth == 0:
                flush()
            continue
        if FRAME_OPEN_RE.match(line):
            if env_depth == 0 and frame_depth == 0:
                flush()
            frame_depth += 1
            buf.append(line)
            continue
        if FRAME_CLOSE_RE.match(line) and frame_depth > 0:
            frame_depth -= 1
            buf.append(line)
            if env_depth == 0 and frame_depth == 0:
                flush()
            continue
        if env_depth > 0 or frame_depth > 0:
            buf.append(line)
            continue
        if line.strip() == "":
            # 먼저 flush 해서 지금까지 쌓인 내용(있다면)을 blocks에
            # 반영한 다음, 그렇게 해서 생겼거나 이미 있던 마지막 블록에
            # "뒤에 실제 빈 줄이 있었다"고 표시한다 — 순서가 중요하다.
            # buf가 비어 있지 않은(=이 빈 줄이 어떤 문단을 막 끝낸)
            # 일반적인 경우, 그 문단을 blocks에 반영하는 flush()가
            # 먼저 일어나야 "마지막 블록"이 바로 그 문단을 가리킨다.
            flush()
            if blocks and blocks[-1][1] not in _JOINS:
                blocks[-1][1] = True
        elif line.strip() == JOIN_MARK:
            # `||` 한 줄: 블록 경계(빈 줄처럼 앞뒤를 갈라 준다)이지만 출력에서는
            # 문단을 나누지 않고 이어 붙인다. `||` 앞에 빈 줄이 있었으면(방금
            # flush 된 블록이 True 로 표시돼 있다) JOIN_BR — `%` 대신 `\\`.
            # `||` 뒤의 빈 줄은 뜻이 없다(빈 줄 분기가 이 표시를 덮어쓰지 않는다).
            flush()
            if blocks and blocks[-1][1] != JOIN_BR:
                blocks[-1][1] = JOIN_BR if blocks[-1][1] is True else JOIN
        else:
            buf.append(line)
    flush()
    return blocks


def render_frame(lines, cfg, pr):
    r"""Beamer 프레임. `={4,}{속성}` ... `={4,}` 사이를
    `\begin{환경}...\end{환경}`으로 감싼다(환경 이름은 기본이 `frame`).

    안쪽 내용은 render_environment()와 똑같은 방식으로 render_blocks()에
    재귀로 그대로 넘긴다 — 이 방언이 지원하는 모든 블록 문법(리스트,
    설명 리스트, 문단, 표 등)이 프레임 안에서도 바깥과 완전히 동일하게
    동작하게 하려는 것이다. "프레임 전용 파서"를 따로 만들지 않았다.

    속성은 `:::{환경}`과 똑같은 parse_attrs()/ATTR_KV_RE 를 그대로
    재사용한다(새 파싱 규칙을 또 만들 이유가 없었다).
      - `name="..."`     -> `\begin{frame}`/`\end{frame}` 대신
        `\begin{그값}`/`\end{그값}`을 쓴다. 안 주면 `frame`. Beamer
        확장 패키지(ltx-talk 등)가 `frame*`, `itemizedframe`처럼
        `frame`과 비슷하게 동작하는 새 환경을 만드는 경우를 위한
        것이다 — title/subtitle/opt/raw 처리는 환경 이름과 무관하게
        완전히 그대로다. 값은 환경 이름 자체라서 인라인 처리를 거치지
        않고 가공 없이 그대로 쓰인다(라텍 명령 이름 자리이지 화면에
        보이는 텍스트가 아니기 때문이다).
      - `title="..."`    -> `\frametitle{...}` (값은 인라인 처리를 거친다)
      - `subtitle="..."` -> `\framesubtitle{...}` (값은 인라인 처리를 거친다)
      - `opt=...`        -> `\begin{환경}[...]`의 대괄호 안에 가공 없이
        그대로 들어간다 — Beamer의 프레임 옵션(`fragile`, `shrink` 등)은
        원고 작성자가 정확히 원하는 문자열을 그대로 쓰는 게 맞다고
        보았다(다른 곳의 raw 계열 속성과 같은 태도).
      - `raw=...`        -> `\begin{환경}[opt]` 바로 뒤에(같은 줄에)
        가공 없이 그대로 이어붙는다. `:::{환경}`의 raw 속성과 같은
        예약어 취급이다 — opt가 없어도 `\begin{환경}raw값`처럼 그냥
        붙는다.
    title/subtitle/opt/raw 넷 다 없으면 대응하는 줄/조각 자체가 아예
    안 나온다 — 빈 `\frametitle{}`이나 빈 대괄호 `[]`를 억지로 만들어
    붙이지 않는다.
    """
    open_m = FRAME_OPEN_RE.match(lines[0])
    attrs = parse_attrs(open_m.group(1))
    inner_lines = lines[1:-1] if FRAME_CLOSE_RE.match(lines[-1]) else lines[1:]

    env_name = attrs.get("name") or "frame"
    out = []
    opt = attrs.get("opt", "")
    raw = attrs.get("raw", "")
    frame_line = rf"\begin{{{env_name}}}"
    if opt:
        frame_line += f"[{opt}]"
    frame_line += raw
    out.append(frame_line)
    if attrs.get("title"):
        out.append(rf"\frametitle{{{process_inline(attrs['title'], cfg, pr)}}}")
    if attrs.get("subtitle"):
        out.append(rf"\framesubtitle{{{process_inline(attrs['subtitle'], cfg, pr)}}}")

    inner_tex = render_blocks(inner_lines, cfg, pr)
    if inner_tex:
        out.append("")
        out.append(inner_tex)
    out.append(rf"\end{{{env_name}}}")
    return "\n".join(out)


def render_environment(lines, cfg, pr):
    open_m = ENV_OPEN_RE.match(lines[0])
    name, attr_str = open_m.group(1), open_m.group(2)
    attrs = parse_attrs(attr_str)
    inner_lines = lines[1:-1] if ENV_CLOSE_RE.match(lines[-1]) else lines[1:]

    tmpl = cfg["environments"].get(name)
    if tmpl is None:
        tmpl = cfg["environments"]["default"]
        # default 템플릿은 %(name)s와 %(raw)s만 쓴다. 그래서 등록되지 않은
        # 환경에 place=/caption= 같은 속성을 주면 아무 데도 쓰이지 않고
        # 조용히 사라진다 — 작성자는 표가 안 떠다니는 이유를 알 수 없다.
        # 버려지는 속성이 있으면 알려준다.
        dropped = [k for k in attrs if k != "raw"]
        if dropped:
            print(
                f"경고: 환경 '{name}'이(가) mapping.yaml에 등록돼 있지 않아 "
                f"속성 {', '.join(sorted(dropped))}이(가) 무시됩니다. "
                f"environments.{name}.begin 템플릿을 정의해야 반영됩니다.",
                file=sys.stderr,
            )
    fmt_ctx = dict(attrs)
    # "raw" 속성은 예약어처럼 취급한다: 값을 escape_text 등 어떤 처리도
    # 거치지 않고 %(raw)s 자리에 그대로 꽂아 넣는다. adjustwidth처럼
    # \begin{...}가 이름 없는(positional) 인자를 여러 개 받는 환경을 위한
    # 탈출구다 — 예: :::{adjustwidth raw={1cm}{1cm}} 이면 %(raw)s가
    # "{1cm}{1cm}"로 그대로 치환된다. attrs에 raw가 없으면 빈 문자열이
    # 기본값이라, raw를 안 쓰는 기존 환경/템플릿은 전혀 영향받지 않는다
    # (Python %-format은 템플릿이 참조하지 않는 여분의 dict 키를 그냥
    # 무시하므로).
    fmt_ctx.setdefault("raw", "")
    fmt_ctx["name"] = name

    # lines: keep 이면 블록 파서를 태우지 않고 원문의 행 구조를 그대로 넘긴다.
    #
    # 운문 환경이 이것을 필요로 한다. 보통의 문단은 여러 줄을 이어붙여 한
    # 문단으로 만드는 것이 옳지만, 시는 행이 곧 의미라서 이어붙이면 원문이
    # 망가진다. oblivoir-misc 의 hverse 처럼 행 끝에 \\ 를 요구하지 않는
    # 환경은 개행만 살려 주면 그대로 조판된다.
    #
    # 행 끝에 무언가를 붙여야 하는 환경(표준 verse 의 \\ 같은)은 line_end 로
    # 지정한다. 마지막 행과 빈 줄에는 붙이지 않는다 — 빈 줄은 연(stanza)
    # 구분이라 그대로 두어야 한다.
    # lines: raw 이면 인라인 처리 자체를 건너뛰고 원문을 글자 그대로 붙인다.
    #
    # TikZ 그림이 대표적인 이유다. \draw[...] (A)to[out=-90,in=90](B); 같은
    # 코드에서 [out=-90,in=90](B) 부분이 LINK_RE(마크다운 링크 문법)와
    # 우연히 같은 모양이라 \href{B}{out=-90,in=90}로 오인되어 버린다. 이런
    # 충돌은 TikZ뿐 아니라 raw LaTeX/외부 언어를 그대로 박아 넣는 환경이면
    # 늘 잠재해 있으므로, "이 환경 안은 절대 건드리지 마라"는 선언을 별도로
    # 마련했다.
    #
    # pr.protect() 로 감싸 자리표시자 하나로 바꿔 둔다. 이러면 이 환경
    # **밖에서** 이어지는 어떤 후속 처리(예: 같은 문서의 다른 곳에서 도는
    # escape_text, 인라인 서식 등)도 이 내용에 닿지 못한다 — 자리표시자는
    # 문서 조립이 끝나는 마지막 단계에서 pr.restore() 가 원문 그대로
    # 되돌려준다. process_inline 을 한 번도 거치지 않으므로 매크로도, 수식도,
    # 각주도, 색인도 전혀 해석되지 않는다 — 정의상 "전부 raw"이기 때문이다.
    if str(tmpl.get("lines", "")).lower() == "raw":
        inner_tex = pr.protect("\n".join(inner_lines))
    elif str(tmpl.get("lines", "")).lower() == "keep":
        line_end = tmpl.get("line_end", "")
        rendered, n = [], len(inner_lines)
        # 앞뒤 빈 줄은 떼어낸다. :::{hverse} 다음 줄과 ::: 앞 줄을 비워 두는
        # 편이 원고에서 읽기 좋은데, 그것이 그대로 나가면 빈 연이 생긴다.
        start, stop = 0, n
        while start < stop and not inner_lines[start].strip():
            start += 1
        while stop > start and not inner_lines[stop - 1].strip():
            stop -= 1
        body_lines = inner_lines[start:stop]
        for i, ln in enumerate(body_lines):
            if not ln.strip():
                rendered.append("")
                continue
            tex = process_inline(ln.strip(), cfg, pr)
            # 바로 다음 줄이 실제 행일 때만 행 끝 표시를 붙인다. 연의 마지막
            # 행(다음이 빈 줄)에 붙이면 연 구분이 두 번 일어나 간격이 벌어진다.
            nxt = body_lines[i + 1] if i + 1 < len(body_lines) else ""
            if line_end and nxt.strip():
                tex += line_end
            rendered.append(tex)
        inner_tex = "\n".join(rendered)
    else:
        inner_tex = render_blocks(inner_lines, cfg, pr)

    try:
        # begin과 end를 똑같이 다룬다. end에서도 속성을 쓸 수 있어야
        # figure처럼 캡션이 내용 "아래"에 오는 환경을 만들 수 있다.
        begin_tmpl = _apply_optional_lines(
            _apply_template_defaults(tmpl["begin"], fmt_ctx), fmt_ctx)
        end_tmpl = _apply_optional_lines(
            _apply_template_defaults(tmpl.get("end", r"\end{%s}" % name), fmt_ctx),
            fmt_ctx)
        begin = begin_tmpl % fmt_ctx
        end = end_tmpl % fmt_ctx
    except KeyError as e:
        # tmpl["begin"]이 요구하는 속성(예: mapping.yaml에 정의된
        # \begin{tcolorbox}[title={%(title)s}] 처럼)이 :::{...} 쪽에
        # 없으면, 예전에는 begin만 기본 \begin{name} 템플릿으로 대체하고
        # end는 그대로 환경 전용 템플릿(예: \end{tcolorbox})을 써서
        # \begin{note} ... \end{tcolorbox} 처럼 서로 짝이 안 맞는 출력이
        # 나왔다 — 이러면 LaTeX 컴파일이 반드시 깨진다. 이제는 속성이
        # 부족하면 begin과 end를 함께 기본 템플릿으로 폴백시켜 최소한
        # 짝은 맞춘다.
        missing = e.args[0] if e.args else "?"
        print(
            f"경고: 환경 '{name}'의 템플릿이 요구하는 속성 '{missing}'이(가) "
            f"주어지지 않아 기본 \\begin{{{name}}}...\\end{{{name}}} 형태로 대체합니다.",
            file=sys.stderr,
        )
        default_tmpl = cfg["environments"]["default"]
        begin = default_tmpl["begin"] % {"name": name, "raw": attrs.get("raw", "")}
        end = default_tmpl.get("end", r"\end{%s}" % name) % {"name": name}
    return f"{begin}\n{inner_tex}\n{end}"


def _extract_brace_option(text):
    """마커 다음에 오는 `{옵션}` 블록을, 중괄호 짝을 실제로 세어 가며
    추출한다.

    예전에는 정규식 `\\{([^}]*)\\}`로 이 블록을 잡았는데, `[^}]*`는
    "닫는 중괄호가 아닌 아무 문자"라 안쪽에 중괄호가 하나라도 있으면
    (예: `label={\\arabic*}`처럼 enumitem 옵션 자체가 중괄호를 쓰는
    경우) 그 안쪽 중괄호에서 조기에 닫혀 버려 옵션과 본문이 엉망으로
    잘리는 문제가 실측으로 확인됐다. 문자 단위로 깊이를 세면 중첩
    중괄호가 몇 겹이든 정확한 짝을 찾는다.

    text가 `{!`(느낌표로 시작하는 중괄호 블록)로 시작하지 않으면
    (None, text, None)을 그대로 돌려준다
    (옵션이 없는 보통 항목 — 세 번째 값 None은 "마커 바로 뒤 문자로
    직접 판정하라"는 신호다). 시작하면 (중괄호 안 내용, 그 뒤 나머지,
    옵션과 본문 사이에 공백이 있었는지)를 돌려준다. 세 번째 값을 따로
    돌려주는 이유: `{옵션}[라벨]`처럼 옵션 블록 바로 뒤에 대괄호 라벨이
    붙는 경우, "마커 바로 뒤 문자"는 언제나 옵션 블록 시작 중괄호이지
    실제 대괄호와 무관하므로, \\relax 삽입 판정(20.2절)은 옵션이 있을
    때 "옵션 블록과 본문 사이"의 공백을 봐야 정확하다 — 처음에는 이걸
    놓쳐서 `{...}[def]`가 공백 없이 붙어 있어도 원래 마커 뒤에 있던
    공백 때문에 \\relax가 잘못 붙는 문제를 실측으로 확인했다.

    짝이 끝내 안 맞으면(닫는 중괄호를 못 찾으면) 옵션 블록이 아니라고
    보고 (None, text, None)으로 안전하게 되돌아간다 — 원고의 중괄호
    실수를 이 함수가 나서서 진단하지는 않는다.
    """
    if not text.startswith("{"):
        return None, text, None
    depth = 0
    for i, ch in enumerate(text):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                opt = text[1:i]
                # 리스트 옵션은 `{!옵션}`처럼 **느낌표로 시작할 때만** 옵션이다.
                # 느낌표가 없는 `{...}`는 그냥 항목 본문의 일부이므로 건드리지
                # 않고 (None, text, None)을 돌려준다. 예전에는 느낌표가 없어도
                # 옵션으로 소비해 버려서, 본문 맨 앞에 중괄호로 묶은 글자를 쓴
                # 항목(`- {\bfseries 강조} 항목`)이 옵션으로 오인돼 사라졌다.
                if not opt.lstrip().startswith("!"):
                    return None, text, None
                raw_rest = text[i + 1:]
                rest = raw_rest.lstrip(" \t")
                space_before_rest = raw_rest != rest
                return opt, rest, space_before_rest
    return None, text, None


def _parse_list_opt(raw_opt_str):
    """`!`로 시작하는 리스트 옵션 문자열을 (대괄호 안에 넣을 옵션, 그
    뒤에 그대로 이어붙일 raw LaTeX)로 나눈다.

    - 따옴표 없이 그냥 콤마가 있으면(`1., \\firmlist`처럼) 첫 콤마에서
      나눈다 — 원래부터 있던 동작이다.
    - 통째로 큰따옴표로 감싸면(`"nosep,label={\\arabic*},ref=\\arabic*",
      \\tightlist`처럼) 그 안의 콤마는 전혀 구분자로 보지 않고 전체가
      그대로 대괄호 안에 들어간다. 닫는 따옴표 **바로 뒤에 오는 콤마**
      부터가 뒤에 붙는 raw LaTeX이다. enumitem처럼 `[key=value,
      key2=value2, ...]`형태로 옵션 자체가 콤마로 여러 개 나열되는
      패키지를 쓸 때 이 표기가 필요하다 — 안 그러면 그 콤마들이 전부
      "대괄호 안 vs 뒤에 붙일 raw LaTeX"의 경계로 오인된다.
    """
    clean = raw_opt_str.lstrip("!").strip()
    if clean.startswith('"'):
        end = clean.find('"', 1)
        if end == -1:
            # 닫는 따옴표를 못 찾았다 — 원고 실수다. 억지로 고치려 들지
            # 않고, 따옴표를 뗀 나머지 전체를 그냥 대괄호 옵션으로 쓴다.
            return clean[1:].strip(), ""
        bracket_opt = clean[1:end]
        tail = clean[end + 1:].strip()
        extra_opt = " " + tail[1:].strip() if tail.startswith(",") else ""
        return bracket_opt, extra_opt
    if "," in clean:
        bracket_opt, extra = clean.split(",", 1)
        return bracket_opt.strip(), " " + extra.strip()
    return clean.strip(), ""


def render_list(lines, cfg, pr):
    """마커로 시작하는 줄들을 itemize/enumerate/description으로 렌더한다.

    items의 각 원소는 [들여쓰기, 본문, 이어지는 줄들, 용어, 종류,
    마커뒤공백여부]다. 마지막 "종류"를 항목마다 따로 들고 다니는 것이
    중요하다. 예전에는 리스트 전체가 list_type 하나만 기억했는데, 그러면
    중첩 줄을 재구성할 때(_reconstruct_item_line) 부모의 종류로 마커를
    다시 붙여버려서 자식의 원래 마커가 지워졌다. 그 결과 불릿 안의 번호
    목록이 itemize로, 번호 안의 불릿이 enumerate로 나왔다.

    "마커뒤공백여부"는 `-[라벨] ...`(공백 없음)과 `- [본문] ...`(공백
    있음)을 구분하기 위한 것이다(20.2절 급 새 규칙 — LaTeX은 원래
    `\\item` 바로 뒤에 오는 `[...]`를 그 항목의 커스텀 라벨로 삼는데,
    본문에 진짜로 대괄호로 시작하는 텍스트를 쓰고 싶을 때는
    `\\item \\relax [...]`로 그 해석을 막아야 하는 게 LaTeX 자체의 특이
    케이스다). 공백이 없으면(`-[라벨]`) 의도한 라벨이라고 보고 그대로
    두고, 공백이 있으면(`- [본문]`) `\\relax`를 끼워 넣어 라벨로 오인되지
    않게 한다 — 단, 이 판정은 인라인 처리를 다 마친 뒤 "결과가 실제로
    리터럴 `[`로 시작하는 경우"에만 적용한다. `[표시](url)` 링크나
    `[^id]` 각주처럼 다른 대괄호 문법이 이미 다른 것으로 변환됐다면
    거기엔 `\\relax`가 끼어들 이유가 없다(문제 자체가 없으므로).
    """
    items = []
    raw_opt_str = None

    for line in lines:
        m_ul = UL_RE.match(line)
        m_ol = OL_RE.match(line)
        m_desc = None if (m_ul or m_ol) else desc_match(line, cfg)

        if m_ul:
            indent = len(m_ul.group(1))
            opt, content, opt_space = _extract_brace_option(m_ul.group(2))
            if opt and not raw_opt_str:
                raw_opt_str = opt.strip()
            if opt_space is not None:
                has_space = opt_space
            else:
                after_marker = indent + 1
                has_space = after_marker < len(line) and line[after_marker] in " \t"
            items.append([indent, content, [], None, "itemize", has_space])
        elif m_ol:
            indent = len(m_ol.group(1))
            opt, content, opt_space = _extract_brace_option(m_ol.group(3))
            if opt and not raw_opt_str:
                raw_opt_str = opt.strip()
            if opt_space is not None:
                has_space = opt_space
            else:
                after_marker = len(m_ol.group(1)) + len(m_ol.group(2)) + 1
                has_space = after_marker < len(line) and line[after_marker] in " \t"
            items.append([indent, content, [], None, "enumerate", has_space])
        elif m_desc:
            indent, term, desc_content = m_desc
            # 설명 리스트도 itemize/enumerate와 똑같이, 첫 항목의 설명이
            # `{옵션}`으로 시작하면 그걸 \begin{description}[옵션]으로
            # 뽑아낸다 — 같은 _extract_brace_option()/_parse_list_opt()를
            # 그대로 재사용한다. Beamer에서 `\begin{description}[<+-|
            # alert@+>]`처럼 description 자체에 오버레이 기본형을 주는
            # 문법이 정확히 이 자리에 필요해서 추가했다. 세 번째 반환값
            # (공백 여부)은 여기서 안 쓴다 — 설명 리스트의 대괄호
            # 라벨/relax 판정(has_space)은 이 옵션 블록과 무관한 별개
            # 메커니즘이라 항상 True로 고정해 온 기존 동작을 그대로 둔다.
            opt, desc_content, _ = _extract_brace_option(desc_content)
            if opt and not raw_opt_str:
                raw_opt_str = opt.strip()
            items.append([indent, desc_content, [], term.strip(), "description", True])
        else:
            if items:
                items[-1][2].append(line)

    if not items:
        return ""

    base_indent = min(it[0] for it in items)
    # 이 레벨의 환경은 base_indent에 실제로 놓인 첫 항목이 정한다. 한 레벨에
    # 서로 다른 마커가 섞이면 그중 첫 번째를 따른다 — 중첩된(더 깊은) 항목은
    # 재귀 호출에서 자기 종류를 스스로 결정하므로 여기 영향을 주지 않는다.
    env = next(it[4] for it in items if it[0] == base_indent)
    
    bracket_opt = ""
    extra_opt = ""
    if raw_opt_str:
        bracket_opt, extra_opt = _parse_list_opt(raw_opt_str)

    opt_part = f"[{bracket_opt}]" if bracket_opt else ""
    out = [rf"\begin{{{env}}}{opt_part}{extra_opt}"]

    i = 0
    while i < len(items):
        indent, content, cont, term, _item_type, has_space = items[i]
        if indent == base_indent:
            j = i + 1
            # cont 는 마커(불릿/번호/설명) 없이 이어지는 순수 문단 줄들이다
            # (마커가 있는 줄은 스캔 단계에서 이미 새 items 항목이 되었으므로
            # cont 안에는 절대 마커 줄이 섞이지 않는다). 예전 코드는 이 cont를
            # 그대로 중첩 리스트(sub_lines)로 넘겨 재귀 호출했는데, 마커가 없으니
            # 재귀 호출한 render_list 안에서 items가 하나도 만들어지지 않고
            # 통째로 버려지는 버그가 있었다. 여기서는 cont를 항목 본문(content)에
            # 직접 이어붙인다.
            full_content = _join_wrapped_lines(content, cont)

            # 진짜 중첩 리스트는 base_indent보다 더 들여쓰인 "다음" items 뿐이다.
            sub_lines = []
            while j < len(items) and items[j][0] > base_indent:
                sub_lines.append(_reconstruct_item_line(items[j]))
                sub_lines.extend(items[j][2])
                j += 1

            # description 리스트에 마커 항목(불릿/번호)이 섞여 들어오면 term이
            # None이다. 예전에는 그대로 process_inline에 넘겨 TypeError로
            # 죽었다. 라벨 없는 \item으로 떨어뜨려 최소한 조판은 되게 한다.
            if env == "description" and term is not None:
                term_tex = process_inline(term, cfg, pr)
                content_tex = process_inline(full_content, cfg, pr)
                out.append(rf"\item[{term_tex}] {content_tex}")
            else:
                item_tex = process_inline(full_content, cfg, pr)
                if has_space and item_tex.startswith("["):
                    # 인라인 처리를 다 마친 뒤에도 리터럴 대괄호가 살아
                    # 남았다는 것은 [표시](url) 링크나 [^id] 각주 같은 다른
                    # 대괄호 문법이 하나도 안 맞았다는 뜻이다 — 그러니 이
                    # 대괄호는 LaTeX의 \item[...] 커스텀 라벨 문법으로
                    # 오인될 위험이 있는 진짜 리터럴 텍스트다. 원본에
                    # 마커와 대괄호 사이에 공백이 있었다면(-[라벨]처럼
                    # 붙여 쓴 게 아니라 - [본문]처럼 띄어 썼다면) 라벨로
                    # 쓸 의도가 아니었다고 보고 \relax 를 끼워 넣어
                    # \item 이 이 대괄호를 자기 라벨로 삼지 못하게 막는다.
                    item_tex = r"\relax " + item_tex
                out.append(r"\item %s" % item_tex)

            if sub_lines:
                out.append(render_list(sub_lines, cfg, pr))
            i = j
        else:
            i += 1
            
    out.append(rf"\end{{{env}}}")
    return "\n".join(out)


def _join_wrapped_lines(content, cont_lines):
    r"""리스트 항목의 첫 줄(content) 뒤에 마커 없이 이어지는 문단 줄(cont_lines)을
    합친다. render_paragraph()와 정확히 같은 규칙이다 — 줄 끝에 공백 두 칸이
    있으면 강제 줄바꿈(\\)으로, 그 줄이 코드펜스/디스플레이 수식/환경처럼
    protect_block_level()이 통째로 압축해 둔 블록 레벨 플레이스홀더 하나뿐이면
    줄바꿈으로, 그 외에는 공백으로 이어붙인다.

    이 마지막 경우(블록 레벨 플레이스홀더)를 render_paragraph()와 똑같이
    처리하지 않으면, 리스트 항목 안에 코드펜스를 쓰고 그 뒤에 같은 항목의
    글이 이어질 때(`- 안내\n  \`\`\`verb\n  ...\n  \`\`\`\n  뒷글`처럼) 그
    `\end{verbatim}` 뒤에 뒷글이 같은 줄로 붙어 나온다 — 일부 verbatim류
    패키지가 `\end{...}` 뒤 같은 줄의 내용에까지 catcode 변경을 번지게
    하므로 실제로 조판이 깨질 수 있는 문제였다(실제로 겪은 버그. 최상위
    문단에서는 0.11.0에서 이미 고쳤는데, 리스트 항목은 render_paragraph가
    아니라 이 함수를 따로 쓰고 있어서 그 수정이 반영이 안 돼 있었다).
    """
    if not cont_lines:
        return content
    segments = [content] + list(cont_lines)
    joined = ""
    for idx, seg in enumerate(segments):
        stripped = seg.strip()
        joined += stripped
        if idx != len(segments) - 1:
            if _BLOCK_PLACEHOLDER_ONLY_RE.match(stripped):
                joined += "\n"
            else:
                joined += r" \\ " if seg.endswith("  ") else " "
    return joined


def _reconstruct_item_line(item):
    """중첩 리스트로 재귀할 때 넘길 마크다운 줄을 항목에서 되만든다.

    반드시 **그 항목 자신의 종류**로 마커를 붙여야 한다. 부모의 종류를 쓰면
    자식이 원래 무엇이었는지가 지워져서, 재귀 호출된 render_list가 부모와
    똑같은 환경을 만들어버린다.

    has_space(마커와 대괄호 사이 공백 여부)도 그대로 보존해서 되만든다 —
    안 그러면 중첩된 `-[라벨]`(공백 없음) 항목이 재구성 과정에서 무조건
    "- "(공백 있음)로 바뀌어 \\relax 판정이 뒤집혀 버린다. has_space가
    거짓일 수 있는 유일한 경우는 원본에서 마커 바로 뒤에 `[`가 왔을
    때뿐이므로(UL_RE/OL_RE 자체가 그렇게만 허용한다), content가 항상
    `[`로 시작한다는 보장이 있어 마커에 붙여 써도 안전하다.
    """
    indent, content, _, term, item_type, has_space = item
    if item_type == "description":
        return " " * indent + f"{term} :: {content}"
    if item_type == "itemize":
        prefix = "- " if has_space else "-"
    else:
        prefix = "1. " if has_space else "1."
    return " " * indent + prefix + content


# 셀 구분자는 백슬래시로 이스케이프하지 않은 | 뿐이다. 셀 안에 세로줄
# 문자를 그대로 쓰려면 \| 로 적는다(일반 마크다운과 같은 규칙).
_TABLE_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")


def _split_table_row(row):
    r"""표 한 행을 셀 목록으로 쪼갠다.

    바깥쪽 파이프를 떼어낼 때 strip("|")을 쓰면 행이 \| 로 끝나는 경우
    이스케이프된 파이프의 | 까지 같이 뜯겨 백슬래시만 남는다. 그래서
    양끝에서 "이스케이프되지 않은" 파이프 하나씩만 제거한다.
    """
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [c.strip().replace("\\|", "|") for c in _TABLE_CELL_SPLIT_RE.split(row)]


_TW_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_TW_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TW_MARK_RE = re.compile(r"[*_~`]")
_TABLE_WRAP_MIN_COL = 16     # 이 폭(반 em 단위) 이상인 열만 X 열 후보
_TABLE_COL_PAD = 2.4         # 열 하나가 차지하는 좌우 간격(반 em 단위, 근사)


def _cell_display_width(cell):
    """셀 한 칸의 화면 폭 추정치(반 em 단위). 한글·CJK·전각 문자는 2,
    그 밖은 1로 센다. 마크업 기호와 링크 주소·이미지는 출력에 안 나오므로
    빼고 센다. 정확한 조판 폭이 아니라 "넘칠 것인가"를 가늠하는 근사다.
    """
    t = _TW_IMG_RE.sub("", cell)
    t = _TW_LINK_RE.sub(r"\1", t)
    t = _TW_MARK_RE.sub("", t)
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
               for ch in t)


def _wrap_colspec(align_chars, header, body_cells, budget):
    """넘칠 표면 폭이 큰 열만 X[정렬,co=폭]으로 바꾼 열 지정을 돌려준다.
    넘치지 않거나 바꿀 열이 없으면 None(= 기존 l/c/r 그대로)."""
    ncol = len(align_chars)
    widths = [0] * ncol
    for row in [header] + body_cells:
        for j in range(min(ncol, len(row))):
            widths[j] = max(widths[j], _cell_display_width(row[j]))
    if sum(widths) + _TABLE_COL_PAD * ncol <= budget:
        return None
    wide = [j for j in range(ncol) if widths[j] >= _TABLE_WRAP_MIN_COL]
    if not wide:
        return None
    parts = []
    for j, a in enumerate(align_chars):
        parts.append(f"X[{a},co={widths[j]}]" if j in wide else a)
    return "".join(parts)


# 파이프 표 바로 다음 줄의 `{키=값,...}`(표 속성 줄). `|`가 없는 줄만 속성으로
# 본다 — `|`가 있으면 그냥 본문 행이다.
_TABLE_ATTR_LINE_RE = re.compile(r"^\{((?:[^{}|]|\{[^{}]*\})*)\}$")
_TABLE_ATTR_KEYS = ("env", "caption", "label", "rowhead", "widths")


def _table_begin(tattrs, colspec, cfg, pr, default_rowhead="1"):
    """표의 여는 줄(\\begin{tblr} / \\begin{longtblr}[...])과 환경 이름을 돌려준다.
    파이프 표와 grid 표가 공유한다. default_rowhead 는 longtblr 에서 쪽마다
    되풀이할 머리글 행 수의 기본값이다."""
    # env=long|longtblr 이면 \begin{longtblr}. longtblr 는 float 이 아니라
    # 자기 안에 캡션을 갖는 쪽나눔 표라서 caption/label 은 선택 인자 [...] 로
    # 나가고, 머리글 행은 rowhead=1 로 쪽마다 되풀이된다(rowhead=0 으로 끈다).
    env_val = (tattrs.get("env") or "tblr").strip().strip('"\'').lower()
    if env_val in ("long", "longtblr"):
        tenv = "longtblr"
    else:
        tenv = "tblr"
        if env_val not in ("tblr", "default", ""):
            print(f"경고: 표 속성 env={env_val} 을(를) 알 수 없습니다 "
                  f"(long 또는 tblr). tblr 로 처리합니다.", file=sys.stderr)
    caption_t = tattrs.get("caption")
    label_t = (tattrs.get("label") or "").strip()
    if tenv == "tblr" and (caption_t or label_t):
        print("경고: 표 속성 caption/label 은 env=long 일 때만 쓸 수 있습니다 "
              "(tblr 은 float 이 아니다 — 캡션이 필요하면 :::{table ...} 를 쓰십시오). "
              "무시합니다.", file=sys.stderr)
        caption_t, label_t = None, ""

    if tenv == "longtblr":
        opt_items = []
        if caption_t:
            opt_items.append("caption={%s}" % process_inline(caption_t, cfg, pr))
        if label_t:
            opt_items.append("label={%s}" % label_t)
        opt_part = "[" + ",".join(opt_items) + "]" if opt_items else ""
        rowhead = (tattrs.get("rowhead") or default_rowhead).strip()
        keys = ["colspec={%s}" % colspec]
        if rowhead and rowhead != "0":
            keys.append("rowhead=%s" % rowhead)
        begin = rf"\begin{{longtblr}}{opt_part}{{{','.join(keys)}}}"
    else:
        begin = rf"\begin{{tblr}}{{{colspec}}}"
    return begin, tenv


def render_table(lines, cfg, pr):
    rows = [ln.strip() for ln in lines if ln.strip()]

    # 마지막 행 바로 뒤(빈 줄 없이)에 `{env=long, caption=..., label=...}` 만으로
    # 된 줄이 오면 그 표의 속성이다. 예전에는 이 줄이 표의 한 행으로 먹혀
    # `\{env=...\}` 라는 쓰레기 행이 되었다. 빈 줄을 두면 이 줄은 표와 떨어진
    # 평범한 문단이 되므로(split_blocks), 이 함수는 붙어 있는 경우만 본다.
    tattrs = {}
    if len(rows) >= 3:
        m_attr = _TABLE_ATTR_LINE_RE.match(rows[-1])
        if m_attr:
            tattrs = parse_figure_attrs(m_attr.group(1))
            rows = rows[:-1]
    for k in tattrs:
        if k not in _TABLE_ATTR_KEYS:
            print(f"경고: 표 속성 '{k}' 은(는) 알 수 없는 키입니다 "
                  f"(쓸 수 있는 것: {', '.join(_TABLE_ATTR_KEYS)}).", file=sys.stderr)
    if "widths" in tattrs:
        print("경고: 표 속성 widths 는 grid 표에서만 쓸 수 있습니다. 무시합니다.",
              file=sys.stderr)
    header = _split_table_row(rows[0])
    sep_row = _split_table_row(rows[1])
    body_rows = rows[2:]
    ncol = len(header)
    
    align_chars = []
    for col in sep_row:
        if col.startswith(":") and col.endswith(":"):
            align_chars.append("c")
        elif col.endswith(":"):
            align_chars.append("r")
        else:
            align_chars.append("l")
            
    colspec = "".join(align_chars)
    if len(colspec) < ncol:
        colspec += "l" * (ncol - len(colspec))
    else:
        colspec = colspec[:ncol]

    # 열 개수는 헤더가 정한다. 모자라면 빈 칸으로 채우고, 넘치면 잘라낸다
    # — 예전에는 자르지 않아서 헤더보다 셀이 많은 행이 그대로 나가
    # tabularray가 열을 임의로 늘리거나 정렬이 어긋났다.
    body_cells = []
    for r_ in body_rows:
        cells = _split_table_row(r_)
        cells += [""] * (ncol - len(cells))
        body_cells.append(cells[:ncol])

    tw = cfg.get("tablewrap")
    if tw is True:
        tw = 70
    try:
        budget = float(tw or 0)
    except (TypeError, ValueError):
        budget = 0
    if budget > 0:
        wrapped = _wrap_colspec(list(colspec), header, body_cells, budget)
        if wrapped:
            colspec = wrapped

    begin, tenv = _table_begin(tattrs, colspec, cfg, pr)

    out = [begin, r"\toprule"]
    out.append(" & ".join(process_inline(h, cfg, pr) for h in header) + r" \\")
    out.append(r"\midrule")
    
    for cells in body_cells:
        out.append(" & ".join(process_inline(c, cfg, pr) for c in cells) + r" \\")
        
    out.append(r"\bottomrule")
    out.append(rf"\end{{{tenv}}}")
    return "\n".join(out)


# --------------------------------------------------------------------------
# pandoc grid table
# --------------------------------------------------------------------------
#
#   +-----------+---------------+
#   | 위치      | 기온          |
#   |           +-------+-------+
#   |           | 최저  | 최고  |
#   +===========+=======+=======+
#   | 남극      | -89.2 | 19.8  |
#   +-----------+-------+-------+
#
# 병합 셀(행·열)과 여러 줄 셀, 머리글 여러 줄(`=` 줄 위쪽), 바닥글(두 번째 `=`),
# 정렬(`+:===+:==:+`)을 읽는다. 파이프 표와 같이 booktabs 규칙(위, 머리글 아래,
# 아래)만 긋고, 머리글 안의 부분 구분선만 \cmidrule 로 옮긴다.
#
# 열 경계는 "문자 번호"가 아니라 "화면 칸"으로 맞춘다. 한글은 고정폭 에디터에서
# 2칸이라, 눈으로 맞춘 표가 문자 번호로는 어긋난다. 화면 칸으로 해석이 안 되면
# 문자 번호로도 한 번 시도한다.

class GridTableError(ValueError):
    pass


_GRID_TOP_RE = re.compile(r"^\+(?:[-:]+\+)+$")
_GRID_H = set("-=:+")      # 가로 테두리에 올 수 있는 글자
_GRID_V = set("|+")        # 세로 테두리에 올 수 있는 글자
_GRID_WIDE = "\x00"        # 전각 글자의 둘째 칸 표시


def _grid_lines(blk):
    """(표 줄 목록, 속성 줄 또는 None). 공통 들여쓰기는 뗀다."""
    lines = [ln.rstrip() for ln in blk]
    attr = None
    if len(lines) >= 4 and _TABLE_ATTR_LINE_RE.match(lines[-1].strip()):
        attr = lines[-1].strip()
        lines = lines[:-1]
    ind = min(len(l) - len(l.lstrip()) for l in lines if l.strip())
    return [l[ind:] for l in lines], attr


def _is_grid_table(blk):
    """첫 줄이 `+----+----+` 꼴이면 grid 표 후보다. 해석 가능 여부는 따로 본다."""
    return len(blk) >= 3 and bool(_GRID_TOP_RE.match(blk[0].strip()))


def _grid_matrix(lines, by_width):
    rows = []
    for ln in lines:
        r = []
        for ch in ln:
            r.append(ch)
            if by_width and unicodedata.east_asian_width(ch) in ("W", "F"):
                r.append(_GRID_WIDE)
        rows.append(r)
    w = max(len(r) for r in rows)
    for r in rows:
        r.extend(" " * (w - len(r)))
    return rows


def _parse_grid_once(lines, by_width):
    g = _grid_matrix(lines, by_width)
    n, w = len(g), len(g[0])

    def ch(r, c):
        return g[r][c] if 0 <= r < n and 0 <= c < w else " "

    if ch(0, 0) != "+":
        raise GridTableError("첫 줄이 `+` 로 시작하지 않습니다")
    # 모서리에서 사각형을 찾는다(docutils 방식): 왼쪽 위 모서리에서 오른쪽으로
    # 가장 가까운 `+`, 거기서 아래로 가장 가까운 `+` 를 잡고 아래·왼쪽 테두리를
    # 확인한다. 못 닫으면 더 먼 모서리를 시도한다.
    cells, seen, queue = [], set(), [(0, 0)]
    while queue:
        r, c = queue.pop(0)
        if (r, c) in seen or ch(r, c) != "+":
            continue
        seen.add((r, c))
        found = None
        for c2 in range(c + 1, w):
            if ch(r, c2) not in _GRID_H:
                break
            if ch(r, c2) != "+":
                continue
            for r2 in range(r + 1, n):
                if ch(r2, c2) not in _GRID_V:
                    break
                if ch(r2, c2) != "+":
                    continue
                if (all(ch(r2, x) in _GRID_H for x in range(c, c2 + 1))
                        and all(ch(y, c) in _GRID_V for y in range(r, r2 + 1))):
                    found = (r, c, r2, c2)
                    break
            if found:
                break
        if not found:
            continue  # 오른쪽·아래 가장자리의 모서리: 셀의 시작점이 아니다
        cells.append(found)
        r, c, r2, c2 = found
        queue += [(r, c2), (r2, c), (r2, c2)]
    if not cells:
        raise GridTableError("닫힌 셀을 찾지 못했습니다")

    # 검증: 셀 안쪽은 겹치지 않고, 글자는 모두 어떤 셀 안쪽에 있어야 하며,
    # 테두리 글자는 어떤 셀의 테두리여야 한다.
    for y in range(n):
        for x in range(w):
            c_ = g[y][x]
            if c_ == " " or c_ == _GRID_WIDE:
                inner = sum(1 for (r, c, r2, c2) in cells if r < y < r2 and c < x < c2)
                if inner == 0 and c_ == " ":
                    # 셀 밖의 공백: 표 오른쪽 바깥의 여백이면 허용
                    on_edge = any(r <= y <= r2 and c <= x <= c2 for (r, c, r2, c2) in cells)
                    if not on_edge and x < max(c2 for (_, _, _, c2) in cells):
                        raise GridTableError(
                            f"표의 {y + 1}째 줄 {x + 1}칸 근처가 어느 셀에도 속하지 않습니다 "
                            f"— 이 줄의 `|` 위치가 위아래 줄과 맞는지 확인하십시오")
                continue
            inner = [1 for (r, c, r2, c2) in cells if r < y < r2 and c < x < c2]
            edge = [1 for (r, c, r2, c2) in cells
                    if r <= y <= r2 and c <= x <= c2 and not (r < y < r2 and c < x < c2)]
            if len(inner) > 1:
                raise GridTableError(f"{y + 1}째 줄에서 셀이 겹칩니다")
            if not inner and not edge:
                raise GridTableError(
                    f"표의 {y + 1}째 줄 {x + 1}칸 `{c_}` 이(가) 어느 셀의 테두리와도 이어지지 않습니다 "
                    f"— 모서리 `+` 나 세로선 `|` 가 어긋났거나 줄이 모자란지 확인하십시오")

    xs = sorted({x for (_, a, _, b) in cells for x in (a, b)})
    ys = sorted({y for (a, _, b, _) in cells for y in (a, b)})
    if ys[0] != 0 or ys[-1] != n - 1:
        raise GridTableError("표의 첫 줄과 끝 줄이 가로 테두리가 아닙니다")

    def border(y):
        return "".join(c_ for c_ in g[y] if c_ != _GRID_WIDE)

    out = []
    for (r, c, r2, c2) in cells:
        rows_txt = ["".join(c_ for c_ in g[y][c + 1:c2] if c_ != _GRID_WIDE).strip()
                    for y in range(r + 1, r2)]
        paras, cur = [], []
        for t in rows_txt:
            if t:
                cur.append(t)
            elif cur:
                paras.append(" ".join(cur))
                cur = []
        if cur:
            paras.append(" ".join(cur))
        out.append({"row": ys.index(r), "col": xs.index(c),
                    "rs": ys.index(r2) - ys.index(r), "cs": xs.index(c2) - xs.index(c),
                    "paras": paras})
    nrows, ncols = len(ys) - 1, len(xs) - 1
    eq = [i for i, y in enumerate(ys) if "=" in border(y)]
    header_rows = eq[0] if eq else 0
    footer_start = eq[1] if len(eq) > 1 else None

    def seg(y, j):
        return "".join(c_ for c_ in g[y][xs[j] + 1:xs[j + 1]] if c_ != _GRID_WIDE)

    aline = ys[eq[0]] if eq else 0
    aligns = []
    for j in range(ncols):
        sg = seg(aline, j)
        if sg.startswith(":") and sg.endswith(":") and len(sg) > 1:
            aligns.append("c")
        elif sg.endswith(":"):
            aligns.append("r")
        else:
            aligns.append("l")
    # 머리글 안쪽의 부분 구분선 -> \cmidrule 범위(1-based, 닫힌 구간)
    cmid = {}
    for i in range(1, header_rows):
        y = ys[i]
        cols = [j + 1 for j in range(ncols)
                if seg(y, j) and set(seg(y, j)) <= set("-=:")]
        ranges = []
        for j in cols:
            if ranges and ranges[-1][1] == j - 1:
                ranges[-1][1] = j
            else:
                ranges.append([j, j])
        if ranges:
            cmid[i - 1] = ranges
    dash_w = [xs[j + 1] - xs[j] - 1 for j in range(ncols)]
    return {"cells": out, "nrows": nrows, "ncols": ncols, "header_rows": header_rows,
            "footer_start": footer_start, "aligns": aligns, "cmid": cmid,
            "dash_widths": dash_w}


def parse_grid_table(blk):
    """grid 표 블록을 해석한다. 화면 칸 기준으로 먼저, 안 되면 문자 번호 기준으로."""
    lines, attr = _grid_lines(blk)
    try:
        return _parse_grid_once(lines, True), attr
    except GridTableError as e1:
        if not any(unicodedata.east_asian_width(c) in ("W", "F") for ln in lines for c in ln):
            raise
        try:
            return _parse_grid_once(lines, False), attr
        except GridTableError:
            raise e1


def render_grid_table(blk, cfg, pr):
    tbl, attr = parse_grid_table(blk)
    tattrs = parse_figure_attrs(_TABLE_ATTR_LINE_RE.match(attr).group(1)) if attr else {}
    for k in tattrs:
        if k not in _TABLE_ATTR_KEYS:
            print(f"경고: 표 속성 '{k}' 은(는) 알 수 없는 키입니다 "
                  f"(쓸 수 있는 것: {', '.join(_TABLE_ATTR_KEYS)}).", file=sys.stderr)
    nrows, ncols = tbl["nrows"], tbl["ncols"]
    grid = [[None] * ncols for _ in range(nrows)]
    for cl in tbl["cells"]:
        grid[cl["row"]][cl["col"]] = cl

    # 열 지정: 기본은 자연 너비(정렬 글자만). 파이프 표와 같이 넘칠 열만 X 로
    # 바꾼다(tablewrap). widths=dash 면 pandoc 처럼 테두리의 대시 수 비율로
    # 모든 열을 X[정렬,co=폭] 로 둔다.
    aligns = tbl["aligns"]
    colspec = "".join(aligns)
    widths_mode = (tattrs.get("widths") or "auto").strip().strip('"\'').lower()
    if widths_mode == "dash":
        colspec = "".join(f"X[{a},co={max(w, 1)}]" for a, w in zip(aligns, tbl["dash_widths"]))
    else:
        if widths_mode not in ("auto", ""):
            print(f"경고: 표 속성 widths={widths_mode} 을(를) 알 수 없습니다 "
                  f"(auto 또는 dash). auto 로 처리합니다.", file=sys.stderr)
        tw = cfg.get("tablewrap")
        if tw is True:
            tw = 70
        try:
            budget = float(tw or 0)
        except (TypeError, ValueError):
            budget = 0
        if budget > 0:
            texts = [[" ".join(grid[r][c]["paras"]) if grid[r][c] and grid[r][c]["cs"] == 1 else ""
                      for c in range(ncols)] for r in range(nrows)]
            wrapped = _wrap_colspec(list(aligns), [""] * ncols, texts, budget)
            if wrapped:
                colspec = wrapped

    hrows = tbl["header_rows"]
    begin, tenv = _table_begin(tattrs, colspec, cfg, pr, default_rowhead=str(hrows))
    out = [begin, r"\toprule"]
    for r in range(nrows):
        if tbl["footer_start"] is not None and r == tbl["footer_start"]:
            out.append(r"\midrule")
        elif hrows and r == hrows:
            out.append(r"\midrule")
        parts = []
        for c in range(ncols):
            cl = grid[r][c]
            if cl is None:
                parts.append("")
                continue
            text = r" \par ".join(process_inline(p, cfg, pr) for p in cl["paras"])
            if cl["rs"] > 1 or cl["cs"] > 1:
                opts = ([f"r={cl['rs']}"] if cl["rs"] > 1 else []) + ([f"c={cl['cs']}"] if cl["cs"] > 1 else [])
                text = r"\SetCell[" + ",".join(opts) + "]{}" + text
            parts.append(text)
        out.append(" & ".join(parts) + r" \\")
        for a, b in tbl["cmid"].get(r, []):
            out.append(rf"\cmidrule[lr]{{{a}-{b}}}")
    out.append(r"\bottomrule")
    out.append(rf"\end{{{tenv}}}")
    return "\n".join(out)


def render_blockquote(lines, cfg, pr):
    inner = [QUOTE_RE.match(ln).group(1) if QUOTE_RE.match(ln) else ln for ln in lines]

    # 앞뒤의 빈 줄은 문단 구분이 아니라 여백이므로 세지 않는다. 가운데에
    # 빈 줄이 남아 있으면 인용이 두 문단 이상이라는 뜻이다.
    start, stop = 0, len(inner)
    while start < stop and not inner[start].strip():
        start += 1
    while stop > start and not inner[stop - 1].strip():
        stop -= 1
    multi = any(not ln.strip() for ln in inner[start:stop])

    env = cfg.get("blockquote_multi_env", "quotation") if multi \
        else cfg.get("blockquote_env", "quote")

    inner_tex = render_blocks(inner, cfg, pr)
    return f"\\begin{{{env}}}\n{inner_tex}\n\\end{{{env}}}"


def render_paragraph(lines, cfg, pr):
    r"""문단을 이루는 여러 줄을 한 줄로 접는다. 보통은 그 사이를 공백
    하나로 잇는다(markdown의 "느슨한 줄바꿈"이 문단 안에서는 공백일
    뿐이라는 관례) — 다만 그 줄이 코드펜스/디스플레이 수식/수식·표
    환경처럼 protect_block_level()이 통째로 압축해 둔 블록 레벨
    플레이스홀더 하나뿐이라면 공백 대신 줄바꿈으로 잇는다.

    이게 필요한 이유: 코드펜스는 (env/frame과 달리) split_blocks()가
    아니라 훨씬 이전 단계(protect_block_level)에서 이미 "그 줄 하나"로
    압축되므로, 뒤따르는 텍스트와 원래 다른 줄이었다는 사실 자체가
    이 시점에는 안 보인다 — 그냥 여느 문단 속 두 줄처럼 보여서 공백
    으로 이어붙여지면, 나중에 플레이스홀더가 실제 `\end{verbatim}`
    등으로 복원될 때 그 뒤 텍스트가 같은 줄에 바로 따라붙는다. 일부
    verbatim류 패키지는 `\end{...}` 뒤에 오는 내용이 같은 줄에 있으면
    그 환경이 바꿔 둔 catcode가 그 내용에도 번져 버리므로, 반드시
    줄을 갈라 둬야 한다.
    """
    parts = []
    for ln in lines:
        hard_break = ln.endswith("  ")
        stripped = ln.strip()
        parts.append((stripped, hard_break, bool(_BLOCK_PLACEHOLDER_ONLY_RE.match(stripped))))
    joined = ""
    for i, (t, hb, is_block_ph) in enumerate(parts):
        joined += t
        if i != len(parts) - 1:
            if is_block_ph:
                joined += "\n"
            else:
                joined += r" \\ " if hb else " "
    return process_inline(joined, cfg, pr)


def render_blocks(lines, cfg, pr):
    blocks = split_blocks(lines)
    out = []
    for blk, _had_blank_after in blocks:
        first = blk[0]

        if ENV_OPEN_RE.match(first):
            out.append(render_environment(blk, cfg, pr))
            continue

        if FRAME_OPEN_RE.match(first):
            out.append(render_frame(blk, cfg, pr))
            continue

        m_h = HEADING_RE.match(first)
        if m_h and len(blk) == 1:
            level = len(m_h.group(1))
            cmd = cfg["headings"].get(level, "paragraph")
            
            title_raw = m_h.group(2).strip()
            attr_str = m_h.group(3)
            attrs = parse_heading_attrs(attr_str)
            
            if attrs.get("unnumbered"):
                cmd += "*"

            title = process_inline(title_raw, cfg, pr)

            # toc= 는 \section[목차용 짧은 제목]{본문 제목} 의 대괄호 인자다.
            # 목차·페이지 헤더에는 짧은 쪽이, 본문에는 긴 쪽이 나가게 하고
            # 싶을 때 쓴다. unnumbered(*판)에는 대괄호 인자 자체가 없으므로
            # 함께 쓰였으면 조용히 무시한다 — LaTeX 이 어차피 받지 않는
            # 조합을 오류로 알리는 것보다, 번호 없는 절 제목 자체는 그대로
            # 살리는 편이 낫다.
            toc_title = attrs.get("toc")
            if toc_title and not attrs.get("unnumbered"):
                toc_tex = process_inline(toc_title, cfg, pr)
                res = rf"\{cmd}[{toc_tex}]{{{title}}}"
            else:
                res = rf"\{cmd}{{{title}}}"

            if attrs.get("label"):
                res += rf"\label{{{attrs['label']}}}"

            out.append(res)
            continue

        if HR_STAR_RE.match(first) and len(blk) == 1:
            asterism_cmd = cfg.get("asterism", r"\bigskip")
            out.append(asterism_cmd)
            continue

        if HR_DASH_RE.match(first) and len(blk) == 1:
            hr_cmd = cfg.get("hr", r"\noindent\rule{\linewidth}{0.5pt}")
            out.append(hr_cmd)
            continue

        m_ul_esc = LIST_ESCAPE_UL_RE.match(first)
        m_ol_esc = LIST_ESCAPE_OL_RE.match(first)
        if m_ul_esc or m_ol_esc:
            if m_ul_esc:
                indent, marker, rest = m_ul_esc.groups()
                literal_first = indent + marker + rest
            else:
                indent, num, punct, rest = m_ol_esc.groups()
                literal_first = indent + num + punct + rest
            out.append(render_paragraph([literal_first] + blk[1:], cfg, pr))
            continue

        if UL_RE.match(first) or OL_RE.match(first) or desc_match(first, cfg):
            out.append(render_list(blk, cfg, pr))
            continue

        if QUOTE_RE.match(first):
            out.append(render_blockquote(blk, cfg, pr))
            continue

        if _is_grid_table(blk):
            try:
                out.append(render_grid_table(blk, cfg, pr))
                continue
            except GridTableError as e:
                print(f"경고: grid 표를 해석하지 못해 문단으로 처리합니다 ({e}).",
                      file=sys.stderr)

        if len(blk) >= 2 and "|" in first and TABLE_SEP_RE.match(blk[1]):
            out.append(render_table(blk, cfg, pr))
            continue

        if len(blk) == 1 and _PH_RE.fullmatch(blk[0].strip()):
            out.append(pr.restore(blk[0].strip()))
            continue

        out.append(render_paragraph(blk, cfg, pr))

    # 블록 사이 구분자: split_blocks() 가 기록해 둔 had_blank_after를
    # 따른다 — 원문에 실제 빈 줄이 있었으면 "\n\n"(새 문단으로 찍힘),
    # 없었으면(:::{환경}/Beamer 프레임이 재귀 처리를 위해 닫는 줄에서
    # 강제로 블록을 끊었을 뿐이면) "\n"(줄만 바꾸고 새 문단으로는 찍지
    # 않는다). 한국어 조판에서는 후자를 새 문단(들여쓰기)으로 잘못
    # 찍으면 안 되기 때문이다 — "::: 뒤에 빈 줄이 없다"는 원고
    # 작성자의 선택 자체가 "이건 새 문단이 아니다"라는 뜻이다.
    pieces = []
    for i, piece in enumerate(out):
        if i < len(out) - 1 and blocks[i][1] in _JOINS:
            piece += _join_suffix(blocks[i][0], blocks[i + 1][0], cfg, blocks[i][1])
        pieces.append(piece)
        if i < len(out) - 1:
            pieces.append("\n\n" if blocks[i][1] is True else "\n")
    return "".join(pieces)


# --------------------------------------------------------------------------
# 6. 최상위 변환 함수
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# 문법 점검 (--lint)
# --------------------------------------------------------------------------
#
# 이 방언에는 "오류를 내지 않고 조용히 다른 결과가 나오는" 실수가 몇 가지
# 있다. 변환은 성공하고 PDF도 나오는데 리스트가 문단으로 뭉개져 있거나,
# 각주가 엉뚱하게 늘어나 있는 식이다. 눈으로 잡기 어려운 종류라 따로 훑는다.
#
# 검사 항목은 짐작이 아니라 실제로 밟았던 실수들이다.

_LINT_MARK_RE = re.compile(r"^ {0,3}(?:[-*+]\s|\d+[.)]\s)")


def _lint_fence_open(line):
    """여는 펜스면 매치를 돌려준다.

    변환기가 실제로 쓰는 두 패턴을 그대로 쓴다. ```showexam ratio=0.4 처럼
    정보 문자열에 =, . 이 들어가는 경우는 _FENCE_OPEN_RE 가 아니라
    _SE_FENCE_OPEN_RE 가 잡으므로 둘 다 본다.
    """
    return _FENCE_OPEN_RE.match(line) or _SE_FENCE_OPEN_RE.match(line)
_LINT_ENV_LOOSE_RE = re.compile(r"^:::\s+\{")
_LINT_FRAME_LOOSE_RE = re.compile(r"^={4,}\s+\{")
_LINT_PROSE_DESC_RE = re.compile(r"\S\s+::(?!:)\s")


def _lint_blocks(lines):
    """빈 줄로 나뉜 블록 목록을 (시작줄번호0기준, 줄목록)으로 돌려준다.

    코드 펜스 안의 빈 줄은 블록을 나누지 않는다. `:::{환경}`과 Beamer
    프레임(`={4,}`) 안의 빈 줄도 마찬가지다 — 변환기 본체
    (split_blocks())가 이 블록들 안에서는 빈 줄로 안 쪼개는데(env_depth/
    frame_depth 추적), 이 함수가 그 사실을 모른 채 코드펜스만 보고
    독자적으로 블록을 나누면 실제 변환 결과와 다른 그림을 보게 된다.
    실제로 이게 빠져 있어서, Beamer 프레임의 여는 줄+리스트+닫는 줄이
    (그 사이에 빈 줄이 없어도) 통째로 "리스트 아닌 하나의 문단 블록"
    으로 오인되고, 그 블록 첫 줄(`={4,}{...}`)이 리스트 마커가 아니라는
    이유로 안의 진짜 리스트 항목들이 "문단에 흡수된 리스트 마커"로
    오탐되는 버그가 있었다(1번 검사 참고). depth 추적 자체는
    split_blocks_indexed()의 것을 그대로 가져왔다 — 이미 검증된 로직을
    또 새로 만들 이유가 없었다.

    펜스 안은 검사 대상이 아니므로 in_fence 표시도 함께 돌려준다.
    """
    out, cur, start = [], [], 0
    in_fence, fence, fence_start = False, "", 0
    env_depth = frame_depth = 0
    for i, ln in enumerate(lines):
        # 펜스 판정은 반드시 변환기와 같은 정규식을 써야 한다. 예전에는
        # 여기만 헐거운 패턴(^\s*`{3,})을 썼는데, 그 탓에 CRLF 파일에서
        # 변환기는 닫는 펜스를 인식하지 못해 문서 절반을 코드로 삼키는데
        # 린터는 "문제 없음"이라고 답하는 일이 벌어졌다.
        opened = _lint_fence_open(ln)
        closed = _FENCE_CLOSE_RE.match(ln)
        if not in_fence and opened:
            in_fence, fence, fence_start = True, opened.group(1), i
        elif in_fence and closed and len(closed.group(1)) >= len(fence):
            in_fence = False

        # 코드펜스 안에서는 env/frame 마커를 판정하지 않는다 — 가이드
        # 문서처럼 코드펜스로 `:::{...}`나 `====`를 "예시로 보여주는"
        # 경우가 흔한데, 그건 리터럴 텍스트일 뿐 진짜 환경/프레임이
        # 아니다.
        if not in_fence:
            if ENV_OPEN_RE.match(ln):
                env_depth += 1
            elif ENV_CLOSE_RE.match(ln) and env_depth > 0:
                env_depth -= 1
            elif FRAME_OPEN_RE.match(ln):
                frame_depth += 1
            elif FRAME_CLOSE_RE.match(ln) and frame_depth > 0:
                frame_depth -= 1

        blank_splits = not in_fence and env_depth == 0 and frame_depth == 0
        if blank_splits and (not ln.strip() or ln.strip() == JOIN_MARK):
            if cur:
                out.append((start, cur))
                cur = []
        else:
            if not cur:
                start = i
            cur.append(ln)
    if cur:
        out.append((start, cur))
    return out, (fence_start if in_fence else None)


def collect_footnote_defs(text):
    """본문에서 각주 정의 식별자만 모아 돌려준다."""
    _, body = split_frontmatter(text)
    return {m.group(1) for m in
            (FOOTNOTE_DEF_RE.match(ln) for ln in body.split("\n")) if m}


def lint_source(text, path=None, base_dir=None, known_defs=None):
    """원고를 훑어 (줄번호, 등급, 메시지) 목록을 돌려준다.

    known_defs 는 "이 파일 밖에서 정의된 각주 식별자" 집합이다. 마스터
    파일과 {{포함}} 하위 파일에 참조와 정의가 나뉘어 있는 경우가 흔한데,
    파일마다 따로 검사하면 그것이 전부 "정의 없는 각주" 오탐이 된다.
    """
    issues = []

    def add(lineno, level, msg):
        issues.append((lineno, level, msg))

    # front matter는 여기서 직접 본다. split_frontmatter()를 부르면 YAML이
    # 깨졌을 때 stderr로 경고가 한 번 더 나가는데, 린터는 줄 번호가 붙은
    # 진단으로 돌려주는 편이 낫다.
    fm = FRONTMATTER_RE.match(text)
    if fm:
        raw_fm = fm.group(1)
        body = text[fm.end():]

        # 들여쓰기에 쓴 탭. YAML은 탭을 들여쓰기로 쓸 수 없어서, 블록
        # 스칼라(preamble: | 등) 안이라도 파싱이 통째로 실패한다. 그러면
        # 헤더 전체가 무시되어 class도 setup도 mapping도 먹지 않는다.
        # LaTeX 편집기에서 복사해 붙이면 흔히 생긴다 — 그쪽에서는 탭이
        # 그냥 공백이라 아무 표시가 나지 않기 때문이다.
        for i, ln in enumerate(raw_fm.split("\n")):
            stripped = ln.lstrip(" ")
            if stripped.startswith("\t"):
                add(i + 2, "오류",
                    "front matter의 들여쓰기에 탭이 있습니다. YAML은 탭을 "
                    "들여쓰기로 쓸 수 없어 헤더 전체가 무시됩니다 — 공백으로 "
                    "바꾸십시오.")

        try:
            parsed = yaml.safe_load(raw_fm)
        except yaml.YAMLError as e:
            first = str(e).split("\n")[0]
            add(1, "오류", f"front matter의 YAML을 읽지 못해 헤더 전체가 "
                           f"무시됩니다. {first}")
            parsed = None
        else:
            if parsed is not None and not isinstance(parsed, dict):
                add(1, "오류", "front matter가 key: value 형태가 아니어서 "
                               "헤더 전체가 무시됩니다.")
    else:
        body = text

    offset = len(text[:len(text) - len(body)].split("\n")) - 1

    lines = body.split("\n")
    blocks, unclosed_fence = _lint_blocks(lines)

    if unclosed_fence is not None:
        add(unclosed_fence + 1 + offset, "오류",
            "코드 펜스가 닫히지 않았습니다. 이 아래 내용이 전부 코드로 취급됩니다.")

    # 펜스 안의 줄 번호를 모아둔다(그 안은 검사하지 않는다).
    fenced = set()
    in_fence, fence = False, ""
    for i, ln in enumerate(lines):
        opened = _lint_fence_open(ln)
        closed = _FENCE_CLOSE_RE.match(ln)
        if not in_fence:
            if opened:
                in_fence, fence = True, opened.group(1)
                fenced.add(i)
            continue
        fenced.add(i)
        if closed and len(closed.group(1)) >= len(fence):
            in_fence = False

    # ── 1. 리스트 항목 안에 블록 요소 ─────────────────────────────
    # 이 방언은 항목 본문에 빈 줄을 허용하지 않는다. 빈 줄을 두면 그
    # 지점에서 리스트가 닫히고, 뒤따르는 항목들이 통째로 한 문단으로
    # 뭉쳐 마커가 평문으로 찍힌다. 오류가 나지 않아 알아채기 어렵다.
    #
    # 이 판정은 "블록의 첫 줄이 리스트 마커가 아니다"를 근거로 삼는데,
    # `:::{환경}`이나 Beamer 프레임(`={4,}`)의 여는 줄 역시 리스트
    # 마커가 아니다 — 그런데 실제 변환기는 그 안쪽 내용을 재귀적으로
    # render_blocks()에 넘기므로, 안쪽의 진짜 리스트는 바깥 블록과
    # 완전히 무관하게 독립적으로 인식된다. 이 재귀 구조를 그대로
    # 반영하지 않으면, 환경/프레임 여는 줄 바로 다음에 오는 정상적인
    # 리스트 전체가 "문단에 흡수됐다"고 오탐된다(실제로 겪은 버그).
    # 그래서 블록이 환경/프레임으로 열리면 그 안쪽만 떼어내 같은 검사를
    # 재귀적으로 다시 돌린다 — 변환기의 재귀 구조를 그대로 따라간
    # 것이다.
    #
    # 같은 이유로 설명 리스트(`{용어}:: 설명` 또는 `용어 :: 설명`)도
    # 예외다 — `_LINT_MARK_RE`는 불릿/번호 리스트 마커만 알고 `::`는
    # 전혀 모른다. 설명 리스트 항목 밑에 들여쓴 하위 리스트를 두는 건
    # (사용자 예시의 `{첫 항목}:: 해설` 다음 줄에 `  1. ABCDE`처럼)
    # 정상 문법인데, blk[0]이 desc_match()로 설명 리스트임을 확인하지
    # 않으면 "리스트 아닌 문단"으로 오판되어 그 아래 진짜 하위 리스트가
    # "문단에 흡수됐다"고 오탐된다(실제로 겪은 버그).
    def _check_orphan_list_markers(blks):
        for st, blk in blks:
            if st in fenced:
                continue
            if ENV_OPEN_RE.match(blk[0]) or FRAME_OPEN_RE.match(blk[0]):
                is_closed = ENV_CLOSE_RE.match(blk[-1]) or FRAME_CLOSE_RE.match(blk[-1])
                inner_lines = blk[1:-1] if is_closed and len(blk) > 1 else blk[1:]
                inner_blocks, _ = _lint_blocks(inner_lines)
                _check_orphan_list_markers([(st + 1 + s, b) for s, b in inner_blocks])
                continue
            if QUOTE_RE.match(blk[0]):
                # 인용(`>`)도 변환기가 `> `를 떼고 안쪽을 재귀적으로
                # render_blocks()에 넘기므로 같은 방식으로 따라간다. 안
                # 보면 인용 안의 `줄 이어쓰기` 바로 다음 줄에 붙은 `- 항목`이
                # 경고 없이 한 문단으로 뭉쳐 버린다. 접두를 떼도 줄 수와
                # 순서가 그대로이므로 줄 번호는 st + s 로 그대로 이어진다.
                inner_lines = [QUOTE_RE.match(ln).group(1) if QUOTE_RE.match(ln) else ln
                               for ln in blk]
                inner_blocks, _ = _lint_blocks(inner_lines)
                _check_orphan_list_markers([(st + s, b) for s, b in inner_blocks])
                continue
            if _LINT_MARK_RE.match(blk[0]) or desc_match(blk[0]) is not None:
                continue
            for k, ln in enumerate(blk[1:], 1):
                if (st + k) in fenced:
                    continue
                if _LINT_MARK_RE.match(ln):
                    add(st + k + 1 + offset, "오류",
                        "리스트 마커가 문단에 흡수됐습니다. 마커 앞에 빈 줄이 없거나(문단 "
                        "바로 뒤에 붙음), 앞 항목 안에 빈 줄이 있어 리스트가 끊긴 것입니다 — "
                        "리스트 앞에는 빈 줄을 두고, 항목 본문에는 빈 줄을 넣지 마십시오.")
                    break

    _check_orphan_list_markers(blocks)

    # ── 2. ::: 짝과 공백 ─────────────────────────────────────────
    depth, opens = 0, []
    for i, ln in enumerate(lines):
        if i in fenced:
            continue
        if _LINT_ENV_LOOSE_RE.match(ln):
            add(i + 1 + offset, "오류",
                "`:::` 와 `{` 사이에 공백이 있어 커스텀 환경으로 인식되지 않습니다.")
        if ENV_OPEN_RE.match(ln):
            depth += 1
            opens.append(i)
        elif ENV_CLOSE_RE.match(ln):
            if depth == 0:
                add(i + 1 + offset, "경고", "열린 적 없는 `:::` 닫는 줄입니다.")
            else:
                depth -= 1
                opens.pop()
    for i in opens:
        add(i + 1 + offset, "오류", "`:::` 블록이 닫히지 않았습니다.")

    # ── 2b. Beamer 프레임(====) 짝과 공백 ─────────────────────────
    frame_depth, frame_opens = 0, []
    for i, ln in enumerate(lines):
        if i in fenced:
            continue
        if _LINT_FRAME_LOOSE_RE.match(ln):
            add(i + 1 + offset, "오류",
                "`====` 와 `{` 사이에 공백이 있어 프레임으로 인식되지 않습니다.")
        if FRAME_OPEN_RE.match(ln):
            frame_depth += 1
            frame_opens.append(i)
        elif FRAME_CLOSE_RE.match(ln):
            if frame_depth == 0:
                add(i + 1 + offset, "경고", "열린 적 없는 `====` 닫는 줄입니다.")
            else:
                frame_depth -= 1
                frame_opens.pop()
    for i in frame_opens:
        add(i + 1 + offset, "오류", "Beamer 프레임(`====`)이 닫히지 않았습니다.")

    # ── 3. 표: 둘째 줄이 구분선인가 ──────────────────────────────
    for st, blk in blocks:
        if st in fenced or "|" not in blk[0] or _LINT_MARK_RE.match(blk[0]):
            continue
        if len(blk) >= 2 and not TABLE_SEP_RE.match(blk[1]):
            if sum(1 for ln in blk if "|" in ln) >= 2:
                add(st + 1 + offset, "경고",
                    "표처럼 보이지만 둘째 줄이 정렬 구분선(`|---|---|`)이 아니어서 "
                    "평범한 문단이 됩니다.")

    # ── 3b. grid 표를 해석할 수 있는가 ───────────────────────────
    for st, blk in blocks:
        if st in fenced or not _is_grid_table(blk):
            continue
        try:
            parse_grid_table(blk)
        except GridTableError as e:
            add(st + 1 + offset, "오류",
                f"grid 표를 해석할 수 없습니다: {e}. 변환하면 표가 아니라 평범한 "
                f"문단이 됩니다.")

    # ── 4. 각주 ─────────────────────────────────────────────────
    defined = set(known_defs or ())
    for i, ln in enumerate(lines):
        if i in fenced:
            continue
        m = FOOTNOTE_DEF_RE.match(ln)
        if m:
            defined.add(m.group(1))
            continue
        if _FOOTNOTE_DEF_LOOSE_RE.match(ln):
            add(i + 1 + offset, "오류",
                "각주 정의의 식별자에 쓸 수 없는 문자가 있습니다 "
                "(라틴 알파벳·숫자·`_`·`-` 만). 정의로 수집되지 않고 본문에 남습니다.")

    for i, ln in enumerate(lines):
        if i in fenced:
            continue
        # 코드 스팬 안의 `[^note1]` 은 문법을 설명하는 예시이지 참조가 아니다.
        for m in FOOTNOTE_REF_RE.finditer(_mask_inline_code(ln)):
            key = m.group(1)
            if key in defined:
                continue
            # 식별자처럼 생겼는데 정의가 없다 = 오타일 가능성이 높다.
            # 인라인 각주로 조용히 둔갑하므로 알려준다.
            if re.fullmatch(r"[A-Za-z0-9_-]+", key):
                add(i + 1 + offset, "경고",
                    f"`[^{key}]` 는 정의가 없어 \"{key}\" 라는 인라인 각주가 됩니다. "
                    f"참조하려던 것이라면 식별자 오타를 확인하십시오.")

    # ── 5. 산문 속 :: (설명 리스트 오인식) ───────────────────────
    for st, blk in blocks:
        if st in fenced or _LINT_MARK_RE.match(blk[0]):
            continue
        first = _mask_inline_code(blk[0])
        # 중괄호형 `{용어} ::  설명`은 문법이 명시적이라(줄 머리의 {..}, :: 뒤
        # 공백 둘 이상) 산문이 우연히 이 꼴이 될 일이 없다 — 경고할 이유가
        # 없다. 경고가 필요한 것은 맨 표기(`용어 :: 설명`)뿐이다.
        if DESC_BRACE_RE.match(first):
            continue
        if desc_match(blk[0]) and _LINT_PROSE_DESC_RE.search(first):
            add(st + 1 + offset, "경고",
                "공백으로 둘러싼 `::` 가 있어 설명 리스트로 인식됩니다. "
                "의도한 것이 아니라면 `:` 하나로 바꾸거나 코드 스팬으로 감싸십시오.")

    # ── 6. {{포함}} 파일 ────────────────────────────────────────
    base = Path(base_dir) if base_dir else Path(".")
    for i, ln in enumerate(lines):
        if i in fenced:
            continue
        for m in INCLUDE_RE.finditer(_mask_inline_code(ln)):
            name = m.group(1).strip()
            try:
                batch_names = _expand_transclusion_range(name, base)
            except IncludeError as e:
                add(i + 1 + offset, "오류", str(e))
                continue
            if batch_names is not None:
                # 배치 트랜스클루전 — 확장된 이름 하나하나에 대해 존재
                # 여부만 확인한다(각 이름은 그 자체로 tex:/확장자 규칙을
                # 그대로 따르므로, 재귀 호출로 같은 검사를 재사용한다).
                for one_name in batch_names:
                    if one_name.startswith("tex:"):
                        tex_name = one_name[len("tex:"):].strip()
                        target = Path(tex_name) if Path(tex_name).is_absolute() else base / tex_name
                        if not target.is_file():
                            add(i + 1 + offset, "오류", f"포함 파일이 없습니다: {target}")
                        continue
                    if not Path(one_name).suffix:
                        add(i + 1 + offset, "오류",
                            f"`{{{{{name}}}}}` 이 펼쳐진 `{one_name}` 에 확장자가 없습니다.")
                        continue
                    target = Path(one_name) if Path(one_name).is_absolute() else base / one_name
                    if not target.is_file():
                        add(i + 1 + offset, "오류", f"포함 파일이 없습니다: {target}")
                continue
            if name.startswith("tex:"):
                # {{tex:파일}} — 마크다운이 아니라 날 LaTeX을 그대로
                # 끼워 넣는 문법(20.1절)이므로, ".md" 확장자 요구도
                # 없고 하위 파일로 재귀 검사하지도 않는다(_lint_targets
                # 참고) — 존재 여부만 확인한다.
                tex_name = name[len("tex:"):].strip()
                if not tex_name:
                    add(i + 1 + offset, "오류",
                        f"`{{{{{name}}}}}` 에 파일 이름이 없습니다.")
                    continue
                target = Path(tex_name) if Path(tex_name).is_absolute() else base / tex_name
                if not target.is_file():
                    add(i + 1 + offset, "오류", f"포함 파일이 없습니다: {target}")
                continue
            if not Path(name).suffix:
                add(i + 1 + offset, "오류",
                    f"`{{{{{name}}}}}` 에 확장자가 없습니다. `.md` 를 자동으로 "
                    f"붙여주지 않습니다.")
                continue
            target = Path(name) if Path(name).is_absolute() else base / name
            if not target.is_file():
                add(i + 1 + offset, "오류", f"포함 파일이 없습니다: {target}")

    # ── 7. 헤딩이 독립 블록인가 ─────────────────────────────────
    for st, blk in blocks:
        if st in fenced or not HEADING_RE.match(blk[0]):
            continue
        if len(blk) > 1:
            add(st + 1 + offset, "오류",
                "헤딩 아래에 빈 줄 없이 본문이 붙어 있습니다. 헤딩은 한 줄짜리 "
                "블록이어야 인식됩니다.")

    # ── 8. `||` 이음 표시에 이을 대상이 있는가 ─────────────────────
    marks = [i for i, ln in enumerate(lines) if i not in fenced and ln.strip() == JOIN_MARK]
    for i in marks:
        prev = next((j for j in range(i - 1, -1, -1) if lines[j].strip()), None)
        nxt = next((j for j in range(i + 1, len(lines)) if lines[j].strip()), None)
        if prev is None or nxt is None:
            add(i + 1 + offset, "경고",
                "`||` 가 문서의 맨 처음이나 맨 끝에 있어 이을 대상이 없습니다.")
        elif lines[prev].strip() == JOIN_MARK or lines[nxt].strip() == JOIN_MARK:
            add(i + 1 + offset, "경고", "`||` 가 연달아 나옵니다. 하나면 충분합니다.")

    issues.sort(key=lambda t: (t[0], t[1]))
    return issues


def _lint_targets(root):
    """검사할 파일 목록을 (경로, 본문) 으로 돌려준다.

    {{포함}} 으로 끌어오는 하위 파일까지 포함한다 — 변환기와 마찬가지로
    이제 재귀적이다(포함된 파일 안의 {{또 다른 포함}}도 계속 따라간다).
    단행본이라면 마스터 파일은 {{...}} 줄만 늘어놓은 껍데기이고 본문은
    전부 하위 파일에 있는데, 그 하위 파일이 다시 챕터를 몇 단계로
    쪼개 놓았을 수도 있다 — 거기까지 안 보면 검사할 것이 남지 않는다.

    병합해서 한 덩어리로 검사하지는 않는다. 그러면 줄 번호가 원고의 어느
    파일 몇 행인지 알 수 없게 된다. 파일마다 따로 보되, 각주 정의만은
    전체에서 모아 공유한다(참조와 정의가 파일을 넘나드는 일이 흔하다).

    seen(이미 목록에 올린 파일의 절대경로)이 순환 방지를 겸한다 — 변환기
    자신의 IncludeError처럼 시끄럽게 멈추지는 않는다(린트는 "문제를
    찾아 보여주는" 도구이지 변환을 실행하는 게 아니므로, 순환 자체는
    조용히 무시하고 나머지 검사를 계속 진행하는 쪽을 택했다). 순환이나
    깊이 초과가 실제로 변환에 문제가 되는지는 변환기 자신의 IncludeError
    가 이미 정확히 알려주므로, 여기서 또 같은 오류를 반복해 보고할
    필요는 없다.
    """
    out = [(root, read_source_text(root))]
    seen = {root.resolve()} if root.exists() else set()
    queue = [out[0]]
    while queue:
        cur_path, cur_text = queue.pop(0)
        _, body = split_frontmatter(cur_text)
        for m in INCLUDE_RE.finditer(_mask_inline_code_multiline(body)):
            name = m.group(1).strip()
            try:
                batch_names = _expand_transclusion_range(name, root.parent)
            except IncludeError:
                # 오류 자체는 lint_source()의 6번 항목이 이미 보고하므로,
                # 여기서는 그냥 재귀 대상에서 빼고 조용히 넘어간다.
                continue
            names = batch_names if batch_names is not None else [name]
            for one_name in names:
                if one_name.startswith("tex:"):
                    # {{tex:파일}} 은 날 LaTeX이지 마크다운이 아니므로, 마크다운
                    # 문법으로 재귀 검사할 대상에 넣지 않는다 — 존재 여부는
                    # lint_source() 의 6번 항목이 이미 따로 확인한다.
                    continue
                # 상대 경로는 변환기와 똑같이 항상 root(최상위 파일)의
                # 폴더 기준이다 — cur_path(지금 스캔 중인 파일)가 몇
                # 단계에 있든 기준점은 바뀌지 않는다.
                target = Path(one_name) if Path(one_name).is_absolute() else root.parent / one_name
                try:
                    key = target.resolve()
                except OSError:
                    key = target
                if key in seen or not target.is_file():
                    continue
                seen.add(key)
                try:
                    entry = (target, read_source_text(target))
                except SourceError as e:
                    print(f"경고: 포함 파일을 읽지 못해 검사에서 뺍니다 — {e}", file=sys.stderr)
                    continue
                out.append(entry)
                queue.append(entry)
    return out



def _mask_inline_code_multiline(text):
    return "\n".join(_mask_inline_code(ln) for ln in text.split("\n"))


def run_lint(paths):
    """--lint 진입점. 오류가 하나라도 있으면 1을 돌려준다."""
    worst = 0
    for path in paths:
        root = Path(path)
        try:
            targets = _lint_targets(root)
        except SourceError as e:
            print(f"오류: {e}", file=sys.stderr)
            worst = 1
            continue

        # 각주 정의는 전체에서 모아 공유한다.
        all_defs = set()
        for _, text in targets:
            all_defs |= collect_footnote_defs(text)

        total_err = total_warn = 0
        for p, text in targets:
            issues = lint_source(text, path=p, base_dir=p.parent,
                                 known_defs=all_defs)
            for lineno, level, msg in issues:
                print(f"{p}:{lineno}: {level}: {msg}")
            n_err = sum(1 for _, lv, _ in issues if lv == "오류")
            total_err += n_err
            total_warn += len(issues) - n_err

        scope = f"{root}" if len(targets) == 1 else f"{root} (+포함 {len(targets) - 1}개)"
        if total_err or total_warn:
            print(f"{scope}: 오류 {total_err}건, 경고 {total_warn}건")
        else:
            print(f"{scope}: 문제 없음")
        if total_err:
            worst = 1
    return worst


# front matter에서 스크립트가 직접 쓰는 키. 이 목록에 없는 키가 "모르는 키"다.
KNOWN_META_KEYS = {
    "class", "classoption", "classoptions", "preamble", "beforestart",
    "title", "author", "date", "toplevel", "mapping", "mappingrule", "setup",
    "compileoption", "pandocoption", "mmdoption", "baseheaderlevel", "latexmkoption",
    # graphicspath: ["./","figures/"] — preamble 맨 끝에
    # \IfPackageLoadedTF{graphicx}{}{\usepackage{graphicx}} +
    # \graphicspath{{./}{figures/}} 두 줄을 붙인다(_build_header_lines
    # 참고). 여기 등록해 두지 않으면 metadata_macros()가 이 값(리스트)을
    # \def\NM 매크로로 만들려다 문자열이 아니라 조용히 건너뛰거나(단일
    # 문자열로 줬을 때는 만들어져 버려서) 원고 작성자가 의도하지 않은
    # \NMgraphicspath 매크로가 딸려 나온다.
    "graphicspath",
    # maketitle: true, tocloft: {...} — \begin{document} 바로 다음에
    # \maketitle/\tableofcontents/\listoffigures/\listoftables 를 자동으로
    # 넣어 준다(_build_frontmatter_commands 참고). 여기 등록해 두지 않으면
    # tocloft(딕셔너리 값)를 metadata_macros() 가 \def\NM 매크로로 만들려다
    # 문자열이 아닌 값이라 오류를 내거나 이상한 결과를 낼 수 있다.
    "maketitle", "tocloft",
    # ndhmain: 은 ndhmd4tex.py 자신은 전혀 안 읽는다 — {{포함}}될 때는
    # 어차피 서브파일의 front matter 전체가 버려지므로 컴파일에 아무
    # 영향이 없다(20장). 오직 ndhmdsync.py(별도 배포되는 짝 스크립트)가
    # "이 파일을 직접 열어 정방향 검색을 할 때, 실제로는 이 최상위
    # 파일의 일부로 컴파일된다"는 힌트로 읽는 용도다. KNOWN_META_KEYS에
    # 넣어 두는 이유는 그것뿐이다 — 안 넣으면 순수 알파벳 키라
    # metadata_macros()가 무해하지만 불필요한 \def\NMndhmain{...} 를
    # 프리앰블에 만들어 버린다(서브파일을 실수로 단독 컴파일했을 때).
    "ndhmain",
}

# 제어열 이름으로 쓸 수 있는 키만 넘긴다. \def\NM<key> 를 만들 것이므로
# 알파벳만 허용한다 — 숫자·밑줄·붙임표가 든 이름은 catcode 11 이 아니라
# 제어열 이름이 거기서 끊긴다.
_META_MACRO_KEY_RE = re.compile(r"^[A-Za-z]+$")


def metadata_macros(meta, cfg=None):
    r"""모르는 키를 \def\NM<key>{값} 목록으로 만든다.

    값이 스칼라(문자열·수·참거짓)인 것만 넘긴다. 리스트나 사전은 LaTeX 쪽에
    옮길 뾰족한 방법이 없고, 억지로 넘기면 파이썬 표현이 그대로 새어나온다.

    **키는 소문자로 낮춰서 매크로를 만든다.** LaTeX 매크로 이름은 대소문자를
    구별하므로, YAML에 Theme: 라고 적고 프리앰블에 \NMtheme 이라 쓰면 조용히
    어긋난다. 낮춰두면 원고 쪽 표기가 어떻든 프리앰블은 한 가지로 쓰면 된다.
    """
    prefix = "NM" if cfg is None else str(cfg.get("metadata_macro_prefix", "NM"))
    if not prefix:
        return []

    # 알려진 키의 대소문자만 다른 변형은 오타일 가능성이 높다. class: 를
    # Class: 라고 적으면 문서 클래스로 쓰이지 않고 \NMclass 만 만들어지는데,
    # 오류가 나지 않아 "왜 안 먹지"로 헤매게 된다.
    known_lower = {k.lower(): k for k in KNOWN_META_KEYS}

    out, seen = [], {}
    for k, v in meta.items():
        if not isinstance(k, str) or k in KNOWN_META_KEYS:
            continue
        if k.startswith("_") or not _META_MACRO_KEY_RE.match(k):
            continue
        if isinstance(v, bool):
            v = "true" if v else "false"
        elif isinstance(v, (int, float)):
            v = str(v)
        elif not isinstance(v, str):
            continue

        low = k.lower()
        if low in known_lower:
            print(
                f"경고: front matter의 '{k}' 는 '{known_lower[low]}' 의 "
                f"대소문자만 다른 이름이라 그 키로 쓰이지 않습니다. "
                f"\\{prefix}{low} 매크로만 만들어집니다.",
                file=sys.stderr,
            )
        if low in seen and seen[low] != k:
            print(
                f"경고: front matter의 '{seen[low]}' 와 '{k}' 가 소문자로 낮추면 "
                f"같은 이름이 되어 뒤엣것만 남습니다.",
                file=sys.stderr,
            )
        seen[low] = k
        out.append(rf"\def\{prefix}{low}{{{v}}}")
    return out


# author 필드 안의 ^[...] 를 \thanks{...} 로 바꾼다. 본문의 인라인 각주와
# 같은 문법(INLINE_FOOTNOTE_RE, 16장)이지만, \author 안에서는 관례상
# \footnote 가 아니라 \thanks 를 쓴다 — \footnote 는 title/author 를 만드는
# 시점(\maketitle 이전, 페이지 번호도 안 잡힌 상태)에 쓰면 각주 번호가
# 어긋나기 쉬운데, \thanks 는 titlepage 전용으로 만들어진 명령이라 그 문제가
# 없다.
_AUTHOR_THANKS_RE = re.compile(r"(?<!\^)\^\[(" + _BRACKET_BODY + r")\]")


def _build_author(author):
    """author: 값(문자열 또는 리스트)을 \\author{...} 안에 넣을 문자열로.

    리스트면 항목마다 이 치환을 적용한 뒤 \\and 로 잇는다 — 여러 저자를
    \\author{A \\and B} 형태로 나열하는 LaTeX 관례를 그대로 따른 것이다.
    author 필드 자체는(title 과 마찬가지로) raw 텍스트로 다룬다는 기존
    원칙은 그대로 둔다 — 여기서 하는 일은 오직 ^[...] 치환과 \\and 이어
    붙이기뿐이고, **굵게** 같은 다른 마크다운 서식은 이전과 똑같이 손대지
    않는다.
    """
    def _sub(text):
        return _AUTHOR_THANKS_RE.sub(lambda m: r"\thanks{%s}" % m.group(1), str(text))

    if isinstance(author, list):
        return r" \and ".join(_sub(a) for a in author)
    return _sub(author)


def _build_header_lines(meta, cfg=None, pandoc=False, mmd=False):
    """front matter로부터 헤더(프리앰블) 줄 리스트를 만든다.

    build_document()와 generate_syncinfo()가 공유한다 — sync 쪽은 본문이
    최종 .tex 파일에서 몇 번째 줄부터 시작하는지 알아야 하는데, 그러려면
    build_document()가 만드는 헤더와 정확히 같은 줄 수를 계산해야 한다.
    로직을 두 곳에 따로 두면 한쪽만 바뀌었을 때 조용히 어긋나므로, 이
    조립 부분 자체를 공유한다.
    """
    documentclass = meta.get("class", "book")
    classoptions = meta.get("classoption") or meta.get("classoptions", "")
    beforestart = meta.get("beforestart", "")
    preamble = meta.get("preamble", "")
    title = meta.get("title", "")
    author = _build_author(meta.get("author", ""))
    # date 는 세 갈래다 — 키가 없으면 아무것도 내보내지 않고(LaTeX 클래스의
    # 기본 \date 에 맡긴다), 키는 있는데 값이 비었으면(`date:` 또는
    # `date: ""`) 날짜를 일부러 지우는 뜻이니 \date{} 를 내보낸다.
    has_date = "date" in meta
    date = meta.get("date")

    opt = f"[{classoptions}]" if classoptions else ""
    # 생성된 .tex 맨 앞에 출처를 밝히는 주석 한 줄. 날짜·원본 경로는 일부러
    # 넣지 않는다 — 같은 입력이 항상 같은 출력을 내야 diff·버전 관리가 조용하다.
    # \DocumentMetadata 처럼 \documentclass 앞에 와야 하는 명령보다도 앞에
    # 오지만 주석이라 영향이 없다. build_document() 와 generate_syncinfo() 가
    # 이 함수를 공유하므로 sync의 줄 번호도 자동으로 맞는다.
    note = f"% converted from ndhmd by ndhmd4tex version {__version__}"
    if pandoc:
        note += " with pandoc syntax"
    elif mmd:
        note += " with multimarkdown syntax"
    header = [note]
    # \documentclass 보다 앞에 와야 하는 것들. \DocumentMetadata 나
    # \PassOptionsToPackage 처럼 클래스 로딩 전에 놓여야 뜻이 있는 명령들이다.
    if beforestart:
        header.append(str(beforestart).rstrip())
    header.append(rf"\documentclass{opt}{{{documentclass}}}")
    # 모르는 키를 넘기는 매크로는 프리앰블보다 먼저 둔다. 프리앰블에서
    # 그 값을 읽어 쓸 수 있어야 하기 때문이다.
    header.extend(metadata_macros(meta, cfg))
    if preamble:
        header.append(str(preamble).rstrip())
    graphicspath = meta.get("graphicspath")
    if graphicspath:
        # 문자열 하나만 줘도, 리스트로 여러 개 줘도 다 받는다 — 이
        # 방언의 다른 자리(mapping:, setup: 등)와 같은 태도다. 경로
        # 문자열 자체는 가공 없이 그대로 {}로 감싼다 — raw= 계열
        # 속성들과 같은 이유로, LaTeX 경로 문법을 이 방언이 대신
        # 판단하려 들지 않는다.
        paths = [graphicspath] if isinstance(graphicspath, str) else list(graphicspath)
        braces = "".join(f"{{{p}}}" for p in paths)
        # graphicx 가 이미 로드돼 있으면(원고 작성자의 preamble이 직접
        # 불렀거나, 다른 패키지가 딸려 불렀거나) 다시 부르지 않는다 —
        # \IfPackageLoadedTF 는 최신 LaTeX2e 커널에 내장된 명령이라
        # 별도 패키지가 필요 없다(실측으로 확인).
        header.append(r"\IfPackageLoadedTF{graphicx}{}{\usepackage{graphicx}}")
        header.append(rf"\graphicspath{{{braces}}}")
    if title:
        header.append(rf"\title{{{title}}}")
    if author:
        header.append(rf"\author{{{author}}}")
    if has_date:
        if date is None or str(date).strip() == "":
            header.append(r"\date{}")
        else:
            header.append(rf"\date{{{date}}}")
    return header


# \tableofcontents* 등 별표 붙은 목차류 명령이 "그 항목 자체를 목차에
# 넣지 않는다"는 뜻으로 실제로 동작하는 것을 실측으로 확인한 클래스만
# 화이트리스트에 올린다(memoir 의 \newlistof 매크로가 이 동작을 제공하고,
# oblivoir 는 memoir 를 상속한다). 표준 article/report/book 클래스에는
# 이런 별표 버전이 아예 없어서, \tableofcontents* 를 그대로 내보내면
# "*" 가 진짜 명령으로 소비되지 않고 그 자리에 문자 그대로 찍히는 것을
# 실측으로 확인했다(컴파일 자체는 성공하지만 목차 페이지에 엉뚱한 별표
# 글자가 남는다). 이 목록 밖의 클래스에서 asterisk: true 를 쓰면 경고만
# 찍고(강제로 막지는 않는다 — 사용자가 직접 별표 버전을 정의해 둔
# 커스텀 클래스일 수도 있으므로) 그대로 진행한다.
_TOCLOFT_ASTERISK_SAFE_CLASSES = {"memoir", "oblivoir"}


def _build_frontmatter_commands(meta, warn=True):
    """\\begin{document} 바로 다음, 본문 앞에 들어갈 명령 줄들을 만든다.

    build_document()와 generate_syncinfo()가 공유한다 — sync 쪽은 본문이
    최종 .tex 파일에서 몇 번째 줄부터 시작하는지 정확히 알아야 하는데,
    이 명령들이 차지하는 줄 수도 그 계산에 들어가야 하기 때문이다.

    warn=False 로 부르면 asterisk 관련 경고를 찍지 않는다 —
    generate_syncinfo()가 오프셋 계산을 위해 이 함수를 먼저 부르고
    build_document()가 실제 조립을 위해 다시 부르는 구조라, 그대로 두면
    경고가 두 번 찍힌다. 호출 경로 중 정확히 한 곳(build_document())만
    warn=True 로 불러 한 번만 뜨게 한다.
    """
    lines = []
    if meta.get("maketitle"):
        lines.append(r"\maketitle")

    tocloft = meta.get("tocloft")
    if isinstance(tocloft, dict):
        star = "*" if tocloft.get("asterisk") else ""
        if star and warn:
            documentclass = str(meta.get("class", "book"))
            if documentclass not in _TOCLOFT_ASTERISK_SAFE_CLASSES:
                print(
                    f"경고: tocloft: asterisk: true 는 memoir 계열 클래스"
                    f"(memoir, oblivoir)에서만 \"그 항목 자체를 목차에 넣지"
                    f" 않는다\"는 뜻으로 실제 동작합니다. 지금 class는"
                    f" '{documentclass}'라, \\tableofcontents{star} 등 뒤의"
                    f" '*' 가 명령으로 소비되지 않고 목차 페이지에 그대로"
                    f" 글자로 찍힐 수 있습니다.",
                    file=sys.stderr,
                )
        if tocloft.get("toc"):
            lines.append(r"\tableofcontents" + star)
        if tocloft.get("lof"):
            lines.append(r"\listoffigures" + star)
        if tocloft.get("lot"):
            lines.append(r"\listoftables" + star)

    return lines


def build_document(body_tex, meta, cfg=None, pandoc=False, mmd=False):
    """front matter로 프리앰블을 만들고 본문 LaTeX을 감싸 완성 문서를 만든다.

    convert()와 convert_pandoc()이 공유한다. 본문을 누가 만들었든 문서의
    겉모양(클래스, 프리앰블, 제목/저자/날짜)은 똑같이 front matter가 정한다는
    것이 --pandoc 모드의 핵심이라, 이 부분만 따로 떼어 두었다.
    """
    header = _build_header_lines(meta, cfg, pandoc=pandoc, mmd=mmd)
    tex = "\n".join(header) + "\n\n"
    tex += "\\begin{document}\n\n"
    fm_commands = _build_frontmatter_commands(meta, warn=True)
    if fm_commands:
        tex += "\n".join(fm_commands) + "\n\n"
    tex += body_tex.strip() + "\n\n"
    tex += "\\end{document}\n"
    return tex


class PandocError(Exception):
    pass


# --pandoc 에 넘겨도 무시할 옵션들. 값을 "옵션 뒤에 따로 오는 인자의 개수"로
# 적어 두었다(--opt=값 형태는 개수와 무관하게 한 토큰이다).
#
# 두 부류다.
#   (a) 프리앰블/문서클래스를 건드리는 것. 이 모드에서 그 둘은 front matter가
#       정한다는 것이 전제이므로, pandoc 쪽 지정은 조용히 버린다.
#   (b) "조각을 내놓는다"는 전제 자체를 깨뜨리는 것. -s 는 물론이고
#       --template, -H/-B/-A 도 **암묵적으로 standalone을 켠다**. 그대로 두면
#       pandoc이 제 \documentclass 를 붙인 완성 문서를 내놓고, 그것이 다시
#       우리 문서 안에 박혀 \documentclass 가 중첩된다.
#   그 밖에 -o(파일로 새어나감)와 -t/-w(출력 형식이 LaTeX이 아니게 됨)도 막는다.
#
# 반대로 --toc, -N, -V, --listings, --metadata, --top-level-division,
# --wrap, -f 는 조각 모드에서 정상 동작하므로 그대로 통과시킨다.
_PANDOC_DENIED_OPTS = {
    "-s": 0, "--standalone": 0,
    "--template": 1,
    "-H": 1, "--include-in-header": 1,
    "-B": 1, "--include-before-body": 1,
    "-A": 1, "--include-after-body": 1,
    "-o": 1, "--output": 1,
    "-t": 1, "--to": 1, "-w": 1, "--write": 1,
    "--pdf-engine": 1,
    "--self-contained": 0, "--embed-resources": 0,
}


def filter_pandoc_args(argv):
    """pandoc 인자 목록에서 무시할 옵션을 걷어낸다.

    걷어낸 것은 경고로 알려준다 — 조용히 사라지면 "왜 안 먹지"로 헤매게 된다.
    """
    out, dropped = [], []
    i, n = 0, len(argv)
    while i < n:
        tok = argv[i]
        name, has_eq = (tok.split("=", 1)[0], True) if "=" in tok else (tok, False)
        if name in _PANDOC_DENIED_OPTS:
            skip = 0 if has_eq else _PANDOC_DENIED_OPTS[name]
            dropped.append(" ".join(argv[i:i + 1 + skip]))
            i += 1 + skip
            continue
        out.append(tok)
        i += 1
    if dropped:
        print(
            "경고: --pandoc 에 준 다음 옵션은 무시합니다 — "
            + ", ".join(dropped)
            + ". 이 모드에서 프리앰블과 \\documentclass 는 front matter가 정하며, "
              "pandoc은 본문 조각만 내놓아야 합니다.",
            file=sys.stderr,
        )
    return out


# pandoc의 --top-level-division 이 받는 값. front matter의 toplevel 과
# 이름이 겹치는 것만 넘긴다(subsection 이하는 pandoc에 대응물이 없다).
_PANDOC_TOPLEVEL = {"part", "chapter", "section"}


def convert_pandoc(source_text, include_base=None, meta=None, extra_args=None, cfg=None, body_only=False):
    r"""본문 변환만 pandoc에 맡기고, 나머지는 이 스크립트가 그대로 담당한다.

    처리 순서가 중요하다.
      1. front matter를 떼어내 보관한다. pandoc에는 본문만 넘긴다 —
         넘겨봐야 pandoc이 제 나름의 메타데이터로 해석해 엉뚱한 것을
         만들고, 우리 preamble/setup 체계와 충돌한다.
      2. {{파일}} 트랜스클루전을 **먼저** 해석한다. pandoc이 모르는 문법이라
         우리가 병합해 통짜 본문으로 만들어 줘야 한다. 결과적으로
         "트랜스클루전이 되는 pandoc"이 된다.
      3. 본문을 pandoc에 표준입력으로 넘겨 LaTeX 조각을 받는다.
         --standalone 을 쓰지 않으므로 \documentclass 나 \begin{document}는
         나오지 않는다. 그 껍데기는 4단계가 만든다.
      4. 보관해둔 front matter로 프리앰블을 만들어 감싼다.

    body_only=True(--default NONE)면 4단계를 건너뛰고 pandoc이 만든
    본문 LaTeX 그대로를 돌려준다 — front matter를 읽지 않았으니 애초에
    감쌀 재료(class, preamble 등)가 없다. meta 는 그래도 toplevel 판정
    등에 pandoc 명령 조립 단계에서 참조되므로, 호출부가 넘겨준 빈
    딕셔너리를 그대로 쓴다(문서 front matter는 안 읽었다는 뜻).
    """
    base_dir = Path(include_base) if include_base is not None else Path(".")
    raw_meta, body = split_frontmatter(source_text)
    if meta is None:
        meta = resolve_setup(raw_meta, base_dir, None, 0)

    body = resolve_includes(body, base_dir)

    cmd = ["pandoc", "-f", "markdown", "-t", "latex", "--wrap=preserve"]

    # front matter의 toplevel을 pandoc에도 알려준다. 이게 없으면 book
    # 클래스에서도 `# 제목`이 \section으로 나가버린다.
    toplevel = meta.get("toplevel")
    if toplevel in _PANDOC_TOPLEVEL:
        cmd.append(f"--top-level-division={toplevel}")

    # 이미지 등 상대 경로가 입력 파일 기준으로 풀리도록.
    cmd.extend(["--resource-path", str(base_dir)])

    user_args = []
    for src in (meta.get("pandocoption", ""), extra_args or ""):
        if src:
            user_args.extend(shlex.split(str(src)))
    cmd.extend(filter_pandoc_args(user_args))

    # encoding을 반드시 명시한다. text=True 만 주면 파이썬이 로케일 기본
    # 인코딩(한국어 윈도우에서는 cp949)으로 파이프에 쓰기 때문에, 본문에
    # cp949에 없는 글자가 하나라도 있으면 UnicodeEncodeError로 죽는다.
    # 한자·이체자·특수기호가 섞인 원고에서 흔히 터진다. pandoc은 입출력을
    # UTF-8로 다루므로 이쪽을 맞추는 것이 옳다.
    try:
        proc = subprocess.run(cmd, input=body, capture_output=True,
                              encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise PandocError(
            "pandoc을 찾을 수 없습니다. --pandoc 옵션에는 pandoc이 PATH에 있어야 합니다."
        )
    if proc.returncode != 0:
        raise PandocError(f"pandoc 실행 실패 (종료 코드 {proc.returncode}):\n{proc.stderr.strip()}")
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    if body_only:
        return proc.stdout
    return build_document(proc.stdout, meta, cfg, pandoc=True)


# --------------------------------------------------------------------------
# --mmd : 본문 변환을 MultiMarkdown(mmd)에 맡기기
# --------------------------------------------------------------------------
#
# --pandoc 과 같은 틀이다. front matter(--- YAML)는 우리가 읽고, mmd에는 본문만
# 넘긴다. 다른 점은 헤딩 단계를 정하는 방식이다. pandoc 은 명령줄 옵션
# (--top-level-division)이 있지만 mmd 는 문서 맨 앞 "메타데이터 블록"의
# `Base Header Level: N` 으로만 정한다.
#
# mmd 의 메타데이터 블록은 --- 로 감싸지 않는다. 문서 첫 줄이 `키: 값` 꼴이면
# 그 줄부터 첫 빈 줄까지가 블록이다. 그래서 (1) 본문에 이미 블록이 있으면 그
# 안에서 값을 고치거나 한 줄 보태야 하고(새 블록을 앞에 얹으면 기존 블록이
# 문단이 된다), (2) 우리가 YAML front matter 를 뗀 뒤 남은 본문의 맨 앞이
# mmd 에게는 메타데이터로 보일 수 있다. 후자 때문에 mmd 의 Title/Author/Date 는
# 읽어 오지 않는다 — 어느 쪽 것인지 우리가 가릴 수 없다.

class MmdError(PandocError):
    pass


# mmd 에 넘겨도 무시할 옵션(기억에 의존한 목록 — 실제 mmd 로 확인 필요).
#   -t/--to, -o/--output : 출력 형식·파일을 우리가 정한다.
#   -f/--full, -s/--snippet : 조각 모드를 우리가 강제한다.
#   -b/--batch, -e/--extract : 파일로 새거나 본문 대신 메타데이터만 내놓는다.
_MMD_DENIED_OPTS = {
    "-t": 1, "--to": 1, "-o": 1, "--output": 1,
    "-f": 0, "--full": 0, "-s": 0, "--snippet": 0,
    "-b": 0, "--batch": 0, "-e": 1, "--extract": 1,
}

_MMD_HEADING_CMDS = ("part", "chapter", "section", "subsection",
                     "subsubsection", "paragraph", "subparagraph")
# 탐침이 실패했을 때만 쓰는 비상 표. 레벨 N 의 `#` 이 어떤 명령이 되는가.
_MMD_FALLBACK_SEQ = {i + 1: c for i, c in enumerate(_MMD_HEADING_CMDS)}
_MMD_META_FIRST_RE = re.compile(r"^[A-Za-z0-9][^:\n]*:")
_MMD_BHL_RE = re.compile(r"^(base[ _-]*header[ _-]*level)[ \t]*:[ \t]*(.*)$", re.I)
_MMD_TOC_MARK = "\uE0F0MMDTOC\uE0F1"
_mmd_probe_cache = {}


def filter_mmd_args(argv):
    out, dropped = [], []
    i, n = 0, len(argv)
    while i < n:
        tok = argv[i]
        name, has_eq = (tok.split("=", 1)[0], True) if "=" in tok else (tok, False)
        if name in _MMD_DENIED_OPTS:
            skip = 0 if has_eq else _MMD_DENIED_OPTS[name]
            dropped.append(" ".join(argv[i:i + 1 + skip]))
            i += 1 + skip
            continue
        out.append(tok)
        i += 1
    if dropped:
        print("경고: --mmd 에 준 다음 옵션은 무시합니다 — " + ", ".join(dropped)
              + ". 이 모드에서 출력 형식은 LaTeX 조각으로 고정이며 문서 틀은 "
                "front matter 가 정합니다.", file=sys.stderr)
    return out


def _find_mmd():
    return shutil.which("multimarkdown") or shutil.which("mmd")


def _mmd_run(exe, args, text, cwd):
    try:
        return subprocess.run([exe] + args, input=text, capture_output=True,
                              encoding="utf-8", errors="replace",
                              cwd=str(cwd) if cwd else None)
    except FileNotFoundError:
        raise MmdError("multimarkdown 을 실행하지 못했습니다.")


def _mmd_snippet_run(exe, args, text, cwd):
    """--snippet 으로 먼저 돌려 보고, 그 옵션을 모르는 mmd 면 빼고 다시 돌린다."""
    proc = _mmd_run(exe, ["-t", "latex", "--snippet"] + args, text, cwd)
    if proc.returncode != 0 and re.search(r"snippet|unrecognized|unknown|usage",
                                          proc.stderr or "", re.I):
        proc = _mmd_run(exe, ["-t", "latex"] + args, text, cwd)
    return proc


def _mmd_probe(exe, cwd):
    """Base Header Level: 1 일 때 `#`~`######` 이 각각 어떤 LaTeX 명령이 되는지
    mmd 에게 직접 물어 {레벨: 명령} 을 돌려준다. 실패하면 None.

    mmd 버전마다 `#` 이 \\part 인지 \\chapter 인지가 다를 수 있어서, 고정 표를
    믿지 않고 실제 설치본에 확인한다. 한 번 돌리면 캐시한다."""
    if exe in _mmd_probe_cache:
        return _mmd_probe_cache[exe]
    text = "Base Header Level: 1\n\n" + "\n\n".join(
        f"{'#' * k} ndhmdprobe{k}" for k in range(1, 7)) + "\n"
    seq = None
    try:
        proc = _mmd_snippet_run(exe, [], text, cwd)
        if proc.returncode == 0:
            found = {}
            for m in re.finditer(r"\\(\w+)\*?(?:\[[^\]]*\])?\{ndhmdprobe(\d)\}", proc.stdout):
                if m.group(1) in _MMD_HEADING_CMDS:
                    found[int(m.group(2))] = m.group(1)
            if len(found) == 6:
                seq = found
    except MmdError:
        pass
    _mmd_probe_cache[exe] = seq
    return seq


def _mmd_level_for(seq, toplevel):
    """`#` 이 toplevel 명령이 되게 하는 Base Header Level. 없으면 None."""
    for k in sorted(seq):
        if seq[k] == toplevel:
            return k
    return None


def _mmd_meta_span(lines):
    """본문 맨 앞 mmd 메타데이터 블록의 (첫 줄, 끝 줄) — 끝 줄은 블록에 속하지
    않는 첫 줄이다. 블록이 없으면 None.

    mmd 는 두 꼴을 다 받는다: 첫 줄이 `키: 값` 이면 첫 빈 줄까지, 첫 줄이
    `---` 이면 다음 `---`(또는 `...`)까지. 후자는 우리 YAML front matter 가
    깨져서(예: 콜론 뒤 탭) 본문으로 흘러들어온 경우에도 나타난다."""
    if not lines:
        return None
    if lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                return 1, i
        return None
    if not _MMD_META_FIRST_RE.match(lines[0]):
        return None
    for i, ln in enumerate(lines):
        if not ln.strip():
            return 0, i
    return 0, len(lines)


def _mmd_apply_base_level(body, meta, exe, cwd):
    """toplevel(없으면 baseheaderlevel)을 mmd 의 Base Header Level 로 옮긴다.

    우선순위: front matter 의 toplevel > front matter 의 baseheaderlevel >
    본문 메타데이터 블록에 이미 있는 값(손대지 않음) > mmd 기본값."""
    lines = body.split("\n")
    span = _mmd_meta_span(lines)
    end = span[1] if span else None
    bhl_idx, bhl_val = None, None
    if span is not None:
        for i in range(span[0], end):
            m = _MMD_BHL_RE.match(lines[i])
            if m:
                bhl_idx = i
                try:
                    bhl_val = int(m.group(2).strip())
                except ValueError:
                    bhl_val = None
                break

    want = None
    top = meta.get("toplevel")
    if top:
        if top not in _PANDOC_TOPLEVEL:
            print(f"경고: --mmd 에서는 toplevel: {top} 을(를) 쓸 수 없습니다 "
                  f"(part / chapter / section). 무시합니다.", file=sys.stderr)
        else:
            seq = _mmd_probe(exe, cwd)
            if seq is None:
                print("경고: mmd 의 헤딩 대응을 알아내지 못해 기본 표(part=1, "
                      "chapter=2, section=3)를 씁니다.", file=sys.stderr)
                seq = _MMD_FALLBACK_SEQ
            want = _mmd_level_for(seq, top)
            if want is None:
                print(f"경고: 이 mmd 에서는 `#` 을 \\{top} 으로 만들 수 없어 "
                      f"toplevel: {top} 을(를) 적용하지 못했습니다.", file=sys.stderr)
    if want is None and not top:
        for k, v in meta.items():
            if re.sub(r"[\s_-]", "", str(k).lower()) == "baseheaderlevel":
                try:
                    want = int(v)
                except (TypeError, ValueError):
                    print(f"경고: baseheaderlevel: {v!r} 은(는) 정수가 아닙니다. "
                          f"무시합니다.", file=sys.stderr)
                break
    if want is None:
        return body
    if bhl_val == want:
        return body
    if bhl_idx is not None:
        if top:
            print(f"경고: 본문의 Base Header Level 이 {bhl_val!r} 이지만 front matter 의 "
                  f"toplevel 을 따라 {want} 로 바꿉니다.", file=sys.stderr)
        lines[bhl_idx] = f"Base Header Level: {want}"
    elif end is not None:
        lines.insert(end, f"Base Header Level: {want}")
    else:
        lines = [f"Base Header Level: {want}", ""] + lines
    return "\n".join(lines)


def convert_mmd(source_text, include_base=None, meta=None, extra_args=None, cfg=None, body_only=False):
    """본문 변환만 MultiMarkdown 에 맡기고 나머지는 이 스크립트가 담당한다.
    순서는 convert_pandoc 과 같다(front matter 보관 → 트랜스클루전 → 외주 → 감싸기).
    """
    base_dir = Path(include_base) if include_base is not None else Path(".")
    raw_meta, body = split_frontmatter(source_text)
    if meta is None:
        meta = resolve_setup(raw_meta, base_dir, None, 0)

    exe = _find_mmd()
    if not exe:
        raise MmdError("multimarkdown 을 찾을 수 없습니다. --mmd 옵션에는 "
                       "multimarkdown(또는 mmd)이 PATH 에 있어야 합니다.")

    # mmd 의 {{TOC}} 는 파일이 아니라 목차 지시자다. 우리 트랜스클루전이
    # 파일로 오해하지 않게 잠시 가려 둔다.
    body = body.replace("{{TOC}}", _MMD_TOC_MARK)
    body = resolve_includes(body, base_dir)
    body = body.replace(_MMD_TOC_MARK, "{{TOC}}")

    cwd = base_dir if base_dir.is_dir() else None
    body = _mmd_apply_base_level(body, meta, exe, cwd)

    user_args = []
    for src in (meta.get("mmdoption", ""), extra_args or ""):
        if src:
            user_args.extend(shlex.split(str(src)))
    proc = _mmd_snippet_run(exe, filter_mmd_args(user_args), body, cwd)
    if proc.returncode != 0:
        raise MmdError(f"multimarkdown 실행 실패 (종료 코드 {proc.returncode}):\n{proc.stderr.strip()}")
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)

    out = proc.stdout
    # 완성 문서 판정은 "첫 의미 있는 줄"로만 한다. 본문에 \begin{document} 가
    # verbatim 예제로 들어 있는 글(LaTeX 설명서 등)을 완성 문서로 오인해
    # 앞뒤를 잘라내는 일이 실제로 있었다.
    first = next((ln for ln in out.split("\n")
                  if ln.strip() and not ln.lstrip().startswith("%")), "")
    if re.match(r"\\(documentclass|input)\b", first):
        m = re.search(r"^\\begin\{document\}[ \t]*\n(.*)^\\end\{document\}[ \t]*$",
                      out, re.S | re.M)
        if m:
            print("경고: mmd 가 완성 문서를 내놓아 \\begin{document} 안쪽만 취했습니다. "
                  "메타데이터(latex input 등)가 원인일 수 있습니다.", file=sys.stderr)
            out = m.group(1)
    if body_only:
        return out
    return build_document(out, meta, cfg, mmd=True)


def convert(source_text, cfg, include_base=None, meta=None, body_only=False, source_path=None):
    cfg = dict(cfg)

    # {{filename}} 포함 지시자 해석 — 재귀적으로(20장) 해석되며, 순환
    # 포함은 IncludeError로 잡힌다. include_base는 최상위 입력 파일이
    # 있는 디렉터리 — 경로 없이 파일 이름만 쓴 {{...}}가 이 디렉터리를
    # 기준으로 찾아진다. main()에서 넘겨주지 않으면(예: 다른 코드에서
    # convert()를 직접 호출하는 경우) 현재 작업 디렉터리를 쓴다.
    # source_path는 최상위 입력 파일 자신의 정확한 경로다 — 이걸 알아야
    # "최상위 파일이 자기 자신을 포함하는" 가장 단순한 순환까지 첫
    # 시도에서 바로 잡을 수 있다(resolve_includes()의 self_path 참고).
    base_dir = Path(include_base) if include_base is not None else Path(".")

    raw_meta, body = split_frontmatter(source_text)
    # main()은 이미 setup 체인까지 해석한 meta를 넘겨준다(front matter를 두 번
    # 파싱하지 않기 위함). 다른 코드가 convert()를 직접 부르는 경우를 위해
    # 여기서도 해석할 수 있게 남겨둔다.
    if meta is None:
        meta = resolve_setup(raw_meta, base_dir, None, 0)

    # Protector를 {{포함}} 해석보다 먼저 만든다 — {{tex:파일}}(20.1절, 날
    # LaTeX을 그대로 삽입하는 문법)이 이 안에서 pr.protect()를 바로
    # 호출해 이후의 모든 마크다운 처리를 우회해야 하기 때문이다. Protector
    # 자체는 생성 시점과 무관하게 동일하게 동작하므로(내부 상태가 빈
    # 리스트일 뿐), 이렇게 앞당겨도 그 뒤(protect_block_level 등)의
    # 기존 동작에는 전혀 영향이 없다.
    pr = Protector()

    body = resolve_includes(body, base_dir, pr, self_path=source_path)

    toplevel = meta.get("toplevel")
    if toplevel:
        hierarchy = ["part", "chapter", "section", "subsection", "subsubsection", "paragraph", "subparagraph"]
        if toplevel in hierarchy:
            start_idx = hierarchy.index(toplevel)
            new_headings = {}
            for i in range(6):
                target_idx = min(start_idx + i, len(hierarchy) - 1)
                new_headings[i + 1] = hierarchy[target_idx]
            cfg["headings"] = new_headings

    # showexam 블록은 다른 무엇보다 먼저 뽑아낸다(이유는 3.5절 주석 참고).
    showexam_store = []
    body = extract_showexam(body, showexam_store)
    body = protect_block_level(body, cfg, pr)
    body, footnotes = extract_footnotes(body)
    body, refdefs = extract_reference_defs(body)
    
    cfg["_footnotes"] = footnotes
    cfg["_refdefs"] = refdefs

    lines = body.split("\n")
    body_tex = render_blocks(lines, cfg, pr)
    body_tex = pr.restore(body_tex)
    # 이제 각주까지 준비됐으니 showexam의 오른쪽 상자를 채운다.
    body_tex = expand_showexam(body_tex, showexam_store, cfg)

    if body_only:
        return body_tex
    return build_document(body_tex, meta, cfg)


class SyncInfoUnavailable(Exception):
    """--syncinfo 를 만들 수 없는 상황(예: {{포함}} 사용)일 때만 든다."""
    pass


def generate_syncinfo(source_text, cfg, include_base=None, meta=None, source_path=None):
    """--syncinfo 전용: 최종 .tex 의 각 블록이 원본 .md 의 몇 번째 줄에서
    왔는지 나타내는 (src_파일, src_시작, src_끝, tex_시작, tex_끝) 목록을
    만든다(write_syncinfo_file() 이 기대하는 순서와 맞춰야 한다 — 한 번
    이 순서가 어긋나 파일의 두 짝이 통째로 엇갈렸던 적이 있다).

    convert() 와 완전히 같은 파이프라인을 한 번 더 밟는다(코드 중복이지만,
    변환 로직 자체는 단 한 글자도 바꾸지 않는다는 원칙을 지키기 위해서다 —
    처음에는 "코드펜스 등이 사라진 자리를 빈 줄로 채워 원본 줄 번호를
    유지"하는 방식을 시도했는데, 실제로 리스트 항목 바로 뒤에 빈 줄 없이
    여러 줄짜리 코드펜스가 오는 경우 그렇게 채워진 빈 줄 때문에 리스트가
    쪼개지는 회귀가 생기는 것을 실측으로 확인했다. 그래서 변환은 원래
    함수들을 그대로 쓰고, 각 함수가 "몇 줄이 몇 줄로 줄었는지"만 옆에서
    기록하게 해서, 그 기록으로 원본 줄 번호를 사후에 역산하는 방식을
    택했다).

    render_blocks() 자체는 건드리지 않는다 — split_blocks()로 나눈 블록을
    하나씩 다시 render_blocks() 에 넣어도 통째로 넣은 것과 결과가 완전히
    같다는 것을 실측으로 확인했으므로(자리표시자의 Protector 인스턴스
    번호를 빼면 바이트 단위로 동일), 블록 단위로 나눠 호출하는 것만으로
    "이 블록이 출력에서 몇 줄을 차지하는지"를 안전하게 알아낼 수 있다.

    {{포함}} 은 resolve_includes_tracked() 로 처리한다 — 이제 재귀적으로
    (몇 단계든) 해석되는데도, "그 줄이 어느 파일의 몇 번째 줄에서
    왔는지"를 원본 파일 하나짜리일 때와 똑같은 방식(LineOriginMap)으로
    추적할 수 있다 — 다만 담기는 값이 정수 하나가 아니라 (파일경로,
    줄번호) 튜플이 된다는 차이뿐이다. apply_shrink()/resolve() 는
    애초에 값의 내용을 들여다보지 않으므로 이 일반화에 코드 변경이
    필요 없었다. 재귀 쪽의 origin 합성(각 단계마다 자기 파일 몫만
    보정하고 더 깊이 포함된 파일을 가리키는 항목은 그대로 두는 것)은
    _resolve_single_include() 가 맡는다.
    """
    cfg = dict(cfg)
    # .resolve() 가 반드시 필요하다 — 이게 없으면(실측으로 발견한 버그),
    # main.md 를 상대경로로("main.md") 실행했을 때(가장 흔한 실사용 방식,
    # 즉 프로젝트 폴더로 cd한 뒤 파일 이름만 치는 경우) base_dir 도 상대
    # 경로("." 등)가 되고, 그 아래 resolve_includes_tracked() 가
    # {{sub/chap1.md}} 를 찾아 만드는 서브파일 경로("sub/chap1.md")도
    # 절대경로로 정규화되지 않은 채 그대로 .nmdsync 의 source_file 컬럼에
    # 박힌다. 최상위 파일(top_path)은 바로 아래 줄에서 이미 resolve() 하고
    # 있었으니, 서브파일 쪽만 이 처리가 빠져 있었던 비대칭이 원인이었다.
    # 이 버그는 실제 컴파일 결과(.tex)에는 영향이 없다 — 상대경로도 실제
    # 파일은 정상적으로 열리기 때문이다(convert()/convert_pandoc() 는
    # 이 문제와 무관하다). 오직 --syncinfo 가 "표시·조회용"으로 저장하는
    # 절대경로 문자열만 잘못됐던 것이라, ndhmdsync.py 가 나중에 이 상대
    # 경로를 자기 자신의(실행 시점의) 작업 폴더 기준으로 다시 resolve()
    # 하면서 엉뚱한 절대경로로 둔갑해 "파일을 못 찾는다"는 오류로
    # 이어졌다(사용자가 서브파일이 있는 폴더 안에서 ndhmdsync 를 실행한
    # 경우, 예를 들어 sub/chap1.md 라는 문자열이 sub/ 안에서 다시
    # resolve() 되어 sub/sub/chap1.md 로 겹쳐 보이는 식이었다).
    base_dir = (Path(include_base) if include_base is not None else Path(".")).resolve()
    top_path = Path(source_path).resolve() if source_path is not None else Path("<입력>")

    raw_meta, body = split_frontmatter(source_text)
    if meta is None:
        meta = resolve_setup(raw_meta, base_dir, None, 0)

    # front matter가 원본 파일에서 몇 줄을 차지했는지 — 이후 계산하는 모든
    # 줄 번호는 "front matter를 뗀 본문(body)" 기준이므로, 최상위 파일
    # 자신을 가리키는 항목을 "원본 .md 파일 전체 기준 줄 번호"로 바꾸려면
    # 이 오프셋을 반드시 더해야 한다(포함된 서브파일은 이미
    # resolve_includes_tracked() 단계에서 자기 자신의 front matter 오프셋을
    # 반영해 절대 위치로 넣어 두므로 이 오프셋과 무관하다). 이 오프셋은
    # 아래 _abs_line() 안에서 딱 한 번만 적용한다 — 예전에 이걸 두 번
    # 적용해(한 번은 여기, 한 번은 최종 조립 단계) 첫 블록이 원본보다
    # fm_line_offset만큼 두 배 밀려 나오는 버그가 있었다(실측으로 발견).
    fm_char_len = len(source_text) - len(body)
    fm_line_offset = source_text[:fm_char_len].count("\n")

    # Protector를 resolve_includes_tracked() 보다 먼저 만든다 — convert()와
    # 같은 이유다: {{tex:파일}}이 그 안에서 pr.protect()를 바로 호출해야
    # 하기 때문이다. 이 함수 하나만 뒤에서 다시 Protector()를 만들지
    # 않도록 아래의 중복 생성도 제거했다.
    pr = Protector()

    body, file_origin = resolve_includes_tracked(body, base_dir, top_path, pr)

    toplevel = meta.get("toplevel")
    if toplevel:
        hierarchy = ["part", "chapter", "section", "subsection", "subsubsection", "paragraph", "subparagraph"]
        if toplevel in hierarchy:
            start_idx = hierarchy.index(toplevel)
            new_headings = {}
            for i in range(6):
                target_idx = min(start_idx + i, len(hierarchy) - 1)
                new_headings[i + 1] = hierarchy[target_idx]
            cfg["headings"] = new_headings

    origin = LineOriginMap(file_origin)

    showexam_store = []
    se_events = []
    body = extract_showexam(body, showexam_store, se_events)
    origin.apply_shrink(se_events)

    block_events = {}
    body = protect_block_level(body, cfg, pr, block_events)
    # protect_block_level() 안에서 실제로 실행되는 순서와 반드시 같아야
    # 누적 결과가 맞는다(코드펜스 -> 주석 -> 라인코멘트 -> 수식환경 ->
    # 표환경 -> 디스플레이수식).
    for key in ("fence", "comment", "linecomment", "mathenv", "tableenv", "dispmath"):
        origin.apply_shrink(block_events.get(key, []))

    fn_events = []
    body, footnotes = extract_footnotes(body, fn_events)
    origin.apply_shrink(fn_events)

    refdef_events = []
    body, refdefs = extract_reference_defs(body, refdef_events)
    origin.apply_shrink(refdef_events)

    cfg["_footnotes"] = footnotes
    cfg["_refdefs"] = refdefs

    lines = body.split("\n")
    blocks = split_blocks_indexed(lines)

    def _abs_line(origin_val):
        """origin.resolve() 가 돌려준 (파일, 0-based 줄) 을 (파일, 1-based
        줄) 로 바꾼다. 최상위 파일이면 front matter 오프셋을 더하고,
        포함된 서브파일이면 resolve_includes_tracked() 가 이미 절대
        위치까지 다 계산해 뒀으므로 그대로 1만 더한다."""
        file_val, local_line = origin_val
        if file_val == top_path:
            return file_val, local_line + fm_line_offset + 1
        return file_val, local_line + 1

    # 이 시점의 origin 은 "지금 lines 의 각 줄" -> "(파일, 그 파일에서의
    # 0-based 줄)" 을 담고 있다. 각 블록을 개별적으로 다시 render_blocks()
    # 에 넣어, 그 결과가 몇 줄을 차지하는지 세면서 블록 사이 구분자를
    # 반영해 누적 출력 줄 번호를 계산한다. 구분자는 각 블록의
    # had_blank_after(split_blocks_indexed가 매긴 것)를 따른다 —
    # render_blocks()(--syncinfo 없을 때 쓰이는 일반 경로)와 정확히
    # 같은 규칙(원문에 실제 빈 줄이 있었으면 "\n\n", 없었으면 "\n")이어야
    # 두 경로의 .tex 출력이 어긋나지 않는다. 예전에는 여기서 항상
    # "\n\n"으로 고정해 놨었는데, 그러면 :::{환경}/Beamer 프레임 뒤에
    # 빈 줄 없이 텍스트가 이어지는 원고에서 --syncinfo를 켜고 끄는 것만
    # 으로 실제 조판 결과(문단 구분 여부)가 달라지는 버그가 있었다.
    sync_entries = []  # (src_file, src_start, src_end, out_start, out_end), 줄번호는 1-based
    out_line = 1  # 본문(전처리 후 텍스트) 기준, 아직 프리앰블 오프셋 전
    rendered_pieces = []
    for i, (blk, start_idx, end_idx, had_blank_after) in enumerate(blocks):
        piece = render_blocks(blk, cfg, pr)
        # showexam 자리표시자(_SE_OPEN...)는 Protector 자리표시자와 다른
        # 문자 체계라 render_blocks() 안의 "블록 전체가 자리표시자 하나면
        # 즉시 복원한다"는 특례에 걸리지 않는다 — 그래서 여기서 직접, 이
        # 조각 하나에 대해 pr.restore() 다음 expand_showexam() 을 미리
        # 적용해 "최종 모양"으로 만든 뒤에야 줄 수를 센다. 이 순서(먼저
        # restore, 그다음 expand)는 원래 convert() 가 문서 전체에 대해
        # 적용하는 순서와 같다 — 처음 구현에서 이걸 생략하고 아직 자리
        # 표시자만 있는 짧은 상태의 줄 수를 세는 바람에, showexam이 있는
        # 문서에서 그 블록 이후 모든 sync 항목의 tex 줄 번호가 실제보다
        # 훨씬 작게 나오는 버그가 있었다(실측으로 발견).
        piece = pr.restore(piece)
        piece = expand_showexam(piece, showexam_store, cfg)
        if i < len(blocks) - 1 and had_blank_after in _JOINS:
            piece += _join_suffix(blk, blocks[i + 1][0], cfg, had_blank_after)
        rendered_pieces.append(piece)
        piece_len = piece.count("\n") + 1 if piece != "" else 0
        if piece_len > 0:
            # 한 블록이 {{포함}} 경계를 넘나드는(빈 줄 없이 서브파일
            # 내용과 메인 파일 내용이 같은 블록으로 묶이는) 흔치 않은
            # 경우는 "블록이 시작하는 지점"의 파일을 대표로 삼는다.
            src_file, src_start = _abs_line(origin.resolve(start_idx))
            _, src_end = _abs_line(origin.resolve(end_idx - 1))
            sync_entries.append((src_file, src_start, src_end, out_line, out_line + piece_len - 1))
            out_line += piece_len
        if i < len(blocks) - 1:
            # render_blocks()의 구분자 규칙과 정확히 일치시킨다: 원문에
            # 실제 빈 줄이 있었으면 "\n\n"(줄 하나 더 차지), 없었으면
            # "\n"(추가로 차지하는 줄 없음).
            out_line += 1 if had_blank_after is True else 0

    separators = ["\n\n" if blocks[i][3] is True else "\n" for i in range(len(rendered_pieces) - 1)]
    body_tex = "".join(
        piece + (separators[i] if i < len(separators) else "")
        for i, piece in enumerate(rendered_pieces)
    )
    # 위에서 조각마다 이미 restore + expand 를 마쳤으므로 이 시점에는
    # 자리표시자가 남아 있지 않아야 정상이다. 그래도 블록 경계를 넘나드는
    # 극단적인 경우를 대비한 안전망으로 한 번 더 통과시킨다 — 이미 없으면
    # 아무 일도 하지 않으므로 무해하다.
    body_tex = pr.restore(body_tex)
    body_tex = expand_showexam(body_tex, showexam_store, cfg)

    # build_document() 와 완전히 같은 방식으로 헤더 줄 수를 계산해, 본문이
    # 최종 .tex 파일에서 몇 번째 줄부터 시작하는지 구한다.
    header = _build_header_lines(meta, cfg)
    header_text = "\n".join(header)
    header_lines = header_text.count("\n") + 1 if header_text else 0
    # build_document()의 조립: header_text + "\n\n" + "\begin{document}\n\n"
    # + (\maketitle 등, 있다면) + "\n\n" + body...
    # warn=False — 여기는 오프셋을 계산만 할 뿐이고, 실제 .tex 조립은 뒤의
    # build_document() 가 다시 담당한다. 그쪽에서 warn=True 로 부르므로
    # 경고는 거기서 한 번만 뜬다(여기서도 warn=True 로 두면 같은 경고가
    # 두 번 찍힌다).
    fm_commands = _build_frontmatter_commands(meta, warn=False)
    fm_command_lines = (len(fm_commands) + 1) if fm_commands else 0
    preamble_offset = header_lines + 1 + 1 + 1 + fm_command_lines  # 헤더 뒤 빈줄, \begin{document}, 그 뒤 빈줄

    final_entries = [
        (src_file, src_s, src_e, out_s + preamble_offset, out_e + preamble_offset)
        for (src_file, src_s, src_e, out_s, out_e) in sync_entries
    ]

    tex = build_document(body_tex, meta, cfg)
    return tex, final_entries


def write_syncinfo_file(path, entries):
    """.nmdsync 파일을 쓴다. 사람이 읽을 수 있는 단순한 탭 구분 텍스트다.

    한 줄에 하나씩: tex_시작 tex_끝 소스파일 소스_시작 소스_끝 (전부 1-based,
    양 끝 포함하는 닫힌 구간). ndhmdsync.py 가 이 파일을 읽어 tex 줄
    번호로 소스 위치를 찾는다. 소스 파일이 행마다 달라질 수 있다
    ({{포함}} 이 있는 문서는 최상위 파일과 포함된 파일이 섞인다) — 그래서
    파일명을 하나의 인자로 통째로 받지 않고, entries 의 각 항목이 자기
    소스 파일을 직접 갖고 있다.

    entries 는 generate_syncinfo() 가 만든 그대로 (src_file, src_start,
    src_end, tex_start, tex_end) 순서로 들어온다 — 파일에 쓸 때는
    tex_start 를 맨 앞에 두므로(찾는 쪽이 tex 줄 번호로 조회하니 그게
    자연스럽다) 순서를 여기서 뒤바꾼다. 처음 구현에서 이 뒤바꾸기를
    깜빡해 파일의 두 짝이 통째로 엇갈렸던 적이 있다(실측으로 발견) —
    컬럼 이름을 헤더 주석에도 남겨 둔 이유이기도 하다.
    """
    lines = [
        "# ndhmd4tex --syncinfo",
        f"# tex_start\ttex_end\tsource_file\tsrc_start\tsrc_end",
    ]
    for src_file, src_s, src_e, tex_s, tex_e in entries:
        lines.append(f"{tex_s}\t{tex_e}\t{src_file}\t{src_s}\t{src_e}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# 7. CLI 및 컴파일/실행
# --------------------------------------------------------------------------

# 사용자가 원하는 PDF 뷰어를 강제로 지정하는 환경변수. RESOURCE_ENV
# (NDHMARKDOWN_RESOURCE_DIRECTORY)와 같은 명명 관례를 따른다. 값은 셸처럼
# 인자를 나눠 받는다 — "okular --unique" 같은 뷰어별 옵션을 쓸 수 있도록.
# 실행 파일을 찾을 수 없거나 뷰어가 오류로 죽으면 플랫폼 기본값으로
# 조용히 물러난다 — 뷰어를 지정하려던 시도 때문에 컴파일 자체가 실패한
# 것처럼 보이면 안 되기 때문이다.
PDF_VIEWER_ENV = "NDHMARKDOWN_PDF_VIEWER"


def _print_elapsed(start_time):
    """총 경과시간을 사람이 읽기 좋은 형태로 보여준다.

    main() 의 성공 지점에서만 부른다 — 실패했거나 --lint 같은 부차
    기능만 쓰고 끝났을 때는 아무 의미가 없어 보여주지 않는다.
    """
    elapsed = time.monotonic() - start_time
    if elapsed < 60:
        print(f"총 경과시간: {elapsed:.1f}초")
    else:
        m, s = divmod(elapsed, 60)
        print(f"총 경과시간: {int(m)}분 {s:.1f}초")


def _has_synctex_option(cmd_parts):
    """cmd(문자열 리스트) 안에 이미 -synctex=N 형태의 옵션이 있는지 확인한다.

    --syncinfo 는 .nmdsync(줄 대응)뿐 아니라 SyncTeX 자체(PDF <-> tex
    페이지/좌표 대응)도 필요하므로, --syncinfo 를 줬으면 컴파일 명령에
    synctex 옵션이 반드시 들어가야 한다(정확한 대시 개수는 컴파일러마다
    달라서 호출부에서 각자 붙인다 — ksruncltex는 --synctex=1(대시 둘),
    latexmk는 -synctex=1(대시 하나)이 정식 문법이다). 다만 원고
    작성자가 compileoption:/latexmkoption: 에 이미 -synctex=... 을
    직접 넣어 뒀을 수도 있는데, 이 경우 뒤에서 또 붙이면 안 된다 —
    실측해 보니 latexmk/xelatex 둘 다 중복된 -synctex= 를 줘도 오류를
    내지 않고 조용히 "나중 값이 이긴다"로 처리하므로(예: `-synctex=1
    -synctex=0` 이면 결국 꺼진다), 여기서 무조건 뒤에 덧붙이면 원고
    작성자가 명시적으로 끈 걸 순서에 따라 조용히 뒤집어버릴 위험이
    있다. "먼저 있으면 손대지 않는다"는 원칙으로 이 위험을 피한다.
    이 함수 자신은 대시 하나짜리(-synctex=)든 둘짜리(--synctex=)든
    똑같이 "이미 있다"고 인정한다 — 어느 쪽 컴파일러의 관례로 이미
    적혀 있든 중복 판정에는 차이가 없어야 하기 때문이다.
    """
    return any(re.match(r"-{1,2}synctex=", part) for part in cmd_parts)


def _run_compiler(cmd, cwd, brief):
    """ksruncltex/latexmk 실행 공통 로직 — --brief 여부에 따라 컴파일러
    자신의 출력을 보여줄지 숨길지만 가른다.

    brief=False(기본)면 지금까지와 완전히 같다: "실행 명령어: ..."를
    보여주고, subprocess에 stdout/stderr를 따로 물리지 않아서 자식
    프로세스의 출력이 OS 파일 디스크립터를 통해 곧장 터미널로 흐른다
    (_PrefixedStream 도, 이 함수도 그 출력을 건드리지 않는다).

    brief=True면 그 출력을 캡처해서 평소엔 아예 보여주지 않는다 —
    성공했으면 "잘 됐다"는 사실 자체가 중요하지, 그 과정의 로그는
    필요 없다는 게 --brief의 취지이기 때문이다. 다만 실패했을 때는
    그 로그가 유일한 단서이므로, 이 경우에 한해 캡처된 출력을 그제서야
    보여준다 — "조용하다"와 "디버깅이 막힌다"는 서로 다른 문제라서,
    실패까지 조용히 넘기지는 않는다.

    "컴파일합니다: <실제로 부른 명령줄>"은 cmd 조립이 다 끝난 이 함수
    안에서 찍는다 — 호출부(main())에서는 engine_flag/compileoption:
    등을 다 반영해 cmd를 완성하기 *전*에 안내 문구를 찍고 있었어서,
    "컴파일합니다"라고만 하고 정작 무엇을 실행하는지는 안 보여주고
    있었다. 실제로 불리는 명령줄 그대로를 여기서 보여줘야 그 말이
    거짓이 되지 않는다.
    """
    if not brief:
        print(f"실행 명령어: {' '.join(cmd)}")
        return subprocess.run(cmd, cwd=cwd)

    print(f"컴파일합니다: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, errors="replace")
    if result.returncode != 0:
        if result.stdout:
            # write_raw(): 이건 이 도구의 메시지가 아니라 컴파일러 자신의
            # 로그를 그대로 옮겨 붙이는 것이므로, verbose 모드에서 그
            # 로그가 애초에 접두어 없이 나오는 것과 형태를 맞춘다 — 실패
            # 시에만 예외적으로 보여주는 로그인데 형태까지 달라지면
            # 오히려 헷갈린다. 명령줄은 위에서 "컴파일합니다: ..."로
            # 이미 보여줬으므로 여기서 또 반복하지 않는다.
            sys.stdout.write_raw(result.stdout)
            if not result.stdout.endswith("\n"):
                print()
    return result


def open_pdf(pdf_path):
    custom = os.environ.get(PDF_VIEWER_ENV)
    if custom:
        try:
            cmd = shlex.split(custom, posix=(sys.platform != "win32"))
            subprocess.Popen(cmd + [str(pdf_path)])
            return
        except (OSError, ValueError) as e:
            print(
                f"경고: {PDF_VIEWER_ENV}='{custom}' 로 PDF를 열지 못해 "
                f"기본 뷰어로 대신 엽니다.\n  {e}",
                file=sys.stderr,
            )
    if sys.platform == "win32":
        os.startfile(pdf_path)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(pdf_path)])
    else:
        subprocess.run(["xdg-open", str(pdf_path)])

class _NdhmdHelpFormatter(argparse.HelpFormatter):
    """`--help` 목록에서 "값을 =로 붙여야 하는 옵션"과 "스페이스로 띄어
    써도 되는 옵션"을 한눈에 구분해 보여준다.

    이 방언에는 두 부류가 섞여 있다.
      - `--default 파일`처럼 값이 필수인 옵션(nargs 기본값)은 스페이스로
        띄우든 `=`로 붙이든 둘 다 된다.
      - `--pandoc[=옵션]`처럼 값이 선택적인 옵션(nargs="?")은, 값이
        `-`로 시작하면(`--number-sections`, `-xelatex` 등 실제로 거의
        항상 이런 모양이다) 스페이스로 띄우면 argparse가 그 값을 별개의
        다음 옵션으로 오인한다 — 그래서 반드시 `=`로 붙여 써야 한다.
      기본 도움말 서식은 이 둘을 똑같이 "--옵션 값"으로만 보여줘서,
      뒤엣것도 띄어 써도 되는 것처럼 오해하기 쉽다. `--옵션[=값]`은
      `ls --color[=WHEN]`처럼 GNU 계열 도구들이 "값을 주려면 반드시
      =로 붙이라"는 뜻으로 흔히 쓰는 표기라, 새 문법을 만드는 대신
      이미 통용되는 관례를 그대로 가져왔다.

    argparse의 내부(밑줄 붙은) 메서드를 오버라이드하는 것이라 파이썬
    버전에 따라 세부가 바뀔 수 있지만, 여기서 건드리는 조각
    (_format_action_invocation, _get_default_metavar_for_optional)은
    아주 오래 안정적으로 유지된 부분이라 위험은 낮다고 판단했다.
    """

    def _format_action_invocation(self, action):
        if not action.option_strings or action.nargs != argparse.OPTIONAL:
            return super()._format_action_invocation(action)
        metavar = action.metavar or self._get_default_metavar_for_optional(action)
        return ", ".join(f"{opt}[={metavar}]" for opt in action.option_strings)


class _PrefixedStream:
    """print()가 쓰는 줄마다 접두어를 붙이는 아주 얇은 래퍼.

    콘솔 출력을 grep 등으로 걸러낼 수 있게 하려는 것이다 — 이 스크립트가
    직접 내는 메시지(오류·경고·안내 전부)에는 자동으로 접두어가 붙지만,
    subprocess.run()으로 띄운 자식 프로세스(xelatex/latexmk 등)의 출력은
    운영체제 파일 디스크립터를 그대로 물려받아 이 래퍼(파이썬 객체)를
    아예 거치지 않으므로 접두어가 안 붙는다 — 코드 안의 수백 개 print문을
    일일이 고치지 않고도, "이 도구 자신의 메시지"와 "컴파일러 자신의
    로그"가 자연스럽게 갈린다.

    완전히 빈 줄(개행 문자만 있는 줄)에는 접두어를 안 붙인다 — 이 방언의
    많은 print문이 `print("\\n안내...")`처럼 앞에 빈 줄을 끼워 넣는
    관례를 쓰는데, 그 빈 줄에까지 접두어가 붙으면 `[ndhmd] ` 만 있는
    보기 싫은 줄이 생긴다.
    """

    def __init__(self, stream, prefix):
        self._stream = stream
        self._prefix = prefix
        self._at_line_start = True

    def write(self, s):
        if not s:
            return 0
        out = []
        for ch in s:
            if self._at_line_start and ch != "\n":
                out.append(self._prefix)
                self._at_line_start = False
            out.append(ch)
            if ch == "\n":
                self._at_line_start = True
        self._stream.write("".join(out))
        return len(s)

    def write_raw(self, s):
        """접두어 없이 그대로 쓴다 — --brief 모드에서 컴파일 실패 시
        캡처해 둔 컴파일러 자신의 로그를 보여줄 때처럼, "이 도구의
        메시지"가 아니라 "그대로 옮겨 붙이는 남의 출력"일 때 쓴다.
        이후 write()가 다시 호출될 때를 위해 줄 시작 상태는 이 내용의
        끝이 개행인지를 보고 정확히 갱신해 둔다.
        """
        if not s:
            return 0
        self._stream.write(s)
        self._at_line_start = s.endswith("\n")
        return len(s)

    def flush(self):
        self._stream.flush()

    def isatty(self):
        return self._stream.isatty()

    def fileno(self):
        # subprocess.run() 등이 실제 OS 파일 디스크립터가 필요할 때(예:
        # stdout=None 으로 자식에게 그대로 물려줄 때) 원본 스트림의
        # fileno를 그대로 내준다 — 그래야 자식 프로세스의 출력이 이
        # 래퍼를 거치지 않고 터미널에 곧장 나간다(원래 의도한 그대로).
        return self._stream.fileno()


def main():
    # 총 경과시간은 "모든 것이 실제로 성공했을 때, 그 때에만" 맨 마지막에
    # 보여준다(main() 끝부분의 두 성공 지점 참고). 실패하거나 --lint 같은
    # 부차 기능만 쓰고 끝나면 이 시각은 아무 데도 쓰이지 않는다.
    start_time = time.monotonic()

    # 경고 메시지에는 원고에서 따온 조각(각주 식별자, 환경 이름 등)이 섞인다.
    # 표준 스트림이 파일이나 파이프로 리다이렉트되면 파이썬이 로케일 인코딩을
    # 쓰는데, 한국어 윈도우의 cp949로는 표현할 수 없는 글자가 있으면 메시지를
    # 찍다가 죽어버린다. 인코딩 자체는 건드리지 않고 에러 처리만 완화해서,
    # 표현 못 하는 글자가 있어도 변환이 멈추지 않게 한다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="ndhmarkdown dialectic -> LaTeX 변환기",
                                  formatter_class=_NdhmdHelpFormatter)
    ap.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")

    verbosity_group = ap.add_mutually_exclusive_group()
    verbosity_group.add_argument("--verbose", action="store_true",
                    help="컴파일러(xelatex/latexmk 등) 출력을 그대로 보여줌(기본값)")
    verbosity_group.add_argument("--brief", action="store_true",
                    help="컴파일러 출력은 숨기고 핵심 메시지만 보여줌(실패하면 그때 보여줌)")
    ap.add_argument("--nopreview", action="store_true",
                    help="컴파일은 하되 끝난 뒤 PDF 뷰어를 열지 않음(--pdf/--pdfxe/--pdflua/--latexmk과 함께 사용)")
    # --init-setup 은 입력 파일 없이도 쓸 수 있어야 하므로 선택 인자로 둔다.
    ap.add_argument("input", nargs="?", help="입력 .md 파일")
    ap.add_argument("-o", "--output", help="출력 .tex 파일 (기본: 입력과 같은 이름)")
    ap.add_argument("--config", help="마크업<->명령 매핑 YAML (기본값에 덮어씀)")
    ap.add_argument("--encoding", metavar="이름",
                    help="입력 파일 인코딩을 지정한다 (기본값: UTF-8)")
    ap.add_argument("--setup", metavar="파일[,파일...]",
                    help="주어진 파일을 YAML frontmatter의 바탕으로 삼는다")
    ap.add_argument("--default", "-d", metavar="파일",
                    help=f"{DEFAULT_SETUP_NAME} 대신 기본 헤더로 쓸 파일. "
                         f"NONE이면 기본 헤더 없음")
    ap.add_argument("--init-setup", action="store_true",
                    help="기본 헤더를 현재 폴더에 꺼냄")
    ap.add_argument("--fetch-images", action="store_true",
                    help="URL 그림 내려받기")
    ap.add_argument("--animation", nargs="?", const="40", metavar="N",
                    help="애니메이션 GIF. 기본값은 40장. all이면 모든 프레임")
    ap.add_argument("--search-resource", nargs="?", const="", metavar="파일",
                    help="실행 파일/스크립트 또는 주어진 리소스 경로를 찾아 보여줌")
    ap.add_argument("--guide", nargs="?", const="ndhmd4tex_dialect_guide.pdf", default=None, metavar="파일",
                    help="가이드 문서 읽기. 기본값은 ndhmd4tex_dialect_guide.pdf")
    ap.add_argument("--lint", action="store_true",
                    help="자주 저지르는 문법 오류 체크")
    ap.add_argument("--syncinfo", action="store_true",
                    help="PDF와의 상호 탐색을 위한 .nmdsync 파일 쓰기")
    ap.add_argument("--dump-meta", action="store_true",
                    help="현재 문서의 최종 front matter를 출력")
    ap.add_argument("--dump-mapping", action="store_true",
                    help="mapping:/mappingrule:/--config 를 병합한 최종 매핑 규칙을 출력")
    # nargs="?" 라서 --pandoc 만 써도, --pandoc="--number-sections" 처럼 값을
    # 붙여도 된다. 값이 - 로 시작하면 argparse가 다음 옵션으로 오해하므로
    # 반드시 = 로 붙여 써야 한다.
    ap.add_argument("--pandoc", nargs="?", const="", default=None, metavar="옵션",
                    help="본문 변환을 pandoc에 일임")
    
    ap.add_argument("--mmd", "--multimarkdown", dest="mmd", nargs="?", const="",
                    default=None, metavar="옵션",
                    help="본문 변환을 MultiMarkdown 에 일임")

    comp_group = ap.add_mutually_exclusive_group()
    comp_group.add_argument("--pdf", action="store_true", help="pdflatex으로 컴파일 미리보기")
    comp_group.add_argument("--pdfxe", action="store_true", help="xelatex으로 컴파일 미리보기")
    comp_group.add_argument("--pdflua", action="store_true", help="lualatex으로 컴파일 미리보기")
    # nargs="?" 라서 --latexmk 만 써도(기본값: -xelatex -interaction=nonstopmode),
    # --latexmk="--synctex=1 -xelatex" 처럼 latexmk 자신의 옵션을 그대로
    # 넘겨도 된다 — 이 문자열은 검증하지 않고 shlex.split해서 그대로
    # latexmk의 인자로 붙인다(compileoption:이 ksruncltex에 하는 것과
    # 같은 철학). bibtex/biber/makeindex/xindex 중 무엇을 쓸지, synctex을
    # 켤지 같은 결정은 -pdf/-xelatex/-lualatex, -synctex=1 등 **대시
    # 하나짜리 latexmk 옵션**으로 원고 작성자가 직접 고른다 — 값이 - 로
    # 시작하면 argparse가 다음 옵션으로 오해하므로 반드시 = 로 붙여 써야
    # 한다. biber는 별도 플래그가 없다 — biblatex이 .bcf 파일을 만들어
    # 두면 latexmk가 알아서 bibtex 대신 biber를 쓴다.
    comp_group.add_argument("--latexmk", nargs="?", const="", default=None, metavar="옵션",
                    help="latexmk로 컴파일 미리보기. 옵션을 부여할 수 있다")

    args = ap.parse_args()
    if args.pandoc is not None and args.mmd is not None:
        ap.error("--pandoc 와 --mmd 는 함께 쓸 수 없습니다.")

    # 콘솔 출력을 grep 등으로 걸러낼 수 있도록, 이 스크립트가 내는 모든
    # 메시지 앞에 [ndhmd]를 붙인다. --help/--version은 argparse가 이
    # 지점 이전에 이미 처리하고 끝내므로 이 접두어가 안 붙는다 — 표준적인
    # 도움말/버전 출력까지 접두어로 지저분해질 이유는 없다.
    sys.stdout = _PrefixedStream(sys.stdout, "[ndhmd] ")
    sys.stderr = _PrefixedStream(sys.stderr, "[ndhmd] ")

    # --brief 는 "이 도구가 실제로 무엇을 했는지"를 최소한으로만 보여주려는
    # 것이므로, 어떤 버전으로 실행했는지도 그 최소한에 포함시킨다 — 나머지
    # 상세 메시지(실행 명령어, 컴파일러 자신의 로그 등)는 이 옵션에서
    # 전부 숨기기 때문에, 버전 정도는 맨 앞에 남겨 둬야 나중에 "그때 그
    # 결과가 어느 버전에서 나온 건지" 추적할 수 있다.
    if args.brief:
        print(f"ndhmd4tex.py {__version__}")

    global SOURCE_ENCODING
    SOURCE_ENCODING = args.encoding

    if args.guide is not None:
        name = args.guide
        if not Path(name).suffix:
            name = name + ".pdf"
        dirs = guide_dirs()
        found = None
        for d in dirs:
            cand = d / name
            if cand.is_file():
                found = cand
                break
        if found is None:
            print(f"오류: 가이드 파일을 찾을 수 없습니다: {name}\n  찾아본 곳:",
                  file=sys.stderr)
            # guide_dirs()는 실제로 존재하는 폴더만 돌려주므로, 폴더 자체가
            # 하나도 없으면 이 목록이 비어서 "어디에 두어야 하는지"조차
            # 알려줄 수 없다 — only_existing=False로 관례적인 후보 경로
            # 전부를(존재 여부와 무관하게) 대신 보여준다.
            candidate_dirs = dirs if dirs else _conventional_dirs("guide", env_var=GUIDE_ENV, only_existing=False)
            for d in candidate_dirs:
                print(f"    {d / name}", file=sys.stderr)
            sys.exit(1)
        print(f"가이드를 엽니다: {found}")
        open_pdf(found)
        sys.exit(0)

    if args.search_resource is not None:
        if not args.search_resource:
            print(program_location())
            # 이 스크립트가 기본 스타일로 쓰는 ndhmd-default.nmd 도 함께
            # 보여준다. $0 하나만으로는 이 파일이 실제로 어디서 오는지(작업
            # 폴더인지, 스크립트/exe 옆인지, 공유 리소스 폴더인지, exe
            # 안이라면 어느 임시 폴더인지) 알 수 없기 때문이다. 여러 곳에
            # 있으면 전부 보여준다 — 맨 앞의 것이 실제로 쓰이는 것이다
            # (find_default_setup 과 같은 순서).
            defaults = find_all_default_setups()
            if defaults:
                print(f"\n{DEFAULT_SETUP_NAME} (쓰이는 순서):")
                for p in defaults:
                    print(f"  {p}")
            else:
                print(f"\n{DEFAULT_SETUP_NAME} 을 찾지 못했습니다. 찾아본 곳:")
                for d in default_setup_dirs():
                    print(f"  {d / DEFAULT_SETUP_NAME}")
            sys.exit(0)
        hits = search_resource(args.search_resource)
        if not hits:
            print(f"'{args.search_resource}' 을(를) 찾지 못했습니다. 찾아본 곳:",
                  file=sys.stderr)
            tried, seen = [Path.cwd() / args.search_resource], set()
            for d in resource_dirs():
                tried.append(d / args.search_resource)
            if Path(args.search_resource).name == DEFAULT_SETUP_NAME:
                for d in default_setup_dirs():
                    tried.append(d / args.search_resource)
            for t in tried:
                try:
                    key = t.resolve()
                except OSError:
                    key = t
                if key in seen:
                    continue
                seen.add(key)
                print(f"  {t}", file=sys.stderr)
            sys.exit(1)
        for h in hits:
            print(h)
        sys.exit(0)

    if args.init_setup:
        sys.exit(init_default_setup())

    if args.lint:
        if not args.input:
            ap.error("점검할 .md 파일이 필요합니다")
        sys.exit(run_lint([args.input]))

    if not args.input:
        ap.error("입력 .md 파일이 필요합니다 (기본 헤더만 꺼내려면 --init-setup)")

    src_path = Path(args.input)
    try:
        text = read_source_text(src_path)
    except SourceError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)

    # --default 값 전처리. "NONE"(대문자, 정확히 일치)은 그대로 두고
    # apply_setup_fallback() 이 특수 신호로 해석하게 한다. 그 외에는
    # 확장자가 없을 때만 .nmd 를 붙인다 — 이미 있으면(점이 하나라도 있으면)
    # 사용자가 고른 그대로 존중한다.
    cli_default = args.default
    if cli_default and cli_default != "NONE" and not Path(cli_default).suffix:
        cli_default = cli_default + ".nmd"

    # --default NONE 이면 문서 구조(class/title/preamble/maketitle/tocloft
    # 등)는 무시하고 본문만 조각으로 낸다 — 단, mapping:/mappingrule:/
    # --config/toplevel: 처럼 "마크업을 어떻게 번역할지"를 정하는 것들은
    # 그대로 반영한다. 이 둘은 서로 다른 층이다 — 전자는 오직
    # build_document()/_build_header_lines()/_build_frontmatter_commands()
    # 안에서만 읽히므로, 그 함수들을 안 부르기만 하면 자동으로 아무 영향이
    # 없다(따로 걷어낼 필요가 없다). 후자는 convert()/convert_pandoc()/
    # main()의 cfg 구성에서 읽혀 본문 변환 자체에 관여하므로, 다른 문서에
    # 끼워 넣을 조각을 낼 때도 그 문서의 관례(예: extra_inline, 커스텀
    # 헤딩 레벨)를 맞추려면 여전히 살아있어야 한다. 그래서 meta 해석과
    # cfg 구성은 body_only 여부와 무관하게 언제나 똑같이 진행한다 —
    # 다른 점은 오직 맨 끝에서 build_document()를 부르느냐 마느냐뿐이다.
    body_only = (cli_default == "NONE")

    # front matter는 여기서 딱 한 번 해석한다(setup 체인 포함). 결과를
    # convert()에도 그대로 넘겨서 이중 파싱을 없앤다.
    try:
        meta, _, setup_chain = resolve_meta(text, src_path, cli_setup=args.setup, cli_default=cli_default)
    except SetupError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)

    if args.dump_meta:
        if body_only:
            print("# --default NONE 이 지정되어 문서 구조(class/title/"
                  "preamble/maketitle/tocloft 등)는 무시하고 본문만 냅니다.\n"
                  "# mapping/mappingrule/toplevel 등 마크업 번역 규칙은 "
                  "아래 메타에 있는 그대로 여전히 적용됩니다.")
        elif setup_chain:
            trail = " -> ".join([src_path.name] + [str(c) for c in setup_chain])
            print(f"# setup 체인: {trail}")
        elif not args.setup:
            # 기본 헤더를 못 찾았을 때 무슨 일이 있었는지 알려준다. 조용히
            # 넘어가면 "왜 안 먹지"를 추적할 방법이 없다. --default 를
            # 줬다면 그 사실 자체가 진단에서 드러나야 한다 — 안 그러면
            # 사용자가 자기가 지정한 적도 없는 ndhmd-default.nmd 라는
            # 이름이 뜬 것을 보고 --default 가 안 먹혔다고 오해할 수 있다.
            # (--default NONE 은 위 body_only 분기에서 이미 처리되므로
            # 여기 도달할 때는 cli_default 가 None 이거나 실제 파일명이다.)
            if cli_default:
                print(f"# --default 로 지정한 {cli_default} 을 찾지 못했습니다. 찾아본 곳:")
                for d in default_setup_dirs():
                    print(f"#   {d / cli_default}")
            else:
                print(f"# {DEFAULT_SETUP_NAME} 을 찾지 못했습니다. 찾아본 곳:")
                for d in default_setup_dirs():
                    print(f"#   {d / DEFAULT_SETUP_NAME}")
        print(yaml.safe_dump(meta, allow_unicode=True, default_flow_style=False, sort_keys=True))
        print("====== end of meta =======")
        # 여기서 곧장 끝내지 않는다 — --dump-mapping을 함께 줬을 수도
        # 있는데, 그건 mapping:/mappingrule:/--config 를 전부 병합한
        # cfg가 필요하고 그 계산은 아직 안 끝났다. 실제 종료는 그
        # 계산까지 마친 뒤, --dump-meta/--dump-mapping 공통 출구에서
        # 한다(아래 "그림 처리 설정은 cfg에 실어 보낸다" 바로 앞 참고).

    # mapping 경로는 setup에서 상속됐더라도 언제나 최상위 입력 파일 기준.
    # --default NONE(body_only) 이어도 이 부분은 그대로 진행한다 —
    # mapping:/mappingrule:/--config 는 "마크업을 어떻게 번역할지"를
    # 정하는 것이라, 다른 문서에 끼워 넣을 조각을 낼 때도 그 문서의
    # 관례(예: extra_inline, 커스텀 헤딩 레벨)를 맞추려면 여전히
    # 살아있어야 한다(위 body_only 정의 옆 주석 참고).
    cfg_path = args.config or meta.get("mapping")
    # front matter의 mapping: 은 setup: 과 마찬가지로 문자열 하나뿐 아니라
    # 리스트도 받는다 — "회사 공통 규칙 파일 + 프로젝트 전용 규칙 파일"처럼
    # 여러 mapping.yaml에 나눠 적은 걸 한 문서에서 다 쓰고 싶을 때를
    # 위해서다. --config(CLI)는 지금은 그대로 단일 파일만 받는다 — 명령줄
    # 에서 여러 파일을 나열하고 싶다면 --setup처럼 콤마 구분을 나중에
    # 추가할 수 있지만, 이번 확장은 front matter의 mapping: 에만
    # 요청됐으므로 범위를 거기로 좁혔다.
    cfg_paths = cfg_path if isinstance(cfg_path, list) else ([cfg_path] if cfg_path else [])
    resolved_paths = []
    for one_path in cfg_paths:
        # --config 는 작업 폴더 기준, front matter의 mapping: 은 입력 파일
        # 기준. 어느 쪽이든 못 찾으면 공유 리소스 폴더를 본다.
        near = [Path.cwd()] if args.config else [src_path.parent]
        found, tried = resolve_resource(one_path, near=near)
        if found is None:
            trail = "\n".join(f"    {t}" for t in tried)
            print(f"오류: 매핑 파일을 찾을 수 없습니다: {one_path}\n  찾아본 곳:\n{trail}",
                  file=sys.stderr)
            sys.exit(1)
        resolved_paths.append(found)
    try:
        cfg = load_configs(resolved_paths)
    except ConfigError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)

    # front matter의 mappingrule: — mapping.yaml 파일을 따로 두기에는 아까운,
    # 한두 항목만 손보는 경우를 위한 것이다. mapping: 파일 위에 얹히므로 파일
    # 전체를 복사해 올 필요 없이 바꿀 것만 적으면 된다. setup: 으로 상속되고
    # mappingrule+: 로 덧붙일 수도 있다(다른 front matter 키와 같은 규칙).
    mapping_rule = meta.get("mappingrule")
    if mapping_rule:
        try:
            extra = yaml.safe_load(mapping_rule)
        except yaml.YAMLError as e:
            print(f"오류: front matter의 mappingrule 을 읽지 못했습니다.\n  {e}",
                  file=sys.stderr)
            sys.exit(1)
        if extra is not None and not isinstance(extra, dict):
            print("오류: front matter의 mappingrule 은 key: value 형태여야 합니다.",
                  file=sys.stderr)
            sys.exit(1)
        if extra:
            cfg = deep_merge(cfg, extra)
            if args.config:
                # --config 는 명령줄에서 준 것이라 front matter의 그 무엇보다
                # 최종 발언권을 갖는다(파일 규칙: --config > mapping: 과 같은
                # 원칙을 mappingrule: 에도 적용). raw YAML만 다시 얹는다 —
                # load_config() 의 전체 병합 결과를 얹으면 --config 파일이
                # 건드리지 않은 키까지 기본값으로 되돌아간다.
                try:
                    cli_raw = load_config_raw(resolved_paths[0])
                except ConfigError as e:
                    print(f"오류: {e}", file=sys.stderr)
                    sys.exit(1)
                cfg = deep_merge(cfg, cli_raw)

    if args.dump_mapping:
        # 이 시점의 cfg가 정확히 "이어붙이거나 덮어쓴 최종 유효한
        # mapping" 이다 — mapping:(여러 파일이면 뒤가 이기는 병합까지
        # 끝났고), mappingrule:, --config(있으면 최종 발언권)까지 전부
        # 반영됐다. 아래에서 cfg에 _image_base 같은 내부 전용 키(밑줄로
        # 시작, 이 실행 한 번을 위한 구현 세부사항일 뿐 원고 작성자가
        # 볼 필요 없는 것)를 덧붙이기 *직전*이라 아직 순수하다 — 그런
        # 키가 하나라도 섞여 나가면 "이게 mapping.yaml에 실제로 적는
        # 키인가?"라는 오해를 살 수 있어 이 타이밍을 골랐다.
        print(yaml.safe_dump(cfg, allow_unicode=True, default_flow_style=False, sort_keys=True))
        print("====== end of mapping =======")

    if args.dump_meta or args.dump_mapping:
        return

    # 그림 처리 설정은 cfg 에 실어 보낸다. do_figure 가 cfg 밖에 닿지 못한다.
    cfg["_image_base"] = str(src_path.parent)
    cfg["_fetch_images"] = args.fetch_images
    cfg["_animation_on"] = args.animation is not None
    if args.animation is None:
        cfg["_animation_frames"] = None
    elif str(args.animation).lower() in ("all", "*", "0"):
        # all: 상한 없음. 늘어나는 파일은 저자가 감당한다.
        cfg["_animation_frames"] = None
    else:
        try:
            cfg["_animation_frames"] = max(1, int(args.animation))
        except ValueError:
            print(f"오류: --animation 값이 숫자가 아닙니다: {args.animation}",
                  file=sys.stderr)
            sys.exit(1)

    try:
        sync_entries = None
        if body_only:
            # 문서를 감싸지 않으므로("--default NONE" 참고) 컴파일 결과
            # 자체가 없다 — sync 는 tex 줄 번호와 컴파일된 위치를 잇는
            # 것이라 애초에 대응시킬 대상이 없다.
            if args.syncinfo:
                print("경고: --default NONE 에서는 --syncinfo 를 만들 수 없습니다 "
                      "(문서를 감싸지 않는 본문 전용 출력이라, 몇 줄이 몇 줄이 "
                      "됐는지 대응시킬 컴파일 결과 자체가 없습니다). "
                      ".nmdsync 파일은 생성되지 않았습니다.", file=sys.stderr)
            if args.pandoc is not None:
                tex = convert_pandoc(text, include_base=src_path.parent, meta=meta,
                                     extra_args=args.pandoc, cfg=cfg, body_only=True)
            elif args.mmd is not None:
                tex = convert_mmd(text, include_base=src_path.parent, meta=meta,
                                  extra_args=args.mmd, cfg=cfg, body_only=True)
            else:
                tex = convert(text, cfg, include_base=src_path.parent, meta=meta, body_only=True, source_path=src_path)
        elif args.mmd is not None:
            tex = convert_mmd(text, include_base=src_path.parent, meta=meta,
                              extra_args=args.mmd, cfg=cfg)
            if args.syncinfo:
                print("경고: --mmd 모드에서는 --syncinfo 를 만들 수 없습니다 "
                      "(본문 변환을 mmd 서브프로세스에 통째로 맡깁니다). "
                      ".nmdsync 파일은 생성되지 않았습니다.", file=sys.stderr)
        elif args.pandoc is not None:
            tex = convert_pandoc(text, include_base=src_path.parent, meta=meta,
                                 extra_args=args.pandoc, cfg=cfg)
            if args.syncinfo:
                print("경고: --pandoc 모드에서는 --syncinfo 를 만들 수 없습니다 "
                      "(본문 변환을 pandoc 서브프로세스에 통째로 맡기므로, 몇 줄이 "
                      "몇 줄이 됐는지 이 스크립트가 알 방법이 없습니다). "
                      ".nmdsync 파일은 생성되지 않았습니다.", file=sys.stderr)
        elif args.syncinfo:
            # SyncInfoUnavailable 은 지금은 generate_syncinfo() 가 던질 일이
            # 없다({{포함}}도 resolve_includes_tracked() 로 지원되므로) —
            # 그래도 앞으로 또 다른 제약이 발견될 경우를 대비한 안전망으로
            # 예외 클래스와 이 처리를 그대로 남겨 둔다. 걸리면 변환 자체는
            # 계속 진행하고 .nmdsync 만 포기한다.
            try:
                tex, sync_entries = generate_syncinfo(
                    text, cfg, include_base=src_path.parent, meta=meta,
                    source_path=src_path)
            except SyncInfoUnavailable as e:
                print(f"경고: {e} 변환은 계속하지만 .nmdsync 는 만들지 않습니다.",
                      file=sys.stderr)
                tex = convert(text, cfg, include_base=src_path.parent, meta=meta, source_path=src_path)
                sync_entries = None
        else:
            tex = convert(text, cfg, include_base=src_path.parent, meta=meta, source_path=src_path)
    except IncludeError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)
    except PandocError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.output) if args.output else src_path.with_suffix(".tex")
    try:
        out_path.write_text(tex, encoding="utf-8")
    except FileNotFoundError:
        print(f"오류: 출력 폴더가 없습니다: {out_path.parent}\n"
              f"  폴더를 먼저 만들거나 -o 경로를 확인하십시오.", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"오류: 출력 파일을 쓸 수 없습니다: {out_path}\n  {e}", file=sys.stderr)
        sys.exit(1)
    print(f"변환 완료: {out_path}")

    if args.syncinfo and sync_entries is not None:
        sync_path = out_path.with_suffix(".nmdsync")
        try:
            write_syncinfo_file(sync_path, sync_entries)
            print(f"동기화 정보: {sync_path}")
        except OSError as e:
            print(f"경고: .nmdsync 파일을 쓰지 못했습니다: {sync_path}\n  {e}",
                  file=sys.stderr)

    engine_flag = None
    if args.pdf:
        engine_flag = "--pdflatex"
    elif args.pdfxe:
        engine_flag = "--xelatex"
    elif args.pdflua:
        engine_flag = "--lualatex"

    use_latexmk = args.latexmk is not None

    if body_only and (engine_flag or use_latexmk):
        # 문서를 감싸지 않은 본문 조각이라 그대로는 컴파일되지 않는다
        # (\documentclass도, \begin{document}도 없다). 조용히 실패하게
        # 두는 대신 여기서 확실히 끄고 알려준다. 이후 코드는 engine_flag/
        # use_latexmk 가 둘 다 거짓이면 그냥 변환만 하고 끝나므로, 이
        # 시점에 꺼두기만 하면 나머지(암시적 latexmk 전환 등)는 자연히
        # 다 건너뛰어진다.
        print("경고: --default NONE 에서는 컴파일 옵션(--pdf/--pdfxe/--pdflua/"
              "--latexmk)을 무시합니다 — 문서를 감싸지 않는 본문 전용 출력이라 "
              "그대로는 컴파일되지 않습니다.", file=sys.stderr)
        engine_flag = None
        use_latexmk = False

    # front matter에 latexmkoption: 이 있고 compileoption: 이 없으면,
    # --pdf/--pdfxe/--pdflua 를 ksruncltex 대신 자동으로 latexmk로 돌린다.
    # 이렇게 하면 원고 자체가 "나는 latexmk로 컴파일한다"는 뜻을 담게
    # 되고, 명령줄에서는 평소처럼 --pdfxe 등만 쳐도(--latexmk를 따로
    # 안 붙여도) latexmk가 불린다. compileoption: 이 있으면(즉 이 원고가
    # 이미 ksruncltex 용 추가 옵션을 갖고 있으면) 기존처럼 ksruncltex를
    # 그대로 쓴다 — 둘 다 있는 원고는 "아직 ksruncltex를 쓴다"는 뜻으로
    # 해석한다. 두 키 다 없으면 당연히 원래 기본값(ksruncltex) 그대로다.
    # 엄밀히 "키가 존재하는지"로 판정한다(값이 빈 문자열이어도 "존재"로
    # 친다) — meta.get(...) 의 참/거짓이 아니라 in 으로 검사하는 이유다.
    implicit_latexmk_engine = None
    if engine_flag and "latexmkoption" in meta and "compileoption" not in meta:
        implicit_latexmk_engine = {
            "--pdflatex": "-pdf",
            "--xelatex": "-pdfxe",
            "--lualatex": "-pdflua",
        }[engine_flag]
        engine_flag = None
        use_latexmk = True

    if not engine_flag and not use_latexmk:
        # 컴파일 없이 변환만으로 끝나는 경로. 여기가 유일한 성공 지점이므로
        # 여기서 경과시간을 보여준다(컴파일까지 갔을 때는 아래 두 번째
        # 지점에서 보여주고, 셋 중 하나만 실행되므로 중복되지 않는다).
        _print_elapsed(start_time)

    if engine_flag:
        if not args.brief:
            print(f"\nPDF 컴파일을 시작합니다... (옵션: {engine_flag})")

        if sys.platform == "win32":
            cmd = ["ksruncltex.bat"]
        else:
            try:
                # errors="replace": TeX 트리 경로에 로케일 인코딩으로 표현할 수
                # 없는 글자가 있어도 여기서 죽지 않게 한다. 경로가 깨지면
                # 어차피 아래 실행 단계에서 잡힌다.
                kpse_path = subprocess.check_output(
                    ["kpsewhich", "ksruncltex.lua"], text=True, errors="replace").strip()
                if not kpse_path:
                    print("오류: kpsewhich로 ksruncltex.lua를 찾을 수 없습니다.", file=sys.stderr)
                    sys.exit(1)
                cmd = ["texlua", kpse_path]
            except Exception as e:
                print(f"오류: kpsewhich 실행 실패 ({e})\n"
                      f"  ksruncltex 가 설치돼 있는지 확인하십시오.", file=sys.stderr)
                sys.exit(1)
        
        cmd.append(engine_flag)
        
        yaml_opts = meta.get("compileoption", "")
        if yaml_opts:
            cmd.extend(shlex.split(yaml_opts))

        # --syncinfo 는 SyncTeX 자체도 필요로 한다. compileoption: 이 이미
        # -synctex=.../--synctex=... 을 갖고 있으면 원고 작성자의 선택을
        # 그대로 두고 손대지 않는다(_has_synctex_option 참고). ksruncltex는
        # 대시 두 개(--synctex=1) 관례를 쓴다 — 기존 가이드/quickstart의
        # compileoption: 예시가 전부 이 형태였다(latexmk는 반대로 대시
        # 하나가 정식 문법이라 아래 latexmk 분기에서는 -synctex=1을 쓴다).
        if args.syncinfo and not _has_synctex_option(cmd):
            cmd.append("--synctex=1")

        cmd.append(out_path.name)
        
        try:
            result = _run_compiler(cmd, out_path.parent, args.brief)
            if result.returncode == 0:
                pdf_path = out_path.with_suffix(".pdf")
                if args.nopreview:
                    print(f"PDF를 만들었습니다(뷰어는 열지 않음): {pdf_path.name}" if args.brief
                          else f"\nPDF를 만들었습니다(뷰어는 열지 않음): {pdf_path.name}")
                else:
                    print(f"PDF를 엽니다: {pdf_path.name}" if args.brief else f"\nPDF를 엽니다: {pdf_path.name}")
                    open_pdf(pdf_path)
                _print_elapsed(start_time)
            else:
                print("\nPDF 컴파일 중 오류가 발생했습니다. 터미널의 로그를 확인하세요.", file=sys.stderr)
                sys.exit(result.returncode)
        except FileNotFoundError:
            print("\n오류: 실행 파일을 찾을 수 없습니다. PATH 설정을 확인하세요.", file=sys.stderr)
            sys.exit(1)

    elif use_latexmk:
        if not args.brief:
            if implicit_latexmk_engine is not None:
                print(
                    f"\nlatexmkoption: 이 있고 compileoption: 이 없어 "
                    f"latexmk로 자동 전환합니다... (엔진: {implicit_latexmk_engine})"
                )
            else:
                print("\nPDF 컴파일을 시작합니다... (latexmk)")

        latexmk_bin = shutil.which("latexmk")
        if latexmk_bin is None:
            print("오류: latexmk 를 PATH 에서 찾을 수 없습니다. "
                  "TeX Live/MiKTeX 설치에 포함돼 있는지 확인하십시오.", file=sys.stderr)
            sys.exit(1)

        cmd = [latexmk_bin]

        if implicit_latexmk_engine is not None:
            # --pdf/--pdfxe/--pdflua + latexmkoption: 조합으로 자동
            # 전환된 경로 — 명시적 --latexmk="..." 와는 결합 방식이
            # 다르다. 여기서는 엔진을 CLI가 고른 그대로 따르고(옵션이
            # 있다고 기본 엔진을 빼는 그 아래 분기의 규칙이 적용되지
            # 않는다 — 애초에 엔진은 이미 --pdf 계열로 확정됐으므로), 그
            # 뒤에 latexmkoption: 값을 그대로 이어붙인다. args.latexmk
            # (명시적 --latexmk)는 이 경로에서는 애초에 None이다
            # (--pdf 계열과 --latexmk 는 상호 배타이므로).
            cmd.append(implicit_latexmk_engine)
            latexmkoption_val = meta.get("latexmkoption", "")
            if latexmkoption_val:
                cmd.extend(shlex.split(str(latexmkoption_val)))
        else:
            # front matter의 latexmkoption: 이 먼저, CLI의 --latexmk="..." 값이
            # 나중 — pandocoption:/--pandoc 과 같은 순서 규칙이다. 이 문자열은
            # 검증하지 않고 shlex.split해서 그대로 latexmk의 인자로 붙인다
            # (compileoption:이 ksruncltex에 하는 것과 같은 철학) — bibtex나
            # biber냐, makeindex냐 xindy냐, synctex을 켤지 같은 결정은 전부
            # 이 문자열 안에서 원고 작성자가 latexmk 자신의 옵션으로 직접
            # 고른다. latexmk는 대시 한 개(`-xelatex`)가 정식 문법이지만
            # 두 개(`--xelatex`)도 관대하게 받아들이는 것을 실측으로 확인했다
            # (Perl Getopt::Long 특유의 동작) — 다만 실재하지 않는 옵션(예:
            # `--biber`, `-biber` 둘 다 없는 옵션이다. biber 사용 여부는
            # biblatex이 만드는 .bcf 파일 유무로 latexmk가 스스로 판단한다)을
            # 주면 latexmk 자신이 명확한 오류를 낸다 — 이 스크립트가 나서서
            # 옵션을 검증하거나 대신 고쳐주지 않는다.
            user_args = []
            for src in (meta.get("latexmkoption", ""), args.latexmk or ""):
                if src:
                    user_args.extend(shlex.split(str(src)))

            if user_args:
                cmd.extend(user_args)
            else:
                # 아무 옵션도 안 줬을 때만 적용하는 기본값 — 이 방언이 한글을
                # 다루므로 xelatex을 기본 엔진으로 삼는다. 옵션을 하나라도
                # 줬다면 이 기본값은 아예 끼워 넣지 않는다 — 원고 작성자가
                # 준 옵션과 상충하는 엔진 플래그가 섞여 들어가는 것을 막기
                # 위해서다(예: latexmkoption: -pdf 라고만 줬는데 여기서 몰래
                # -xelatex 도 같이 넣으면 둘이 충돌한다).
                cmd.append("-xelatex")

        # --syncinfo 는 SyncTeX 자체도 필요로 한다. latexmkoption:/
        # --latexmk="..." 이 이미 -synctex=... 을 갖고 있으면 원고
        # 작성자의 선택을 그대로 두고 손대지 않는다(암시적 전환 경로든
        # 명시적 경로든, 이 시점이면 cmd에 그 옵션이 이미 다 들어간
        # 뒤이므로 여기 한 곳에서만 검사하면 둘 다 커버된다). latexmk는
        # 대시 하나(-synctex=1)가 정식 문법이다 — ksruncltex(위
        # engine_flag 분기)의 --synctex=1(대시 두 개) 관례와 다르다.
        if args.syncinfo and not _has_synctex_option(cmd):
            cmd.append("-synctex=1")

        # -interaction=nonstopmode 는 사용자가 이미 줬든 안 줬든 항상
        # 강제로 붙인다 — 없으면 오류가 났을 때 그 안에서 호출되는
        # *latex 엔진이 터미널 입력을 기다리며 멈춰 버리는 것을 실측으로
        # 확인했다. 중복으로 들어가도 무해하다.
        cmd.append("-interaction=nonstopmode")

        cmd.append(out_path.name)

        try:
            result = _run_compiler(cmd, out_path.parent, args.brief)
            if result.returncode == 0:
                pdf_path = out_path.with_suffix(".pdf")
                if args.nopreview:
                    print(f"PDF를 만들었습니다(뷰어는 열지 않음): {pdf_path.name}" if args.brief
                          else f"\nPDF를 만들었습니다(뷰어는 열지 않음): {pdf_path.name}")
                else:
                    print(f"PDF를 엽니다: {pdf_path.name}" if args.brief else f"\nPDF를 엽니다: {pdf_path.name}")
                    open_pdf(pdf_path)
                _print_elapsed(start_time)
            else:
                print("\nPDF 컴파일 중 오류가 발생했습니다. 터미널의 로그를 확인하세요.", file=sys.stderr)
                sys.exit(result.returncode)
        except FileNotFoundError:
            print("\n오류: 실행 파일을 찾을 수 없습니다. PATH 설정을 확인하세요.", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
