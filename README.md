conda activate game-env
pip install -r requirements.txt
python app\_pygame.py



\## Render deployment

\- `requirements.txt` is placed at the repository root (`beautiful\_soup/requirements.txt`).

\- This repository includes `render.yaml` with:

&nbsp; - `rootDir: .`

&nbsp; - `buildCommand: pip install -r requirements.txt`

&nbsp; - `startCommand: gunicorn adapters.flask\_app:app`



If your Git repository is a monorepo and this project lives in a subfolder, set Render

`Root Directory` to that subfolder (for example `beautiful\_soup`) so Render can find

`requirements.txt`.

