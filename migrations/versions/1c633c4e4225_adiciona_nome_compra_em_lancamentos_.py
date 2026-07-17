"""adiciona nome_compra em lancamentos_fatura

Revision ID: 1c633c4e4225
Revises: 48f00aeff861
Create Date: 2026-07-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c633c4e4225'
down_revision: Union[str, None] = '48f00aeff861'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Campo opcional preenchido pelo usuário pra nomear uma compra
    # específica (ex: "Tênis Leo"). Nenhum lançamento antigo tem esse nome
    # até o usuário dar um — null pra todos os já gravados (ver CLAUDE.md
    # "Compatibilidade com dados existentes").
    with op.batch_alter_table('lancamentos_fatura', schema=None) as batch_op:
        batch_op.add_column(sa.Column('nome_compra', sa.String(length=150), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('lancamentos_fatura', schema=None) as batch_op:
        batch_op.drop_column('nome_compra')
