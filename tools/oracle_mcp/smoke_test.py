"""Prueba de humo del servidor MCP via stdio (mismo transporte que usa Bob).

Uso:  uv run --directory tools/oracle_mcp python smoke_test.py
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent

CASES = [
    ("list_objects", {"schema": "BI_SEMANTIC"}),
    ("describe_object", {"schema": "BI_SEMANTIC", "name": "VW_DIM_VEHICULO"}),
    ("run_readonly_query", {"sql": "SELECT COUNT(*) AS TOTAL FROM BI_SEMANTIC.VW_DIM_VEHICULO"}),
    ("run_readonly_query", {"sql": "SELECT COUNT(*) FROM EDW_3FN.DUMMY"}),
    ("run_readonly_query", {"sql": "DELETE FROM BI_SEMANTIC.VW_DIM_VEHICULO"}),
    ("run_readonly_query", {"sql": "SELECT 1 FROM DUAL; DROP TABLE X"}),
    ("run_readonly_query", {"sql": "WITH a AS (SELECT 1 n FROM DUAL) SELECT * FROM a FOR UPDATE"}),
    ("describe_object", {"schema": "EDW_3FN", "name": "X"}),
]


def _brief(text: str) -> str:
    try:
        data = json.loads(text)
    except ValueError:
        return text[:200]
    if "error" in data:
        return f"{data['error']}: {data['detail'][:160]}"
    return f"columns={data['columns'][:6]} rows={data['rows'][:3]} row_count={data['row_count']}"


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / "server.py")])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            print("TOOLS:", tools)
            for name, args in CASES:
                res = await session.call_tool(name, args)
                print(f"- {name} {json.dumps(args)[:90]}\n    -> {_brief(res.content[0].text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
