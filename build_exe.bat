@echo off
REM Compilation des executables Windows autonomes de CIDRE (Nuitka).
REM Prerequis : environnement de compilation prepare avec
REM   .venv\Scripts\python.exe -m pip install -r requirements-build.txt
REM Resultat :
REM   build_exe\CIDRE.exe             (generateur de site, gui_tk.py)
REM   build_exe\CIDRE-Actualites.exe  (editeur d'actualites, actualites_editor.py)
REM   build_exe\CIDRE-ONIX.exe        (validateur ONIX, onix_validator.py)
REM Rapports de compilation : build_exe\reports\<nom>-nuitka-report.xml

setlocal EnableExtensions
pushd "%~dp0" || exit /b 1

set "PYTHON=.venv\Scripts\python.exe"
set "NUITKA_EXPECTED=4.1.3"
set "APP_VERSION=1.0.0"
set "OUT_DIR=build_exe"
set "REPORT_DIR=%OUT_DIR%\reports"

REM --- Verifications prealables -------------------------------------------

if not exist "%PYTHON%" (
    echo ERREUR : %PYTHON% introuvable.
    echo Creez l'environnement virtuel puis installez les dependances :
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements-build.txt
    popd & exit /b 1
)

set "NUITKA_VERSION="
for /f "delims=" %%v in ('"%PYTHON%" -m nuitka --version 2^>nul') do (
    if not defined NUITKA_VERSION set "NUITKA_VERSION=%%v"
)

if not defined NUITKA_VERSION (
    echo ERREUR : Nuitka n'est pas installe dans .venv.
    echo Preparez l'environnement de compilation avec :
    echo     .venv\Scripts\python.exe -m pip install -r requirements-build.txt
    popd & exit /b 1
)

if not "%NUITKA_VERSION%"=="%NUITKA_EXPECTED%" (
    echo ERREUR : Nuitka %NUITKA_VERSION% installe, %NUITKA_EXPECTED% attendu ^(requirements-build.txt^).
    echo Alignez l'environnement de compilation avec :
    echo     .venv\Scripts\python.exe -m pip install -r requirements-build.txt
    popd & exit /b 1
)

if not exist "%REPORT_DIR%" mkdir "%REPORT_DIR%"

REM --- Compilations ---------------------------------------------------------

call :build_one gui_tk.py CIDRE "CIDRE - Generateur de site statique (Excel vers HTML)" ^
    "--include-package=markdown --include-package=openpyxl --include-package=xlrd"
if errorlevel 1 ( popd & exit /b 1 )

call :build_one actualites_editor.py CIDRE-Actualites "CIDRE - Editeur d'actualites (feuille ACTUS)" ""
if errorlevel 1 ( popd & exit /b 1 )

call :build_one onix_validator.py CIDRE-ONIX "CIDRE - Validateur ONIX (onixcheck)" ^
    "--include-package=onixcheck --include-package-data=onixcheck"
if errorlevel 1 ( popd & exit /b 1 )

echo.
echo Termine. Executables :
echo     %OUT_DIR%\CIDRE.exe
echo     %OUT_DIR%\CIDRE-Actualites.exe
echo     %OUT_DIR%\CIDRE-ONIX.exe
popd & exit /b 0

REM --- Sous-routine : compilation d'un executable ---------------------------
REM %1 = script d'entree, %2 = nom de l'exe (sans .exe),
REM %3 = description Windows, %4 = options Nuitka supplementaires.

:build_one
set "SCRIPT=%~1"
set "STEM=%~n1"
set "NAME=%~2"
set "DESCRIPTION=%~3"
set "EXTRA_OPTIONS=%~4"
set "EXE=%OUT_DIR%\%NAME%.exe"
set "REPORT=%REPORT_DIR%\%NAME%-nuitka-report.xml"

echo.
echo ============================================================
echo Compilation : %SCRIPT% -^> %EXE%
echo ============================================================

REM Ecarter l'ancien executable pour qu'il ne passe pas pour le nouveau.
if exist "%EXE%" del /f "%EXE%"
if exist "%EXE%" (
    echo ERREUR : impossible de supprimer l'ancien %EXE% ^(fichier en cours d'utilisation ?^).
    exit /b 1
)

REM Nettoyer les repertoires intermediaires de cette compilation uniquement.
for %%d in ("%OUT_DIR%\%STEM%.build" "%OUT_DIR%\%STEM%.dist" "%OUT_DIR%\%STEM%.onefile-build") do (
    if exist "%%~d" rd /s /q "%%~d"
)

"%PYTHON%" -m nuitka "%SCRIPT%" ^
    --mode=onefile ^
    --enable-plugin=tk-inter ^
    --windows-console-mode=disable ^
    --assume-yes-for-downloads ^
    --output-dir="%OUT_DIR%" ^
    --output-filename="%NAME%.exe" ^
    --report="%REPORT%" ^
    --company-name="PURH" ^
    --product-name="%NAME%" ^
    --file-description="%DESCRIPTION%" ^
    --product-version=%APP_VERSION% ^
    --file-version=%APP_VERSION% ^
    %EXTRA_OPTIONS%

if errorlevel 1 (
    echo.
    echo ERREUR : Nuitka a echoue pour %SCRIPT%.
    echo Rapport de compilation : %REPORT%
    exit /b 1
)

if not exist "%EXE%" (
    echo.
    echo ERREUR : Nuitka a rendu la main sans erreur mais %EXE% est absent.
    echo Rapport de compilation : %REPORT%
    exit /b 1
)

echo OK : %EXE%
exit /b 0
