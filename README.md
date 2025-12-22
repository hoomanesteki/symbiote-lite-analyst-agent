# Symbiote Lite — Human-in-the-Loop Analyst Agent

## Run
```bash
python -m scripts.run_agent
```

## Database
By default the agent expects a SQLite DB at:
- `./data/taxi_trips.sqlite`

Or set:
- `SYMBIOTE_DB_PATH=/absolute/path/to/taxi_trips.sqlite`

## Environment (optional)
- `OPENAI_API_KEY` enables OpenAI routing/rewrite
- `SYMBIOTE_MODEL` sets model name (default: gpt-4)
