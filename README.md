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