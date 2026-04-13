conda activate game-env
pip install -r requirements.txt
python app\_pygame.py

## Wasm (Web Assembly) 版のビルド方法
    "combat",
    "assets/data",
    "system",
    "utils",
フォルダ内のファイルは scripts/build_wasm_bundle.py によりZIP圧縮するため、変更があればターミナルに以下のコマンドを入力
(base) PS D:\Python\beautiful_soup> cd scripts
(base) PS D:\Python\beautiful_soup\scripts> python build_wasm_bundle.py
Wrote Wasm bundle: D:\Python\beautiful_soup\web_wasm\python_bundle.zip
(base) PS D:\Python\beautiful_soup\scripts> cd ..    
(base) PS D:\Python\beautiful_soup> python wasm_app.py
Wasm static server: http://127.0.0.1:8000/web_wasm/

## 継続して情報を保持するための方針（wasm_app.py 起点の画面横断）

単一の状態オブジェクトを source of truth にする
ff3_wasm_menu_state_v1 に全画面共通で使うデータを保持し、各画面は「自分の担当フィールドだけ更新」し、未知フィールドは必ず温存（merge）してください。今回の修正はこの原則に合わせています。.

部分更新時に overwrite しない
localStorage.setItem 前に既存 state を展開し、差分だけ上書きする（{ ...existing, changedField: ... }）運用に統一すると、今回のような画面間データ消失を防げます。.

保存エンベロープにも menu_state を同梱
セーブファイルに menu_state を含めることで、ロード復元時に UI 側の詳細状態（魔法セット候補など）も戻せます。.


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
- `web_wasm/index.html` + `web_wasm/app.js` + `web_wasm/pyodide_runtime.js`
  - ブラウザ側の起点。SPA ルータを起動し、`pyodide_runtime.js` 経由で Pyodide を 1 回だけ初期化し、`typing-extensions` と `jsonschema` を `loadPackage()` で読み込んだうえで `python_bundle.zip` を展開し、`WasmBattleEngine` を呼び出します。
- `web_wasm/ARCHITECTURE.md`
  - SPA 化後の `web_wasm` 構成と責務分担の簡易メモ。
- `web_wasm/REGRESSION_CHECKLIST.md`
  - 主要画面を手動確認するときの簡易回帰チェックリスト。

ローカル開発時は、次の順で起動すると Flask 版に近い流れを確認しやすいです。

1. `python scripts/build_wasm_bundle.py`
2. `python wasm_app.py`
3. ブラウザで `http://127.0.0.1:8000/web_wasm/` を開く

この構成では、`wasm_app.py` はあくまで静的ファイル配信用であり、戦闘計算そのものはブラウザ内の Pyodide 上で完結します。

### Save data / Slot design

- 保存形式は `version: 1` の envelope と `save` 本体に分離しています。
- `save.schema_version` はゲームデータの版です。Wasm 側の現在 schema は `2` です。
- `schema_version: 2` では、各 party member に以下の追加項目を持てます。
  - `current_job`
  - `mp_levels`
- `schema_version: 1` の旧 save は `web_wasm/bootstrap_runtime.py` の `migrate_save()` で v2 へ引き上げます。
- ブラウザ保存は `IndexedDB` のスロット管理を使います。
  - `AUTO SAVE`: 戦闘終了時に更新
  - `Slot 1` - `Slot 3`: 手動保存用
- 最後に使った手動スロットはブラウザ側で記憶し、メニュー画面で強調表示します。

### JSON Schema / Validation

- スキーマ定義は [schemas/ff3-save-envelope.schema.json](/Users/hirotaka/beautiful_soup/schemas/ff3-save-envelope.schema.json) にあります。
- `assets/data/data_loader.py` では `jsonschema` を使って次を検証します。
  - `validate_save_data(...)`
  - `validate_save_envelope(...)`
- `save_savedata(...)` は保存前に validation を行います。
- `load_savedata(...)` はロード後の save 本体を validation します。
- Wasm bundle にも `schemas/` を同梱するため、Pyodide 側でも同じスキーマを参照できます。

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
await pyodide.loadPackage("jsonschema");
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
