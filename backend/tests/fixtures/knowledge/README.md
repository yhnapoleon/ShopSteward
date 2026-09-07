# Knowledge validation fixtures

`chartsheet.xlsx` is a synthetic workbook generated with openpyxl 3.1.5 in the bundled document runtime. It contains a Data worksheet (A=3, B=7) and a separate Chart chartsheet. The saved workbook was reopened with openpyxl, verifying both sheet names, one chartsheet and the value 7. It contains no real business data.

The binary is a fixed regression input for preserving valid originals. The companion negative test changes only the chartsheet content-type declaration. It is separate from the frozen K0 corpus and does not change K0 evaluation denominators.

SpreadsheetML permits worksheets, chartsheets and dialog sheets; see [Microsoft Open XML sheets documentation](https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-sheets). K1 validates package structure, not chart rendering or document extraction.
