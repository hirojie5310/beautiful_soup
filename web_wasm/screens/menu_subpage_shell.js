export function renderMenuSubpageShell({ width = "narrow", content = "", styles = "" }) {
  return `
    <style>
      .menu-subpage.screen { min-height: calc(100vh - 20px); }
      .menu-subpage .frame {
        border: 2px solid rgba(255,255,255,0.45);
        border-radius: 10px;
        background: rgba(16, 24, 56, 0.96);
        padding: 10px;
      }
      .menu-subpage .btn {
        border: 1px solid rgba(255,255,255,0.7);
        border-radius: 8px;
        color: #eef2ff;
        background: linear-gradient(180deg, #4459bf, #20317e);
        padding: 8px 10px;
        cursor: pointer;
      }
      .menu-subpage .btn.active {
        color: #ffe588;
        box-shadow: inset 0 0 0 2px rgba(255,229,136,0.5);
      }
      .menu-subpage .muted { color: #acb6d7; }
      ${styles}
    </style>
    <div class="screen ${width} menu-subpage">
      ${content}
    </div>
  `;
}
