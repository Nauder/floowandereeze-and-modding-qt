Write-Output "Running tests..."

pylint **/*.py `
    --ignore-paths=qtdesigner/,local/,pages/ui/ `
    --disable=import-error `
    --fail-under=8

black .\pages\ --check

Write-Output "Tests finished"