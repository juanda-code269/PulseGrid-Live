# LivePipe

A reusable adapter architecture with `fetch_data()`, `validate_data()`, `transform_data()`, and `display_data()`. Includes Open-Meteo weather, CoinGecko prices, an offline sensor, caching, manual refresh, timeouts, validation, logging, visible provenance, and failure handling.

```bash
pip install -r requirements.txt
streamlit run app.py
```

New sources subclass `Adapter`, return the standard `timestamp` / `value` / `unit` schema, and register in `make_adapter()`.
