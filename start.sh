#!/bin/bash

# Start using bash

# Backend
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend em outra janela
# cd frontend
# npm run dev