conda activate game-env
pip install -r requirements.txt
python app\_pygame.py

## Render deployment
- `requirements.txt` is placed at the repository root (`beautiful_soup/requirements.txt`).
- This repository includes `render.yaml` with:
  - `rootDir: .`
  - `buildCommand: pip install -r /opt/render/project/src/requirements.txt`
  - `startCommand: gunicorn --chdir /opt/render/project/src adapters.flask_app:app`

If you created the Render Web Service manually (not Blueprint), set the same commands in
Render dashboard:
- Build Command: `pip install -r /opt/render/project/src/requirements.txt`
- Start Command: `gunicorn --chdir /opt/render/project/src adapters.flask_app:app`

`/opt/render/project/src` is Render's repository root path, so these commands still work
when Render's working directory differs from the repo root.


## main へ確実に反映する Git 手順（PowerShell）

`work` ブランチが存在しない環境でも使えるように、`main` へ直接反映する最短手順です。

1. 最新の `main` を取得
   - `git checkout main`
   - `git pull origin main`
2. `requirements.txt` が `main` にあるか確認（`rg` 不要）
   - `git ls-tree -r --name-only HEAD | findstr /R "^requirements\.txt$"`
3. 変更をコミット
   - `git add requirements.txt render.yaml README.md`
   - `git commit -m "Add Render deployment files and docs"`
4. `main` へ push
   - `git push origin main`
5. push されたコミットに `requirements.txt` が含まれるか再確認
   - `git fetch origin`
   - `git ls-tree -r --name-only origin/main | findstr /R "^requirements\.txt$"`
6. Render 側で確認
   - Deploy ログの `Checking out commit <hash> in branch main` の `<hash>` が、
     手順 4 で push したコミットと一致することを確認

`work` ブランチを使う場合は、先に `git branch --list work` で存在確認し、
存在しない場合は `git switch -c work` で作成してから作業してください。

## Browser-only battle execution (Pyodide / Wasm)

Flask の `/battle/round` で行っている「JSON を受け取り、1 ラウンドを計算し、ログと結果を返す」処理は、
`combat.wasm_api.WasmBattleEngine` に切り出したことで、Pyodide 上でも同じ DTO 契約のまま再利用できます。

### どのファイルを設け、どこを起点に実行するか

Flask 版の `flask_app.py` に相当する Wasm 版の起点は、次の 4 ファイル構成です。

- `combat/wasm_api.py`
  - Flask の `/battle/round` と同じ戦闘 DTO 契約を Wasm 側へ公開する Python エントリ。
- `scripts/build_wasm_bundle.py`
  - `combat/`, `assets/data/`, `system/`, `utils/` を `web_wasm/python_bundle.zip` に固めるビルド用スクリプト。
- `wasm_app.py`
  - Flask サーバーの代わりに、`web_wasm/` をブラウザで確認するための静的サーバー起点。
- `web_wasm/index.html` + `web_wasm/main.js`
  - ブラウザ側の起点。Pyodide を起動し、`typing-extensions` を `loadPackage()` で読み込んだうえで `python_bundle.zip` を展開し、`WasmBattleEngine` を呼び出します。

ローカル開発時は、次の順で起動すると Flask 版に近い流れを確認しやすいです。

1. `python scripts/build_wasm_bundle.py`
2. `python wasm_app.py`
3. ブラウザで `http://127.0.0.1:8000/web_wasm/` を開く

この構成では、`wasm_app.py` はあくまで静的ファイル配信用であり、戦闘計算そのものはブラウザ内の Pyodide 上で完結します。

### Python side

```python
from combat.wasm_api import WasmBattleEngine

engine = WasmBattleEngine.create_default(seed=7)

initial_payload = engine.build_initial_payload()
result_json = engine.execute_round_json(
    '{"planned_actions": [], "lifecycle_state": "ready_for_actions"}'
)
```

### Browser side (example)

```javascript
import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";

const pyodide = await loadPyodide();
await pyodide.loadPackage("typing-extensions");
await pyodide.runPythonAsync(`
from combat.wasm_api import WasmBattleEngine
engine = WasmBattleEngine.create_default(seed=7)

def run_battle_round_wasm(js_input_json):
    return engine.execute_round_json(js_input_json)
`);

const runRound = pyodide.globals.get("run_battle_round_wasm");
const resultJson = runRound(JSON.stringify({
  planned_actions: [],
  lifecycle_state: "ready_for_actions",
}));
const result = JSON.parse(resultJson);
console.log(result.logs);
console.log(result.session_status);
```

### Design notes

- 入力は Flask 版と同じ `planned_actions` / `lifecycle_state` の JSON を使います。
- 出力も Flask 版と同じ `logs` / `lifecycle` / `session_status` を返すため、HTTP を外しても UI 側の契約を維持できます。
- 戦闘セッションは Wasm 内の Python メモリに保持されるため、Render のようなサーバーを介さずにラウンド実行を継続できます。
combat/w