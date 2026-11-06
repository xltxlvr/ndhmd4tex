#!/usr/bin/env python3
r"""ndhmdsync.py — .nmdsync 를 이용해 md<->tex 줄 번호를 서로 바꾼다.

ndhmd4tex.py --syncinfo 가 만드는 {출력}.nmdsync 파일을 읽어, 두 방향을
지원한다.

역방향(--line): "이 .tex 파일의 N번째 줄은 원본 .md 파일의 몇 번째 줄이었나".
PDF 뷰어의 "역방향 검색(inverse search)" 명령으로 등록해 두면, 다음 체인이
완성된다.

    PDF 클릭 --[SyncTeX]--> tex 줄 번호 --[ndhmdsync.py]--> md 줄 번호
                                                              --[code --goto]--> VS Code

이 문서가 애초에 ndhmd4tex.py --syncinfo 로 만들어진 게 아니라 손으로 쓴
LaTeX을 곧장(latexmk 등으로) 컴파일한 것이면 .nmdsync 자체가 없다 —
이 경우 .synctex.gz/.synctex 가 있는지만 확인해, 있으면 markdown 역추적을
포기하고 .tex 파일 자신을 그 줄에서 연다([TEXEDIT] 섹션, 아래 참고). PDF
뷰어의 역방향 검색 명령을 한 번 등록해 두면, markdown 기반 문서든 순정
LaTeX 문서든 같은 설정으로 둘 다 다뤄진다는 뜻이다. .synctex 류도 없으면
(즉 SyncTeX 자체가 꺼져 있었으면) 평소처럼 오류로 알린다.

정방향(--md-line): "지금 에디터에 있는 .md 파일의 N번째 줄은 .tex 파일의
몇 번째 줄이 됐나"를 찾아 PDF 뷰어로 그 위치를 보여준다. VS Code의
tasks.json에 등록해 단축키로 쓰는 것을 염두에 두었다(${file}, ${lineNumber}
내장 변수를 그대로 넘기면 된다).

    VS Code 커서 위치 --[tasks.json의 ${file}/${lineNumber}]--> ndhmdsync.py
                       --[.nmdsync]--> tex 줄 번호 --[뷰어의 forward search]--> PDF

지원하는 PDF 뷰어는 플랫폼별로 하나씩만 고정한다: Windows는 SumatraPDF,
macOS는 Skim, 그 외(Linux)는 Okular. 다른 뷰어는 지원하지 않는다.

다만 아래 세 폴더를 순서대로 뒤져 ndhmdsync.ini 가 있으면, 하드코딩된
뷰어·에디터 대신 그 설정을 우선 적용한다(ndhmd4tex.py 의 resource_dirs()
가 공유 리소스를 찾는 것과 정확히 같은 관례 — 그 옆에 있을 ndhmd4tex/
resources 폴더와 나란히 두려는 것이다). OS별로 하나만 보는 게 아니라
**셋 다 순서대로** 훑는다 — 설정을 여러 기계에서 동기화해 쓰는 경우를
감안한 것이다.

    ~/Library/ndhmd4tex/config/ndhmdsync.ini
    ~/ndhmd4tex/config/ndhmdsync.ini
    ~/.config/ndhmd4tex/config/ndhmdsync.ini

파일 형식은 예시로 함께 배포되는 ndhmdsync.ini.example 참고. 값 안에서
%f(대상 파일), %l(줄 번호), %p(정방향에서만, PDF 경로)를 자리표시자로 쓴다.
[TEXEDIT] 섹션(.nmdsync 없이 .synctex 류만 있을 때 쓰는 에디터)은 command
가 아예 없으면 OS 기본 프로그램으로 그냥 여는 게 기본값이다 — 다른 두
섹션과 달리 "하드코딩된 특정 프로그램"으로의 폴백이 없다.

지원하는 파일 포함(ndhmd4tex.py 의 {{파일}})도 이 스크립트 자체는 손댈
것이 없다 — .nmdsync 의 각 항목이 처음부터 자기 소스 파일을 따로 갖는
구조였으므로, 최상위 파일과 포함된 파일이 섞인 .nmdsync 도 그대로
읽힌다(ndhmd4tex.py 0.9.0 부터). 다만 포함된 서브파일을 직접 열어 놓고
정방향 검색을 하면 출력 경로 유추가 서브파일 자신의 이름을 따라가려
해서 틀리는데, 서브파일의 front matter에 `ndhmain: main.md` 를 적어
두면 그 파일을 기준으로 유추하도록 바꿀 수 있다(값이 없거나 자기
자신을 가리키면 평소대로 그 파일 자신이 최상위 문서다).

사용법:
    # 역방향 — PDF 뷰어의 inverse search 명령으로 등록
    python3 ndhmdsync.py 파일.tex --line 125
    python3 ndhmdsync.py 파일.tex --line 125 --print   # 에디터를 열지 않고 결과만 출력

    # 정방향 — 에디터에서 실행
    python3 ndhmdsync.py 파일.md --md-line 42
    python3 ndhmdsync.py 파일.md --md-line 42 --print  # 뷰어를 열지 않고 결과만 출력

Copyright (c) 2026 Nova de Hi
Licensed under the MIT License. See LICENSE for details.
"""

