@echo off
setlocal enabledelayedexpansion

:: ===========================================================================
:: 1. 옵션 파싱
::    --bin=<dir|TEX>      : 설치/삭제 대상 바이너리 디렉터리 (설치 시와 동일한 의미)
::    --uninstall / --purge : 설치된 파일과 리소스/설정 폴더를 모두 삭제
::    --yes / -y            : 삭제 확인 프롬프트 생략
:: ===========================================================================
set "BIN_ARG="
set "MODE=install"
set "ASSUME_YES=0"

:parse_args
if "%~1"=="" goto :end_args
set "arg=%~1"

if /i "!arg!"=="--bin" (
    set "BIN_ARG=%~2"
    shift
    shift
    goto :parse_args
)

if /i "!arg:~0,6!"=="--bin=" (
    set "BIN_ARG=!arg:~6!"
    shift
    goto :parse_args
)

if /i "!arg!"=="--uninstall" (
    set "MODE=uninstall"
    shift
    goto :parse_args
)

if /i "!arg!"=="--purge" (
    set "MODE=uninstall"
    shift
    goto :parse_args
)

if /i "!arg!"=="--yes" (
    set "ASSUME_YES=1"
    shift
    goto :parse_args
)

if /i "!arg!"=="-y" (
    set "ASSUME_YES=1"
    shift
    goto :parse_args
)

shift
goto :parse_args
:end_args

if defined BIN_ARG (
    set "BIN_ARG=!BIN_ARG:"=!"
)

if /i "!MODE!"=="uninstall" goto :do_uninstall
goto :do_install

:: ===========================================================================
:: UNINSTALL / PURGE
:: ===========================================================================
:do_uninstall
echo == ndhmd4tex Uninstaller ==
echo.

set "BIN_DIR="
if defined BIN_ARG (
    if /i not "!BIN_ARG!"=="TEX" (
        set "BIN_DIR=!BIN_ARG!"
    ) else (
        echo Detecting TeX binary directory...
        for /f "delims=" %%I in ('where pdflatex 2^>nul') do (
            if "!BIN_DIR!"=="" set "BIN_DIR=%%~dpI"
        )
        if "!BIN_DIR!"=="" (
            echo [Error] Could not find TeX installation. Please specify the path directly.
            exit /b 1
        )
        if "!BIN_DIR:~-1!"=="\" set "BIN_DIR=!BIN_DIR:~0,-1!"
    )
) else (
    rem --bin 이 없으면 PATH 상에 이미 설치된 ndhmd4tex.exe 를 찾아 그 위치를 사용
    for /f "delims=" %%I in ('where ndhmd4tex 2^>nul') do (
        if "!BIN_DIR!"=="" set "BIN_DIR=%%~dpI"
    )
    if defined BIN_DIR (
        if "!BIN_DIR:~-1!"=="\" set "BIN_DIR=!BIN_DIR:~0,-1!"
    )
)

if defined BIN_DIR (
    echo Binary directory: !BIN_DIR!
) else (
    echo [Warn] Could not determine binary install directory automatically.
    echo        Specify it with --bin=^<path^> ^(or --bin=TEX^) if you also want the binaries removed.
)
echo.

