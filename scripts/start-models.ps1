param([ValidateSet('all','llm','embedding')][string]$Mode = 'all')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$runtime = Join-Path $projectRoot '.runtime\llama\llama-server.exe'
$qwenModel = Join-Path $projectRoot 'models\qwen2.5-1.5b-instruct-q4_k_m.gguf'
$bgeModel = Join-Path $projectRoot 'models\bge-small-zh-v1.5-q8_0.gguf'
$logDir = Join-Path $projectRoot '.runtime'

if (!(Test-Path $runtime) -or !(Test-Path $qwenModel) -or !(Test-Path $bgeModel)) {
    throw 'Models/runtime are missing. Run: py -3 scripts/install_models.py'
}

function Start-KbqaModel([string]$Name, [string[]]$Arguments, [int]$Port) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        Write-Output "$Name already listening on 127.0.0.1:$Port (PID $($listener.OwningProcess))"
        return
    }
    $process = Start-Process -FilePath $runtime -ArgumentList $Arguments -WorkingDirectory (Join-Path $projectRoot '.runtime\llama') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "$Name.log") -RedirectStandardError (Join-Path $logDir "$Name.err") -PassThru
    Write-Output "Started $Name (PID $($process.Id)), waiting for port $Port"
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        Start-Sleep -Seconds 1
        if ($process.HasExited) {
            Get-Content (Join-Path $logDir "$Name.err") -Tail 20
            throw "$Name exited during startup"
        }
        if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
            Write-Output "$Name ready on 127.0.0.1:$Port"
            return
        }
    }
    throw "$Name did not listen within 45 seconds"
}

if ($Mode -in @('all','embedding')) {
    Start-KbqaModel 'embedding' @('-m', $bgeModel, '--embedding', '--pooling', 'cls', '--alias', 'bge-small-zh', '--host', '127.0.0.1', '--port', '8082', '-c', '512', '-t', '4', '--no-webui') 8082
}
if ($Mode -in @('all','llm')) {
    Start-KbqaModel 'llm' @('-m', $qwenModel, '--alias', 'local-qwen', '--host', '127.0.0.1', '--port', '8081', '-c', '4096', '-t', '8', '--no-webui', '-n', '512') 8081
}
