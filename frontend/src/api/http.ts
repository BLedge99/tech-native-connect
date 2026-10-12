export type ApiError = {
  error: {
    code: string;
    message: string;
    fields?: Record<string, string>;
  };
};

let csrfToken = '';

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(init.method ?? 'GET') && csrfToken) {
    headers.set('X-CSRF-Token', csrfToken);
  }

  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: 'include',
  });
  csrfToken = response.headers.get('X-CSRF-Token') ?? csrfToken;

  if (!response.ok) {
    const body = (await response.json()) as ApiError;
    throw body;
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}