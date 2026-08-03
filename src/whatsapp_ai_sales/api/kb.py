"""Product knowledge base admin APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import kb_dep, require_admin

router = APIRouter(prefix="/api/kb", tags=["kb"], dependencies=[Depends(require_admin)])


class ProductIn(BaseModel):
    name: str
    sku: str | None = None
    sections: dict[str, str] = {}


class ProductOut(BaseModel):
    id: int
    name: str
    sku: str | None = None


@router.post("/products", response_model=ProductOut)
def create_product(payload: ProductIn, kb: kb_dep) -> ProductOut:
    product = kb.upsert_product(payload.name, sku=payload.sku, sections=payload.sections)
    return ProductOut(id=product.id, name=product.name, sku=product.sku)


@router.get("/products", response_model=list[ProductOut])
def list_products(kb: kb_dep) -> list[ProductOut]:
    return [ProductOut(id=p.id, name=p.name, sku=p.sku) for p in kb.list_products()]


@router.delete("/products/{product_id}")
def delete_product(product_id: int, kb: kb_dep) -> dict[str, str]:
    kb.delete_product(product_id)
    return {"status": "ok"}


@router.post("/reindex")
def reindex(kb: kb_dep) -> dict[str, str]:
    kb.reindex()
    return {"status": "ok"}
