from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.cache import cache_get, cache_set, cache_delete
from app.config import settings
from app.database import get_db
from app.deps import get_current_admin

router = APIRouter(tags=["centres"])

# Only the default (unfiltered, first-page) listing is cached — that's the hot
# path a browsing client hits repeatedly. Filtered/paginated queries go
# straight to the DB rather than trying to cache every possible query shape.
CENTRES_DEFAULT_CACHE_KEY = "centres:list:default"
TESTS_DEFAULT_CACHE_KEY = "tests:list:default"


def _invalidate_listing_caches() -> None:
    """Called whenever a centre or test is created, so stale listings aren't served."""
    cache_delete(CENTRES_DEFAULT_CACHE_KEY, TESTS_DEFAULT_CACHE_KEY)


@router.post("/centres/", response_model=schemas.CentreOut, status_code=status.HTTP_201_CREATED)
def create_centre(
    payload: schemas.CentreCreate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    centre = models.DiagnosticCentre(name=payload.name, location=payload.location)
    db.add(centre)
    db.commit()
    db.refresh(centre)
    _invalidate_listing_caches()
    return centre


@router.get("/centres/", response_model=List[schemas.CentreOut])
def list_centres(
    location: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    is_default_query = location is None and skip == 0 and limit == 50

    if is_default_query:
        cached = cache_get(CENTRES_DEFAULT_CACHE_KEY)
        if cached is not None:
            return cached

    query = db.query(models.DiagnosticCentre).options(joinedload(models.DiagnosticCentre.tests))
    if location:
        query = query.filter(models.DiagnosticCentre.location.ilike(f"%{location}%"))
    centres = query.offset(skip).limit(min(limit, 100)).all()

    if is_default_query:
        serialized = [schemas.CentreOut.model_validate(c).model_dump(mode="json") for c in centres]
        cache_set(CENTRES_DEFAULT_CACHE_KEY, serialized, ttl_seconds=settings.cache_ttl_seconds)

    return centres


@router.get("/centres/{centre_id}", response_model=schemas.CentreOut)
def get_centre(centre_id: str, db: Session = Depends(get_db)):
    centre = (
        db.query(models.DiagnosticCentre)
        .options(joinedload(models.DiagnosticCentre.tests))
        .filter(models.DiagnosticCentre.id == centre_id)
        .first()
    )
    if not centre:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic centre not found")
    return centre


@router.post(
    "/centres/{centre_id}/tests/",
    response_model=schemas.TestOut,
    status_code=status.HTTP_201_CREATED,
)
def add_test_to_centre(
    centre_id: str,
    payload: schemas.TestCreate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    centre = db.query(models.DiagnosticCentre).filter(models.DiagnosticCentre.id == centre_id).first()
    if not centre:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic centre not found")

    test = models.DiagnosticTest(centre_id=centre.id, name=payload.name, price=payload.price)
    db.add(test)
    db.commit()
    db.refresh(test)
    _invalidate_listing_caches()
    return test


@router.get("/tests/", response_model=List[schemas.TestOut])
def list_tests(
    centre_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    is_default_query = centre_id is None and skip == 0 and limit == 50

    if is_default_query:
        cached = cache_get(TESTS_DEFAULT_CACHE_KEY)
        if cached is not None:
            return cached

    query = db.query(models.DiagnosticTest)
    if centre_id:
        query = query.filter(models.DiagnosticTest.centre_id == centre_id)
    tests = query.offset(skip).limit(min(limit, 100)).all()

    if is_default_query:
        serialized = [schemas.TestOut.model_validate(t).model_dump(mode="json") for t in tests]
        cache_set(TESTS_DEFAULT_CACHE_KEY, serialized, ttl_seconds=settings.cache_ttl_seconds)

    return tests


@router.get("/tests/{test_id}", response_model=schemas.TestOut)
def get_test(test_id: str, db: Session = Depends(get_db)):
    test = db.query(models.DiagnosticTest).filter(models.DiagnosticTest.id == test_id).first()
    if not test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic test not found")
    return test
