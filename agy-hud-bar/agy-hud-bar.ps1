# Antigravity Desktop Always-On-Top Draggable Mini HUD Bar
# Displays: Current Conversation token/s | Quota Remaining | Cache Hit Rate | Context Occupancy

$ErrorActionPreference = 'SilentlyContinue'

# Single-instance guard: signal any previous HUD instance to close cleanly
$mutexName = 'Local\AntigravityHudMiniBarMutex_v1'
$script:stopEventName = 'Local\AntigravityHudMiniBarStop_v1'
try {
    $existingStop = [System.Threading.EventWaitHandle]::OpenExisting($script:stopEventName)
    if ($existingStop) {
        $existingStop.Set() | Out-Null
        $existingStop.Dispose()
        Start-Sleep -Milliseconds 350
    }
} catch {}

$script:stopEvent = New-Object System.Threading.EventWaitHandle($false, [System.Threading.EventResetMode]::AutoReset, $script:stopEventName)

Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$settingsPath = Join-Path $scriptDir 'hud_settings.json'
$appDataRoot = Join-Path $env:USERPROFILE '.gemini\antigravity'
$hudLivePath = Join-Path $appDataRoot 'sidecar_data\token-meter\dashboard\data\hud_live.json'
$brainDir = Join-Path $appDataRoot 'brain'

# Default persisted settings
$script:settings = @{
    left = -1
    top = -1
    locked = $false
    appearance = 'capsule' # 'capsule' | 'seamless' | 'glass'
    pinnedConversationId = ''
}

if (Test-Path $settingsPath) {
    try {
        $loaded = Get-Content $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($null -ne $loaded.left) { $script:settings.left = [double]$loaded.left }
        if ($null -ne $loaded.top) { $script:settings.top = [double]$loaded.top }
        if ($null -ne $loaded.locked) { $script:settings.locked = [bool]$loaded.locked }
        if ($loaded.appearance) { $script:settings.appearance = [string]$loaded.appearance }
        if ($null -ne $loaded.pinnedConversationId) { $script:settings.pinnedConversationId = [string]$loaded.pinnedConversationId }
    } catch {}
}

function Save-HudSettings {
    try {
        $json = $script:settings | ConvertTo-Json -Depth 3
        [System.IO.File]::WriteAllText($settingsPath, $json, [System.Text.Encoding]::UTF8)
    } catch {}
}

