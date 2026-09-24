# Refreshes the tables of contents / figures / tables in the report and exports a PDF, using Microsoft Word.
#   powershell -ExecutionPolicy Bypass -File report\tools\export_pdf.ps1
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$docx = Join-Path $root "Sentari_Project_Report.docx"
$pdf = Join-Path $root "Sentari_Project_Report.pdf"

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($docx.ToString(), $false, $false)
    # two passes: page numbers shift once the lists are filled in
    for ($pass = 0; $pass -lt 2; $pass++) {
        foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
        $doc.Fields.Update() | Out-Null
        $doc.Repaginate()
    }
    $doc.Save()
    $doc.ExportAsFixedFormat($pdf.ToString(), 17, $false, 0, 0, 1, 1, 0, $true, $true, 1)  # 17 = PDF, bookmarks from headings
    $pages = $doc.ComputeStatistics(2)
    $doc.Close($false)
    Write-Output "pages=$pages"
    Write-Output "pdf=$pdf"
} finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
