"""Validated write contracts; money is integer paise and stock is whole packs."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PositiveInt = Annotated[int, Field(strict=True, gt=0, le=1_000_000)]
NonNegative = Annotated[int, Field(strict=True, ge=0, le=1_000_000_000)]


class WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NeedRequest(WriteModel):
    shop_id: PositiveInt
    product_id: PositiveInt
    qty: PositiveInt
    urgency: Literal["normal", "urgent"] = "normal"
    alt_product_ids: list[PositiveInt] = Field(default_factory=list, max_length=10)
    budget_paise: NonNegative | None = None
    min_shelf_days: int = Field(default=14, ge=0, le=3650)


class InventoryEdit(WriteModel):
    product_id: PositiveInt
    lot_id: PositiveInt | None = None
    qty: NonNegative | None = None
    delta: int | None = Field(default=None, strict=True, ge=-1_000_000, le=1_000_000)
    expected_version: PositiveInt | None = None
    cost_paise: NonNegative | None = None
    expiry_date: str | None = None
    condition: Literal["sealed", "opened", "damaged"] | None = None
    permit_share: bool | None = None
    slow: bool | None = None
    retained_floor: NonNegative | None = None

    @field_validator("expiry_date")
    @classmethod
    def valid_date(cls, value):
        if value is not None:
            date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def no_ambiguous_quantity(self):
        if self.qty is not None and self.delta is not None:
            raise ValueError("send an absolute quantity or a delta, not both")
        if self.lot_id is None and self.qty is None:
            raise ValueError("a new lot requires an explicit quantity")
        if self.lot_id is not None and self.expected_version is None:
            raise ValueError("editing a lot requires its expected_version")
        return self


class InventoryRequest(WriteModel):
    shop_id: PositiveInt
    changes: list[InventoryEdit] = Field(min_length=1, max_length=100)
    reason: str = Field(default="owner confirm", max_length=500)


class CaptureRequest(WriteModel):
    shop_id: PositiveInt
    text: str = Field(min_length=1, max_length=20_000)


class QuoteRequest(WriteModel):
    product_id: PositiveInt
    supplier_name: str = Field(min_length=1, max_length=120)
    price_paise: PositiveInt
    min_order_packs: PositiveInt = 1
    lead_days: int = Field(default=1, ge=0, le=365)


class RunParameters(WriteModel):
    time_limit_ms: int = Field(default=5000, ge=100, le=10_000)
    min_shelf_days: int = Field(default=14, ge=0, le=3650)
    radius_km: float = Field(default=3.0, gt=0, le=50)
    include_purchases: bool = True
    urgent_only: bool = False
    shop_ids: list[PositiveInt] | None = Field(default=None, min_length=1, max_length=25)


class PlanningRequest(WriteModel):
    case_id: Literal["cluster-main"] = "cluster-main"
    params: RunParameters = Field(default_factory=RunParameters)


class ShopPreferences(WriteModel):
    expected_version: PositiveInt
    cash_limit_paise: NonNegative
    sharing_opt_in: bool