echo This will remove:
if defined BIN_DIR (
    if exist "!BIN_DIR!\ndhmd4tex.exe" echo   - !BIN_DIR!\ndhmd4tex.exe
    if exist "!BIN_DIR!\ndhmd4tex.py" echo   - !BIN_DIR!\ndhmd4tex.py
    if exist "!BIN_DIR!\ndhmd4tex.cmd" echo   - !BIN_DIR!\ndhmd4tex.cmd
    if exist "!BIN_DIR!\ndhmd2html.exe" echo   - !BIN_DIR!\ndhmd2html.exe
    if exist "!BIN_DIR!\ndhmd2html.py" echo   - !BIN_DIR!\ndhmd2html.py
    if exist "!BIN_DIR!\ndhmd2html.cmd" echo   - !BIN_DIR!\ndhmd2html.cmd
    if exist "!BIN_DIR!\ndhmdsync.exe" echo   - !BIN_DIR!\ndhmdsync.exe
    if exist "!BIN_DIR!\ndhmdsync.py" echo   - !BIN_DIR!\ndhmdsync.py
    if exist "!BIN_DIR!\ndhmdsync.cmd" echo   - !BIN_DIR!\ndhmdsync.cmd
    if exist "!BIN_DIR!\ndhmd-default.nmd" echo   - !BIN_DIR!\ndhmd-default.nmd
)
if exist "%USERPROFILE%\ndhmd4tex" echo   - %USERPROFILE%\ndhmd4tex ^(remove all^)
if exist "%USERPROFILE%\.config\ndhmd4tex" echo   - %USERPROFILE%\.config\ndhmd4tex ^(remove all^)
if exist "%USERPROFILE%\Library\ndhmd4tex" echo   - %USERPROFILE%\Library\ndhmd4tex ^(remove all^)
echo.

if "!ASSUME_YES!"=="1" goto :confirmed
set "ANSWER="
set /p "ANSWER=Proceed with uninstall? [y/N] "
if /i not "!ANSWER!"=="y" (
    echo Aborted.
    exit /b 0
)

:confirmed
if defined BIN_DIR (
    if exist "!BIN_DIR!\ndhmd4tex.exe" (del /f /q "!BIN_DIR!\ndhmd4tex.exe" && echo Removed !BIN_DIR!\ndhmd4tex.exe)
    if exist "!BIN_DIR!\ndhmd4tex.py" (del /f /q "!BIN_DIR!\ndhmd4tex.py" && echo Removed !BIN_DIR!\ndhmd4tex.py)
    if exist "!BIN_DIR!\ndhmd4tex.cmd" (del /f /q "!BIN_DIR!\ndhmd4tex.cmd" && echo Removed !BIN_DIR!\ndhmd4tex.cmd)
    if exist "!BIN_DIR!\ndhmd2html.exe" (del /f /q "!BIN_DIR!\ndhmd2html.exe" && echo Removed !BIN_DIR!\ndhmd2html.exe)
    if exist "!BIN_DIR!\ndhmd2html.py" (del /f /q "!BIN_DIR!\ndhmd2html.py" && echo Removed !BIN_DIR!\ndhmd2html.py)
    if exist "!BIN_DIR!\ndhmd2html.cmd" (del /f /q "!BIN_DIR!\ndhmd2html.cmd" && echo Removed !BIN_DIR!\ndhmd2html.cmd)
    if exist "!BIN_DIR!\ndhmdsync.exe" (del /f /q "!BIN_DIR!\ndhmdsync.exe" && echo Removed !BIN_DIR!\ndhmdsync.exe)
    if exist "!BIN_DIR!\ndhmdsync.py" (del /f /q "!BIN_DIR!\ndhmdsync.py" && echo Removed !BIN_DIR!\ndhmdsync.py)
    if exist "!BIN_DIR!\ndhmdsync.cmd" (del /f /q "!BIN_DIR!\ndhmdsync.cmd" && echo Removed !BIN_DIR!\ndhmdsync.cmd)
    if exist "!BIN_DIR!\ndhmd-default.nmd" (del /f /q "!BIN_DIR!\ndhmd-default.nmd" && echo Removed !BIN_DIR!\ndhmd-default.nmd)
)

if exist "%USERPROFILE%\ndhmd4tex" (rmdir /s /q "%USERPROFILE%\ndhmd4tex" && echo Removed %USERPROFILE%\ndhmd4tex)
if exist "%USERPROFILE%\.config\ndhmd4tex" (rmdir /s /q "%USERPROFILE%\.config\ndhmd4tex" && echo Removed %USERPROFILE%\.config\ndhmd4tex)
if exist "%USERPROFILE%\Library\ndhmd4tex" (rmdir /s /q "%USERPROFILE%\Library\ndhmd4tex" && echo Removed %USERPROFILE%\Library\ndhmd4tex)

