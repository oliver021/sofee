"""Harness del agente (deepagents sobre LangGraph).

La fachada hacia el resto de la API vive en los módulos de este paquete; el
frontend nunca ve tipos de LangGraph (ver docs/deep-agent-roadmap.md §3.1).
"""

import os

# LangGraph lee LANGGRAPH_STRICT_MSGPACK al importar su serde, así que debe fijarse
# antes de cualquier import de langgraph. Este __init__ se ejecuta primero.
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
