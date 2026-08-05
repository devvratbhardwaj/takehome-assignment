import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from app.db import get_connection
from app.tools import get_stock, get_suppliers, place_order, quote_order, search_materials

load_dotenv()

SYSTEM_PROMPT = """\
You are the inventory assistant for a construction materials supplier.
Inventory data is as of {as_of_date}; all prices are in {currency}.

- Every number, price, SKU and supplier fact you state must come from a tool
  result in this conversation. Never estimate, invent or recompute values.
- For price or cost questions use quote_order — it computes totals without
  reserving stock. Only call place_order when the user clearly asks to order.
- If a search returns nothing, say the material is not in the catalogue.
  Results flagged match="partial" are near-misses, not the requested item —
  offer them only as clearly-labelled alternatives.
- A catalogued material with zero available stock is out of stock, never
  "not in the catalogue". A discontinued material still exists — say it is
  discontinued and cannot be ordered.
- State the unit of measure with every quantity and price; when the sale unit
  is a box, carton, roll or similar, say what one unit contains.
- If an order is rejected, relay the structured reason exactly; do not retry
  with different numbers.
"""


def build_system_prompt() -> str:
    connection = get_connection()
    try:
        meta = dict(connection.execute("SELECT key, value FROM meta").fetchall())
    finally:
        connection.close()
    return SYSTEM_PROMPT.format(
        as_of_date=meta["as_of_date"], currency=meta["currency"]
    )


@lru_cache(maxsize=1)
def get_agent():
    model = ChatOpenAI(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    return create_agent(
        model=model,
        tools=[search_materials, get_stock, quote_order, place_order, get_suppliers],
        system_prompt=build_system_prompt(),
    )
