' 静默运行 sync.ps1（不弹窗）
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\Users\admin\Documents\deepseek-harness\default-workspace\dsh-persona-curiosity\sync.ps1""", 0, False
