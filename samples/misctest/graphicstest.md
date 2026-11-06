---
preamble+: |
  \usepackage{fapapersize}
  \usefapapersize{210mm,297mm,0.66in,*,0.66in,*}
  \usepackage[export]{adjustbox}
  \usepackage{wrapstuff}
  \usepackage{inlinegraphicx}
  \usepackage{capt-of}
  \usepackage{jiwonlipsum}
---

# 그림 넣기 

## 단순 `\includegraphics`

![](example-image){width=5cm}

## 플로팅, 캡션, 라벨

![예제 그림, MWE 패키지](example-image-a){width=5cm,label="fig:label"}

## 드라이 캡션, 라벨

![](example-image-b){caption="드라이 캡션",label="fig:labela",width=5cm}

## 캡션 없는 플로트 

![""](example-image-c){width=5cm,right}

## wrapfig

![](example-image-a){width=3cm,wrap,wrapspec="r"}
\jiwon[1]

## online image 

![온라인 이미지](https://cdn.imweb.me/upload/S2024121748e4513968c4a/f982c89cf2b53.png){width=5cm,label="fig:online"}

- 최초 실행 시 `--fetch-images` 옵션을 한번 주어야 한다. 일단 다운로드에
성공하면 그 후로는 fetch 옵션 없이 동작함.
- **다운로드 불가능한 그림은 다운로드 불가능하다.**
- 다운로드한 이미지는 `_images/` 서브 폴더에 저장됨

## inline 그림 

인라인 그림을 넣을 때는 (![](example-image){inline,inlinespec="scale=1.1,strut={()}"})
`inlinegraphicx` 패키지를 사전에 로드해야겠다.

# 라벨에 대한 참조.

위의 [F:fig:label]\과 [F:fig:labela]\를 보시오. [F:fig:online]\는 온라인 이미지입니다.

# 이 문서의 소스.

\boxedverbatiminput{\jobname.md}

