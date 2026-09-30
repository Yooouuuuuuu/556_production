@echo off
REM Embedding sidecar: bge-m3 on CPU, OpenAI-compatible /v1/embeddings at :18768.
start "556-embedder" /min D:\dev\556_production\bin\llama\llama-server.exe -m D:\dev\556_production\models\bge-m3-Q8_0.gguf --embedding --pooling cls -c 8192 --host 127.0.0.1 --port 18768