# Build crisp WPF borderless topmost pill matching Antigravity Composer dark bar
[xml]$xaml = @"
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Antigravity Token HUD"
        WindowStyle="None"
        AllowsTransparency="True"
        Background="Transparent"
        Topmost="True"
        ShowInTaskbar="False"
        ResizeMode="NoResize"
        SizeToContent="WidthAndHeight"
        UseLayoutRounding="True"
        SnapsToDevicePixels="True"
        TextOptions.TextFormattingMode="Display"
        TextOptions.TextRenderingMode="ClearType">
    <Border x:Name="RootPill"
            CornerRadius="6"
            Background="#EB16181D"
            BorderBrush="#2EFFFFFF"
            BorderThickness="1"
            Padding="9,3,9,3"
            Cursor="SizeAll">
        <Border.ToolTip>
            <ToolTip Background="#F514171F" Foreground="#E2E8F0" BorderBrush="#38FFFFFF" BorderThickness="1" Padding="10,8">
                <TextBlock x:Name="TxtTooltip" FontFamily="Segoe UI, Microsoft YaHei UI" FontSize="12" LineHeight="18" Text="正在读取 Antigravity 实时遥测数据…"/>
            </ToolTip>
        </Border.ToolTip>
        <StackPanel Orientation="Horizontal" VerticalAlignment="Center">
            <!-- Status Dot -->
            <Ellipse x:Name="DotStatus" Width="6" Height="6" Fill="#38BDF8" VerticalAlignment="Center" Margin="0,0,7,0"/>

            <!-- 1. Current Conversation token/s -->
            <TextBlock x:Name="TxtSpeedIcon" Text="⚡ " Foreground="#38BDF8" FontFamily="Segoe UI Symbol, Microsoft YaHei UI" FontSize="11.5" VerticalAlignment="Center"/>
            <TextBlock x:Name="TxtSpeed" Text="— tok/s" Foreground="#E5E7EB" FontFamily="Segoe UI Variable Text, Segoe UI, Microsoft YaHei UI" FontSize="12" FontWeight="SemiBold" VerticalAlignment="Center"/>

            <Border Width="1" Height="11" Background="#24FFFFFF" Margin="8,0,8,0" VerticalAlignment="Center"/>

            <!-- 2. Quota Remaining -->
            <TextBlock Text="限额 " Foreground="#9CA3AF" FontFamily="Segoe UI, Microsoft YaHei UI" FontSize="11.5" VerticalAlignment="Center"/>
            <TextBlock x:Name="TxtQuota" Text="—%" Foreground="#34D399" FontFamily="Segoe UI Variable Text, Segoe UI, Microsoft YaHei UI" FontSize="12" FontWeight="SemiBold" VerticalAlignment="Center"/>

            <Border Width="1" Height="11" Background="#24FFFFFF" Margin="8,0,8,0" VerticalAlignment="Center"/>

            <!-- 3. Cache Hit Rate -->
            <TextBlock Text="缓存 " Foreground="#9CA3AF" FontFamily="Segoe UI, Microsoft YaHei UI" FontSize="11.5" VerticalAlignment="Center"/>
            <TextBlock x:Name="TxtCache" Text="—%" Foreground="#2DD4BF" FontFamily="Segoe UI Variable Text, Segoe UI, Microsoft YaHei UI" FontSize="12" FontWeight="SemiBold" VerticalAlignment="Center"/>

            <Border Width="1" Height="11" Background="#24FFFFFF" Margin="8,0,8,0" VerticalAlignment="Center"/>

            <!-- 4. Context Occupancy -->
            <TextBlock Text="上下文 " Foreground="#9CA3AF" FontFamily="Segoe UI, Microsoft YaHei UI" FontSize="11.5" VerticalAlignment="Center"/>
            <TextBlock x:Name="TxtContext" Text="—" Foreground="#C4B5FD" FontFamily="Segoe UI Variable Text, Segoe UI, Microsoft YaHei UI" FontSize="12" FontWeight="SemiBold" VerticalAlignment="Center"/>
        </StackPanel>
    </Border>
</Window>
"@

$reader = New-Object System.Xml.XmlNodeReader $xaml
$window = [Windows.Markup.XamlReader]::Load($reader)

$rootPill   = $window.FindName('RootPill')
$dotStatus  = $window.FindName('DotStatus')
$txtSpeed   = $window.FindName('TxtSpeed')
$txtQuota   = $window.FindName('TxtQuota')
$txtCache   = $window.FindName('TxtCache')
$txtContext = $window.FindName('TxtContext')
$txtTooltip = $window.FindName('TxtTooltip')

$brushConverter = New-Object System.Windows.Media.BrushConverter
function To-Brush([string]$hex) {
    return $brushConverter.ConvertFromString($hex)
}

function Apply-Appearance {
    switch ($script:settings.appearance) {
        'seamless' {
            # Alpha=1 keeps mouse drag & right-click hit-testing active while visually invisible on dark Composer bar
            $rootPill.Background = To-Brush '#02000000'
            $rootPill.BorderBrush = To-Brush '#00000000'
        }
        'glass' {
            $rootPill.Background = To-Brush '#B814161B'
            $rootPill.BorderBrush = To-Brush '#38FFFFFF'
        }
        default {
            $rootPill.Background = To-Brush '#F015171C'
            $rootPill.BorderBrush = To-Brush '#2CFFFFFF'
        }
    }
    $rootPill.Cursor = if ($script:settings.locked) { [System.Windows.Input.Cursors]::Arrow } else { [System.Windows.Input.Cursors]::SizeAll }
}

Apply-Appearance

# Position window (restore saved coordinates or place near bottom-center where chat composer sits)
$window.Add_Loaded({
    $workArea = [System.Windows.SystemParameters]::WorkArea
    if ($script:settings.left -ge 0 -and $script:settings.top -ge 0 -and
        $script:settings.left -lt ($workArea.Right - 60) -and $script:settings.top -lt ($workArea.Bottom - 15)) {
        $window.Left = $script:settings.left
        $window.Top = $script:settings.top
    } else {
        $window.Left = [Math]::Max(40, ($workArea.Width - $window.ActualWidth) / 2 - 40)
        $window.Top  = [Math]::Max(40, $workArea.Bottom - 78)
    }
})

