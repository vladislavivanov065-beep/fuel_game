import { create } from 'zustand'
import * as authApi from '../api/auth'
import { ApiError } from '../api/client'

type AuthStatus = 'idle' | 'loading' | 'authenticated' | 'unauthenticated'

interface AuthState {
  user: authApi.User | null
  status: AuthStatus
  error: string | null
  checkSession: () => Promise<void>
  login: (payload: authApi.LoginPayload) => Promise<void>
  register: (payload: authApi.RegisterPayload) => Promise<void>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  status: 'idle',
  error: null,

  checkSession: async () => {
    set({ status: 'loading' })
    try {
      const user = await authApi.fetchCurrentUser()
      set({ user, status: 'authenticated', error: null })
    } catch {
      set({ user: null, status: 'unauthenticated' })
    }
  },

  login: async (payload) => {
    set({ status: 'loading', error: null })
    try {
      const user = await authApi.login(payload)
      set({ user, status: 'authenticated', error: null })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Login failed'
      set({ status: 'unauthenticated', error: message })
      throw err
    }
  },

  register: async (payload) => {
    set({ status: 'loading', error: null })
    try {
      const user = await authApi.register(payload)
      set({ user, status: 'authenticated', error: null })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Registration failed'
      set({ status: 'unauthenticated', error: message })
      throw err
    }
  },

  logout: async () => {
    await authApi.logout()
    set({ user: null, status: 'unauthenticated', error: null })
  },
}))
