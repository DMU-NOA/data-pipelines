' 작업 스케줄러에서 수집 job을 콘솔 창 없이 실행한다.
' 사용: wscript.exe run_hidden.vbs <job 이름> [인자...]
' 예:   wscript.exe run_hidden.vbs collect_sdot --api realtime --days 14 --skip-complete
' 로그: data\logs\<job 이름>.log

Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))

job = WScript.Arguments(0)
args = ""
For i = 1 To WScript.Arguments.Count - 1
    args = args & " " & WScript.Arguments(i)
Next

If Not fso.FolderExists(root & "\data\logs") Then fso.CreateFolder(root & "\data\logs")
logFile = """" & root & "\data\logs\" & job & ".log"""

command = "cmd /c cd /d """ & root & """ && set PYTHONIOENCODING=utf-8" & _
    " && echo ==== %date% %time% " & job & args & " >> " & logFile & _
    " && .venv\Scripts\python.exe -m noa_data.jobs." & job & args & " >> " & logFile & " 2>&1"

CreateObject("WScript.Shell").Run command, 0, True
