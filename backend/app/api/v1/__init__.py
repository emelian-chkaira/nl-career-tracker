from fastapi import APIRouter
from . import auth, jobs, companies, me, analytics, cv, admin, tasks, mail

api = APIRouter(prefix="/api/v1")
for m in (auth, jobs, companies, me, analytics, cv, admin, tasks, mail): api.include_router(m.router)
api.include_router(mail.ai)
