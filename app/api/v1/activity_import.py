
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ...core.responses import error_response, success_response
from ...core.security import require_api_key
from ...schemas.activity_import import (
    ContextResolution, ImportBatchCreate, ImportRecordCreate,
    ProductResolution, ReviewCommand,
)
from ...services.activity_import import (
    ImportConflict, ImportNotFound, ImportValidation,
    approve_record, create_batch, get_batch_preview, get_record, list_batches,
    promote_record, reconcile_batch, reconcile_record, reject_record,
    resolve_product, set_context, stage_record,
)

router = APIRouter(
    prefix="/api/v1/activity-import",
    tags=["Activity Historical Migration"],
    dependencies=[Depends(require_api_key)],
)

def _err(exc):
    if isinstance(exc,ImportNotFound): code,status="IMPORT_NOT_FOUND",404
    elif isinstance(exc,ImportConflict): code,status="IMPORT_CONFLICT",409
    else: code,status="IMPORT_VALIDATION",422
    return JSONResponse(
        status_code=status,
        content=jsonable_encoder(error_response(code=code,message=str(exc))),
    )

@router.post("/batches", operation_id="createActivityImportBatch",
             summary="Create Historical Import Batch (ऐतिहासिक आयात बॅच तयार करा)")
def create_batch_api(req: ImportBatchCreate):
    try: return success_response(create_batch(req))
    except (ImportNotFound,ImportConflict,ImportValidation) as e: return _err(e)

@router.get("/batches", operation_id="listActivityImportBatches")
def list_batches_api(farm_id: UUID|None=None,status: str|None=None):
    return success_response(list_batches(farm_id,status))

@router.post("/batches/{batch_id}/records", operation_id="stageHistoricalActivity")
def stage_record_api(batch_id: UUID, req: ImportRecordCreate):
    try: return success_response(stage_record(batch_id,req))
    except (ImportNotFound,ImportConflict,ImportValidation) as e: return _err(e)

@router.get("/records/{record_id}", operation_id="getHistoricalImportRecord")
def get_record_api(record_id: UUID):
    try: return success_response(get_record(record_id))
    except (ImportNotFound,ImportConflict,ImportValidation) as e: return _err(e)

@router.post("/records/{record_id}/reconcile", operation_id="reconcileHistoricalActivity")
def reconcile_record_api(record_id: UUID):
    try: return success_response(reconcile_record(record_id))
    except (ImportNotFound,ImportConflict,ImportValidation) as e: return _err(e)

@router.post("/batches/{batch_id}/reconcile", operation_id="reconcileHistoricalBatch")
def reconcile_batch_api(batch_id: UUID):
    try: return success_response(reconcile_batch(batch_id))
    except (ImportNotFound,ImportConflict,ImportValidation) as e: return _err(e)

@router.get("/batches/{batch_id}/preview", operation_id="previewHistoricalImportBatch")
def preview_batch_api(batch_id: UUID):
    try: return success_response(get_batch_preview(batch_id))
    except (ImportNotFound,ImportConflict,ImportValidation) as e: return _err(e)

@router.post("/records/{record_id}/context", operation_id="resolveHistoricalActivityContext")
def context_api(record_id: UUID, req: ContextResolution):
    try: return success_response(set_context(record_id,req))
    except (ImportNotFound,ImportConflict,ImportValidation) as e: return _err(e)

@router.post("/records/{record_id}/product", operation_id="resolveHistoricalProduct")
def product_api(record_id: UUID, req: ProductResolution):
    try: return success_response(resolve_product(record_id,req))
    except (ImportNotFound,ImportConflict,ImportValidation) as e: return _err(e)

@router.post("/records/{record_id}/approve", operation_id="approveHistoricalActivity")
def approve_api(record_id: UUID, req: ReviewCommand):
    try: return success_response(approve_record(record_id,req))
    except (ImportNotFound,ImportConflict,ImportValidation) as e: return _err(e)

@router.post("/records/{record_id}/reject", operation_id="rejectHistoricalActivity")
def reject_api(record_id: UUID, req: ReviewCommand):
    try: return success_response(reject_record(record_id,req))
    except (ImportNotFound,ImportConflict,ImportValidation) as e: return _err(e)

@router.post("/records/{record_id}/promote", operation_id="promoteHistoricalActivity")
def promote_api(record_id: UUID, req: ReviewCommand):
    try: return success_response(promote_record(record_id,req))
    except (ImportNotFound,ImportConflict,ImportValidation) as e: return _err(e)
