@echo off
set PYTHONUNBUFFERED=1
cd /d "D:\Source\2026\P2\PilotCode"
python -u tests\e2e\run_e2e_tests.py --category c_simple --mode cli --timeout 360 > run1_stdout.txt 2>&1
echo DONE > run1_done.txt
