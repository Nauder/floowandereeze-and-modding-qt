# Compile the resource file
pyside6-rcc .\qtdesigner\resources.qrc -o .\pages\ui\resources_rc.py

# Define the UI directory
$ui_dir = ".\qtdesigner\ui"
$output_dir = ".\pages\ui"

# Get all .ui files and convert them to Python files
Get-ChildItem -Path $ui_dir -Filter *.ui | ForEach-Object {
    $inputFile = $_.FullName
    $outputFile = "$output_dir\$($_.BaseName).py"
    pyside6-uic $inputFile -o $outputFile --from-imports
    Write-Output "Converted $inputFile to $outputFile"
}