import argparse
import configparser
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

__version__ = "0.5.6"


class SyncLookupError(Exception):
    pass


def load_syncinfo(path):
    """.nmdsync 를 읽어 [(tex_start, tex_end, source_file, src_start, src_end), ...] 로.

    tex_start 기준으로 정렬해서 돌려준다.
    """
    entries = []
    text = Path(path).read_text(encoding="utf-8")
    for lineno, raw in enumerate(text.split("\n"), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 5:
            raise SyncLookupError(
                f"{path}:{lineno}: 형식이 어긋났습니다(탭 구분 5개 필드 필요): {raw!r}"
            )
        try:
            tex_s, tex_e = int(parts[0]), int(parts[1])
            src_s, src_e = int(parts[3]), int(parts[4])
        except ValueError:
            raise SyncLookupError(f"{path}:{lineno}: 줄 번호가 숫자가 아닙니다: {raw!r}")
        entries.append((tex_s, tex_e, parts[2], src_s, src_e))
    entries.sort(key=lambda e: e[0])
    return entries


def find_source_location(entries, tex_line):
    """tex_line 을 담는 구간을 찾는다. 없으면 가장 가까운 구간으로 근사한다.

    (source_file, src_line, exact) 를 돌려준다. exact 가 False 면 정확히
    담는 구간이 없어 근처 구간으로 대신했다는 뜻이다.
    """
    if not entries:
        raise SyncLookupError("동기화 정보가 비어 있습니다.")

    for tex_s, tex_e, src_file, src_s, src_e in entries:
        if tex_s <= tex_line <= tex_e:
            tex_span = tex_e - tex_s
            src_span = src_e - src_s
            if tex_span > 0 and src_span > 0:
                ratio = (tex_line - tex_s) / tex_span
                src_line = src_s + round(ratio * src_span)
            else:
                src_line = src_s
            return src_file, src_line, True

    # 정확히 담는 구간이 없다 — 가장 가까운 구간으로 근사한다. 거리가
    # 동률이면(전형적으로 문단 사이의 "구분용 빈 줄"처럼 앞뒤 구간까지
    # 거리가 똑같은 경계 지점) *다음* 구간을 우선한다.
    #
    # 예를 들어 main.md 가 {{sub/chap1.md}} 를 포함하는 경계에서, main.md
    # 의 마지막 문단과 chap1.md 의 첫 블록 사이에 있는 빈 줄에서 역방향
    # 검색을 하면, 예전에는(파이썬 min() 이 동률일 때 리스트의 앞쪽 —
    # tex_start 오름차순 정렬이므로 더 작은 tex_line, 즉 "이전" 구간 —
    # 을 그대로 유지하는 성질 때문에) 서브파일로 들어가지 못하고 그 앞의
    # main.md 줄에서 멈추는 것이 실사용에서 확인됐다. key 를
    # (거리, -tex_start) 튜플로 주면, 거리가 같을 때 tex_start 가 더 큰
    # 쪽(뒤에 오는 구간)이 이긴다 — 어느 쪽으로도 "정답"이 없는 경계
    # 이므로, {{포함}} 직후 진입 방향을 우선한 것뿐이지 이게 유일하게
    # 옳은 방향이라는 뜻은 아니다.
    def _distance(e):
        tex_s, tex_e = e[0], e[1]
        if tex_line < tex_s:
            return tex_s - tex_line
        if tex_line > tex_e:
            return tex_line - tex_e
        return 0

    best = min(entries, key=lambda e: (_distance(e), -e[0]))
    tex_s, tex_e, src_file, src_s, src_e = best
    src_line = src_s if abs(tex_line - tex_s) <= abs(tex_line - tex_e) else src_e
    return src_file, src_line, False


def find_tex_location(entries, md_file, md_line):
    """find_source_location() 의 반대 방향 — md_line(md 파일 기준)을 담는
    구간을 찾아 tex 줄 번호로 바꾼다. (tex_line, exact) 를 돌려준다.

    entries 는 여러 소스 파일이 섞여 있을 수 있다 — {{포함}} 을 쓰는
    문서라면 최상위 파일과 포함된 파일들이 한 .nmdsync 안에 함께 담긴다
    (ndhmd4tex.py 0.9.0 부터). 그러니 먼저 md_file과 같은 파일을 가리키는
    항목만 추린다. 경로 비교는 절대경로로 정규화해서 한다 — 에디터가
    주는 경로와 .nmdsync 에 적힌 경로의 표기가(상대/절대, 대소문자 등)
    다를 수 있어서다.
    """
    if not entries:
        raise SyncLookupError("동기화 정보가 비어 있습니다.")

    md_resolved = Path(md_file).resolve()
    same_file = [e for e in entries if Path(e[2]).resolve() == md_resolved]
    if not same_file:
        known = sorted({str(Path(e[2]).resolve()) for e in entries})
        known_list = "\n".join(f"    {k}" for k in known)
        raise SyncLookupError(
            f"{md_resolved} 를 가리키는 항목이 동기화 정보 안에 없습니다.\n"
            f"  .nmdsync 안에 있는 파일:\n{known_list}\n"
            f"  두 값이 다르다면 에디터가 준 파일과 .nmdsync가 실제로 짝이 "
            f"맞는지 확인하십시오."
        )

    for tex_s, tex_e, src_file, src_s, src_e in same_file:
        if src_s <= md_line <= src_e:
            tex_span = tex_e - tex_s
            src_span = src_e - src_s
            if tex_span > 0 and src_span > 0:
                ratio = (md_line - src_s) / src_span
                tex_line = tex_s + round(ratio * tex_span)
            else:
                tex_line = tex_s
            return tex_line, True

    # find_source_location() 과 같은 원칙 — 동률이면 다음 구간을 우선한다.
    def _distance(e):
        src_s, src_e = e[3], e[4]
        if md_line < src_s:
            return src_s - md_line
        if md_line > src_e:
            return md_line - src_e
        return 0

    best = min(same_file, key=lambda e: (_distance(e), -e[3]))
    tex_s, tex_e, src_file, src_s, src_e = best
    tex_line = tex_s if abs(md_line - src_s) <= abs(md_line - src_e) else tex_e
    return tex_line, False


# --------------------------------------------------------------------------
# Config Loading & Parsing
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Config Loading & Parsing
# --------------------------------------------------------------------------
#
# ndhmd4tex.py의 resource_dirs()(공유 설정 파일을 찾는 함수)와 정확히 같은
# 세 경로를, 정확히 같은 순서로 훑는다 — 그 함수 옆에 ndhmd4tex/resources
# 폴더가 이미 있을 테니, 그 옆에 나란히 ndhmd4tex/config 폴더를 두는
# 것이 자연스럽다는 취지다. ndhmd4tex.py처럼 "OS별로 하나만 본다"가
# 아니라 **셋 다 순서대로 훑는다** — 설정을 여러 기계에서 동기화해 쓰는
# 경우(예: Dropbox/iCloud로 홈 폴더 일부를 동기화)를 감안한 것으로,
# resource_dirs()의 설계를 그대로 따른 것이다. 존재하지 않는 경로는
# 그냥 건너뛰므로 잃는 것이 없다.
_CONFIG_CANDIDATES = [
    ("Library", "ndhmd4tex", "config"),
    ("ndhmd4tex", "config"),
    (".config", "ndhmd4tex", "config"),
]


def find_config_file():
    """ndhmdsync.ini 를 세 후보 폴더에서 순서대로 찾는다.

    실제로 파일이 존재하는 첫 폴더의 것을 쓴다(resource_dirs()와 달리
    "발견된 모든 폴더의 목록"이 아니라 "쓸 파일 하나"가 필요하므로).
    아무 데도 없으면 None.
    """
    home = Path.home()
    for parts in _CONFIG_CANDIDATES:
        candidate = home.joinpath(*parts, "ndhmdsync.ini")
        if candidate.is_file():
            return candidate
    return None


def load_app_config(verbose=False):
    """설정 파일을 읽어서 ConfigParser 객체를 반환한다.

    interpolation=None 이 반드시 필요하다 — 기본 ConfigParser는 값 안의
    `%`를 자기 보간 문법으로 해석하려 드는데, 우리 값은 정확히
    `%f`/`%l`/`%p` 처럼 `%` 뒤에 한 글자가 오는 placeholder를 쓴다.
    interpolation=None 없이 이런 값을 읽으면 config.read() 시점에
    InterpolationSyntaxError로 죽는다(실측으로 확인한 버그) — 사용자가
    실제로 %f 같은 placeholder를 쓰는 순간 무조건 터지는 셈이라 반드시
    고쳐야 했다.

    설정 파일을 못 찾으면(또는 --verbose 로 확인하고 싶으면) 그 사실을
    stderr에 알린다 — 빈 ConfigParser를 그대로 돌려주므로, 호출부의
    "커스텀 명령이 있으면 그걸 쓰고 없으면 하드코딩 폴백" 로직은 그대로
    작동한다.
    """
    config = configparser.ConfigParser(interpolation=None)
    cfg_path = find_config_file()
    if verbose:
        if cfg_path:
            print(f"[진단] 설정 파일: {cfg_path}", file=sys.stderr)
        else:
            searched = "\n".join(
                f"    {Path.home().joinpath(*parts, 'ndhmdsync.ini')}"
                for parts in _CONFIG_CANDIDATES
            )
            print(f"[진단] 설정 파일을 찾지 못했습니다(하드코딩된 기본값을 씁니다). "
                  f"다음 위치를 확인했습니다:\n{searched}", file=sys.stderr)
    if cfg_path is not None:
        config.read(cfg_path, encoding="utf-8")
    return config


def _shlex_split_no_escape(s):
    """shlex.split() 대신 쓴다. 명령 템플릿 안의 경로가 Windows식
    백슬래시를 쓸 수 있으므로, 백슬래시를 이스케이프 문자로 취급하지
    않도록 shlex 자체의 이스케이프 처리를 끈다(escape="").

    실측으로 확인한 문제: 원래는 `posix=(sys.platform != "win32")`로
    플랫폼에 따라 분기했는데, 어느 쪽도 안전하지 않았다.
      - posix=False: 따옴표 문자 자체를 벗겨내지 않아서, 공백이 있는
        경로(`"C:\\Program Files\\..."`)를 따옴표로 감싸도 결과 토큰에
        따옴표 글자가 그대로 남아 파일을 못 찾는다.
      - posix=True(기본 escape 설정): 따옴표는 정상 처리되지만, 따옴표
        *밖에* 있는 백슬래시를 이스케이프 문자로 먹어버려서(`\\P`가 `P`가
        되는 식) 따옴표 없이 쓴 Windows 경로의 백슬래시가 통째로
        사라지고, 트레일린 백슬래시가 있으면 "닫는 따옴표 없음" 예외로
        아예 죽는다.
    escape=""로 이스케이프 자체를 꺼버리면 두 문제가 한 번에 해결된다 —
    따옴표는 여전히 정상적으로 인식·제거되고(공백 있는 경로를 따옴표로
    감싸면 안전), 백슬래시는 이스케이프 문자가 아니라 그냥 리터럴 문자로
    취급되어 항상 그대로 보존된다. 플랫폼별로 다르게 할 이유가 없어져
    분기 자체를 없앴다.
    """
    lex = shlex.shlex(s, posix=True)
    lex.whitespace_split = True
    lex.escape = ""
    return list(lex)


def parse_custom_command(cmd_template, file_path, line_num, pdf_path=None):
    """설정된 명령어 문자열을 먼저 토큰 단위로 쪼갠 뒤, 그 안의
    플레이스홀더(%f/%l/%p)를 실제 값으로 채운다.

    순서가 중요하다. "먼저 값을 채우고 나중에 쪼개는" 순서로 하면, 실제
    파일 경로 자체에 공백이 들어 있을 때(Windows 사용자 이름에 흔하다 —
    예: C:\\Users\\John Doe\\...) 그 공백이 shlex에 의해 또 다른 토큰
    경계로 오인되어, 원래 하나여야 할 경로 인자가 여러 조각으로 쪼개지는
    버그가 실측으로 확인됐다(예: %f 가 "C:\\Users\\John Doe\\doc.md" 로
    채워진 뒤 공백에서 갈라져 ['C:\\Users\\John', 'Doe\\doc.md'] 가 되어
    버림). 템플릿을 먼저 쪼개면 "이 자리가 인자 하나"라는 경계가 이미
    확정된 뒤에 값을 끼워 넣으므로, 값 안에 무엇이 들어있든 안전하다.
    """
    tokens = _shlex_split_no_escape(cmd_template)
    result = []
    for tok in tokens:
        tok = tok.replace("%f", str(file_path)).replace("%l", str(line_num))
        if pdf_path:
            tok = tok.replace("%p", str(pdf_path))
        result.append(tok)
    return result


# --------------------------------------------------------------------------
# forward search — PDF 뷰어 위치 찾기
# --------------------------------------------------------------------------

_SKIM_DISPLAYLINE = Path("/Applications/Skim.app/Contents/SharedSupport/displayline")
_SUMATRA_CANDIDATES = [
    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
]

def locate_sumatra():
    candidates = list(_SUMATRA_CANDIDATES)
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        candidates.append(str(Path(localappdata) / "SumatraPDF" / "SumatraPDF.exe"))
    for c in candidates:
        if Path(c).is_file():
            return Path(c)
    return None

def locate_skim():
    return _SKIM_DISPLAYLINE if _SKIM_DISPLAYLINE.is_file() else None

def locate_okular():
    found = shutil.which("okular")
    return Path(found) if found else None

def build_forward_command(viewer, tex_file, tex_line, pdf_file, config):
    # 1. 커스텀 커맨드 설정이 있는 경우 최우선 적용
    if config.has_option("PDFVIEW", "command"):
        cmd_template = config.get("PDFVIEW", "command")
        cmd = parse_custom_command(cmd_template, tex_file, tex_line, pdf_file)
        return "custom", cmd

    # 2. 폴백: 기본 하드 코딩 로직
    tex_file, pdf_file = str(tex_file), str(pdf_file)

    if viewer == "sumatra":
        exe = locate_sumatra()
        if exe is None:
            raise SyncLookupError(
                "SumatraPDF.exe 를 찾을 수 없습니다. 다음 위치만 확인합니다"
                "(포터블 설치는 지원하지 않습니다):\n"
                "  C:\\Program Files\\SumatraPDF\\SumatraPDF.exe\n"
                "  C:\\Program Files (x86)\\SumatraPDF\\SumatraPDF.exe\n"
                "  %LOCALAPPDATA%\\SumatraPDF\\SumatraPDF.exe"
            )
        return "sumatra", [
            str(exe), "-reuse-instance", "-forward-search", tex_file,
            str(tex_line), pdf_file,
        ]

    if viewer == "skim":
        exe = locate_skim()
        if exe is None:
            raise SyncLookupError(
                "Skim.app 을 찾을 수 없습니다(/Applications/Skim.app 고정 위치만 "
                "확인합니다). https://skim-app.sourceforge.io 에서 설치하십시오."
            )
        return "skim", [str(exe), str(tex_line), pdf_file, tex_file]

    if viewer == "okular":
        exe = locate_okular()
        if exe is None:
            raise SyncLookupError(
                "okular 실행 파일을 PATH 에서 찾을 수 없습니다. 배포판의 "
                "패키지 관리자로 설치했는지 확인하십시오."
            )
        return "okular", [
            str(exe), "--unique", f"{pdf_file}#src:{tex_line} {tex_file}",
        ]

    raise SyncLookupError(f"알 수 없는 뷰어입니다: {viewer}")


def default_viewer_for_platform():
    if sys.platform == "win32":
        return "sumatra"
    if sys.platform == "darwin":
        return "skim"
    return "okular"


def _popen_detached(cmd):
    """부모 프로세스와의 콘솔 핸들 충돌을 방지하며 자식 프로세스를 독립적으로 띄운다.

    macOS에서는 자식을 띄운 뒤 아주 잠깐(0.3초) 그대로 머무른다. VS Code의
    "터미널"에 직접 명령을 치면 되는데 Tasks로 실행하면(같은 명령, 같은
    코드인데도) 아무 반응이 없는 문제를 실측(log stream으로 잡은 tccd
    로그)으로 추적한 결과가 근거다 — Tasks가 띄우는 셸(bash)은 작업 하나
    끝나면 곧바로 종료되는데, macOS의 TCC 데몬이 "누가 Skim을 제어하려
    했는지" 그 bash 프로세스의 신원(코드 서명 등)을 확인하려는 순간과
    그 bash가 실제로 종료되는 순간이 겹치면, tccd가
    "SecTaskCopySigningIdentifier(): No such process" 류의 오류로 신원
    확인 자체에 실패하고 — 그 결과가 승인도 거부도 아닌 채로 아무 일도
    안 일어나는 것처럼 보인다. 터미널에 직접 치면 그 셸이 계속 살아있는
    대화형 프로세스라 이 경합 자체가 생기지 않는다. 이 지연은 경합
    창(window)을 줄여 줄 뿐 근본적으로 없애지는 못한다 — macOS 자신의
    TCC 내부 타이밍 문제이기 때문이다. Windows/Linux에는 이런 문제가
    없으므로 macOS에서만 적용한다.
    """
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        kwargs["stdin"] = subprocess.DEVNULL
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    proc = subprocess.Popen(cmd, **kwargs)
    if sys.platform == "darwin":
        time.sleep(0.3)
    return proc


def _open_file_with_os_default(path):
    """줄 번호 개념 없이, OS가 그 확장자에 연결해 둔 기본 프로그램으로
    파일을 그냥 연다(Windows라면 보통 메모장 등).

    [TEXEDIT] command 가 설정 파일에 아예 없을 때의 최종 폴백이다 —
    ndhmd4tex.py의 open_pdf()가 PDF에 대해 쓰는 것과 같은 3분기
    (os.startfile / open / xdg-open)를 그대로 가져왔다. open_in_editor()
    의 폴백(VS Code를 못 찾으면 오류)과 다르게, 여기서는 "최소한 뭔가는
    열린다"는 게 더 중요하다고 판단했다 — .tex를 직접 손으로 쓰는
    프로젝트(.nmdsync 없이 .synctex.gz/.synctex만 있는 경우)라면 애초에
    "정확히 그 줄로 이동"이 안 될 걸 각오하고 쓰는 기능이므로, 특정
    에디터가 없다고 아예 실패시키는 것보다 일단 파일이라도 여는 쪽이
    낫다.
    """
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)])
    else:
        subprocess.run(["xdg-open", str(path)])


