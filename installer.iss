#define MyAppName "AirPrint Bridge"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Salman Asmat"
#define MyAppExeName "AirPrintBridge.exe"
#define MyAppDir "C:\Program Files\AirPrintBridge"

[Setup]
AppId={{D370A1A2-5678-4321-ABCD-B1C2A3D4E5F6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={#MyAppDir}
OutputDir=.\Release
OutputBaseFilename=AirPrintBridge_Setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Files]
Source: "dist\AirPrintBridge.exe"; DestDir: "{app}"; Flags: ignoreversion

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--startup auto install"; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Parameters: "start"; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "stop"; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Parameters: "remove"; Flags: runhidden waituntilterminated

[UninstallDelete]
Type: files; Name: "{app}\airprint_bridge.log"
