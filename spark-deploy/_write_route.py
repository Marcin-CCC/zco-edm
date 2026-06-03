#!/usr/bin/env python3
import sys
content = sys.stdin.buffer.read()
import os
os.makedirs("/home/marcin/zco-edm-app/frontend/src/app/api/[[...path]]", exist_ok=True)
with open("/home/marcin/zco-edm-app/frontend/src/app/api/[[...path]]/route.ts", "wb") as out:
    out.write(content)
print(f"Written {len(content)} bytes")
