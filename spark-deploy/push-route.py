#!/usr/bin/env python3
"""Push the fixed route.ts to Spark server."""
import subprocess, sys

# Read the local route.ts
with open('frontend/src/app/api/[[...path]]/route.ts', 'r') as f:
    content = f.read()

# Write a helper script on Spark
with open('spark-deploy/_write_route.py', 'w') as f:
    f.write('#!/usr/bin/env python3\n')
    f.write('import sys\n')
    f.write('content = sys.stdin.buffer.read()\n')
    f.write('import os\n')
    f.write('os.makedirs("/home/marcin/zco-edm-app/frontend/src/app/api/[[...path]]", exist_ok=True)\n')
    f.write('with open("/home/marcin/zco-edm-app/frontend/src/app/api/[[...path]]/route.ts", "wb") as out:\n')
    f.write('    out.write(content)\n')
    f.write('print(f"Written {len(content)} bytes")\n')

# Copy helper to Spark
subprocess.run(['scp', 'spark-deploy/_write_route.py', 'spark:/tmp/_write_route.py'])

# Run it with stdin pipe
result = subprocess.run(
    ['ssh', 'spark', 'python3 /tmp/_write_route.py'],
    input=content.encode('utf-8'),
    capture_output=True
)
print(result.stdout.decode())
if result.stderr:
    print('STDERR:', result.stderr.decode())

# Verify
result2 = subprocess.run(
    ['ssh', 'spark', 'grep BACKEND_URL /home/marcin/zco-edm-app/frontend/src/app/api/[[...path]]/route.ts'],
    capture_output=True, text=True
)
print('Verified:', result2.stdout.strip())

print("SUCCESS")