# Drag support
$rootPill.Add_MouseLeftButtonDown({
    param($sender, $e)
    if (-not $script:settings.locked -and $e.ButtonState -eq [System.Windows.Input.MouseButtonState]::Pressed) {
        try {
            $window.DragMove()
            $script:settings.left = [Math]::Round($window.Left, 1)
            $script:settings.top  = [Math]::Round($window.Top, 1)
            Save-HudSettings
        } catch {}
    }
})

# Formatting helpers
function Format-CompactTokens([double]$n) {
    if ($n -ge 1000000) { return ('{0:N2}M' -f ($n / 1000000)) }
    if ($n -ge 1000)    { return ('{0:N1}k' -f ($n / 1000)) }
    return ('{0:N0}' -f $n)
}

function Format-ResetCountdown([string]$iso) {
    if (-not $iso) { return '' }
    try {
        $target = [DateTimeOffset]::Parse($iso).ToLocalTime()
        $diff = $target - [DateTimeOffset]::Now
        if ($diff.TotalMinutes -le 0) { return '即将重置' }
        if ($diff.TotalHours -ge 1) {
            return ('{0}h {1}m 后重置 ({2})' -f [int][Math]::Floor($diff.TotalHours), $diff.Minutes, $target.ToString('HH:mm'))
        }
        return ('{0}m 后重置 ({1})' -f [int][Math]::Ceiling($diff.TotalMinutes), $target.ToString('HH:mm'))
    } catch {
        return ''
    }
}

# Data fetching:
# 1) Prefer live hud_live.json written by token-meter sidecar (works across Antigravity restarts)
# 2) Direct LS RPC if ANTIGRAVITY_LS_ADDRESS + ANTIGRAVITY_CSRF_TOKEN are present in env (instant startup)
# 3) Local transcript.jsonl fallback if LS is temporarily restarting
$script:recentConversations = @()

function Get-ContextLimitForModel([string]$modelStr) {
    $s = ($modelStr + '').ToLowerInvariant()
    if ($s.Contains('claude')) { return 200000 }
    if ($s.Contains('gpt-oss') -or $s.Contains('120b')) { return 131072 }
    return 1048576
}

