import { request } from './http';

export type User = {
  id: string;
  email: string;
  display_name: string;
  first_name: string;
  is_admin: boolean;
  profile_complete: boolean;
  is_active?: boolean;
  created_at: string;
  profile?: {
    role: 'software_developer' | 'business_developer' | null;
    bio: string | null;
    looking_for: string | null;
  };
};

export type Credentials = { email: string; password: string };

export function currentUser() {
  return request<User>('/users/me');
}

export function registerAccount(input: Credentials & { display_name: string }) {
  return request<User>('/auth/register', { method: 'POST', body: JSON.stringify(input) });
}

export function loginAccount(input: Credentials) {
  return request<User>('/auth/login', { method: 'POST', body: JSON.stringify(input) });
}

export function logoutAccount() {
  return request<void>('/auth/logout', { method: 'POST' });
}

export function requestMagicLink(email: string) {
  return request<{ message: string; dev_magic_link?: string }>('/auth/magic-link', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}