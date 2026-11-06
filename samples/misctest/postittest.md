---
setup: articlelike.nmd
mapping: postit.yaml
preamble+: |
  \usepackage[most]{tcolorbox}
  \usepackage{wrapstuff}
  \usepackage{postit}

  \usepackage{lipsum}
  % postit 패키지는 색상값에 xcolor스타일의 !신택스를 허용하지 않음
  \colorlet{yellowA}{yellow!30}
  \usepackage{ninecolors}
---

# PostIt! package

간단한 박스를 {|yellowA|이렇게} 두를 수 있답니다. {||olive8||**PostIt**!} 패키지랍니다.

:::{postit}
\lipsum[1][1-2]
:::


:::{postit opt="StorePostIt=NoteY",raw="<center>"}
This is a small Post-It ! For example \[(a+b)^2=a^2+2ab+b^2.\]
:::
:::{postit opt="Render=tikz,Width=8cm,Color=blue,Rotate=-5,StorePostIt=NoteZ"}
\lipsum[1][1-2]
:::
:::{tikzpicture opt="remember picture,overlay"}
\draw[very thick,->,>=latex] (NoteY-S)to[out=-90,in=90](NoteZ-N) ;
:::

***

:::{wrapstuff raw="[r,top=2]"}
:::{postit opt="Rotate=5,Render=tikzv2,Pin=Scotch,Color=pink"}
\lipsum[1][1-2]
::: 
:::
\lipsum[1-2]
