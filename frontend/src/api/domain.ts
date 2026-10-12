import { request } from './http';

export type Ref = { id: string; name: string; category?: string | null };
export type PublicUser = {
  id: string;
  display_name: string;
  first_name: string;
  role?: 'software_developer' | 'business_developer' | null;
  course?: Ref | null;
  bio?: string | null;
  looking_for?: string | null;
  skills?: Ref[];
  interests?: Ref[];
  has_photo?: boolean;
  photo_url?: string | null;
};
export type Profile = {
  bio: string | null;
  role: 'software_developer' | 'business_developer' | null;
  course: Ref | null;
  looking_for: string | null;
  skills: Ref[];
  interests: Ref[];
  has_photo: boolean;
  photo_url: string | null;
  profile_complete?: boolean;
};
export type MatchItem = {
  user: PublicUser;
  score: number;
  reasons: string[];
  shared_skills: Ref[];
  connection_state: 'none' | 'pending_incoming' | 'pending_outgoing' | 'connected';
};
export type Connection = {
  id: string;
  status: 'pending' | 'accepted' | 'declined';
  other: PublicUser;
  sender: PublicUser;
  receiver: PublicUser;
  message: string | null;
  created_at: string;
  responded_at: string | null;
  viewer_is_sender: boolean;
};
export type Message = {
  id: string;
  thread_id: string;
  sender_id: string;
  body: string;
  created_at: string;
  pending?: boolean;
  client_id?: string;
};
export type Thread = {
  id: string;
  other: PublicUser;
  last_message: Message | null;
  last_message_at: string | null;
  unread_count: number;
};
export type Idea = {
  id: string;
  title: string;
  description: string;
  category: string;
  skills_needed: string[];
  course: Ref | null;
  is_open: boolean;
  interest_count: number;
  created_at: string;
  author: PublicUser;
  viewer_has_interested: boolean;
  viewer_is_author: boolean;
};
export type Page<T> = { items: T[]; next_cursor: string | null };

const queryString = (values: Record<string, string | boolean | undefined>) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined) params.set(key, String(value));
  }
  return params.toString();
};

export function getProfile() {
  return request<{ id: string; email: string; display_name: string; first_name: string; is_admin: boolean; profile_complete: boolean; profile: Profile }>('/users/me');
}

export function updateProfile(input: {
  bio?: string | null;
  role?: Profile['role'];
  course_id?: string | null;
  looking_for?: string | null;
  skill_ids?: string[];
  interest_ids?: string[];
}) {
  return request<{ profile: Profile }>('/users/me', { method: 'PATCH', body: JSON.stringify(input) });
}

export function uploadPhoto(file: File) {
  const body = new FormData();
  body.set('file', file);
  return request<{ photo_url: string }>('/users/me/photo', { method: 'POST', body });
}

export function deletePhoto() {
  return request<void>('/users/me/photo', { method: 'DELETE' });
}

export const getCourses = () => request<Page<Ref>>('/courses?limit=100');
export const getSkills = () => request<Page<Ref>>('/skills?limit=100');
export const getInterests = () => request<Page<Ref>>('/interests?limit=100');
export const getPublicProfile = (id: string) => request<PublicUser & { profile: Profile }>(`/users/${encodeURIComponent(id)}`);

export function getMatches(params: {
  limit?: number;
  cursor?: string;
  skill?: string[];
  role?: string;
  course_id?: string;
  interest?: string[];
}) {
  const query = new URLSearchParams();
  if (params.limit) query.set('limit', String(params.limit));
  if (params.cursor) query.set('cursor', params.cursor);
  if (params.role) query.set('role', params.role);
  if (params.course_id) query.set('course_id', params.course_id);
  params.skill?.forEach((value) => query.append('skill', value));
  params.interest?.forEach((value) => query.append('interest', value));
  return request<Page<MatchItem>>(`/matches${query.size ? `?${query}` : ''}`);
}

export const createConnection = (receiver_id: string, message?: string) =>
  request<Connection>('/connections', { method: 'POST', body: JSON.stringify({ receiver_id, message }) });

