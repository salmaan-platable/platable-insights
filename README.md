# Platable Insights (Streamlit)

Five-view Streamlit app: Company, Vendor, Item, Account Manager, Settings. Upload a single combined sheet in Settings.

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy
- Push this folder to GitHub, deploy on Streamlit Cloud with entrypoint `streamlit_app.py`.
- In the app: Settings → upload your combined sheet → open any view.