def open_in_editor(source_file, src_line, config):
    # 1. 커스텀 커맨드 설정이 있는 경우 최우선 적용
    if config.has_option("EDITOR", "command"):
        cmd_template = config.get("EDITOR", "command")
        cmd = parse_custom_command(cmd_template, source_file, src_line)
        try:
            _popen_detached(cmd)
            return True
        except OSError as e:
            print(f"오류: 설정된 에디터 '{cmd[0]}' 실행에 실패했습니다: {e}", file=sys.stderr)
            return False

    # 2. 폴백: 기본 하드 코딩 VS Code 실행 로직
    code_bin = shutil.which("code")
    if not code_bin:
        print(
            "오류: 'code' 명령을 찾을 수 없습니다. VS Code의 셸 명령을 "
            "설치했는지 확인하십시오(명령 팔레트 -> "
            "'Shell Command: Install code command in PATH').",
            file=sys.stderr,
        )
        return False
    try:
        _popen_detached([code_bin, "--goto", f"{source_file}:{src_line}:1"])
        return True
    except OSError as e:
        print(f"오류: '{code_bin}' 실행에 실패했습니다: {e}", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser(
        description="ndhmd4tex.py --syncinfo 가 만든 .nmdsync 로 md<->tex "
                    "줄 번호를 서로 바꾼다. --line 을 주면 역방향(PDF에서 "
                    "받은 tex 줄 -> md 위치, 설정된 에디터를 연다). --md-line 을 "
                    "주면 정방향(에디터의 현재 md 줄 -> PDF 뷰어에서 그 "
                    "위치를 보여준다)."
    )
    ap.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("file", help="역방향: .tex 파일. 정방향: .md 파일")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--line", type=int, metavar="N",
                       help="[역방향] 찾을 tex 줄 번호(1-based)")
    mode.add_argument("--md-line", type=int, metavar="N",
                       help="[정방향] 찾을 md 줄 번호(1-based) — 보통 에디터 변수를 받음")
    ap.add_argument("--sync-file", metavar="파일",
                    help="자동 탐색 대신 .nmdsync 파일을 직접 지정한다")
    ap.add_argument("--tex", metavar="파일",
                    help="[정방향] .tex 파일 경로(기본: md 파일과 같은 이름 .tex)")
    ap.add_argument("--pdf", metavar="파일",
                    help="[정방향] .pdf 파일 경로(기본: md 파일과 같은 이름 .pdf)")
    ap.add_argument("--viewer", choices=["sumatra", "skim", "okular"],
                    help="[정방향] 사용할 PDF 뷰어(기본: 실행 중인 OS로 자동 선택)")
    ap.add_argument("--print", action="store_true", dest="print_only",
                    help="역방향: 에디터를 열지 않고 '파일:줄'만 출력. "
                         "정방향: 뷰어를 열지 않고 '파일:줄'만 출력")
    ap.add_argument("--verbose", action="store_true",
                    help="파일 경로 유추 과정과(정방향) 설정 파일을 어디서 "
                         "찾았는지(양방향)를 stderr에 미리 찍는다")
    args = ap.parse_args()

    if args.md_line is not None:
        _run_forward(args)
    else:
        _run_reverse(args)


