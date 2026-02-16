# DomainError 設計と Flask エラーハンドラ雛形

## 1. 目的

Flask 移行時の手戻りを減らすために、例外を `DomainError` 系に統一し、
Flask 側で HTTP レスポンスへ一元変換できるようにする。

## 2. エラー型設計

`combat/errors.py` で以下を定義。

- `DomainError`: 基底クラス
  - `message`, `code`, `http_status`, `details` を保持
  - `to_payload()` で API レスポンス形式に変換
- `InputValidationError` (`422`): 入力/DTO バリデーション
- `InvalidLifecycleError` (`409`): 状態遷移違反
- `StateNotInitializedError` (`500`): 状態初期化漏れ
- `InternalDomainError` (`500`): 想定外エラーの外部公開用

## 3. 既存実装への適用ポイント

- DTO バリデーション
  - `DTOValidationError` を `InputValidationError` 継承へ変更
- ユースケース境界
  - `execute_round_dto` の状態不正を `InvalidLifecycleError` 化
- 状態依存処理
  - `get_state(None)` を `StateNotInitializedError` 化

## 4. Flask エラーハンドラ雛形

`adapters/flask_error_handlers.py` に以下を用意。

- `map_domain_error_to_http(error)`
- `map_unexpected_error_to_http(error)`
- `register_flask_error_handlers(app)`

想定レスポンス形式:

```json
{
  "error": {
    "code": "input_validation_error",
    "message": "planned_actions must be list[object|null]. actual=dict",
    "details": {}
  }
}
```

## 5. ルート実装例（最小）

```python
from flask import Flask, jsonify, request

from adapters.flask_error_handlers import register_flask_error_handlers
from combat.dto import parse_execute_round_input_dict, to_json_ready_dict
from combat.usecases import execute_round_dto

app = Flask(__name__)
register_flask_error_handlers(app)

@app.post("/battle/round")
def post_battle_round():
    request_dto = parse_execute_round_input_dict(request.get_json(force=True))
    output_dto = execute_round_dto(session=current_session, request=request_dto, rng=rng)
    return jsonify(to_json_ready_dict(output_dto)), 200
```

この形にすると、ルートでは業務ロジックに触れず、エラーもハンドラに委譲できる。
