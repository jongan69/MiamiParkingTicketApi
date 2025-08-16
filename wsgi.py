#!/usr/bin/env python3
"""
WSGI entry point for production deployment
"""

from main import app

if __name__ == "__main__":
    app.run()
