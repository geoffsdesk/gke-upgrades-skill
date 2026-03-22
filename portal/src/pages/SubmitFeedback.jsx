import React, { useState, useEffect } from 'react'
import { useAuth } from '../lib/AuthContext'
import { supabase } from '../lib/supabase'
import Layout from '../components/Layout'

const FEEDBACK_TYPES = [
  { value: 'correction', label: 'Correction', desc: 'Something in the skill is wrong or outdated', color: 'bg-red-100 text-red-800' },
  { value: 'missing', label: 'Missing Content', desc: 'Important topic not covered by the skill', color: 'bg-orange-100 text-orange-800' },
  { value: 'improvement', label: 'Improvement', desc: 'Existing content could be better or more precise', color: 'bg-blue-100 text-blue-800' },
  { value: 'new_eval', label: 'New Eval Suggestion', desc: 'A scenario that should be tested but isn\'t', color: 'bg-purple-100 text-purple-800' },
  { value: 'kb_update', label: 'KB Update', desc: 'New authoritative info from PM/engineering', color: 'bg-green-100 text-green-800' },
]

const TOPIC_AREAS = [
  'Release Channels & Version Lifecycle',
  'Maintenance Windows & Exclusions',
  'Node Pool Upgrade Strategies',
  'Control Plane Upgrades',
  'AI/ML & GPU Workloads',
  'Troubleshooting & Recovery',
  'Cluster Disruption Budget',
  'GKE Notifications',
  'gcloud Syntax & API',
  'Other',
]

const EVAL_IDS = Array.from({ length: 40 }, (_, i) => i + 1)

