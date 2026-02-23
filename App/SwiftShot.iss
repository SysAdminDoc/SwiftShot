; ===================================================================
; SwiftShot Installer - Inno Setup 6 Script
; ===================================================================
;
; Prerequisites:
;   1. Run Build-SwiftShot.ps1 first (produces dist\SwiftShot\)
;   2. Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;
; Build:
;   iscc.exe SwiftShot.iss
; ===================================================================

#define AppName        "SwiftShot"
#define AppVersion     "2.0.0"
#define AppPublisher   "SwiftShot Project"
#define AppURL         "https://github.com/SysAdminDoc/SwiftShot"
#define AppExeName     "SwiftShot.exe"
#define AppCopyright   "Copyright (C) 2025 SwiftShot Project"

[Setup]
AppId={{B7E3A1F2-5C8D-4E6A-9F0B-1D2C3E4F5A6B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
AppCopyright={#AppCopyright}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=SwiftShot-Setup
SetupIconFile=swiftshot.ico
UninstallDisplayIcon={app}\swiftshot.ico
UninstallDisplayName={#AppName} {#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
AppMutex=SwiftShot_SingleInstance
CloseApplications=yes
RestartApplications=no
CreateUninstallRegKey=yes
VersionInfoVersion={#AppVersion}.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Screenshot Tool Setup
VersionInfoCopyright={#AppCopyright}
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=This will install {#AppName} {#AppVersion} on your computer.%n%n{#AppName} is a fast, full-featured screenshot tool with annotation editor, window capture, scrolling capture, OCR, and more.%n%nIt is recommended that you close all other applications before continuing.

[Tasks]
Name: "desktopicon";  Description: "Create a &desktop shortcut";                 GroupDescription: "Shortcuts:"
Name: "startupentry"; Description: "Launch {#AppName} when Windows starts";      GroupDescription: "Startup:";     Flags: unchecked
Name: "fileassoc";    Description: "Associate .png files with {#AppName} Editor"; GroupDescription: "Integration:"; Flags: unchecked

[Files]
Source: "dist\SwiftShot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "swiftshot.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";          Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\swiftshot.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";    Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\swiftshot.ico"; Tasks: desktopicon
Name: "{autostartup}\{#AppName}";    Filename: "{app}\{#AppExeName}"; Parameters: "--minimized"; Tasks: startupentry

[Registry]
Root: HKA; Subkey: "Software\Classes\.png\OpenWithProgids";             ValueType: string; ValueName: "SwiftShot.png"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\SwiftShot.png";                    ValueType: string; ValueName: ""; ValueData: "PNG Image - {#AppName}"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\SwiftShot.png\DefaultIcon";        ValueType: string; ValueName: ""; ValueData: "{app}\swiftshot.ico,0"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\SwiftShot.png\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExeName}";                   ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExeName}\DefaultIcon";        ValueType: string; ValueName: ""; ValueData: "{app}\swiftshot.ico,0"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExeName}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/F /IM {#AppExeName}"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\SwiftShot"

[Code]
procedure TaskKill(ExeName: String);
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM ' + ExeName, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    TaskKill('{#AppExeName}');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    TaskKill('{#AppExeName}');
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'SwiftShot');
end;
