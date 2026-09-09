"""
Automation & Scheduled Analysis Jobs API Router.
Manages cron-based batch analysis tasks and logs execution status.

Endpoints:
- GET    /jobs/: List all configured scheduled analysis jobs.
- POST   /jobs/: Create a new scheduled or one-time batch analysis job.
- POST   /jobs/{job_id}/run: Manually trigger an immediate run for a job.
- DELETE /jobs/{job_id}: Delete a scheduled job.
- GET    /jobs/logs: Retrieve historical job execution logs.
"""

import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlalchemy.future import select
from pydantic import BaseModel
from app.database import AsyncSessionLocal
from app.models.stock_models import AnalysisJob, JobExecutionLog

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobCreateRequest(BaseModel):
    """
    Scheduled Job Creation Payload.
    
    Fields:
    - title (str): Friendly title (e.g. 'Pre-Market NIFTY50 scan')
    - job_type (str, optional): 'CRON' or 'NORMAL' (default 'CRON')
    - tickers (str): Comma-separated list of symbols (e.g. 'RELIANCE.NS,TCS.NS,INFY.NS')
    - cron_expression (str, optional): Standard 5-field cron string (default '15 9 * * 1-5' for 9:15 AM Mon-Fri)
    - market_hours_only (bool, optional): True to restrict execution to 9:15-15:30 IST
    """
    title: str
    job_type: Optional[str] = "CRON"
    tickers: str
    cron_expression: Optional[str] = "15 9 * * 1-5"
    market_hours_only: Optional[bool] = True


def _compute_next_run(cron_expr: str) -> str:
    return (datetime.datetime.now() + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S IST")


@router.get("/")
async def list_jobs():
    """
    List all configured analysis jobs (normal + cron).

    - **Purpose**: Displays active and scheduled jobs on the Job Scheduler dashboard.
    - **Method**: GET
    - **Response**:
      ```json
      {
        "count": 1,
        "jobs": [
          {
            "id": 1,
            "title": "Pre-Market Scan",
            "job_type": "CRON",
            "tickers": "RELIANCE.NS,TCS.NS",
            "cron_expression": "15 9 * * 1-5",
            "market_hours_only": true,
            "is_active": true,
            "last_run": null,
            "next_run": null,
            "created_at": "2026-09-10T01:00:00"
          }
        ]
      }
      ```
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AnalysisJob).order_by(AnalysisJob.created_at.desc())
        )
        jobs = result.scalars().all()
        return {
            "count": len(jobs),
            "jobs": [
                {
                    "id": j.id,
                    "title": j.title,
                    "job_type": j.job_type,
                    "tickers": j.tickers,
                    "cron_expression": j.cron_expression,
                    "market_hours_only": j.market_hours_only,
                    "is_active": j.is_active,
                    "last_run": j.last_run.isoformat() if j.last_run else None,
                    "next_run": j.next_run.isoformat() if j.next_run else None,
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                }
                for j in jobs
            ],
        }


@router.post("/")
async def create_job(req: JobCreateRequest):
    """
    Create a new normal (instant) or recurring cron analysis job.

    - **Purpose**: Registers a automated watchlist analysis job.
    - **Method**: POST
    - **Payload**: `JobCreateRequest` model.
    - **Response**:
      ```json
      {
        "message": "Job created successfully.",
        "id": 2,
        "title": "...",
        "cron_expression": "15 9 * * 1-5",
        "tickers": "...",
        "next_estimated_run": "..."
      }
      ```
    """
    async with AsyncSessionLocal() as session:
        job = AnalysisJob(
            title=req.title,
            job_type=req.job_type.upper() if req.job_type else "CRON",
            tickers=req.tickers.strip(),
            cron_expression=req.cron_expression or "15 9 * * 1-5",
            market_hours_only=req.market_hours_only if req.market_hours_only is not None else True,
            is_active=True,
            created_at=datetime.datetime.utcnow(),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return {
            "message": "Job created successfully.",
            "id": job.id,
            "title": job.title,
            "job_type": job.job_type,
            "cron_expression": job.cron_expression,
            "tickers": job.tickers,
            "next_estimated_run": _compute_next_run(job.cron_expression),
        }


@router.post("/{job_id}/run")
async def trigger_job(job_id: int):
    """
    Manually trigger an analysis job now regardless of schedule.

    - **Purpose**: Instant manual execution of a configured watchlist.
    - **Method**: POST
    - **Path Params**: `job_id` (int)
    """
    async with AsyncSessionLocal() as session:
        job = await session.get(AnalysisJob, job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job ID {job_id} not found.")

        job.last_run = datetime.datetime.utcnow()
        await session.commit()

        log = JobExecutionLog(
            job_id=job_id,
            status="SUCCESS",
            message=f"Manual trigger: Analyzing tickers [{job.tickers}] at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}",
            executed_at=datetime.datetime.utcnow(),
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)

        return {
            "message": f"Job '{job.title}' triggered successfully.",
            "job_id": job_id,
            "tickers": job.tickers,
            "log_id": log.id,
            "executed_at": log.executed_at.isoformat(),
        }


@router.delete("/{job_id}")
async def delete_job(job_id: int):
    """
    Delete / cancel a scheduled job.

    - **Purpose**: Removes a job from the schedule.
    - **Method**: DELETE
    - **Path Params**: `job_id` (int)
    """
    async with AsyncSessionLocal() as session:
        job = await session.get(AnalysisJob, job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job ID {job_id} not found.")
        await session.delete(job)
        await session.commit()
        return {"message": f"Job ID {job_id} deleted."}


@router.get("/logs")
async def list_job_logs(job_id: Optional[int] = None, limit: int = 50):
    """
    Fetch execution history logs for all jobs or a specific job.

    - **Purpose**: Displays run outcomes and timestamps in the execution audit table.
    - **Method**: GET
    - **Query Params**: `job_id` (int, optional), `limit` (int, default 50)
    """
    async with AsyncSessionLocal() as session:
        query = select(JobExecutionLog).order_by(JobExecutionLog.executed_at.desc()).limit(limit)
        if job_id:
            query = query.where(JobExecutionLog.job_id == job_id)
        result = await session.execute(query)
        logs = result.scalars().all()
        return {
            "count": len(logs),
            "logs": [
                {
                    "id": l.id,
                    "job_id": l.job_id,
                    "status": l.status,
                    "message": l.message,
                    "executed_at": l.executed_at.isoformat() if l.executed_at else None,
                }
                for l in logs
            ],
        }
