# Wasm Map 改修テンプレート

`web_wasm` のマップ改修で、実際に 1 件追加・変更するときのテンプレートです。
作業前にこの文書を複製し、対象マップ名やフラグ名を埋めて使う想定です。

## 使い方

1. この文書を見ながら、対象作業のチェックリストを上から順に埋める。
2. JSON 雛形を `assets/maps/*.json` に合わせてコピーする。
3. 対応するコード参照先を見ながら、必要な JS 側の登録や分岐を追加する。
4. 最後に関連テストと実機確認項目を消化する。

---

## 0. 共通メモ

### 対象

- 作業名:
- 対象マップ ID:
- 対象 Location Group:
- 対象 Location:
- 追加する event flag:
- 追加する dialogue index:
- 関連 treasure_id:
- 関連 npc_key / scripted_sequence:

### 主な編集先

- マップ JSON: `assets/maps/*.json`
- マップ manifest: `web_wasm/map_data.js`
- マップ画面本体: `web_wasm/screens/map_screen.js`
- 追従者判定: `web_wasm/guest_companion.js`
- セリフ本文: `assets/data/merged_fixed.json`
- 関連テスト: `web_wasm/map_data.test.mjs`, `web_wasm/screens/map_screen.test.mjs`, `web_wasm/guest_companion.test.mjs`

### 共通チェック

- [ ] `id` とファイル名、`MAP_MANIFEST` のキーが対応している
- [ ] `location_requirement.group` / `locations` が既存 Location と一致している
- [ ] `spawn` から通路に出られる
- [ ] `collision_gids` と見た目が破綻していない
- [ ] 新しい `event_flag` 名が既存と衝突していない
- [ ] 新しい `treasure_id` 名が既存と衝突していない
- [ ] 新しい `npc_key` / `scripted_sequence` 名が既存と衝突していない

---

## 1. 新マップ追加テンプレート

### チェックリスト

- [ ] `assets/maps/新Map名.json` を作成した
- [ ] `id`, `name`, `width`, `height`, `rows`, `spawn`, `collision_gids`, `tileset`, `location_requirement`, `objects` を定義した
- [ ] 既存マップから入る `exit` を必要に応じて追加した
- [ ] `web_wasm/map_data.js` の `MAP_MANIFEST` に登録した
- [ ] 必要なら Location 側の導線を確認した
- [ ] マップの中央付近や主要導線の通行確認をした
- [ ] `web_wasm/map_data.test.mjs` の manifest / 解決テストを更新した

### JSON 雛形

```json
{
  "id": "New_Map_Id",
  "name": "New Map Name",
  "tile_width": 24,
  "tile_height": 24,
  "width": 16,
  "height": 16,
  "tileset": {
    "name": "TILESET - Sample",
    "image": "../assets/images/maps/sample.png",
    "columns": 16,
    "tile_count": 128
  },
  "collision_gids": [1, 2, 70],
  "location_requirement": {
    "group": "Sample Group",
    "locations": ["Sample Location"]
  },
  "encounter_rate": 0.05,
  "padding": {
    "top": 10,
    "right": 10,
    "bottom": 10,
    "left": 10,
    "fill_gid": 1
  },
  "spawn": {
    "x": 3,
    "y": 5
  },
  "objects": [],
  "rows": [
    "1,1,1,1",
    "1,0,0,1",
    "1,0,0,1",
    "1,1,1,1"
  ]
}
```

### 連動箇所

- `web_wasm/map_data.js`
  - `MAP_MANIFEST`
  - `normalizeMapDefinition(...)`
  - `loadMapDefinition(...)`
- `web_wasm/screens/map_screen.js`
  - `deriveMapLaunchContext(...)`
  - `resolveInitialMapSelection(...)`

---

## 2. NPC・セリフ追加テンプレート

### チェックリスト

