import json
import uvicorn
from fastapi import FastAPI, HTTPException
import os

app = FastAPI(title='miniQMT Bridge')

OUTPUT_JSON_PATH = 'C:/Users/Administrator/Desktop/fundamentals.json'

@app.get('/api/health')
def health_check():
    return {'status': 'ok', 'qmt_path': r'C:\国金证券QMT交易端\userdata_mini'}

@app.get('/api/bulk_quote')
def bulk_quote():
    try:
        from xtquant import xtdata
        # Return what xtdata gives, or at least fake it if not connected for testing.
        return xtdata.get_full_tick([])
    except ImportError:
        return {"error": "xtquant not found", "data": {}}
    except Exception as e:
        return {"error": str(e), "data": {}}

@app.get('/api/fundamentals')
def get_fundamentals():
    if not os.path.exists(OUTPUT_JSON_PATH):
        raise HTTPException(status_code=404, detail="fundamentals.json not found")
    try:
        with open(OUTPUT_JSON_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="fundamentals.json is malformed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000)
