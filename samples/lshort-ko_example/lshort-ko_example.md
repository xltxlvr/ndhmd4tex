---
setup: lshort-ko_example_preamble.nmd
compileoption: --makeindex='komkindex -s kotex.ist -k'
---

# 알아두어야 할 기본 사항

## 1.3.1 공백

```showexam frame=none
It does not matter whether you
enter one or several     spaces
after a word.

An empty line starts a new
paragraph.
```

## 1.3.2 특별한 문자

```showexam
$ # % ^ & _ { } `~` \
```

    - #은 행의 첫머리에 있으면 header 지시문이 된다. 문장 중간에 오도록 순서를 바꿈.
    - $는 수식 모드로 판정되지 않는 경우에 주의. 즉 좌우로 `$...$` 형식이 있으면 수식이다.
    - `\`는 그 뒤에 이어지는 알파벳이 있으면 \LaTeX{} 매크로로 인식한다.
    - `~` 부호는 복잡하다. 일반적으로 텍스트 안에서(좌우에 문자가 있을 때)는 \LaTeX 에서의 용법
      그대로이다. `\~`는 *kswdash* 패키지를 얹으면 물결표로 동작한다. 그래서 마크다운 해석기가
      이 부호는 해석하지 않도록 해두었다. 부호 자체를 찍어야 한다면 위의 예와 같이 하라.

## 1.3.3 \LaTeX{} 명령

```showexam 
New \TeX users may miss whitespaces 
after a command. <!--renders wrong-->
Experienced \TeX{} users are \TeX perts, 
and know how to use whitespaces.
```

이 방언에서 %는 comment로 쓰이지 않는다. 주석은 markdown 방식으로 적는다.

```showexam 
You can *lean* on **me**!

Please, start a new line right here!\\
Thank you.
```

## 1.3.4 주석 

```showexam 
This is an <!-- stupid 
Better: instructive -->
example: Supercalifragilisticexpialidocious
```

이 방언에는 하이픈 위치를 나타내는 별도의 명령이 없다. 그러므로
특별히 이러한 경우는 `{=latex}`이라는 raw attribute 지정자를 써야 한다.

```showexam 
This is an example: `Super\-ca\-li\-frag\-i\-list\-icexpi\-al\-i\-do\-cious.`{=latex}
```

```showexam 
This is another <!--rather stupid,
but helpful -->
example for embedding 
comments in your documents.
```

`//`를 행의 첫머리에 두어 행 주석으로 처리되게 하려면 config에서 
`linecomment: true`로 해야 한다. 스크립트의 디폴트는 `false`이다.

```showexam 
This is another
// rather stupid, but helpful 
example for comments.
```

# 텍스트의 조판 

## 2.4.1 따옴표 

```showexam 
"please press the 'x' key."
```

다른 마크다운 언어와 달리 스마트 따옴표는 매우 잘 동작한다. 그러나
어떤 이유에선가 여는 따옴표가 인식되지 않을 때(주로 여는 따옴표 직전의 스페이스가 사라져서 생길 때가 많다)
back-tick을 강제할 수 있다.

```showexam
\`\`please press the \`x' key.''
```

## 2.4.2 대시와 하이픈 {#sec:dashellip}

```showexam 
daughter-in-law, X-rated\\
pages 13--67\\
yes --- or no?\\
$0$, $1$ and $-1$.
```

이 방언은 `---`를 `\textemdash`로 치환한다.
*oblivoir* 클래스 또는 *kopunct* 패키지를 통해 얻을 수 있는 `\expldash`를
긴 대시 자리에 쓰고 싶다면 `mapping` 기능을 이용하여 `mdash:` 키의 값을 바꾼다.

만약 *kswdash*나 *ksvqt* 패키지를 이용한다면 한국어 문장을 위한 추가 문장부호를 얻을 수 있다.
가운뎃점이나 줄임표 등.
다만 이 경우 config yaml에서 `\.`를 extra_macro로 풀어두어야 한다.

```showexam 
13\~67쪽. \<1마크다운 방언> 마크다운\.레이텍\...
```

## 2.4.3 틸데

```showexam 
[](http://www.rich.edu/~bush) \\
[](http://www.clever.edu/~demo)

1\~2, a~b
```

## 2.4.5 도 기호 

```showexam 
It's $-30\,^{\circ}\mathrm{C}$. \\
It's $-30$\,\textdegree C \\
30\,\textcelsius \\
30℃ (unicode [U+2103])
```