- [ ] 対象マップ JSON の `objects` に `type: "npc"` を追加した
- [ ] `x`, `y`, `sprite_image`, `movement`, `direction` を設定した
- [ ] `dialogue_index` か `dialogue_indices` を設定した
- [ ] `assets/data/merged_fixed.json` に対応する本文を追加した
- [ ] 会話後に状態を変えるなら `set_event_flag` を設定した
- [ ] 出現条件や差し替え条件があるなら `required_event_flag` / `required_event_flag_absent` を設定した
- [ ] 特殊演出が必要なら `npc_key` を付与した
- [ ] 実機で表示、会話、会話後の状態変化を確認した

### JSON 雛形

```json
{
  "type": "npc",
  "name": "Sample NPC",
  "npc_key": "sample_npc_key",
  "x": 8,
  "y": 6,
  "sprite_image": "../assets/images/NPCs/fs_man1.png",
  "dialogue_index": 900,
  "movement": "fixed",
  "direction": "down",
  "set_event_flag": "sample_npc_spoken",
  "required_event_flag": "sample_story_started",
  "required_event_flag_absent": "sample_npc_hidden"
}
```

### 複数ページ会話の雛形

```json
{
  "type": "npc",
  "name": "Sample NPC Multi",
  "x": 10,
  "y": 6,
  "sprite_image": "../assets/images/NPCs/fs_woman1.png",
  "dialogue_indices": [901, 902, 903],
  "movement": "random",
  "direction": "left"
}
```

### `merged_fixed.json` 用メモ

- index:
- content:

```text
1ページ目の本文
```

### 連動箇所

- `web_wasm/map_data.js`
  - `normalizeObject(...)`
- `web_wasm/screens/map_screen.js`
  - `npcDialogueIndices(...)`
  - `resolveNpcDialogueIndicesForInteraction(...)`
  - `loadMergedFixedContentByIndices(...)`
  - `findAdjacentNpc(...)`
  - `persistNamedEventFlags(...)`

---

## 3. treasure 追加テンプレート

### チェックリスト

- [ ] 対象マップ JSON の `objects` に `type: "treasure"` を追加した
- [ ] `treasure_id`, `item_name`, `inventory_bucket`, `quantity` を設定した
- [ ] `closed_gid`, `open_gid` を設定した
- [ ] `treasure_id` が一意であることを確認した
- [ ] 守護敵がいるなら `guarded_by` を設定した
- [ ] 開封後タイル差し替えが自然に見えることを確認した
- [ ] 実機で入手、再開封不可、再入場後の永続化を確認した

### 通常 treasure 雛形

```json
{
  "type": "treasure",
  "name": "sample_treasure_1",
  "x": 4,
  "y": 7,
  "treasure_id": "sample_map_treasure_potion_1",
  "item_name": "Potion",
  "inventory_bucket": "Anywhere",
  "quantity": 1,
  "closed_gid": 125,
  "open_gid": 126
}
```

### GIL treasure 雛形

```json
{
  "type": "treasure",
  "name": "sample_treasure_gil",
  "x": 5,
  "y": 7,
  "treasure_id": "sample_map_treasure_500_gil",
  "item_name": "GIL",
  "inventory_bucket": "Anywhere",
  "quantity": 500,
  "closed_gid": 125,
  "open_gid": 126
}
```

### 守護 treasure 雛形

```json
{
  "type": "treasure",
  "name": "sample_guarded_treasure",
  "x": 6,
  "y": 7,
  "treasure_id": "sample_map_treasure_guarded",
  "item_name": "Longsword",
  "inventory_bucket": "Weapon",
  "quantity": 1,
  "guarded_by": ["Goblin", "Goblin"],
  "closed_gid": 125,
  "open_gid": 126
}
```

### 連動箇所

- `web_wasm/screens/map_screen.js`
  - `treasureKey(...)`
  - `openAdjacentTreasure(...)`
  - `finalizeTreasureOpen(...)`
  - `writeSavedTreasureStates(...)`
  - `applyPendingGuardedTreasureReward(...)`
  - `applySwitchStateToMap(...)`

