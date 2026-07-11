import { apiRequest } from './client'

export interface User {
  id: string
  email: string
  display_name: string
  created_at: string
}

export interface RegisterPayload {
  email: string
  password: string
  display_name: string
}

export interface LoginPayload {
  email: string
  password: string
}

export function register(payload: RegisterPayload): Promise<User> {
  return apiRequest<User>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function login(payload: LoginPayload): Promise<User> {
  return apiRequest<User>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function logout(): Promise<void> {
  return apiRequest<void>('/api/auth/logout', { method: 'POST' })
}

export function fetchCurrentUser(): Promise<User> {
  return apiRequest<User>('/api/auth/me')
}
