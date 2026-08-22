#!/bin/bash
set -e
uvicorn ace.main:app --reload