---

## 4. 追従者追加テンプレート

### チェックリスト

- [ ] 加入元 NPC か event をマップ JSON に追加した
- [ ] 追従開始フラグ名を決めた
- [ ] `web_wasm/guest_companion.js` に active 判定を追加した
- [ ] `web_wasm/screens/map_screen.js` にスプライト URL を追加した
- [ ] 必要なら `npc_key` または `scripted_sequence` を追加した
- [ ] 専用の `run...Sequence()` を追加した
- [ ] シーケンス内で加入フラグ保存を追加した
- [ ] 追従位置状態の初期化を追加した
- [ ] 実機で加入後の追従、会話、戦闘復帰後の維持を確認した

### 加入元 NPC 雛形

```json
{
  "type": "npc",
  "name": "Sample Guest NPC",
  "npc_key": "sample_guest_join_npc",
  "x": 3,
  "y": 9,
  "sprite_image": "../assets/images/NPCs/fs_sara.png",
  "dialogue_index": 910,
  "movement": "fixed",
  "direction": "left",
  "required_event_flag_absent": "sample_guest_joined"
}
```

### 加入 event 雛形

```json
{
  "type": "event",
  "name": "Sample Guest Join Event",
  "x": 5,
  "y": 9,
  "hidden": true,
  "scripted_sequence": "sample_guest_join_sequence",
  "required_event_flag": "sample_story_mid",
  "required_event_flag_absent": "sample_guest_joined"
}
```

### 追加時メモ

- 追従者種別名:
- 加入フラグ:
- 離脱フラグ:
- 使用スプライト:
- 会話 index:
- 専用 sequence 名:

### 連動箇所

- `web_wasm/guest_companion.js`
  - `isSaraGuestActive(...)` 相当
  - `resolveActiveGuestFollowerType(...)`
- `web_wasm/screens/map_screen.js`
  - `shouldRenderGuestFollowerOnMap(...)`
  - `followerSpriteUrlForType(...)`
  - `syncSaraFollowerStateForMap(...)`
  - `maybeFollowWithSealedCaveSara(...)`
  - `maybeOpenSaraFollowerDialogue(...)`

---

## 5. 追従者離脱テンプレート

### チェックリスト

- [ ] 離脱トリガーとなる NPC / event / 戦闘後 cutscene を決めた
- [ ] 離脱フラグ名を決めた
- [ ] `guest_companion.js` の active 判定が離脱後 false になるよう更新した
- [ ] 離脱イベント側で `persistNamedEventFlag(...)` を呼ぶようにした
- [ ] 必要ならマップ上の NPC 差し替え条件を JSON に追加した
- [ ] 必要なら再入場や再描画処理を追加した
- [ ] 実機で離脱後に追従が消え、再入場後も復帰しないことを確認した

### 離脱 event 雛形

```json
{
  "type": "event",
  "name": "Sample Guest Leave Event",
  "x": 7,
  "y": 12,
  "hidden": true,
  "dialogue_indices": [920, 921],
  "set_event_flag": "sample_guest_left_party",
  "required_event_flag": "sample_guest_joined",
  "required_event_flag_absent": "sample_guest_left_party"
}
```

### 離脱後 NPC 差し替え雛形

```json
{
  "type": "npc",
  "name": "Sample NPC After Leave",
  "x": 7,
  "y": 4,
  "sprite_image": "../assets/images/NPCs/fs_king1.png",
  "dialogue_index": 922,
  "movement": "fixed",
  "direction": "down",
  "required_event_flag": "sample_guest_left_party"
}
```

### 連動箇所

- `web_wasm/guest_companion.js`
- `web_wasm/screens/map_screen.js`
  - `persistNamedEventFlag(...)`
  - `runPostBattleCutscene(...)` 系
  - `renderMapTiles(...)`

---

## 6. イベント追加テンプレート

### チェックリスト

