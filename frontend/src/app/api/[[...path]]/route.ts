import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://backend:8000';

// Szczegółowe logi proxy — domyślnie WYŁĄCZONE (PROXY_DEBUG=true aby włączyć).
// Nigdy nie logujemy nagłówków ani ciała żądania: nagłówek Authorization
// niesie token JWT, a ciało — dane osobowe z dokumentów medycznych.
const PROXY_DEBUG = process.env.PROXY_DEBUG === 'true';

function debugLog(...args: unknown[]) {
  if (PROXY_DEBUG) console.log('[PROXY]', ...args);
}

function shouldProxy(path: string): boolean {
  const staticExtensions = ['.js', '.jsx', ".ts", '.tsx', '.mjs', '.cjs', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.eot'];
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
  // Next.js catchall routes capture the full path AFTER /api/ prefix
  // e.g., request to /api/files/queue → path = ['files', 'queue']
  const cleanPath = path.filter(p => p.length > 0);
  
  // Handle query parameters from the original request
  const queryParams = request.nextUrl.search;
  const queryStr = queryParams || '';

  // Build full URL: BACKEND_URL + /api/ + cleanPath + query
  // We prepend /api/ because backend routes are defined with /api/ prefix
  const fullUrl = `${BACKEND_URL}/api/${cleanPath.join('/')}${queryStr}`;
  
  debugLog(`${method} /${cleanPath.join('/')} -> ${fullUrl}`);

  // Get auth token from request headers
  // Note: Next.js lowercases header names, so we check both 'authorization' and 'Authorization'
  let authHeader = request.headers.get('authorization') || request.headers.get('Authorization');

  // Also try to get token from cookies (fallback)
  const tokenCookie = request.cookies.get('auth_token')?.value;

  // Build headers - copy all headers except problematic ones
  const headers = new Headers();
  
  // Copy all headers except host, cookie, and others that cause issues.
  // content-length MUST be skipped — fetch/undici computes it from the actual
  // body; a stale or char-based value breaks requests with multi-byte (PL) chars.
  const skipHeaders = ['host', 'cookie', 'origin', 'referer', 'content-length', 'connection', 'accept-encoding'];
  request.headers.forEach((value, key) => {
    if (skipHeaders.includes(key.toLowerCase())) return;
    headers.set(key, value);
  });
  
  // Set auth header explicitly if found
  if (authHeader) {
    headers.set('authorization', authHeader);
  } else if (tokenCookie) {
    headers.set('authorization', `Bearer ${tokenCookie}`);
  } else {
    debugLog(`brak tokenu — backend zwróci 401`);
  }

  let url = fullUrl;
  let redirectCount = 0;
  const maxRedirects = 5;

  // Read the request body ONCE, before the redirect loop.
  // Request body is a one-shot stream — reading it inside the loop crashed
  // on the second iteration (e.g. backend 307 /api/folders → /api/folders/),
  // losing the body and failing all redirected POST/PUT requests.
  let requestBody: string | Blob | undefined;
  if (method !== 'GET' && method !== 'HEAD') {
    const contentType = request.headers.get('content-type') || '';
    // For JSON requests, read as text to preserve JSON body.
    // Do NOT set content-length manually — String.length counts UTF-16 chars,
    // not UTF-8 bytes; Polish diacritics would produce a short Content-Length
    // and stall/truncate the upstream request. fetch computes it correctly.
    // UWAGA: nie logować requestBody — /api/auth/login niesie hasło w JSON.
    if (contentType.includes('application/json')) {
      requestBody = await request.text();
    } else {
      requestBody = await request.blob();
    }
  }

  while (redirectCount < maxRedirects) {
    const fetchInit: RequestInit = {
      method,
      headers,
      credentials: 'include',
      redirect: 'manual', // Handle redirects manually to preserve auth
    };
    if (requestBody !== undefined) {
      fetchInit.body = requestBody;
    }

    try {
      const response = await fetch(url, fetchInit);

      // Streaming passthrough dla czatu (odpowiedź strumieniowana z n8n)
      // Nie buforujemy body — przekazujemy ReadableStream 1:1 do przeglądarki.
      if (cleanPath[0] === 'chat' && response.ok && response.body) {
        const streamHeaders = new Headers();
        streamHeaders.set('Content-Type', response.headers.get('content-type') || 'text/plain; charset=utf-8');
        streamHeaders.set('Cache-Control', 'no-cache');
        streamHeaders.set('X-Accel-Buffering', 'no');
        streamHeaders.set('Access-Control-Allow-Origin', '*');
        return new NextResponse(response.body, { status: response.status, headers: streamHeaders });
      }

      // Handle redirect manually - preserve auth headers
      if (response.status >= 300 && response.status < 400 && response.headers.get('location')) {
        redirectCount++;
        const location = response.headers.get('location')!;
        const isAbsolute = location.startsWith('http');
        url = isAbsolute ? location : `${BACKEND_URL}${location}`;
        continue; // Follow redirect
      }

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
      if (redirectCount > 0) {
        return NextResponse.json({ detail: 'Backend redirect failed' }, { status: 502 });
      }
      return NextResponse.json({ detail: 'Backend unavailable' }, { status: 502 });
    }
  }

  return NextResponse.json({ detail: 'Too many redirects' }, { status: 502 });
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
