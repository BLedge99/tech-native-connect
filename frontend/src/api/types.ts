/** Typed response shapes. Mirrors backend/app/schemas.py.
 *
 * Note UserPublic deliberately has no `email` field — that is the leak guard
 * from specs/03_profiles.md §6, and making it unrepresentable in the type is
 * the first line of defence.
 */

export type UserRole = 'software_developer' | 'business_developer'
export type ConnectionState =
  | 'none'
  | 'pending_incoming'
  | 'pending_outgoing'
  | 'connected'
  | 'declined'

export interface Ref {
  id: string
  name: string
}

export interface Course {
  id: string
  name: string
}

export interface Profile {
  bio: string | null
  role: UserRole | null
  course: Course | null
  looking_for: string | null
  skills: Ref[]
  interests: Ref[]
  profile_complete: boolean
  has_photo: boolean
  photo_url: string | null
}

export interface UserPublic {
  id: string
  display_name: string
  first_name: string
  created_at: string | null
  profile: Profile
}

export interface Me {
  id: string
  email: string
  display_name: string
  first_name: string
  is_admin: boolean
  is_active: boolean
  created_at: string | null
  last_login_at: string | null
  profile: Profile
  csrf_token: string
}

export interface UserSummary {
  id: string
  display_name: string
  first_name: string | null
  has_photo: boolean
  photo_url: string | null
}

export interface Match {
  user: UserPublic
  score: number
  reasons: string[]
  shared_skills: Ref[]
  connection_state: ConnectionState
}

export interface Connection {
  id: string
  status: 'pending' | 'accepted' | 'declined'
  other: UserSummary
  message: string | null
  created_at: string
  responded_at: string | null
  unread_count: number
  thread_id: string | null
}

export interface ConnectionSummary {
  received_pending: number
  sent_pending: number
  connected: number
  unread_messages: number
}

export interface Message {
  id: string
  thread_id: string
  sender_id: string
  body: string
  created_at: string
  client_id?: string
  pending?: boolean
}

export interface Thread {
  id: string
  other: UserSummary
  last_message: Message | null
  unread_count: number
  last_message_at: string | null
}

export interface AppNotification {
  id: string
  type: string
  text: string
  url: string
  read_at: string | null
  created_at: string
  actor_id: string | null
  data: Record<string, unknown>
}

export type IdeaCategory =
  | 'find_problem'
  | 'build_product'
  | 'design_brand'
  | 'run_campaign'
  | 'other'

export interface Idea {
  id: string
  title: string
  description: string
  category: IdeaCategory
  skills_needed: string[]
  course: Course | null
  is_open: boolean
  interest_count: number
  viewer_has_interested: boolean
  created_at: string
  author: UserSummary
}

export interface AdminUser {
  id: string
  email: string
  display_name: string
  first_name: string
  is_admin: boolean
  is_active: boolean
  created_at: string
  last_login_at: string | null
  role: UserRole | null
  course: Course | null
  skills: Ref[]
  profile_complete: boolean
}

export interface AdminOverview {
  total_users: number
  active_users: number
  new_this_week: number
  connections_made: number
  project_ideas: number
}

export interface AuditRow {
  id: string
  admin_id: string
  action: string
  target_type: string | null
  target_id: string | null
  metadata: Record<string, unknown>
  created_at: string
}

export interface Page<T> {
  items: T[]
  next_cursor: string | null
}