# NOA 상시 수집 작업을 Windows 작업 스케줄러에 등록한다.
# 다시 실행하면 같은 이름의 작업을 덮어쓴다.
#
# 등록:  powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1
# 확인:  schtasks /Query /TN "\NOA\" /FO TABLE
# 중지:  schtasks /Change /TN "\NOA\realtime" /DISABLE
#
# 로그인되어 있고 PC가 켜져 있을 때만 실행된다.
#
# - realtime : 15분마다 실시간 도시데이터 수집 (파일로만 저장)
# - daily    : 매일 새벽 나머지 수집 (이후 DB 적재, 예측도 여기에 추가)

$runner = Join-Path $PSScriptRoot "run_hidden.vbs"

# 이전에 작업별로 나눠 등록했던 것은 정리한다.
$oldTasks = @("citydata", "sdot_realtime", "sdot_recent", "kto_concentration", "tourapi_details")

foreach ($name in $oldTasks) {
    schtasks /Query /TN "\NOA\$name" 2>$null | Out-Null

    if ($LASTEXITCODE -eq 0) {
        schtasks /Delete /TN "\NOA\$name" /F | Out-Null
        Write-Output "정리: \NOA\$name"
    }
}

$tasks = @(
    @{ Name = "realtime"; Args = "collect_seoul_citydata"; Schedule = @("/SC", "MINUTE", "/MO", "15") },
    @{ Name = "daily";    Args = "run_daily";              Schedule = @("/SC", "DAILY", "/ST", "01:10") }
)

foreach ($task in $tasks) {
    $action = "wscript.exe `"$runner`" $($task.Args)"
    $arguments = @("/Create", "/F", "/TN", "\NOA\$($task.Name)", "/TR", $action) + $task.Schedule
    schtasks @arguments | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Output "등록: \NOA\$($task.Name)  ($($task.Schedule -join ' '))"
    }
    else {
        Write-Output "실패: \NOA\$($task.Name)"
    }
}
