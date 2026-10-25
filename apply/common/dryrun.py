"""Dry-run: roda o bot de ponta a ponta SEM enviar nada.

Com a variável `TRIVOR_DRY_RUN=1` cada bot executa o fluxo completo
até chegar na aba de preenchimento da candidatura (etapas/perguntas/
formulário) e PARA ali — não preenche campo, não envia, não anexa
currículo, não grava no relatório. Serve pra ver como o flow anda
sem deixar rastro na plataforma.

Os pontos de parada ficam em cada `candidatar_vaga*`, logo antes de
o preenchimento começar. Num bot onde o próprio clique de entrada
já pode enviar direto (ex.: "Candidatura rápida" do Solides), a
parada fica antes do clique. O caminho de produção (variável ausente)
cuesta zero: uma leitura de os.environ por candidatura.
"""
from __future__ import annotations

import os

__all__ = ["STATUS", "ativo"]

# Status que cada candidatar_vaga* devolve quando para no dry-run.
# Os mains reconhecem este valor pra pular salvar_log/registrar.
STATUS = "dry_run"


def ativo() -> bool:
    """True quando o processo está rodando em modo dry-run."""
    return os.environ.get("TRIVOR_DRY_RUN") == "1"
