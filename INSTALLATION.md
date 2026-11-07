# ndhmd4tex 설치 안내

python script를 `python`으로 직접 실행하는 경우(가상환경 등)는 설명하지 않는다.
다음 설명은 `ndhmd4tex` 및 `ndhmdsync` 명령을 터미널 어디에서나 실행하려 하는 경우에 대한 것이다.

## 1. 설치 스크립트 이용 (권장)

압축 해제한 파일 묶음에서 디렉터리 구조를 변경하지 않고 설치 스크립트를 실행한다. 기본적으로 `Resources` 폴더의 내용을 OS 환경에 맞는 위치로 복사하며, 명령행 옵션을 통해 실행 파일(`ndhmd4tex`, `ndhmdsync`)과 기본 설정 파일(`ndhmd-default.nmd`)까지 한 번에 복사할 수 있다.

### 실행 파일 동시 설치 옵션 (`--bin`)

- **`--bin=TEX`**: 시스템에 설치된 TeX 엔진(TeX Live, MiKTeX 등)의 바이너리 폴더를 자동으로 찾아 3개의 파일을 복사한다.
- **`--bin="경로"`**: 사용자가 지정한 경로(예: `/usr/local/bin` 또는 `C:\Users\NAME\bin`)로 3개의 파일을 복사한다.
- **옵션 생략**: `--bin` 옵션을 주지 않으면 기존과 동일하게 `Resources` 폴더만 복사된다.

> **주의:** 지정된 바이너리 경로에 쓰기 권한이 없는 경우 복사가 실패할 수 있다. 이 경우 스크립트가 경고 메시지와 함께 종료되며, Windows는 **'관리자 권한'**으로, macOS/Linux는 **`sudo`**를 사용하여 다시 실행해야 한다.

### OS별 설치 방법

**Windows:**
명령 프롬프트를 열고 스크립트를 실행한다. (시스템 경로에 설치할 경우 명령 프롬프트를 '관리자 권한으로 실행'해야 한다.)
```bat
> .\install_ndhmd.bat --bin=TEX
```

**macOS / Linux:**
`python3`과 `pip3`이 동작하는 환경으로 간주한다. 스크립트 복사 전, PyYAML을 **전역적으로** 설치해야 한다.
```bash
$ pip3 install pyyaml --break-system-packages
```
이후 스크립트에 실행 권한을 주고 실행한다. (시스템 경로 복사 시 `sudo` 필요)
```bash
$ chmod +x install_ndhmd.sh
$ sudo ./install_ndhmd.bash --bin=TEX
```

## 언인스톨 

```bat
> .\install_ndhmd.bat --uninstall 
```

macOS/Linux에서는

```bash
$ bash ./install_ndhmd.bash --uninstall
```

스크립트 해석기가 `bash`임에 주의할 것.

---

여기까지 진행해서 성공했다면 이후 설명은 불필요하다.
참고를 목적으로 유지한다.

---

## 2. 수작업 설치 (참고용)

### Windows

**실행 파일 설치:**

  - `script\ndhmd4tex.exe`, `script\ndhmdsync.py`, `script\ndhmd-default.nmd` 3개의 파일을 `PATH`가 걸려 있는 위치에 가져다 둔다.
  - **[사용자 환경 변수]**에서 새로운 폴더를 추가하거나,
  - 이미 `PATH` 변수에 포함된 폴더(예: `C:\TeXLive\2026\bin\windows`)에 복사한다.
  - `ndhmdsync.py`는 (위의 설치 스크립트를 사용하지 않았을 때) `python ndhmdsync.py` 형식으로 실행하낟.

**Resources 설치:**

  - 홈 디렉터리 아래 `ndhmd4tex\resources`라는 폴더를 만든다. 사용자 이름이 `USERNAME`이라면 `C:\Users\USERNAME\ndhmd4tex\resources`.
  - 배포 파일 묶음의 `Resources` 폴더 아래 모든 파일을 이곳으로 복사한다.
  - 사용자가 직접 만든 설정 파일(`.yaml`, `.nmd`)도 이곳으로 복사한다.

### macOS / Linux

**실행 파일 설치:**

  - `python3`은 설치되어 있고 `python3`과 `pip3`이 동작하는 것으로 간주한다.
  - PyYAML을 **전역적으로** 설치한다.
```bash
$ pip3 install pyyaml --break-system-packages
```
  - `script/ndhmd4tex.py`와 `script/ndhmdsync.py` 스크립트의 확장자를 없애고 이름을 변경한 다음 실행 권한을 준다.
```bash
$ mv script/ndhmd4tex.py ndhmd4tex
$ mv script/ndhmdsync.py ndhmdsync
$ chmod a+x ndhmd4tex ndhmdsync
```
  - `/usr/local/bin` 디렉터리에 두 개의 스크립트와 기본 설정 파일 `script/ndhmd-default.nmd` 파일을 복사한다.
```bash
$ sudo cp ./ndhmd4tex ./ndhmdsync /usr/local/bin/ 
$ sudo cp script/ndhmd-default.nmd /usr/local/bin/
```

**Resources 설치:**

- **macOS:** `~/Library/ndhmd4tex/resources` 폴더를 만들고 배포 파일 묶음의 `Resources` 폴더 아래의 파일을 이 위치로 복사한다.
```bash
$ mkdir -p ~/Library/ndhmd4tex/resources 
$ cp Resources/* ~/Library/ndhmd4tex/resources/
```
- **Linux:** 기본적으로 macOS에서 설명한 바와 같고, 다만 설정 파일의 위치를 `~/.config/ndhmd4tex/resources`로 하는 것이 좋다.
```bash
$ mkdir -p ~/.config/ndhmd4tex/resources 
$ cp Resources/* ~/.config/ndhmd4tex/resources/
```