def _run_reverse_texonly(args, config, tex_path):
    """.nmdsync 는 없지만 .synctex.gz/.synctex 는 있을 때의 경로 — 이
    문서는 ndhmd4tex.py --syncinfo 로 만들어진 게 아니라, 손으로 쓴
    LaTeX을 곧장(latexmk 등으로) 컴파일한 것으로 본다. SyncTeX 자체는
    -synctex=1 만 주면 markdown과 완전히 무관하게 항상 만들어지므로,
    이 파일의 존재는 "SyncTeX은 켜져 있다"는 것 이상을 보장하지
    않는다 — 그래도 최소한 "markdown 역추적을 시도할 대상 자체가
    아니다"라는 신호로는 충분하다.

    md 역추적은 할 수 없으니, 그 대신 .tex 파일 자체를 그 줄에서 연다.
    [TEXEDIT] command 가 설정돼 있으면 그 명령(%f/%l 치환)으로, 없으면
    OS 기본 프로그램으로 그냥 연다(정확한 줄로는 못 가지만 최소한
    파일은 열린다 — SumatraPDF 등에 이 스크립트를 역방향 검색기로
    한 번 등록해 두면, markdown 기반 문서든 순정 LaTeX 문서든 같은
    설정으로 둘 다 다뤄지길 바라는 경우를 위한 것이다).
    """
    if args.print_only:
        print(f"{tex_path}:{args.line}")
        return

    if config.has_option("TEXEDIT", "command"):
        cmd_template = config.get("TEXEDIT", "command")
        cmd = parse_custom_command(cmd_template, tex_path, args.line)
        try:
            _popen_detached(cmd)
            return
        except OSError as e:
            print(f"오류: 설정된 편집기 '{cmd[0]}' 실행에 실패했습니다: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        _open_file_with_os_default(tex_path)
    except OSError as e:
        print(f"오류: '{tex_path}' 열기에 실패했습니다: {e}", file=sys.stderr)
        sys.exit(1)


def _run_reverse(args):
    config = load_app_config(verbose=args.verbose)
    tex_path = Path(args.file)
    if tex_path.suffix == "":
        # PDF 뷰어(SumatraPDF 등)는 SyncTeX 데이터에 기록된 소스 파일
        # 이름을 그대로 %f 에 채워 이 스크립트를 부른다. 그런데 LaTeX
        # 엔진이 \input{file}처럼 확장자를 생략해서 쓴 경우, SyncTeX도
        # 그 이름을 확장자 없이 그대로 기록하는 경우가 실제로 있다 —
        # 그러면 이 스크립트가 %f 로 받는 args.file 자체가 이미 확장자
        # 없는 채로 들어온다(실측으로 확인된 문제).
        #
        # 확장자가 없으면 뒤이은 모든 처리(.nmdsync/.synctex 존재 확인,
        # [TEXEDIT] 명령의 %f)가 잘못된 이름을 기준으로 돌아간다 —
        # 특히 VS Code의 `--goto 파일:줄:칸` 문법이 이 상황에 취약해서,
        # 실제 파일과 다른 경로로 인식돼 조용히 실패하거나 엉뚱한 새
        # 파일을 만들려 든다. 이 스크립트의 역방향 검색은 애초에 .tex
        # 파일만 다루므로(--help의 file 인자 설명 참고), 확장자가 아예
        # 없을 때만 .tex 로 보정한다 — 이미 다른 확장자(.ltx 등)가
        # 붙어 있으면 원고 작성자가 의도적으로 쓴 것일 수 있으니
        # 건드리지 않는다.
        tex_path = tex_path.with_suffix(".tex")
    sync_path = Path(args.sync_file) if args.sync_file else tex_path.with_suffix(".nmdsync")

    if not sync_path.is_file():
        # .nmdsync 가 없어도, .synctex.gz/.synctex 가 있으면(즉 이 tex이
        # 원래부터 markdown 없이 곧장 컴파일된 것으로 보이면) 조용히
        # 실패하는 대신 .tex 자체를 여는 경로로 넘어간다.
        synctex_gz = tex_path.with_suffix(".synctex.gz")
        synctex_plain = tex_path.with_suffix(".synctex")
        if synctex_gz.is_file() or synctex_plain.is_file():
            _run_reverse_texonly(args, config, tex_path)
            return
        print(
            f"오류: 동기화 정보를 찾을 수 없습니다: {sync_path}\n"
            f"  ndhmd4tex.py 를 --syncinfo 옵션으로 실행했는지 확인하십시오.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        entries = load_syncinfo(sync_path)
        src_file, src_line, exact = find_source_location(entries, args.line)
    except SyncLookupError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)

    if not exact:
        print(
            f"참고: tex {args.line}행을 정확히 담는 구간이 없어 "
            f"가장 가까운 위치로 대신합니다.",
            file=sys.stderr,
        )

    if args.print_only:
        print(f"{src_file}:{src_line}")
        return

    if not open_in_editor(src_file, src_line, config):
        print(f"{src_file}:{src_line}", file=sys.stderr)
        sys.exit(1)


_FRONTMATTER_BLOCK_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
_NDHMAIN_LINE_RE = re.compile(r"^ndhmain:\s*(.+?)\s*$", re.MULTILINE)


def read_ndhmain(md_path):
    """md_path 의 front matter에서 `ndhmain: <파일>` 값을 찾아, 그 파일의
    절대경로를 돌려준다. 없거나, 있어도 자기 자신을 가리키면(identity)
    None을 돌려준다 — 그 경우 md_path 자신이 최상위 문서라는 뜻이므로,
    호출부는 기존처럼 md_path 자체를 기준으로 출력 경로를 유추하면 된다.

    {{포함}}으로 다른 파일에 흡수되는 서브파일은, 자기 자신이 실제로
    어느 최상위 문서의 일부로 컴파일되는지 스스로 알 도리가 없다 — 그
    관계를 아는 것은 오직 그 서브파일을 포함하는 쪽(main.md)뿐이다.
    그래서 서브파일 자신의 front matter에 이 관계를 직접 적어 두는
    방식을 쓴다.

        ---
        ndhmain: main.md
        ---

    ndhmd4tex.py 자신은 이 키를 전혀 안 읽는다({{포함}}될 때 서브파일의
    front matter 전체가 통째로 버려지므로 컴파일에는 아무 영향이 없다,
    KNOWN_META_KEYS 에 이름만 올려 두어 무해한 매크로로 새어나가지
    않게 했을 뿐이다) — 순전히 ndhmdsync.py 가 정방향 검색의 기본 출력
    경로를 유추할 때만 쓰는 힌트다. YAML 파서를 따로 쓰지 않는 이유는
    이 스크립트가 표준 라이브러리만으로 돌아가야 하고, 필요한 것도
    "한 줄짜리 문자열 값 하나"뿐이라 정규식으로 충분하기 때문이다.

    값은 상대경로로 적어도 된다 — main.md 가 서브폴더 안의 파일을
    {{sub/ch1.md}} 로 포함하는 흔한 구성에서, ch1.md 쪽은
    `ndhmain: ../main.md` 처럼 자기 자신을 기준으로 한 상대경로를 쓰면
    된다. 이 함수가 그 경로를 ch1.md **자신이 실제로 있는 폴더**
    기준으로 풀고(md_path.parent 에 이어붙인 뒤 resolve()), 이 정규화가
    ".." 를 알아서 접어 주므로, ndhmdsync.py 를 어느 작업 폴더에서
    실행하든(sub/ 안에서든, 완전히 다른 곳에서든, 절대경로로 부르든)
    항상 main.md 하나로 정확히 찾아간다 — 실측으로 확인했다.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm_m = _FRONTMATTER_BLOCK_RE.match(text)
    if not fm_m:
        return None
    line_m = _NDHMAIN_LINE_RE.search(fm_m.group(1))
    if not line_m:
        return None

    raw = line_m.group(1).strip()
    # YAML 문자열이 따옴표로 감싸져 있을 수 있다 — ndhmain: "main.md" 나
    # ndhmain: 'main.md' 둘 다 흔히 쓰는 표기이므로 벗겨 준다.
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1]
    if not raw:
        return None

    target = Path(raw)
    if not target.is_absolute():
        target = md_path.parent / target
    target = target.resolve()

    if target == md_path.resolve():
        return None  # identity — 자기 자신이 최상위 문서라는 뜻

    return target


def _run_forward(args):
    config = load_app_config(verbose=args.verbose)
    md_path = Path(args.file).resolve()

    # ndhmain: 힌트가 있으면 출력 경로 유추 기준을 그 파일로 바꾼다 —
    # 단, 줄 번호를 찾는 대상은 여전히 md_path(지금 실제로 열려 있는
    # 파일) 그대로다. find_tex_location() 은 .nmdsync 안에서 md_path 와
    # 정확히 같은 절대경로를 가리키는 항목을 찾으므로(포함된 서브파일도
    # 자기 자신의 절대경로로 정확히 기록돼 있다), 이 부분은 건드릴
    # 필요가 없다.
    main_path = read_ndhmain(md_path)
    base_path = main_path if main_path is not None else md_path

    sync_path = Path(args.sync_file) if args.sync_file else base_path.with_suffix(".nmdsync")
    tex_path = Path(args.tex) if args.tex else base_path.with_suffix(".tex")
    pdf_path = Path(args.pdf) if args.pdf else base_path.with_suffix(".pdf")

    if args.verbose:
        ndhmain_line = (
            f"[진단] ndhmain 힌트: {main_path} (출력 경로 유추 기준을 이 파일로 바꿈)\n"
            if main_path is not None else ""
        )
        print(
            f"[진단] 받은 파일: {args.file}\n"
            f"[진단] 절대경로로: {md_path}\n"
            f"{ndhmain_line}"
            f"[진단] 찾는 .nmdsync: {sync_path}\n"
            f"[진단] 찾는 .tex: {tex_path}\n"
            f"[진단] 찾는 .pdf: {pdf_path}\n"
            f"[진단] md 줄 번호: {args.md_line}",
            file=sys.stderr,
        )

    if not sync_path.is_file():
        print(
            f"오류: 동기화 정보를 찾을 수 없습니다: {sync_path}\n"
            f"  ndhmd4tex.py 를 --syncinfo 옵션으로 실행했는지 확인하십시오.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not pdf_path.is_file() and not args.print_only:
        print(f"오류: PDF 파일이 없습니다: {pdf_path}\n"
              f"  먼저 --pdf 계열 옵션으로 컴파일하십시오.", file=sys.stderr)
        sys.exit(1)

    try:
        entries = load_syncinfo(sync_path)
        tex_line, exact = find_tex_location(entries, md_path, args.md_line)
    except SyncLookupError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)

    if not exact:
        print(
            f"참고: md {args.md_line}행을 정확히 담는 구간이 없어 "
            f"가장 가까운 위치로 대신합니다.",
            file=sys.stderr,
        )

    if args.print_only:
        print(f"{tex_path}:{tex_line}")
        return

    viewer = args.viewer or default_viewer_for_platform()
    try:
        _, cmd = build_forward_command(viewer, tex_path, tex_line, pdf_path, config)
    except SyncLookupError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"[진단] 실행할 명령: {cmd}", file=sys.stderr)

    try:
        _popen_detached(cmd)
    except OSError as e:
        print(f"오류: 뷰어/명령 실행에 실패했습니다: {e}", file=sys.stderr)
        sys.exit(1)
    if args.verbose:
        print(
            "[진단] 명령 실행을 마쳤습니다(예외 없음) — 여기까지 왔는데도 "
            "뷰어가 반응하지 않는다면, ndhmdsync.py 문제가 아니라 뷰어나 "
            "OS 쪽 문제일 가능성이 큽니다. macOS라면 Skim에 대한 자동화"
            "(Automation) 권한이 이 터미널을 실행한 앱(예: VS Code)에 "
            "허용돼 있는지 확인해 보십시오(시스템 설정 → 개인정보 보호 및 "
            "보안 → 자동화).",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()