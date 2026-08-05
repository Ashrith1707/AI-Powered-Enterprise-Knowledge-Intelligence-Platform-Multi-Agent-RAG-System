"""Introspection endpoint: lists registered agents and their capabilities."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.coordinator import CoordinatorAgent
from app.core.database import get_db

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
def list_agents(db: Session = Depends(get_db)):
    return CoordinatorAgent(db).registry.all_agents()
