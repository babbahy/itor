'use client';

import {
  CircleAlert,
  CircleCheck,
  FlaskConical,
  MessageSquare,
  Send,
  Sparkles,
  WifiOff,
  Wrench,
} from 'lucide-react';
import Link from 'next/link';
import { useState, type ReactNode } from 'react';
import type { Diagnosis, Fix, Ticket } from '@/lib/api';
import { duration, providerLabel, timeLabel } from '@/lib/presentation';
import { Badge, Notice, Spinner } from './ui';

export type HomeStatus = {
  tone: 'green' | 'amber' | 'muted';
  title: string;
  detail: string;
  offline: boolean;
};

export function HomeScreen({
  status,
  paidSeconds,
  down,
  checking,
  diagnosis,
  checkError,
  fixes,
  planning,
  canStopWorkload,
  stopping,
  outcome,
  notice,
  onCheck,
  onQuickFix,
  onStopWorkload,
  onAskIT,
  onDemo,
}: {
  status: HomeStatus;
  paidSeconds?: number;
  down: boolean;
  checking: boolean;
  diagnosis?: Diagnosis;
  checkError?: string;
  fixes?: Fix[];
  planning?: string;
  canStopWorkload: boolean;
  stopping: boolean;
  outcome?: ReactNode;
  notice?: ReactNode;
  onCheck: (question: string) => void;
  onQuickFix: (fix: Fix) => void;
  onStopWorkload: () => void;
  onAskIT: (diagnosis?: string) => void;
  onDemo: () => void;
}) {
  const [describing, setDescribing] = useState(false);
  const [question, setQuestion] = useState('');
  const Icon = status.offline ? WifiOff : status.tone === 'green' ? CircleCheck : CircleAlert;
  return (
    <div className="home">
      <header className="home-brand">
        <span className="brand-icon">
          <Sparkles size={20} fill="currentColor" strokeWidth={1.5} />
        </span>
        <strong>itor</strong>
      </header>
      {notice}
      <section className={`home-status home-${status.tone}`} aria-live="polite">
        <Icon size={44} aria-hidden="true" />
        <h1>{status.title}</h1>
        <p>{status.detail}</p>
      </section>

      {!diagnosis && !checking && (
        <div className="home-actions">
          {describing ? (
            <form
              className="home-describe"
              onSubmit={(event) => {
                event.preventDefault();
                onCheck(question);
              }}
            >
              <label htmlFor="problem">What is not working? (optional)</label>
              <input
                id="problem"
                autoFocus
                maxLength={400}
                placeholder="For example: websites don't load, Teams is frozen…"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
              />
              <button className="button primary big" type="submit" disabled={down}>
                <Wrench size={20} />
                Check and fix
              </button>
            </form>
          ) : (
            <button className="button primary big" disabled={down} onClick={() => setDescribing(true)}>
              <Wrench size={20} />
              Fix my problem
            </button>
          )}
          <button className="button secondary big" disabled={down} onClick={() => onAskIT()}>
            <MessageSquare size={20} />
            Ask IT
          </button>
        </div>
      )}

      {checking && (
        <div className="home-card home-center">
          <Spinner />
          <p>itor is checking your PC and connection…</p>
        </div>
      )}
      {checkError && <Notice kind="error">{checkError}</Notice>}

      {diagnosis && !checking && (
        <article className="home-card">
          <Badge tone={diagnosis.provider === 'rules' ? 'muted' : 'violet'}>{providerLabel(diagnosis)}</Badge>
          <h2>{diagnosis.headline}</h2>
          <p>{diagnosis.explanation}</p>
          {diagnosis.safe_steps.length > 0 && (
            <ul className="home-steps">
              {diagnosis.safe_steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ul>
          )}
          <h3>What itor can try</h3>
          <ul className="home-fixes">
            {canStopWorkload && (
              <li>
                <span>Stop the background task that is slowing your PC</span>
                <button className="button primary" disabled={stopping} onClick={onStopWorkload}>
                  {stopping ? <Spinner /> : <Wrench size={16} />}
                  Fix it
                </button>
              </li>
            )}
            {(fixes ?? [])
              .filter((fix) => fix.supported)
              .map((fix) => (
                <li key={fix.id}>
                  <span>{fix.title}</span>
                  <button
                    className="button secondary"
                    disabled={Boolean(planning)}
                    onClick={() => onQuickFix(fix)}
                  >
                    {planning === fix.id ? <Spinner /> : <Wrench size={16} />}
                    Fix it
                  </button>
                </li>
              ))}
          </ul>
          {outcome}
          <div className="home-still">
            <p>Still not working?</p>
            <button className="button secondary" onClick={() => onAskIT(diagnosis.headline)}>
              <MessageSquare size={17} />
              Ask IT
            </button>
            <button
              className="text-button"
              onClick={() => {
                setDescribing(false);
                setQuestion('');
                onCheck('');
              }}
            >
              Check again
            </button>
          </div>
        </article>
      )}

      <footer className="home-footer">
        {paidSeconds != null && <span>Today: {duration(paidSeconds)} worked</span>}
        <Link href="/day">See more ›</Link>
        <button className="text-button" onClick={onDemo}>
          <FlaskConical size={14} /> Demo
        </button>
      </footer>
    </div>
  );
}

export function AskIT({
  diagnosis,
  sending,
  error,
  ticket,
  offline,
  onSend,
  onClose,
}: {
  diagnosis?: string;
  sending: boolean;
  error?: string;
  ticket?: Ticket;
  offline: boolean;
  onSend: (message: string) => void;
  onClose: () => void;
}) {
  const [message, setMessage] = useState('');
  if (ticket)
    return (
      <div className="approval-body">
        <div className="section-heading">
          <div className="section-icon violet-icon">
            <Send size={21} />
          </div>
          <div>
            <h3>{ticket.sent ? 'Sent to IT' : 'Saved. It will be sent when you are back online.'}</h3>
            <p>
              {timeLabel(ticket.created_at)} · IT gets your message, what itor measured and what was already tried.
            </p>
          </div>
        </div>
        <div className="button-row dialog-actions">
          <button className="button primary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    );
  return (
    <form
      className="approval-body"
      onSubmit={(event) => {
        event.preventDefault();
        onSend(message);
      }}
    >
      <label className="field-label" htmlFor="it-message">
        Tell IT what is wrong
      </label>
      <textarea
        id="it-message"
        required
        rows={4}
        maxLength={1000}
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        placeholder="For example: since this morning, websites do not load."
      />
      <p className="muted small">
        itor adds automatically: your PC status, the connection checks
        {diagnosis ? `, what it found ("${diagnosis}")` : ''} and the fixes already tried.
        {offline ? ' You are offline: the ticket will leave as soon as the connection is back.' : ''}
      </p>
      {error && <Notice kind="error">{error}</Notice>}
      <div className="button-row dialog-actions">
        <button type="button" className="button secondary" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="button primary" disabled={sending || !message.trim()}>
          {sending ? <Spinner /> : <Send size={17} />}
          Send to IT
        </button>
      </div>
    </form>
  );
}
