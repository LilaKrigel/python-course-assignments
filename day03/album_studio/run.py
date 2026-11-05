"""Start Album Studio:  python run.py

The app opens in your browser. Keep this window open while you work; close it to stop the app.
"""
import argparse
import threading
import webbrowser

from studio.server import app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Album Studio")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}"
    print(f"Album Studio is running at {url}\nKeep this window open while you work; close it to stop.")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    app.run(host="127.0.0.1", port=args.port, threaded=True)