function Fetch-DirectLsSnapshot {
    if (-not $env:ANTIGRAVITY_LS_ADDRESS -or -not $env:ANTIGRAVITY_CSRF_TOKEN) { return $null }
    try {
        $headers = @{
            'Content-Type' = 'application/json'
            'x-codeium-csrf-token' = $env:ANTIGRAVITY_CSRF_TOKEN
        }
        $baseUri = "http://$($env:ANTIGRAVITY_LS_ADDRESS)/exa.language_server_pb.LanguageServerService"
        $u = Invoke-RestMethod -Uri "$baseUri/GetUserStatus" -Method Post -Headers $headers -Body '{}' -TimeoutSec 3
        $all = Invoke-RestMethod -Uri "$baseUri/GetAllCascadeTrajectories" -Method Post -Headers $headers -Body '{}' -TimeoutSec 3

        $labelMap = @{}
        $quotaMap = @{}
        $cfgData = $u.userStatus.cascadeModelConfigData
        $selModelId = [string]$cfgData.defaultOverrideModelConfig.modelOrAlias.model
        foreach ($c in $cfgData.clientModelConfigs) {
            $mid = [string]$c.modelOrAlias.model
            if ($mid) {
                $labelMap[$mid] = [string]$c.label
                if ($c.quotaInfo) {
                    $quotaMap[$mid] = @{
                        pct = [double]$c.quotaInfo.remainingFraction * 100.0
                        reset = [string]$c.quotaInfo.resetTime
                    }
                }
            }
        }

        $convs = @()
        foreach ($p in $all.trajectorySummaries.PSObject.Properties) {
            $s = $p.Value
            if (-not $s.trajectoryMetadata.parentConversationId) {
                $convs += [PSCustomObject]@{
                    id = $p.Name
                    status = [string]$s.status
                    lastMod = [string]$s.lastModifiedTime
                }
            }
        }
        $sorted = $convs | Sort-Object @{Expression={ if ($_.status -eq 'CASCADE_RUN_STATUS_RUNNING') { 1 } else { 0 } }; Descending=$true}, @{Expression={$_.lastMod}; Descending=$true}
        $targetId = if ($script:settings.pinnedConversationId -and ($sorted.id -contains $script:settings.pinnedConversationId)) {
            $script:settings.pinnedConversationId
        } else {
            [string]($sorted | Select-Object -First 1).id
        }
        if (-not $targetId) { return $null }

        $tr = Invoke-RestMethod -Uri "$baseUri/GetCascadeTrajectory" -Method Post -Headers $headers -Body ("{`"cascadeId`":`"$targetId`"}") -TimeoutSec 4
        $inSum = 0.0; $cacheSum = 0.0; $outSum = 0.0; $decOut = 0.0; $decMs = 0.0
        $latest = $null
        foreach ($st in $tr.trajectory.steps) {
            $mu = $st.metadata.modelUsage
            if (-not $mu) { continue }
            $inT = [double]($mu.inputTokens + 0)
            $caT = [double](($mu.cacheReadTokens, $mu.cacheReadInputTokens | Where-Object { $_ } | Select-Object -First 1) + 0)
            $ouT = [double]($mu.outputTokens + 0)
            if (($inT + $caT + $ouT) -le 0) { continue }
            $inSum += $inT; $cacheSum += $caT; $outSum += $ouT

            $cMs = if ($st.metadata.createdAt) { [DateTimeOffset]::Parse($st.metadata.createdAt).ToUnixTimeMilliseconds() } else { 0 }
            $vMs = if ($st.metadata.viewableAt) { [DateTimeOffset]::Parse($st.metadata.viewableAt).ToUnixTimeMilliseconds() } else { 0 }
            $fMs = if ($st.metadata.finishedGeneratingAt) { [DateTimeOffset]::Parse($st.metadata.finishedGeneratingAt).ToUnixTimeMilliseconds() } else { 0 }
            $dMs = if ($vMs -gt 0 -and $fMs -gt ($vMs + 80)) { $fMs - $vMs } elseif ($cMs -gt 0 -and $fMs -gt ($cMs + 80)) { $fMs - $cMs } else { 0 }
            $eMs = if ($cMs -gt 0 -and $fMs -gt ($cMs + 80)) { $fMs - $cMs } else { 0 }
            if ($dMs -gt 0 -and $ouT -gt 0) { $decOut += $ouT; $decMs += $dMs }

            $latest = @{
                modelId = [string]$mu.model
                total = $inT + $caT + $ouT
                decodeRate = if ($dMs -gt 0) { $ouT / ($dMs / 1000.0) } else { $null }
                e2eRate = if ($eMs -gt 0) { $ouT / ($eMs / 1000.0) } else { $null }
                ttftMs = if ($cMs -gt 0 -and $vMs -ge $cMs) { $vMs - $cMs } else { $null }
            }
        }

        $effModel = if ($selModelId) { $selModelId } elseif ($latest) { $latest.modelId } else { '' }
        $effLabel = if ($effModel -and $labelMap.ContainsKey($effModel)) { $labelMap[$effModel] } else { $effModel }
        $q = if ($effModel -and $quotaMap.ContainsKey($effModel)) { $quotaMap[$effModel] } else { $null }
        $ctxUsed = if ($latest) { $latest.total } else { 0 }
        $ctxLim = Get-ContextLimitForModel "$effModel $effLabel"
        $promptTot = $inSum + $cacheSum

        return @{
            conversationId = $targetId
            title = "会话 $($targetId.Substring(0,8))"
            status = [string]($sorted | Where-Object { $_.id -eq $targetId } | Select-Object -First 1).status
            selectedModelLabel = $effLabel
            latestDecodeTokPerSec = if ($latest) { $latest.decodeRate } else { $null }
            latestE2eTokPerSec = if ($latest) { $latest.e2eRate } else { $null }
            latestTtftMs = if ($latest) { $latest.ttftMs } else { $null }
            avgDecodeTokPerSec = if ($decMs -gt 0) { $decOut / ($decMs / 1000.0) } else { $null }
            quotaRemainingPct = if ($q) { $q.pct } else { $null }
            quotaResetTime = if ($q) { $q.reset } else { $null }
            cacheHitRatePct = if ($promptTot -gt 0) { ($cacheSum / $promptTot) * 100.0 } else { 0.0 }
            contextUsedTokens = $ctxUsed
            contextLimitTokens = $ctxLim
            contextUsedPct = if ($ctxLim -gt 0) { ($ctxUsed / $ctxLim) * 100.0 } else { 0.0 }
            cumulativeTotalTokens = $inSum + $cacheSum + $outSum
        }
    } catch {
        return $null
    }
}

