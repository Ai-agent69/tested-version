"""Standalone 3D Cybernetic Point Cloud AI Model component for Streamlit.
Renders the real 3D WebGL undulating particle blob with electric cyan-to-lavender
gradients on pure obsidian black space.
"""
from __future__ import annotations
from pathlib import Path
import functools

@functools.lru_cache(maxsize=1)
def _get_three_js() -> str:
    path = Path("static/three.min.js")
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""

@functools.lru_cache(maxsize=1)
def _get_orb_js() -> str:
    path = Path("static/alexa_orb.js")
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""

def get_alexa_orb_html(initial_state: str = "idle") -> str:
    """Generate self-contained HTML for the pure 3D Point Cloud AI Model widget."""
    three_code = _get_three_js()
    orb_code = _get_orb_js()

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body, html {{
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: #000000;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }}
  #orbStage {{
    position: relative;
    width: 320px;
    height: 320px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #000000;
  }}
  #orb3DContainer {{
    width: 100%;
    height: 100%;
    position: relative;
    cursor: pointer;
  }}
  #orb3DContainer canvas {{
    width: 100% !important;
    height: 100% !important;
    display: block;
  }}
</style>
</head>
<body>
  <div id="orbStage">
    <div id="orb3DContainer" title="Click to interact with 3D Particle AI Model"></div>
  </div>

  <script>
    {three_code}
  </script>
  <script>
    {orb_code}
  </script>
  <script>
    let orbInstance = null;
    window.addEventListener('DOMContentLoaded', () => {{
      orbInstance = new AlexaOrb3D({{ containerId: 'orb3DContainer' }});
      if (orbInstance) {{
        orbInstance.setState('{initial_state}');
      }}
    }});
  </script>
</body>
</html>
"""