## 2.4.6 통화 기호 

```showexam 
$, \texteuro, \textwon, \textyen
```

## 2.4.7 줄임표 

```showexam 
Not like this ... but like this: \\
New York, Tokyo, Budapest\obldots 
```

줄임표는 기본적으로 `\ldots`로 변환된다. 이 문서에서는 yaml config를 통하여 
`\obellipsis`가 되도록 해두었다. 설정 파일을 참조하라.

만약 정말로 줄임표가 `\ldots`가 되게 해야 한다면, 설정 파일을 통하여 `\obldots`로
하든가, 아니면 `\obldots`를 직접 입력하자(*oblivoir*).

한국어 문서에서 폰트 이슈로 줄임표가 부적절해보일 때에는 `kswdash` 패키지의
방식을 이용할 수 있다(\S~[#sec:dashellip]).

## 2.4.9 액센트와 특수 문자 

```showexam 
H\^otel, na\"\i ve, \'el\`eve \\
sm\o rrebr\o d, Se\~norita,
Sch\"onbrunner Schlo\ss, Stra\ss e
```

이 마크다운 방언에서는 모든 액센트 기호를 지원하지 않는다.
위의 예가 그러하다. 원칙적으로 확장 라틴문자는 직접 입력해야 한다.

```showexam 
Hôtel, naïve élève smørrebrød, Señorita, 
Schönbrunner Schloß, Straße
```
참고로, 필자가 작성한 [`pm IME GUI`라는 앱](https://nonametex.imweb.me/?q=YToxOntzOjEyOiJrZXl3b3JkX3R5cGUiO3M6MzoiYWxsIjt9&bmode=view&idx=171896425&t=board)으로 LaTeX 입력 방식을 통해 확장 라틴 문자를 얻을 수 있다.

굳이 \LaTeX 표기법을 원한다면 다음과 같이 하라.

```showexam 
`Stra\ss{e}`{=latex}
```

## 2.6 단어 사이의 공백 

```showexam 
Mr.~Smith was happy to see her.\\
cf.~Fig.~5\\
I like BASIC\@. What about you?
```

## 2.8 교차참조 {#sec:this}

```showexam ratio=.6
A reference to this subsection \label{sec:here}
looks like: 
"see section [#sec:this] on page 
[page:sec:this], and page [page:sec:here]."
```

\LaTeX{} 명령 `\label`로 지정한 라벨도 참조할 수 있음을 보였다.

## 2.9 조사의 선택 {#sec:autojosa}

```showexam 
[#sec:autojosa]\을 보아라.
```


## 2.10 각주 

```verb
Footnotes[^fn1] are often used by people
using \LaTeX.

[^fn1]: This is a footnote.
```

Footnotes[^fn1] are often used by people
using \LaTeX.

[^fn1]: This is a footnote.

인라인 각주 형식도 지원한다.

```verb 
인라인 각주^[이 텍스트는 각주의 모양과 위치를 보여준다.]도 
잘 지원한다.
```

인라인 각주^[이 텍스트는 각주의 모양과 위치를 보여준다.]도 
잘 지원한다.

```showexam 
물론 `\footnote` 명령을 직접\footnote{다른 각주}
써도 될 거다.
```

## 2.11 단어의 강조 

```showexam 
기본, *이탤릭 italic*, **두껍게 bold**, 
~~취소선 strike out~~,
__밑줄 underline__, ^^방점강조 dotemph^^,
***산세리프 서체 san serif family***
```

여기서 __밑줄 처리__와 ***산세리프 서체***는 `mapping` config 파일에 정의하여 사용자화한 것이다.
밑줄 `\uline`과 취소선 `\sout`으로 구현하므로 *ulem* 패키지 또는 *luatexko*가 필요하다.

## 2.12.1 리스트 문단 

```showexam 
1. You can nest the list environments
   to your taste   
   * But it might start to look silly
   - [-] With a dash.   
2. Therefore remember:
   {Stupid} ::  things will not become smart
      because they are in a list.
   {Smart} ::  things, though, can be presented
      beautifully in a list 
```

`description`의 엄격한 문법이 도입되었다. 규칙은 키워드를 중괄호로 감싸고 두 개의 콜론 뒤에 두 개의 스페이스를 두는 것이다.

`oblivoir`에서 많이 쓰는 `enumerate`의 옵션 인자는 다음처럼 할 수 있다.

```showexam 
1. {!(1),\firmlist} You can nest the list environments.
1. Therefore, remember 
```

## 2.12.2 문단의 정렬

```showexam 
:::{flushleft}
This text is\\ left-aligned.
\LaTeX{} is not trying to make
each line the same length.
:::

:::{flushright}
This text is\\ right-aligned.
\LaTeX{} is not trying to make
each line the same length.
:::

:::{center}
This text is\\ centered.
\LaTeX{} is not trying to make
each line the same length.
:::
```

## 2.12.3 인용문과 운문 

```showexam 
A typographical rule of thumb
for the line length is:

> On average, no line should
> be longer than 66 characters.

This is why \LaTeX{} pages have
such large borders by default
and also why multicolumn print
is used in newspapers.
```

인용문이 두 문단 이상(즉 중간에 빈 줄이 들어가면) `quote`가 아니라 `quotation`으로 된다.

운문의 경우 이 방언은 행 끝의 `\\`를 붙이지 ***않아야*** 한다.
만약 행마다 `\\`를 붙이는 형태의 시를 조판하려 한다면 `\begin{verse}`로
마크업하거나 raw로 전달하여야 한다.

```showexam 
I know only one English poem by
heart. It is about Humpty Dumpty.

:::{verse}
Humpty Dumpty sat on a wall:
Humpty Dumpty had a great fall.
All the King's horses and all
the King's men
Couldn't put Humpty together again.
:::
```

*oblivoir-misc* 패키지의 `hverse` 환경을 쓸 수 있다.

````showexam
:::{hverse}
창밖에 밤비가 속살거려
육첩방은 남의 나라,

시인이란 슬픈 천명인 줄 알면서도
한 줄 시를 적어 볼까,
:::
````

## 2.12.4 요약문

```showexam
:::{abstract}
The abstract abstract.
:::
```

## 2.12.5 그대로 보이기 

```showexam 
The `\ldots` command \ldots.
```

````showexam 
```verb
10 PRINT "HELLO WORLD ";
20 GOTO 10
```
````

`verbatim*` 환경을 직접 쓰는 방법은 현재 기본으로 지원하고 있지 않다.
그러나 필요하다면 config 파일을 통해서 쓸 수 있다. config 파일의 설정에
대하여는 \<!사양서>를 볼 것.
별표붙은 `\verb*` 명령은 latex attribute를 주어 직접 쓰면 된다.

```showexam 
`\verb*|like     this :-) |`{=latex}
```

사양서 제10장 코드 블록은 verbatim 및 소스 코드 리스팅과 관련된 여러 설정을
상세히 설명한다.

## 2.12.6 표 

표준 마크다운의 '파이프' table을 쓸 수 있다. 이것은 항상 booktabs 형식으로 바뀐다.

```showexam 
| 표기         | 이름        |
|------------:|:------------|
| 7C0         | hexadecimal |
| 3700        | octal       |
| 11111000000 | binary      |
```

preamble에 

```verb
    \usepackage{tabularray}
    \UseTblrLibrary{booktabs}
```

를 (거의 언제나) 두어야 한다. 이 설정을 바꾸려면 config 파일을 수정해서 불러온다.

그 이외의 표는 [T/B/L/R 도우미](https://nonametex.imweb.me/?bmode=view&idx=170644211&t=board)로 그린 코드를
그대로 가져오는 것으로 충분하다.

```showexam 
\begin{tblr}{
  colspec = {lcr},
  hline{1,Z} = {1pt},
  hline{2} = {solid},
  row{odd} = {cyan8!20},
  row{1} = {bg=cyan4,fg=white,font=\sffamily\bfseries\small},
}
  Head A & Head B & Head C \\
  Data 1 & Data 2 & Data 3 \\
  Data 4 & Data 5 & Data 6 \\
  Data 7 & Data 8 & Data 9 \\
\end{tblr}
```

표를 플로팅하려면 table 환경 안에 넣는다. 표 [#tab:1]\는 위 예시 코드를
`:::{table}` 안에 넣은 것이다.

```verb 
:::{table place="htbp",caption="T/B/L/R 도우미로 그린 표",label="tab:1",align="\centering"}
\begin{tblr}{
...
\end{tblr}
:::
```

:::{table place="htbp",caption="T/B/L/R 도우미로 그린 표",label="tab:1",align="\centering"}
\begin{tblr}{
  colspec = {lcr},
  hline{1,Z} = {1pt},
  hline{2} = {solid},
  row{odd} = {cyan8!20},
  row{1} = {bg=cyan4,fg=white,font=\sffamily\bfseries\small},
}
  Head A & Head B & Head C \\
  Data 1 & Data 2 & Data 3 \\
  Data 4 & Data 5 & Data 6 \\
  Data 7 & Data 8 & Data 9 \\
\end{tblr}
:::


## 2.13 그림 포함하기 

```showexam 
문장 중에 
![](example-image-a){height=12pt,raise=-3pt} 
그림
```

위의 예시에서 `raise=-3pt` 부분을 위해 *adjustbox* 패키지에 `[export]` 옵션을 주어서 로드해야 한다.

```showexam
단독으로 그림 

:::{center}
![](example-image-b){width=.8\linewidth}
:::
```

플로트로 넣을 때는 캡션 텍스트를 주면 된다. 

```verb
![캡션 텍스트](example-image-c){label="fig:1", place=htbp, width=.3\linewidth, align="\centering"}
```

![캡션 텍스트](example-image-c){label="fig:1", place=htbp, width=.3\linewidth, align="\centering"}

플로팅하지만 캡션을 달지 않을 때는 캡션 텍스트에 `""`(빈 따옴표 쌍)을 넣는다. 이때는 `label`이 
아무 의미가 없다.

```showexam 
위의 그림 [#fig:1]\를 참조할 수 있는 것이다.
```

## 2.14 떠다니는 개체 

앞서 테이블과 그림에 대한 부분에서 시험하였다. 
`figure`의 경우는 `\includegraphics`가 있을 때의 표기법을 앞절에서
보였는데, 외부 그림이 아니라 다른 어떤 것이라도 `figure` 안에 넣어야 할 때는
`table`과 같은 문법을 쓸 수 있다. 다음 예(그림 [#fig:tikz])를 보아라.

```verb
:::{figure place=htbp,align="\centering",caption="TikZ로 그린 그림",label="fig:tikz"}
\begin{tikzpicture}[scale=3]
\clip (-0.1,-0.2) rectangle (1.8,1.2);
\draw[step=.25cm,gray,very thin] (-1.4,-1.4) grid (3.4,3.4);
\draw (-1.5,0) -- (2.5,0);
\draw (0,-1.5) -- (0,1.5);
\draw (0,0) circle (1cm);
\filldraw[fill=green!20!white,draw=green!50!black](0,0) -- (3mm,0mm) arc (0:30:3mm) -- cycle;
\end{tikzpicture}
:::
```

:::{figure place=htbp,align="\centering",caption="TikZ로 그린 그림",label="fig:tikz"}
\begin{tikzpicture}[scale=3]
\clip (-0.1,-0.2) rectangle (1.8,1.2);
\draw[step=.25cm,gray,very thin] (-1.4,-1.4) grid (3.4,3.4);
\draw (-1.5,0) -- (2.5,0);
\draw (0,-1.5) -- (0,1.5);
\draw (0,0) circle (1cm);
\filldraw[fill=green!20!white,draw=green!50!black](0,0) -- (3mm,0mm) arc (0:30:3mm) -- cycle;
\end{tikzpicture}
:::

# 수학식 조판 

## 3.2 수식 기초 

수식은 거의 \LaTeX 의 것을 그대로 쓰면 된다. 

```showexam 
Add $a$ squared and $b$ squared
to get $c$ squared. Or, using
a more mathematical approach:
$a^2 + b^2 = c^2$

***

\TeX{} is pronounced as
$\tau\epsilon\chi$\\
100~m$^{3}$ of water\\
This comes from my $\heartsuit$
```

```showexam
Add $a$ squared and $b$ squared
to get $c$ squared. Or, using
a more mathematical approach
\begin{equation}
a^2 + b^2 = c^2
\end{equation}
Einstein says
\begin{equation}
E = mc^2 \label{clever}
\end{equation}
He didn't say
\begin{equation}
1 + 1 = 3 \tag{dumb}
\end{equation}
This is a reference to
[E:clever].
```

`[E:label]`과 같이 라벨 붙은 수식을 참조(`\eqref`)할 수 있다.

```showexam 
This is text style:
$\lim_{n \to \infty}
\sum_{k=1}^
n \frac{1}{k^2}
= \frac{\pi^2}{6}$.
And this is display style:
\begin{equation}
\lim_{n \to \infty}
\sum_{k=1}^
n \frac{1}{k^2}
= \frac{\pi^2}{6}
\end{equation}
``` 

```showexam 
$x^{2} \geq 0\qquad
\text{for all } x
\in \mathbb{R}$
```

```showexam 
\begin{equation*}
\begin{matrix}
1 & 2 \\
3 & 4
\end{matrix} \qquad
\begin{bmatrix}
p_{11} & p_{12} & \ldots
& p_{1n} \\
p_{21} & p_{22} & \ldots
& p_{2n} \\
\vdots & \vdots & \ddots
& \vdots \\
p_{m1} & p_{m2} & \ldots
& p_{mn}
\end{bmatrix}
\end{equation*}
```

## 3.9 수학적 문단 

```showexam ratio=.6
:::{theorem title="[Murphy's Law]",label="thm:mur"}
If there are two or
more ways to do something, and
one of those ways can result in
a catastrophe, then someone
will do it.
:::

Let's see [#thm:mur].
```

주의. 위의 예에서 label을 주고 옵션 인자를 주고 하는 것은 config 파일의 theorem 환경 설정을 따른다. 기본값으로 정해진 것은 단순히 
```verb 
\begin{theorem}
```  

만을 출력해주는 것이므로 주의하라.
이 문서의 config 파일의 설정을 참고할 것.

```verb 
environments:
  theorem:
    begin: |-
      \begin{theorem}%(title|)s
      ?\label{%(label)s}
    end: '\end{theorem}'
```

## 3.9.1 증명 

```showexam 
:::{proof}
Trivial, use
\begin{equation*}
E=mc^2. \qedhere
\end{equation*}
:::
```

# 특별한 기능 

## 문헌 목록과 인용 

```verb 
:::{thebibliography widest="99"}
\bibitem{pa} H.~Partl: \emph{German \TeX}, TUGboat Volume~9, Issue~1 (1988)
:::
```

```showexam 
[@pa].
```

*natbib* 류의 `\citet`, `\citep`를 쓸 때는 preamble에 관련 설정을 완비하고 
`[@t:pa]`, `[@p:pa]`와 같이 마크업한다.

## 4.2 색인 

색인을 마크업하는 것은 대단히 쉬워졌다. 

```showexam ratio=.6
[[한국어 문서]]의 [[색인]] [[작성]]을 위해서 [[makeindex|Commands!makeindex]]를 
그대로 쓰면 [[만족]]스러운 [[결과]]를 얻기 어렵다. 
\koTeX 은  이를 위하여 [[komkindex|Commands!komkindex]]라는 
[[프로그램]]을 [[제공]]한다.
\koTeX 과 함께 [[배포]]되므로 이미 [[설치]]되어 있을 것이다. 
이 [[프로그램]]은 한 가지 유용한 [[옵션]]을 [[|프로그램 옵션]]
가지고 있는데, [[라틴 문자]]보다 [[한글]]이 [[색인]]에서 먼저 
나타나게 하고 싶으면 
`-k` 옵션을 줄 수 있다는 것이다. 
이밖에 최근 [[유니코드 문자]]를 처리할 수 있는 
[[색인 유틸리티|색인!유틸리티]]가 발전하는
중이다. [[xindy]], [[xindex]] 등이 그 예이다.
```

* preamble에 `\makeindex`가, 문서의 (backmatter에) `\printindex`가 있어야 한다.
* preamble의 `compileoption:` 키에 `--makeindex='INDEXPROCPROG'`를 지정해야 한다.
이 글은 간단히 `komkindex`를 부르도록 하였다. 결과는 [page:sec:index] 페이지를 보라.

# 수학적 그래프 그리기 

```showexam 
\begin{tikzpicture}[scale=3]
\clip (-0.1,-0.2) rectangle (1.8,1.2);
\draw[step=.25cm,gray,very thin] (-1.4,-1.4) grid (3.4,3.4);
\draw (-1.5,0) -- (2.5,0);
\draw (0,-1.5) -- (0,1.5);
\draw (0,0) circle (1cm);
\filldraw[fill=green!20!white,draw=green!50!black](0,0) -- (3mm,0mm) arc (0:30:3mm) -- cycle;
\end{tikzpicture}
```

\backmatter 

:::{thebibliography widest="99"}
\bibitem{pa} H.~Partl: \emph{German \TeX},
TUGboat Volume~9, Issue~1 (1988)
:::

\printindex
