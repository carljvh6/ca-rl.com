"""HTML renderer for interactive lap replay widgets."""

from __future__ import annotations

import json
from html import escape
from uuid import uuid4


def render_lap_replay_widget(payload: dict) -> str:
    """Render an SVG-based lap replay widget driven by browser-side animation."""
    widget_id = f"lap-replay-{uuid4().hex}"
    title = escape(str(payload.get("title") or "Lap Replay"))
    subtitle = escape(str(payload.get("subtitle") or ""))
    circuit = payload.get("circuit", {})
    view_box = circuit.get("view_box", [0, 0, 1000, 1000])
    path_points = circuit.get("path", [])
    path_d = _path_d(path_points)
    corners = circuit.get("corners", [])
    drivers = payload.get("drivers", {})
    driver_codes = list(drivers.keys())
    if len(driver_codes) < 2:
        return "<p>Error: replay payload is missing one or both drivers.</p>"
    driver1 = drivers[driver_codes[0]]
    driver2 = drivers[driver_codes[1]]
    payload_json = escape(json.dumps(payload, separators=(",", ":")))

    def card(driver: dict) -> str:
        code = escape(str(driver.get("driver_code") or "DRV"))
        label = escape(str(driver.get("selector_label") or "Selected lap"))
        segment = escape(str(driver.get("segment") or ""))
        accent = escape(str(driver.get("color") or "#ffffff"))
        lap_no = escape(str(driver.get("lap_number") or "—"))
        lap_time = escape(_format_lap_time(driver.get("lap_time_seconds")))
        segment_html = f"<span class='lap-replay-meta-chip'>{segment}</span>" if segment else ""
        return f"""
        <div class="lap-replay-card" data-driver="{code}" style="--lap-accent:{accent}">
            <div class="lap-replay-card-head">
                <div>
                    <div class="lap-replay-code">{code}</div>
                    <div class="lap-replay-label">{label}</div>
                </div>
                <div class="lap-replay-meta">
                    <span class="lap-replay-meta-chip">Lap {lap_no}</span>
                    {segment_html}
                    <span class="lap-replay-meta-chip">{lap_time}</span>
                </div>
            </div>
            <div class="lap-replay-stats">
                <div><span>Speed</span><strong data-field="speed">0</strong><small>km/h</small></div>
                <div><span>Throttle</span><strong data-field="throttle">0</strong><small>%</small></div>
                <div><span>Brake</span><strong data-field="brake">0</strong><small>%</small></div>
                <div><span>Gear</span><strong data-field="gear">0</strong><small>gear</small></div>
            </div>
        </div>
        """

    corner_html = "".join(
        f"""
        <g class="lap-replay-corner">
            <circle cx="{corner['x']}" cy="{corner['y']}" r="10"></circle>
            <text x="{corner['x'] + 16}" y="{corner['y'] - 12}">{escape(str(corner['label']))}</text>
        </g>
        """
        for corner in corners
    )

    return f"""
    <div id="{widget_id}" class="lap-replay-widget">
        <style>
            #{widget_id} {{
                --panel:#0f172a;
                --panel-2:#111827;
                --ink:#e5eefb;
                --muted:#8ea0b8;
                --track:#d9e3f0;
                --track-shadow:rgba(30,41,59,0.55);
                background:
                    radial-gradient(circle at top left, rgba(78,161,255,0.10), transparent 34%),
                    radial-gradient(circle at top right, rgba(255,107,87,0.10), transparent 30%),
                    linear-gradient(180deg, #08111f, #0f172a 55%, #111827);
                border:1px solid rgba(148,163,184,0.18);
                border-radius:24px;
                padding:20px;
                color:var(--ink);
                box-shadow:0 30px 80px rgba(2,6,23,0.45);
            }}
            #{widget_id} .lap-replay-head {{
                display:flex;
                justify-content:space-between;
                gap:16px;
                flex-wrap:wrap;
                margin-bottom:16px;
            }}
            #{widget_id} .lap-replay-title {{ font-size:1.35rem; font-weight:700; margin:0; }}
            #{widget_id} .lap-replay-subtitle {{ margin:6px 0 0; color:var(--muted); font-size:0.95rem; }}
            #{widget_id} .lap-replay-controls {{
                display:flex;
                flex-wrap:wrap;
                gap:12px;
                align-items:center;
                margin-bottom:16px;
            }}
            #{widget_id} .lap-replay-btn,
            #{widget_id} .lap-replay-mode button {{
                background:rgba(15,23,42,0.9);
                color:var(--ink);
                border:1px solid rgba(148,163,184,0.22);
                border-radius:999px;
                padding:10px 14px;
                font:inherit;
                cursor:pointer;
            }}
            #{widget_id} .lap-replay-mode {{
                display:inline-flex;
                padding:4px;
                border-radius:999px;
                background:rgba(15,23,42,0.8);
                border:1px solid rgba(148,163,184,0.18);
            }}
            #{widget_id} .lap-replay-mode button.active {{ background:#f8fafc; color:#0f172a; }}
            #{widget_id} .lap-replay-slider {{ flex:1 1 280px; accent-color:#f8fafc; }}
            #{widget_id} .lap-replay-timing {{ min-width:90px; text-align:right; color:var(--muted); font-variant-numeric:tabular-nums; }}
            #{widget_id} .lap-replay-stage {{ display:grid; grid-template-columns:minmax(0, 1.5fr) minmax(280px, 0.9fr); gap:16px; }}
            #{widget_id} .lap-replay-map,
            #{widget_id} .lap-replay-side {{ background:rgba(15,23,42,0.62); border:1px solid rgba(148,163,184,0.18); border-radius:20px; }}
            #{widget_id} .lap-replay-map {{ padding:16px; min-height:460px; overflow:hidden; }}
            #{widget_id} svg {{ width:100%; height:100%; min-height:420px; display:block; }}
            #{widget_id} .lap-replay-track-bg {{ fill:none; stroke:var(--track-shadow); stroke-width:42; stroke-linecap:round; stroke-linejoin:round; }}
            #{widget_id} .lap-replay-track {{ fill:none; stroke:var(--track); stroke-width:28; stroke-linecap:round; stroke-linejoin:round; opacity:0.96; }}
            #{widget_id} .lap-replay-corner circle {{ fill:#0f172a; stroke:rgba(248,250,252,0.28); }}
            #{widget_id} .lap-replay-corner text {{ fill:#b7c5d9; font-size:26px; font-weight:600; paint-order:stroke; stroke:#08111f; stroke-width:6px; }}
            #{widget_id} .lap-replay-dot {{ stroke:#eff6ff; stroke-width:8; filter:drop-shadow(0 0 18px rgba(255,255,255,0.26)); }}
            #{widget_id} .lap-replay-side {{ padding:14px; display:grid; gap:12px; align-content:start; }}
            #{widget_id} .lap-replay-status {{ display:flex; justify-content:space-between; gap:12px; background:rgba(8,17,31,0.7); border-radius:16px; padding:12px 14px; color:var(--muted); }}
            #{widget_id} .lap-replay-status strong {{ display:block; color:var(--ink); font-size:1rem; margin-top:3px; }}
            #{widget_id} .lap-replay-card {{ border-radius:18px; background:linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); border:1px solid rgba(148,163,184,0.18); padding:14px; }}
            #{widget_id} .lap-replay-card-head {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:12px; }}
            #{widget_id} .lap-replay-code {{ font-size:1.1rem; font-weight:800; letter-spacing:0.04em; color:var(--lap-accent); }}
            #{widget_id} .lap-replay-label {{ color:var(--muted); font-size:0.88rem; margin-top:2px; }}
            #{widget_id} .lap-replay-meta {{ display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }}
            #{widget_id} .lap-replay-meta-chip {{ background:rgba(148,163,184,0.12); border:1px solid rgba(148,163,184,0.18); border-radius:999px; color:#d8e1ee; padding:4px 8px; font-size:0.78rem; }}
            #{widget_id} .lap-replay-stats {{ display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:10px; }}
            #{widget_id} .lap-replay-stats div {{ background:rgba(8,17,31,0.68); border-radius:14px; padding:10px 12px; }}
            #{widget_id} .lap-replay-stats span,
            #{widget_id} .lap-replay-stats small {{ display:block; color:var(--muted); font-size:0.78rem; }}
            #{widget_id} .lap-replay-stats strong {{ display:block; font-size:1.4rem; margin:4px 0 2px; font-variant-numeric:tabular-nums; }}
            @media (max-width: 980px) {{
                #{widget_id} .lap-replay-stage {{ grid-template-columns:1fr; }}
                #{widget_id} .lap-replay-map {{ min-height:360px; }}
            }}
        </style>

        <div class="lap-replay-head">
            <div>
                <h3 class="lap-replay-title">{title}</h3>
                <p class="lap-replay-subtitle">{subtitle}</p>
            </div>
        </div>

        <div class="lap-replay-controls">
            <button type="button" class="lap-replay-btn" data-role="play-toggle">Pause</button>
            <div class="lap-replay-mode" data-role="mode-toggle">
                <button type="button" data-mode="real_time" class="active">Real-time</button>
                <button type="button" data-mode="equal_progress">Equal-progress</button>
            </div>
            <input type="range" min="0" max="1" step="0.001" value="0" class="lap-replay-slider" data-role="scrubber" />
            <div class="lap-replay-timing" data-role="timing">0:00.000</div>
        </div>

        <div class="lap-replay-stage">
            <div class="lap-replay-map">
                <svg viewBox="{view_box[0]} {view_box[1]} {view_box[2]} {view_box[3]}" preserveAspectRatio="xMidYMid meet" aria-label="Lap replay circuit">
                    <path class="lap-replay-track-bg" d="{path_d}"></path>
                    <path class="lap-replay-track" d="{path_d}"></path>
                    {corner_html}
                    <circle class="lap-replay-dot" data-dot="{escape(driver_codes[0])}" cx="{path_points[0]['x'] if path_points else 0}" cy="{path_points[0]['y'] if path_points else 0}" r="18" fill="{escape(str(driver1.get('color') or '#ff6b57'))}"></circle>
                    <circle class="lap-replay-dot" data-dot="{escape(driver_codes[1])}" cx="{path_points[0]['x'] if path_points else 0}" cy="{path_points[0]['y'] if path_points else 0}" r="18" fill="{escape(str(driver2.get('color') or '#4ea1ff'))}"></circle>
                </svg>
            </div>
            <div class="lap-replay-side">
                <div class="lap-replay-status">
                    <div>Corner<strong data-role="corner-label">-</strong></div>
                    <div>Delta<strong data-role="delta-label">-</strong></div>
                </div>
                {card(driver1)}
                {card(driver2)}
            </div>
        </div>

        <script type="application/json" id="{widget_id}-data">{payload_json}</script>
        <script>
            (() => {{
                const root = document.getElementById({json.dumps(widget_id)});
                const payload = JSON.parse(document.getElementById({json.dumps(widget_id + "-data")}).textContent);
                const dots = new Map(Array.from(root.querySelectorAll('[data-dot]')).map((el) => [el.dataset.dot, el]));
                const cards = new Map(Array.from(root.querySelectorAll('.lap-replay-card')).map((el) => [el.dataset.driver, el]));
                const playButton = root.querySelector('[data-role="play-toggle"]');
                const scrubber = root.querySelector('[data-role="scrubber"]');
                const timing = root.querySelector('[data-role="timing"]');
                const cornerLabel = root.querySelector('[data-role="corner-label"]');
                const deltaLabel = root.querySelector('[data-role="delta-label"]');
                const modeButtons = Array.from(root.querySelectorAll('[data-role="mode-toggle"] [data-mode]'));
                const primaryDriver = {json.dumps(driver_codes[0])};
                const secondaryDriver = {json.dumps(driver_codes[1])};
                const state = {{ mode: payload.mode_default || 'real_time', playing: true, currentTime: 0, raf: null, lastStamp: null }};
                const modeData = () => payload.modes[state.mode] || {{ duration_seconds: 1, samples: [] }};
                const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
                const formatTime = (seconds) => {{
                    const value = Number(seconds || 0);
                    const mins = Math.floor(value / 60);
                    const secs = value - mins * 60;
                    return `${{mins}}:${{secs.toFixed(3).padStart(6, '0')}}`;
                }};
                const findSample = (time) => {{
                    const samples = modeData().samples || [];
                    if (!samples.length) return null;
                    const duration = Math.max(Number(modeData().duration_seconds || 1), 0.001);
                    const ratio = clamp(time / duration, 0, 1);
                    return samples[Math.min(samples.length - 1, Math.round(ratio * (samples.length - 1)))];
                }};
                const renderDriver = (driverCode, sampleData) => {{
                    const dot = dots.get(driverCode);
                    const card = cards.get(driverCode);
                    if (!sampleData) return;
                    if (dot) {{
                        dot.setAttribute('cx', sampleData.x);
                        dot.setAttribute('cy', sampleData.y);
                    }}
                    if (card) {{
                        for (const field of ['speed', 'throttle', 'brake', 'gear']) {{
                            const el = card.querySelector(`[data-field="${{field}}"]`);
                            if (el) el.textContent = sampleData[field] ?? 0;
                        }}
                    }}
                }};
                const render = () => {{
                    const sample = findSample(state.currentTime);
                    if (!sample) return;
                    for (const [driverCode, sampleData] of Object.entries(sample.cars || {{}})) {{
                        renderDriver(driverCode, sampleData);
                    }}
                    const duration = Math.max(Number(modeData().duration_seconds || 1), 0.001);
                    scrubber.max = String(duration);
                    scrubber.value = String(clamp(state.currentTime, 0, duration));
                    timing.textContent = formatTime(state.mode === 'equal_progress' ? Math.max(...Object.values(sample.cars || {{}}).map((car) => Number(car.time_seconds || 0)), 0) : state.currentTime);
                    cornerLabel.textContent = sample.corner_label || '-';
                    if (state.mode === 'equal_progress' && typeof sample.delta_seconds === 'number') {{
                        const delta = sample.delta_seconds;
                        if (Math.abs(delta) < 0.001) {{
                            deltaLabel.textContent = 'Level';
                        }} else {{
                            deltaLabel.textContent = `${{delta < 0 ? primaryDriver : secondaryDriver}} +${{Math.abs(delta).toFixed(3)}}s`;
                        }}
                    }} else if (typeof sample.delta_progress === 'number') {{
                        const delta = sample.delta_progress;
                        if (Math.abs(delta) < 0.0005) {{
                            deltaLabel.textContent = 'Side by side';
                        }} else {{
                            deltaLabel.textContent = `${{delta > 0 ? primaryDriver : secondaryDriver}} +${{(Math.abs(delta) * 100).toFixed(1)}}% lap`;
                        }}
                    }} else {{
                        deltaLabel.textContent = '-';
                    }}
                }};
                const tick = (stamp) => {{
                    if (!state.playing) return;
                    if (state.lastStamp == null) state.lastStamp = stamp;
                    const elapsed = (stamp - state.lastStamp) / 1000;
                    state.lastStamp = stamp;
                    const duration = Math.max(Number(modeData().duration_seconds || 1), 0.001);
                    state.currentTime = clamp(state.currentTime + elapsed, 0, duration);
                    if (state.currentTime >= duration) {{
                        state.currentTime = duration;
                        state.playing = false;
                        playButton.textContent = 'Play';
                    }} else {{
                        state.raf = requestAnimationFrame(tick);
                    }}
                    render();
                }};
                const start = () => {{
                    cancelAnimationFrame(state.raf);
                    state.playing = true;
                    state.lastStamp = null;
                    playButton.textContent = 'Pause';
                    state.raf = requestAnimationFrame(tick);
                }};
                const stop = () => {{
                    state.playing = false;
                    playButton.textContent = 'Play';
                    cancelAnimationFrame(state.raf);
                    state.raf = null;
                }};
                playButton.addEventListener('click', () => {{
                    if (state.playing) {{
                        stop();
                    }} else {{
                        if (state.currentTime >= Number(modeData().duration_seconds || 1)) state.currentTime = 0;
                        start();
                    }}
                }});
                scrubber.addEventListener('input', () => {{
                    state.currentTime = Number(scrubber.value || 0);
                    render();
                }});
                modeButtons.forEach((button) => {{
                    button.addEventListener('click', () => {{
                        const previous = modeData();
                        const ratio = previous.duration_seconds ? state.currentTime / previous.duration_seconds : 0;
                        state.mode = button.dataset.mode;
                        modeButtons.forEach((el) => el.classList.toggle('active', el === button));
                        const next = modeData();
                        state.currentTime = clamp(ratio * Number(next.duration_seconds || 1), 0, Number(next.duration_seconds || 1));
                        render();
                    }});
                }});
                render();
                start();
            }})();
        </script>
    </div>
    """


def _path_d(points: list[dict]) -> str:
    if not points:
        return ""
    segments = [f"M {points[0]['x']} {points[0]['y']}"]
    for point in points[1:]:
        segments.append(f"L {point['x']} {point['y']}")
    return " ".join(segments)


def _format_lap_time(value: object) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return "—"
    mins = int(seconds // 60)
    secs = seconds - mins * 60
    return f"{mins}:{secs:06.3f}"
