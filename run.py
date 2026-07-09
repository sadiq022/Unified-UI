#!/usr/bin/env python3
"""
Unified UI — Run Script
Builds the React frontend (if needed) and starts the FastAPI server.

Usage:
    python run.py              # Start normally (builds frontend if missing)
    python run.py --rebuild    # Force rebuild the frontend
    python run.py --dev        # Start without building (use if running Vite dev server separately)
"""

import os
import sys
import subprocess
import argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(ROOT, "frontend")
DIST_DIR = os.path.join(FRONTEND_DIR, "dist")


def run_command(cmd, cwd=None, check=True):
    """Run a shell command and stream output."""
    print(f"  → {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd or ROOT, check=check)
    return result.returncode == 0


def check_node():
    """Check if Node.js is available."""
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def install_frontend_deps():
    """Install npm dependencies if node_modules doesn't exist."""
    node_modules = os.path.join(FRONTEND_DIR, "node_modules")
    if not os.path.isdir(node_modules):
        print("\n📦 Installing frontend dependencies...")
        run_command("npm install", cwd=FRONTEND_DIR)
    else:
        print("  ✓ Frontend dependencies already installed")


def build_frontend():
    """Build the React frontend with Vite."""
    print("\n🔨 Building frontend...")
    run_command("npm run build", cwd=FRONTEND_DIR)
    print("  ✓ Frontend built successfully")


def start_server(host="0.0.0.0", port=5000):
    """Start the FastAPI server with uvicorn."""
    print(f"\n🚀 Starting Unified UI server on http://localhost:{port}")
    print(f"   Press Ctrl+C to stop\n")

    try:
        import uvicorn
        uvicorn.run("backend.app:app", host=host, port=port, reload=False)
    except ImportError:
        print("❌ uvicorn not found. Install dependencies first:")
        print(f"   pip install -r {os.path.join(ROOT, 'requirements.txt')}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Unified UI — Multi-Model LLM Comparison")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild the frontend")
    parser.add_argument("--dev", action="store_true", help="Skip frontend build (dev mode)")
    parser.add_argument("--host", default="0.0.0.0", help="Server host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="Server port (default: 5000)")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════╗")
    print("║         🔮 Unified UI v1.0.0             ║")
    print("║   Multi-Model LLM Comparison Chatbot     ║")
    print("╚══════════════════════════════════════════╝")

    if not args.dev:
        if not check_node():
            print("\n❌ Node.js not found. Please install Node.js to build the frontend.")
            print("   Visit: https://nodejs.org/")
            sys.exit(1)

        install_frontend_deps()

        if args.rebuild or not os.path.isdir(DIST_DIR):
            build_frontend()
        else:
            print("  ✓ Frontend already built (use --rebuild to rebuild)")

    start_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