echo.
echo Uninstall complete!
pause
exit /b 0

:: ===========================================================================
:: INSTALL (기존 동작)
:: ===========================================================================
:do_install

:: 2. 리소스, 가이드, 설정 파일 복사
set "BASE_DIR=%USERPROFILE%\ndhmd4tex"

echo Installing resources to: !BASE_DIR!\resources
if not exist "!BASE_DIR!\resources" mkdir "!BASE_DIR!\resources"
if exist "Resources\*" xcopy "Resources\*.*" "!BASE_DIR!\resources\" /Y /E /I >nul

echo Installing guides to: !BASE_DIR!\guide
if not exist "!BASE_DIR!\guide" mkdir "!BASE_DIR!\guide"
if exist "guide\*" xcopy "guide\*.*" "!BASE_DIR!\guide\" /Y /E /I >nul

echo Installing config examples to: !BASE_DIR!\config
if not exist "!BASE_DIR!\config" mkdir "!BASE_DIR!\config"
if exist "config_example\ndhmdsync.ini.example" copy /Y "config_example\ndhmdsync.ini.example" "!BASE_DIR!\config\" >nul

echo.

:: 3. --bin 옵션 처리
if not defined BIN_ARG goto :skip_bin

if /i not "!BIN_ARG!"=="TEX" (
    set "BIN_DIR=!BIN_ARG!"
    goto :check_dir
)

echo Detecting TeX binary directory...
set "BIN_DIR="
for /f "delims=" %%I in ('where pdflatex 2^>nul') do (
    if "!BIN_DIR!"=="" set "BIN_DIR=%%~dpI"
)

if "!BIN_DIR!"=="" (
    echo [Error] Could not find TeX installation. Please specify the path directly.
    exit /b 1
)
if "!BIN_DIR:~-1!"=="\" set "BIN_DIR=!BIN_DIR:~0,-1!"

:check_dir
echo Installing binary to: !BIN_DIR!

:: 대상 폴더가 존재하는지 확인
if exist "!BIN_DIR!" goto :dir_ok
echo [Error] Directory does not exist: !BIN_DIR!
exit /b 1

:dir_ok
:: 쓰기 권한 테스트
copy /y NUL "!BIN_DIR!\.test_write" >nul 2>&1
if not errorlevel 1 goto :write_ok

echo.
echo [Error] Permission denied writing to !BIN_DIR!.
echo Please run this script as Administrator (관리자 권한으로 실행하세요).
exit /b 1

:write_ok
del "!BIN_DIR!\.test_write" >nul 2>&1

:: --- ndhmd4tex 복사 및 .cmd 생성 분기 처리 시작 ---
:: .exe는 script\ 가 아니라 pyinstaller\ 아래에서 찾는다
if exist "pyinstaller\ndhmd4tex.exe" (
    copy /Y "pyinstaller\ndhmd4tex.exe" "!BIN_DIR!\" >nul
    if errorlevel 1 goto :copy_err
) else if exist "script\ndhmd4tex.py" (
    copy /Y "script\ndhmd4tex.py" "!BIN_DIR!\" >nul
    if errorlevel 1 goto :copy_err
    echo [Info] ndhmd4tex.exe not found. Copied ndhmd4tex.py instead.

    :: ndhmd4tex.cmd 생성 (괄호 중첩 버그를 피하기 위해 한 줄씩 출력)
    echo @echo off> "!BIN_DIR!\ndhmd4tex.cmd"
    echo python "%%~dp0ndhmd4tex.py" %%*>> "!BIN_DIR!\ndhmd4tex.cmd"

    if errorlevel 1 (
        echo [Error] Failed to create ndhmd4tex.cmd wrapper script.
        goto :copy_err
    )
    echo [Info] Created ndhmd4tex.cmd wrapper in !BIN_DIR!
) else (
    echo [Error] Could not find ndhmd4tex.exe ^(pyinstaller\^) or ndhmd4tex.py ^(script\^).
    goto :copy_err
)
:: --- ndhmd4tex 복사 및 .cmd 생성 분기 처리 끝 ---

