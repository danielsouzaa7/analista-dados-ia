FROM python:3.12-slim

RUN useradd -m -u 1000 user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data && chown user data
USER user

# Extensão do Postgres do DuckDB. Sem Deno: o Python roda no navegador do visitante.
RUN python -c "import duckdb; duckdb.sql('INSTALL postgres')"

# A LLM_API_KEY vem de variável secreta da hospedagem em runtime; nunca ENV nem COPY .env.
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
