import React, { useState, useEffect } from 'react'
import { useAuth } from '../lib/AuthContext'
import { supabase } from '../lib/supabase'
import Layout from '../components/Layout'

const STATUS_OPTIONS = ['pending', 'approved', 'rejected', 'incorporated']
const STATUS_COLORS = {
  pending: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  approved: 'bg-green-100 text-green-800 border-green-300',
  rejected: 'bg-red-100 text-red-800 border-red-300',
  incorporated: 'bg-blue-100 text-blue-800 border-blue-300',
}

export default function AdminDashboard() {
  const { user } = useAuth()
  const [feedback, setFeedback] = useState([])
  const [filter, setFilter] = useState('pending')
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [stats, setStats] = useState({})
  const [inviteCodes, setInviteCodes] = useState([])
  const [showInvites, setShowInvites] = useState(false)
  const [newCode, setNewCode] = useState({ code: '', role: 'reviewer', max_uses: 10 })

  useEffect(() => { loadFeedback(); loadStats(); loadInviteCodes() }, [filter])

  async function loadFeedback() {
    setLoading(true)
    let query = supabase
      .from('feedback')
      .select('*')
      .order('created_at', { ascending: false })

    if (filter !== 'all') {
      query = query.eq('status', filter)
    }

    const { data } = await query.limit(100)
    setFeedback(data || [])
    setLoading(false)
  }

  async function loadStats() {
    const { data } = await supabase.from('feedback').select('status')
    if (data) {
      const counts = {}
      data.forEach(d => { counts[d.status] = (counts[d.status] || 0) + 1 })
      setStats(counts)
    }
  }

  async function loadInviteCodes() {
    const { data } = await supabase
      .from('invite_codes')
      .select('*')
      .order('created_at', { ascending: false })
    if (data) setInviteCodes(data)
  }

  async function updateStatus(id, newStatus) {
    await supabase
      .from('feedback')
      .update({
        status: newStatus,
        reviewed_by: user.displayName,
        reviewed_at: new Date().toISOString(),
      })
      .eq('id', id)
    loadFeedback()
    loadStats()
    if (selected?.id === id) {
      setSelected(prev => ({ ...prev, status: newStatus }))
    }
  }

  async function addAdminNote(id, note) {
    await supabase
      .from('feedback')
      .update({ admin_notes: note })
      .eq('id', id)
  }

  async function createInviteCode() {
    if (!newCode.code) return
    await supabase.from('invite_codes').insert({
      code: newCode.code.toUpperCase(),
      role: newCode.role,
      max_uses: parseInt(newCode.max_uses) || null,
      active: true,
      uses: 0,
    })
    setNewCode({ code: '', role: 'reviewer', max_uses: 10 })
    loadInviteCodes()
  }

  async function toggleInviteCode(id, active) {
    await supabase.from('invite_codes').update({ active: !active }).eq('id', id)
    loadInviteCodes()
  }

  function exportApproved() {
    const approved = feedback.filter(f => f.status === 'approved')
    const exportData = {
      exported_at: new Date().toISOString(),
      exported_by: user.displayName,
      count: approved.length,
      feedback: approved.map(f => ({
        id: f.id,
        type: f.type,
        topic: f.topic,
        eval_id: f.eval_id,
        title: f.title,
        description: f.description,
        current_behavior: f.current_behavior,
        expected_behavior: f.expected_behavior,
        source: f.source,
        priority: f.priority,
        submitted_by: f.submitted_by,
        submitted_at: f.created_at,
      })),
    }
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `feedback-export-${new Date().toISOString().split('T')[0]}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Layout>
      {/* Stats Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
        {['all', ...STATUS_OPTIONS].map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`p-3 rounded-xl border text-center transition-all ${
              filter === s
                ? 'border-gke-blue bg-blue-50 ring-2 ring-gke-blue/20'
                : 'border-gray-200 bg-white hover:border-gray-300'
            }`}
          >
            <div className="text-2xl font-bold text-gke-dark">
              {s === 'all'
                ? Object.values(stats).reduce((a, b) => a + b, 0)
                : stats[s] || 0}
            </div>
            <div className="text-xs text-gke-gray capitalize">{s}</div>
          </button>
        ))}
      </div>

      <div className="flex gap-3 mb-4">
        <button
          onClick={exportApproved}
          className="px-4 py-2 bg-gke-green text-white rounded-lg text-sm font-medium hover:bg-green-700 transition-colors"
        >
          Export Approved as JSON
        </button>
        <button
          onClick={() => setShowInvites(!showInvites)}
          className="px-4 py-2 bg-white border border-gray-300 text-gke-gray rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
        >
          {showInvites ? 'Hide' : 'Manage'} Invite Codes
        </button>
      </div>

      {/* Invite Codes Panel */}
      {showInvites && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6">
          <h3 className="text-sm font-semibold text-gke-dark mb-3">Invite Codes</h3>
          <div className="flex gap-2 mb-4">
            <input
              type="text"
              value={newCode.code}
              onChange={e => setNewCode(p => ({ ...p, code: e.target.value.toUpperCase() }))}
              placeholder="GKE-CODE"
              className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm font-mono w-40"
            />
            <select
              value={newCode.role}
              onChange={e => setNewCode(p => ({ ...p, role: e.target.value }))}
              className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm"
            >
              <option value="reviewer">Reviewer</option>
              <option value="admin">Admin</option>
            </select>
            <input
              type="number"
              value={newCode.max_uses}
              onChange={e => setNewCode(p => ({ ...p, max_uses: e.target.value }))}
              placeholder="Max uses"
              className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm w-24"
            />
            <button
              onClick={createInviteCode}
              disabled={!newCode.code}
              className="px-4 py-1.5 bg-gke-blue text-white rounded-lg text-sm disabled:opacity-50"
            >
              Create
            </button>
          </div>
          <div className="space-y-2">
            {inviteCodes.map(ic => (
              <div key={ic.id} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                <div className="flex items-center gap-3">
                  <code className="text-sm font-mono font-bold">{ic.code}</code>
                  <span className="text-xs text-gke-gray">{ic.role}</span>
                  <span className="text-xs text-gke-gray">{ic.uses}/{ic.max_uses || '\u221e'} uses</span>
                </div>
                <button
                  onClick={() => toggleInviteCode(ic.id, ic.active)}
                  className={`text-xs px-2 py-1 rounded ${ic.active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}
                >
                  {ic.active ? 'Active' : 'Disabled'}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Feedback List + Detail */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* List */}
        <div className="lg:col-span-2 space-y-2">
          {loading ? (
            <div className="text-center py-8 text-gke-gray">Loading...</div>
          ) : feedback.length === 0 ? (
            <div className="text-center py-8 text-gke-gray">No {filter} feedback.</div>
          ) : (
            feedback.map(f => (
              <button
                key={f.id}
                onClick={() => setSelected(f)}
                className={`w-full text-left p-4 rounded-xl border transition-all ${
                  selected?.id === f.id
                    ? 'border-gke-blue bg-blue-50 ring-2 ring-gke-blue/20'
                    : 'border-gray-200 bg-white hover:border-gray-300'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <h4 className="text-sm font-medium text-gke-dark line-clamp-1">{f.title}</h4>
                  <span className={`shrink-0 px-2 py-0.5 rounded-full text-xs font-medium border ${STATUS_COLORS[f.status]}`}>
                    {f.status}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="text-xs px-1.5 py-0.5 bg-gray-100 rounded text-gke-gray">{f.type}</span>
                  <span className="text-xs text-gke-gray">{f.submitted_by}</span>
                  <span className="text-xs text-gke-gray">{new Date(f.created_at).toLocaleDateString()}</span>
                </div>
              </button>
            ))
          )}
        </div>

        {/* Detail */}
        <div className="lg:col-span-3">
          {selected ? (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 sticky top-6">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-lg font-semibold text-gke-dark">{selected.title}</h3>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${STATUS_COLORS[selected.status]}`}>
                      {selected.status}
                    </span>
                    <span className="text-xs text-gke-gray">{selected.type}</span>
                    <span className="text-xs text-gke-gray">{selected.topic}</span>
                    {selected.eval_id && (
                      <span className="text-xs px-1.5 py-0.5 bg-purple-100 text-purple-800 rounded">
                        Eval {selected.eval_id}
                      </span>
                    )}
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      selected.priority === 'high' ? 'bg-red-100 text-red-800' :
                      selected.priority === 'medium' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-gray-100 text-gray-600'
                    }`}>
                      {selected.priority}
                    </span>
                  </div>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-xs font-semibold text-gke-gray uppercase tracking-wide">Description</label>
                  <p className="text-sm text-gke-dark mt-1 whitespace-pre-wrap">{selected.description}</p>
                </div>

                {selected.current_behavior && (
                  <div>
                    <label className="text-xs font-semibold text-gke-red uppercase tracking-wide">Current Behavior</label>
                    <p className="text-sm text-gke-dark mt-1 whitespace-pre-wrap bg-red-50 p-3 rounded-lg">{selected.current_behavior}</p>
                  </div>
                )}

                {selected.expected_behavior && (
                  <div>
                    <label className="text-xs font-semibold text-gke-green uppercase tracking-wide">Expected Behavior</label>
                    <p className="text-sm text-gke-dark mt-1 whitespace-pre-wrap bg-green-50 p-3 rounded-lg">{selected.expected_behavior}</p>
                  </div>
                )}

                {selected.source && (
                  <div>
                    <label className="text-xs font-semibold text-gke-gray uppercase tracking-wide">Source</label>
                    <p className="text-sm text-gke-dark mt-1">{selected.source}</p>
                  </div>
                )}

                <div className="text-xs text-gke-gray">
                  Submitted by <strong>{selected.submitted_by}</strong> on {new Date(selected.created_at).toLocaleString()}
                  {selected.reviewed_by && (
                    <span> · Reviewed by <strong>{selected.reviewed_by}</strong> on {new Date(selected.reviewed_at).toLocaleString()}</span>
                  )}
                </div>

                {/* Admin Actions */}
                <div className="border-t border-gray-200 pt-4">
                  <label className="text-xs font-semibold text-gke-gray uppercase tracking-wide mb-2 block">Actions</label>
                  <div className="flex gap-2">
                    {selected.status !== 'approved' && (
                      <button
                        onClick={() => updateStatus(selected.id, 'approved')}
                        className="px-4 py-2 bg-gke-green text-white rounded-lg text-sm font-medium hover:bg-green-700"
                      >
                        Approve
                      </button>
                    )}
                    {selected.status !== 'rejected' && (
                      <button
                        onClick={() => updateStatus(selected.id, 'rejected')}
                        className="px-4 py-2 bg-gke-red text-white rounded-lg text-sm font-medium hover:bg-red-700"
                      >
                        Reject
                      </button>
                    )}
                    {selected.status === 'approved' && (
                      <button
                        onClick={() => updateStatus(selected.id, 'incorporated')}
                        className="px-4 py-2 bg-gke-blue text-white rounded-lg text-sm font-medium hover:bg-blue-700"
                      >
                        Mark Incorporated
                      </button>
                    )}
                    {selected.status !== 'pending' && (
                      <button
                        onClick={() => updateStatus(selected.id, 'pending')}
                        className="px-4 py-2 bg-white border border-gray-300 text-gke-gray rounded-lg text-sm font-medium hover:bg-gray-50"
                      >
                        Reset to Pending
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
              <p className="text-gke-gray">Select a feedback item to review.</p>
            </div>
          )}
        </div>
      </div>
    </Layout>
  )
}
