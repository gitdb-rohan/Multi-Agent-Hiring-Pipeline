from fastapi import APIRouter, Depends, HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
import hashlib
import os
import uuid

from app.dependencies import get_db
from app.infra.db import HRUser

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()

def hash_password(password: str) -> str:
    # A simple deterministic hash for this prototype. In prod, use bcrypt or passlib.
    salt = "hireflow_salt"
    return hashlib.sha256((password + salt).encode()).hexdigest()

class AuthRequest(BaseModel):
    email: str
    password: str

@router.post("/register")
async def register(req: AuthRequest, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    existing = await db.execute(select(HRUser).where(HRUser.email == req.email.lower()))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    new_user = HRUser(
        email=req.email.lower(),
        hashed_password=hash_password(req.password),
        auth_token=uuid.uuid4().hex
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"status": "success", "email": new_user.email, "token": new_user.auth_token}

@router.post("/login")
async def login(req: AuthRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(HRUser).where(HRUser.email == req.email.lower()))
    user = result.scalars().first()
    
    if not user or user.hashed_password != hash_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    # Generate new token on login
    user.auth_token = uuid.uuid4().hex
    await db.commit()
    
    return {"status": "success", "email": user.email, "token": user.auth_token}

async def get_current_hr(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db)
) -> str:
    """
    Dependency to validate the token and return the HR's email.
    """
    token = credentials.credentials
    result = await db.execute(select(HRUser).where(HRUser.auth_token == token))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
        
    return user.email
