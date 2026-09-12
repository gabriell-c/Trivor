$docs = "c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\docs"
$pdfs = Get-ChildItem $docs -Filter "*.pdf" | Sort-Object Name
$result = "PDFs: $($pdfs.Count)"
foreach ($p in $pdfs) {
    $result += "`n  $($p.Name)"
}
$result | Out-File -FilePath "C:\temp\pdf_list.txt" -Encoding utf8
"done"
