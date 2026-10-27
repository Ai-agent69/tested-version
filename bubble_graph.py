"""
bubble_graph.py
───────────────
Interactive physics-based 'Bubbles connected through Ties and Ropes' visualizer.
Embeds as an interactive HTML5 canvas component in Streamlit.
"""

from __future__ import annotations

import json
from typing import Any


def get_bubble_rope_html(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    """Generates self-contained HTML/JS canvas for floating bubbles connected by elastic ropes."""
    payload = json.dumps({"nodes": nodes, "edges": edges})

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; user-select: none; }}
  body {{
    background: radial-gradient(circle at 50% 40%, #201048 0%, #0e0722 60%, #060310 100%);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #ffffff;
    height: 100vh;
    overflow: hidden;
    position: relative;
  }}
  .toolbar {{
    position: absolute;
    top: 14px;
    left: 16px;
    display: flex;
    gap: 8px;
    z-index: 20;
  }}
  .tool-btn {{
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.2);
    color: #ffffff;
    padding: 6px 14px;
    border-radius: 999px;
    font-size: 12.5px;
    font-weight: 600;
    cursor: pointer;
    backdrop-filter: blur(8px);
    transition: all 0.2s ease;
  }}
  .tool-btn:hover {{
    background: rgba(147, 51, 234, 0.4);
    border-color: rgba(192, 132, 252, 0.6);
    transform: translateY(-1px);
  }}
  .legend {{
    position: absolute;
    bottom: 14px;
    left: 16px;
    display: flex;
    gap: 14px;
    background: rgba(14, 7, 34, 0.75);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 999px;
    padding: 6px 16px;
    font-size: 12px;
    backdrop-filter: blur(8px);
    z-index: 20;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  .legend-dot.semantic {{ background: #38bdf8; box-shadow: 0 0 8px #38bdf8; }}
  .legend-dot.episodic {{ background: #ec4899; box-shadow: 0 0 8px #ec4899; }}
  .legend-dot.procedural {{ background: #fbbf24; box-shadow: 0 0 8px #fbbf24; }}
  .legend-dot.temporary {{ background: #a855f7; box-shadow: 0 0 8px #a855f7; }}

  .detail-sheet {{
    position: absolute;
    top: 14px;
    right: 16px;
    width: 290px;
    background: rgba(22, 11, 48, 0.92);
    border: 1px solid rgba(192, 132, 252, 0.4);
    border-radius: 14px;
    padding: 14px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.6);
    backdrop-filter: blur(12px);
    z-index: 20;
    display: none;
    animation: fadeIn 0.2s ease;
  }}
  @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(-4px); }} to {{ opacity: 1; transform: translateY(0); }} }}
  .detail-sheet h4 {{ font-size: 14px; color: #c084fc; margin-bottom: 6px; }}
  .detail-sheet p {{ font-size: 12.5px; color: #e2e8f0; line-height: 1.45; margin-bottom: 8px; }}
  .detail-meta {{ font-size: 11px; color: #94a3b8; font-family: monospace; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 6px; }}

  canvas {{ display: block; width: 100%; height: 100%; cursor: grab; }}
  canvas:active {{ cursor: grabbing; }}
</style>
</head>
<body>
  <div class="toolbar">
    <button class="tool-btn" onclick="shakeBubbles()">🌪️ Shake</button>
    <button class="tool-btn" onclick="tugRopes()">🪢 Tug Ropes</button>
    <button class="tool-btn" onclick="floatDrift()">🫧 Float Drift</button>
    <button class="tool-btn" onclick="resetView()">🎯 Reset Center</button>
  </div>

  <div class="legend">
    <span class="legend-item"><span class="legend-dot semantic"></span> Semantic</span>
    <span class="legend-item"><span class="legend-dot episodic"></span> Episodic</span>
    <span class="legend-item"><span class="legend-dot procedural"></span> Procedural</span>
    <span class="legend-item"><span class="legend-dot temporary"></span> Temporary</span>
  </div>

  <div class="detail-sheet" id="detailSheet">
    <div style="display:flex; justify-content:space-between; align-items:center;">
      <h4 id="detailType">Bubble Memory</h4>
      <span style="cursor:pointer; color:#94a3b8; font-size:16px;" onclick="document.getElementById('detailSheet').style.display='none'">&times;</span>
    </div>
    <p id="detailContent"></p>
    <div class="detail-meta" id="detailMeta"></div>
  </div>

  <canvas id="bubbleCanvas"></canvas>

  <script>
    const data = {payload};
    const canvas = document.getElementById('bubbleCanvas');
    const ctx = canvas.getContext('2d');

    let width = canvas.width = window.innerWidth;
    let height = canvas.height = window.innerHeight;

    window.addEventListener('resize', () => {{
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    }});

    // Color maps for glossy bubbles
    const BUBBLE_COLORS = {{
      semantic:   {{ top: '#bae6fd', mid: '#38bdf8', bot: '#0369a1', glow: '#38bdf8', emoji: '🧠' }},
      episodic:   {{ top: '#fbcfe8', mid: '#ec4899', bot: '#9d174d', glow: '#ec4899', emoji: '🎬' }},
      procedural: {{ top: '#fef3c7', mid: '#fbbf24', bot: '#b45309', glow: '#fbbf24', emoji: '⚙️' }},
      temporary:  {{ top: '#e9d5ff', mid: '#a855f7', bot: '#6b21a8', glow: '#a855f7', emoji: '⏳' }}
    }};

    // Setup bubble nodes
    const cx = width / 2;
    const cy = height / 2;
    const rawNodes = data.nodes || [];
    const rawEdges = data.edges || [];

    let nodes = rawNodes.map((n, i) => {{
      const angle = (i / Math.max(1, rawNodes.length)) * Math.PI * 2;
      const dist = 110 + (i % 3) * 60;
      const typeKey = (n.type || 'semantic').toLowerCase();
      const style = BUBBLE_COLORS[typeKey] || BUBBLE_COLORS.semantic;
      return {{
        id: String(n.id || i),
        label: n.label || n.content || ('Memory ' + (i + 1)),
        type: typeKey,
        style: style,
        x: cx + Math.cos(angle) * dist + (Math.random() - 0.5) * 40,
        y: cy + Math.sin(angle) * dist + (Math.random() - 0.5) * 40,
        vx: (Math.random() - 0.5) * 0.8,
        vy: (Math.random() - 0.5) * 0.8,
        radius: 38 + (i % 3) * 4,
        phase: Math.random() * Math.PI * 2,
        floatSpeed: 0.02 + Math.random() * 0.015,
        isDragging: false,
        raw: n
      }};
    }});

    // Setup rope edges
    let edges = rawEdges.map(e => ({{
      source: String(e.source),
      target: String(e.target),
      relationship: e.relationship || 'rope_tie',
      restLength: 135
    }}));

    // If no edges, synthesize organic rope ties between nearby bubbles!
    if (edges.length === 0 && nodes.length > 1) {{
      for (let i = 0; i < nodes.length - 1; i++) {{
        edges.push({{
          source: nodes[i].id,
          target: nodes[i + 1].id,
          relationship: 'connected_memory',
          restLength: 130
        }});
      }}
      if (nodes.length > 2) {{
        edges.push({{
          source: nodes[0].id,
          target: nodes[nodes.length - 1].id,
          relationship: 'associative_tie',
          restLength: 145
        }});
      }}
    }}

    let selectedBubble = null;
    let dragBubble = null;
    let dragOffsetX = 0;
    let dragOffsetY = 0;

    // Mouse / Touch handlers
    canvas.addEventListener('mousedown', (e) => {{
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      dragBubble = nodes.find(n => Math.hypot(n.x - mx, n.y - my) <= n.radius + 6);
      if (dragBubble) {{
        dragBubble.isDragging = true;
        dragOffsetX = mx - dragBubble.x;
        dragOffsetY = my - dragBubble.y;
        selectedBubble = dragBubble;
        showDetail(dragBubble);
      }}
    }});

    window.addEventListener('mousemove', (e) => {{
      if (dragBubble) {{
        const rect = canvas.getBoundingClientRect();
        dragBubble.x = e.clientX - rect.left - dragOffsetX;
        dragBubble.y = e.clientY - rect.top - dragOffsetY;
        dragBubble.vx = 0;
        dragBubble.vy = 0;
      }}
    }});

    window.addEventListener('mouseup', () => {{
      if (dragBubble) {{
        dragBubble.isDragging = false;
        dragBubble = null;
      }}
    }});

    function showDetail(b) {{
      const sheet = document.getElementById('detailSheet');
      document.getElementById('detailType').textContent = `${{b.style.emoji}} ${{b.type.toUpperCase()}} BUBBLE`;
      document.getElementById('detailContent').textContent = b.label;
      const connected = edges.filter(e => e.source === b.id || e.target === b.id).length;
      document.getElementById('detailMeta').textContent = `ID: ${{b.id}} | Connected Ropes: ${{connected}} | Radius: ${{b.radius}}px`;
      sheet.style.display = 'block';
    }}

    // Toolbar functions
    window.shakeBubbles = function() {{
      nodes.forEach(n => {{
        n.vx += (Math.random() - 0.5) * 14;
        n.vy += (Math.random() - 0.5) * 14;
      }});
    }};

    window.tugRopes = function() {{
      edges.forEach(e => {{
        const s = nodes.find(n => n.id === e.source);
        const t = nodes.find(n => n.id === e.target);
        if (s && t) {{
          const dx = t.x - s.x;
          const dy = t.y - s.y;
          s.vx += dx * 0.08;
          s.vy += dy * 0.08;
          t.vx -= dx * 0.08;
          t.vy -= dy * 0.08;
        }}
      }});
    }};

    let floatActive = true;
    window.floatDrift = function() {{
      floatActive = !floatActive;
    }};

    window.resetView = function() {{
      nodes.forEach((n, i) => {{
        const angle = (i / Math.max(1, nodes.length)) * Math.PI * 2;
        n.x = width / 2 + Math.cos(angle) * 130;
        n.y = height / 2 + Math.sin(angle) * 130;
        n.vx = 0; n.vy = 0;
      }});
    }};

    // Main Physics & Render Animation Loop
    let time = 0;
    function animate() {{
      time += 0.02;
      ctx.clearRect(0, 0, width, height);

      // 1. Spring physics for ropes
      for (const edge of edges) {{
        const s = nodes.find(n => n.id === edge.source);
        const t = nodes.find(n => n.id === edge.target);
        if (!s || !t) continue;

        const dx = t.x - s.x;
        const dy = t.y - s.y;
        const dist = Math.hypot(dx, dy) || 1;
        const diff = dist - edge.restLength;
        const force = diff * 0.022; // spring constant

        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        if (!s.isDragging) {{ s.vx += fx; s.vy += fy; }}
        if (!t.isDragging) {{ t.vx -= fx; t.vy -= fy; }}
      }}

      // 2. Bubble-to-bubble collision bounce
      for (let i = 0; i < nodes.length; i++) {{
        for (let j = i + 1; j < nodes.length; j++) {{
          const a = nodes[i];
          const b = nodes[j];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.hypot(dx, dy) || 1;
          const minDist = a.radius + b.radius + 12;

          if (dist < minDist) {{
            const overlap = (minDist - dist) * 0.5;
            const nx = dx / dist;
            const ny = dy / dist;

            if (!a.isDragging) {{ a.x -= nx * overlap; a.y -= ny * overlap; a.vx -= nx * 0.5; a.vy -= ny * 0.5; }}
            if (!b.isDragging) {{ b.x += nx * overlap; b.y += ny * overlap; b.vx += nx * 0.5; b.vy += ny * 0.5; }}
          }}
        }}
      }}

      // 3. Update position and float motion
      for (const node of nodes) {{
        if (!node.isDragging) {{
          if (floatActive) {{
            node.vy += Math.sin(time + node.phase) * 0.12;
            node.vx += Math.cos(time + node.phase) * 0.08;
          }}

          node.x += node.vx;
          node.y += node.vy;
          node.vx *= 0.92;
          node.vy *= 0.92;

          // Boundary bounce
          const pad = node.radius + 10;
          if (node.x < pad) {{ node.x = pad; node.vx *= -0.7; }}
          if (node.x > width - pad) {{ node.x = width - pad; node.vx *= -0.7; }}
          if (node.y < pad) {{ node.y = pad; node.vy *= -0.7; }}
          if (node.y > height - pad) {{ node.y = height - pad; node.vy *= -0.7; }}
        }}
      }}

      // 4. Draw Ropes (Ties)
      for (const edge of edges) {{
        const s = nodes.find(n => n.id === edge.source);
        const t = nodes.find(n => n.id === edge.target);
        if (!s || !t) continue;

        const dx = t.x - s.x;
        const dy = t.y - s.y;
        const dist = Math.hypot(dx, dy);

        // Rope catenary sag calculation
        const midX = (s.x + t.x) / 2;
        const midY = (s.y + t.y) / 2;
        const sag = Math.max(0, 22 - (dist / edge.restLength) * 16);
        const ctrlX = midX;
        const ctrlY = midY + sag;

        // Base rope shadow
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.quadraticCurveTo(ctrlX, ctrlY, t.x, t.y);
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.4)';
        ctx.lineWidth = 5;
        ctx.stroke();

        // Braided Rope cord
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.quadraticCurveTo(ctrlX, ctrlY, t.x, t.y);
        ctx.strokeStyle = '#d4a373'; // warm golden rope twine
        ctx.lineWidth = 3.5;
        ctx.stroke();

        // Braided Rope highlights (dashed line)
        ctx.beginPath();
        ctx.setLineDash([4, 4]);
        ctx.moveTo(s.x, s.y);
        ctx.quadraticCurveTo(ctrlX, ctrlY, t.x, t.y);
        ctx.strokeStyle = '#fae1c7';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.setLineDash([]); // reset

        // Tied Knot rings at each bubble perimeter
        const angleS = Math.atan2(ctrlY - s.y, ctrlX - s.x);
        const knotSx = s.x + Math.cos(angleS) * s.radius;
        const knotSy = s.y + Math.sin(angleS) * s.radius;
        ctx.beginPath();
        ctx.arc(knotSx, knotSy, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#b45309';
        ctx.fill();
        ctx.strokeStyle = '#fde68a';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        const angleT = Math.atan2(ctrlY - t.y, ctrlX - t.x);
        const knotTx = t.x + Math.cos(angleT) * t.radius;
        const knotTy = t.y + Math.sin(angleT) * t.radius;
        ctx.beginPath();
        ctx.arc(knotTx, knotTy, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#b45309';
        ctx.fill();
        ctx.strokeStyle = '#fde68a';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Relationship label pill
        if (edge.relationship && edge.relationship !== 'rope_tie') {{
          ctx.font = '10.5px sans-serif';
          const textW = ctx.measureText(edge.relationship).width;
          ctx.fillStyle = 'rgba(26, 14, 56, 0.85)';
          ctx.fillRect(ctrlX - textW / 2 - 6, ctrlY - 8, textW + 12, 16);
          ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
          ctx.strokeRect(ctrlX - textW / 2 - 6, ctrlY - 8, textW + 12, 16);
          ctx.fillStyle = '#e2e8f0';
          ctx.textAlign = 'center';
          ctx.fillText(edge.relationship, ctrlX, ctrlY + 4);
        }}
      }}

      // 5. Draw Glossy 3D Bubbles
      for (const node of nodes) {{
        const isSelected = selectedBubble && selectedBubble.id === node.id;
        const r = node.radius;

        // Outer soft glow aura
        ctx.beginPath();
        ctx.arc(node.x, node.y, r + (isSelected ? 14 : 8), 0, Math.PI * 2);
        ctx.fillStyle = isSelected ? 'rgba(255, 255, 255, 0.4)' : `${{node.style.glow}}28`;
        ctx.fill();

        // 3D Spherical Radial Gradient Body
        const grad = ctx.createRadialGradient(
          node.x - r * 0.35, node.y - r * 0.35, r * 0.1,
          node.x, node.y, r
        );
        grad.addColorStop(0, '#ffffff');
        grad.addColorStop(0.25, node.style.top);
        grad.addColorStop(0.65, node.style.mid);
        grad.addColorStop(1, node.style.bot);

        ctx.beginPath();
        ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();

        // Rim highlight
        ctx.strokeStyle = isSelected ? '#ffffff' : 'rgba(255, 255, 255, 0.7)';
        ctx.lineWidth = isSelected ? 3 : 1.8;
        ctx.stroke();

        // Specular reflection highlight oval (looks like shiny glass bubble reflection)
        ctx.beginPath();
        ctx.ellipse(node.x - r * 0.35, node.y - r * 0.38, r * 0.28, r * 0.14, -Math.PI / 4, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255, 255, 255, 0.75)';
        ctx.fill();

        // Second subtle rim light at bottom right
        ctx.beginPath();
        ctx.ellipse(node.x + r * 0.32, node.y + r * 0.32, r * 0.22, r * 0.09, -Math.PI / 4, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255, 255, 255, 0.28)';
        ctx.fill();

        // Emoji & Label inside bubble
        ctx.font = '16px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(node.style.emoji, node.x, node.y - 4);

        ctx.font = 'bold 11px sans-serif';
        ctx.fillStyle = '#ffffff';
        ctx.shadowColor = 'rgba(0, 0, 0, 0.8)';
        ctx.shadowBlur = 4;
        const shortLabel = node.label.length > 14 ? node.label.slice(0, 12) + '..' : node.label;
        ctx.fillText(shortLabel, node.x, node.y + 13);
        ctx.shadowBlur = 0; // reset
      }}

      requestAnimationFrame(animate);
    }}

    animate();
  </script>
</body>
</html>"""
