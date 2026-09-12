@echo off
setlocal
cd /d "%~dp0"
echo [1/3] Installing package + dev deps...
python -m pip install -e .[dev] || exit /b 1
echo [2/3] Running tests...
rem Keep pytest's scratch data in the project.  This also avoids machines where
rem the user's default %%TEMP%% folder has restrictive permissions.
if not exist build mkdir build || exit /b 1
python -m pytest -q --basetemp build\pytest-tmp -p no:cacheprovider || exit /b 1
echo [3/3] Building dist\skyrim-downgrade.exe...
python tools\make_icon.py || exit /b 1
python -m PyInstaller --onefile --console --name skyrim-downgrade --clean --noconfirm ^
  --icon assets\skyrim-downgrader.ico ^
  --collect-submodules pywinauto --collect-submodules comtypes ^
  skyrim_downgrader\__main__.py || exit /b 1
echo Done: dist\skyrim-downgrade.exe
