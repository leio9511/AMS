import uvicorn
from fastapi import FastAPI
import sys

app = FastAPI(title='miniQMT Bridge')

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

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000)
