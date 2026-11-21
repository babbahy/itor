'use client';

import {
  CalendarDays,
  Check,
  ClipboardCheck,
  Clock3,
  ExternalLink,
  Lightbulb,
  Plus,
  Video,
} from 'lucide-react';
import { type FormEvent } from 'react';
import type { Meeting, Preflight } from '@/lib/api';
import { dateLabel, meetingCountdown, timeLabel } from '@/lib/presentation';
import { Badge, Notice, Spinner } from './ui';

export function MeetingHero({
  meeting,
  now,
  preflight,
  join,
  joinBlocked,
  down,
  loading,
  preparing,
  onPrepare,
  onAdd,
  onChecklist,
}: {
  meeting?: Meeting;
  now: number;
  preflight?: Preflight;
  join: string | null;
  joinBlocked: boolean;
  down: boolean;
  loading: boolean;
  preparing: boolean;
  onPrepare: () => void;
  onAdd: () => void;
  onChecklist: () => void;
}) {
  return (
    <article className="hero-card" aria-label="Next meeting">
      <div className="hero-content">
        <div className="hero-kicker">
          <CalendarDays size={17} />
          <span className="eyebrow">Up next</span>
          {meeting && (
            <Badge tone="violet">{meetingCountdown(meeting, now)}</Badge>
          )}
        </div>
        <h2 className={loading ? 'skeleton hero-skeleton' : ''}>
          {meeting?.title ??
            (loading ? 'Finding your next meeting' : 'No upcoming meeting')}
        </h2>
        {meeting ? (
          <>
            <div className="meeting-meta">
              <span>
                <Video size={16} />
                {meeting.platform}
              </span>
              <span>
                <Clock3 size={16} />
                {timeLabel(meeting.start_at)} ·{' '}
                {Math.round(
                  (Date.parse(meeting.end_at) - Date.parse(meeting.start_at)) /
                    60_000,
                )}{' '}
                min
              </span>
              <span className="meeting-source">
                {meeting.source === 'demo' ? 'Demo meeting' : 'Local meeting'}
              </span>
            </div>
            {meeting.notes && <p className="meeting-notes">{meeting.notes}</p>}
          </>
        ) : (
          <p className="meeting-notes">
            {down
              ? 'Start the local device agent to see your schedule.'
              : 'Add a meeting to run a preflight and keep your join link handy.'}
          </p>
        )}
        <div className="button-row hero-actions">
          {meeting ? (
            <button
              className="button primary"
              disabled={down || preparing}
              onClick={onPrepare}
            >
              {preparing ? (
                <Spinner />
              ) : preflight ? (
                <Check size={18} />
              ) : (
                <ClipboardCheck size={18} />
              )}
              {preparing
                ? 'Checking device…'
                : preflight
                  ? 'Run preflight again'
                  : 'Prepare my meeting'}
            </button>
          ) : (
            <button
              className="button primary"
              disabled={down || loading}
              onClick={onAdd}
            >
              <Plus size={18} />
              Add a meeting
            </button>
          )}
          {meeting &&
            (join ? (
              <a
                className="button hero-secondary"
                href={join}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink size={16} />
                Join meeting
              </a>
            ) : (
              <span className="join-hint">
                {joinBlocked ? 'Join link unavailable offline' : 'No join link'}
              </span>
            ))}
        </div>
        {preflight && (
          <p className="prepared-note">
            Preflight completed at {timeLabel(preflight.completed_at)}{' '}
            <button
              className="text-button hero-checklist-link"
              onClick={onChecklist}
            >
              View checklist
            </button>
          </p>
        )}
      </div>
    </article>
  );
}

export function Upcoming({
  meetings,
  now,
  stale,
  onAdd,
}: {
  meetings: Meeting[];
  now: number;
  stale: boolean;
  onAdd: () => void;
}) {
  return (
    <article className="card upcoming-panel">
      <div className="panel-heading">
        <div>
          <h2>Upcoming meetings</h2>
          {stale && <p>Last loaded schedule</p>}
        </div>
        <button
          className="icon-button"
          aria-label="Add a meeting"
          title="Add a meeting"
          onClick={onAdd}
          disabled={stale}
        >
          <Plus size={19} />
        </button>
      </div>
      {meetings.length ? (
        <ul>
          {meetings.slice(0, 4).map((meeting) => (
            <li key={meeting.id}>
              <span className="mini-icon">
                <Video size={16} />
              </span>
              <div>
                <strong>{meeting.title}</strong>
                <p>
                  {timeLabel(meeting.start_at)} ·{' '}
                  {dateLabel(meeting.start_at, {
                    weekday: 'short',
                    month: 'short',
                    day: 'numeric',
                  })}
                </p>
              </div>
              <span className="schedule-time">
                {meetingCountdown(meeting, now)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted empty-line">
          No later meetings on your local schedule.
        </p>
      )}
    </article>
  );
}

export function DailyTip() {
  return (
    <article className="card tip-panel">
      <span className="mini-icon">
        <Lightbulb size={18} />
      </span>
      <div>
        <h2>Before you join</h2>
        <p>
          Check your microphone and speaker in the meeting app, especially after
          connecting a headset.
        </p>
      </div>
    </article>
  );
}

export function MeetingForm({
  now,
  busy,
  error,
  onSave,
  onCancel,
}: {
  now: number;
  busy: boolean;
  error?: string;
  onSave: (body: object) => void;
  onCancel: () => void;
}) {
  const local = new Date(now);
  const pad = (value: number) => String(value).padStart(2, '0');
  const defaultDate = `${local.getFullYear()}-${pad(local.getMonth() + 1)}-${pad(local.getDate())}`;
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const start = new Date(`${data.get('date')}T${data.get('time')}`);
    if (!Number.isFinite(start.getTime())) return;
    onSave({
      title: String(data.get('title')).trim(),
      start_at: start.toISOString(),
      duration_minutes: Number(data.get('duration')),
      platform: String(data.get('platform')),
      join_url: String(data.get('join_url')).trim() || null,
      notes: String(data.get('notes')).trim() || null,
    });
  }
  return (
    <form className="meeting-form" onSubmit={submit}>
      <label>
        Meeting title
        <input
          name="title"
          placeholder="Project check-in"
          required
          minLength={1}
          maxLength={120}
        />
      </label>
      <div className="form-grid">
        <label>
          Date
          <input name="date" type="date" defaultValue={defaultDate} required />
        </label>
        <label>
          Time
          <input name="time" type="time" required />
        </label>
      </div>
      <div className="form-grid">
        <label>
          Duration in minutes
          <input
            name="duration"
            type="number"
            min={5}
            max={480}
            defaultValue={30}
            required
          />
        </label>
        <label>
          Platform
          <select name="platform" defaultValue="Microsoft Teams">
            <option>Microsoft Teams</option>
            <option>Google Meet</option>
            <option>Zoom</option>
            <option>Webex</option>
            <option>In person</option>
            <option>Other</option>
          </select>
        </label>
      </div>
      <label>
        Join URL <span>Optional</span>
        <input
          name="join_url"
          type="url"
          placeholder="https://…"
          maxLength={2048}
        />
      </label>
      <label>
        Preparation notes <span>Optional</span>
        <textarea name="notes" maxLength={800} rows={2} />
      </label>
      {error && <Notice kind="error">{error}</Notice>}
      <div className="button-row dialog-actions">
        <button className="button secondary" type="button" onClick={onCancel}>
          Cancel
        </button>
        <button className="button primary" type="submit" disabled={busy}>
          {busy && <Spinner />}Add meeting
        </button>
      </div>
    </form>
  );
}
