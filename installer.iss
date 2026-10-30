; Inno Setup script: turns dist\PDFExtractor into one shareable setup .exe.
; Built by build_installer.bat. Needs Inno Setup 6 (https://jrsoftware.org/isdl.php).

#define AppName "PDF Extractor by Osama"
#define AppVersion "1.2.0"
#define AppExe "PDFExtractor.exe"

[Setup]
AppId={{39DAD9C0-3B33-45EE-8031-378C2EF367E8}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Osama
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Lets people without admin rights install just for themselves.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer
OutputBaseFilename=PDF-Extractor-by-Osama-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\PDFExtractor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Adds PDF Extractor to the "Open with" menu for PDF files.
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithList\{#AppExe}"; ValueType: string; ValueName: ""; ValueData: ""; Flags: uninsdeletekey

[InstallDelete]
; Removes shortcuts left by 1.0.0, which was named just "PDF Extractor".
Type: files; Name: "{autoprograms}\PDF Extractor.lnk"
Type: files; Name: "{autodesktop}\PDF Extractor.lnk"

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
