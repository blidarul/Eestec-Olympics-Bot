# stops whatever listens on the fake gateway port (4010)
Get-NetTCPConnection -LocalPort 4010 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
