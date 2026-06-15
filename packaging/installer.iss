; Instalador de pptx2web — Inno Setup (per-usuario, sin admin).
; Compilar:  ISCC.exe /DMyAppVersion=0.1.0 packaging\installer.iss
; (build.ps1 pasa la versión automáticamente leyéndola de __init__.py.)

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "pptx2web"
#define MyAppExe "pptx2web-gui.exe"
; AppId FIJO: garantiza que las actualizaciones reinstalen sobre la misma ruta.
#define MyAppId "{{B2F8C4A1-7E3D-4C9A-9F2B-2A6E1D5C8F30}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=NovaPixel
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Sin permisos de administrador: instala en el perfil del usuario.
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=pptx2web-setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Cierra la app si está abierta (lo necesita la auto-actualización OTA).
CloseApplications=yes
RestartApplications=no
; Icono opcional: solo se usa si packaging\pptx2web.ico existe.
#if FileExists(AddBackslash(SourcePath) + "pptx2web.ico")
SetupIconFile=pptx2web.ico
#endif

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
; Todo el dist de PyInstaller (incluye exe, _internal, player\, themes\, bin\).
Source: "..\dist\pptx2web-gui\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
; Al terminar (también tras una actualización silenciosa) relanza la app.
Filename: "{app}\{#MyAppExe}"; Description: "Iniciar {#MyAppName}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#MyAppExe}"; Flags: nowait runasoriginaluser; Check: WizardSilent