export default function SubmitFeedback() {
  const { user } = useAuth()
  const [submissions, setSubmissions] = useState([])
  const [form, setForm] = useState({
    type: '',
    topic: '',
    evalId: '',
    title: '',
    description: '',
    currentBehavior: '',
    expectedBehavior: '',
    source: '',
    priority: 'medium',
  })
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    loadMySubmissions()
  }, [])

  async function loadMySubmissions() {
    const { data } = await supabase
      .from('feedback')
      .select('id, type, title, status, created_at')
      .eq('submitted_by', user.displayName)
      .order('created_at', { ascending: false })
      .limit(10)
    if (data) setSubmissions(data)
  }

  function updateForm(field, value) {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setSuccess(false)

    const { error } = await supabase.from('feedback').insert({
      type: form.type,
      topic: form.topic,
      eval_id: form.evalId ? parseInt(form.evalId) : null,
      title: form.title,
      description: form.description,
      current_behavior: form.currentBehavior || null,
      expected_behavior: form.expectedBehavior || null,
      source: form.source || null,
      priority: form.priority,
      submitted_by: user.displayName,
      status: 'pending',
    })

    if (!error) {
      setSuccess(true)
      setForm({
        type: '', topic: '', evalId: '', title: '', description: '',
        currentBehavior: '', expectedBehavior: '', source: '', priority: 'medium',
      })
      loadMySubmissions()
      setTimeout(() => setSuccess(false), 3000)
    }

    setSubmitting(false)
  }

  const statusBadge = (status) => {
    const colors = {
      pending: 'bg-yellow-100 text-yellow-800',
      approved: 'bg-green-100 text-green-800',
      rejected: 'bg-red-100 text-red-800',
      incorporated: 'bg-blue-100 text-blue-800',
    }
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colors[status] || 'bg-gray-100 text-gray-800'}`}>
        {status}
      </span>
    )
  }

  return (
    <Layout>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Submission Form */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h2 className="text-xl font-semibold text-gke-dark mb-1">Submit Feedback</h2>
            <p className="text-sm text-gke-gray mb-6">
              Help improve the GKE Upgrades skill with corrections, missing content, or new eval ideas.
            </p>

            {success && (
              <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-gke-green">
                Feedback submitted successfully! It's now in the review queue.
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Type */}
              <div>
                <label className="block text-sm font-medium text-gke-gray mb-2">Feedback Type *</label>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {FEEDBACK_TYPES.map(t => (
                    <button
                      key={t.value}
                      type="button"
                      onClick={() => updateForm('type', t.value)}
                      className={`p-3 rounded-lg border text-left transition-all ${
                        form.type === t.value
                          ? 'border-gke-blue bg-blue-50 ring-2 ring-gke-blue/20'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${t.color}`}>
                        {t.label}
                      </span>
                      <p className="text-xs text-gke-gray mt-1">{t.desc}</p>
                    </button>
                  ))}
                </div>
              </div>

              {/* Topic + Eval */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gke-gray mb-1">Topic Area *</label>
                  <select
                    value={form.topic}
                    onChange={(e) => updateForm('topic', e.target.value)}
                    required
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-gke-blue outline-none"
                  >
                    <option value="">Select topic...</option>
                    {TOPIC_AREAS.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gke-gray mb-1">Related Eval (optional)</label>
                  <select
                    value={form.evalId}
                    onChange={(e) => updateForm('evalId', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-gke-blue outline-none"
                  >
                    <option value="">None</option>
                    {EVAL_IDS.map(id => <option key={id} value={id}>Eval {id}</option>)}
                  </select>
                </div>
              </div>

              {/* Title */}
              <div>
                <label className="block text-sm font-medium text-gke-gray mb-1">Title *</label>
                <input
                  type="text"
                  value={form.title}
                  onChange={(e) => updateForm('title', e.target.value)}
                  placeholder="Brief summary of the feedback"
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-gke-blue outline-none"
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-gke-gray mb-1">Description *</label>
                <textarea
                  value={form.description}
                  onChange={(e) => updateForm('description', e.target.value)}
                  placeholder="Detailed description of the feedback, including specific GKE features, gcloud commands, or version details..."
                  required
                  rows={4}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-gke-blue outline-none resize-y"
                />
              </div>

              {/* Current / Expected (for corrections) */}
              {(form.type === 'correction' || form.type === 'improvement') && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gke-gray mb-1">Current Behavior</label>
                    <textarea
                      value={form.currentBehavior}
                      onChange={(e) => updateForm('currentBehavior', e.target.value)}
                      placeholder="What the skill currently says or does..."
                      rows={3}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-gke-blue outline-none resize-y"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gke-gray mb-1">Expected Behavior</label>
                    <textarea
                      value={form.expectedBehavior}
                      onChange={(e) => updateForm('expectedBehavior', e.target.value)}
                      placeholder="What the skill should say instead..."
                      rows={3}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-gke-blue outline-none resize-y"
                    />
                  </div>
                </div>
              )}

              {/* Source */}
              <div>
                <label className="block text-sm font-medium text-gke-gray mb-1">Source / Reference</label>
                <input
                  type="text"
                  value={form.source}
                  onChange={(e) => updateForm('source', e.target.value)}
                  placeholder="Link to doc, design doc, internal ref, or 'personal expertise'"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-gke-blue outline-none"
                />
              </div>

              {/* Priority */}
              <div>
                <label className="block text-sm font-medium text-gke-gray mb-1">Priority</label>
                <div className="flex gap-3">
                  {['low', 'medium', 'high'].map(p => (
                    <label key={p} className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="radio"
                        name="priority"
                        value={p}
                        checked={form.priority === p}
                        onChange={() => updateForm('priority', p)}
                        className="text-gke-blue"
                      />
                      <span className="text-sm capitalize">{p}</span>
                    </label>
                  ))}
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting || !form.type || !form.topic || !form.title || !form.description}
                className="w-full bg-gke-blue text-white py-2.5 rounded-lg font-medium text-sm hover:bg-gke-dark-blue disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {submitting ? 'Submitting...' : 'Submit Feedback'}
              </button>
            </form>
          </div>
        </div>

        {/* My Submissions Sidebar */}
        <div>
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <h3 className="text-sm font-semibold text-gke-dark mb-3">My Recent Submissions</h3>
            {submissions.length === 0 ? (
              <p className="text-sm text-gke-gray">No submissions yet.</p>
            ) : (
              <div className="space-y-3">
                {submissions.map(s => (
                  <div key={s.id} className="p-3 bg-gray-50 rounded-lg">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-medium text-gke-dark line-clamp-2">{s.title}</p>
                      {statusBadge(s.status)}
                    </div>
                    <div className="flex items-center gap-2 mt-1.5">
                      <span className="text-xs text-gke-gray">
                        {new Date(s.created_at).toLocaleDateString()}
                      </span>
                      <span className="text-xs px-1.5 py-0.5 bg-gray-200 rounded text-gke-gray">
                        {s.type}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Quick Guide */}
          <div className="bg-blue-50 rounded-xl border border-blue-200 p-5 mt-4">
            <h3 className="text-sm font-semibold text-gke-dark-blue mb-2">Feedback Guide</h3>
            <ul className="text-xs text-gke-gray space-y-1.5">
              <li><strong>Corrections:</strong> When the skill gives wrong info (wrong flags, outdated limits, incorrect behavior)</li>
              <li><strong>Missing Content:</strong> Topics or scenarios not covered (new features, edge cases)</li>
              <li><strong>Improvements:</strong> Content exists but could be more precise or actionable</li>
              <li><strong>New Evals:</strong> Real-world scenarios that should be tested</li>
              <li><strong>KB Updates:</strong> Authoritative info from PM/engineering sources</li>
            </ul>
          </div>
        </div>
      </div>
    </Layout>
  )
}
