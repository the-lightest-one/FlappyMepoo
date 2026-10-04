param(
    [int]$Port = 8080,
    [string]$TunnelHost = "nokey@localhost.run"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$log = Join-Path $env:TEMP "botapp-tunnel.log"
$err = Join-Path $env:TEMP "botapp-tunnel.err"
$server = $null
$tunnel = $null

function Stop-All {
    foreach ($process in @($tunnel, $server)) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

try {
    Write-Host "1/3 Запускаю сервер игры на порту $Port..." -ForegroundColor Cyan
    $server = Start-Process -FilePath "py" -ArgumentList "src/server.py" `
        -WorkingDirectory $root -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 3
    try {
        Invoke-WebRequest "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 5 | Out-Null
        Write-Host "    сервер отвечает." -ForegroundColor Green
    }
    catch {
        throw "Сервер не отвечает на http://127.0.0.1:$Port — проверь, что порт свободен (py src/server.py)."
    }

    Write-Host "2/3 Открываю HTTPS-туннель ($TunnelHost)..." -ForegroundColor Cyan
    Remove-Item $log, $err -Force -ErrorAction SilentlyContinue
    $tunnel = Start-Process -FilePath "ssh" -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $log -RedirectStandardError $err `
        -ArgumentList @(
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ServerAliveInterval=30",
            "-o", "ExitOnForwardFailure=yes",
            "-R", "80:localhost:$Port",
            $TunnelHost
        )

    $pattern = 'https://[a-z0-9]+\.lhr\.life'
    $url = $null
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 500
        if ($tunnel.HasExited) { break }
        if (Test-Path -LiteralPath $log) {
            $found = Select-String -LiteralPath $log -Pattern $pattern -ErrorAction SilentlyContinue
            if ($found) { $url = $found.Matches[0].Value; break }
        }
    }

    if (-not $url) {
        $details = if (Test-Path $err) { (Get-Content $err -Raw) } else { "" }
        throw "Не дождался адреса туннеля. Вывод ssh:`n$details`nПопробуй ещё раз или замени -Host на serveo.net"
    }

    Write-Host "    адрес получен: $url" -ForegroundColor Green

    Write-Host "3/3 Проверяю адрес снаружи..." -ForegroundColor Cyan
    try {
        $check = Invoke-WebRequest "$url/" -UseBasicParsing -TimeoutSec 20
        Write-Host "    публичный адрес отвечает: $($check.StatusCode)" -ForegroundColor Green
    }
    catch {
        Write-Host "    предупреждение: проверка снаружи не прошла ($($_.Exception.Message))" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "Готово. Игра доступна по адресу:" -ForegroundColor White
    Write-Host "  $url" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Теперь запустите бота через воторое окно терминала:" -ForegroundColor White
    Write-Host "  cd $root" -ForegroundColor Gray
    Write-Host "  `$env:BOTAPP_GAME_URL=`"$url`"" -ForegroundColor Gray
    Write-Host "  `$env:BOT_TOKEN=`"123456:ABC...`"" -ForegroundColor Gray
    Write-Host "  py src/bot.py" -ForegroundColor Gray
    Write-Host ""
    Write-Host "" -ForegroundColor White
    Write-Host "" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Скрипт работает, пока открыто это окно. Остановить — Ctrl+C." -ForegroundColor DarkGray

    Wait-Process -Id $tunnel.Id
    Write-Host "Туннель закрыт." -ForegroundColor DarkGray
}
finally {
    Stop-All
}
