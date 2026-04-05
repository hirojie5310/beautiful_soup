# web_wasm SPA 構成メモ

`web_wasm` は現在、`index.html` を起点にした単一ページアプリとして動作します。
以前の `menu.html` や `battle.html` などは、古いブックマークやリンクを壊さないための SPA ルート向けリダイレクトだけを担当します。

## エントリポイント

- `index.html`
  - 最小限の SPA シェルです。
- `app.js`
  - store と router を組み立てて、アプリ全体を起動します。
- `router.js`
  - `#/location` `#/menu` `#/battle` などのハッシュルートを解決します。
  - 画面モジュールを遅延読み込みし、ルート切替時に前の画面をクリーンアップします。

## 共通ランタイムと状態

- `pyodide_runtime.js`
  - Pyodide の共有インスタンスを 1 つだけ管理します。
  - 画面や battle ロジックは、直接 Pyodide を初期化せず `getPyodideRuntime()` を使います。
- `store/app_store.js`
  - 現在ルート、選択中 Location、選択中メンバー、`menu_state`、save envelope を持つアプリ内の状態管理です。
  - 必要な変更をブラウザストレージへ永続化します。
- `shared_storage.js`
  - save envelope の解析とローカル保存を担当します。
- `location_shared.js`
  - location、shop、inn、回復処理などで共有する補助処理を持ちます。

## 画面構成

- `screens/location_screen.js`
  - Location 選択と、battle / shop / inn / menu への入口です。
- `screens/menu_screen.js`
  - パーティ一覧、save / load、各サブ画面への遷移を担当します。
- `screens/item_screen.js`
- `screens/magic_screen.js`
- `screens/equip_screen.js`
- `screens/status_screen.js`
- `screens/job_screen.js`
  - menu 配下のサブ画面です。共通レイアウトは `screens/menu_subpage_shell.js` を使います。
- `screens/shop_screen.js`
- `screens/inn_screen.js`
- `screens/battle_screen.js`
  - menu 以外の遷移先を SPA 画面として包むラッパです。
- `screens/screen_shared.js`
  - 画面間で共通になる UI イベント、選択メンバー同期、save 反映、Location 表示文言をまとめる補助です。

## データの流れ

1. `router.js` が常に 1 画面だけをマウントします。
2. 各画面は `store.getState()` から必要な状態を読みます。
3. 永続化が必要な変更は store 経由で戻します。
   - `patch(...)`: 軽い UI 状態更新
   - `updateMenuState(...)`: `menu_state` 更新
   - `updateSaveEnvelope(...)`: save 更新
   - `persistMenuEnvelope(...)`: `menu_state` と save をまとめて更新
4. battle や equip のようにゲームルール依存の再計算が必要な箇所は、JavaScript で再実装せず Pyodide 上の Python に委譲します。

## 今後の実装ルール

- 新しい画面は `screens/` 配下に追加し、`router.js` に登録します。
- 画面遷移は `window.location.href` ではなく `navigate(...)` を使います。
- Pyodide の取得は `loadPyodide()` を直接呼ばず、`getPyodideRuntime()` を使います。
- `menu_state` と save は store を通して同期を保ちます。
- 旧 `*.html` は実装本体ではなく、互換性維持のためのリダイレクトとして扱います。
