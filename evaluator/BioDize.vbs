' BioDize Evaluator -- Doppelklick zum Starten (kein CMD-Fenster)
' Benoetigt: Python 3.10+ (pythonw.exe aus dem Installationsverzeichnis)
Set oFSO   = CreateObject("Scripting.FileSystemObject")
Set oShell = CreateObject("WScript.Shell")
sDir = oFSO.GetParentFolderName(WScript.ScriptFullName)

' pythonw.exe suchen: Venv zuerst, dann Standard-Python-Pfade
Dim sPythonw
Dim oCandidates(4)
oCandidates(0) = sDir & "\..\backend\.venv\Scripts\pythonw.exe"
oCandidates(1) = "C:\Temp\py313-arm64-full\pythonw.exe"
oCandidates(2) = "C:\Users\" & oShell.ExpandEnvironmentStrings("%USERNAME%") & "\AppData\Local\Programs\Python\Python313\pythonw.exe"
oCandidates(3) = "C:\Program Files\Python313\pythonw.exe"
oCandidates(4) = "C:\Program Files (x86)\Python313\pythonw.exe"

Dim i
For i = 0 To 4
    If oFSO.FileExists(oCandidates(i)) Then
        sPythonw = oCandidates(i)
        Exit For
    End If
Next

If sPythonw = "" Then
    ' Fallback: pythonw via PATH (kein Fenster bei .pyw-Dateien)
    sPythonw = "pythonw"
End If

sCmd = """" & sPythonw & """ -B """ & sDir & "\launcher.pyw"""
oShell.Run sCmd, 0, False
