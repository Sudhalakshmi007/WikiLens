"""
WikiLens Application Launcher
Starts the FastAPI server with Uvicorn.
"""

import uvicorn
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("=" * 60)
    print(" Starting WikiLens Smart Wikipedia Search Engine")
    print(" Local Access: http://127.0.0.1:8000")
    print(" Network Access (Phone/Other devices): http://192.168.151.198:8000")
    print(" API Documentation: http://127.0.0.1:8000/docs")
    print("=" * 60)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)

