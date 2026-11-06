#!/bin/bash

# ---------------------------------------------------------------------------
# 1. 옵션 파싱
#    --bin=<dir|TEX>   : 설치/삭제 대상 바이너리 디렉터리 (설치 시와 동일한 의미)
#    --uninstall/--purge : 설치된 파일과 리소스/설정 폴더를 모두 삭제
#    --yes / -y        : 삭제 확인 프롬프트 생략
# ---------------------------------------------------------------------------
BIN_ARG=""
MODE="install"
ASSUME_YES=0

for i in "$@"; do
  case $i in
    --bin=*)
      BIN_ARG="${i#*=}"
      ;;
    --uninstall|--purge)
      MODE="uninstall"
      ;;
    --yes|-y)
      ASSUME_YES=1
      ;;
    *)
      ;;
  esac
done

# 운영체제 감지
OS="$(uname -s)"

# sudo 사용 여부 확인하여 실제 사용자 홈 디렉터리 설정
if [ -n "$SUDO_USER" ]; then
    USER_HOME=$(eval echo ~"$SUDO_USER")
else
    USER_HOME="$HOME"
fi

# ndhmd4tex 스크립트가 OS와 무관하게 훑는 세 위치
CONFIG_ROOTS=(
    "$USER_HOME/ndhmd4tex"
    "$USER_HOME/.config/ndhmd4tex"
    "$USER_HOME/Library/ndhmd4tex"
)

# 기본 설치 경로(BASE_DIR)는 OS에 따라 하나로 결정
if [ "$OS" = "Darwin" ]; then
    BASE_DIR="$USER_HOME/Library/ndhmd4tex"
elif [ "$OS" = "Linux" ]; then
    BASE_DIR="$USER_HOME/.config/ndhmd4tex"
else
    echo "Unsupported OS: $OS"
    exit 1
fi

# --bin 으로 설치되는 파일 목록 (ndhmdsync 확장자는 자동 판별)
BIN_FILES=("ndhmd4tex" "ndhmd-default.nmd")

resolve_bin_dir() {
    if [ -n "$BIN_ARG" ]; then
        if [ "$BIN_ARG" = "TEX" ]; then
            local tex_bin
            tex_bin=$(command -v pdflatex)
            if [ -z "$tex_bin" ]; then
                echo "[Error] Could not find TeX installation. Please specify the path directly." >&2
                exit 1
            fi
            dirname "$tex_bin"
        else
            printf '%s\n' "$BIN_ARG"
        fi
    else
        # --bin 이 주어지지 않으면 PATH 상에 이미 설치된 ndhmd4tex 를 찾아 그 위치를 사용
        local found
        found=$(command -v ndhmd4tex 2>/dev/null)
        if [ -n "$found" ]; then
            dirname "$found"
        fi
    fi
}

# ===========================================================================
# UNINSTALL / PURGE
# ===========================================================================
if [ "$MODE" = "uninstall" ]; then
    echo "== ndhmd4tex Uninstaller =="
    BIN_DIR=$(resolve_bin_dir)

    if [ -n "$BIN_DIR" ]; then
        echo "Binary directory: $BIN_DIR"
    else
        echo "[Warn] Could not determine binary install directory automatically."
        echo "       Specify it with --bin=<path> (or --bin=TEX) if you also want the binaries removed."
    fi
    echo ""

    echo "This will remove:"
    if [ -n "$BIN_DIR" ]; then
        for f in "${BIN_FILES[@]}" "ndhmdsync"; do
            [ -e "$BIN_DIR/$f" ] && echo "  - $BIN_DIR/$f"
        done
    fi
    for root in "${CONFIG_ROOTS[@]}"; do
        [ -d "$root" ] && echo "  - $root (전체 폴더)"
    done
    echo ""

    if [ "$ASSUME_YES" -ne 1 ]; then
        read -r -p "Proceed with uninstall? [y/N] " ans
        case "$ans" in
            [yY]|[yY][eE][sS]) ;;
            *) echo "Aborted."; exit 0 ;;
        esac
    fi

    if [ -n "$BIN_DIR" ]; then
        for f in "${BIN_FILES[@]}" "ndhmdsync"; do
            if [ -e "$BIN_DIR/$f" ]; then
                rm -f "$BIN_DIR/$f" && echo "Removed $BIN_DIR/$f"
            fi
        done
    fi

    for root in "${CONFIG_ROOTS[@]}"; do
        if [ -d "$root" ]; then
            rm -rf "$root" && echo "Removed $root"
        fi
    done

    echo ""
    echo "Uninstall complete!"
    exit 0
fi

# ===========================================================================
# INSTALL (기존 동작)
# ===========================================================================

# 2. 리소스, 가이드, 설정 파일 복사
echo "Installing resources to: $BASE_DIR/resources"
mkdir -p "$BASE_DIR/resources"
[ -d "Resources" ] && cp -a Resources/. "$BASE_DIR/resources/"

echo "Installing guides to: $BASE_DIR/guide"
mkdir -p "$BASE_DIR/guide"
[ -d "guide" ] && cp -a guide/. "$BASE_DIR/guide/"

echo "Installing config examples to: $BASE_DIR/config"
mkdir -p "$BASE_DIR/config"
[ -f "config_example/ndhmdsync.ini.example" ] && cp "config_example/ndhmdsync.ini.example" "$BASE_DIR/config/"

echo ""

# 3. --bin 옵션 처리
if [ -n "$BIN_ARG" ]; then
    if [ "$BIN_ARG" = "TEX" ]; then
        echo "Detecting TeX binary directory..."
        TEX_BIN=$(command -v pdflatex)
        if [ -z "$TEX_BIN" ]; then
            echo "[Error] Could not find TeX installation. Please specify the path directly."
            exit 1
        fi
        BIN_DIR=$(dirname "$TEX_BIN")
    else
        BIN_DIR="$BIN_ARG"
    fi

    echo "Installing binaries to: $BIN_DIR"

    if [ ! -d "$BIN_DIR" ]; then
        echo "[Error] Directory does not exist: $BIN_DIR"
        exit 1
    fi

    if [ ! -w "$BIN_DIR" ]; then
        echo ""
        echo "[Error] Permission denied writing to $BIN_DIR."
        echo "Please run this script with sudo (sudo로 실행하세요)."
        exit 1
    fi

    # 파일 복사, 이름 변경 및 실행 권한 부여
    cp "script/ndhmd4tex.py" "$BIN_DIR/ndhmd4tex" || { echo "[Error] Failed to copy ndhmd4tex.py"; exit 1; }
    chmod +x "$BIN_DIR/ndhmd4tex"

    cp "script/ndhmdsync.py" "$BIN_DIR/ndhmdsync" || { echo "[Error] Failed to copy ndhmdsync.py"; exit 1; }
    chmod +x "$BIN_DIR/ndhmdsync"

    cp "script/ndhmd-default.nmd" "$BIN_DIR/" || { echo "[Error] Failed to copy ndhmd-default.nmd"; exit 1; }

    echo "Successfully installed binaries and ndhmd-default.nmd to $BIN_DIR"
fi

echo ""
echo "Installation complete!"
