; Inno Setup script for Usage Window.
; Build the app first:
;   python -m PyInstaller --onedir --noconsole --icon icon.ico --name UsageWindow
;       --distpath build\onedir --add-data "<abs>\icon.png;." --add-data "<abs>\icon.ico;." usage_window.pyw
; Then compile this file with ISCC.exe. The installer lands in build\installer.

[Setup]
AppName=Usage Window
AppVersion=1.0
AppPublisher=neal659
DefaultDirName={localappdata}\Programs\Usage Window
DefaultGroupName=Usage Window
PrivilegesRequired=lowest
OutputDir=build\installer
OutputBaseFilename=UsageWindow-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\UsageWindow.exe
Compression=lzma2
SolidCompression=yes
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start Usage Window when I sign in to Windows"

[Files]
Source: "build\onedir\UsageWindow\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Usage Window"; Filename: "{app}\UsageWindow.exe"
Name: "{autodesktop}\Usage Window"; Filename: "{app}\UsageWindow.exe"; Tasks: desktopicon
Name: "{userstartup}\Usage Window"; Filename: "{app}\UsageWindow.exe"; Tasks: startup

[Run]
Filename: "{app}\UsageWindow.exe"; Description: "Start Usage Window now"; Flags: nowait postinstall skipifsilent
