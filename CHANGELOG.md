# ndhmd4tex 변경 이력

## ndhmd4tex.py 0.22.1, ndhmd2html.py 0.4.0 그대로

- **`external` 의 결과 종류 `math`.** 도구의 출력(숫자나 식)을 `\ensuremath{...}` 로 감싸 수식
  모드로 넣는다. 여러 줄은 한 줄로 잇고, 출력이 비어 있으면 오류로 멈춘다. ndhmd2html 에서는
  `\(...\)` 인라인 수식이 된다.

## ndhmd4tex.py 0.22.0, ndhmd2html.py 0.4.0

- **```` ```external ```` 블록: 외부 도구의 결과를 그림이나 글로 받아온다.**
  `` ```external tool=lilypond, caption="…", label=…, width=… `` 처럼 쓴다.
  - 도구는 mapping 의 `external:` 에 등록한 것만 이름으로 부를 수 있다(원고에 명령줄을 쓰지 않는다).
  - 실행은 `--external` 을 줘야 한다. 결과는 원고 폴더의 `_external/` 에 내용 해시로 캐시되고,
    캐시에 있으면 옵션 없이도 쓴다.
  - 그림 결과(pdf png svg jpg eps)는 `![캡션](…){속성}` 으로 바뀌어 기존 그림 경로를 탄다.
    글 결과는 `text`(그대로 보이는 블록) / `markdown`(다시 변환) / `tex`(raw).
  - 실패(미등록 도구, 실행 파일 없음, 0 아닌 종료, 시간 초과, 결과 파일 없음)하면 변환을 멈춘다.
  - `--syncinfo` 줄 대응, `showexam` 안에서의 실행, 더 긴 펜스 안의 예제는 실행하지 않는 것을 확인했다.
  - graphviz(`dot`)와 python 으로 시험했다. lilypond 와 `crop`(pdfcrop)은 개발 환경에 없어
    실행해 보지 못했다.
- **ndhmd2html**: 같은 규칙·같은 캐시로 `external` 을 처리한다. PDF 그림은 같은 이름의 PNG 를
  옆에 만들어 쓴다(도구의 `web` 명령 → PySide6 QtPdf → pdftocairo → pdftoppm → gs).
  QtPdf 경로와 pdftocairo 경로를 각각 확인했다.
- **ndhmd2html 버그 수정**: 그림 속성의 `width=0.5\linewidth` 가 HTML 에 반영되지 않던 문제
  (`\linewidth` 가 매크로 단계에서 먼저 사라졌다).

## ndhmd4tex.py 0.21.3, ndhmd2html.py 0.3.2

- **버그 수정: polyglossia 의 아랍어 RTL 블록이 `\begin{arabic}` 으로 나가 컴파일이 실패했다.**
  `\arabic` 은 LaTeX 의 카운터 출력 명령이라 polyglossia 는 아랍어 환경 이름을 `Arabic` 으로
  둔다(gloss-arabic.ldf 의 `envname=Arabic`). 이제 `\begin{Arabic}` 으로 내며, 원고에서는
  `:::{arabic}` 과 `:::{Arabic}` 을 모두 받는다. 이름이 다른 언어는 polyglossia 전체에서
  아랍어 하나뿐임을 gloss 파일에서 확인했다. babel 쪽(`otherlanguage`)은 영향이 없다.
- ndhmd2html 도 `:::{Arabic}` 을 RTL 블록으로 알아본다(class 는 `arabic rtl` 로 통일).

## ndhmd4tex.py 0.21.2, ndhmd2html.py 0.3.1

- **RTL 블록과 인라인 구간을 구분한다.** 0.21.1 까지는 `:::{hebrew}` 안에서도 줄마다
  `\texthebrew{}` 를 다시 씌웠다. 이제
  - `:::{hebrew}` 처럼 RTL 언어 이름을 가진 환경은 RTL 블록이고, 안쪽(겹친 `verse` 등 포함)의
    그 문자는 감싸지 않는다. 감싼 구간이 없어도 프리앰블의 언어·글꼴 선언은 들어간다.
  - RTL 글자만 있는 독립 문단(`detect: auto`)은 인라인이 아니라 RTL 블록으로 낸다. 한글·라틴
    글자가 하나라도 있으면 보통 문단이다.
  - 블록은 polyglossia 에서 `\begin{hebrew}`, babel 에서 `\begin{otherlanguage}{hebrew}`.
    primitive 는 예전대로 둔다(블록 없음, 경고).
  - 블록 안의 LTR 구간은 자동으로 감싸지 않는다. 필요하면 원고에서 `\LR{...}` 로 감싼다.
  - babel 쪽은 XeTeX 로 조판해 운문과 여러 줄 문단이 오른쪽 기준으로 놓이는 것을 확인했다.
    polyglossia 쪽은 개발 환경에서 조판하지 못했다. `--syncinfo` 줄 대응은 확인했다.
- **ndhmd2html**: RTL 블록은 `<div class="hebrew rtl" lang="he" dir="rtl">`, RTL 문단은
  `<p lang="he" dir="rtl">` 로 내고 그 안의 구간은 다시 감싸지 않는다.

## ndhmd4tex.py 0.21.1, ndhmd2html.py 0.3.0 그대로

- `sample_mapping.yaml`: front matter 전용 키 목록에 `RTLtypeset`, `mmdoption`,
  `baseheaderlevel`, `latexmkoption`, `graphicspath`, `maketitle`, `tocloft` 를 보태고,
  ndhmd2html 용 `html:` 키(macros, environments)의 예시를 넣었다.
- **`RTLtypeset`: 사용자가 직접 선언한 것은 건드리지 않는다.** 0.21.0 은 `\usepackage{polyglossia}` /
  `\usepackage[bidi=...]{babel}` 과 언어 선언을 무조건 넣었다. babel 을 다른 옵션으로 이미 불렀으면
  option clash 가 나고, `\babelfont` 는 사용자가 정한 글꼴을 덮어썼다. 이제 패키지는
  `\IfPackageLoadedTF` 로, 언어는 `\texthebrew` / `\extrashebrew` 가 정의됐는지로 판단해 건너뛴다.
  babel 을 직접 부르고 히브리어 글꼴을 따로 준 문서로 조판해, 그 글꼴이 유지되는 것을 확인했다.

## ndhmd4tex.py 0.21.0, ndhmd2html.py 0.3.0

- **`RTLtypeset`: 오른쪽에서 왼쪽으로 쓰는 문자.** 한국어·영어 본문에 섞인 히브리·아랍·시리아
  문자 구간을 찾아 한 덩어리로 감싸고, 필요한 줄을 프리앰블 맨 끝에 넣는다. 원고에 RTL
  구간이 없으면 아무것도 하지 않는다(가이드 두 권의 출력이 버전 줄 외에 같음을 확인).
  - `method`: `polyglossia`(기본, `\texthebrew{}`) / `babel`(`\foreignlanguage{}`) /
    `primitive`(패키지 없이 `\beginR..\endR` 또는 `\textdir TRT`) / `custom`(template) / `none`.
  - `detect`: `auto`(기본, 문자 범위로 자동 인식) / `markup`(`markup: "{RL:%s}"` 로 표기한 것만).
  - 글꼴은 `font:`(기본 FreeSerif)와 문자별 `hebrew: {font:, lang:}` 로 정한다. `preamble:` 에
    `\hebrewfont` 가 이미 있으면 그것을 쓴다.
  - 구간 뒤의 숫자는 구간에 포함한다(유니코드 양방향 규칙). 방향 제어 문자는 지운다.
  - `--syncinfo` 의 줄 대응은 넣은 프리앰블 줄까지 계산한다. `--body-only` 는 필요한 줄을 알린다.
  - `polyglossia` 는 oblivoir + XeTeX/LuaTeX 에서 인라인 RTL 이 바르게 나오는 것을 확인했다.
    `primitive`·`babel` 은 XeTeX + fontspec(article)에서 확인했고 LuaTeX·oblivoir 조합은 미확인.
  - `\DocumentMetadata` 없는 문서에서 `\UseMathForPositioningText` 미정의 오류가 나면(bidi 추정)
    `preamble:` 에 `\providecommand\UseMathForPositioningText{}` 를 넣는다.
- **ndhmd2html**: 같은 인식 규칙으로 `<span class="rtl" lang="he" dir="rtl">` 를 낸다.
- **ndhmd2html 버그 수정**: 인라인 각주 `^[...]` 나 그림 캡션 안의 코드 스팬·수식이 깨진
  표지 문자로 나가던 문제(따로 보관하는 HTML 이 바깥 복원을 받지 못했다).

## ndhmd2html.py 0.2.0, ndhmd4tex.py 0.20.6 그대로

- **딸림 스타일시트 `<출력이름>_simple.css`.** 변환할 때 출력 파일 옆에 만들고 HTML 에서
  연결한다. 꾸밈을 최소로 한 출발점으로, 도구가 내는 class 가 모두 설명과 함께 적혀 있고
  그 문서에만 나오는 class(환경 이름, `tex-매크로`, extra_inline 규칙 이름)는 빈 규칙으로
  들어간다. 이미 있는 파일은 덮어쓰지 않으며, 문서에 새 class 가 생기면 그것만 끝에 빈
  규칙으로 덧붙인다. `--no-simple-css` 로 끈다. `--css` 로 준 파일은 이 뒤에 연결된다.

## ndhmd2html.py 0.1.0 (새 도구), ndhmd4tex.py 0.20.6 그대로

- **`ndhmd2html.py`: ndhmd 원고를 HTML 로.** EPUB 으로 가는 준비 단계다. ndhmd4tex.py 를
  고치지 않고 옆에서 불러 쓰므로(front matter·setup·`{{포함}}`·주석·블록 분할·표 해석)
  두 도구가 원고를 같게 읽는다. `python3 ndhmd2html.py 원고.md [--xhtml] [--toc] [--css 파일]`.