export const getConnections = (filter: string) =>
  request<Page<Connection>>(`/connections?${queryString({ filter })}`);

export const answerConnection = (id: string, action: 'accept' | 'decline') =>
  request<Connection>(`/connections/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ action }) });

export const withdrawConnection = (id: string) =>
  request<void>(`/connections/${encodeURIComponent(id)}`, { method: 'DELETE' });

export const connectionSummary = () => request<{ received_pending: number; sent_pending: number; connected: number; unread_messages: number }>('/connections/summary');

export const getThreads = () => request<Page<Thread>>('/threads');
export const getThread = (id: string) => request<Thread>(`/threads/${encodeURIComponent(id)}`);
export const getMessages = (id: string, after?: string) => {
  const query = after ? `?after=${encodeURIComponent(after)}` : '';
  return request<Page<Message> & { last_read_at: string | null; unread_count: number }>(`/threads/${encodeURIComponent(id)}/messages${query}`);
};
export const postMessage = (id: string, body: string) =>
  request<Message>(`/threads/${encodeURIComponent(id)}/messages`, { method: 'POST', body: JSON.stringify({ body }) });

export const getNotifications = (limit = 20) =>
  request<Page<{ id: string; type: string; read_at: string | null; created_at: string; data: { text: string }; url: string }> & { unread_count: number }>(`/notifications?limit=${limit}`);
export const unreadNotificationCount = () => request<{ unread_count: number }>('/notifications/unread-count');
export const markNotificationRead = (id: string) =>
  request(`/notifications/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ read: true }) });
export const markAllNotificationsRead = () => request<void>('/notifications/read-all', { method: 'PATCH' });

export const getIdeas = (values: Record<string, string | boolean | undefined>) =>
  request<Page<Idea>>(`/ideas${queryString(values) ? `?${queryString(values)}` : ''}`);
export const saveIdea = (input: Partial<Idea> & { title: string; description: string; category: string; skills_needed: string[] }) =>
  request<Idea>('/ideas', { method: 'POST', body: JSON.stringify(input) });
export const updateIdea = (id: string, input: Partial<Idea>) =>
  request<Idea>(`/ideas/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(input) });
export const deleteIdea = (id: string) => request<void>(`/ideas/${encodeURIComponent(id)}`, { method: 'DELETE' });
export const interestInIdea = (id: string) => request(`/ideas/${encodeURIComponent(id)}/interest`, { method: 'POST' });
export const withdrawIdeaInterest = (id: string) => request<void>(`/ideas/${encodeURIComponent(id)}/interest`, { method: 'DELETE' });

export const getAdminOverview = () => request<Record<string, number>>('/admin/overview');
export const getAdminUsers = (search = '') => request<Page<PublicUser & { email: string; is_admin: boolean; is_active: boolean; role: string | null }>>(`/admin/users${search ? `?search=${encodeURIComponent(search)}` : ''}`);
export const getAdminAudit = () => request<Page<{ id: string; action: string; created_at: string; target_type: string | null; metadata: object; admin: PublicUser }>>('/admin/audit');
export const adminAction = (userId: string, action: string) => request(`/admin/users/${encodeURIComponent(userId)}/${action}`, { method: 'POST' });
export const adminReferenceList = (kind: 'courses' | 'skills' | 'interests') => request<Page<Ref>>(`/admin/${kind}`);
export const adminCreateReference = (kind: 'courses' | 'skills' | 'interests', input: { name: string; category?: string }) =>
  request(`/admin/${kind}`, { method: 'POST', body: JSON.stringify(input) });
export const adminRenameReference = (kind: 'courses' | 'skills' | 'interests', id: string, input: { name?: string; category?: string | null }) =>
  request(`/admin/${kind}/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(input) });
export const adminDeleteReference = (kind: 'skills' | 'interests', id: string) =>
  request<void>(`/admin/${kind}/${encodeURIComponent(id)}`, { method: 'DELETE' });
