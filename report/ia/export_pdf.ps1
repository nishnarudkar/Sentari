# Refresh the contents / figure / table lists in report\ia\Sentari_Report.docx and export a PDF with Microsoft Word.
#   powershell -ExecutionPolicy Bypass -File report\ia\export_pdf.ps1
$ErrorActionPreference = "Stop"
$docx = Join-Path $PSScriptRoot "Sentari_Report.docx"
$pdf = Join-Path $PSScriptRoot "Sentari_Report.pdf"
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($docx, $false, $false)
    for ($pass = 0; $pass -lt 2; $pass++) {
        foreach ($toc in $doc.TablesOfContents) { $toc.Update() }

        $doc.Repaginate()
    }
    $doc.Save()
    $doc.ExportAsFixedFormat($pdf, 17, $false, 0, 0, 1, 1, 0, $true, $true, 1)
    Write-Output ("pages={0}" -f $doc.ComputeStatistics(2))
    $doc.Close($false)
} finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
