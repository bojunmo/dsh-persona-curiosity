# 自动同步 dsh-persona-curiosity 到 GitHub
# 用法：双击或 powershell -File sync.ps1
# 也可以挂到 Windows 定时任务（每 30 分钟）

$ErrorActionPreference = 'SilentlyContinue'

$dir = 'C:\Users\admin\Documents\deepseek-harness\default-workspace\dsh-persona-curiosity'
$key = 'C:\Users\admin\Documents\deepseek-harness\default-workspace\.ssh-dsh\id_ed25519'
$log = Join-Path $dir 'sync.log'

Push-Location $dir

$ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$changed = git status --porcelain

if (-not $changed) {
    "[$ts] 无变化，跳过" | Out-File -Append -Encoding utf8 $log
    Pop-Location
    exit 0
}

git add -A 2>&1 | Out-Null
git commit -m "auto: sync $ts" 2>&1 | Out-Null

$env:GIT_SSH_COMMAND = "ssh -i `"$key`" -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
$out = git push 2>&1
Remove-Item Env:GIT_SSH_COMMAND -ErrorAction SilentlyContinue

if ($LASTEXITCODE -eq 0) {
    "[$ts] 已同步: $(($changed -split "`n").Count) 个文件变化" | Out-File -Append -Encoding utf8 $log
} else {
    "[$ts] 失败: $out" | Out-File -Append -Encoding utf8 $log
}

Pop-Location