function Fetch-HudData {
    # 1. Try sidecar's live hud_live.json if updated within last 15s
    if (Test-Path $hudLivePath) {
        try {
            $item = Get-Item $hudLivePath
            if (((Get-Date) - $item.LastWriteTime).TotalSeconds -lt 15) {
                $raw = Get-Content $hudLivePath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($raw -and $raw.conversations) {
                    $script:recentConversations = @($raw.conversations)
                    if ($script:settings.pinnedConversationId) {
                        $pinned = $raw.conversations | Where-Object { $_.conversationId -eq $script:settings.pinnedConversationId } | Select-Object -First 1
                        if ($pinned) { return $pinned }
                    }
                    if ($raw.active) { return $raw.active }
                }
            }
        } catch {}
    }

    # 2. Direct LS RPC fallback when env vars exist
    $direct = Fetch-DirectLsSnapshot
    if ($direct) { return $direct }

    # 3. Transcript disk fallback
    if (Test-Path $brainDir) {
        try {
            $latestFile = Get-ChildItem -Path $brainDir -Directory |
                ForEach-Object { Join-Path $_.FullName '.system_generated\logs\transcript.jsonl' } |
                Where-Object { Test-Path $_ } |
                ForEach-Object { Get-Item $_ } |
                Sort-Object LastWriteTime -Descending |
                Select-Object -First 1
            if ($latestFile) {
                $lines = Get-Content $latestFile.FullName -Encoding UTF8
                $inSum = 0.0; $caSum = 0.0; $ouSum = 0.0; $ctxUsed = 0.0; $lastRate = $null
                for ($i = 0; $i -lt $lines.Count; $i++) {
                    $obj = $lines[$i] | ConvertFrom-Json
                    if ($obj.type -eq 'PLANNER_RESPONSE') {
                        $inT = [double]($obj.input_tokens + 0)
                        $caT = [double]($obj.cache_read_tokens + 0)
                        $ouT = [double]($obj.output_tokens + 0)
                        $inSum += $inT; $caSum += $caT; $ouSum += $ouT
                        $ctxUsed = $inT + $caT + $ouT
                        if ($i + 1 -lt $lines.Count) {
                            $nObj = $lines[$i + 1] | ConvertFrom-Json
                            $dt = ([DateTimeOffset]::Parse($nObj.created_at) - [DateTimeOffset]::Parse($obj.created_at)).TotalSeconds
                            if ($dt -ge 0.5 -and $dt -lt 300 -and $ouT -gt 0) { $lastRate = $ouT / $dt }
                        }
                    }
                }
                $pt = $inSum + $caSum
                return @{
                    conversationId = $latestFile.Directory.Parent.Parent.Name
                    title = '本地会话日志模式'
                    status = 'IDLE'
                    selectedModelLabel = 'Gemini (离线日志)'
                    latestDecodeTokPerSec = $lastRate
                    latestE2eTokPerSec = $lastRate
                    latestTtftMs = $null
                    avgDecodeTokPerSec = $lastRate
                    quotaRemainingPct = $null
                    quotaResetTime = $null
                    cacheHitRatePct = if ($pt -gt 0) { ($caSum / $pt) * 100.0 } else { 0.0 }
                    contextUsedTokens = $ctxUsed
                    contextLimitTokens = 1048576
                    contextUsedPct = ($ctxUsed / 1048576.0) * 100.0
                    cumulativeTotalTokens = $inSum + $caSum + $ouSum
                }
            }
        } catch {}
    }
    return $null
}

