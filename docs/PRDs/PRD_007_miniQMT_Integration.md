# PRD-007: miniQMT (xtquant) FastAPI Bridge Integration

## 1. Problem Statement
The AMS (Automated Market Screener) system runs on a Linux node in Singapore. However, it requires real-time market data and trading execution capabilities via 国金证券 miniQMT and its Python library `xtquant`. Because `xtquant` relies on Windows C++ DLLs and local IPC memory mapping, it cannot run natively on the Linux node. We need a robust, low-latency mechanism for the Linux AMS core to communicate with the Windows miniQMT client.

## 2. Solution: The FastAPI Bridge Architecture
We will implement a "Fat Server, Thin Client" C/S architecture utilizing Tencent Cloud's VPC internal network for zero-trust, ultra-low latency (<1ms) communication between the two Singapore nodes.

- **Windows Node (The Bridge)**: A standalone, lightweight Python FastAPI application. It imports `xtquant`, connects to the local miniQMT client, and exposes REST endpoints (e.g., `/api/quote`, `/api/trade`) and WebSockets (for real-time tick subscriptions).
- **Linux Node (AMS Core)**: The AMS engine will be refactored to replace its legacy data fetchers with a new `QMTClient` class that makes HTTP requests to the Windows internal IP.

## 3. Scope & Target Directory
- **Target Project Absolute Path**: `/root/.openclaw/workspace/AMS`
- **In Scope**: 
  - Creating the Windows FastAPI server script (`qmt_bridge_server.py`) to be manually deployed to the Windows node.
  - Creating the Linux Python client (`qmt_client.py`) to handle HTTP/WS communication within AMS.
- **Out of Scope**: Complex trading logic or strategy modifications. This is strictly an infrastructure and data pipe integration.

## 4. Testing Strategy & TDD Guardrails
**Testing Framework**: `pytest`
**Strategy**:
- **Unit Tests**: The `QMTClient` on Linux must be tested using `responses` or `unittest.mock` to simulate the FastAPI server's JSON responses. No real network connection is allowed during unit testing.
- **TDD GUARDRAIL (CRITICAL)**: Every micro-PR contract generated for this feature MUST contain both the failing test AND its corresponding implementation fix in the exact same PR. Never split a test and its implementation across different PRs. The PR MUST pass CI preflight cleanly.
## 5. Appendix: Infrastructure Setup & Connection Details (Runbook)
To reproduce or reconnect the Windows miniQMT node, follow these exact steps.
- **Node IP**: `43.134.76.215`
- **Port**: `TCP 8000` (Must be allowed in Tencent Cloud Security Group & Windows Firewall for the Linux internal IP)
- **QMT UserData Path**: `C:\国金证券QMT交易端\userdata_mini`

### Windows Node Setup (Manual RDP)
1. Install Python 3.10 (64-bit) from python.org. Ensure "Add Python to PATH" is checked.
2. Open `cmd` and install dependencies:
   `pip install fastapi uvicorn xtquant`
3. Create `server.py` on the Desktop with the following bridge code:
   ```python
   import uvicorn
   from fastapi import FastAPI

   app = FastAPI(title='miniQMT Bridge')

   @app.get('/')
   def health_check():
       return {'status': 'ok', 'qmt_path': r'C:\国金证券QMT交易端\userdata_mini'}

   if __name__ == '__main__':
       uvicorn.run(app, host='0.0.0.0', port=8000)
   ```
4. Run the server: `python server.py`
5. Verify from Linux: `curl http://43.134.76.215:8000/`
