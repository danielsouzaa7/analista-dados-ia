"""Python no navegador do visitante: o servidor pede a execução por SSE e espera o resultado num POST.

`executor` é o gerador que o agente consome; `entregar` é chamado pela rota POST /api/python/resultado."""
import logging
import secrets
import threading
import time
from collections.abc import Generator
from dataclasses import dataclass, field

from app import python_tool

PRAZO_S = 80  # 45 s de carga do Pyodide + 30 s de execução (prazos do front) + 5 s de folga para o POST
BATIDA_S = 2  # python_aguardando: devolve o controle ao Starlette a cada 2 s (abre a janela do cancelamento)
ERRO_PRAZO = {"saida": "", "erro": "O navegador não devolveu o resultado do Python a tempo."}
log = logging.getLogger("analista")


@dataclass
class _Pendente:
    id: str
    nonce: str
    pronto: threading.Event = field(default_factory=threading.Event)
    resultado: dict | None = None


_PENDENTES: dict[str, _Pendente] = {}  # por sessão: o agente roda uma ferramenta por vez
_LOCK = threading.Lock()


def executor(sessao_id: str):
    def rodar(id_: str, codigo: str, csv: str, restante: float) -> Generator[dict, None, dict]:
        pend = _Pendente(id_, secrets.token_hex(16))
        fim = time.monotonic() + min(PRAZO_S, restante)  # antes do yield: enviar o CSV não come o prazo
        with _LOCK:
            _PENDENTES[sessao_id] = pend
        log.info("python_pedido bytes=%d", len(csv) + len(codigo))
        try:
            yield {"evento": "python_pedido", "id": id_, "nonce": pend.nonce, "codigo": codigo,
                   "csv": csv, "preludio": python_tool.PRELUDIO}
            while not pend.pronto.wait(min(BATIDA_S, max(0.0, fim - time.monotonic()))):
                if time.monotonic() >= fim:
                    break
                yield {"evento": "python_aguardando", "id": id_}
        finally:  # sem yield nem return aqui: o GeneratorExit precisa atravessar
            with _LOCK:
                if _PENDENTES.get(sessao_id) is pend:
                    del _PENDENTES[sessao_id]
                resultado = pend.resultado  # ler e remover na mesma seção crítica
        return resultado or ERRO_PRAZO
    return rodar


def entregar(sessao_id: str, id_: str, nonce: str, saida: str, erro: str | None) -> bool:
    """Aceita o resultado uma única vez; qualquer recusa devolve False (a rota responde sempre igual)."""
    with _LOCK:
        pend = _PENDENTES.get(sessao_id)
        if pend is None or pend.id != id_ or pend.resultado is not None \
                or not secrets.compare_digest(nonce.encode(), pend.nonce.encode()):
            return False
        pend.resultado = {"saida": saida, "erro": erro}
        del _PENDENTES[sessao_id]
        pend.pronto.set()
        return True
