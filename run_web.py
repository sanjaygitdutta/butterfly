"""
Starts the Web Dashboard server on http://localhost:8000
"""
import uvicorn

if __name__ == "__main__":
    print("Starting Web Dashboard on http://localhost:8000 ...")
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=False)
