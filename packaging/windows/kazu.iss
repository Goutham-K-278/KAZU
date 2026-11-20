; Inno Setup per-user Windows installer script (no admin required, LZMA2 compression).
; Displays the Kazu logo in the installer, Start Menu, Desktop shortcut, and Add/Remove Programs.
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{8D6B4A7E-4B1C-4B27-9D5B-9F7E4E2D1A01}
AppName=Kazu
AppVersion={#AppVersion}
AppPublisher=Kazu
DefaultDirName={localappdata}\Programs\Kazu
DefaultGroupName=Kazu
PrivilegesRequired=lowest
Compression=lzma2/ultra64
SolidCompression=yes
OutputBaseFilename=Kazu-Setup-{#AppVersion}-Windows-x64
SetupIconFile=..\icons\kazu.ico
UninstallDisplayIcon={app}\kazu.exe
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Files]
Source: "..\..\dist\kazu\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Kazu"; Filename: "{app}\kazu.exe"; IconFilename: "{app}\kazu.exe"
Name: "{autodesktop}\Kazu"; Filename: "{app}\kazu.exe"; IconFilename: "{app}\kazu.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\kazu.exe"; Description: "Launch Kazu"; Flags: nowait postinstall skipifsilent