- [ ] 対象マップ JSON に `type: "event"` を追加した
- [ ] `x`, `y`, `name` を設定した
- [ ] 会話のみなら `dialogue_indices` を設定した
- [ ] 戦闘イベントなら `enemy_names` を設定した
- [ ] 戦闘後会話があるなら `post_victory_dialogue_indices` を設定した
- [ ] 一度きり制御が必要なら `set_event_flag` / `required_event_flag_absent` を設定した
- [ ] 汎用処理で足りないなら `scripted_sequence` と専用関数を追加した
- [ ] `merged_fixed.json` に本文を追加した
- [ ] 実機で発火、再発条件、戦闘後反映を確認した

### 会話だけの event 雛形

```json
{
  "type": "event",
  "name": "Sample Story Event",
  "x": 8,
  "y": 11,
  "dialogue_indices": [930],
  "set_event_flag": "sample_story_event_seen",
  "required_event_flag_absent": "sample_story_event_seen",
  "hidden": true
}
```

### 戦闘 event 雛形

```json
{
  "type": "event",
  "name": "Sample Ambush Event",
  "x": 9,
  "y": 11,
  "dialogue_indices": [931],
  "enemy_names": ["Goblin", "Goblin"],
  "post_victory_dialogue_indices": [932],
  "set_event_flag": "sample_ambush_cleared",
  "required_event_flag_absent": "sample_ambush_cleared",
  "hidden": true
}
```

### 専用シーケンス event 雛形

```json
{
  "type": "event",
  "name": "Sample Scripted Event",
  "x": 10,
  "y": 11,
  "hidden": true,
  "scripted_sequence": "sample_scripted_sequence",
  "required_event_flag": "sample_story_started",
  "required_event_flag_absent": "sample_scripted_done"
}
```

### 連動箇所

- `web_wasm/screens/map_screen.js`
  - `findStandingObject(...)`
  - `triggerStandingEvent(...)`
  - `eventEnemyNames(...)`
  - `eventPostVictoryDialogueIndices(...)`
  - `navigateToEncounter(...)`
  - `runPostBattleCutscene(...)`

---

## 7. switch / barrier 併用テンプレート

### チェックリスト

- [ ] `switch` object を置いた
- [ ] `barrier` object を置いた
- [ ] 両者の `switch_id` / `trigger_by` が一致している
- [ ] `closed_gid` / `open_gid` が見た目どおりに切り替わる
- [ ] 実機で ON/OFF と通行可否を確認した

### switch 雛形

```json
{
  "type": "switch",
  "name": "switch1",
  "x": 10,
  "y": 2,
  "switch_id": "switch1"
}
```

### barrier 雛形

```json
{
  "type": "barrier",
  "name": "switch1 barrier",
  "x": 7,
  "y": 2,
  "trigger_by": "switch1",
  "closed_gid": 49,
  "open_gid": 1
}
```

### 連動箇所

- `web_wasm/screens/map_screen.js`
  - `toggleAdjacentSwitch(...)`
  - `applySwitchStateToMap(...)`

---

## 8. 変更後の確認テンプレート

### テスト

- [ ] `node --test /Users/hirotaka/beautiful_soup/web_wasm/map_data.test.mjs`
- [ ] `node --test /Users/hirotaka/beautiful_soup/web_wasm/screens/map_screen.test.mjs`
- [ ] `node --test /Users/hirotaka/beautiful_soup/web_wasm/guest_companion.test.mjs`

### 実機確認

- [ ] 対象マップへ正常に入れる
- [ ] 通路・衝突判定が意図どおり
- [ ] NPC 表示・向き・移動が意図どおり
- [ ] セリフが想定どおり表示される
- [ ] treasure が一度だけ開く
- [ ] event が条件どおりに発火する
- [ ] event flag による出し分けが効く
- [ ] 追従者の加入・追従・離脱が意図どおり
- [ ] 戦闘復帰後の後処理が壊れていない

### 作業ログ

- 変更ファイル:
- 実行テスト:
- 実機確認結果:
- 残課題:

