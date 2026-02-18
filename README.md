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