function Update-HudUi {
    if ($script:stopEvent.WaitOne(0)) {
        $window.Close()
        return
    }

    $d = Fetch-HudData
    if (-not $d) {
        $dotStatus.Fill = To-Brush '#6B7280'
        $txtTooltip.Text = "等待连接 Antigravity 会话数据…`n右键可切换外观模式或退出"
        return
    }

    $isRunning = ([string]$d.status) -match 'RUNNING'
    $dotStatus.Fill = if ($isRunning) { To-Brush '#22D3EE' } else { To-Brush '#34D399' }

    # 1. token/s
    $rate = if ($null -ne $d.latestDecodeTokPerSec -and [double]$d.latestDecodeTokPerSec -gt 0) {
        [double]$d.latestDecodeTokPerSec
    } elseif ($null -ne $d.avgDecodeTokPerSec -and [double]$d.avgDecodeTokPerSec -gt 0) {
        [double]$d.avgDecodeTokPerSec
    } else { 0.0 }
    $txtSpeed.Text = if ($rate -gt 0) { ('{0:N1} tok/s' -f $rate) } else { '— tok/s' }

    # 2. Quota Remaining
    if ($null -ne $d.quotaRemainingPct) {
        $qPct = [double]$d.quotaRemainingPct
        $txtQuota.Text = ('{0:N0}%' -f $qPct)
        if ($qPct -le 15) { $txtQuota.Foreground = To-Brush '#F87171' }
        elseif ($qPct -le 35) { $txtQuota.Foreground = To-Brush '#FBBF24' }
        else { $txtQuota.Foreground = To-Brush '#34D399' }
    } else {
        $txtQuota.Text = '—%'
        $txtQuota.Foreground = To-Brush '#9CA3AF'
    }

    # 3. Cache Hit Rate
    $cPct = if ($null -ne $d.cacheHitRatePct) { [double]$d.cacheHitRatePct } else { 0.0 }
    $txtCache.Text = ('{0:N1}%' -f $cPct)

    # 4. Context Occupancy
    $ctxUsed = [double]($d.contextUsedTokens + 0)
    $ctxLim  = [double]($d.contextLimitTokens + 0)
    $ctxPct  = if ($ctxLim -gt 0) { ($ctxUsed / $ctxLim) * 100.0 } else { 0.0 }
    $txtContext.Text = if ($ctxUsed -gt 0) {
        ('{0} ({1:N0}%)' -f (Format-CompactTokens $ctxUsed), $ctxPct)
    } else {
        '0 (0%)'
    }
    if ($ctxPct -ge 80) { $txtContext.Foreground = To-Brush '#F87171' }
    elseif ($ctxPct -ge 55) { $txtContext.Foreground = To-Brush '#FBBF24' }
    else { $txtContext.Foreground = To-Brush '#C4B5FD' }

    # Detailed Hover Tooltip
    $avgStr  = if ($d.avgDecodeTokPerSec) { ('{0:N1} tok/s' -f [double]$d.avgDecodeTokPerSec) } else { '—' }
    $e2eStr  = if ($d.latestE2eTokPerSec) { ('{0:N1} tok/s' -f [double]$d.latestE2eTokPerSec) } else { '—' }
    $ttftStr = if ($d.latestTtftMs) { ('{0:N2}s' -f ([double]$d.latestTtftMs / 1000.0)) } else { '—' }
    $qDetail = if ($null -ne $d.quotaRemainingPct) {
        $cd = Format-ResetCountdown ([string]$d.quotaResetTime)
        ('{0:N1}% {1}' -f [double]$d.quotaRemainingPct, $(if ($cd) { "· $cd" } else { '' }))
    } else { '未获取到配额信息' }

    $modeTag = if ($script:settings.pinnedConversationId) { '[已锁定会话]' } else { '[自动跟随当前对话]' }
    $txtTooltip.Text = @(
        "会话: $($d.title) $modeTag"
        "当前模型: $($d.selectedModelLabel)"
        "────────────────────────────"
        "⚡ 生成速率: 最新 $($txtSpeed.Text)  |  会话均值 $avgStr  |  端到端 $e2eStr  |  TTFT $ttftStr"
        "🔋 限额剩余: $qDetail"
        "🎯 缓存命中: 累计 $('{0:N1}%' -f $cPct)"
        "🧠 上下文占用: $('{0:N0}' -f $ctxUsed) / $('{0:N0}' -f $ctxLim) tokens ($('{0:N2}%' -f $ctxPct))"
        "📊 会话累计总消耗: $(Format-CompactTokens ([double]$d.cumulativeTotalTokens)) tokens"
        "────────────────────────────"
        "左键按住可拖放到输入框红框位置 · 右键打开设置菜单"
    ) -join "`n"
}

