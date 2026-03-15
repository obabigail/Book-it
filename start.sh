#!/usr/bin/env bash

uvicorn main:app --host 0.0.0.0 --port 8000 &

streamlit run cli.py --server.port $PORT --server.address 0.0.0.0