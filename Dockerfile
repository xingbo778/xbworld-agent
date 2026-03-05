###############################################################################
# XBWorld Agent — lightweight image (agent only, no freeciv server)
#
# Connects to a remote xbworld-server and plays autonomously via LLM.
# Exposes a tracing dashboard on $PORT.
###############################################################################
FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py agent.py agent_tools.py game_client.py \
     decision_engine.py llm_providers.py state_api.py \
     main.py multi_main.py run_remote.py trace_server.py ./

ENV PYTHONUNBUFFERED=1

CMD ["python3", "main.py"]
