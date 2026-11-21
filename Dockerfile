FROM python:3.12-slim

COPY --from=denoland/deno:bin-2.9.8 /deno /usr/local/bin/deno

RUN useradd -m -u 1000 user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data && chown user data sandbox  # sandbox: o build grava node_modules e pyodide_cache
USER user

# Extensão do Postgres do DuckDB e cache do Pyodide/pandas (o sandbox roda sem rede).
RUN python -c "import duckdb; duckdb.sql('INSTALL postgres')" \
    && cd sandbox \
    && deno install --entrypoint runner.ts \
    && deno run --allow-read --allow-write=./pyodide_cache,./node_modules --allow-net runner.ts --preparar

# A LLM_API_KEY vem de variável secreta da hospedagem em runtime; nunca ENV nem COPY .env.
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
