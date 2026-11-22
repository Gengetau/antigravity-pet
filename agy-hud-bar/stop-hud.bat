@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { $e = [System.Threading.EventWaitHandle]::OpenExisting('Local\AntigravityHudMiniBarStop_v1'); $e.Set() | Out-Null; $e.Dispose(); Write-Host 'HUD stopped.' } catch { Write-Host 'HUD is not running.' }"