# Build dynamic Right-Click Context Menu
$ctxMenu = New-Object System.Windows.Controls.ContextMenu
$rootPill.ContextMenu = $ctxMenu

$ctxMenu.Add_Opened({
    $ctxMenu.Items.Clear()

    $miFollow = New-Object System.Windows.Controls.MenuItem
    $miFollow.Header = '自动跟随最新活跃对话'
    $miFollow.IsCheckable = $true
    $miFollow.IsChecked = [string]::IsNullOrEmpty($script:settings.pinnedConversationId)
    $miFollow.Add_Click({
        $script:settings.pinnedConversationId = ''
        Save-HudSettings
        Update-HudUi
    })
    $ctxMenu.Items.Add($miFollow) | Out-Null

    if ($script:recentConversations.Count -gt 0) {
        $miConvs = New-Object System.Windows.Controls.MenuItem
        $miConvs.Header = '指定监控某个会话'
        foreach ($c in $script:recentConversations) {
            $sub = New-Object System.Windows.Controls.MenuItem
            $sub.Header = [string]$c.title
            $sub.Tag = [string]$c.conversationId
            $sub.IsCheckable = $true
            $sub.IsChecked = ($script:settings.pinnedConversationId -eq [string]$c.conversationId)
            $sub.Add_Click({
                param($s, $e)
                $script:settings.pinnedConversationId = [string]$s.Tag
                Save-HudSettings
                Update-HudUi
            })
            $miConvs.Items.Add($sub) | Out-Null
        }
        $ctxMenu.Items.Add($miConvs) | Out-Null
    }

    $ctxMenu.Items.Add((New-Object System.Windows.Controls.Separator)) | Out-Null

    # Appearance submenu
    $miStyle = New-Object System.Windows.Controls.MenuItem
    $miStyle.Header = '外观融合模式'
    $modes = @(
        @{ key = 'capsule';  label = '暗色胶囊边框 (默认，便于对位)' },
        @{ key = 'seamless'; label = '无边框融合模式 (透明底，贴合输入框黑底)' },
        @{ key = 'glass';    label = '轻透毛玻璃胶囊' }
    )
    foreach ($m in $modes) {
        $sm = New-Object System.Windows.Controls.MenuItem
        $sm.Header = $m.label
        $sm.Tag = $m.key
        $sm.IsCheckable = $true
        $sm.IsChecked = ($script:settings.appearance -eq $m.key)
        $sm.Add_Click({
            param($s, $e)
            $script:settings.appearance = [string]$s.Tag
            Apply-Appearance
            Save-HudSettings
        })
        $miStyle.Items.Add($sm) | Out-Null
    }
    $ctxMenu.Items.Add($miStyle) | Out-Null

    $miLock = New-Object System.Windows.Controls.MenuItem
    $miLock.Header = '锁定当前坐标 (防误拖动)'
    $miLock.IsCheckable = $true
    $miLock.IsChecked = [bool]$script:settings.locked
    $miLock.Add_Click({
        $script:settings.locked = -not $script:settings.locked
        Apply-Appearance
        Save-HudSettings
    })
    $ctxMenu.Items.Add($miLock) | Out-Null

    $miRefresh = New-Object System.Windows.Controls.MenuItem
    $miRefresh.Header = '立即刷新数据'
    $miRefresh.Add_Click({ Update-HudUi })
    $ctxMenu.Items.Add($miRefresh) | Out-Null

    $ctxMenu.Items.Add((New-Object System.Windows.Controls.Separator)) | Out-Null

    $miExit = New-Object System.Windows.Controls.MenuItem
    $miExit.Header = '退出悬浮条'
    $miExit.Add_Click({ $window.Close() })
    $ctxMenu.Items.Add($miExit) | Out-Null
})

$timer = New-Object System.Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromMilliseconds(1800)
$timer.Add_Tick({ Update-HudUi })
$timer.Start()

$window.Add_Closed({
    $timer.Stop()
    if ($script:stopEvent) { $script:stopEvent.Dispose() }
})

Update-HudUi
$window.ShowDialog() | Out-Null
