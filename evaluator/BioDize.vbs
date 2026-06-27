' BioDize Evaluator -- Doppelklick zum Starten (kein CMD-Fenster)
' Benoetigt: Python 3.10+ mit Windows Python Launcher (py.exe)
Set oFSO   = CreateObject("Scripting.FileSystemObject")
Set oShell = CreateObject("WScript.Shell")
sDir = oFSO.GetParentFolderName(WScript.ScriptFullName)
sCmd = "py -B """ & sDir & "\launcher.pyw"""
oShell.Run sCmd, 0, False
