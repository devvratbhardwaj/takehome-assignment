from pydantic import BaseModel, ConfigDict, Field


class Supplier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: str
    name: str
    location: str
    standard_lead_time_days: int = Field(ge=0)
    payment_terms: str


class Material(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    description: str
    category: str
    spec_grade: str | None
    unit_of_measure: str
    unit_price: float = Field(ge=0)
    currency: str
    qty_on_hand: int = Field(ge=0)
    qty_reserved: int = Field(ge=0)
    reorder_point: int = Field(ge=0)
    min_order_qty: int = Field(ge=0)
    primary_supplier_id: str
    warehouse: str
    discontinued: bool

    @property
    def qty_available(self) -> int:
        ## Can be negative in case of over-allocation
        return self.qty_on_hand - self.qty_reserved


class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str
    as_of_date: str
    currency: str
    notes: str
    definitions: dict[str, str]


class InventoryData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: Meta
    suppliers: list[Supplier]
    materials: list[Material]

