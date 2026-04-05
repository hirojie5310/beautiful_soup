# web_wasm 軽い回帰確認チェックリスト

SPA 移行後に、主要画面を一巡するときの簡易チェックメモです。
各項目は「最低限ここを見れば大きな退行に気づける」という粒度に絞っています。

## 事前条件

- `web_wasm/` をブラウザで開く
- 既存セーブデータがある場合はロードしてから確認する
- 可能なら 1 回 battle を開始して party / menu_state を初期化した後に確認する

## location

- 開く
  - `index.html#/location` で Location 画面が表示される
  - Location Group と Location の候補が表示される
- 戻る
  - `shop` `inn` `menu` `battle` から戻って再度開ける
- 状態反映
  - 選択した Location Group / Location が保持される
  - 画面を移動して戻っても選択内容が残る
- 保存反映
  - battle 開始後や save 後に戻っても、最後に選んだ Location が維持される

## shop

- 開く
  - `location` から遷移して Shop 画面が開く
  - map / type / goods の候補が表示される
- 戻る
  - `Locationへ戻る` で `location` に戻れる
  - `メニュー` で `menu` に移動できる
- 状態反映
  - 画面上に現在の Location が表示される
  - 商品選択に応じて価格表示が切り替わる
- 保存反映
  - 購入後に GIL が減る
  - `menu` や `item` で購入品が反映される
  - 画面を開き直しても購入結果が残る

## inn

- 開く
  - `location` から遷移して Inn 画面が開く
  - 所持 GIL と宿泊料金が表示される
- 戻る
  - `Locationへ戻る` で `location` に戻れる
  - `メニュー` で `menu` に移動できる
- 状態反映
  - 現在の Location が表示される
  - 宿泊後に HP / MP / 状態異常が回復する
- 保存反映
  - 宿泊後に GIL が減る
  - `menu` や `status` で回復結果が反映される
  - 画面を開き直しても回復結果が残る

## menu

- 開く
  - `location` や `battle` から遷移して MENU が開く
  - party 一覧と CP / GIL が表示される
- 戻る
  - `Location選択へ戻る` で `location` に戻れる
- 状態反映
  - party の HP / MP / row / job が現在状態を反映している
  - `ならびかえ` で front / back を切り替えられる
- 保存反映
  - `セーブ` でブラウザ保存とファイル保存が動く
  - `ロード` で party / resources / location が復元される

## item

- 開く
  - `menu` から `アイテム` で開く
  - 所持アイテム一覧が表示される
- 戻る
  - `BACK` で `menu` に戻れる
- 状態反映
  - 使用可能アイテムを使うと対象キャラの HP / 状態異常が更新される
  - 並び順切替や item 選択が画面に反映される
- 保存反映
  - 使用後に在庫が減る
  - `menu` や `status` を開き直しても結果が残る

## magic

- 開く
  - `menu` から `まほう` で開く
  - キャラ名、job、魔法スロット、候補一覧が表示される
- 戻る
  - `BACK` で `menu` に戻れる
  - `◀` `▶` と左右キーでキャラ切替できる
- 状態反映
  - `learn` `remove` `swap` `use` の各操作が画面に反映される
  - 使用時に MP が減り、回復系なら対象ステータスが更新される
- 保存反映
  - `menu` や `status` を開き直しても魔法設定と HP / MP 変化が残る

## equip

- 開く
  - `menu` から `そうび` で開く
  - 装備スロットと候補一覧が表示される
- 戻る
  - `BACK` で `menu` に戻れる
  - `◀` `▶` と左右キーでキャラ切替できる
- 状態反映
  - 装備変更後に装備欄と画面上の攻撃 / 防御表示が更新される
  - `release` で全装備解除ができる
- 保存反映
  - `status` を開くと攻撃力、防御力、攻撃回数などが反映される
  - `item` や再度 `equip` を開いても在庫と装備状態が一致する

## status

- 開く
  - `menu` から `ステータス` で開く
  - 顔画像、名前、LV、能力値が表示される
- 戻る
  - `BACK` で `menu` に戻れる
  - `◀` `▶` と左右キーでキャラ切替できる
- 状態反映
  - `equip` `item` `magic` `job` の変更結果が反映される
  - 表示キャラが直前に選んでいたキャラと一致する
- 保存反映
  - 画面を開き直しても最新ステータスが残る

## job

- 開く
  - `menu` から `ジョブ` で開く
  - 候補ジョブ、必要 CP、現在ジョブが表示される
- 戻る
  - `BACK` で `menu` に戻れる
  - `◀` `▶` と左右キーでキャラ切替できる
- 状態反映
  - ジョブ選択後に current 表示が切り替わる
  - CP 消費が画面に反映される
- 保存反映
  - `menu` や `status` に戻っても job と CP の更新が残る

## battle

- 開く
  - `location` から `battle` に入れる
  - 背景、敵、コマンド、ログが表示される
- 戻る
  - battle 中または終了後に `menu` や `location` へ戻れる
- 状態反映
  - 選択した Location に応じた battle が始まる
  - 戦闘結果が party の HP / 状態 / resources に反映される
- 保存反映
  - battle 終了後に `menu` や `status` で結果が見える
  - save 後に再読み込みしても戦闘結果が残る

## 重点確認パターン

- `location -> battle -> menu -> status`
  - battle 結果が status に反映される
- `menu -> equip -> menu -> status`
  - 装備変更が status に反映される
- `menu -> item -> status`
  - アイテム使用結果が status に反映される
- `location -> shop -> menu -> item`
  - 購入品と GIL 変化が item / menu に反映される
- `location -> inn -> menu -> status`
  - 回復結果と GIL 変化が反映される
