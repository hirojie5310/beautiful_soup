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
- `save_repository.js`
  - save envelope / `menu_state` の読み書き入口です。
  - UI 層は `localStorage` / `IndexedDB` を直接触らず、この repository 経由で保存・読込・slot 一覧・削除を行います。
- `shared_storage.js`
  - save envelope の解析、`IndexedDB` スロット保存、last-used slot の保持を担当する低レベル実装です。
- `location_shared.js`
  - location、shop、inn、回復処理などで共有する補助処理を持ちます。

## 画面構成

- `screens/location_screen.js`
  - Location 選択と、battle / shop / inn / menu への入口です。
- `screens/menu_screen.js`
  - パーティ一覧、manual save slot 選択、auto save 表示、各サブ画面への遷移を担当します。
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
   - 通常の画面表示で storage を直接再読込しません。
   - 初期データの非同期読込は `app.js` → `store.initialize()` に集約します。
   - 例外は、ユーザーが明示的に選ぶ manual load / auto load の `loadSlot()` 系操作だけです。
3. 永続化が必要な変更は store 経由で戻します。
   - `patch(...)`: 軽い UI 状態更新
   - `updateMenuState(...)`: `menu_state` 更新
   - `updateSaveEnvelope(...)`: save 更新
   - `persistMenuEnvelope(...)`: `menu_state` と save をまとめて更新
   - slot 保存・読込・削除は `saveRepository` 経由
4. battle や equip のようにゲームルール依存の再計算が必要な箇所は、JavaScript で再実装せず Pyodide 上の Python に委譲します。
5. 戦闘終了時は `AUTO SAVE` スロットが更新され、手動保存は `Slot 1` - `Slot 3` をメニューから選びます。

## Save schema

- top-level envelope は JavaScript 側が管理します。
- `save.schema_version` はゲームデータの版です。
- 現在の Wasm runtime は `schema_version: 2` を前提にします。
- `schema_version: 1` の旧 save は `bootstrap_runtime.py` の `migrate_save()` で v2 へ変換します。
- v2 の追加項目:
  - `current_job`
  - `mp_levels`

## RuntimeState contract

- Python 側の実行時状態は `combat.runtime_state.RuntimeState` が境界です。
- `RuntimeState` の save は `SaveDataState` 相当の JSON 化可能な dict として扱います。
- `init_runtime_state()` は構築後に `validate_runtime_state(...)` を通します。
- 重要な不変条件:
  - `save.gil`, `save.CP`, inventory count は 0 以上
  - party member の `name` は空文字不可
  - `hp`, `max_hp`, `exp`, `mp`, `mp_levels` は 0 以上
  - `hp <= max_hp`
  - `row` は `front` / `back` のみ
  - `job_level` / `job_levels` は `level >= 1`, `skill_point >= 0`
- save の構造検証は `schemas/ff3-save-envelope.schema.json`、RuntimeState 固有の不変条件は `validate_runtime_state(...)` に集約します。

## Battle save patch

- 戦闘終了時の save 反映差分は `combat.battle_save_patch.BattleSavePatch` で表現します。
- Wasm round response は `battle_save_patch` を返します。
- `RuntimeState.apply(patch)` が `BattleSavePatch` の save 反映入口です。
- Wasm 経路では勝利報酬と戦闘終了時の runtime party HP/MP 同期を patch apply 経由に移しています。
- Flask / Pygame 互換のため、既存の `apply_victory_rewards(...)` は直接 save 反映 API として残しています。
- `battle_save_patch` の主な対象:
  - `resource_changes`: gil / CP
  - `party_changes`: hp / max_hp / level / exp / job_level / mp_levels
  - `inventory_changes`
  - `item_stock_changes`
  - `rewards`
- 今後、保存副作用をさらに分離する場合は、Flask / Pygame 側の勝利報酬も `BattleSavePatch` 生成と `state.apply(patch)` に寄せます。

### Current Status

- 2026-04-29 時点では、BattleResult 差分化は **Wasm の battle-finished 保存経路で実運用中** です。
- JS 側は `battle_save_patch` を browser save mirror 更新に使える状態になっています。
- 一方で Flask / Pygame では `apply_victory_rewards(...)` による直接 save mutation が残っており、**プロジェクト全体では mixed mode** です。

### Completion Line

BattleResult 差分化は、次の条件をすべて満たした時点で「完了」とみなします。

