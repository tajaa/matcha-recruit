import { useState, useEffect } from 'preact/hooks'
import { api } from '../lib/api'
import type { AgentConfig, FeedItem } from '../lib/api'

interface Props {
  open: boolean
  onClose: () => void
}

export function Settings({ open, onClose }: Props) {
  const [config, setConfig] = useState<AgentConfig | null>(null)
  const [feeds, setFeeds] = useState<FeedItem[]>([])
  const [labels, setLabels] = useState('')
  const [maxEmails, setMaxEmails] = useState(25)
  const [interests, setInterests] = useState('')
  const [maxEntries, setMaxEntries] = useState(10)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState('')

  useEffect(() => {
    if (open) {
      api.getConfig().then((c) => {
        setConfig(c)
        setFeeds(c.feeds.length ? c.feeds : [{ url: '', name: '' }])
        setLabels(c.gmail_label_ids.join(', '))
        setMaxEmails(c.gmail_max_emails)
        setInterests(c.rss_interests)
        setMaxEntries(c.rss_max_entries_per_feed)
        setStatus('')
      })
    }
  }, [open])

  if (!open) return null

  const addFeed = () => setFeeds([...feeds, { url: '', name: '' }])

  const removeFeed = (i: number) => setFeeds(feeds.filter((_, idx) => idx !== i))

  const updateFeed = (i: number, field: 'url' | 'name', val: string) => {
    const updated = [...feeds]
    updated[i] = { ...updated[i], [field]: val }
    setFeeds(updated)
  }

  const handleSave = async () => {
    setSaving(true)
    setStatus('')
    try {
      const validFeeds = feeds.filter((f) => f.url.trim())
      const labelList = labels
        .split(',')
        .map((l) => l.trim())
        .filter(Boolean)

      const updated = await api.updateConfig({
        feeds: validFeeds,
        gmail_label_ids: labelList.length ? labelList : ['INBOX'],
        gmail_max_emails: maxEmails,
        rss_interests: interests,
        rss_max_entries_per_feed: maxEntries,
      })
      setConfig(updated)
      setFeeds(updated.feeds.length ? updated.feeds : [{ url: '', name: '' }])
      setStatus('saved')
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : 'Save failed')
    }
    setSaving(false)
  }

  if (!config) {
    return (
      <div class="settings-overlay" onClick={onClose}>
        <div class="settings-panel" onClick={(e) => e.stopPropagation()}>
          <div class="settings-loading">loading...</div>
        </div>
      </div>
    )
  }

  return (
    <div class="settings-overlay" onClick={onClose}>
      <div class="settings-panel" onClick={(e) => e.stopPropagation()}>
        <div class="settings-header">
          <h2>settings</h2>
          <button class="settings-close" onClick={onClose}>
            &#10005;
          </button>
        </div>

        <div class="settings-body">
          <section class="settings-section">
            <h3>rss feeds</h3>
            <div class="feed-list">
              {feeds.map((feed, i) => (
                <div class="feed-row" key={i}>
                  <input
                    type="text"
                    placeholder="https://example.com/rss"
                    value={feed.url}
                    onInput={(e) =>
                      updateFeed(i, 'url', (e.target as HTMLInputElement).value)
                    }
                  />
                  <input
                    type="text"
                    placeholder="name"
                    value={feed.name}
                    class="feed-name"
                    onInput={(e) =>
                      updateFeed(i, 'name', (e.target as HTMLInputElement).value)
                    }
                  />
                  <button
                    class="feed-remove"
                    onClick={() => removeFeed(i)}
                    title="Remove feed"
                  >
                    &#10005;
                  </button>
                </div>
              ))}
            </div>
            <button class="btn-add" onClick={addFeed}>
              + add feed
            </button>
          </section>

          <section class="settings-section">
            <h3>rss options</h3>
            <label>
              <span>interests</span>
              <input
                type="text"
                value={interests}
                onInput={(e) =>
                  setInterests((e.target as HTMLInputElement).value)
                }
                placeholder="AI, startups, engineering..."
              />
            </label>
            <label>
              <span>max entries per feed</span>
              <input
                type="number"
                value={maxEntries}
                min={1}
                max={50}
                onInput={(e) =>
                  setMaxEntries(
                    parseInt((e.target as HTMLInputElement).value) || 10
                  )
                }
              />
            </label>
          </section>

          <section class="settings-section">
            <h3>email</h3>
            <label>
              <span>gmail labels (comma-separated)</span>
              <input
                type="text"
                value={labels}
                onInput={(e) =>
                  setLabels((e.target as HTMLInputElement).value)
                }
                placeholder="INBOX"
              />
            </label>
            <label>
              <span>max emails to fetch</span>
              <input
                type="number"
                value={maxEmails}
                min={1}
                max={100}
                onInput={(e) =>
                  setMaxEmails(
                    parseInt((e.target as HTMLInputElement).value) || 25
                  )
                }
              />
            </label>
          </section>
        </div>

        <div class="settings-footer">
          {status && (
            <span class={`settings-status ${status === 'saved' ? 'ok' : 'err'}`}>
              {status === 'saved' ? 'settings saved' : status}
            </span>
          )}
          <button class="btn-sm primary" onClick={handleSave} disabled={saving}>
            {saving ? 'saving...' : 'save'}
          </button>
        </div>
      </div>
    </div>
  )
}
