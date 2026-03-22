import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext'

export default function LoginPage() {
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { user, loginWithInviteCode } = useAuth()
  const navigate = useNavigate()

  // If already logged in, redirect
  React.useEffect(() => {
    if (user) {
      navigate(user.role === 'admin' ? '/admin' : '/submit')
    }
  }, [user, navigate])

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const session = await loginWithInviteCode(code, name)
      navigate(session.role === 'admin' ? '/admin' : '/submit')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-gke-blue rounded-2xl mb-4 shadow-lg">
            <svg className="w-9 h-9 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gke-dark">GKE Upgrades Skill</h1>
          <p className="text-gke-gray mt-1">Feedback Portal</p>
        </div>

        {/* Login Card */}
        <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gke-dark mb-4">Sign in with invite code</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gke-gray mb-1">Your Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Jane Smith"
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-gke-blue focus:border-gke-blue outline-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gke-gray mb-1">Invite Code</label>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                placeholder="e.g. GKE-ABC123"
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono tracking-wider focus:ring-2 focus:ring-gke-blue focus:border-gke-blue outline-none"
              />
            </div>

            {error && (
              <div className="text-sm text-gke-red bg-red-50 border border-red-200 rounded-lg p-3">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !code || !name}
              className="w-full bg-gke-blue text-white py-2.5 rounded-lg font-medium text-sm hover:bg-gke-dark-blue disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-gke-gray mt-4">
          Don't have an invite code? Contact the skill maintainer.
        </p>
      </div>
    </div>
  )
}
