# Prueba rápida de compresión contra la app en ejecución
# Uso: powershell -ExecutionPolicy Bypass -File test_compresion.ps1 -Archivo .\mi_archivo.pdf

param(
    [string]$Archivo = "tu_archivo.pdf",
    [string]$Servidor = "http://localhost:5000"
)

$niveles = @("baja", "media", "alta", "ultra")

if (-not (Test-Path $Archivo)) {
    Write-Host "No encontré $Archivo. Ejecuta: .\test_compresion.ps1 -Archivo .\ruta\al.pdf" -ForegroundColor Red
    exit 1
}

$tamanoOrigen = (Get-Item $Archivo).Length / 1MB
Write-Host ("Archivo original: {0} ({1:F2} MB)`n" -f $Archivo, $tamanoOrigen) -ForegroundColor Cyan

foreach ($nivel in $niveles) {
    $salida = "resultado_$nivel.pdf"
    Write-Host "Probando nivel: $nivel" -ForegroundColor Yellow

    # curl.exe (no el alias de PowerShell, que no acepta -F)
    & curl.exe -s -f -F "archivo=@$Archivo" -F "nivel=$nivel" "$Servidor/api/compresion" -o $salida

    if ($LASTEXITCODE -eq 0 -and (Test-Path $salida)) {
        $tamanoNuevo = (Get-Item $salida).Length / 1MB
        $reduccion = (1 - ($tamanoNuevo / $tamanoOrigen)) * 100
        Write-Host ("   Comprimido: {0:F2} MB  (reducción {1:F1} %)`n" -f $tamanoNuevo, $reduccion) -ForegroundColor Green
    } else {
        Write-Host "   Error en compresión (código $LASTEXITCODE)`n" -ForegroundColor Red
    }
}
