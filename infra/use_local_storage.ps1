# Dot-source to keep runtime caches on the same drive as this checkout.
# Applies only to this shell and its child processes.
$shopStewardStorageRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../ShopSteward-storage'))
$shopStewardStorageFolders = @{
    TEMP = 'tmp'; TMP = 'tmp'; UV_CACHE_DIR = 'uv-cache';
    PIP_CACHE_DIR = 'pip-cache'; HF_HOME = 'huggingface';
    HF_HUB_CACHE = 'huggingface\hub'; HUGGINGFACE_HUB_CACHE = 'huggingface\hub';
    TORCH_HOME = 'torch-cache'
}
foreach ($shopStewardStorageName in $shopStewardStorageFolders.Keys) {
    $shopStewardStoragePath = Join-Path $shopStewardStorageRoot $shopStewardStorageFolders[$shopStewardStorageName]
    New-Item -ItemType Directory -Path $shopStewardStoragePath -Force | Out-Null
    [Environment]::SetEnvironmentVariable($shopStewardStorageName, $shopStewardStoragePath, 'Process')
}