1. 戦闘終了で発生する永続 save 更新が、全ランタイム経路で `BattleSavePatch` 生成と `RuntimeState.apply(patch)` を通る。
2. Flask / Pygame / Wasm のどの battle-finished 経路でも、`apply_victory_rewards(...)` のような直接 save mutation API に依存しない。
3. JS 側の battle-finished 保存は、`battle_save_patch` を一次入力として mirror / store 更新できる。
4. 戦闘終了で追加された新しい save 副作用は、`BattleSavePatch` の表現対象に必ず追加され、差分テストが先に用意される。
5. `battle_save_patch` を使う主要経路で、生成・適用・JS 消費の回帰テストが揃っている。

### Migration Rules

- 移行中に battle-finished save 更新を新規追加する場合、まず `BattleSavePatch` の生成と適用を追加し、直接 mutation は互換レイヤに閉じ込めます。
- mixed mode のあいだも、Wasm 側の battle-finished 保存で直接 `state.save` を更新する新規コードは追加しません。
- Flask / Pygame で互換 API を残す場合は、「どの経路が未移行か」をこの文書か関連ドキュメントに明記します。
- `apply_victory_rewards(...)` を削除できる状態になったら、この節の Current Status を更新し、Completion Line の達成を明記します。

## 今後の実装ルール

- 新しい画面は `screens/` 配下に追加し、`router.js` に登録します。
- 画面遷移は `window.location.href` ではなく `navigate(...)` を使います。
- Pyodide の取得は `loadPyodide()` を直接呼ばず、`getPyodideRuntime()` を使います。
- screen は原則として store の state を読むだけにし、起動時の storage 再読込を持ち込みません。
- 非同期 load は `store.initialize()` に集約し、screen で許容する読込操作は `loadSlot()` などユーザー明示操作だけにします。
- `menu_state` と save は store を通して同期を保ちます。
- save envelope / `menu_state` の永続化入口は `saveRepository` に集約します。
- `assets/maps/**.json` に新しいマップデータを追加したら、対応する URL / エントリを `web_wasm/map_data.js` に必ず登録します。
- マップデータを追加・更新したら、`web_wasm/map_data.test.mjs` など関連テストも更新し、Wasm 側からそのマップが解決できることを確認します。
- マップデータ JSON を新規作成したら、`spawn` 座標からマップ中央の衝突判定がないスペースまで実際に到達できるかを確認します。途中に見た目は同じだが衝突判定付きの壁面タイルが混ざっていて導線を塞いでいる場合は、元画像と同じデザインで衝突判定のない別 `gid` のタイルへ手作業で置換して、経路を通過可能にしてから保存します。
- RuntimeState に新しい永続フィールドを追加したら、型契約、JSON Schema、不変条件テストを同時に更新します。
- 戦闘終了で save に新しい副作用を追加したら、`BattleSavePatch` と差分テストも更新します。
- 旧 `*.html` は実装本体ではなく、互換性維持のためのリダイレクトとして扱います。

## Map BGM 差し替えメモ

### 差し替え手順

1. `assets/sounds/bgm/` に差し替えたい音源を配置します。
2. マップ画面 BGM の割り当ては `web_wasm/screens/map_screen.js` の定数と `resolveMapBgmUrl(...)` で管理します。
3. 対象 map / location group に対応する BGM 定数を更新します。
4. `web_wasm/screens/map_screen.test.mjs` の `resolveMapBgmUrl selects map themes by map id or location group` も更新します。
5. 変更後は `node --test /Users/hirotaka/beautiful_soup/web_wasm/screens/map_screen.test.mjs` を実行します。
6. ブラウザで対象マップに入り、BGM 再生とメモリ使用量が安定していることを確認します。

### 推奨エンコード条件

- 形式はまず `Ogg Vorbis` を優先します。
- チャンネルは `stereo`、サンプルレートは `44.1kHz` を推奨します。
- ビットレートは既存の安定実績に合わせて `約 112 kbps` 前後を目安にします。
- 既存の安定ファイルと大きく異なる特殊なエンコード条件は避けます。
- 音源差し替え後は、再生可否だけでなくブラウザのメモリ増加がないかも必ず確認します。

### トラブルシュート

- 特定マップでだけメモリ使用量が急増する場合、そのマップ固有ロジックではなく BGM ファイル自体が原因のことがあります。
- Kazus では旧 `jinn-the-fire.ogg` で、再生中にメモリが増え続ける事象がありました。再エンコード版へ差し替えたところ安定しました。
- 問題切り分けでは、まずそのマップの BGM を使用実績のある既知の安定音源へ一時的に差し替え、症状が消えるか確認します。
