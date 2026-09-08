import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlalchemy.future import select
from pydantic import BaseModel
from app.database import AsyncSessionLocal
from app.models.stock_models import AnalysisJob, JobExecutionLog

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobCreateRequest(BaseModel):
    title: str
    job_type: Optional[str] = "CRON"            # NORMAL / CRON
    tickers: str                                  # comma-separated e.g. "RELIANCE.NS,TCS.NS"
    cron_expression: Optional[str] = "15 9 * * 1-5"  # default: 9:15 AM Mon-Fri IST
    market_hours_only: Optional[bool] = True


def _compute_next_run(cron_expr: str) -> str:
    """Naive next-run estimator for display purposes (replace with APScheduler in production)."""
    return (datetime.datetime.now() + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S IST")


@router.get("/")
async def list_jobs():
    """List all configured analysis jobs (normal + cron)."""
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
    """Create a new normal (instant) or cron analysis job."""
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
    """Manually trigger an analysis job now regardless of its schedule."""
    async with AsyncSessionLocal() as session:
        job = await session.get(AnalysisJob, job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job ID {job_id} not found.")

        # Update last_run
        job.last_run = datetime.datetime.utcnow()
        await session.commit()

        # Log execution
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
    """Delete / cancel a scheduled job."""
    async with AsyncSessionLocal() as session:
        job = await session.get(AnalysisJob, job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job ID {job_id} not found.")
        await session.delete(job)
        await session.commit()
        return {"message": f"Job ID {job_id} deleted."}


@router.get("/logs")
async def list_job_logs(job_id: Optional[int] = None, limit: int = 50):
    """Fetch execution history logs for all jobs or a specific job."""
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
