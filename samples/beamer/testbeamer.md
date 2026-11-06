---
setup: beamermd.nmd
title: Presentation with Beamer
author: W. H. OH
institute: Korean \TeX~Users Group
date: \today
theme: Madrid
maketitle: true
preamble+: |
    \usepackage{koredumath}
    \iftutex
    \setmainhangulfont{Noto Serif CJK KR}
    \setsanshangulfont{Noto Sans CJK KR}[CompressPunctuations]
    \fi
    \usepackage{tzplot}
    \def\emph#1{\alert{\bfseries #1}}
    \def\textbf#1{\structure{#1}}
---

====={}
\tableofcontents
=====

# 첫 프레임 

====={title="첫 프레임"}
markdown으로 해보는 beamer presentation 작성
=====

# 테스트 프레임즈

======{title="좋은 발표자료의 요건"}
- {!"<+-| alert@+>"} 내용에 집중하자 
- 지루하지 않게 
- 실제 발표할 내용이 슬라이드에 기록된 내용보다 많아야 한다 
- 대체로 인터넷 자료보다 매뉴얼이 더 신뢰할 만하다. 항상 `beamer` 매뉴얼을 참고
- 중요한 패키지 사용법을 숙달하자 
- 새로운 아이디어가 중요하다 
======

======{title="프레임에 제목을 달자",subtitle="작은 제목",opt=fragile}
{uncover}  ::  <1-> 주어진 슬라이드에서 visible.
{only}     ::  <2-> 주어진 슬라이드에서 show.
{visible}  ::  <3-> 주어진 슬라이드에서 visible.
{onslide}  ::  <4-> 해당 슬라이드에서 open.
{temporal} ::  <5-> 세 인자를 취하여 해당 슬라이드 이후 `#3`. 그 이전까지 `#1`, 해당 슬라이드에서 `#2`.
======

# Introduction

======{title="Blocks and Theorems"}
:::{example}
슬루츠키 방정식은 경제학에서
한 재화의 가격 변화로 인한 수요의 변화가 대체 효과와
소득 효과의 결과로 이루어진 것임을 나타내는 공식이다.
수학자이자 경제학자인 예브게니 슬루츠키의 이름을 따서
명명되었다.
:::

:::{block raw="{Slutsky Equation}"}
\[
\pdv{x_i(\mathbf{p},w)}{y_i} =
\pdv{h_i(\mathbf{p}, u)}{p_j}
- \pdv{x_i (\mathbf{p}, w)}{w} x_j(\mathbf{p},w)
\]
:::
======

```tex
\begingroup %%% this group should be terminated
\usebackgroundtemplate{
    \begin{tikzpicture}[overlay,remember picture]
    \tznode[anchor=north west,opacity=.3](current page.north west){\pgfimage[width=\paperwidth,height=\paperheight]{bonobonob}}
    \end{tikzpicture}
}
```

====={title="Background Image, Opacity",opt="<+->",raw="\color{black}"}
- 글이 너무 많은 것보다는 차라리 아주 적은 것이 좋다. 보통 한 프레임에 20 내지 40단어 정도를 쓰는데 많아도 80단어를 넘어서는 안 된다.
- 청중이 주제에 대해 잘 알고 있다고 가정하지 말라. 자신이 사용하는 용어의 원래 의미를 끊임없이 상기시키는 것이 좋다.
- 발표 도중에 언급하지 않을 내용을 슬라이드에 포함하지 말라. 오히려 슬라이드에 없는 화제를 발표에서 언급하는 것이 더 좋다.
- *단순하게, 단순하게!* 청중은 슬라이드에 50초 이상 주목하지 않는다. 긴 문장이나 수식을 읽고 있을 리가 없다.
- 랜스 포트노 교수가 말하기를, "대체로 파워포인트 사용자가 더 좋은 발표를 한다. 왜냐하면 파워포인트는 수식 입력이 너무 어려워서 수식을 덜 쓰니까 발표가 더 간명하고 쉬워지기 때문이다."라고 하였다.
=====

```tex
\endgroup  %% here terminates the group
```

====={title="Columns and Column"}
:::{columns}
:::{column raw="[c]{.4\linewidth}"}
![](bonobonob){width=\linewidth}
:::

:::{column raw="[c]{.6\linewidth}"}
《보노보노(ぼのぼの)》는 일본의 만화가 **이가라시 미키오**가 1986년부터 연재 중인 4컷 만화이자, 이를 원작으로 하는 애니메이션과 주인공 캐릭터의 이름입니다. 겉보기에는 단순하고 귀여운 동물 만화 같지만, 삶과 관계에 대한 깊이 있는 철학적 메시지를 담고 있어 어린이뿐만 아니라 성인들에게도 큰 위로를 주는 작품으로 널리 알려져 있습니다.
:::
:::
=====