' Windows Task Scheduler runner. Exit with the Python job's exit code.
' Log: data\logs\<job>.log. Use venv Python if installed, otherwise PATH python.
Option Explicit
Dim fso, shell, root, job, args, i, logFolder, logFile, pythonExe
Dim command, exitCode

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))

If WScript.Arguments.Count < 1 Then
    WScript.Quit 2
End If
job = WScript.Arguments(0)
Select Case job
    Case "run_realtime", "run_daily", "run_training"
    Case Else
        WScript.Quit 2
End Select

args = ""
For i = 1 To WScript.Arguments.Count - 1
    args = args & " " & WScript.Arguments(i)
Next

logFolder = root & "\data\logs"
If Not fso.FolderExists(root & "\data") Then fso.CreateFolder(root & "\data")
If Not fso.FolderExists(logFolder) Then fso.CreateFolder(logFolder)
logFile = Chr(34) & logFolder & "\" & job & ".log" & Chr(34)

pythonExe = root & "\.venv\Scripts\python.exe"
If fso.FileExists(pythonExe) Then
    pythonExe = Chr(34) & pythonExe & Chr(34)
Else
    ' Match the Python available to the current Windows user.
    pythonExe = "python"
End If

command = "cmd.exe /d /c cd /d " & Chr(34) & root & Chr(34) & _
    " && set PYTHONIOENCODING=utf-8" & _
    " && echo ==== %date% %time% " & job & args & " >> " & logFile & _
    " && echo Python: " & pythonExe & " >> " & logFile & _
    " && " & pythonExe & " -m noa_data.jobs." & job & args & _
    " >> " & logFile & " 2>&1"

' Run(..., True) waits and returns cmd.exe / Python exit status.
exitCode = shell.Run(command, 0, True)
If exitCode <> 0 Then
    Dim out
    Set out = fso.OpenTextFile(logFolder & "\" & job & ".log", 8, True)
    out.WriteLine "FAILED: job=" & job & " exit_code=" & exitCode
    out.Close
End If
WScript.Quit exitCode
