
# `ndhmd4tex`: \LaTeX{} 문서 작성을 위한 markdown 방언의 설계와 활용

한동안 여기저기 흩어놓았던 글들을 돌아보니, 저도 모르게 하나의 궤적을 그리고 있었습니다. 이번엔 그 궤적의 다음 정거장, `ndhmd4tex` 이야기를 해볼까 합니다. 버전 0.3.3, 아직 세상을 놀라게 할 만한 완성도는 아니지만 "이제 남 앞에 내놓아도 부끄럽지 않겠다" 싶은 형태는 갖추었습니다.

## 지금까지 걸어온 길

돌이켜보면 이 여정은 꽤 오래전에 시작됐습니다.

먼저 [「org mode에서 \LaTeX{} 하기」](https://nonametex.imweb.me/?q=YToyOntzOjEyOiJrZXl3b3JkX3R5cGUiO3M6MzoiYWxsIjtzOjc6ImtleXdvcmQiO3M6ODoib3JnIG1vZGUiO30%3D&bmode=view&idx=134694319&t=board)에서는 Emacs org mode가 \LaTeX{}과 어떤 관계를 맺을 수 있는지 살펴봤습니다. org mode는 원래 아웃라이너이자 할 일 관리 도구였지만, export 백엔드를 통해 \LaTeX{} 문서를 뽑아낼 수 있다는 점이 꽤나 매력적이었습니다. 다만 org 문법 자체가 \LaTeX{} 사용자에게는 다소 낯선 세계이기도 했습니다.

다음으로 [「pandoc markdown에서 \LaTeX{}」](https://nonametex.imweb.me/?q=YToyOntzOjEyOiJrZXl3b3JkX3R5cGUiO3M6MzoiYWxsIjtzOjc6ImtleXdvcmQiO3M6NjoicGFuZG9jIjt9&bmode=view&idx=168551657&t=board)에서는 pandoc markdown을 \LaTeX{}의 프론트엔드로 삼는 방법을 논했습니다. markdown의 익숙함과 pandoc의 강력한 변환력을 빌려 오면, \LaTeX{} 특유의 진입장벽을 조금은 낮출 수 있었습니다.

그리고 [KTUG 문고 002 「숙향전」](https://nonametex.imweb.me/?q=YToyOntzOjEyOiJrZXl3b3JkX3R5cGUiO3M6MzoiYWxsIjtzOjc6ImtleXdvcmQiO3M6MTI6InR4dDJwZGZlYm9vayI7fQ%3D%3D&bmode=view&idx=144741310&t=board) 소스와 컴파일 방법을 소개하면서는 `txt2pdfebook`이라는 개인 출판 시스템을 선보였습니다. 이건 multimarkdown으로 글을 쓰고, \LaTeX{}을 순전히 "인쇄소"로만 부려먹는 방식이었습니다. 즉 저자는 markdown만 알면 되고, \LaTeX{}은 뒤에서 묵묵히 조판만 해주는 구도였습니다.

세 편의 글을 관통하는 질문은 결국 하나였던 것 같습니다. "\LaTeX{}의 조판 실력은 갖되, \LaTeX{} 문법의 번거로움은 덜어낼 수 없을까?" org mode도, pandoc markdown도, multimarkdown도 각자의 방식으로 그 질문에 답해주었지만, 매번 어딘가 아쉬운 지점이 남았습니다. 기존 방언들은 애초에 \LaTeX{}을 염두에 두고 설계된 게 아니었으니 당연한 일이기도 합니다.

## 그래서, 방언을 하나 더 만들었습니다

기존 markdown 방언들 사이를 오가며 이것저것 짜깁기하다 보니 어느 순간 "차라리 처음부터 \LaTeX{} 출력을 목적으로 설계된 markdown 방언이 있으면 어떨까" 하는 생각에 이르렀습니다. 겁도 없이 방언을 하나 더 만들어버린 셈인데, markdown 방언이 이미 넘쳐나는 세상에 하나를 더 보태는 게 다소 민망하기도 합니다. 그래도 "나에게 꼭 맞는 신발이 없으면 직접 만들어 신는다"는 마음으로 밀어붙여 봤습니다.

그렇게 태어난 것이 `ndhmd4tex`입니다. 이름 그대로, \LaTeX{}을 향한(for TeX) markdown입니다. org mode의 유연한 구조화 능력, pandoc markdown의 익숙한 문법, txt2pdfebook에서 얻은 "\LaTeX{}은 프린터처럼 다룬다"는 교훈, 이 세 가지 경험을 한 그릇에 담아보려 했습니다. 저자는 markdown의 편안함 속에서 글을 쓰고, \LaTeX{} 특유의 정교한 조판 결과는 그대로 누리는 것, 그것이 이 방언이 지향하는 지점입니다.

## 지금의 `ndhmd4tex`, 0.3.3

버전 번호가 아직 1.0에도 이르지 못한 걸 보면 알 수 있듯, 이건 완성된 제품이라기보다는 계속 다듬어가는 도구에 가깝습니다. 그래도 0.3.3에 이르러서는 "이걸로 실제 문서 몇 편을 무리 없이 뽑아낼 수 있다"는 확신이 생겼습니다. 세 편의 이전 글에서 시도했던 여러 접근을 하나의 일관된 문법 아래 정리했고, \LaTeX{} 문서 특유의 요구사항, 이를테면 각주나 참고문헌, 상호 참조 같은 것들을 markdown의 어휘 안에서 자연스럽게 표현할 수 있도록 신경을 썼습니다.

물론 아직 다듬어야 할 구석도, 채워야 할 빈틈도 적지 않습니다. 다만 "형태를 갖췄다"는 말에는 이제 남에게 보여주고 의견을 들어도 좋을 만큼은 여물었다는 뜻도 담겨 있습니다.

## 앞으로에 대한 기대

거창한 포부는 없습니다. 다만 이 방언이 저처럼 "\LaTeX{}으로 예쁘게 조판은 하고 싶은데, \LaTeX{} 문법과는 계속 씨름하기 싫다"는 분들에게 작게나마 쓸모가 있었으면 합니다. 개인 출판이든, 논문이든, 혹은 그냥 취미로 쓰는 긴 글이든, markdown 한 장으로 시작해서 \LaTeX{}의 손끝에서 마무리되는 흐름을 조금 더 매끄럽게 만드는 것, 그 정도면 충분히 만족스러운 목표입니다.

org mode에서 시작해 pandoc을 거쳐 multimarkdown까지 돌아온 이 여정이, `ndhmd4tex`라는 이름으로 잠정적인 종착지에 닿은 셈입니다. 물론 "잠정적"이라는 단서를 굳이 붙인 이유는, 이 여정이 여기서 끝날 것 같지 않기 때문입니다. 다음 정거장이 어디일지는 저도 아직 모릅니다.
