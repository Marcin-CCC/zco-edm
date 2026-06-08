import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://backend:8000';

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
  
  // DEBUG: Log incoming request details
  console.log(`[PROXY] === REQUEST START ===`);
  console.log(`[PROXY] Method: ${method}`);
  console.log(`[PROXY] Path: ${path.join('/')}`);
  console.log(`[PROXY] Clean Path: ${cleanPath.join('/')}`);
  console.log(`[PROXY] Target URL: ${fullUrl}`);
  console.log(`[PROXY] BACKEND_URL: ${BACKEND_URL}`);
  console.log(`[PROXY] Original headers:`, Object.fromEntries(request.headers.entries()));
  
  // Get auth token from request headers
  // Note: Next.js lowercases header names, so we check both 'authorization' and 'Authorization'
  let authHeader = request.headers.get('authorization') || request.headers.get('Authorization');
  console.log(`[PROXY] Auth header from request: ${authHeader ? 'EXISTS' : 'MISSING'}`);
  
  // Also try to get token from cookies (fallback)
  const tokenCookie = request.cookies.get('auth_token')?.value;
  console.log(`[PROXY] Cookie auth_token: ${tokenCookie ? 'EXISTS' : 'MISSING'}`);
  
  // Build headers - copy all headers except problematic ones
  const headers = new Headers();
  
  // Copy all headers except host, cookie, and others that cause issues
  const skipHeaders = ['host', 'cookie', 'origin', 'referer'];
  request.headers.forEach((value, key) => {
    if (skipHeaders.includes(key.toLowerCase())) return;
    headers.set(key, value);
  });
  
  // Set auth header explicitly if found
  if (authHeader) {
    headers.set('authorization', authHeader);
    console.log(`[PROXY] Set Authorization header from request`);
  } else if (tokenCookie) {
    headers.set('authorization', `Bearer ${tokenCookie}`);
    console.log(`[PROXY] Set Authorization header from cookie`);
  } else {
    console.log(`[PROXY] WARNING: No auth token found - backend will return 401`);
  }
  
  console.log(`[PROXY] Final Authorization header: ${headers.get('authorization') ? 'SET' : 'NOT SET'}`);

  let url = fullUrl;
  let redirectCount = 0;
  const maxRedirects = 5;

  while (redirectCount < maxRedirects) {
    const fetchInit: RequestInit = {
      method,
      headers,
      credentials: 'include',
      redirect: 'manual', // Handle redirects manually to preserve auth
    };

    if (method !== 'GET' && method !== 'HEAD') {
      const contentType = request.headers.get('content-type') || '';
      console.log(`[PROXY] Content-Type: ${contentType}`);
      console.log(`[PROXY] Method: ${method}`);
      // For JSON requests, read as text to preserve JSON body
      if (contentType.includes('application/json')) {
        const textBody = await request.text();
        console.log(`[PROXY] JSON body: ${textBody}`);
        fetchInit.body = textBody;
        headers.set('content-length', String(textBody.length));
      } else {
        const body = await request.blob();
        fetchInit.body = body;
      }
    }

    try {
      const response = await fetch(url, fetchInit);

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
