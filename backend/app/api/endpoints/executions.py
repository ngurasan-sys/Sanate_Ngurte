"""Read-only view of the executions log — real order-result rows
published by ExecutionEngine (see engines/execution.py's
persist_execution publish) and persisted by AsyncPersistenceWorker.
"""

from fastapi import APIRouter

from backend.app.workers.persistence import persistence_worker

router = APIRouter(prefix="/api/v1/executions", tags=["executions"])


@router.get("")
async def list_executions(limit: int = 200):
    cursor = persistence_worker.conn.cursor()
    rows = cursor.execute(
        "SELECT timestamp, instrument, action, status FROM executions "
        "ORDER BY timestamp DESC LIMIT ?",
        [limit],
    ).fetchall()
    return [
        {"timestamp": str(r[0]), "instrument": r[1], "action": r[2], "status": r[3]}
        for r in rows
    ]
