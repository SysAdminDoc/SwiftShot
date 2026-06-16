' SwiftShot Silent Launcher - No console window at all
Set WshShell = CreateObject("WScript.Shell")
strDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strDir
WshShell.Run """" & strDir & "\.venv\Scripts\pythonw.exe"" """ & strDir & "\main.py""", 0, False
Set WshShell = Nothing