- 조판 전용 마크업(리스트 `{!...}`, 그림 place/align/wrapspec, 표 env/rowhead, 환경 raw=,
  `\vspace` 등)은 무시한다. `||` 는 두 평문단을 한 `<p>` 로 잇는 데만 쓴다.
- `:::{환경}` 은 quote/quotation/center/table/figure/verse/hverse/thebibliography 만 표준
  HTML 로 옮기고, 나머지는 `<div class="환경이름" data-키="값">` 으로 식별만 가능하게 낸다.
- raw LaTeX(```tex, `{{tex:파일}}`, tabular/tblr, `lines: raw`)은 생략하고 개수를 알린다
  (`--keep-raw`). 수식은 원문 그대로 내보내 MathJax 가 읽는다.
- 출력은 XML 로도 올바르고 id 는 XML 이름 규칙에 맞춘다(`fig:one` -> `fig-one`).
  가이드 두 권과 예제 원고에서 중복 id·끊긴 링크·문단 속 블록 요소가 없음을 확인했다.
- 상호참조(`[#라벨]` `[F:]` `[T:]` `[title:]` `[C:]` `[@키]`), 각주 종류, 조사 매크로,
  tagged reference, grid 표(병합 셀), showexam, Beamer 프레임을 다룬다. 자세한 규칙과
  내보내는 class 목록은 `ndhmd2html.py` 맨 앞의 설명에 있다.

## ndhmd4tex.py 0.20.6, ndhmdsync.py 0.5.6 그대로

- **버그 수정: 주석 `<!-- ... -->` 안의 `{{파일}}`이 유효했다.** 트랜스클루전은 주석이
  지워지기 전에 풀렸기 때문에 (1) 주석으로 꺼 둔 `{{없는파일.md}}`가 변환을 오류로
  멈추게 하고, (2) 포함된 파일 속의 `-->`가 주석을 일찍 닫아 뒷부분이 본문으로 새고,
  (3) 순환·깊이 검사도 주석 속 포함에 걸렸다. 이제 주석 안의 `{{...}}`는 읽지도 치환하지도
  않는다(한 줄에 섞여 있으면 주석 바깥 것만). `--syncinfo`용 추적판(resolve_includes_tracked)과
  `--lint`의 포함 검사도 같은 규칙을 따른다. 코드 펜스 안의 `<!--`는 주석으로 치지 않으며,
  닫히지 않은 `<!--`는 주석이 아니다(변환기의 COMMENT_RE와 같은 규칙).

## ndhmd4tex.py 0.20.5, ndhmdsync.py 0.5.6 그대로

- **`tilde: wavedash`.** 문서의 `~`를 언제나 wavedash로만 쓰는 모드. `wavedash:`로 정한
  문자가 있으면 그것, 없으면 `\textasciitilde{}`로 통일한다(`\~`도 같다). `^`와는
  무관하게 latex 모드와 같다. `~~취소선~~`은 먼저 처리되고, 코드 스팬·수식·`\매크로`는
  그대로다. 다른 모드의 출력은 달라지지 않는다(가이드 두 권을 0.20.3과 비교해 확인).

## ndhmd4tex.py 0.20.4, ndhmdsync.py 0.5.6 그대로

- **`quotes` 매핑 키.** 직선 따옴표를 바꿀 결과 문자를 고른다. `tex`(기본, 지금까지의
  ``..'' `..'), `unicode`(U+201C/201D, U+2018/2019), 4글자(큰따옴표 여닫이 + 작은따옴표
  여닫이), 2글자(큰따옴표만 바꾸고 작은따옴표는 tex 그대로), 같은 길이의 리스트.
  여는/닫는 판정, `\"`·`\'` 이스케이프, 코드·수식 보호는 그대로이고 바뀌는 것은 결과
  문자뿐이며 그 문자는 뒤 단계가 건드리지 못하게 보호된다. 잘못된 값은 경고 후 `tex`.
  기본값에서는 출력이 바뀌지 않는다(가이드 두 권을 0.20.3과 비교해 확인).

## ndhmd4tex.py 0.20.3, ndhmdsync.py 0.5.6 그대로

- **`--mmd` 버그 수정.** 본문에 `\begin{document}`가 verbatim 예제로 들어 있는 글(LaTeX
  설명서)에서, mmd 출력을 "완성 문서"로 오인해 그 지점 앞뒤를 잘라내던 문제. 이제
  출력의 첫 의미 있는 줄이 `\documentclass`/`\input`일 때만 완성 문서로 본다.
  실제 mmd 6.8.0 출력(1567줄)으로 재현하여 본문이 빠짐없이 나오는 것을 확인했다.
- 본문 맨 앞이 `---`로 감싼 mmd 메타데이터 블록일 때도 `Base Header Level`을
  찾아 처리한다(front matter YAML이 깨져 본문으로 흘러든 경우 포함).

## ndhmd4tex.py 0.20.2, ndhmdsync.py 0.5.6 그대로

- **`--mmd` (`--multimarkdown`): 본문 변환을 MultiMarkdown에 맡긴다.** `--pandoc`과
  같은 틀로, front matter와 `{{파일}}`은 이쪽이 처리하고 본문만
  `multimarkdown -t latex --snippet`에 넘긴다. `mmdoption:` 키와 CLI 인자를
  지원하고 형식을 바꾸는 옵션은 경고 후 버린다. `.tex` 출처 주석에
  `with multimarkdown syntax`가 붙는다.
- 헤딩 단계: front matter의 `toplevel` > `baseheaderlevel` > 본문 메타데이터 블록의
  `Base Header Level` 순. `toplevel`→N 변환은 mmd에게 `# ~ ######`을 실제로 돌려
  보는 탐침으로 보정한다(실패 시 part=1/chapter=2/section=3). 본문의 기존
  메타데이터 블록은 새 블록을 얹지 않고 그 안에서 고친다.
- mmd의 Title/Author/Date는 읽지 않는다(mmd는 `---` 없이 메타데이터를 찾으므로
  front matter와 구분할 수 없다). `{{TOC}}`는 트랜스클루전에서 제외한다.
- **실제 mmd로는 아직 검증하지 못했다**(개발 환경에 mmd 없음). 가짜 mmd로 인자
  조립·필터·메타데이터 병합·탐침 보정·오류 처리를 시험했다.

## ndhmd4tex.py 0.20.1, ndhmdsync.py 0.5.6 그대로

- **showexam 위아래 배치.** 펜스 줄에 `layout=stack`을 쓰면 원문 상자를 본문
  전체 폭으로 놓고 그 아래에 결과를 잇는다(둘 사이는 `sep=rule`의 가는 선,
  `space`/`none`/LaTeX 코드도 가능). minipage를 쓰지 않아 **쪽을 넘어 이어진다**.
  `layout=auto`는 원문에서 가장 긴 줄의 표시 폭이 `stack_width`(기본 36)를
  넘으면 stack으로 간다. mapping의 `showexam:`에 `layout`, `stack_width`, `sep`,
  `stack_template`이 새로 생겼다. 기본값은 `side`라 기존 출력은 그대로다.
  stack에서 `ratio`/`gap`/`align`을 쓰면 경고하고 무시한다.

## ndhmd4tex.py 0.20.0, ndhmdsync.py 0.5.6 그대로

- **pandoc grid table 지원.** `+---+---+` 꼴의 표를 읽는다. 행·열 병합
  (`\SetCell[r=,c=]`), 여러 줄 셀(줄은 공백으로, 빈 줄은 `\par`), 여러 줄
  머리글(`=` 줄 위쪽), 바닥글(두 번째 `=` 줄), 머리글 구분선의 콜론 정렬을
  지원한다. booktabs 세 줄만 긋고 머리글 안의 부분 구분선은 `\cmidrule`로
  옮긴다. 열 너비는 **자연 너비**가 기본이고 파이프 표와 같은 `tablewrap`이
  적용된다. 표 뒤 속성 줄에 `widths=dash`를 쓰면 pandoc처럼 대시 수 비율의
  `X` 열이 된다. `{env=long, caption=, label=, rowhead=}` 속성 줄은 파이프
  표와 같고 `rowhead` 기본값은 머리글 줄 수다.
- **열 경계는 화면 칸 기준**(한글 2칸). 해석이 안 되면 문자 번호 기준으로도
  한 번 읽는다. 셀 안에는 평문·인라인 서식만(블록 요소는 아직 안 됨).
- 해석할 수 없는 grid 표(모서리·`|` 어긋남)는 `--lint` 오류, 변환 시에는
  경고 후 예전처럼 문단으로 처리한다. 지금까지는 이런 표가 조용히 문단으로
  뭉개지고 lint도 침묵했다.
- 내부: 표의 여는 줄 조립을 `_table_begin()`으로 뽑아 파이프 표와 공유한다
  (파이프 표 출력은 변하지 않음을 확인). 가이드 14.1절에 반영.

## ndhmd4tex.py 0.19.5, ndhmdsync.py 0.5.6 그대로

- **`||` 앞에 빈 줄이 있으면 `\\`로 행 나눔.** 앞뒤가 모두 평문 문단일 때,
  `||` 앞에 빈 줄이 없으면 지금처럼 `%`로 이어 붙이고, 있으면 `%` 대신 `\\`를
  넣는다(`문장\\`을 손으로 쓰지 않고 쓰기 위한 것). `||` 뒤의 빈 줄은 뜻이
  없다. 이웃이 문단이 아니면(리스트·인용·헤딩 등) 빈 줄이 있어도 `\\` 없이
  그냥 이어진다. 뒤 문단이 `[`나 `*`로 시작하면 `\\{}`로 선택 인자 오인을
  막는다. 0.19.4의 "`||` 앞뒤 빈 줄은 같은 뜻"은 이 변경으로 대체됐다.
  가이드 4.1절에 반영.

## ndhmd4tex.py 0.19.4, ndhmdsync.py 0.5.6 그대로

- **`||` — 문단을 나누지 않고 이어 붙이기.** `||`만 있는 줄은 구조상 빈 줄과
  같이 앞뒤 블록을 갈라 주지만(그래서 `||` 바로 뒤의 `+ 항목`이 빈 줄 없이도
  리스트로 인식된다), 출력에서는 빈 줄 없이 줄바꿈만 둔다. 조사로 시작하는
  문단이나 목록·수식 뒤의 이어지는 문단을 `\noindent` 없이 들여쓰기 없이 잇는
  용도다. 앞뒤가 모두 평문 문단이면 앞 문단 끝에 `%`를 붙여 `''라고`가
  `'' 라고`로 벌어지지 않게 한다(공백이 들어가는 변형은 없다). 앞뒤의 빈
  줄은 있어도 같은 뜻이다. `:::` 환경 안에서도 되고, 코드 펜스 안은 글자
  그대로다. `--lint`는 문서 맨 처음·끝의 `||`와 연달아 나온 `||`를 경고하고,
  `||`를 블록 경계로 보아 `평문단 ⏎ || ⏎ + 항목`을 오탐하지 않는다.
  `--syncinfo` 유무와 무관하게 `.tex`가 같고 tex↔md 매핑도 맞는 것을
  확인했다. 가이드 4.1절에 반영.

## ndhmd4tex.py 0.19.3, ndhmdsync.py 0.5.6 그대로

- **각주의 종류 — mapping `notes`와 꼬리표.** `^[…]{A}`, `[^id]{B}`처럼 각주
  바로 뒤 `{이름}`으로 종류를 고른다. 기본 등록: `default`(`\footnote`),
  `side`(`\sidefootnote`), `page`(`\pagenote`), `sidepar`, `sidebar`,
  `verb`(`\verbfootnote`); `\footnoteA` 등은 mapping `notes:`에 더한다.
  템플릿은 `%(text)s`와 `%(opt)s`(번호 지정) 사용, 예전 `%s`도 허용.
  `{A, opt=3}` → `\footnoteA[3]{…}`.
- **기호 각주 `{sym}` / `{sym=N}`.** `\fnsymbol` 기호를 일회성으로 쓴다.
  `{\renewcommand{\thefootnote}{\fnsymbol{footnote}}\footnote[N]{…}}`로 나가고,
  번호를 지정한 `\footnote[N]`은 카운터를 올리지 않으므로 일반 번호에 영향이
  없다(article/memoir/hyperref에서 컴파일 확인). 자동 번호는 문서 순서대로,
  9 초과는 경고.
- 등록되지 않은 `{이름}`은 꼬리표가 아니므로 경고(변환 시점; lint는 mapping을
  모른다) 후 본문에 그대로 남는다. 꼬리표가 없는 각주의 출력은 달라지지 않는다.
- **`\verb|…|` 구간은 본문 어디서나 그대로 통과.** 예전에는 구분자 안의
  `_`, `#`가 이스케이프되어 `\verb`가 망가졌다.
- 가이드 16장에 반영.

## ndhmd4tex.py 0.19.2, ndhmdsync.py 0.5.6 그대로

- **mapping 키 `tilde`: `~`/`^` 방언 선택.** `latex`(기본, 지금까지의
  동작) | `pandoc` | `multimarkdown`(`mmd`). pandoc은 `~`를
  `\textasciitilde{}`로, 안에 공백 없는 `~x~`/`^x^`를 아래/위첨자로.
  multimarkdown은 거기에 더해 `a~b`→`a\textsubscript{b}`, `a^b`→
  `a\textsuperscript{b}`, 뒤에 글자 없는 `~`→`\ensuremath{\sim}`.
  `~~취소선~~`, `^^방점^^`, `^[각주]`, 코드·수식·매크로(인자 포함)는 먼저
  보호되므로 충돌 없음. `\~`는 모든 모드에서 wavedash. `--pandoc`에서는
  무시. 기본값에서 출력이 0.19.1과 동일함을 확인(`--syncinfo` 포함). 가이드
  7.2절에 반영.

## ndhmd4tex.py 0.19.1, ndhmdsync.py 0.5.6 그대로

- **생성된 `.tex` 첫 줄에 출처 주석.** `% converted from ndhmd by ndhmd4tex
  version 0.19.1`. `--pandoc`으로 변환했으면 끝에 ` with pandoc syntax`가
  붙는다. 날짜·원본 경로는 넣지 않아 같은 입력이 늘 같은 출력을
  낸다. `\DocumentMetadata`보다도 앞이지만 주석이라 영향 없다. `--default
  NONE`(body-only)에는 붙이지 않는다. 헤더 함수를 sync가 공유하므로 줄
  번호 매핑은 자동으로 맞고(확인함), `--syncinfo` 유무와 무관하게 `.tex`는
  동일하다. 가이드 2장에 반영.

## ndhmd4tex.py 0.19.0, ndhmdsync.py 0.5.6 그대로

- **front matter `date:` 처리 변경.** 키가 **없으면** `\date`를 내보내지
  않는다(예전에는 `\date{\today}`를 내보냈다 — 클래스 기본 `\date`가 어차피
  오늘 날짜라 조판 결과는 같다). 키는 있는데 값이 비어 있으면(`date:` 또는
  `date: ""`, 공백뿐인 값 포함) `\date{}`를 내보내 날짜를 지운다. 값이 있으면
  전처럼 `\date{값}`. `setup:` 상속에서 부모가 준 날짜를 자식이 `date:`로 비워
  지우는 것도 된다. 헤더 줄 수가 달라지는 것은 sync가 같은 함수를 공유해
  자동으로 맞는다(`--syncinfo` 유무와 무관하게 `.tex` 동일 확인). 가이드 2장에
  반영.

## ndhmd4tex.py 0.18.1, ndhmdsync.py 0.5.6 그대로

- **`--lint`: 중괄호형 설명 리스트(`{용어} ::  설명`)에는 "공백으로 둘러싼
  `::`" 경고를 내지 않음.** 이 경고는 산문에 우연히 ` :: `가 들어가 맨 표기
  (`용어 :: 설명`)로 오인될 때를 위한 것인데, 중괄호형은 줄 머리의 `{..}`와
  `::` 뒤 공백 둘 이상을 요구하는 명시적 문법이라 오인 여지가 없다. 맨 표기와
  산문 속 `::`에는 전과 같이 경고한다. 변환 결과는 바뀌지 않는다.

## ndhmd4tex.py 0.18.0, ndhmdsync.py 0.5.6 그대로

- **파이프 표 속성 줄과 `longtblr` 출력.** 마지막 행 바로 다음 줄(빈 줄 없이)의
  `{env=long, caption="…", label=…, rowhead=…}`가 그 표의 속성이 된다.
  `env=long`(또는 `longtblr`)이면 `\begin{longtblr}[caption={…},label={…}]
  {colspec={…},rowhead=1}`로 내보낸다 — 쪽을 넘어 이어지는 표, 머리글 행 쪽마다
  반복(`rowhead=0`으로 끔), 캡션과 `[#라벨]` 참조가 float 래퍼 없이 된다.
  `tblr`에 `caption`/`label`을 주면 경고 후 무시, 알 수 없는 키도 경고.
  예전에는 이 줄이 표의 한 행으로 먹혀 `\{env=...\}` 쓰레기 행이 되었으므로
  기존 문서와 충돌하지 않는다. `tablewrap`(X 열)과 같이 동작하고 `--syncinfo`
  유무와 무관하게 `.tex` 동일. 실제 컴파일로 쪽 나눔·머리글 반복·"(Continued)"
  캡션·`\ref`까지 확인. 가이드 14장에 반영.

## ndhmd4tex.py 0.17.1, ndhmdsync.py 0.5.6 그대로

- **`rawopt` 값이 `[`로 시작하지 않으면 자동으로 `[…]`로 감쌈.**
  `[@fake]{rawopt="p.~3"}`가 `\cite` 뒤에 `p.~3`이 그대로 붙어
  `\citep.~3{fake}`라는 깨진 출력이 되던 것을 `\cite[p.~3]{fake}`로 고쳤다.
  `[`로 시작하는 값(`[see][p.~23]` 포함)은 이전처럼 원문 그대로.
  값이 비면 선택 인자 없는 평범한 인용. 가이드 16장에 반영.

## ndhmd4tex.py 0.17.0, ndhmdsync.py 0.5.6 그대로

- **인용의 선택 인자: `[@키]{rawopt="…"}`.** `[@Allen04]{rawopt="[see][p.~23]"}`
  → `\cite[see][p.~23]{Allen04}`, `{rawopt="[p.~50]"}` → `\cite[p.~50]{Allen04}`.
  값을 해석하지 않고 **원문 그대로** 명령과 `{키}` 사이에 끼운다(따옴표는
  선택, 따옴표 안의 `]`/`}` 허용). 모든 refcite 프리픽스(`@t:`, `@p:` 등)에
  동작하며 템플릿에 `{%s}`가 없으면 경고 후 무시. `{rawopt=`로 시작하지 않는
  중괄호는 건드리지 않는다. 이 형태를 링크·그림 참조보다 **앞서** 처리하는
  것이 핵심이었다 — `[see][p.~23]`이 `[text][label]` 링크 참조와 모양이
  같아 뒤에서는 미정의 라벨로 가로채이기 때문이다. natbib로 실제 컴파일해
  `(see Allen, 2004, p. 23)`까지 확인. 가이드 16장(상호참조·인용)에 반영.

## ndhmd4tex.py 0.16.0, ndhmdsync.py 0.5.6 그대로

- **그림 참조에 사용처 속성 추가: `![캡션][라벨]{label=…,width=…}`.**
  지금까지 참조로 넣는 그림의 속성은 정의 줄(`[라벨]: x.png width=…`)에서만
  올 수 있어서, 같은 그림을 여러 곳에 쓰면 `label=`도 공유되어 `\label`이
  중복됐다. 이제 `]` 바로 뒤의 `{…}`(`![캡션](x){…}`와 같은 규칙, 띄우면
  본문)가 그 인스턴스만의 값이고, 정의 줄은 공유 기본값이다. 같은 키는
  사용처가 이기며 값을 비우면(`{label=}`) 정의의 속성을 지운다(`align`
  제외). 정의 줄의 `label=`은 호환성을 위해 계속 받되, 그 정의가 두 번
  이상 쓰이는데 사용처가 `label`을 주지 않으면 경고한다. 링크 참조는
  속성이 없어 변화 없음. 가이드 15.6에 반영.

## ndhmd4tex.py 0.15.1, ndhmdsync.py 0.5.6 그대로

- **리스트 옵션은 `{!…}`일 때만 옵션.** 마커 바로 뒤의 `{…}`를 `!` 없이도
  리스트 옵션(`\begin{enumerate}[…]`)으로 소비하던 것을 고쳤다. 이제
  `1. {!\quad(1),\oblivoirlist} 항목`처럼 느낌표로 시작할 때만 옵션이고,
  `!` 없는 `{…}`는 항목 본문의 일부다(다른 본문 속 중괄호처럼 글자 그대로
  찍힘). 불릿/번호/설명 리스트 모두 같다. **호환성 주의:** 옛 문서에서
  `1. {(1)} 항목`처럼 `!` 없이 옵션을 줬다면 `{!(1)}`로 고쳐야 한다.

## ndhmd4tex.py 0.15.0, ndhmdsync.py 0.5.6 그대로

- **`wavedash` (mapping 키): `\~`를 물결표로.** `default`(기본값)면 `~`와
  `\~`를 둘 다 LaTeX에 맡기는 옛 동작 그대로다. 다른 값이면 `~`는 묶음빈칸
  (nobreak space) 그대로, `\~`만 그 값으로 바뀐다. 값의 꼴: 16진
  코드포인트(`FF5E`, `U+301C`, 정수로 읽힌 `3030`도 16진 자리수로 해석),
  한 글자(`〜`), LaTeX 매크로(`\koreanWaveDash` -> `\koreanWaveDash{}`).
  알아볼 수 없는 값은 경고 후 default. 본문·제목·각주·표 셀에서 동작을
  확인했고, 인라인 코드 스팬 안의 `~`와 front matter 값은 그대로다.
  가이드 7.2와 `sample_mapping.yaml`에 반영.

## ndhmd4tex.py 0.14.1, ndhmdsync.py 0.5.6 그대로

- **`--lint`: 인용(`>`) 안의 "리스트 마커가 문단에 흡수됐습니다" 검사.**
  변환기는 `> `를 떼고 안쪽을 재귀적으로 변환하는데 lint는 인용 블록을
  통째로 "리스트 아닌 문단"으로만 보고 안쪽을 검사하지 않아서, 인용 안에서
  문단 바로 뒤에 붙인 `- 항목`이 경고 없이 한 문단으로 뭉쳤다(인용 밖에서는
  경고됨). 이제 환경/프레임과 같은 방식으로 접두를 떼고 안쪽을 재귀 검사한다
  (중첩 인용 `> >` 포함, 줄 번호 유지). 변환 결과는 바뀌지 않는다.
  경고 문구도 두 원인(마커 앞 빈 줄 없음 / 항목 안 빈 줄)을 모두 말하도록 고침.

## ndhmd4tex.py 0.14.0, ndhmdsync.py 0.5.6 그대로

- **파이프 표의 긴 셀 자동 줄바꿈 (`tablewrap`, mapping 키).** 표의 추정
  폭(한글·CJK 한 글자=2, 그 밖=1, 마크업·링크 주소 제외, 열마다 간격 2.4)이
  `tablewrap`(기본 70 ≈ 한글 35자)을 넘으면, 폭이 16 이상인 열만
  `l/c/r` 대신 `X[정렬,co=폭]`으로 바꿔 그 열 안에서 줄바꿈되게 한다.
  이하인 표는 출력이 이전과 완전히 같다. `0`/`false`로 끈다. 실측: tabularray는
  `X` 열이 하나라도 있으면 내용이 짧아도 표를 `\linewidth` 전체로 늘리므로
  넘칠 표에만 적용하는 것이고, `co=` 계수는 열 폭 비율대로 반영됨을 확인.
  한계: 폭이 큰 열이 없이 짧은 열이 많아 넘치는 표는 해결하지 못한다.
  raw `tblr`/`tabular`는 건드리지 않는다. `--syncinfo` 유무와 무관하게
  `.tex` 동일, 줄 수 불변.

## ndhmd4tex.py 0.13.4, ndhmdsync.py 0.5.6 그대로

- **`--syncinfo`: 앞/뒤에 같은 줄 텍스트가 붙은 여러 줄짜리 보호 구간
  (tblr 등) 뒤로 위치가 계속 어긋나던 버그 수정.** 예: `{\small\begin{tblr}
  … \end{tblr}}`, `\end{tblr} 뒤에 글`, `앞글 <!-- 여러 줄 주석 --> 뒤글`.
  `_line_events_for_full_line_matches()`가 "매치가 그 줄(들)을 통째로
  차지할 때만" 줄 축약 이벤트를 만들었는데, 매치 앞뒤에 텍스트가 남아
  있어도 매치 안에 개행이 있으면 여러 줄이 한 줄로 합쳐지므로 이벤트가
  필요하다. 이벤트가 없으니 합쳐진 줄 수만큼 그 뒤 모든 위치가 밀렸다
  (tblr가 여러 개면 밀림이 누적). 이제 이 경우 `(시작줄, 끝줄, 1)` 이벤트를
  만든다. 또한 `\end{tblr}\begin{tblr}`처럼 한 줄에서 맞물려 구간이
  겹치는 매치는 하나로 합친다. 한 줄 안에서 끝나는 매치는 전과 같이
  이벤트가 없다. `--syncinfo` 유무와 무관하게 `.tex` 출력 동일함을 재확인.

## ndhmd4tex.py 0.13.3, ndhmdsync.py 0.5.6 그대로

- `--nopreview` 추가 — `--pdf`/`--pdfxe`/`--pdflua`/`--latexmk`로 컴파일은
  그대로 하되, 성공 후 시스템 PDF 뷰어를 여는 마지막 단계만 생략한다
  ("PDF를 만들었습니다(뷰어는 열지 않음): …" 안내만 출력, 총 경과시간은
  그대로). `--brief`와 함께 써도 되고, 컴파일 실패 시 동작은 변함없다.
  옵션이 없으면 기존 동작과 동일. 가이드 1장에 반영.

## ndhmd4tex.py 0.13.2, ndhmdsync.py 0.5.6 그대로

- `--dump-meta`/`--dump-mapping` 출력 끝에 각각 `====== end of meta
  =======`/`====== end of mapping =======` 줄을 추가 — 둘을 함께 줘서
  한 번에 볼 때 경계를 한눈에 알아보기 쉽게 함. 가이드 1장에 반영.

## ndhmd4tex.py 0.13.1, ndhmdsync.py 0.5.6 그대로

- **`--syncinfo`에서 `linecomment: true`(라인 코멘트, `mapping.yaml`/
  `mappingrule:` 키) 사용 시 그 지점 이후 모든 줄 번호가 어긋나던
  버그 수정.** `_line_events_for_full_line_matches()`가 "매치 범위
  안의 개행 개수"로 그 매치가 차지한 줄 수를 셌는데, `LINECOMMENT_RE`
  (`^//.*\n?`)는 유일하게 그 줄을 끝내는 개행 문자까지 매치 안에
  삼키는 정규식이라 이 계산이 어긋났다 — 실제로는 두 곳에서 문제가
  겹쳐 있었다: (1) "그 줄의 끝"을 찾을 때 이미 다음 줄 시작인 `m.end()`
  에서 또 다음 개행을 찾아 엉뚱하게 그 다음 줄까지 삼켜서, 애초에
  "이 매치가 그 줄 전체를 차지했다"는 판정 자체가 실패해 **이벤트가
  통째로 안 만들어졌고**, (2) 설령 이벤트가 만들어져도 차지한 줄 수가
  실제보다 하나 많게 계산됐다. `COMMENT_RE`(HTML 주석)/`MATH_ENV_RE`/
  `TABLE_ENV_RE`/`DISPLAY_MATH_RE`는 전부 비개행 문자로 끝나는 매치만
  만들어 이 문제가 없었음을 확인. 이 버그는 라인 코멘트가 있는 위치가
  최상위 파일이든 트랜스클루전된 서브파일이든 동일하게 발생하는
  근본적인 문제였다(트랜스클루전 자체의 결함은 아니었음). 최상위/
  서브파일/연속된 여러 라인 코멘트 각각에서 실측 검증, `--syncinfo`
  유무와 무관하게 `.tex` 출력이 동일함을 diff 0으로 재확인, 실제
  xelatex 컴파일 성공.

## ndhmd4tex.py 0.13.0, ndhmdsync.py 0.5.6 그대로

- **트랜스클루전(`{{파일}}`)이 재귀적으로 해석되도록 변경** — 기존
  "정확히 한 단계만" 제약을 없애고, 포함된 파일 안에 또 `{{서브서브}}`
  가 있어도(그 안에 또 있어도, ...) 계속 파고든다. 상대 경로는 재귀
  깊이와 무관하게 항상 최상위 입력 파일 기준(기존과 동일한 태도).
  - **순환 포함**(자기 자신을 직접 포함하는 것 포함)은 즉시 IncludeError
    로 멈추고 전체 사슬을 보여줌. `convert()`/`resolve_includes_tracked()`
    가 최상위 파일 자신을 처음부터 순환감지 체인에 넣도록 해서(source_path
    매개변수 추가), "A→B→A" 순환이 정확한 사슬로 표시되도록 함(첫
    구현에서는 최상위 파일이 체인에 없어 감지가 한 턴 늦고 메시지도
    부정확했던 걸 자체 검증 중 발견해 수정).
  - **깊이 20단계에서 안전장치로 멈춤**(순환 없어도). 정상적인 원고가
    이 깊이까지 갈 일은 없음 — 순수한 안전망.
  - `--lint`(`_lint_targets`)도 재귀로 확장 — 몇 단계로 쪼개든 서브파일
    전부 린트 대상에 포함(이전엔 2단계 이상 서브파일이 검사망에서
    완전히 빠지는 사각지대였음).
  - `--syncinfo`도 재귀 origin 합성을 정확히 지원(3단계까지 실측
    검증) — `ndhmain:`도 몇 단계에 있는 서브파일이든 그대로 동작함을
    확인(이미 절대경로 매칭 방식이라 별도 수정 불필요했음).
  - `--syncinfo` 유무와 무관하게 `.tex` 출력이 완전히 동일함을 재귀
    2단계/3단계 각각에서 diff 0으로 확인. 실제 xelatex 컴파일까지 성공.
  - 가이드 20장에 "너무 깊은 재귀는 피할 것"(2~3단계 권장) 경고 추가.

## ndhmd4tex.py 0.12.0, ndhmdsync.py 0.5.6 그대로

- **MultiMarkdown식 tagged reference 추가** — 같은 그림/링크를 여러 번
  쓸 때 경로/URL을 한 곳에 정의(`[라벨]: 값`)해 두고 라벨로 재사용.
  `![alt][라벨]`(그림), `[text][라벨]`/`[][라벨]`(링크). 대괄호
  한 겹짜리 shortcut(`[Markdown]` 단독)은 산문의 일반 대괄호 사용과
  구별할 수 없어 의도적으로 배제하고, 대괄호 두 겹(`][` 시퀀스, 일반
  산문에 사실상 안 나타남)만 지원 — `[[용어]]`/`[^id]`/`[#id]` 어느
  것과도 시작 문자가 달라 충돌 없음(각주 네임스페이스는 라벨이
  `^`로 시작하는 걸 부정 전방탐색으로 별도 배제). 그림 참조와 링크
  참조는 같은 라벨 풀을 공유(어느 쪽으로 해석할지는 참조하는 쪽이
  결정, MultiMarkdown과 동일). 정의는 한 줄만 지원(여러 줄 이어쓰기
  없음 — 둘째 줄부터는 조용히 사라지지 않고 평문으로 남아 실수가
  바로 보임). 미정의 라벨 참조는 경고 후 원문 유지. 실제 xelatex
  컴파일까지 검증, 각주/색인/상호참조와의 비충돌 확인, 전체 가이드
  문서 회귀 없음 확인. 자세한 내용은 가이드 15.6절.

## ndhmd4tex.py 0.11.5, ndhmdsync.py 0.5.6 그대로

- **리스트 항목 안 코드펜스 바로 다음에 같은 항목의 글이 이어질 때,
  `\end{verbatim}` 등과 같은 줄에 붙던 버그 수정.** 0.11.0에서
  `render_paragraph()`는 고쳤지만, 리스트 항목은 별도 함수
  `_join_wrapped_lines()`를 쓰고 있어서 그 수정이 반영 안 돼 있었다
  — 같은 로직(블록 레벨 플레이스홀더 줄은 공백 대신 개행)을 적용해
  해결. 최상위 문단과의 일관성도 확인(코드펜스 *앞* 텍스트가 같은
  줄에 붙는 건 원래부터 정상 — catcode 오염은 `\end{...}` *뒤*에만
  해당).
- **[알려진 문제, 이번에는 미수정] 리스트 항목 안 코드펜스가 2단계
  이상 중첩되면 아예 인식되지 않는다.** `_FENCE_OPEN_RE`가 CommonMark
  대로 절대 들여쓰기 0~3칸까지만 코드펜스로 인정하는데, 중첩 리스트는
  필연적으로 4칸을 넘어서 코드펜스 자체가 리터럴 텍스트로 남아버린다.
  1단계 리스트(들여쓰기 2~3칸)는 우연히 괜찮음. 고치려면 "리스트 항목
  콘텐츠 기준 상대 들여쓰기" 판정이 필요한데, extract_code_fences()가
  실행되는 시점엔 리스트 중첩 문맥을 전혀 모르는 구조라 재설계가
  필요함 — 별도로 다룰 것.

## ndhmd4tex.py 0.11.4 그대로, ndhmdsync.py 0.5.6

- **역방향 검색(`--line`)의 대상 `.tex` 파일 경로에 확장자가 없으면
  자동으로 `.tex`를 보정해 붙임.** PDF 뷰어가 SyncTeX 데이터에 기록된
  소스 파일명을 그대로 `%f`에 채워 이 스크립트를 부르는데, LaTeX
  엔진이 `\input{file}`처럼 확장자를 생략해서 쓴 경우 SyncTeX도 그
  이름을 확장자 없이 그대로 기록하는 경우가 실제로 있다는 게 확인됨
  — 특히 VS Code의 `--goto 파일:줄:칸` 문법이 이 상황에 취약해서,
  확장자 없는 경로가 실제 파일과 안 맞아 조용히 실패하거나 엉뚱한 새
  파일을 만들려 든다. `_run_reverse()`에서 `tex_path`가 만들어지는
  지점에 정규화를 추가 — `.nmdsync`/`.synctex` 존재 확인, `[TEXEDIT]`
  의 `%f` 전부 이 정규화된 경로를 쓰게 됨. 이미 다른 확장자(`.ltx` 등)
  가 붙어 있으면 건드리지 않음(확장자가 아예 없을 때만 보정). 기존
  `.tex`/`.nmdsync` 정상 경로 회귀 없음 확인. `ndhmdsync.ini.example`
  에도 반영.

## ndhmd4tex.py 0.11.4 그대로, ndhmdsync.py 0.5.5

- **`ndhmdsync.py`에 `[TEXEDIT]` 섹션 추가.** 역방향 검색(`--line`)에서
  `.nmdsync`를 못 찾았을 때, `.synctex.gz`/`.synctex`가 있으면(즉 이
  문서가 `ndhmd4tex.py`가 아니라 손으로 쓴 LaTeX을 곧장 컴파일한 것으로
  보이면) 조용히 오류로 죽는 대신 `.tex` 파일 자신을 그 줄에서 연다.
  `[TEXEDIT] command`가 설정돼 있으면 그 명령(`%f`/`%l` 치환, 예:
  `texworks -p=%l "%f"`)으로, 없으면 OS가 `.tex`에 연결해 둔 기본
  프로그램으로 그냥 연다(다른 두 섹션과 달리 "하드코딩된 특정
  프로그램" 폴백이 없음 — 최소한 뭔가는 열리는 쪽을 택함). PDF 뷰어의
  역방향 검색 명령을 한 번만 등록해 두면 markdown 기반 문서든 순정
  LaTeX 문서든 같은 설정으로 다뤄짐. 기존 `.nmdsync` 정상 경로는 완전히
  회귀 없이 그대로 동작함을 확인. `ndhmdsync.ini.example`에 예시 추가,
  가이드 1.5절에도 문서화.

## ndhmd4tex.py 0.11.4 (ndhmdsync.py는 0.5.4 그대로)

- **`--dump-mapping` 추가**: `mapping:`/`mappingrule:`/`--config`를 전부
  병합한 최종 매핑 규칙을 YAML로 출력. `--dump-meta`가 보여주는 건
  `mapping:` 값(파일 경로)일 뿐 병합된 내용은 아니었던 것과 다르다 —
  여러 `mapping.yaml`을 나열했을 때 `extra_inline`처럼 이어붙는 키와
  "뒤가 이긴다"는 키가 섞여 있고 `mappingrule:`/`--config`까지
  우선순위대로 얹히므로, 병합 결과를 직접 봐야 확실하다. `--dump-meta`
  와 함께 주면 순서대로(meta 먼저, mapping 나중) 출력하고 종료. 내부
  전용 키(`_image_base` 등)는 안 섞여 나가는 것 확인. 자세한 내용은
  가이드 1장.

## ndhmd4tex.py 0.11.3 (ndhmdsync.py는 0.5.4 그대로)

- **`--lint`가 정상적인 설명 리스트(`{용어}::  설명`) 밑에 들여쓴 하위
  리스트를 "리스트 마커가 문단에 흡수됐다"로 오탐하던 버그 수정.** 1번
  검사(`_check_orphan_list_markers`)가 블록 첫 줄이 리스트인지 판정할
  때 불릿/번호 리스트(`_LINT_MARK_RE`)만 알고 `::` 설명 리스트 문법을
  몰랐던 것이 원인 — `desc_match()`도 함께 확인하도록 고침. 수정 전
  코드로 되돌려 대조 검증(올바른 문법으로 쓴 정상 케이스가 수정 전엔
  오탐, 수정 후엔 통과)까지 마침. 설명 리스트는 각 항목이 독립적인
  `::` 마커로 항상 새 블록을 열기 때문에, 불릿/번호 리스트와 달리
  "마커가 평문에 흡수되는" 유형의 실수 자체가 구조적으로 없다는 것도
  확인.

## ndhmd4tex.py 0.11.2 (ndhmdsync.py는 0.5.4 그대로)

- **`--syncinfo` 심각한 버그 수정**: 0.11.0에서 `:::{환경}`/Beamer
  프레임 뒤 빈 줄 유무에 따라 블록 구분자를 다르게(`\n\n` 또는 `\n`)
  잇도록 `render_blocks()`를 고쳤는데, `--syncinfo` 전용 경로
  (`generate_syncinfo()`/`split_blocks_indexed()`)는 옛날처럼 항상
  `\n\n`으로 고정돼 있어서 두 경로가 어긋났다. 그 결과 **`--syncinfo`를
  켜는 것만으로 같은 원고의 실제 `.tex` 출력(문단 구분 여부)이
  달라지고**, 그 지점 이후 모든 sync 항목의 tex 줄 번호도 한 줄씩
  밀렸다 — {{포함}}으로 여러 파일을 합칠수록 이런 지점이 늘어나 오차가
  누적되므로 트랜스클루전이 있는 문서에서 특히 잘 드러났다(실제로
  보고받은 증상과 일치). `split_blocks_indexed()`에도 `split_blocks()`
  와 같은 had_blank_after 정보를 추가하고, `generate_syncinfo()`의
  블록 조인 로직을 `render_blocks()`와 정확히 같게 맞춰 해결. `--syncinfo`
  유무와 무관하게 `.tex` 출력이 완전히 동일해짐을 확인(diff 0,
  트랜스클루전 포함 문서로도 검증). `ndhmdsync.py`는 `.nmdsync` 포맷
  자체가 안 바뀌어 손댈 필요 없음.

## ndhmd4tex.py 0.11.1 (ndhmdsync.py는 0.5.4 그대로)

- `^^M` 추가 — 소스에 쓰면 생성되는 .tex 파일 자체에 진짜 개행 문자를
  삽입한다(LaTeX에게 줄바꿈을 지시하는 게 아니라 순수하게 소스 레벨의
  개행). `\def\linecommand#1^^M{...}`처럼 그 입력 줄 끝까지를 인자로
  받는 TeX 매크로를 쓰기 위한 것 — 이 방언이 평문의 줄바꿈을 전부
  공백으로 합쳐 버려서 원래 이런 매크로를 쓸 방법이 없었다.
  `^^방점^^`(extra_inline 기본값)과 표기가 비슷하지만 짝이 없어 충돌
  없음. 인라인 코드/코드펜스 안에서는 리터럴로 유지됨. 자세한 내용은
  가이드 18.1절.

## ndhmd4tex.py 0.11.0 (ndhmdsync.py는 0.5.4 그대로)

- **`graphicspath:` front matter 키 추가.** `graphicspath: ["./","figures/"]`
  이면 preamble 맨 끝에 `\IfPackageLoadedTF{graphicx}{}{\usepackage{graphicx}}`
  + `\graphicspath{{./}{figures/}}`를 붙인다. graphicx가 이미 로드돼
  있으면 다시 로드하지 않음. 문자열 하나만 줘도 됨. 자세한 내용은
  가이드 2장.
- **코드펜스 닫는 줄 바로 다음에 빈 줄 없이 이어지는 텍스트가 같은 줄에
  붙어 나오던 버그 수정.** `render_paragraph`가 여러 줄을 무조건 공백
  으로 잇는데, 코드펜스는 블록 레벨에서 이미 "그 줄 하나짜리
  플레이스홀더"로 압축돼 있어 이 규칙에 그대로 걸렸던 것 — 이제 그
  경우는 공백 대신 줄바꿈으로 잇는다. 일부 verbatim류 패키지가
  `\end{...}` 뒤 같은 줄의 내용에까지 catcode 변경을 번지게 하는
  문제를 막는다.
- **`:::{환경}`/Beamer 프레임의 닫는 줄 바로 다음에 빈 줄 없이 이어지는
  텍스트가 무조건 새 문단(빈 줄)으로 찍히던 버그 수정.** 재귀 처리를
  위해 `split_blocks()`가 닫는 줄에서 항상 강제로 블록을 끊는데, 이
  "강제 분리"와 "원문의 진짜 빈 줄"을 구분 못 해서 항상 새 문단으로
  이어붙이고 있었음. 이제 원문에 빈 줄이 없으면 줄바꿈만 하고(한국어
  조판에서 이게 들여쓰기되는 새 문단으로 보이면 곤란하므로), 빈 줄이
  있으면 기존처럼 새 문단으로 찍는다. 자세한 내용은 가이드 10장/17장.

## ndhmd4tex.py 0.10.9 (ndhmdsync.py는 0.5.4 그대로)

- 0.10.8에서 추가한 `--syncinfo` 자동 synctex 옵션의 대시 개수 수정.
  `ksruncltex`(`compileoption:`)는 `--synctex=1`(대시 둘, 기존
  가이드/quickstart 예시와 일치), `latexmk`(`latexmkoption:`)는
  `-synctex=1`(대시 하나, latexmk 정식 문법)로 각자 맞춰 붙임 — 이전엔
  두 경로 모두 대시 하나로 통일해서 넣던 실수가 있었음. 중복 검사
  (`_has_synctex_option`)는 원래부터 대시 1개/2개 둘 다 인식했으므로
  영향 없음.

## ndhmd4tex.py 0.10.8 (ndhmdsync.py는 0.5.4 그대로)

- `--syncinfo`를 주면 `-synctex=1`을 컴파일 명령(ksruncltex/latexmk
  양쪽, 암시적 latexmk 전환 포함)에 자동으로 덧붙임 — `compileoption:`/
  `latexmkoption:`을 따로 챙길 필요 없음. 이미 `-synctex=...`가 있으면
  그 값을 그대로 존중하고 손대지 않음(중복 옵션이 원고 작성자의 명시적
  선택을 조용히 뒤집는 걸 막기 위함). 실측 결과 중복 `-synctex=` 자체는
  latexmk/xelatex 둘 다 오류 없이 마지막 값으로 조용히 덮어씀을 확인.
  자세한 내용은 가이드 1.5절/1.6절.

## ndhmd4tex.py 0.10.7 (ndhmdsync.py는 0.5.4 그대로)

- 인라인 코드 스팬(백틱) 안의 `\[...\]`/`$$...$$`/수식·표 환경(`align`,
  `tabular` 등)이 진짜 LaTeX 명령으로 오인되어 컴파일 에러를 내던 버그
  수정. 예: `` `grep '\[ndhmd\]'` `` → 이제 `\texttt{grep
  '\textbackslash{}[ndhmd\textbackslash{}]'}`로 정확히 이스케이프됨.
  원인은 DISPLAY_MATH_RE/MATH_ENV_RE/TABLE_ENV_RE의 `` (?<!`)...(?!`) ``
  가드가 "매치 경계 바로 옆 백틱"만 볼 뿐 "코드 스팬 전체 안에 포함된
  경우"는 못 걸렀던 것. `_mask_inline_code_multiline()` 기반의
  `_protect_regex_outside_code()`로 세 곳 모두 통일해서 고침(`--syncinfo`
  이벤트 기록도 함께 정확해짐). 진짜 디스플레이 수식/수식 환경은 실제
  xelatex 컴파일로 회귀 없음 확인.

## ndhmd4tex.py 0.10.6 (ndhmdsync.py는 0.5.4 그대로)

- `--brief`의 "컴파일합니다." 메시지에 실제로 부른 명령줄을 포함하도록
  수정 — `컴파일합니다: /usr/bin/latexmk -xelatex ...`처럼. 이 메시지가
  cmd 조립이 끝나기 전에 찍혀서 정작 무엇을 실행하는지 안 보여주던
  문제였음. 실패 시 중복으로 뜨던 "실행 명령어" 줄도 제거(이미
  "컴파일합니다: ..."로 명령줄을 보여줬으므로).

## ndhmd4tex.py 0.10.5 (ndhmdsync.py는 0.5.4 그대로)

- `--brief`/`--verbose`(기본, 상호배타) 추가 — `--brief`면 `--pdf`류/
  `--latexmk`의 컴파일러 자신의 로그를 숨기고 "컴파일합니다."/"PDF를
  엽니다" 등 핵심만 보여줌. 컴파일 실패 시에는 숨겼던 로그를 그제서야
  보여줌(조용함과 디버깅 불가는 다른 문제). 이 도구가 직접 내는 모든
  메시지 앞에 `[ndhmd] ` 접두어 자동 부착(콘솔 출력을 grep으로 걸러낼
  수 있게) — 컴파일러 자신의 로그에는 안 붙음, `--help`/`--version`
  출력에도 안 붙음. 자세한 내용은 가이드 1장.

## ndhmd4tex.py 0.10.4 (ndhmdsync.py는 0.5.4 그대로)

- `--lint`가 `:::{환경}`/Beamer 프레임(`={4,}`) 여는 줄 바로 다음에 오는
  정상적인 리스트를 "리스트 마커가 문단에 흡수됐다"로 오탐하던 버그
  수정. `_lint_blocks()`가 환경/프레임의 빈 줄 depth를 몰랐던 것과,
  1번 검사가 그 재귀 구조(변환기는 안쪽 내용을 재귀적으로 처리)를
  반영 못했던 것 두 가지가 원인이었음. 진짜 실수(리스트 항목 안 빈
  줄)는 최상위/환경 안/프레임 안/중첩 전부 정확한 줄 번호로 여전히
  잡아내는 것 확인.

## ndhmd4tex.py 0.10.3 (ndhmdsync.py는 0.5.4 그대로)

- Beamer 프레임에 `name=` 속성 추가 — `====={name="frame*",...}`처럼
  `\begin{frame}` 대신 다른 이름의 환경(`frame*`, `itemizedframe` 등,
  ltx-talk 같은 Beamer 확장 패키지용)을 쓸 수 있음. title/subtitle/
  opt/raw 처리는 그대로. 안 주면 기존처럼 `frame`. 자세한 내용은
  가이드 23장.

## ndhmd4tex.py 0.10.2 (ndhmdsync.py는 0.5.4 그대로)

- `:::{환경}`/Beamer 프레임의 따옴표 속성 값(`ATTR_KV_RE`/`parse_attrs`)
  안에 따옴표 자체를 넣을 수 있게 함 — CSV/SQL처럼 겹쳐 쓴다
  (`title="A --- ""B"""` → 값 `A --- "B"`). 기존엔 이스케이프 개념이
  아예 없어서 `\"`도 그냥 다음 `"`에서 값이 끊겼다. 자세한 내용은
  가이드 17장.

## ndhmd4tex.py 0.10.1 (ndhmdsync.py는 0.5.4 그대로)

- 배치 트랜스클루전에 열린 범위(`*`) 추가 — `{{sub??.md;??=01-*}}`처럼
  끝을 실제 디렉터리 검색으로 결정. 중간에 빠진 번호(예: sub11.md
  없음)는 조용히 건너뛰고 다음 것으로 자연스럽게 이어짐. 고정 범위
  (`01-20`)는 기존처럼 하나라도 없으면 여전히 오류 — `*`를 쓸 때만
  예외적으로 조용히 건너뜀. `*`는 끝자리에서만 지원, 검색 범위는
  문서 기준 디렉터리로 한정. `--lint`/`--syncinfo`도 지원. 자세한
  내용은 가이드 20.2절.

## ndhmd4tex.py 0.10.0 (ndhmdsync.py는 0.5.4 그대로)

- Beamer 프레임 지원 추가 — `={4,}{title=,subtitle=,opt=,raw=}` ...
  `={4,}`로 `\begin{frame}...\end{frame}`을 감쌈(`:::{환경}`과 같은
  아키텍처, 재귀 렌더링으로 안의 모든 블록 문법 지원). 설명 리스트도
  첫 항목에 `{!옵션}` 블록을 쓸 수 있게 확장해서 `\begin{description}
  [<+-| alert@+>]` 같은 Beamer 오버레이 지정을 지원. 실제 xelatex+beamer
  컴파일로 오버레이 단계별 강조까지 확인. `--lint`(짝 검사)도 지원.
  자세한 내용은 가이드 23장.

## ndhmd4tex.py 0.9.20 (ndhmdsync.py는 0.5.4 그대로)

- 배치 트랜스클루전에 콤마 구분 목록 지원 추가 —
  `{{sub??.md;??=01-10,12-20}}`처럼 불연속 범위, 단일 숫자와 범위를
  섞어 쓰기(`?=1-3,7,9-10`)가 가능해짐. 콤마 없는 기존 단순 범위
  표기는 완전히 하위 호환. 자세한 내용은 가이드 20.2절.

## ndhmd4tex.py 0.9.19 (ndhmdsync.py는 0.5.4 그대로)

- 배치 트랜스클루전 추가 — `{{sub??.md;??=01-20}}`으로 `{{sub01.md}}`
  부터 `{{sub20.md}}`까지 한 번에 씀. `?`/`??` 자리는 숫자 전용(셸 glob
  아님), 범위 구분자는 대시(`-`). `--syncinfo`(파일별 정확한 원본 줄
  추적)와 `--lint`(펼쳐진 파일 각각의 존재 확인, 재귀 검사 포함)
  전부 지원. `tex:` 접두사와도 함께 쓸 수 있음. 자세한 내용은 가이드
  20.2절.

## ndhmd4tex.py 0.9.18 (ndhmdsync.py는 0.5.4 그대로)

- `--help`에서 값을 `=`로 붙여야 하는 옵션(`--pandoc`, `--latexmk`,
  `--animation`, `--search-resource`, `--guide`)을 `--옵션[=값]`으로
  표시(GNU 계열 도구 관례). 스페이스로 띄워도 되는 옵션(`--default` 등)은
  그대로 `--옵션 값`. 순수 표시만 바뀌고 실제 파싱은 그대로.

## ndhmd4tex.py 0.9.17, ndhmdsync.py 0.5.4

- `--version`에 `-v` 축약형 추가(양쪽 스크립트 모두). ndhmdsync.py에는
  `--version`/`-v` 자체가 없었는데 이번에 신설. ndhmd4tex.py의 `--help`
  출력을 전반적으로 간략하게 정리.

## ndhmd4tex.py 0.9.16 (ndhmdsync.py는 0.5.3 그대로)

- `mapping:`에 리스트 지원 추가 — 여러 YAML을 순서대로 병합(보통 키는
  `setup: [a, b]`와 같이 나중 파일이 이김, `extra_inline`만 예외로 모든
  파일에 걸쳐 이어붙임). 자세한 내용은 가이드 1.2절.

## ndhmd4tex.py 0.9.15 (ndhmdsync.py는 0.5.3 그대로)

- 각주 별행 정의(`[^id]: ...`)의 식별자에 한글 음절 허용(`[A-Za-z0-9_\-가-힣]+`,
  공백은 여전히 불가). 기존에 "정의 누락 + 각주 이중 생성"으로 조용히
  깨지던 문제 해결. 가이드 22장, 치트시트에서 해당 함정 항목 삭제.

## ndhmd4tex.py 0.9.14 (ndhmdsync.py는 0.5.3 그대로)

- `--guide` 옵션 추가 — `~/ndhmd4tex/guide` 등(resources/와 같은 3단계
  구조)에서 가이드 PDF를 찾아 texdoc처럼 바로 연다. 자세한 내용은 가이드
  1.2.2절.

## ndhmd4tex.py 0.9.13 (ndhmdsync.py는 0.5.3 그대로)

- `mapping:`/`setup:`에 경로 없이 파일 이름만 쓰면 공유 리소스 폴더
  아래를 재귀적으로도 찾음(가장 얕은 것 우선, 명시적 경로는 재귀 안 함).
  `--search-resource`는 재귀로 찾은 후보 전부를 얕은 순서로 나열. 자세한
  내용은 가이드 1.2절.

## ndhmd4tex.py 0.9.12 (ndhmdsync.py는 0.5.3 그대로)

- `--default NONE`을 재조정 — "문서 구조"(class/title/preamble/setup/
  maketitle/tocloft)만 무시하고, `mapping:`/`mappingrule:`/`toplevel:`/
  `--config` 같은 "마크업 번역 규칙"은 그대로 적용(전에는 이것도 다
  무시했었다). 다른 문서에 조각을 끼워 넣을 때 그 문서의 관례를 맞출
  수 있게 됐다. 자세한 내용은 가이드 1.1절.

## ndhmd4tex.py 0.9.11 (ndhmdsync.py는 0.5.3 그대로)

- `--default NONE`의 동작을 강화 — front matter를 통째로 무시하고
  본문만 변환(문서 래핑 없음). `--config`/`--syncinfo`/컴파일 옵션은
  경고 후 무시, `--pandoc`과는 함께 동작. 자세한 내용은 가이드 1.1절.

## ndhmd4tex.py 0.9.10 (ndhmdsync.py는 0.5.3 그대로)

- `--default`/`-d` 옵션 추가 — `ndhmd-default.nmd` 자리를 임시로 다른
  파일로 교체(`--setup`과 달리 문서 자신의 `setup:`은 여전히 이김).
  `--default NONE`(대문자)이면 기본 헤더를 아예 안 찾는다. 자세한 내용은
  가이드 1.1절.

## ndhmd4tex.py 0.9.9 (ndhmdsync.py는 0.5.3 그대로)

- 치트시트를 0.9.9 기준으로 갱신(`--latexmk`/`latexmkoption` 추가, note
  두 개 축약·삭제로 공간 확보).

- 문단이 우연히 리스트 마커처럼 보일 때 이스케이프하는 문법 추가 —
  `{-}`/`{*}`/`{+}`, `{1}.`/`{1})`가 실제 마커 검사보다 먼저 걸려서
  그 글자 그대로 찍힌다. 자세한 내용은 가이드 11장.

## ndhmd4tex.py 0.9.8 (ndhmdsync.py는 0.5.3 그대로)

- 리스트 `{옵션}`이 큰따옴표로 감싼 부분을 지원 — `enumitem`처럼 옵션
  자체가 쉼표로 나열되는 패키지도 안전하게 씀(`{!"nosep,label={\arabic*}",
  \tightlist}`). 버그 수정: 옵션 안 중첩 중괄호(`label={\arabic*}`)가
  기존 정규식에서 조기에 잘리던 문제. 가이드 11장 참고.

## ndhmd4tex.py 0.9.7 (ndhmdsync.py는 0.5.3 그대로)

- 리스트 항목이 리터럴 대괄호로 시작할 때, 마커와 대괄호 사이 공백
  유무로 `\item [라벨]`(커스텀 라벨)과 `\item \relax [...]`(그냥 본문)을
  구분하도록 함(`-[정의]` vs `- [텍스트]`). 자세한 내용은 가이드 11장.

## ndhmdsync.py 0.5.3 (ndhmd4tex.py는 0.9.6 그대로)

- macOS에서 뷰어/에디터를 띄운 직후 0.3초 대기 추가 — 터미널 직접 실행은
  되는데 VS Code Tasks로는 반응 없는 문제가, tccd 로그(`log stream`)에서
  Tasks가 띄운 bash가 TCC 신원 확인 시점에 이미 종료돼(`No such process`)
  생기는 경합임을 실측으로 확인하고 완화. 근본 해결은 아니고 경합
  창을 줄이는 것뿐이다.

## ndhmd4tex.py 0.9.6 (ndhmdsync.py는 0.5.2 그대로)

- `latexmkoption:`은 있고 `compileoption:`은 없으면 `--pdf`/`--pdfxe`/
  `--pdflua`만으로 자동으로 `latexmk`가 불리도록 함(엔진은 고른 대로,
  거기에 `latexmkoption:` 값을 이어붙임). 자세한 내용은 가이드 1.6절.

## ndhmd4tex.py 0.9.5 (ndhmdsync.py는 0.5.2 그대로)

- `--latexmk` 추가 — `ksruncltex` 대신 표준 `latexmk`로 컴파일. 옵션
  조합(bibtex/biber, synctex 등)은 검증 없이 그대로 통과시킨다
  (`--latexmk="--synctex=1 --xelatex"`, front matter `latexmkoption:`).
  자세한 내용은 가이드 1.6절 참고.

## ndhmd4tex.py 0.9.4 (ndhmdsync.py는 0.5.2 그대로)

- `{{tex:파일}}` 문법 추가 — 날 LaTeX 파일을 마크다운 처리 없이 그 자리에
  그대로 삽입. `--pandoc`/`--syncinfo`/`--lint` 모두 지원. 자세한 내용은
  가이드 20.1절 참고.
- 치트시트를 0.9.4 기준으로 갱신(`maketitle`/`tocloft`, `{{tex:파일}}` 추가,
  단 배치를 재조정해 표가 컬럼 경계에서 어색하게 안 쪼개지도록 개선).

## ndhmdsync.py 0.5.2 (ndhmd4tex.py는 0.9.3 그대로)

- `--verbose`가 정방향 검색에서 실행할 명령과 완료 여부까지 보여주도록
  확장 — 뷰어가 반응 없을 때 우리 쪽 문제인지 뷰어/OS 쪽 문제인지 구분 가능.

## ndhmd4tex.py 0.9.3 (ndhmdsync.py는 0.5.1 그대로)

- `maketitle:`/`tocloft:` front matter 키 추가 — `\maketitle`/목차류를
  `\begin{document}` 뒤에 자동 삽입. 사용법과 주의사항은 가이드 2.3절 참고.

## ndhmdsync.py 0.5.1 (ndhmd4tex.py는 0.9.2 그대로)

- 근사 폴백에서 동률일 때 다음 구간을 우선하도록 수정 — `{{포함}}` 경계에서
  서브파일로 더 잘 넘어간다.

## ndhmd4tex.py 0.9.2 (ndhmdsync.py는 0.5.0 그대로)

- 버그 수정: `{{포함}}` 문서에서 `--syncinfo`가 서브파일 경로를 절대경로로
  정규화하지 않던 문제(상대경로로 실행했을 때만 발생).

## ndhmdsync.py 0.5.0, ndhmd4tex.py 0.9.1

- `ndhmain:` front matter 키 추가 — 포함된 서브파일을 직접 열어도 정방향
  검색이 올바른 최상위 문서를 찾는다(상대경로 지원).

## ndhmdsync.py 0.4.0 (ndhmd4tex.py는 0.9.0 그대로)

- `ndhmdsync.ini` 설정 파일로 에디터·PDF 뷰어 명령 커스터마이즈 지원.
- 버그 수정: `configparser` 보간 오류, 경로에 공백 있을 때 명령 분해 오류.

## ndhmd4tex.py 0.9.0

- `--syncinfo`가 `{{포함}}` 문서에서도 동작하도록 확장(1단계 포함만
  지원, 재귀 없음). `ndhmdsync.py`는 변경 없음.

## ndhmdsync.py 0.2.2 (ndhmd4tex.py는 0.8.1 그대로)

- 정방향 검색 실패 시 `--verbose` 진단과 더 친절한 오류 메시지 추가.

## ndhmdsync.py 0.2.1 (ndhmd4tex.py는 0.8.1 그대로)

- Windows에서 GUI 프로그램이 실행할 때 반응 없이 멈추던 문제에 대한 방어책
  (콘솔 생성 억제) 추가.

## ndhmdsync.py 0.2.0 (ndhmd4tex.py는 0.8.1 그대로)

- 정방향 검색(`--md-line`) 추가 — Windows는 SumatraPDF, macOS는 Skim,
  Linux는 Okular 지원.

## ndhmdsync.py 0.1.1 (ndhmd4tex.py는 0.8.1 그대로)

- 버그 수정: Windows에서 `code` 명령을 못 찾던 문제(PATHEXT 미해석).

## 0.8.1

- 버그 수정: `--syncinfo`가 `{{포함}}` 없는 문서에서도 조용히 스킵되던
  문제(가이드 안 예시 코드펜스를 진짜 포함 지시자로 오판).

## 0.8.0

- `--syncinfo`, `ndhmdsync.py` 신설 — PDF ↔ 원본 md 역방향 검색 지원.

## 0.7.0

- `[표시](#라벨)` 문법으로 `\hyperref` 링크 지원.
- `author:`가 리스트를 받아 `\and`/`\thanks` 처리.

## 0.6.6

- PDF 뷰어 안내 문구 단순화, "총 경과시간"을 성공 시에만 표시.

## 0.6.5

- 버그 수정: `linecomment`로 지운 줄이 리스트를 쪼개던 문제.

## 0.6.4

- `linecomment: true` 추가 — `//`로 시작하는 행 주석 지원.

## 0.6.3

- `setup:`이 리스트를 받도록 확장. `--setup`도 콤마로 여러 파일 지정 가능.

## 0.6.2

- 커스텀 환경에 `lines: raw` 추가 — TikZ 등 raw 코드를 그대로 통과.

## 0.6.1

- 버그 수정: `--search-resource`가 `ndhmd-default.nmd`를 못 찾던 문제.

## 0.6.0

- 문장 중 `---`의 기본 출력을 `\textemdash`로 변경(별도 정의 불필요).
  `asterism`도 설정 가능.

## 0.5.12

- `NDHMARKDOWN_PDF_VIEWER` 환경변수로 PDF 뷰어 지정 가능.

## 0.5.11

- `--animation`이 이미 뽑은 프레임을 재활용.

## 0.5.10

- 그림 대체텍스트에 링크 중첩 지원. `url` 안 `%`를 자동 이스케이프.

## 0.5.9 (문서 수정 포함)

- 인라인 라벨 `{#id}` 추가.

## 0.5.8 (문서 수정 포함)

- 가이드: minted 3.0 + TeX Live 2025 이후 `-shell-escape` 불필요 명시.
- 헤딩에 `toc="짧은 제목"` 속성 추가.

## 0.5.7

- `--search-resource`(인자 없이)가 `ndhmd-default.nmd`의 실제 출처를 모두
  나열.

## 0.5.6

- `--search-resource` 옵션 추가 — 리소스 파일을 어디서 찾는지 확인.

## 0.5.5

- `mappingrule:` front matter 키 추가 — `mapping.yaml` 없이 설정 병합.

## 0.5.4

- 그림의 대체텍스트가 비면 항상 안 띄우도록 수정. `label`만 있고 `caption`
  없는 그림에 경고.

## 0.5.3

- `caption=` 속성의 뜻 변경(dry caption). 그림에 `inline`/`inlinespec=`
  속성 추가.

## 0.5.2

- 버그 수정: Windows에서 그림 경로가 역슬래시로 나가 컴파일이 깨지던 문제.

## 0.5.1

- `--fetch-images` 없어도 기존 캐시 파일 사용. 그림에 `href=` 속성 추가.

## 0.5.0

- `--fetch-images`, 이미지 포맷 자동 변환, `--animation` 추가.

## 0.4.1

- 모르는 키의 매크로 이름을 소문자로 통일.

## 0.4.0

- `--lint`에 front matter 점검 추가.

0.3 계열에서 쌓인 것: 인라인 각주, `--pandoc`, 기본 헤더와 `--setup`,
`--lint`, 운문 환경, 줄임표, `extra_inline`, 그림 `wrap`, 공유 리소스 폴더,
`beforestart`, CRLF 정규화. 자세한 것은 아래 각 항목 참고.

## 0.3.23

- `beforestart:` 추가. 모르는 키를 `\def\NM<키>{값}`으로 전달.

## 0.3.22

- 버그 수정: CRLF 원고의 줄바꿈을 LF로 통일하지 않던 문제.

## 0.3.21

- `mapping`/`setup`/기본 헤더를 공유 리소스 폴더에서도 찾도록 확장.

## 0.3.20

- 그림에 `wrap` 속성 추가(`wrapstuff` 환경).

## 0.3.19

- `--lint`가 `{{포함}}` 하위 파일까지 검사.

## 0.3.18

- `--lint` 옵션 추가 — 흔한 마크업 실수 점검.

## 0.3.17

- 각주 대괄호 파싱 버그 수정, 대괄호 한 겹 중첩 허용.

## 0.3.16

- `extra_inline` 설정 추가, 인라인 규칙이 다중 캡처 그룹 지원.

## 0.3.15

- 두 문단 이상 인용구를 `quotation`으로 렌더.

## 0.3.14

- 참조 프리픽스 `[E:]`/`[F:]`/`[T:]` 추가.

## 0.3.13

- 설명 리스트에 중괄호 표기 `{용어} :: 설명` 추가.

## 0.3.12

- 설명 리스트 판정 엄격화(오인식 해소).

## 0.3.11

- 오류 처리 정리 — 설정 파일/YAML 오류 시 트레이스백 대신 메시지.

## 0.3.10

- 입력 파일 오류 처리 및 인코딩 폴백(UTF-8→cp949→euc-kr) 추가.

## 0.3.9

- 마침표 세 개를 `\ldots{}`로 변환.

## 0.3.8

- 운문 환경 `:::{hverse}`/`{verse}` 추가.

## 0.3.7

- `--init-setup` 옵션 추가.

## 0.3.6

- PyInstaller 실행 파일에서 기본 헤더를 찾도록 대응.

## 0.3.5

- 헤더 없는 원고를 위한 기본 헤더(`ndhmd-default.nmd`) 도입.

## 0.3.4

- `--pandoc`이 값을 받도록 확장, 충돌하는 pandoc 옵션 무시.

## 0.3.3

- 버그 수정: Windows(cp949)에서 `--pandoc` 사용 시 죽던 문제.

## 0.3.2

- 각주 식별자가 범위를 벗어나면 경고.

## 0.3.1

- 인라인 각주 `[^각주 본문]` 지원.

## 0.3.0

- 0.2.14에서 버전만 올림. 0.2 계열 누적분: `showexam` 2단 블록, 인라인 raw
  스팬, 기본 환경(`table`/`figure`/`thebibliography`), natbib 인용
  프리픽스, `--pandoc`, 틸드 정책 변경.
