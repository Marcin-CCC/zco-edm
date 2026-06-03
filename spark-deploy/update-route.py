#!/usr/bin/env python3
"""Write the fixed route.ts to Spark server."""
import os, sys

# Create the route.ts content
content = r'''import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8082';

function shouldProxy(path: string): boolean {
  const staticExtensions = ['.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.eot'];
  for (const ext of staticExtensions) {
    if (path.endsWith(ext)) return false;
  }
  return true;
}

async function proxyRequest(method: string, path: string[], request: NextRequest) {
  if (path.length > 0 && path[0] === '.well-known') {
    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  }

  if (!shouldProxy(path.join('/'))) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  }

  const cleanPath = path.filter(p => p.length > 0);
  const apiUrl = `/api/${cleanPath.join('/')}`;
  const url = `${BACKEND_URL}${apiUrl}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (key.toLowerCase() === 'host') return;
    headers.set(key, value);
  });

  try {
    const fetchInit: RequestInit = {
      method,
      headers,
      credentials: 'include',
      redirect: 'follow',
    };

    if (method !== 'GET' && method !== 'HEAD') {
      const contentType = request.headers.get('content-type');
      if (contentType?.includes('multipart/form-data')) {
        fetchInit.body = await request.blob();
      } else if (contentType?.includes('application/json')) {
        fetchInit.body = await request.text();
      }
    }

    const response = await fetch(url, fetchInit);

    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/pdf') ||
        contentType.includes('application/octet-stream') ||
        contentType.includes('application/') ||
        response.headers.get('content-disposition')) {
      const blob = await response.blob();
      const responseHeaders = new Headers();
      response.headers.forEach((value, key) => {
        responseHeaders.set(key, value);
      });
      responseHeaders.set('Access-Control-Allow-Origin', '*');
      return new NextResponse(blob, { status: response.status, headers: responseHeaders });
    }

    const data = await response.json().catch(() => null);
    return NextResponse.json(data || { detail: 'No response body' }, {
      status: response.status,
      headers: { 'Access-Control-Allow-Origin': '*' },
    });
  } catch (error) {
    console.error('Proxy error:', error);
    return NextResponse.json({ detail: 'Backend unavailable' }, { status: 502 });
  }
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const resolvedParams = await params;
  return proxyRequest('GET', resolvedParams.path || [], request);
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const resolvedParams = await params;
  return proxyRequest('POST', resolvedParams.path || [], request);
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const resolvedParams = await params;
  return proxyRequest('PUT', resolvedParams.path || [], request);
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const resolvedParams = await params;
  return proxyRequest('DELETE', resolvedParams.path || [], request);
}

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  const resolvedParams = await params;
  return proxyRequest('PATCH', resolvedParams.path || [], request);
}

export async function OPTIONS(request: NextRequest, { params }: { params: Promise<{ path?: string[] }> }) {
  return new NextResponse(null, {
    status: 204,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, PATCH, OPTIONS',
      'Access-Control-Allow-Headers': 'Authorization, Content-Type, Accept',
    },
  });
}
'''

# Create the directory on Spark via ssh
os.system('ssh spark "mkdir -p /home/marcin/zco-edm-app/frontend/src/app/api/[[...path]]"')

# Write the file using ssh python
import subprocess
result = subprocess.run(
    ['ssh', 'spark', 'python3', '-c', f'''
import os
p = r"/home/marcin/zco-edm-app/frontend/src/app/api/[[...path]]/route.ts"
c = r\'\'\'{content.lstrip()}\'\'\'
with open(p, "w") as f:
    f.write(c)
print("OK")
'''],
    capture_output=True, text=True
)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

print("Done!")