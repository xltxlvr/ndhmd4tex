---
setup: articlelike.nmd
toplevel: chapter
preamble+: |
  \usepackage{minted}
---

# `ndhmd4tex.py` Quick Start {unnumbered}

이 문서는 `ndhmd4tex_dialect_guide.md`(문법 사양서)와 달리, **처음 설치해서 첫 PDF를 뽑아보기까지**만 다룬다. 문법 전체 목록은 사양서를 참고할 것.

- **전제**: TeX Live(2026 계열) 또는 MiKTeX이 이미 설치되어 있어야 한다.
- **Python**: Windows 실행 파일(`.exe`)은 별도의 Python 설치를 요구하지 않지만 macOS 또는 Linux 환경에서는 python3와 PyYAML 모듈 패키지가 필요하다.

---

## 설치하기

설치 과정은 복잡한 설정 없이 스크립트 실행으로 끝난다.

### `ksruncltex` 설치

[이곳](https://nonametex.imweb.me/?bmode=view&idx=170827898&t=board)에서 다운로드받은 zip 파일을 풀어서 `install.bat` 또는 `(sudo) sh ./install.sh`을 실행한다. (끝)

### `ndhmd4tex` 설치

[이곳](https://nonametex.imweb.me/intro/?bmode=view&idx=173124991&t=board)에서 다운로드받은 zip 파일을 풀어서 `install_ndh4md.bat` 또는 `(sudo) sh ./install_ndhmd4tex.sh`을 실행한다. (끝)

---

## 첫 문서 — 헤더 없이 바로 PDF까지

**yaml 헤더는 없어도 된다.** 마크다운만 적으면 된다. `hello.md`:

```markdown
# 안녕, ndhmd4tex

이건 **첫 문서**다. *기울임*도 되고, 각주도 됩니다[^a].

[^a]: 각주 예시.
```

그리고 터미널(또는 명령 프롬프트)에서 다음 한 줄을 실행한다:

```bash
python3 ndhmd4tex.py hello.md --pdflua
```

이걸로 markdown → tex → PDF → 뷰어 열기까지 전부 끝난다. `hello.tex`와 `hello.pdf`가 생기고, 완성된 PDF가 시스템 기본 뷰어로 열린다.

- `--pdflua`(lualatex), `--pdfxe`(xelatex), `--pdf`(pdflatex) 중 하나를 고른다. 한글 문서는 보통 `--pdflua`나 `--pdfxe`를 쓴다(`pdflatex`은 한글 폰트 자동 감지가 약하다).
- 컴파일 없이 `.tex`만 보고 싶으면 옵션 없이 `python3 ndhmd4tex.py hello.md`를 실행한다. `\chapter{안녕, ndhmd4tex}`, `\textbf{첫 문서}`, `\emph{기울임}`, `\footnote{각주 예시.}`로 바뀐 것을 확인할 수 있다.
- 내부적으로 일어나는 일:
  1. `hello.md` → `hello.tex` 변환. 이때 헤더가 없으므로 기본값 설정이 씌워진다.
  2. 컴파일러 래퍼인 `ksruncltex`를 호출해서 실제 컴파일.
  3. 성공하면 `hello.pdf`를 시스템 기본 PDF 뷰어로 자동으로 연다 (macOS `open`, Linux `xdg-open`, Windows는 탐색기 연결 프로그램 그대로).
- 컴파일이 실패하면 터미널에 로그가 그대로 출력되니 거기서 원인을 확인한다. `minted`나 보조파일(`.aux` 등) 꼬임으로 인한 흔한 오류는 `ksruncltex`가 `--fresh` 옵션으로 자동으로 한 번 재시도해준다.

---

## 문서마다 다르게 — front matter

헤더가 없으면 설치 스크립트가 함께 설치한 기본 헤더로 문서를 만든다.
그리고 이 값은 원고 자신의 front matter로 덮어쓸 수 있다. `hello.md` 맨 위에 이런 식으로 붙인다.

```yaml
---
title: 첫 문서
author: 홍길동
toplevel: section
preamble+: |
  \usepackage{amsmath,amssymb}
compileoption: --synctex=1
---
```

- `title`, `author` — `\title{}`, `\author{}`로 나간다. 본문에서 `\maketitle`을 적어야 실제로 찍힌다.
- `toplevel: section` — 마크다운 `#`이 `\section`으로 매핑되게 한다. 기본 헤더가 `chapter`로 잡아두었으므로, 짧은 글에는 이렇게 낮춰 쓰면 된다.
- `preamble+:` — 기본 헤더의 프리앰블 **뒤에 덧붙는다**. 그냥 `preamble:`로 적으면 기본 헤더의 것을 **통째로 갈아치우니** 주의할 것. 패키지 몇 개만 보태는 경우라면 거의 언제나 `preamble+:`가 맞다.
- `compileoption: --synctex=1` — `ksruncltex`를 호출할 때 그대로 추가 인자로 붙는다. 컴파일 엔진은 `--pdflua` 같은 CLI 옵션이 정하므로 여기에는 적지 않는다. synctex을 켜두면 지원하는 PDF 뷰어(Skim, SumatraPDF, Okular 등)에서 에디터와 PDF 사이를 클릭 한 번으로 오갈 수 있다.

`class:`도 여기서 바꿀 수 있지만, 그때는 `classoptions:`와 `toplevel:`도 함께 손봐야 한다. 기본 헤더가 넘기던 클래스 옵션이 그대로 남아 새 클래스와 어긋나기 쉽기 때문이다.

설정이 어디서 왔는지 헷갈리면 이 명령으로 확인한다. 병합된 최종 헤더와, 그것을 어느 파일에서 물려받았는지를 보여준다.

```bash
python3 ndhmd4tex.py hello.md --dump-meta
```

여기까지 되면 문서 작성을 시작할 준비가 끝난 것이다. front matter의 나머지 키는 사양서 2장, 헤더를 여러 문서가 나눠 쓰는 방법은 21장, 문법의 전체 목록은 사양서 전체를 참고할 것.
