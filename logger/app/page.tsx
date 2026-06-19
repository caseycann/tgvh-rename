"use client";

import { useEffect, useState } from "react";

type RecentTake = {
  id: string;
  Date?: string;
  Location?: string;
  Scene?: string;
  Shot?: string;
  Take?: number;
  "Flagged Take"?: boolean;
  Status?: string;
};

function todayLocal(): string {
  const d = new Date();
  const offset = d.getTimezoneOffset();
  return new Date(d.getTime() - offset * 60000).toISOString().slice(0, 10);
}

export default function Page() {
  const [date, setDate] = useState(todayLocal());
  const [location, setLocation] = useState("");
  const [scene, setScene] = useState("");
  const [shot, setShot] = useState("");
  const [take, setTake] = useState("1");
  const [flaggedTake, setFlaggedTake] = useState(false);
  const [status, setStatus] = useState("");
  const [notes, setNotes] = useState("");
  const [loggedBy, setLoggedBy] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const [recent, setRecent] = useState<RecentTake[]>([]);

  async function loadRecent() {
    try {
      const res = await fetch("/api/recent-takes");
      const data = await res.json();
      if (res.ok) setRecent(data.takes ?? []);
    } catch {
      // best-effort, ignore
    }
  }

  useEffect(() => {
    loadRecent();
  }, []);

  // Auto-suggest next take number when location/scene/shot match the most recent matching entry.
  useEffect(() => {
    if (!location || !scene || !shot) return;
    const match = recent.find(
      (r) => r.Location === location && r.Scene === scene && r.Shot === shot
    );
    if (match && typeof match.Take === "number") {
      setTake(String(match.Take + 1));
    }
  }, [location, scene, shot, recent]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setMessage(null);
    try {
      const res = await fetch("/api/log-take", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          date,
          location,
          scene,
          shot,
          take,
          flaggedTake,
          status: status || undefined,
          notes: notes || undefined,
          loggedBy: loggedBy || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMessage({ text: data.error ?? "Failed to log take", ok: false });
      } else {
        setMessage({ text: `Logged ${location}_${scene}_${shot}_${String(take).padStart(2, "0")}`, ok: true });
        setNotes("");
        setStatus("");
        setFlaggedTake(false);
        setTake(String(Number(take) + 1));
        loadRecent();
      }
    } catch (err) {
      setMessage({ text: String(err), ok: false });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main>
      <h1>Take Logger</h1>
      <p className="subtitle">Log each take straight off the slate.</p>

      <form onSubmit={handleSubmit}>
        <label>
          Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
        </label>

        <label>
          Location
          <input
            type="text"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="Grange"
            required
          />
        </label>

        <div className="row">
          <label>
            Scene
            <input
              type="text"
              value={scene}
              onChange={(e) => setScene(e.target.value)}
              placeholder="23"
              required
            />
          </label>
          <label>
            Shot
            <input
              type="text"
              value={shot}
              onChange={(e) => setShot(e.target.value)}
              placeholder="04"
              required
            />
          </label>
          <label>
            Take
            <input
              type="number"
              min="1"
              value={take}
              onChange={(e) => setTake(e.target.value)}
              required
            />
          </label>
        </div>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={flaggedTake}
            onChange={(e) => setFlaggedTake(e.target.checked)}
          />
          Flagged take (circle this one)
        </label>

        <label>
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">—</option>
            <option value="Good">Good</option>
            <option value="No good">No good</option>
            <option value="Exceptional">Exceptional</option>
          </select>
        </label>

        <label>
          Notes
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            placeholder="Optional — anything from the slate"
          />
        </label>

        <label>
          Logged by
          <input
            type="text"
            value={loggedBy}
            onChange={(e) => setLoggedBy(e.target.value)}
            placeholder="Optional"
          />
        </label>

        <button type="submit" disabled={submitting}>
          {submitting ? "Logging…" : "Log Take"}
        </button>

        {message && (
          <div className={`status ${message.ok ? "ok" : "error"}`}>{message.text}</div>
        )}
      </form>

      <div className="recent">
        <h2>Recently logged</h2>
        <ul>
          {recent.map((r) => (
            <li key={r.id}>
              <span>
                {r.Location}_{r.Scene}_{r.Shot}_{String(r.Take).padStart(2, "0")}
                {r["Flagged Take"] ? <span className="flag"> ★</span> : null}
              </span>
              <span>{r.Status ?? ""}</span>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
