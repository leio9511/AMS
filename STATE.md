# AMS Project State
- **Current Milestone**: M8 (QMT Windows Edge Refactoring)
- **Active Branch**: `master`
- **Current Status**: [Blocked] - `get_financial_data` on the QMT bridge consistently returns empty data structures, even though the service is healthy. This confirms that the issue is not a network or API signature problem, but likely a data availability issue at the source. The QMT instance on the Windows server is probably not logged in.
- **Next Action**: 
    - The spike script `spike_financial_data_schema.py` has been created and run, confirming the data retrieval issue across all known table names.
    - The AMS project is blocked until the Boss can confirm the Windows QMT client is logged in and has data. Once confirmed, the spike script can be re-run to verify data flow.
