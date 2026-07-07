@echo off
REM Compilation de CIDRE en executable Windows autonome (Nuitka).
REM Prerequis : .venv avec requirements.txt + Nuitka installes.
REM Resultat : build_exe\CIDRE.exe (fichier unique, distribuable tel quel).

.venv\Scripts\python.exe -m nuitka gui_tk.py ^
    --standalone ^
    --onefile ^
    --enable-plugin=tk-inter ^
    --windows-console-mode=disable ^
    --include-module=openpyxl ^
    --include-package=markdown ^
    --include-module=xlrd ^
    --output-dir=build_exe ^
    --output-filename=CIDRE.exe ^
    --company-name="PURH" ^
    --product-name="CIDRE" ^
    --file-description="CIDRE - Generateur de site statique (Excel vers HTML)" ^
    --product-version=1.0.0 ^
    --assume-yes-for-downloads

echo.
echo Termine. Executable : build_exe\CIDRE.exe
pause
