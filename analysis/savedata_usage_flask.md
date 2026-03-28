# ffiii_savedata.json 参照棚卸し（`adapters/flask_app.py` 起点）

## 対象と前提

- 起点: `adapters/flask_app.py` の `create_app()` から始まる Flask 実行経路。
- 調査方法: `state.save` / `party_entry` の読み書きを静的に追跡。
- ここでの「参照されない」は **読み取り値としてゲーム挙動に使われない** ことを指す。
  - 例: 値を読み込んでも直後に必ず上書きされる項目は「実質未使用入力」とみなす。

## 結論（要約）

### 1) トップレベルで実質未使用（Flask ゲーム内挙動に未参照）

- `event_flag`
- `treasures`

上記2つは、Flask 戦闘/メニューの経路で `state.save` から参照されていない。

### 2) パーティメンバー内で実質未使用（入力として不要）

以下は `party[]` に存在していても、初期化時に挙動決定へ使われない（または上書きされる）:

- `image_name`（未参照）
- `hp`（ロード時に読まれず、初期 HP は再計算値でセット）
- `max_hp`（いったん読んで `BaseCharacter` に入れるが、後段で必ず再計算値に上書き）
- `strength`, `agility`, `vitality`, `intelligence`, `mind`（同様に補間値で上書き）

> 補足（誤解しやすい点）
>
> - `assets/data/ffiii_jobs_compact.json` の `StatsByLevel` は **実際に適用されている**。
> - 本ドキュメントで「実質未使用」としたのは、`ffiii_savedata.json` 側の
>   `party[].strength/agility/vitality/intelligence/mind` の入力値であり、
>   これらはロード時に `StatsByLevel` 由来値で上書きされるため。

### 3) 「冗長だが互換/補助用途がある」項目

- `party[].level`
  - 最終レベルは `exp` から算出される。
  - ただし `normalize_party_entry()` で `exp` の下限クランプに使用されるため、完全未使用ではない。
- `party[].job_level`
  - `job_levels` が存在する現行形式ではフォールバック用途。
  - 旧セーブ互換や `job_levels` 欠損時の初期化に使われる。

### 4) 参照されている（削除非推奨）主要項目

- トップレベル: `party`, `gil`, `CP`, `map.surface`, `inventory`, `item_stock`
- パーティ内: `name`, `exp`, `job`, `job_levels`, `mp`, `row`, `equipment`, `Magic`, `status_effects`, `portrait_key`

## 根拠（主要コード）

- セーブデータロード: `init_runtime_state()` が `ffiii_savedata.json` を `state.save` に読み込む。
- パーティ構築: `build_party_members_from_save()` → `character_from_party_entry()`。
  - `exp` からレベル再算出。
  - ステータス/最大HPをジョブの `StatsByLevel` から再計算し、`base.*` を上書き。
- 地形依存コマンド (`Terrain`): `save.get("map").get("surface")` を参照。
- 勝利報酬: `gil` / `CP` / `item_stock` を更新。

## 補足

- `event_flag`, `treasures` は将来拡張（イベント進行/宝箱開封管理）向けに保持されている可能性はある。
  ただし、**現時点の Flask 実装起点では未使用**。
- `hp` は「現在HPを永続化する意図」が見える一方で、起動時ロードで反映していないため、
  セーブ再開時に全快再計算される挙動になっている。
