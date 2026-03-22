import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext'

export default function Layout({ children }) {
  const { user, logout } = useAuth()
  const location = useLocation()

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gke-blue rounded-lg flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-semibold text-gke-dark">GKE Upgrades Skill</h1>
              <p className="text-xs text-gke-gray">Feedback Portal</p>
            </div>
          </div>

          {user && (
            <div className="flex items-center gap-4">
              <nav className="flex gap-1">
                <Link
                  to="/submit"
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    location.pathname === '/submit'
                      ? 'bg-gke-blue text-white'
                      : 'text-gke-gray hover:bg-gray-100'
                  }`}
                >
                  Submit Feedback
                </Link>
                {user.role === 'admin' && (
                  <Link
                    to="/admin"
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                      location.pathname === '/admin'
                        ? 'bg-gke-blue text-white'
                        : 'text-gke-gray hover:bg-gray-100'
                    }`}
                  >
                    Admin
                  </Link>
                )}
              </nav>
              <div className="flex items-center gap-2 text-sm text-gke-gray">
                <span>{user.displayName}</span>
                <button
                  onClick={logout}
                  className="text-gke-red hover:underline text-xs"
                >
                  Logout
                </button>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
        {children}
      </main>
    </div>
  )
}
