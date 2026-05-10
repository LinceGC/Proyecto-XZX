@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul
title Spryta Build Script

echo.
echo ============================================================
echo  SPRYTA - SCRIPT DE BUILD COMPLETO (RUNTIMES AISLADOS)
echo ============================================================
echo.

if not exist "setting.pyw" (
    echo ERROR: No se encontro setting.pyw
    pause
    exit /b 1
)
if not exist "main.pyw" (
    echo ERROR: No se encontro main.pyw
    pause
    exit /b 1
)
if not exist "spryta_startup.pyw" (
    echo ERROR: No se encontro spryta_startup.pyw
    pause
    exit /b 1
)
if not exist "assets\icons\icon.ico" (
    echo ERROR: No se encontro assets\icons\icon.ico
    pause
    exit /b 1
)

echo [PASO 1/7] Instalando dependencias de Python...
echo.

pip install --upgrade pip --quiet
pip install --upgrade ^
    pyinstaller ^
    PySide6 ^
    pygame ^
    psutil ^
    Pillow ^
    opencv-python ^
    keyboard ^
    pywin32

if %errorlevel% neq 0 (
    echo ERROR: Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

pip install --upgrade gputil --quiet 2>nul
echo  gputil: instalado o saltado (es opcional)
echo.
echo  OK - Dependencias instaladas.
echo.

echo [PASO 2/7] Creando archivos __init__.py para PyInstaller...

if not exist "src\tools\__init__.py" (
    type nul > "src\tools\__init__.py"
    echo  Creado: src\tools\__init__.py
)
if not exist "src\ui\__init__.py" (
    type nul > "src\ui\__init__.py"
    echo  Creado: src\ui\__init__.py
)

echo  OK
echo.

echo [PASO 3/7] Limpiando builds anteriores...

if exist "build"       rmdir /s /q "build"
if exist "dist_temp"   rmdir /s /q "dist_temp"
if exist "dist\Spryta" rmdir /s /q "dist\Spryta"

echo  OK
echo.

echo [PASO 4/7] Compilando main.exe (main.pyw) en runtime aislado...
echo.

pyinstaller main.spec ^
    --distpath "dist_temp\sprite" ^
    --workpath "build\sprite" ^
    --noconfirm

if %errorlevel% neq 0 (
    echo ERROR: Fallo la compilacion de main.pyw
    pause
    exit /b 1
)

echo.
echo  OK - main.exe compilado.
echo.

echo [PASO 5/7] Compilando Spryta.exe (setting.pyw)...
echo.

pyinstaller setting.spec ^
    --distpath "dist_temp\settings" ^
    --workpath "build\settings" ^
    --noconfirm

if %errorlevel% neq 0 (
    echo ERROR: Fallo la compilacion de setting.pyw
    pause
    exit /b 1
)

echo.
echo  OK - Spryta.exe compilado.
echo.

echo [PASO 6/7] Compilando spryta_startup.exe (spryta_startup.pyw) en runtime aislado...
echo.

pyinstaller startup.spec ^
    --distpath "dist_temp\startup" ^
    --workpath "build\startup" ^
    --noconfirm

if %errorlevel% neq 0 (
    echo ERROR: Fallo la compilacion de spryta_startup.pyw
    pause
    exit /b 1
)

echo.
echo  OK - spryta_startup.exe compilado.
echo.

echo [PASO 7/7] Ensamblando distribucion final en dist\Spryta\ (SIN mezclar _internal)...

set "OUT=dist\Spryta"
mkdir "%OUT%" 2>nul

set "SETTINGS_DIR="
set "SPRITE_DIR="
set "STARTUP_DIR="

if exist "dist_temp\settings\Spryta\Spryta.exe" set "SETTINGS_DIR=dist_temp\settings\Spryta"
if exist "dist_temp\settings\Spryta.exe" set "SETTINGS_DIR=dist_temp\settings"

if exist "dist_temp\sprite\main\main.exe" set "SPRITE_DIR=dist_temp\sprite\main"
if exist "dist_temp\sprite\main.exe" set "SPRITE_DIR=dist_temp\sprite"

if exist "dist_temp\startup\spryta_startup\spryta_startup.exe" set "STARTUP_DIR=dist_temp\startup\spryta_startup"
if exist "dist_temp\startup\spryta_startup.exe" set "STARTUP_DIR=dist_temp\startup"

if "%SETTINGS_DIR%"=="" (
    echo ERROR: No se pudo localizar salida de setting.spec
    pause
    exit /b 1
)
if "%SPRITE_DIR%"=="" (
    echo ERROR: No se pudo localizar salida de main.spec
    pause
    exit /b 1
)
if "%STARTUP_DIR%"=="" (
    echo ERROR: No se pudo localizar salida de startup.spec
    pause
    exit /b 1
)

REM --- Copiar Spryta como base (runtime propio de Settings) ---
xcopy /e /y /q "%SETTINGS_DIR%\*" "%OUT%\" > nul
if %errorlevel% neq 0 (
    echo ERROR: No se pudo copiar runtime de Spryta
    pause
    exit /b 1
)
echo  Copiado: runtime de Spryta

REM --- Copiar main runtime aislado ---
mkdir "%OUT%\main_runtime" 2>nul
xcopy /e /y /q "%SPRITE_DIR%\*" "%OUT%\main_runtime\" > nul
if %errorlevel% neq 0 (
    echo ERROR: No se pudo copiar runtime de main
    pause
    exit /b 1
)
echo  Copiado: main_runtime\ (main.exe + _internal)

REM --- Copiar startup runtime aislado ---
mkdir "%OUT%\startup_runtime" 2>nul
xcopy /e /y /q "%STARTUP_DIR%\*" "%OUT%\startup_runtime\" > nul
if %errorlevel% neq 0 (
    echo ERROR: No se pudo copiar runtime de startup
    pause
    exit /b 1
)
echo  Copiado: startup_runtime\ (spryta_startup.exe + _internal)

REM --- Copiar assets ---
xcopy /e /y /q "assets" "%OUT%\assets\" > nul
echo  Copiada: carpeta assets\

REM --- Crear carpetas vacias ---
mkdir "%OUT%\Audio"   2>nul
mkdir "%OUT%\sprites" 2>nul
mkdir "%OUT%\data"    2>nul
echo  Creadas: carpetas Audio\, sprites\, data\

echo.
echo ============================================================
echo  BUILD COMPLETADO CON EXITO
echo.
echo  Distribucion lista en:
echo    %OUT%\
echo.
echo  Contenido:
echo    Spryta.exe                      ^<-- interfaz principal
echo    main_runtime\main.exe          ^<-- runtime aislado de sprites
echo    main_runtime\_internal\...     ^<-- DLLs/deps SOLO de main
echo    startup_runtime\spryta_startup.exe ^<-- runtime aislado de startup
echo    startup_runtime\_internal\...      ^<-- DLLs/deps SOLO de startup
echo    assets\
echo    Audio\
echo    sprites\
echo    data\
echo ============================================================
echo.
pause
