import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://backend:8000';

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

  // Filter out empty segments from the catchall route
  const cleanPath = path.filter(p => p.length > 0);
  // Build the API URL - prepend /api because Next.js catchall strips /api prefix
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
        // ⚠️ MUST use request.text() not request.blob() — blob() loses FormData field structure
        // FastAPI expects multipart/form-data with field names (file, folder_id, etc.)
        const bodyText = await request.text();
        console.log('[Proxy] Multipart body length:', bodyText.length, 'Content-Type:', contentType);
        fetchInit.body = bodyText;
      } else if (contentType?.includes('application/json') ||
                 contentType?.includes('application/x-www-form-urlencoded') ||
                 !contentType) {
        const bodyText = await request.text();
        console.log('[Proxy] Body length:', bodyText.length, 'Content-Type:', contentType);
        fetchInit.body = bodyText;
      }
    }

    const response = await fetch(url, fetchInit);

    // Handle 204 No Content (DELETE success)
    if (response.status === 204) {
      return new NextResponse(null, {
        status: 204,
        headers: { 'Access-Control-Allow-Origin': '*' },
      });
    }

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