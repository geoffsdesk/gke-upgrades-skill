import React, { createContext, useContext, useState, useEffect } from 'react'
import { supabase } from './supabase'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Check for existing session in localStorage
    const stored = localStorage.getItem('gke_feedback_session')
    if (stored) {
      try {
        const parsed = JSON.parse(stored)
        // Validate session hasn't expired (24h)
        if (parsed.expiresAt > Date.now()) {
          setUser(parsed)
        } else {
          localStorage.removeItem('gke_feedback_session')
        }
      } catch { /* ignore */ }
    }
    setLoading(false)
  }, [])

  async function loginWithInviteCode(code, displayName) {
    // Validate invite code against Supabase
    const { data, error } = await supabase
      .from('invite_codes')
      .select('*')
      .eq('code', code.trim().toUpperCase())
      .eq('active', true)
      .single()

    if (error || !data) {
      throw new Error('Invalid or expired invite code')
    }

    // Check if max uses exceeded
    if (data.max_uses && data.uses >= data.max_uses) {
      throw new Error('This invite code has been used too many times')
    }

    // Increment usage
    await supabase
      .from('invite_codes')
      .update({ uses: (data.uses || 0) + 1 })
      .eq('id', data.id)

    const session = {
      id: crypto.randomUUID(),
      displayName: displayName.trim(),
      role: data.role, // 'reviewer' or 'admin'
      inviteCodeId: data.id,
      expiresAt: Date.now() + 24 * 60 * 60 * 1000, // 24h
    }

    localStorage.setItem('gke_feedback_session', JSON.stringify(session))
    setUser(session)
    return session
  }

  function logout() {
    localStorage.removeItem('gke_feedback_session')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, loginWithInviteCode, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
