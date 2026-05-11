; ============================================================
; spryta_installer.iss
; Instalador de Spryta para Inno Setup (per-user)
; ============================================================

#define AppName "Spryta"
#define AppVersion "1.0.0"
#define AppPublisher "Spryta"
#define AppURL "https://www.patreon.com/Spryta"
#define AppExeName "Spryta.exe"
#define StartupExeName "spryta_startup.exe"
#define BuildDir "dist\\Spryta"

[Setup]
; NO cambiar AppId una vez publicado
AppId={{d9959120-1844-45a0-a0b9-1576628ed17a}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; IMPORTANTE:
; La aplicacion se instala en el perfil del usuario, no en Program Files.
; Los datos modificables viven en {localappdata}\Spryta para evitar UAC/admin.
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableDirPage=no
DisableProgramGroupPage=yes

; Instalacion por usuario (sin UAC admin). No requiere elevacion.
PrivilegesRequired=lowest

OutputDir=installer_output
OutputBaseFilename=Spryta_Setup_v{#AppVersion}
SetupIconFile=assets\icons\icon.ico

Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

MinVersion=10.0
WizardStyle=modern

; Cierra procesos del usuario actual durante actualizaciones/desinstalaciones; no requiere admin.
CloseApplications=yes
CloseApplicationsFilter={#AppExeName},main.exe,{#StartupExeName}
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "autostart"; Description: "Start Spryta &automatically with Windows"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Copiar binarios principales (solo raiz de dist\Spryta)
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion
; Copiar subcarpetas de runtime/recursos necesarias para ejecutar la app
Source: "{#BuildDir}\assets\*";         DestDir: "{app}\assets";         Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#BuildDir}\Spryta_internal\*"; DestDir: "{app}\Spryta_internal"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "{#BuildDir}\_internal\*";      DestDir: "{app}\_internal";      Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "{#BuildDir}\main_runtime\*";   DestDir: "{app}\main_runtime";   Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#BuildDir}\startup_runtime\*"; DestDir: "{app}\startup_runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
; Copiar contenido por defecto de Audio/Sprites al perfil del usuario.
; No se elimina al desinstalar para preservar datos del usuario.
Source: "{#BuildDir}\Audio\*";   DestDir: "{localappdata}\Spryta\Audio";   Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist uninsneveruninstall
Source: "{#BuildDir}\sprites\*"; DestDir: "{localappdata}\Spryta\sprites"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist uninsneveruninstall
[Dirs]
; Crear la carpeta de datos del usuario durante la instalacion.
; {localappdata} = C:\Users\USUARIO\AppData\Local\
Name: "{localappdata}\Spryta";           Flags: uninsneveruninstall
Name: "{localappdata}\Spryta\sprites";   Flags: uninsneveruninstall
Name: "{localappdata}\Spryta\Audio";     Flags: uninsneveruninstall
Name: "{localappdata}\Spryta\data";      Flags: uninsneveruninstall

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\icons\icon.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\icons\icon.ico"; Tasks: desktopicon

[Registry]
; Autoarranque por usuario
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Spryta"; ValueData: """{app}\startup_runtime\{#StartupExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Intentar cerrar procesos del usuario actual antes de desinstalar.
; taskkill no requiere admin para procesos propios; si no hay procesos, no falla la desinstalacion.
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM {#AppExeName} /IM main.exe /IM {#StartupExeName} /IM ""Spryta Sprite.exe"" >nul 2>nul || exit /B 0"; Flags: runhidden

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Hook disponible para pasos posteriores a la instalacion
  end;
end;
