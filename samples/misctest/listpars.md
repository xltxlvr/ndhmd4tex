---
preamble+: |
    \usepackage[shortlabels]{enumitem}
    \usepackage{dhucs-enumitem}
---

# 기본

가장 중요한 사실: **리스트 문단 중간에 빈 줄이 들어가면 그 리스트의 끝**.

- 아이테마이즈 
- 아이테마이즈 

1. enumerate item 
1. enumerate item 2

{용어} ::  해설 
{설명} ::  설명형 리스트

# 커스텀 라벨

빈 칸이 허용되는 경우는 오직 **커스텀 라벨**의 대괄호뿐이다.

-[(제1번)] G장조.
- [제1번] G장조.

# enumitem, enumrate(memoir)

1. {!(1),\firmlist} 첫 항목
1. 둘째 항목

1. {!"label={\pgana*},noitemsep"} 첫 항목
1. 둘째 항목 