:: --- ndhmd2html 복사 및 .cmd 생성 분기 처리 시작 ---
:: .exe는 script\ 가 아니라 pyinstaller\ 아래에서 찾는다 (ndhmd4tex와 동일한 방식)
if exist "pyinstaller\ndhmd2html.exe" (
    copy /Y "pyinstaller\ndhmd2html.exe" "!BIN_DIR!\" >nul
    if errorlevel 1 goto :copy_err
) else if exist "script\ndhmd2html.py" (
    copy /Y "script\ndhmd2html.py" "!BIN_DIR!\" >nul
    if errorlevel 1 goto :copy_err
    echo [Info] ndhmd2html.exe not found. Copied ndhmd2html.py instead.

    :: ndhmd2html.cmd 생성 (괄호 중첩 버그를 피하기 위해 한 줄씩 출력)
    echo @echo off> "!BIN_DIR!\ndhmd2html.cmd"
    echo python "%%~dp0ndhmd2html.py" %%*>> "!BIN_DIR!\ndhmd2html.cmd"

    if errorlevel 1 (
        echo [Error] Failed to create ndhmd2html.cmd wrapper script.
        goto :copy_err
    )
    echo [Info] Created ndhmd2html.cmd wrapper in !BIN_DIR!
) else (
    echo [Error] Could not find ndhmd2html.exe ^(pyinstaller\^) or ndhmd2html.py ^(script\^).
    goto :copy_err
)
:: --- ndhmd2html 복사 및 .cmd 생성 분기 처리 끝 ---

:: --- ndhmdsync 복사 및 .cmd 생성 분기 처리 시작 ---
:: .exe는 pyinstaller\ 를 먼저 찾고, 없으면 script\ 도 확인한다
if exist "pyinstaller\ndhmdsync.exe" (
    copy /Y "pyinstaller\ndhmdsync.exe" "!BIN_DIR!\" >nul
    if errorlevel 1 goto :copy_err
) else if exist "script\ndhmdsync.exe" (
    copy /Y "script\ndhmdsync.exe" "!BIN_DIR!\" >nul
    if errorlevel 1 goto :copy_err
) else if exist "script\ndhmdsync.py" (
    copy /Y "script\ndhmdsync.py" "!BIN_DIR!\" >nul
    if errorlevel 1 goto :copy_err
    echo [Info] ndhmdsync.exe not found. Copied ndhmdsync.py instead.

    :: ndhmdsync.cmd 생성 (괄호 중첩 버그를 피하기 위해 한 줄씩 출력)
    echo @echo off> "!BIN_DIR!\ndhmdsync.cmd"
    echo python "%%~dp0ndhmdsync.py" %%*>> "!BIN_DIR!\ndhmdsync.cmd"

    if errorlevel 1 (
        echo [Error] Failed to create ndhmdsync.cmd wrapper script.
        goto :copy_err
    )
    echo [Info] Created ndhmdsync.cmd wrapper in !BIN_DIR!
) else (
    echo [Error] Could not find ndhmdsync.exe or ndhmdsync.py in pyinstaller or script directory.
    goto :copy_err
)
:: --- ndhmdsync 복사 및 .cmd 생성 분기 처리 끝 ---

copy /Y "script\ndhmd-default.nmd" "!BIN_DIR!\" >nul
if errorlevel 1 goto :copy_err

goto :copy_ok

:copy_err
echo [Error] Failed to copy binary files.
exit /b 1

:copy_ok
echo Successfully copied binaries and ndhmd-default.nmd to !BIN_DIR!

:skip_bin
echo.
echo Installation complete!
pause
